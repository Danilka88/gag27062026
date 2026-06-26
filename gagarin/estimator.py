from typing import Tuple, Optional
import numpy as np
import math

from gagarin.correlator import MatchResult
from gagarin.config import Config


class VelocityEstimator:
    def __init__(self, config: Config = None):
        self.config = config or Config.default()

    def estimate(
        self,
        match: MatchResult,
        center_lat: float,
        center_lon: float,
    ) -> dict:
        dt = 1.0 / self.config.nmea_freq_hz
        speed_estimate = match.speed_ms
        azimuth_estimate = match.azimuth_deg

        lag_distance = match.lag_samples * speed_estimate * dt
        correction_lat, correction_lon = self._offset_coords(
            center_lat, center_lon,
            lag_distance,
            azimuth_estimate,
        )

        return {
            "azimuth_deg": azimuth_estimate,
            "speed_ms": speed_estimate,
            "speed_kmh": speed_estimate * 3.6,
            "position_lat": correction_lat,
            "position_lon": correction_lon,
            "correlation": match.correlation,
            "confidence": match.confidence,
            "lag_samples": match.lag_samples,
            "lag_distance_m": lag_distance,
            "terrain_roughness": match.terrain_roughness,
            "timestamp": None,
        }

    @staticmethod
    def _offset_coords(
        lat: float,
        lon: float,
        distance_m: float,
        azimuth_deg: float,
    ) -> Tuple[float, float]:
        R = 6371000.0
        az_rad = math.radians(azimuth_deg)
        dlat = distance_m * math.cos(az_rad) / R
        dlon = distance_m * math.sin(az_rad) / (R * math.cos(math.radians(lat)))
        return lat + math.degrees(dlat), lon + math.degrees(dlon)
