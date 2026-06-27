from typing import List, Optional, Tuple
from dataclasses import dataclass
import numpy as np
import math

from gagarin.dem_loader import DEMLoader
from gagarin.correlator import CorrelationMetrics
from gagarin.geo_utils import offset_coords, offset_coords_batch
from gagarin.config import Config
from gagarin.constants import EARTH_RADIUS


@dataclass
class RecoveryResult:
    recovered_lat: float
    recovered_lon: float
    correlation: float
    confidence: float
    search_grid_lats: List[float]
    search_grid_lons: List[float]
    correlation_map: np.ndarray
    dr_lat: float
    dr_lon: float
    true_lat: Optional[float] = None
    true_lon: Optional[float] = None


class LostRecoveryModule:
    def __init__(self, dem: DEMLoader, config: Config):
        self.dem = dem
        self.config = config

    def detect_lost_segments(
        self, estimates: list, min_consecutive: int = 5
    ) -> List[Tuple[int, int]]:
        segments = []
        start = None
        for i, est in enumerate(estimates):
            qual = None
            if est and hasattr(est, "quality") and est.quality:
                qual = est.quality.get("quality")
            is_poor = qual is None or qual == "poor" or qual == "none"
            if is_poor and start is None:
                start = i
            elif not is_poor and start is not None:
                if i - start >= min_consecutive:
                    segments.append((start, i - 1))
                start = None
        if start is not None and len(estimates) - start >= min_consecutive:
            segments.append((start, len(estimates) - 1))
        return segments

    def recover(
        self,
        profile: np.ndarray,
        dr_lat: float,
        dr_lon: float,
        azimuth_deg: float,
        speed_ms: float,
        search_radius_m: float = 500.0,
        grid_size: int = 7,
    ) -> RecoveryResult:
        n_points = len(profile)
        dt = 1.0 / self.config.nmea_freq_hz
        d_step = speed_ms * dt

        half_span = search_radius_m
        offsets_1d = np.linspace(-half_span, half_span, grid_size)

        grid_lats = np.zeros((grid_size, grid_size))
        grid_lons = np.zeros((grid_size, grid_size))
        corr_map = np.zeros((grid_size, grid_size))

        azimuth_rad = math.radians(azimuth_deg)

        for ri in range(grid_size):
            for ci in range(grid_size):
                offset_north = offsets_1d[ri]
                offset_east = offsets_1d[ci]
                dlat = offset_north / EARTH_RADIUS
                dlon = offset_east / (EARTH_RADIUS * math.cos(math.radians(dr_lat)))
                hyp_lat = dr_lat + math.degrees(dlat)
                hyp_lon = dr_lon + math.degrees(dlon)

                hyp_lat, hyp_lon = self.dem.normalize_coordinates(
                    np.array([hyp_lat]), np.array([hyp_lon])
                )
                hyp_lat = float(hyp_lat[0])
                hyp_lon = float(hyp_lon[0])

                grid_lats[ri, ci] = hyp_lat
                grid_lons[ri, ci] = hyp_lon

                distances = np.arange(n_points, dtype=np.float64) * d_step
                lats = np.full(n_points, hyp_lat)
                lons = np.full(n_points, hyp_lon)
                lats, lons = offset_coords_batch(lats, lons, distances, azimuth_rad, hyp_lat)
                lats, lons = self.dem.normalize_coordinates(lats, lons)
                ref = self.dem.elevation_batch(lats, lons)
                corr = CorrelationMetrics.ncc(profile, ref)
                corr_map[ri, ci] = corr

        best_ri, best_ci = np.unravel_index(np.argmax(corr_map), corr_map.shape)
        best_corr = float(corr_map[best_ri, best_ci])
        recovered_lat = float(grid_lats[best_ri, best_ci])
        recovered_lon = float(grid_lons[best_ri, best_ci])

        corr_flat = corr_map.flatten()
        median_corr = float(np.median(corr_flat))
        sharpness = (best_corr - median_corr) / (best_corr + 1e-12)
        confidence = float(np.clip(sharpness, 0.0, 1.0))

        return RecoveryResult(
            recovered_lat=recovered_lat,
            recovered_lon=recovered_lon,
            correlation=best_corr,
            confidence=confidence,
            search_grid_lats=grid_lats.tolist(),
            search_grid_lons=grid_lons.tolist(),
            correlation_map=corr_map,
            dr_lat=dr_lat,
            dr_lon=dr_lon,
        )

    def compute_distance_m(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
        return 2 * EARTH_RADIUS * math.atan2(math.sqrt(a), math.sqrt(1 - a))
