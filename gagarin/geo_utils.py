from typing import Tuple
import math
import numpy as np

from gagarin.constants import EARTH_RADIUS


def offset_coords(
    lat: float,
    lon: float,
    distance_m: float,
    azimuth_rad: float,
) -> Tuple[float, float]:
    dlat = distance_m * math.cos(azimuth_rad) / EARTH_RADIUS
    dlon = distance_m * math.sin(azimuth_rad) / (EARTH_RADIUS * math.cos(math.radians(lat)))
    return lat + math.degrees(dlat), lon + math.degrees(dlon)


def offset_coords_batch(
    lats: np.ndarray,
    lons: np.ndarray,
    distances: np.ndarray,
    azimuth_rad: float,
    center_lat: float,
) -> Tuple[np.ndarray, np.ndarray]:
    if lats.shape != lons.shape or lats.shape != distances.shape:
        raise ValueError(
            f"Shape mismatch: lats={lats.shape}, lons={lons.shape}, "
            f"distances={distances.shape}"  # noqa: E251
        )
    cos_lat = np.cos(np.radians(center_lat))
    dlat = distances * math.cos(azimuth_rad) / EARTH_RADIUS
    dlon = distances * math.sin(azimuth_rad) / (EARTH_RADIUS * cos_lat)
    return lats + np.degrees(dlat), lons + np.degrees(dlon)
