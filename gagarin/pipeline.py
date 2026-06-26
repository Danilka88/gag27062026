from typing import List, Optional, Callable
import time
import threading
from collections import deque
import numpy as np

from gagarin.nmea_parser import NMEAParser, NMEAReading
from gagarin.profile import extract_terrain_profile
from gagarin.correlator import TERCOMCorrelator, MatchResult
from gagarin.estimator import VelocityEstimator
from gagarin.eskf import ErrorStateKalmanFilter
from gagarin.quality import assess_match
from gagarin.dem_loader import DEMLoader
from gagarin.config import Config


class NavigationPipeline:
    def __init__(
        self,
        dem: DEMLoader,
        config: Config = None,
        on_update: Optional[Callable] = None,
    ):
        self.config = config or Config.default()
        self.parser = NMEAParser()
        self.correlator = TERCOMCorrelator(dem, config)
        self.estimator = VelocityEstimator(config)
        self.dem = dem

        self.buffer: deque[NMEAReading] = deque()
        self.readings: List[NMEAReading] = []

        self.center_lat: Optional[float] = None
        self.center_lon: Optional[float] = None
        self.last_result: Optional[MatchResult] = None
        self.last_estimate: Optional[dict] = None
        self.on_update = on_update

        self.kf: Optional[ErrorStateKalmanFilter] = None
        if config.kalman_enabled:
            self.kf = ErrorStateKalmanFilter(dt=1.0 / config.nmea_freq_hz)

        self.total_distance = 0.0
        self.last_distance_trigger = 0.0
        self._last_update_time = None
        self.running = False

    @property
    def is_initialized(self) -> bool:
        return self.center_lat is not None

    def initialize(self, lat: float, lon: float):
        self.center_lat = lat
        self.center_lon = lon
        if self.kf:
            self.kf.set_position(lat, lon)

    def feed_line(self, line: str) -> Optional[dict]:
        reading = self.parser.parse_line(line)
        if reading is None:
            return None
        return self.feed_reading(reading)

    def feed_reading(self, reading: NMEAReading) -> Optional[dict]:
        self.buffer.append(reading)
        self.readings.append(reading)

        if len(self.buffer) > self.config.window_size:
            self.buffer.popleft()

        if not self.is_initialized:
            return None

        if len(self.buffer) < self.config.window_size:
            return None

        if self.config.adaptive_sampling:
            dt = 1.0 / self.config.nmea_freq_hz
            if len(self.readings) >= 2:
                prev = self.readings[-2]
                dist_estimate = 50.0
                self.total_distance += dist_estimate

                if self.total_distance - self.last_distance_trigger < self.config.adaptive_min_distance_m:
                    return None
                self.last_distance_trigger = self.total_distance

        profile = extract_terrain_profile(
            list(self.buffer), self.config.baro_altitude
        )
        if len(profile) < 5:
            return None

        match = self.correlator.search(profile, self.center_lat, self.center_lon)
        if match is None:
            return None

        self.last_result = match
        estimate = self.estimator.estimate(match, self.center_lat, self.center_lon)

        R = 6371000.0
        az_rad = np.radians(estimate["azimuth_deg"])
        speed = estimate["speed_ms"]
        vx = speed * np.sin(az_rad)
        vy = speed * np.cos(az_rad)

        dt_center = 1.0 / self.config.nmea_freq_hz
        R = 6371000.0
        cos_lat = np.cos(np.radians(estimate["position_lat"]))

        # Dead reckoning: advance center by 1 step (speed * dt)
        dr_dlat = speed * np.cos(az_rad) * dt_center / R
        dr_dlon = speed * np.sin(az_rad) * dt_center / (R * cos_lat)

        # Lag correction: accumulated position error from cross-correlation
        lag_m = estimate["lag_distance_m"]
        corr_dlat = lag_m * np.cos(az_rad) / R
        corr_dlon = lag_m * np.sin(az_rad) / (R * cos_lat)

        self.center_lat += np.degrees(dr_dlat + corr_dlat)
        self.center_lon += np.degrees(dr_dlon + corr_dlon)

        if self.kf:
            self.kf.predict()
            self.kf.update_position(estimate["position_lat"], estimate["position_lon"])
            self.kf.update_velocity(vx, vy)
            self.kf.reset()
            kf_state = self.kf.get_state()
            estimate["filtered_lat"] = kf_state["lat"]
            estimate["filtered_lon"] = kf_state["lon"]
            estimate["filtered_speed_ms"] = kf_state["speed_ms"]
            self.center_lat = kf_state["lat"]
            self.center_lon = kf_state["lon"]

        quality = assess_match(match)
        estimate["quality"] = quality
        estimate["timestamp"] = reading.timestamp
        estimate["terrain_roughness"] = match.terrain_roughness

        self.last_estimate = estimate

        if self.on_update:
            self.on_update(estimate)

        return estimate

    def feed_file(self, path: str) -> List[dict]:
        results = []
        with open(path) as f:
            for line in f:
                result = self.feed_line(line.strip())
                if result is not None:
                    results.append(result)
        return results

    def stream_file(self, path: str, speed_factor: float = 1.0):
        dt = 1.0 / self.config.nmea_freq_hz
        with open(path) as f:
            for line in f:
                result = self.feed_line(line.strip())
                if result is not None:
                    print(
                        f"[NAV] az={result['azimuth_deg']:.1f}° "
                        f"v={result['speed_ms']:.1f} m/s "
                        f"conf={result['confidence']:.2f} "
                        f"pos=({result['position_lat']:.5f}, {result['position_lon']:.5f})"
                    )
                time.sleep(dt / speed_factor)

    def get_correlation_data(self) -> Optional[dict]:
        if self.last_result is None:
            return None
        return {
            "observed": self.last_result.observed_profile.tolist(),
            "reference": self.last_result.reference_profile.tolist(),
            "azimuth": self.last_result.azimuth_deg,
            "speed": self.last_result.speed_ms,
            "correlation": self.last_result.correlation,
            "confidence": self.last_result.confidence,
        }
