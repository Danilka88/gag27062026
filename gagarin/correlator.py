from typing import List, Optional
from dataclasses import dataclass
import numpy as np

from gagarin.dem_loader import DEMLoader
from gagarin.config import Config
from gagarin.geo_utils import offset_coords_batch


@dataclass
class MatchResult:
    azimuth_deg: float
    speed_ms: float
    correlation: float
    lag_samples: int
    confidence: float
    terrain_roughness: float
    reference_profile: np.ndarray
    observed_profile: np.ndarray


@dataclass
class Hypothesis:
    azimuth_deg: float
    speed_ms: float
    correlation: float
    lag: int


class CorrelationMetrics:
    @staticmethod
    def ncc(a: np.ndarray, b: np.ndarray) -> float:
        a = a.astype(np.float64)
        b = b.astype(np.float64)
        a_mean = a - np.mean(a)
        b_mean = b - np.mean(b)
        denom = np.sqrt(np.sum(a_mean ** 2) * np.sum(b_mean ** 2))
        if denom < 1e-12:
            return 0.0
        return float(np.sum(a_mean * b_mean) / denom)

    @staticmethod
    def cross_correlation(a: np.ndarray, b: np.ndarray) -> np.ndarray:
        return np.correlate(a, b, mode="same")

    @staticmethod
    def compute_confidence(corr_profile: np.ndarray, roughness: float) -> float:
        max_corr = float(np.max(np.abs(corr_profile)))
        if len(corr_profile) < 3 or max_corr < 0.01:
            return 0.0
        sorted_vals = np.sort(np.abs(corr_profile))
        median_corr = float(sorted_vals[len(sorted_vals) // 2])
        sharpness = (max_corr - median_corr) / (max_corr + 1e-12)
        terrain_factor = min(roughness / 20.0, 1.0)
        return float(np.clip(sharpness * terrain_factor, 0.0, 1.0))


class HypothesisSearch:
    def __init__(self, dem: DEMLoader, config: Config):
        self.dem = dem
        self.config = config
        self._cached_coarse_azimuths: Optional[np.ndarray] = None

    def build_reference_profile(
        self,
        center_lat: float,
        center_lon: float,
        azimuth_deg: float,
        speed_ms: float,
        n_points: int,
    ) -> np.ndarray:
        dt = 1.0 / self.config.nmea_freq_hz
        d_step = speed_ms * dt
        azimuth_rad = np.radians(azimuth_deg)

        distances = np.arange(n_points, dtype=np.float64) * d_step
        lats = np.full(n_points, center_lat)
        lons = np.full(n_points, center_lon)
        lats, lons = offset_coords_batch(lats, lons, distances, azimuth_rad, center_lat)
        lats, lons = self.dem.normalize_coordinates(lats, lons)
        return self.dem.elevation_batch(lats, lons)

    def search_grid(
        self,
        profile: np.ndarray,
        center_lat: float,
        center_lon: float,
        azimuths: np.ndarray,
        speeds: np.ndarray,
        min_std: float = None,
    ) -> List[Hypothesis]:
        n = len(profile)
        hypotheses = []
        for az in azimuths:
            for sp in speeds:
                ref = self.build_reference_profile(center_lat, center_lon, az, sp, n)
                if min_std is not None and np.std(ref) < min_std:
                    continue
                corr = CorrelationMetrics.ncc(profile, ref)
                hypotheses.append(Hypothesis(az, sp, corr, 0))
        return hypotheses

    def coarse_search(
        self,
        profile: np.ndarray,
        center_lat: float,
        center_lon: float,
    ) -> List[Hypothesis]:
        cfg = self.config
        n_az = int(360 / cfg.coarse_azimuth_step)
        if self._cached_coarse_azimuths is None or len(self._cached_coarse_azimuths) != n_az:
            self._cached_coarse_azimuths = np.arange(0, 360, cfg.coarse_azimuth_step)
        speeds = np.linspace(cfg.speed_range_ms[0], cfg.speed_range_ms[1], cfg.n_speed_hypotheses)
        hypotheses = self.search_grid(profile, center_lat, center_lon, self._cached_coarse_azimuths, speeds, cfg.terrain_std_threshold * 0.5)
        hypotheses.sort(key=lambda h: h.correlation, reverse=True)
        return hypotheses[:10]

    def fine_search(
        self,
        profile: np.ndarray,
        center_lat: float,
        center_lon: float,
        top_hypotheses: List[Hypothesis],
    ) -> List[Hypothesis]:
        cfg = self.config
        fine_hypotheses = []
        for hyp in top_hypotheses:
            fine_azs = np.arange(
                max(0, hyp.azimuth_deg - cfg.fine_azimuth_margin),
                min(360, hyp.azimuth_deg + cfg.fine_azimuth_margin + 1e-9),
                cfg.fine_azimuth_step,
            )
            n_speeds = max(5, cfg.n_speed_hypotheses // 3)
            fine_speeds = np.linspace(
                max(cfg.speed_range_ms[0], hyp.speed_ms - cfg.fine_speed_margin),
                min(cfg.speed_range_ms[1], hyp.speed_ms + cfg.fine_speed_margin),
                n_speeds,
            )
            fine_hypotheses.extend(self.search_grid(profile, center_lat, center_lon, fine_azs, fine_speeds))

        fine_hypotheses.sort(key=lambda h: h.correlation, reverse=True)
        return fine_hypotheses[:10]


class TERCOMCorrelator:
    def __init__(self, dem: DEMLoader, config: Config = None):
        cfg = config or Config.default()
        self._hypothesis_search = HypothesisSearch(dem, cfg)
        self.config = cfg

    def search(
        self,
        observed_profile: np.ndarray,
        center_lat: float,
        center_lon: float,
    ) -> Optional[MatchResult]:
        if len(observed_profile) < 5:
            return None

        roughness = float(np.std(observed_profile))
        if roughness < self.config.terrain_std_threshold:
            return None

        coarse = self._hypothesis_search.coarse_search(observed_profile, center_lat, center_lon)
        if not coarse:
            return None

        fine = self._hypothesis_search.fine_search(
            observed_profile, center_lat, center_lon, coarse[:self.config.coarse_top_n]
        )
        if not fine:
            fine = coarse[:1]

        best = fine[0]

        ref_profile = self._hypothesis_search.build_reference_profile(
            center_lat, center_lon,
            best.azimuth_deg, best.speed_ms,
            len(observed_profile),
        )

        best_corr = CorrelationMetrics.ncc(observed_profile, ref_profile)

        corr_full = CorrelationMetrics.cross_correlation(
            observed_profile.astype(np.float64),
            ref_profile.astype(np.float64),
        )
        best_lag = int(np.argmax(corr_full)) - len(observed_profile) // 2

        confidence = CorrelationMetrics.compute_confidence(corr_full, roughness)

        return MatchResult(
            azimuth_deg=best.azimuth_deg,
            speed_ms=best.speed_ms,
            correlation=best_corr,
            lag_samples=best_lag,
            confidence=confidence,
            terrain_roughness=roughness,
            reference_profile=ref_profile,
            observed_profile=observed_profile,
        )
