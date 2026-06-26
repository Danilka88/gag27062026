from typing import List
import numpy as np

from gagarin.nmea_parser import NMEAReading


def extract_terrain_profile(
    readings: List[NMEAReading],
    baro_altitude: float = 1500.0,
) -> np.ndarray:
    if not readings:
        return np.array([])

    altitudes = np.array([r.altitude for r in readings])
    terrain = baro_altitude - altitudes
    terrain = np.maximum(terrain, -500.0)
    return terrain



