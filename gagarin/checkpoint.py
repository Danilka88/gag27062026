from typing import List, Optional, Tuple
from dataclasses import dataclass
import numpy as np

from gagarin.dem_loader import DEMLoader
from gagarin.pipeline import NavigationPipeline
from gagarin.config import Config
from gagarin.geo_utils import offset_coords_batch, haversine_m, offset_coords


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


def _extract_profile(
    dem: DEMLoader,
    lat: float, lon: float,
    azimuth_deg: float, speed_ms: float,
    n_points: int, freq_hz: float,
) -> np.ndarray:
    dt = 1.0 / freq_hz
    d_step = speed_ms * dt
    distances = np.arange(n_points) * d_step
    az_rad = np.radians(azimuth_deg)
    lats = np.full(n_points, lat)
    lons = np.full(n_points, lon)
    lats, lons = offset_coords_batch(lats, lons, distances, az_rad, lat)
    lats, lons = dem.normalize_coordinates(lats, lons)
    return dem.elevation_batch(lats, lons)


def _ncc(a: np.ndarray, b: np.ndarray) -> float:
    a = a.astype(np.float64)
    b = b.astype(np.float64)
    a_m = a - np.mean(a)
    b_m = b - np.mean(b)
    denom = np.sqrt(np.sum(a_m ** 2) * np.sum(b_m ** 2))
    if denom < 1e-12:
        return 0.0
    return float(np.sum(a_m * b_m) / denom)


def _search_position_grid(
    dem: DEMLoader,
    observed: np.ndarray,
    center_lat: float, center_lon: float,
    azimuth_deg: float, speed_ms: float,
    freq_hz: float,
    pixel_radius: int = 5,
) -> Tuple[float, float, float, float]:
    cr, cc = dem.lonlat_to_pixel(center_lat, center_lon)
    cr_i, cc_i = int(round(cr)), int(round(cc))
    best_ncc = -1.0
    best_lat, best_lon = center_lat, center_lon
    best_r, best_c = float(cr), float(cc)
    for r in range(cr_i - pixel_radius, cr_i + pixel_radius + 1):
        for c in range(cc_i - pixel_radius, cc_i + pixel_radius + 1):
            lat, lon = dem.pixel_to_lonlat(r, c)
            ref = _extract_profile(dem, lat, lon, azimuth_deg, speed_ms, len(observed), freq_hz)
            ncc_val = _ncc(observed, ref)
            if ncc_val > best_ncc:
                best_ncc = ncc_val
                best_lat, best_lon = lat, lon
                best_r, best_c = float(r), float(c)
    return best_lat, best_lon, float(best_ncc)


def run_tercom(
    dem: DEMLoader,
    altitudes: np.ndarray,
    start_lat: float,
    start_lon: float,
    config: Optional[Config] = None,
    estimated_speed: float = 60.0,
    estimated_azimuth: float = 45.0,
    freq_hz: float = 10.0,
) -> Tuple[List[object], List[int]]:
    cfg = config or Config.default()
    cfg.default_speed = estimated_speed
    cfg.default_azimuth = estimated_azimuth
    cfg.nmea_freq_hz = freq_hz
    cfg.window_size = min(cfg.window_size, max(len(altitudes) // 2, 10))
    cfg.adaptive_sampling = False

    pipeline = NavigationPipeline(dem, cfg)
    pipeline.initialize(start_lat, start_lon)

    estimates = []
    estimate_indices = []
    buf = []
    az_rad = np.radians(estimated_azimuth)
    ws = cfg.window_size

    for i, alt in enumerate(altitudes):
        buf.append(alt)
        if len(buf) > ws:
            buf.pop(0)
        if len(buf) < ws:
            continue

        observed_radar = np.array(buf)
        terrain = cfg.baro_altitude - observed_radar
        if float(np.std(terrain)) < cfg.terrain_std_threshold:
            continue

        t_start = (i - ws + 1) / freq_hz
        dr_dist_start = t_start * estimated_speed
        dr_lat_start, dr_lon_start = offset_coords(start_lat, start_lon, dr_dist_start, az_rad)

        est_lat, est_lon, corr_val = _search_position_grid(
            dem, terrain, dr_lat_start, dr_lon_start,
            estimated_azimuth, estimated_speed, freq_hz,
            pixel_radius=5,
        )

        if corr_val < 0.5:
            continue

        class _SimpleEst:
            pass

        est = _SimpleEst()
        est.position_lat = est_lat
        est.position_lon = est_lon
        est.azimuth_deg = float(estimated_azimuth)
        est.speed_ms = float(estimated_speed)
        est.correlation = float(corr_val)
        est.confidence = float(max(0, min(1, (corr_val - 0.5) * 2)))
        qual = "good" if corr_val > 0.9 else "marginal" if corr_val > 0.7 else "poor"
        est.quality = {"quality": qual}
        est.filtered_lat = None
        est.filtered_lon = None
        est.timestamp = i / freq_hz

        pipeline.last_estimate = est
        pipeline.center_lat = est_lat
        pipeline.center_lon = est_lon

        estimates.append(est)
        estimate_indices.append(i - ws + 1)

    return estimates, estimate_indices


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
