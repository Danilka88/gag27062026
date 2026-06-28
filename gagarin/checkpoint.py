from typing import List, Optional, Tuple
from dataclasses import dataclass, asdict
import numpy as np

from gagarin.dem_loader import DEMLoader
from gagarin.pipeline import NavigationPipeline
from gagarin.nmea_parser import NMEAReading
from gagarin.config import Config
from gagarin.geo_utils import offset_coords_batch, haversine_m


@dataclass
class CheckpointResult:
    true_lats: List[float]
    true_lons: List[float]
    true_rows: List[float]
    true_cols: List[float]
    est_lats: List[float]
    est_lons: List[float]
    est_rows: List[float]
    est_cols: List[float]
    errors_m: List[float]
    correlations: List[float]
    qualities: List[str]
    n_estimates: int
    n_steps: int
    start_lat: float
    start_lon: float

    def to_dict(self) -> dict:
        def _py(v):
            if isinstance(v, (np.floating,)):
                return float(v)
            if isinstance(v, (np.integer,)):
                return int(v)
            return v
        return {
            "n_estimates": self.n_estimates,
            "n_steps": self.n_steps,
            "start_lat": self.start_lat,
            "start_lon": self.start_lon,
            "segments": [
                {
                    "step": i,
                    "true_lat": round(float(self.true_lats[i]), 7),
                    "true_lon": round(float(self.true_lons[i]), 7),
                    "true_row": round(float(self.true_rows[i]), 2),
                    "true_col": round(float(self.true_cols[i]), 2),
                }
                for i in range(self.n_steps)
            ],
            "estimates": [
                {
                    "step": i + 1,
                    "true_lat": round(float(self.true_lats[i]), 7),
                    "true_lon": round(float(self.true_lons[i]), 7),
                    "true_row": round(float(self.true_rows[i]), 2),
                    "true_col": round(float(self.true_cols[i]), 2),
                    "est_lat": round(float(self.est_lats[i]), 7),
                    "est_lon": round(float(self.est_lons[i]), 7),
                    "est_row": round(float(self.est_rows[i]), 2),
                    "est_col": round(float(self.est_cols[i]), 2),
                    "error_m": round(float(self.errors_m[i]), 2),
                    "correlation": round(float(self.correlations[i]), 4),
                    "quality": self.qualities[i],
                }
                for i in range(self.n_estimates)
            ],
            "stats": {
                "mean_error_m": round(float(np.mean(self.errors_m)), 2) if self.errors_m else 0,
                "max_error_m": round(float(np.max(self.errors_m)), 2) if self.errors_m else 0,
                "min_error_m": round(float(np.min(self.errors_m)), 2) if self.errors_m else 0,
                "mean_correlation": round(float(np.mean(self.correlations)), 4) if self.correlations else 0,
                "total_distance_km": round(float(
                    haversine_m(self.true_lats[0], self.true_lons[0],
                                 self.true_lats[-1], self.true_lons[-1]) / 1000.0
                ), 2),
            },
        }


def read_altitudes(path: str) -> np.ndarray:
    alts = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                alts.append(float(line))
    return np.array(alts, dtype=np.float64)


def convert_start_point(
    dem: DEMLoader, x: float, y: float, coord_type: str,
) -> Tuple[float, float]:
    if coord_type == "pixel":
        return dem.pixel_to_lonlat(y, x)
    elif coord_type == "geo":
        return float(x), float(y)
    elif coord_type == "projected":
        return dem.projected_to_lonlat(x, y)
    else:
        raise ValueError(f"Unknown coord_type: {coord_type}")


def compute_true_trajectory(
    start_lat: float, start_lon: float,
    azimuth_deg: float, speed_ms: float,
    n_steps: int, freq_hz: float,
) -> Tuple[np.ndarray, np.ndarray]:
    dt = 1.0 / freq_hz
    distances = np.arange(n_steps) * speed_ms * dt
    start_lats = np.full(n_steps, start_lat)
    start_lons = np.full(n_steps, start_lon)
    az_rad = np.radians(azimuth_deg)
    lats, lons = offset_coords_batch(start_lats, start_lons, distances, az_rad, start_lat)
    return lats, lons


def run_tercom(
    dem: DEMLoader,
    altitudes: np.ndarray,
    start_lat: float,
    start_lon: float,
    config: Optional[Config] = None,
    estimated_speed: float = 60.0,
    estimated_azimuth: float = 45.0,
    freq_hz: float = 10.0,
) -> List[object]:
    cfg = config or Config.default()
    cfg.default_speed = estimated_speed
    cfg.default_azimuth = estimated_azimuth
    cfg.nmea_freq_hz = freq_hz
    cfg.window_size = min(cfg.window_size, max(len(altitudes) // 2, 10))
    cfg.adaptive_sampling = False

    pipeline = NavigationPipeline(dem, cfg)
    pipeline.initialize(start_lat, start_lon)

    estimates = []
    for i, alt in enumerate(altitudes):
        reading = NMEAReading(altitude=alt, timestamp=i / freq_hz)
        est = pipeline.feed_reading(reading)
        if est is not None:
            estimates.append(est)

    return estimates


def collect_result(
    dem: DEMLoader,
    true_lats: np.ndarray,
    true_lons: np.ndarray,
    estimates: List,
    estimate_indices: Optional[List[int]] = None,
) -> CheckpointResult:
    n_steps = len(true_lats)
    true_rows = []
    true_cols = []
    for lat, lon in zip(true_lats, true_lons):
        r, c = dem.lonlat_to_pixel(lat, lon)
        true_rows.append(r)
        true_cols.append(c)

    if not estimates:
        return CheckpointResult(
            true_lats=list(true_lats),
            true_lons=list(true_lons),
            true_rows=true_rows,
            true_cols=true_cols,
            est_lats=[],
            est_lons=[],
            est_rows=[],
            est_cols=[],
            errors_m=[],
            correlations=[],
            qualities=[],
            n_estimates=0,
            n_steps=n_steps,
            start_lat=float(true_lats[0]),
            start_lon=float(true_lons[0]),
        )

    n_est = len(estimates)
    est_lats = []
    est_lons = []
    est_rows = []
    est_cols = []
    errors_m = []
    correlations = []
    qualities = []

    for i, est in enumerate(estimates):
        elat = float(est.position_lat)
        elon = float(est.position_lon)
        est_lats.append(elat)
        est_lons.append(elon)
        r, c = dem.lonlat_to_pixel(elat, elon)
        est_rows.append(r)
        est_cols.append(c)

        est_step_idx = estimate_indices[i] if estimate_indices else i
        est_step_idx = min(est_step_idx, n_steps - 1)
        err = haversine_m(elat, elon,
                          float(true_lats[est_step_idx]),
                          float(true_lons[est_step_idx]))
        errors_m.append(err)

        correlations.append(float(est.correlation))
        qualities.append(est.quality.get("quality", "unknown") if est.quality else "unknown")

    return CheckpointResult(
        true_lats=list(true_lats),
        true_lons=list(true_lons),
        true_rows=true_rows,
        true_cols=true_cols,
        est_lats=est_lats,
        est_lons=est_lons,
        est_rows=est_rows,
        est_cols=est_cols,
        errors_m=errors_m,
        correlations=correlations,
        qualities=qualities,
        n_estimates=n_est,
        n_steps=n_steps,
        start_lat=float(true_lats[0]),
        start_lon=float(true_lons[0]),
    )
