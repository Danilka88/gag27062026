from typing import List, Tuple, Optional
from dataclasses import dataclass
import numpy as np
from numba import njit

from gagarin.dem_loader import DEMLoader
from gagarin.config import Config


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


class TERCOMCorrelator:
    def __init__(self, dem: DEMLoader, config: Config = None):
        self.dem = dem
        self.config = config or Config.default()

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

        coarse_hypotheses = self._coarse_search(observed_profile, center_lat, center_lon)
        if not coarse_hypotheses:
            return None

        fine_hypotheses = self._fine_search(
            observed_profile, center_lat, center_lon, coarse_hypotheses[:self.config.coarse_top_n]
        )
        if not fine_hypotheses:
            fine_hypotheses = coarse_hypotheses[:1]

        best = fine_hypotheses[0]

        ref_profile = self._build_reference_profile(
            center_lat, center_lon,
            best.azimuth_deg, best.speed_ms,
            len(observed_profile),
        )

        best_corr = self._ncc(observed_profile, ref_profile)

        corr_full = self._cross_correlation(
            observed_profile.astype(np.float64),
            ref_profile.astype(np.float64),
        )
        best_lag = int(np.argmax(np.abs(corr_full))) - len(observed_profile) // 2

        confidence = self._compute_confidence(corr_full, roughness)

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

    def _coarse_search(
        self,
        profile: np.ndarray,
        center_lat: float,
        center_lon: float,
    ) -> List[Hypothesis]:
        n = len(profile)
        azimuths = np.arange(0, 360, self.config.coarse_azimuth_step)
        speeds = np.linspace(
            self.config.speed_range_ms[0],
            self.config.speed_range_ms[1],
            self.config.n_speed_hypotheses,
        )

        hypotheses = []
        for az in azimuths:
            for sp in speeds:
                ref = self._build_reference_profile(center_lat, center_lon, az, sp, n)
                if np.std(ref) < self.config.terrain_std_threshold * 0.5:
                    continue
                corr = self._ncc(profile, ref)
                hypotheses.append(Hypothesis(az, sp, corr, 0))

        hypotheses.sort(key=lambda h: h.correlation, reverse=True)
        return hypotheses[:10]

    def _fine_search(
        self,
        profile: np.ndarray,
        center_lat: float,
        center_lon: float,
        top_hypotheses: List[Hypothesis],
    ) -> List[Hypothesis]:
        n = len(profile)
        fine_hypotheses = []

        for hyp in top_hypotheses:
            az_center = hyp.azimuth_deg
            sp_center = hyp.speed_ms

            fine_azs = np.arange(
                max(0, az_center - self.config.fine_azimuth_margin),
                min(360, az_center + self.config.fine_azimuth_margin + 1e-9),
                self.config.fine_azimuth_step,
            )
            n_speeds = max(5, self.config.n_speed_hypotheses // 3)
            fine_speeds = np.linspace(
                max(self.config.speed_range_ms[0], sp_center - 15),
                min(self.config.speed_range_ms[1], sp_center + 15),
                n_speeds,
            )

            for az in fine_azs:
                for sp in fine_speeds:
                    ref = self._build_reference_profile(center_lat, center_lon, az, sp, n)
                    corr = self._ncc(profile, ref)
                    fine_hypotheses.append(Hypothesis(az, sp, corr, 0))

        fine_hypotheses.sort(key=lambda h: h.correlation, reverse=True)
        return fine_hypotheses[:10]

    def _build_reference_profile(
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

        R = 6371000.0
        cos_lat = np.cos(np.radians(center_lat))
        lat_rad = np.radians(center_lat)

        distances = np.arange(n_points, dtype=np.float64) * d_step
        dlat = distances * np.cos(azimuth_rad) / R
        dlon = distances * np.sin(azimuth_rad) / (R * cos_lat)

        lats = center_lat + np.degrees(dlat)
        lons = center_lon + np.degrees(dlon)
        lats, lons = self.dem.normalize_coordinates(lats, lons)
        return self.dem.elevation_batch(lats, lons)

    @staticmethod
    def _ncc(a: np.ndarray, b: np.ndarray) -> float:
        a = a.astype(np.float64)
        b = b.astype(np.float64)
        a_mean = a - np.mean(a)
        b_mean = b - np.mean(b)
        denom = np.sqrt(np.sum(a_mean ** 2) * np.sum(b_mean ** 2))
        if denom < 1e-12:
            return 0.0
        return float(np.sum(a_mean * b_mean) / denom)

    @staticmethod
    def _cross_correlation(a: np.ndarray, b: np.ndarray) -> np.ndarray:
        return np.correlate(a, b, mode="same")

    @staticmethod
    def _compute_confidence(corr_profile: np.ndarray, roughness: float) -> float:
        max_corr = float(np.max(np.abs(corr_profile)))
        if len(corr_profile) < 3 or max_corr < 0.01:
            return 0.0
        sorted_vals = np.sort(np.abs(corr_profile))
        median_corr = float(sorted_vals[len(sorted_vals) // 2])
        sharpness = (max_corr - median_corr) / (max_corr + 1e-12)
        terrain_factor = min(roughness / 20.0, 1.0)
        return float(np.clip(sharpness * terrain_factor, 0.0, 1.0))
