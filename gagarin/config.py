from dataclasses import dataclass, field
from typing import Tuple


@dataclass(frozen=True)
class Config:
    baro_altitude: float = 1500.0
    nmea_freq_hz: float = 10.0
    window_size: int = 200

    azimuth_search_range: Tuple[float, float, float] = (0.0, 360.0, 1.0)
    speed_search_range: Tuple[float, float, int] = (10.0, 150.0, 15)

    coarse_azimuth_step: float = 10.0
    fine_azimuth_step: float = 0.5
    fine_azimuth_margin: float = 6.0

    speed_range_ms: Tuple[float, float] = (10.0, 150.0)
    n_speed_hypotheses: int = 10

    coarse_top_n: int = 5
    position_correction_gain: float = 0.5

    terrain_std_threshold: float = 3.0
    confidence_threshold: float = 0.7

    dem_path: str = "data/dem"
    output_path: str = "data/output"

    kalman_enabled: bool = True
    adaptive_sampling: bool = True
    adaptive_min_distance_m: float = 50.0

    seed: int = 42

    @classmethod
    def default(cls) -> "Config":
        return cls()
