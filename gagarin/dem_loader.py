from typing import Optional, Tuple
import numpy as np
import rioxarray
import xarray as xr
from pyproj import Transformer


class CoordinateTransformer:
    def __init__(self, src_crs, transform):
        self._transformer_lonlat_to_xy = Transformer.from_crs("EPSG:4326", src_crs, always_xy=True)
        self._transformer_xy_to_lonlat = Transformer.from_crs(src_crs, "EPSG:4326", always_xy=True)
        self._transform = transform

    def lonlat_to_pixel(self, lon: float, lat: float) -> Tuple[float, float]:
        x, y = self._transformer_lonlat_to_xy.transform(lon, lat)
        col, row = ~self._transform * (x, y)
        return float(row), float(col)

    def lonlat_to_pixel_batch(self, lons: np.ndarray, lats: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        xs, ys = self._transformer_lonlat_to_xy.transform(lons.tolist(), lats.tolist())
        xs = np.asarray(xs, dtype=np.float64)
        ys = np.asarray(ys, dtype=np.float64)
        cols = (xs - self._transform.c) / self._transform.a
        rows = (ys - self._transform.f) / self._transform.e
        return rows, cols

    def get_elevation_grid(self, data: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        ny, nx = data.shape
        xs = np.arange(nx) * self._transform.a + self._transform.c
        ys = np.arange(ny) * self._transform.e + self._transform.f
        return xs, ys, data

    def get_geographic_grid(self, data: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        xs, ys, _ = self.get_elevation_grid(data)
        _, lons = self._transformer_xy_to_lonlat.transform(xs.tolist(), [ys[0]] * len(xs))
        lats, _ = self._transformer_xy_to_lonlat.transform([xs[0]] * len(ys), ys.tolist())
        return np.array(lons), np.array(lats), data


class DEMInterpolator:
    def __init__(self, data: np.ndarray):
        self._data = data

    @property
    def shape(self):
        return self._data.shape

    def elevation(self, row: float, col: float) -> float:
        h, w = self._data.shape
        r0 = int(np.floor(row))
        c0 = int(np.floor(col))
        if r0 < 0 or r0 >= h - 1 or c0 < 0 or c0 >= w - 1:
            return float(self._data[max(0, min(r0, h - 1)), max(0, min(c0, w - 1))])
        dr = row - r0
        dc = col - c0
        v00 = float(self._data[r0, c0])
        v10 = float(self._data[r0 + 1, c0])
        v01 = float(self._data[r0, c0 + 1])
        v11 = float(self._data[r0 + 1, c0 + 1])
        return (
            v00 * (1 - dr) * (1 - dc)
            + v10 * dr * (1 - dc)
            + v01 * (1 - dr) * dc
            + v11 * dr * dc
        )

    def elevation_batch(self, rows: np.ndarray, cols: np.ndarray) -> np.ndarray:
        rows_f = np.floor(rows).astype(np.int64)
        cols_f = np.floor(cols).astype(np.int64)
        dr = rows - rows_f
        dc = cols - cols_f

        h, w = self._data.shape
        rows_f = np.clip(rows_f, 0, h - 2)
        cols_f = np.clip(cols_f, 0, w - 2)

        v00 = self._data[rows_f, cols_f]
        v10 = self._data[np.clip(rows_f + 1, 0, h - 1), cols_f]
        v01 = self._data[rows_f, np.clip(cols_f + 1, 0, w - 1)]
        v11 = self._data[np.clip(rows_f + 1, 0, h - 1), np.clip(cols_f + 1, 0, w - 1)]

        return (
            v00 * (1 - dr) * (1 - dc)
            + v10 * dr * (1 - dc)
            + v01 * (1 - dr) * dc
            + v11 * dr * dc
        )

    def get_raw_data(self) -> np.ndarray:
        return self._data


class DEMLoader:
    def __init__(self, path: str):
        self._ds: Optional[xr.DataArray] = None
        self._coord: Optional[CoordinateTransformer] = None
        self._interp: Optional[DEMInterpolator] = None
        self._bounds: Optional[Tuple[float, float, float, float]] = None
        self._crs = "EPSG:4326"
        self._load(path)

    def _load(self, path: str):
        self._ds = rioxarray.open_rasterio(path, masked=True).squeeze()
        if "spatial_ref" in self._ds.coords:
            self._ds = self._ds.drop_vars("spatial_ref")

        crs = self._ds.rio.crs
        if crs is None:
            crs = "EPSG:4326"
            self._ds.rio.write_crs(crs, inplace=True)

        src_crs = self._ds.rio.crs or "EPSG:4326"
        transform = self._ds.rio.transform()
        self._crs = src_crs
        self._coord = CoordinateTransformer(src_crs, transform)
        self._interp = DEMInterpolator(self._ds.values)
        self._bounds = self._ds.rio.bounds()

    @property
    def crs(self):
        return self._crs

    @property
    def bounds(self):
        return self._bounds

    @property
    def resolution(self):
        res = self._ds.rio.resolution()
        return abs(res[0]), abs(res[1])

    def elevation(self, lat: float, lon: float) -> float:
        row, col = self._coord.lonlat_to_pixel(lon, lat)
        return self._interp.elevation(row, col)

    def elevation_batch(self, lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
        rows_pix, cols_pix = self._coord.lonlat_to_pixel_batch(
            np.asarray(lons, dtype=np.float64), np.asarray(lats, dtype=np.float64)
        )
        return self._interp.elevation_batch(rows_pix, cols_pix)

    def get_elevation_grid(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        return self._coord.get_elevation_grid(self._interp.get_raw_data())

    def get_geographic_grid(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        return self._coord.get_geographic_grid(self._interp.get_raw_data())

    def normalize_coordinates(self, lats: np.ndarray, lons: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        b = self._bounds
        lats = np.clip(lats, b[1], b[3])
        lons = np.clip(lons, b[0], b[2])
        return lats, lons


def load_dem(path: str) -> DEMLoader:
    return DEMLoader(path)
