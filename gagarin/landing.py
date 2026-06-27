from typing import List, Optional, Tuple
from dataclasses import dataclass
import math
import numpy as np
from scipy.ndimage import uniform_filter

from gagarin.dem_loader import DEMLoader
from gagarin.geo_utils import haversine_m


@dataclass
class LandingZone:
    lat: float
    lon: float
    flatness_m: float
    area_m2: float
    cell_count: int
    polygon_lats: List[float]
    polygon_lons: List[float]


class LandingZoneFinder:
    def __init__(self, dem: DEMLoader):
        self.dem = dem
        self._grid_cache: Optional[Tuple[np.ndarray, np.ndarray, np.ndarray]] = None

    def _get_grid(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        if self._grid_cache is None:
            self._grid_cache = self.dem.get_geographic_grid()
        return self._grid_cache

    def find_landing_zone(
        self,
        center_lat: float,
        center_lon: float,
        search_radius_m: float = 500.0,
        window_size_m: float = 30.0,
        flatness_threshold_m: float = 5.0,
        min_area_m2: float = 400.0,
    ) -> Optional[LandingZone]:
        lons, lats, data = self._get_grid()

        if len(lats) < 2 or len(lons) < 2:
            return None

        res_lat = abs(np.mean(np.diff(lats)))
        res_lon = abs(np.mean(np.diff(lons)))
        if res_lat < 1e-10 or res_lon < 1e-10:
            return None

        ri = int(np.argmin(np.abs(lats - center_lat)))
        ci = int(np.argmin(np.abs(lons - center_lon)))

        m_per_deg_lat = 111320.0
        cos_center = math.cos(math.radians(center_lat))

        search_px_lat = max(3, int(search_radius_m / (res_lat * m_per_deg_lat)))
        search_px_lon = max(3, int(search_radius_m / (res_lon * m_per_deg_lat * cos_center)))

        window_px = max(3, int(window_size_m / (res_lat * m_per_deg_lat)))
        if window_px % 2 == 0:
            window_px += 1

        r0 = max(0, ri - search_px_lat)
        r1 = min(len(lats), ri + search_px_lat + 1)
        c0 = max(0, ci - search_px_lon)
        c1 = min(len(lons), ci + search_px_lon + 1)

        if r1 - r0 < window_px or c1 - c0 < window_px:
            return None

        crop = data[r0:r1, c0:c1].astype(np.float64)

        mean = uniform_filter(crop, size=window_px, mode="reflect")
        mean_sq = uniform_filter(crop ** 2, size=window_px, mode="reflect")
        local_std = np.sqrt(np.maximum(mean_sq - mean ** 2, 0))

        pad = window_px // 2
        inner = local_std[pad : local_std.shape[0] - pad, pad : local_std.shape[1] - pad]
        if inner.size == 0:
            return None

        cri = min(ri - r0, inner.shape[0] - 1)
        cci = min(ci - c0, inner.shape[1] - 1)

        flat = inner < flatness_threshold_m

        if np.any(flat):
            candidates = np.argwhere(flat)
            dists = np.sqrt(
                ((candidates[:, 0] - cri) ** 2 + (candidates[:, 1] - cci) ** 2).astype(np.float64)
            )
            best = candidates[int(np.argmin(dists))]
        else:
            best_flat = np.unravel_index(int(np.argmin(inner)), inner.shape)
            best = np.array([best_flat[0], best_flat[1]])

        best_r, best_c = int(best[0]), int(best[1])
        zlat = float(lats[r0 + pad + best_r])
        zlon = float(lons[c0 + pad + best_c])
        zone_flatness = float(inner[best_r, best_c])

        if np.any(flat):
            used = np.zeros_like(flat, dtype=bool)
            stack = [(best_r, best_c)]
            used[best_r, best_c] = True
            min_r, max_r = best_r, best_r
            min_c, max_c = best_c, best_c

            while stack:
                cr, cc = stack.pop()
                for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    nr, nc = cr + dr, cc + dc
                    if (
                        0 <= nr < flat.shape[0]
                        and 0 <= nc < flat.shape[1]
                        and not used[nr, nc]
                        and flat[nr, nc]
                    ):
                        used[nr, nc] = True
                        stack.append((nr, nc))
                        min_r = min(min_r, nr)
                        max_r = max(max_r, nr)
                        min_c = min(min_c, nc)
                        max_c = max(max_c, nc)

            poly_lat1 = float(lats[r0 + pad + min_r])
            poly_lat2 = float(lats[r0 + pad + max_r])
            poly_lon1 = float(lons[c0 + pad + min_c])
            poly_lon2 = float(lons[c0 + pad + max_c])

            poly_lats = [poly_lat1, poly_lat1, poly_lat2, poly_lat2]
            poly_lons = [poly_lon1, poly_lon2, poly_lon2, poly_lon1]

            dh = abs(poly_lat2 - poly_lat1) * m_per_deg_lat
            dw = abs(poly_lon2 - poly_lon1) * m_per_deg_lon
            area_m2 = dh * dw
            cell_count = int(np.sum(used))
        else:
            poly_lats = [zlat] * 4
            poly_lons = [zlon] * 4
            area_m2 = 0.0
            cell_count = 1

        if not np.any(flat) or area_m2 < min_area_m2:
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
