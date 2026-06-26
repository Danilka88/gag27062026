import warnings
from dataclasses import dataclass, replace
from typing import Tuple, Any


@dataclass
class Config:
    baro_altitude: float = 1500.0
    nmea_freq_hz: float = 10.0
    window_size: int = 200

    coarse_azimuth_step: float = 10.0
    fine_azimuth_step: float = 0.5
    fine_azimuth_margin: float = 6.0

    speed_range_ms: Tuple[float, float] = (10.0, 150.0)
    n_speed_hypotheses: int = 10

    coarse_top_n: int = 5

    terrain_std_threshold: float = 3.0
    confidence_threshold: float = 0.7

    dem_path: str = "data/dem"
    output_path: str = "data/output"

    kalman_enabled: bool = True
    adaptive_sampling: bool = True
    adaptive_min_distance_m: float = 50.0

    seed: int = 42

    noise_std: float = 2.0
    default_azimuth: float = 45.0
    default_speed: float = 60.0
    flight_duration: float = 300.0

    def __post_init__(self):
        if self.window_size <= 0:
            raise ValueError("window_size must be positive")
        if self.nmea_freq_hz <= 0:
            raise ValueError("nmea_freq_hz must be positive")
        if self.coarse_azimuth_step <= 0:
            raise ValueError("coarse_azimuth_step must be positive")
        if self.terrain_std_threshold < 0:
            raise ValueError("terrain_std_threshold must be non-negative")
        if self.seed < 0:
            raise ValueError("seed must be non-negative")
        if self.n_speed_hypotheses <= 0:
            raise ValueError("n_speed_hypotheses must be positive")
        if self.flight_duration <= 0:
            raise ValueError("flight_duration must be positive")

    def merge(self, updates: dict) -> "Config":
        unknown = [k for k in updates if not hasattr(self, k)]
        if unknown:
            warnings.warn(f"Unknown config keys ignored: {unknown}")
        valid = {k: v for k, v in updates.items() if hasattr(self, k)}
        return replace(self, **valid)

    @classmethod
    def default(cls) -> "Config":
        return cls()
