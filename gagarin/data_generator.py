from typing import List, Iterator
from dataclasses import dataclass
import numpy as np
import math

from gagarin.dem_loader import DEMLoader
from gagarin.config import Config
from gagarin.geo_utils import offset_coords_batch


@dataclass
class FlightParams:
    start_lat: float
    start_lon: float
    azimuth_deg: float
    speed_ms: float
    duration_s: float = 30.0

    @property
    def azimuth_rad(self) -> float:
        return math.radians(self.azimuth_deg)


class DataGenerator:
    def __init__(self, dem: DEMLoader, config: Config = None):
        self.dem = dem
        self.config = config or Config.default()
        self.rng = np.random.default_rng(self.config.seed)

    def generate_profile(
        self, params: FlightParams, noise_std: float = 3.0
    ) -> np.ndarray:
        n = int(params.duration_s * self.config.nmea_freq_hz)
        dt = 1.0 / self.config.nmea_freq_hz
        distances = np.arange(n) * params.speed_ms * dt
        start_lats = np.full(n, params.start_lat)
        start_lons = np.full(n, params.start_lon)
        lats, lons = offset_coords_batch(start_lats, start_lons, distances, params.azimuth_rad, params.start_lat)

        true_terrain = self.dem.elevation_batch(lats, lons)
        noise = self.rng.normal(0, noise_std, size=n)
        radar_altitudes = self.config.baro_altitude - true_terrain + noise
        min_val = np.min(radar_altitudes)
        if min_val < 1.0:
            radar_altitudes += 1.0 - min_val
        return radar_altitudes

    def generate_nmea_lines(
        self, params: FlightParams, noise_std: float = 3.0
    ) -> List[str]:
        return list(self.stream_nmea(params, noise_std))

    def generate_nmea_file(self, path: str, params: FlightParams, noise_std: float = 3.0):
        lines = self.generate_nmea_lines(params, noise_std)
        with open(path, "w") as f:
            for line in lines:
                f.write(line + "\n")
        return path

    def stream_nmea(
        self, params: FlightParams, noise_std: float = 3.0
    ) -> Iterator[str]:
        radar_alts = self.generate_profile(params, noise_std)
        base_time = 123519.0
        for i, alt in enumerate(radar_alts):
            ts = base_time + i * (1.0 / self.config.nmea_freq_hz)
            hhmmss = self._seconds_to_nmea_time(ts)
            alt_str = f"{alt:.1f}"
            sentence = (
                f"$GPGGA,{hhmmss},,,,,,,,{alt_str},M,,,"
            )
            csum = self._nmea_checksum(sentence[1:])
            yield f"{sentence}*{csum:02X}"

    @staticmethod
    def _seconds_to_nmea_time(seconds: float) -> str:
        h = int(seconds // 3600) % 24
        m = int((seconds % 3600) // 60)
        s = seconds % 60
        return f"{h:02d}{m:02d}{s:06.3f}"

    @staticmethod
    def _nmea_checksum(s: str) -> int:
        c = 0
        for ch in s:
            c ^= ord(ch)
        return c
