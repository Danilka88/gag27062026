from typing import List, Tuple
from dataclasses import dataclass
import math
import numpy as np

from gagarin.constants import EARTH_RADIUS
from gagarin.geo_utils import haversine_m, offset_coords_batch


@dataclass
class ReplannedRoute:
    waypoints: List[Tuple[float, float]]
    total_distance_m: float
    n_waypoints: int


class RouteReplanner:
    def replan(
        self,
        from_lat: float,
        from_lon: float,
        to_lat: float,
        to_lon: float,
        n_waypoints: int = 20,
    ) -> ReplannedRoute:
        total_dist = haversine_m(from_lat, from_lon, to_lat, to_lon)

        bearing = self._bearing(from_lat, from_lon, to_lat, to_lon)

        distances = np.linspace(0, total_dist, n_waypoints)
        lats = np.full(n_waypoints, from_lat)
        lons = np.full(n_waypoints, from_lon)

        new_lats, new_lons = offset_coords_batch(lats, lons, distances, bearing, from_lat)

        points = [(float(lat), float(lon)) for lat, lon in zip(new_lats, new_lons)]

        return ReplannedRoute(
            waypoints=points,
            total_distance_m=total_dist,
            n_waypoints=n_waypoints,
        )

    @staticmethod
    def _bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        lat1_r = math.radians(lat1)
        lat2_r = math.radians(lat2)
        dlon_r = math.radians(lon2 - lon1)
        x = math.sin(dlon_r) * math.cos(lat2_r)
        y = math.cos(lat1_r) * math.sin(lat2_r) - math.sin(lat1_r) * math.cos(lat2_r) * math.cos(dlon_r)
        return math.atan2(x, y)
