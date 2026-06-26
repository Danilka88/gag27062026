from typing import Optional
from dataclasses import dataclass
import math

from gagarin.correlator import MatchResult
from gagarin.config import Config
from gagarin.geo_utils import offset_coords


@dataclass
class NavigationEstimate:
    azimuth_deg: float
    speed_ms: float
    position_lat: float
    position_lon: float
    correlation: float
    confidence: float
    lag_samples: int
    lag_distance_m: float
    terrain_roughness: float
    timestamp: Optional[float] = None
    quality: Optional[dict] = None
    filtered_lat: Optional[float] = None
    filtered_lon: Optional[float] = None
    filtered_speed_ms: Optional[float] = None


class VelocityEstimator:
    def __init__(self, config: Config = None):
        self.config = config or Config.default()

    def estimate(
        self,
        match: MatchResult,
        center_lat: float,
        center_lon: float,
    ) -> NavigationEstimate:
        dt = 1.0 / self.config.nmea_freq_hz
        speed_estimate = match.speed_ms
        azimuth_estimate = match.azimuth_deg
        azimuth_rad = math.radians(azimuth_estimate)

        lag_distance = match.lag_samples * speed_estimate * dt
        correction_lat, correction_lon = offset_coords(
            center_lat, center_lon,
            lag_distance,
            azimuth_rad,
        )

        return NavigationEstimate(
            azimuth_deg=azimuth_estimate,
            speed_ms=speed_estimate,
            position_lat=correction_lat,
            position_lon=correction_lon,
            correlation=match.correlation,
            confidence=match.confidence,
            lag_samples=match.lag_samples,
            lag_distance_m=lag_distance,
            terrain_roughness=match.terrain_roughness,
        )