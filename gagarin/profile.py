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



