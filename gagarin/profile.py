from typing import List, Optional
import numpy as np

from gagarin.nmea_parser import NMEAReading

_DEFAULT_BARO: float = 1500.0


def extract_terrain_profile(
    readings: List[NMEAReading],
    baro_altitude: Optional[float] = None,
) -> np.ndarray:
    if not readings:
        return np.array([])

    baro = _DEFAULT_BARO if baro_altitude is None else baro_altitude
    altitudes = np.array([r.altitude for r in readings])
    terrain = baro - altitudes
    terrain = np.maximum(terrain, -500.0)
    return terrain



