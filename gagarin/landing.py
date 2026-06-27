from typing import Optional
from dataclasses import dataclass
import math
import numpy as np
from scipy.ndimage import uniform_filter

from gagarin.dem_loader import DEMLoader

M_PER_DEG_LAT = 111320.0


@dataclass
class LandingZone:
    lat: float
    lon: float
    flatness_m: float
    area_m2: float
    cell_count: int
    polygon_lats: list
    polygon_lons: list


class LandingZoneFinder:
    def __init__(self, dem: DEMLoader):
        self.dem = dem

    @staticmethod
    def _window_size_px(window_size_m: float, res_deg: float) -> int:
        px = max(3, int(window_size_m / (res_deg * M_PER_DEG_LAT)))
        return px + 1 if px % 2 == 0 else px

    @staticmethod
    def _search_px(radius_m: float, res_deg: float) -> int:
        return max(3, int(radius_m / (res_deg * M_PER_DEG_LAT)))

    @staticmethod
    def _local_std(data: np.ndarray, window_px: int) -> np.ndarray:
        mean = uniform_filter(data, size=window_px, mode="reflect")
        mean_sq = uniform_filter(data ** 2, size=window_px, mode="reflect")
        return np.sqrt(np.maximum(mean_sq - mean ** 2, 0))

    @staticmethod
    def _expand_flat_bbox(
        flat_mask: np.ndarray, start_r: int, start_c: int
    ) -> tuple:
        used = np.zeros_like(flat_mask, dtype=bool)
        stack = [(start_r, start_c)]
        used[start_r, start_c] = True
        min_r = max_r = start_r
        min_c = max_c = start_c

        while stack:
            r, c = stack.pop()
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nr, nc = r + dr, c + dc
                if (
                    0 <= nr < flat_mask.shape[0]
                    and 0 <= nc < flat_mask.shape[1]
                    and not used[nr, nc]
                    and flat_mask[nr, nc]
                ):
                    used[nr, nc] = True
                    stack.append((nr, nc))
                    min_r = min(min_r, nr)
                    max_r = max(max_r, nr)
                    min_c = min(min_c, nc)
                    max_c = max(max_c, nc)

        return min_r, max_r, min_c, max_c, int(np.sum(used))

    def find_landing_zone(
        self,
        center_lat: float,
        center_lon: float,
        search_radius_m: float = 500.0,
        window_size_m: float = 30.0,
        flatness_threshold_m: float = 5.0,
        min_area_m2: float = 400.0,
    ) -> Optional[LandingZone]:
        lons, lats, data = self.dem.get_geographic_grid()

        if len(lats) < 2 or len(lons) < 2:
            return None

        res_lat = abs(np.mean(np.diff(lats)))
        res_lon = abs(np.mean(np.diff(lons)))
        if res_lat < 1e-10 or res_lon < 1e-10:
            return None

        ri = int(np.argmin(np.abs(lats - center_lat)))
        ci = int(np.argmin(np.abs(lons - center_lon)))

        cos_center = math.cos(math.radians(center_lat))

        search_px_lat = self._search_px(search_radius_m, res_lat)
        search_px_lon = self._search_px(search_radius_m, res_lon * cos_center)
        window_px = self._window_size_px(window_size_m, res_lat)

        r0 = max(0, ri - search_px_lat)
        r1 = min(len(lats), ri + search_px_lat + 1)
        c0 = max(0, ci - search_px_lon)
        c1 = min(len(lons), ci + search_px_lon + 1)

        if r1 - r0 < window_px or c1 - c0 < window_px:
            return None

        crop = data[r0:r1, c0:c1].astype(np.float64)

        local_std = self._local_std(crop, window_px)

        pad = window_px // 2
        inner = local_std[pad : local_std.shape[0] - pad, pad : local_std.shape[1] - pad]
        if inner.size == 0:
            return None

        cri = min(ri - r0, inner.shape[0] - 1)
        cci = min(ci - c0, inner.shape[1] - 1)

        flat = inner < flatness_threshold_m

        if not np.any(flat):
            return None

        candidates = np.argwhere(flat)
        dists = np.sqrt(
            ((candidates[:, 0] - cri) ** 2 + (candidates[:, 1] - cci) ** 2).astype(np.float64)
        )
        best = candidates[int(np.argmin(dists))]
        best_r, best_c = int(best[0]), int(best[1])

        min_r, max_r, min_c, max_c, cell_count = self._expand_flat_bbox(flat, best_r, best_c)

        zlat = float(lats[r0 + pad + best_r])
        zlon = float(lons[c0 + pad + best_c])
        zone_flatness = float(inner[best_r, best_c])

        poly_lat1 = float(lats[r0 + pad + min_r])
        poly_lat2 = float(lats[r0 + pad + max_r])
        poly_lon1 = float(lons[c0 + pad + min_c])
        poly_lon2 = float(lons[c0 + pad + max_c])

        poly_lats = [poly_lat1, poly_lat1, poly_lat2, poly_lat2]
        poly_lons = [poly_lon1, poly_lon2, poly_lon2, poly_lon1]

        m_per_deg_lon = M_PER_DEG_LAT * cos_center
        dh = abs(poly_lat2 - poly_lat1) * M_PER_DEG_LAT
        dw = abs(poly_lon2 - poly_lon1) * m_per_deg_lon
        area_m2 = dh * dw

        if area_m2 < min_area_m2:
            return None

        return LandingZone(
            lat=zlat,
            lon=zlon,
            flatness_m=zone_flatness,
            area_m2=area_m2,
            cell_count=cell_count,
            polygon_lats=poly_lats,
            polygon_lons=poly_lons,
        )
