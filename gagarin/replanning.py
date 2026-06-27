from typing import List, Tuple
from dataclasses import dataclass
import math

from gagarin.constants import EARTH_RADIUS


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
        points = []
        for i in range(n_waypoints):
            t = i / max(n_waypoints - 1, 1)
            lat = from_lat + (to_lat - from_lat) * t
            lon = from_lon + (to_lon - from_lon) * t
            points.append((lat, lon))

        total_dist = self._haversine_m(from_lat, from_lon, to_lat, to_lon)

        return ReplannedRoute(
            waypoints=points,
            total_distance_m=total_dist,
            n_waypoints=n_waypoints,
        )

    def _haversine_m(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
        return 2 * EARTH_RADIUS * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    def format_waypoints_csv(self, route: ReplannedRoute) -> str:
        lines = ["lat,lon"]
        for lat, lon in route.waypoints:
            lines.append(f"{lat:.6f},{lon:.6f}")
        return "\n".join(lines)
