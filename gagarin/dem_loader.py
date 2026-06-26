from typing import Optional, Tuple
import numpy as np
import rioxarray
import xarray as xr
from pyproj import Transformer


class DEMLoader:
    def __init__(self, path: str):
        self._ds: Optional[xr.DataArray] = None
        self._transformer_lonlat_to_xy: Optional[Transformer] = None
        self._transformer_xy_to_lonlat: Optional[Transformer] = None
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
        self._transformer_lonlat_to_xy = Transformer.from_crs("EPSG:4326", src_crs, always_xy=True)
        self._transformer_xy_to_lonlat = Transformer.from_crs(src_crs, "EPSG:4326", always_xy=True)

    @property
    def crs(self):
        return self._ds.rio.crs

    @property
    def bounds(self):
        return self._ds.rio.bounds()

    @property
    def resolution(self):
        res = self._ds.rio.resolution()
        return abs(res[0]), abs(res[1])

    def _lonlat_to_pixel(self, lon: float, lat: float) -> Tuple[float, float]:
        x, y = self._transformer_lonlat_to_xy.transform(lon, lat)
        transform = self._ds.rio.transform()
        col, row = ~transform * (x, y)
        return float(row), float(col)

    def _lonlat_to_pixel_batch(self, lons: np.ndarray, lats: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        xs, ys = self._transformer_lonlat_to_xy.transform(lons.tolist(), lats.tolist())
        xs = np.asarray(xs, dtype=np.float64)
        ys = np.asarray(ys, dtype=np.float64)
        transform = self._ds.rio.transform()
        cols = (xs - transform.c) / transform.a
        rows = (ys - transform.f) / transform.e
        return rows, cols

    def elevation(self, lat: float, lon: float) -> float:
        row, col = self._lonlat_to_pixel(lon, lat)
        return self._bilinear_interp(row, col)

    def elevation_batch(self, lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
        rows, cols = self._lonlat_to_pixel_batch(np.asarray(lons, dtype=np.float64), np.asarray(lats, dtype=np.float64))

        rows_f = np.floor(rows).astype(np.int64)
        cols_f = np.floor(cols).astype(np.int64)
        dr = rows - rows_f
        dc = cols - cols_f

        h, w = self._ds.shape
        rows_f = np.clip(rows_f, 0, h - 2)
        cols_f = np.clip(cols_f, 0, w - 2)

        data = self._ds.values
        v00 = data[rows_f, cols_f]
        v10 = data[np.clip(rows_f + 1, 0, h - 1), cols_f]
        v01 = data[rows_f, np.clip(cols_f + 1, 0, w - 1)]
        v11 = data[np.clip(rows_f + 1, 0, h - 1), np.clip(cols_f + 1, 0, w - 1)]

        result = (
            v00 * (1 - dr) * (1 - dc)
            + v10 * dr * (1 - dc)
            + v01 * (1 - dr) * dc
            + v11 * dr * dc
        )
        return result

    def _bilinear_interp(self, row: float, col: float) -> float:
        data = self._ds.values
        h, w = data.shape
        r0 = int(np.floor(row))
        c0 = int(np.floor(col))
        if r0 < 0 or r0 >= h - 1 or c0 < 0 or c0 >= w - 1:
            return float(data[max(0, min(r0, h - 1)), max(0, min(c0, w - 1))])
        dr = row - r0
        dc = col - c0
        v00 = float(data[r0, c0])
        v10 = float(data[r0 + 1, c0])
        v01 = float(data[r0, c0 + 1])
        v11 = float(data[r0 + 1, c0 + 1])
        return (
            v00 * (1 - dr) * (1 - dc)
            + v10 * dr * (1 - dc)
            + v01 * (1 - dr) * dc
            + v11 * dr * dc
        )

    def get_elevation_grid(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        data = self._ds.values
        ny, nx = data.shape
        transform = self._ds.rio.transform()
        xs = np.arange(nx) * transform.a + transform.c
        ys = np.arange(ny) * transform.e + transform.f
        return xs, ys, data

    def get_geographic_grid(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        xs, ys, data = self.get_elevation_grid()
        lons = np.empty_like(xs)
        lats = np.empty_like(ys)
        for i, x in enumerate(xs):
            _, lons[i] = self._transformer_xy_to_lonlat.transform(x, ys[0])
        for j, y in enumerate(ys):
            lats[j], _ = self._transformer_xy_to_lonlat.transform(xs[0], y)
        return lons, lats, data

    def normalize_coordinates(self, lats: np.ndarray, lons: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        bounds = self.bounds
        lats = np.clip(lats, bounds[1], bounds[3])
        lons = np.clip(lons, bounds[0], bounds[2])
        return lats, lons


def load_dem(path: str) -> DEMLoader:
    return DEMLoader(path)
