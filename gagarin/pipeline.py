from typing import List, Optional, Callable
import time
import numpy as np

from gagarin.nmea_parser import NMEAParser, NMEAReading
from gagarin.correlator import TERCOMCorrelator, MatchResult
from gagarin.estimator import VelocityEstimator, NavigationEstimate
from gagarin.eskf import ErrorStateKalmanFilter
from gagarin.buffer import NMEABuffer
from gagarin.quality import assess_match
from gagarin.dem_loader import DEMLoader
from gagarin.config import Config
from gagarin.constants import EARTH_RADIUS


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

        self.nmea_buffer = NMEABuffer(self.config)

        self.center_lat: Optional[float] = None
        self.center_lon: Optional[float] = None
        self.last_result: Optional[MatchResult] = None
        self.last_estimate: Optional[NavigationEstimate] = None
        self.on_update = on_update

        self.kf: Optional[ErrorStateKalmanFilter] = None
        if config.kalman_enabled:
            self.kf = ErrorStateKalmanFilter(dt=1.0 / config.nmea_freq_hz)

    @property
    def is_initialized(self) -> bool:
        return self.center_lat is not None

    def initialize(self, lat: float, lon: float):
        b = self.dem.bounds
        if not (b[1] <= lat <= b[3] and b[0] <= lon <= b[2]):
            raise ValueError(
                f"Стартовая позиция ({lat:.4f}, {lon:.4f}) за пределами DEM "
                f"({b[1]:.4f}–{b[3]:.4f} lat, {b[0]:.4f}–{b[2]:.4f} lon)"
            )
        self.center_lat = lat
        self.center_lon = lon
        if self.kf:
            self.kf.set_position(lat, lon)

    def feed_line(self, line: str) -> Optional[NavigationEstimate]:
        reading = self.parser.parse_line(line)
        if reading is None:
            return None
        return self.feed_reading(reading)

    def feed_reading(self, reading: NMEAReading) -> Optional[NavigationEstimate]:
        self.nmea_buffer.add(reading)

        if not self.is_initialized or not self.nmea_buffer.is_full():
            return None

        if self.config.adaptive_sampling:
            speed = self.last_estimate.speed_ms if self.last_estimate else self.config.default_speed
            if not self.nmea_buffer.advance_distance(speed):
                return None

        profile = self.nmea_buffer.get_profile(self.config.baro_altitude)
        if len(profile) < 5:
            return None

        match = self.correlator.search(profile, self.center_lat, self.center_lon)
        if match is None:
            if self.kf:
                self.kf.predict()
            self._dead_reckon_forward()
            return None

        self.last_result = match
        estimate = self.estimator.estimate(match, self.center_lat, self.center_lon)
        self._update_center(estimate)
        self._apply_kalman(estimate)

        estimate.quality = assess_match(match)
        estimate.timestamp = reading.timestamp
        self.last_estimate = estimate

        if self.on_update:
            self.on_update(estimate)

        return estimate

    def _update_center(self, estimate: NavigationEstimate):
        az_rad = np.radians(estimate.azimuth_deg)
        speed = estimate.speed_ms
        dt_center = 1.0 / self.config.nmea_freq_hz
        cos_lat = np.cos(np.radians(estimate.position_lat))

        dr_lat = speed * np.cos(az_rad) * dt_center / EARTH_RADIUS
        dr_lon = speed * np.sin(az_rad) * dt_center / (EARTH_RADIUS * cos_lat)

        lag_m = estimate.lag_distance_m
        corr_lat = lag_m * np.cos(az_rad) / EARTH_RADIUS
        corr_lon = lag_m * np.sin(az_rad) / (EARTH_RADIUS * cos_lat)

        self.center_lat += np.degrees(dr_lat + corr_lat)
        self.center_lon += np.degrees(dr_lon + corr_lon)

    def _dead_reckon_forward(self):
        dt = 1.0 / self.config.nmea_freq_hz
        if self.last_estimate:
            az_rad = np.radians(self.last_estimate.azimuth_deg)
            speed = self.last_estimate.speed_ms
        else:
            az_rad = np.radians(self.config.default_azimuth)
            speed = self.config.default_speed
        cos_lat = np.cos(np.radians(self.center_lat))
        dlat = speed * np.cos(az_rad) * dt / EARTH_RADIUS
        dlon = speed * np.sin(az_rad) * dt / (EARTH_RADIUS * cos_lat)
        self.center_lat += np.degrees(dlat)
        self.center_lon += np.degrees(dlon)

    def _apply_kalman(self, estimate: NavigationEstimate):
        if not self.kf:
            return
        az_rad = np.radians(estimate.azimuth_deg)
        speed = estimate.speed_ms
        vx = speed * np.sin(az_rad)
        vy = speed * np.cos(az_rad)

        self.kf.predict()
        self.kf.update_position(estimate.position_lat, estimate.position_lon)
        self.kf.update_velocity(vx, vy)
        self.kf.reset()
        kf_state = self.kf.get_state()
        estimate.filtered_lat = kf_state["lat"]
        estimate.filtered_lon = kf_state["lon"]
        estimate.filtered_speed_ms = kf_state["speed_ms"]
        self.center_lat = kf_state["lat"]
        self.center_lon = kf_state["lon"]

    def feed_file(self, path: str) -> List[NavigationEstimate]:
        results: List[NavigationEstimate] = []
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
                        f"[НАВ] az={result.azimuth_deg:.1f}° "
                        f"v={result.speed_ms:.1f} м/с "
                        f"conf={result.confidence:.2f} "
                        f"pos=({result.position_lat:.5f}, {result.position_lon:.5f})"
                    )
                time.sleep(dt / speed_factor)


