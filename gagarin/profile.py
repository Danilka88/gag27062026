from typing import List, Optional
import numpy as np

from gagarin.nmea_parser import NMEAReading
from gagarin.config import Config


def extract_terrain_profile(
    readings: List[NMEAReading],
    baro_altitude: Optional[float] = None,
) -> np.ndarray:
    if not readings:
        return np.array([])

    baro = baro_altitude if baro_altitude is not None else Config.default().baro_altitude
    altitudes = np.array([r.altitude for r in readings])
    terrain = baro - altitudes
    terrain = np.maximum(terrain, -500.0)
    return terrain


def sliding_window(
    readings: List[NMEAReading],
    window_size: int,
    baro_altitude: Optional[float] = None,
) -> List[np.ndarray]:
    config = Config.default()
    baro = baro_altitude if baro_altitude is not None else config.baro_altitude

    terrain = extract_terrain_profile(readings, baro)
    if len(terrain) < window_size:
        return [terrain]

    windows = []
    for i in range(0, len(terrain) - window_size + 1, window_size // 2):
        windows.append(terrain[i:i + window_size])
    return windows


def profile_roughness(profile: np.ndarray) -> float:
    if len(profile) < 2:
        return 0.0
    return float(np.std(profile))
