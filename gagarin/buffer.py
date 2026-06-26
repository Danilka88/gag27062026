from typing import List, Optional
from collections import deque
import numpy as np

from gagarin.nmea_parser import NMEAReading
from gagarin.profile import extract_terrain_profile
from gagarin.config import Config


class NMEABuffer:
    def __init__(self, config: Config):
        self.config = config
        self._buffer: deque[NMEAReading] = deque()
        self._readings: List[NMEAReading] = []
        self._total_distance = 0.0
        self._last_distance_trigger = 0.0

    @property
    def buffer(self) -> deque[NMEAReading]:
        return self._buffer

    @property
    def readings(self) -> List[NMEAReading]:
        return self._readings

    def add(self, reading: NMEAReading) -> None:
        self._buffer.append(reading)
        self._readings.append(reading)
        if len(self._buffer) > self.config.window_size:
            self._buffer.popleft()

    def get_profile(self, baro_altitude: Optional[float] = None) -> np.ndarray:
        profile = extract_terrain_profile(list(self._buffer), baro_altitude)
        return profile

    def is_full(self) -> bool:
        return len(self._buffer) >= self.config.window_size

    def advance_distance(self, speed_ms: float) -> bool:
        dist = speed_ms / self.config.nmea_freq_hz
        self._total_distance += dist
        if self._total_distance - self._last_distance_trigger < self.config.adaptive_min_distance_m:
            return False
        self._last_distance_trigger = self._total_distance
        return True
