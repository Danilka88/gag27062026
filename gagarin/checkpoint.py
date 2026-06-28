from typing import List, Optional, Tuple
from dataclasses import dataclass
import numpy as np

from gagarin.dem_loader import DEMLoader
from gagarin.config import Config
from gagarin.geo_utils import offset_coords, offset_coords_batch, haversine_m


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
    radar_altitudes: List[float]
    true_terrain: List[float]
    n_estimates: int
    n_steps: int
    start_lat: float
    start_lon: float
    best_azimuth: Optional[float] = None
    best_speed: Optional[float] = None
    heatmap_azimuths: Optional[List[float]] = None
    heatmap_ncc_vals: Optional[List[float]] = None
    heatmap_best_corr: Optional[float] = None
    heatmap_top_azimuths: Optional[List[float]] = None
    heatmap_top_corrs: Optional[List[float]] = None
    informativity_ratio: Optional[float] = None
    heatmap_terrain_std: Optional[float] = None
    heatmap_ambiguous: bool = False
    confidences: Optional[List[float]] = None
    discrimination_ratios: Optional[List[float]] = None
    peak_to_valleys: Optional[List[float]] = None
    terrain_stds: Optional[List[float]] = None
    mad_values: Optional[List[float]] = None

    def to_dict(self) -> dict:
        def _py(v):
            if isinstance(v, (np.floating,)):
                return float(v)
            if isinstance(v, (np.integer,)):
                return int(v)
            return v

        segments = []
        for i in range(self.n_steps):
            segments.append({
                "step": i,
                "true_lat": round(float(self.true_lats[i]), 7),
                "true_lon": round(float(self.true_lons[i]), 7),
                "true_row": round(float(self.true_rows[i]), 2),
                "true_col": round(float(self.true_cols[i]), 2),
            })

        estimates = []
        for i in range(self.n_estimates):
            conf_val = round(float(self.confidences[i]), 4) if self.confidences and i < len(self.confidences) else None
            dr_val = round(float(self.discrimination_ratios[i]), 3) if self.discrimination_ratios and i < len(self.discrimination_ratios) else None
            p2v_val = round(float(self.peak_to_valleys[i]), 1) if self.peak_to_valleys and i < len(self.peak_to_valleys) else None
            ts_val = round(float(self.terrain_stds[i]), 2) if self.terrain_stds and i < len(self.terrain_stds) else None
            estimates.append({
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
                "confidence": conf_val,
                "discrimination_ratio": dr_val,
                "peak_to_valley": p2v_val,
                "terrain_std": ts_val,
                "mad": round(float(self.mad_values[i]), 2) if self.mad_values and i < len(self.mad_values) else None,
            })

        return {
            "n_estimates": self.n_estimates,
            "n_steps": self.n_steps,
            "start_lat": self.start_lat,
            "start_lon": self.start_lon,
            "best_azimuth": self.best_azimuth,
            "best_speed": self.best_speed,
            "radar_altitudes": [round(float(a), 2) for a in self.radar_altitudes],
            "true_terrain": [round(float(t), 2) for t in self.true_terrain],
            "segments": segments,
            "estimates": estimates,
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
            "heatmap": {
                "azimuths": self.heatmap_azimuths,
                "ncc_vals": self.heatmap_ncc_vals,
                "best_azimuth": self.best_azimuth,
                "best_correlation": self.heatmap_best_corr,
                "top_azimuths": self.heatmap_top_azimuths,
                "top_correlations": self.heatmap_top_corrs,
                "informativity_ratio": getattr(self, "informativity_ratio", None),
                "terrain_std": getattr(self, "heatmap_terrain_std", None),
                "ambiguous": getattr(self, "heatmap_ambiguous", False),
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


@dataclass
class WindowEstimate:
    position_lat: float
    position_lon: float
    azimuth_deg: float
    speed_ms: float
    correlation: float
    confidence: float
    discrimination_ratio: float
    peak_to_valley: float
    terrain_std: float
    quality: dict
    timestamp: float
    mad_value: float = 30.0
    filtered_lat: Optional[float] = None
    filtered_lon: Optional[float] = None


def _azimuth_consensus(estimates: list) -> float:
    weights = {}
    for est in estimates:
        az = round(est.azimuth_deg, 1)
        weights[az] = weights.get(az, 0) + est.correlation
    if not weights:
        return estimates[0].azimuth_deg if estimates else 0.0
    return max(weights, key=weights.get)


def _ransac_filter(
    estimates: list, indices: list,
) -> tuple:
    if len(estimates) < 4:
        return estimates, indices
    lats = np.array([e.position_lat for e in estimates])
    lons = np.array([e.position_lon for e in estimates])
    med_lat, med_lon = float(np.median(lats)), float(np.median(lons))
    dists = np.array([haversine_m(lat, lon, med_lat, med_lon) for lat, lon in zip(lats, lons)])
    med_dist = float(np.median(dists))
    mad = float(np.median(np.abs(dists - med_dist)))
    threshold = med_dist + 2.0 * max(mad, 1.0)
    keep = [i for i, d in enumerate(dists) if d <= threshold]
    if len(keep) < max(3, len(estimates) // 2):
        return estimates, indices
    return [estimates[i] for i in keep], [indices[i] for i in keep]


def _eskf_filter_estimates(
    estimates: list, indices: list,
) -> tuple:
    if len(estimates) < 2:
        for e in estimates:
            e.filtered_lat = e.position_lat
            e.filtered_lon = e.position_lon
        return estimates, indices

    estimates[0].filtered_lat = estimates[0].position_lat
    estimates[0].filtered_lon = estimates[0].position_lon

    for i in range(1, len(estimates)):
        dt = max(0.01, estimates[i].timestamp - estimates[i - 1].timestamp)
        dr_dist = dt * estimates[i].speed_ms
        az_rad = np.radians(estimates[i].azimuth_deg)
        dr_lat, dr_lon = offset_coords(
            estimates[i - 1].filtered_lat,
            estimates[i - 1].filtered_lon,
            dr_dist, az_rad,
        )

        discr = max(estimates[i].discrimination_ratio, 1.0)
        w = min(1.0, max(0.0, (discr - 1.0) / 10.0))

        estimates[i].filtered_lat = dr_lat + w * (estimates[i].position_lat - dr_lat)
        estimates[i].filtered_lon = dr_lon + w * (estimates[i].position_lon - dr_lon)

    return estimates, indices


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


def _detrend(a: np.ndarray) -> np.ndarray:
    x = np.arange(len(a))
    coeffs = np.polyfit(x, a, 1)
    return a - np.polyval(coeffs, x)


def _ncc(a: np.ndarray, b: np.ndarray) -> float:
    a = a.astype(np.float64)
    b = b.astype(np.float64)
    a_m = a - np.mean(a)
    b_m = b - np.mean(b)
    denom = np.sqrt(np.sum(a_m ** 2) * np.sum(b_m ** 2))
    if denom < 1e-12:
        return 0.0
    return float(np.sum(a_m * b_m) / denom)


def _ncc_detrend(a: np.ndarray, b: np.ndarray) -> float:
    return _ncc(_detrend(a), _detrend(b))


def _ncc_adaptive(a: np.ndarray, b: np.ndarray, terrain_std: float) -> float:
    if terrain_std >= 20.0:
        return _ncc_detrend(a, b)
    elif terrain_std < 10.0:
        return _ncc(a, b)
    else:
        raw = abs(_ncc(a, b))
        det = abs(_ncc_detrend(a, b))
        return max(raw, det)


def _mad(a: np.ndarray, b: np.ndarray) -> float:
    a = a.astype(np.float64) - np.mean(a)
    b = b.astype(np.float64) - np.mean(b)
    return float(np.mean(np.abs(a - b)))


def _classify_quality(
    ncc: float, discr: float, p2v: float, terrain_std: float, mad: float = 30.0,
) -> str:
    if ncc > 0.8 and discr > 3.0 and p2v > 25.0 and terrain_std > 6.0 and mad < 10.0:
        return "good"
    if ncc > 0.6 and discr > 1.5 and p2v > 10.0 and terrain_std > 3.0 and mad < 20.0:
        return "marginal"
    return "poor"


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


def _compute_heatmap(
    dem: DEMLoader,
    observed_terrain: np.ndarray,
    start_lat: float, start_lon: float,
    freq_hz: float,
    step_deg: float = 1.0,
    nominal_speed: float = 60.0,
) -> dict:
    n = min(len(observed_terrain), 60)
    observed = observed_terrain[:n]
    n_eff = len(observed)

    if n_eff < 5:
        return {
            "azimuths": [], "ncc_vals": [],
            "best_azimuth": None, "best_correlation": None,
            "top_azimuths": [], "top_correlations": [],
            "terrain_std": 0.0,
        }

    terrain_std = float(np.std(observed))
    azimuths = np.arange(0, 360, step_deg)
    ncc_vals = np.zeros(len(azimuths))

    for ai, az in enumerate(azimuths):
        ref = _extract_profile(dem, start_lat, start_lon, az, nominal_speed, n_eff, freq_hz)
        ncc_vals[ai] = abs(_ncc_adaptive(observed, ref, terrain_std))

    best_idxs = np.argsort(-np.abs(ncc_vals))[:3]
    top_azimuths = [float(azimuths[i]) for i in best_idxs]
    top_correlations = [float(ncc_vals[i]) for i in best_idxs]

    return {
        "azimuths": [float(a) for a in azimuths],
        "ncc_vals": [float(v) for v in ncc_vals],
        "best_azimuth": top_azimuths[0],
        "best_correlation": top_correlations[0],
        "top_azimuths": top_azimuths,
        "top_correlations": top_correlations,
        "terrain_std": terrain_std,
    }


def _search_position_grid(
    dem: DEMLoader,
    observed: np.ndarray,
    center_lat: float, center_lon: float,
    azimuth_deg: float, speed_ms: float,
    freq_hz: float,
    pixel_radius: int = 4,
) -> Tuple[float, float, float, float, float]:
    cr, cc = dem.lonlat_to_pixel(center_lat, center_lon)
    cr_i, cc_i = int(round(cr)), int(round(cc))

    grid_size = 2 * pixel_radius + 1
    ncc_vals = np.zeros((grid_size, grid_size))
    mad_vals = np.full((grid_size, grid_size), float('inf'))
    best_mad = float('inf')
    best_ncc = -1.0
    best_dr, best_dc = 0, 0

    for dr in range(-pixel_radius, pixel_radius + 1):
        for dc in range(-pixel_radius, pixel_radius + 1):
            r, c = cr_i + dr, cc_i + dc
            lat, lon = dem.pixel_to_lonlat(r, c)
            ref = _extract_profile(dem, lat, lon, azimuth_deg, speed_ms, len(observed), freq_hz)
            mad_val = _mad(observed, ref)
            ncc_val = _ncc(observed, ref)
            mad_vals[dr + pixel_radius, dc + pixel_radius] = mad_val
            ncc_vals[dr + pixel_radius, dc + pixel_radius] = abs(ncc_val)
            if mad_val < best_mad:
                best_mad = mad_val
                best_ncc = ncc_val
                best_dr, best_dc = dr, dc

    best_r, best_c = cr_i + best_dr, cc_i + best_dc
    best_lat, best_lon = dem.pixel_to_lonlat(best_r, best_c)

    second_best_mad = float('inf')
    excl = min(2, max(pixel_radius - 1, 1))
    for ndr in range(-pixel_radius, pixel_radius + 1):
        for ndc in range(-pixel_radius, pixel_radius + 1):
            if (ndr == best_dr and ndc == best_dc) or (abs(ndr - best_dr) <= excl and abs(ndc - best_dc) <= excl):
                continue
            nr = ndr + pixel_radius
            nc = ndc + pixel_radius
            if mad_vals[nr, nc] < second_best_mad:
                second_best_mad = mad_vals[nr, nc]

    if second_best_mad == float('inf'):
        discrimination = 99.0
    else:
        discrimination = second_best_mad / max(best_mad, 1e-12)

    return best_lat, best_lon, float(best_mad), float(best_ncc), float(discrimination)


def _search_speed(
    dem: DEMLoader,
    observed_terrain: np.ndarray,
    start_lat: float, start_lon: float,
    azimuth_deg: float, terrain_std: float,
    ws: int, cfg: Config, freq_hz: float,
) -> Tuple[float, float]:
    speeds = np.linspace(10, 150, 15)
    n_ref = min(ws, 60)
    best_speed = cfg.default_speed
    best_mad = float('inf')
    obs_first = observed_terrain[:n_ref]
    for sp in speeds:
        ref = _extract_profile(dem, start_lat, start_lon, azimuth_deg, sp, n_ref, freq_hz)
        mad_val = _mad(obs_first, ref)
        if mad_val < best_mad:
            best_mad = mad_val
            best_speed = sp
    return best_speed, best_mad


def _process_windows(
    dem: DEMLoader,
    observed_terrain: np.ndarray,
    start_lat: float, start_lon: float,
    azimuth_deg: float, speed_ms: float,
    ws: int, top_azs: List[float],
    freq_hz: float, cfg: Config,
) -> Tuple[List, List[int]]:
    estimates = []
    estimate_indices = []
    az_rad = np.radians(azimuth_deg)
    step_samples = max(ws // 4, 1)

    GATE_MAD_MAX = 30.0
    GATE_NCC_MIN = 0.3
    GATE_DISCR_MIN = 1.0
    GATE_P2V_MIN = 5.0

    for i in range(0, len(observed_terrain) - ws + 1, step_samples):
        window = observed_terrain[i:i + ws]
        window_std = float(np.std(window))
        if window_std < cfg.terrain_std_threshold:
            continue
        p2v = float(np.max(window) - np.min(window))
        if p2v < GATE_P2V_MIN:
            continue
        t_center = (i + ws / 2) / freq_hz
        dr_dist = t_center * speed_ms
        dr_lat, dr_lon = offset_coords(start_lat, start_lon, dr_dist, az_rad)

        best_grid_mad = float('inf')
        best_grid_ncc = -1.0
        best_est_lat, best_est_lon = dr_lat, dr_lon
        best_az_used = azimuth_deg
        best_discr = 1.0
        for az_candidate in top_azs:
            elat, elon, mad_val, ncc_val, discr = _search_position_grid(
                dem, window, dr_lat, dr_lon,
                az_candidate, speed_ms, freq_hz,
                pixel_radius=4,
            )
            if mad_val < best_grid_mad:
                best_grid_mad = mad_val
                best_grid_ncc = ncc_val
                best_est_lat, best_est_lon = elat, elon
                best_az_used = az_candidate
                best_discr = discr

        if best_grid_mad > GATE_MAD_MAX:
            continue
        if abs(best_grid_ncc) < GATE_NCC_MIN:
            continue
        if best_discr < GATE_DISCR_MIN:
            continue

        qual = _classify_quality(abs(best_grid_ncc), best_discr, p2v, window_std, best_grid_mad)
        confidence = float(max(0, min(1, 1.0 - best_grid_mad / 30.0)))

        est = WindowEstimate(
            position_lat=best_est_lat,
            position_lon=best_est_lon,
            azimuth_deg=float(best_az_used),
            speed_ms=float(speed_ms),
            correlation=float(abs(best_grid_ncc)),
            confidence=confidence,
            mad_value=float(best_grid_mad),
            discrimination_ratio=float(best_discr),
            peak_to_valley=p2v,
            terrain_std=window_std,
            quality={"quality": qual},
            timestamp=(i + ws // 2) / freq_hz,
        )

        estimates.append(est)
        estimate_indices.append(i + ws // 2)

    return estimates, estimate_indices


def run_tercom(
    dem: DEMLoader,
    altitudes: np.ndarray,
    start_lat: float,
    start_lon: float,
    config: Optional[Config] = None,
    freq_hz: float = 10.0,
    baro_altitude: float = 1500.0,
) -> Tuple[List, List[int], dict]:
    cfg = config or Config.default()
    base_ws = min(cfg.window_size, max(len(altitudes) // 2, 10))

    observed_terrain = baro_altitude - altitudes
    observed_terrain = np.maximum(observed_terrain, -500.0)

    heatmap = _compute_heatmap(dem, observed_terrain[:base_ws], start_lat, start_lon, freq_hz)
    best_az = heatmap.get("best_azimuth")
    top_azs = heatmap.get("top_azimuths", [best_az] if best_az else [])
    if best_az is None:
        return [], [], heatmap

    first_std = float(np.std(observed_terrain[:base_ws]))
    heatmap["terrain_std"] = float(first_std)

    informativity = first_std / max(cfg.noise_std, 0.1)
    heatmap["informativity_ratio"] = float(informativity)

    ws = base_ws

    best_speed, _ = _search_speed(dem, observed_terrain, start_lat, start_lon,
                                  best_az, first_std, ws, cfg, freq_hz)

    if first_std >= 20.0:
        estimates, indices = _process_windows(
            dem, observed_terrain, start_lat, start_lon,
            best_az, best_speed, ws, top_azs, freq_hz, cfg,
        )
        if not estimates:
            return [], [], heatmap
        consensus_az = _azimuth_consensus(estimates)
        estimates, indices = _ransac_filter(estimates, indices)
        estimates, indices = _eskf_filter_estimates(estimates, indices)
        heatmap["best_azimuth"] = float(consensus_az)
        heatmap["best_speed"] = float(best_speed)
        return estimates, indices, heatmap

    primary_az = top_azs[0]
    candidates = []
    for cand_az in top_azs:
        cand_speed, _ = _search_speed(dem, observed_terrain, start_lat, start_lon,
                                      cand_az, first_std, ws, cfg, freq_hz)
        ests, est_indices = _process_windows(
            dem, observed_terrain, start_lat, start_lon,
            cand_az, cand_speed, ws, top_azs, freq_hz, cfg,
        )
        if not ests:
            continue
        consensus_az = _azimuth_consensus(ests)
        mean_ncc = float(np.mean([e.correlation for e in ests]))
        candidates.append((ests, est_indices, consensus_az, cand_speed, mean_ncc, cand_az))

    if not candidates:
        return [], [], heatmap

    def _score(c):
        _, _, consensus_az, _, mncc, _ = c
        ad = min(abs(consensus_az - primary_az), abs(consensus_az - primary_az - 360), abs(consensus_az - primary_az + 360))
        bonus = 0.03 * max(0, 1.0 - ad / 90.0)
        return mncc + bonus

    candidates.sort(key=_score, reverse=True)
    best = candidates[0]

    ambiguous = False
    if len(candidates) > 1:
        c0_az = candidates[0][2]
        c1_az = candidates[1][2]
        ang = min(abs(c0_az - c1_az), abs(c0_az - c1_az - 360), abs(c0_az - c1_az + 360))
        if ang > 30 and candidates[1][4] > 0.90 * candidates[0][4]:
            ambiguous = True

    heatmap["ambiguous"] = ambiguous

    estimates, indices, best_az, best_speed, _, _ = best
    estimates, indices = _ransac_filter(estimates, indices)
    estimates, indices = _eskf_filter_estimates(estimates, indices)
    heatmap["best_azimuth"] = float(best_az)
    heatmap["best_speed"] = float(best_speed)
    return estimates, indices, heatmap


def collect_result(
    dem: DEMLoader,
    true_lats: np.ndarray,
    true_lons: np.ndarray,
    estimates: List,
    radar_altitudes: np.ndarray,
    estimate_indices: Optional[List[int]] = None,
    heatmap_data: Optional[dict] = None,
) -> CheckpointResult:
    n_steps = len(true_lats)
    true_rows = []
    true_cols = []
    for lat, lon in zip(true_lats, true_lons):
        r, c = dem.lonlat_to_pixel(lat, lon)
        true_rows.append(r)
        true_cols.append(c)

    true_terrain = dem.elevation_batch(true_lats, true_lons).tolist()

    if heatmap_data is None:
        heatmap_data = {}

    best_az = heatmap_data.get("best_azimuth")
    best_sp = estimates[0].speed_ms if estimates else None

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
                confidences=[],
                discrimination_ratios=[],
                peak_to_valleys=[],
                terrain_stds=[],
                mad_values=[],
                radar_altitudes=radar_altitudes.tolist(),
                true_terrain=true_terrain,
                n_estimates=0,
                n_steps=n_steps,
                start_lat=float(true_lats[0]),
                start_lon=float(true_lons[0]),
                best_azimuth=best_az,
                best_speed=best_sp,
                heatmap_azimuths=heatmap_data.get("azimuths"),
                heatmap_ncc_vals=heatmap_data.get("ncc_vals"),
                heatmap_best_corr=heatmap_data.get("best_correlation"),
                heatmap_top_azimuths=heatmap_data.get("top_azimuths"),
                heatmap_top_corrs=heatmap_data.get("top_correlations"),
                informativity_ratio=heatmap_data.get("informativity_ratio"),
                heatmap_terrain_std=heatmap_data.get("terrain_std"),
                heatmap_ambiguous=heatmap_data.get("ambiguous", False),
            )

    n_est = len(estimates)
    est_lats = []
    est_lons = []
    est_rows = []
    est_cols = []
    errors_m = []
    correlations = []
    qualities = []
    confidences = []
    discrimination_ratios = []
    peak_to_valleys = []
    terrain_stds = []
    mad_values = []

    for i, est in enumerate(estimates):
        elat = float(est.filtered_lat if est.filtered_lat is not None else est.position_lat)
        elon = float(est.filtered_lon if est.filtered_lon is not None else est.position_lon)
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
        confidences.append(float(getattr(est, "confidence", 0.5)))
        discrimination_ratios.append(float(getattr(est, "discrimination_ratio", 1.0)))
        peak_to_valleys.append(float(getattr(est, "peak_to_valley", 0.0)))
        terrain_stds.append(float(getattr(est, "terrain_std", 0.0)))
        mad_values.append(float(getattr(est, "mad_value", 30.0)))

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
        radar_altitudes=radar_altitudes.tolist(),
        true_terrain=true_terrain,
        n_estimates=n_est,
        n_steps=n_steps,
        start_lat=float(true_lats[0]),
        start_lon=float(true_lons[0]),
        best_azimuth=best_az,
        best_speed=best_sp,
        heatmap_azimuths=heatmap_data.get("azimuths"),
        heatmap_ncc_vals=heatmap_data.get("ncc_vals"),
        heatmap_best_corr=heatmap_data.get("best_correlation"),
        heatmap_top_azimuths=heatmap_data.get("top_azimuths"),
        heatmap_top_corrs=heatmap_data.get("top_correlations"),
        informativity_ratio=heatmap_data.get("informativity_ratio"),
        heatmap_terrain_std=heatmap_data.get("terrain_std"),
        heatmap_ambiguous=heatmap_data.get("ambiguous", False),
        confidences=confidences,
        discrimination_ratios=discrimination_ratios,
        peak_to_valleys=peak_to_valleys,
        terrain_stds=terrain_stds,
        mad_values=mad_values,
    )
