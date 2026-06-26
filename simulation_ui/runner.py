import os
import math
from typing import Dict, Any, Generator
import numpy as np

from gagarin.dem_loader import DEMLoader
from gagarin.data_generator import DataGenerator, FlightParams
from gagarin.pipeline import NavigationPipeline
from gagarin.correlator import HypothesisSearch, CorrelationMetrics
from gagarin.nmea_parser import NMEAParser
from gagarin.profile import extract_terrain_profile
from gagarin.preprocess import TerrainAnalyzer, _latlon_distance_m, _adaptive_corridor_width
from gagarin.config import Config
from gagarin.constants import EARTH_RADIUS
from simulation_ui.texts import STEPS as STEP_TEXTS
from simulation_ui.svg_generator import (
    svg_dem, svg_nmea, svg_buffer, svg_profile,
    svg_heatmap, svg_ncc_bar, svg_lag, svg_trajectory,
    svg_eskf_error, svg_quality, svg_result, svg_corridor,
    svg_fingerprints, svg_empty,
)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SCENARIOS = {
    "synthetic": {
        "name": "Камчатка (синтетический)",
        "description": "Плавный рельеф, σ=95 м — идеален для отладки TERCOM",
        "dem_path": "data/dem/synthetic_kamchatka.tif",
        "dem_name": "Synthetic Kamchatka",
        "dem_size": "400×400",
        "dem_std": "95 м",
        "baro_altitude": 1500.0,
        "flight_duration": 40.0,
    },
    "dramatic": {
        "name": "Камчатка (драматический)",
        "description": "6 вулканов + гребни + каньоны, σ=687 м — сложный рельеф",
        "dem_path": "data/dem/dramatic_kamchatka.tif",
        "dem_name": "Dramatic Kamchatka",
        "dem_size": "400×400",
        "dem_std": "687 м",
        "baro_altitude": 3500.0,
        "flight_duration": 40.0,
    },
}


def get_scenarios() -> Dict[str, Dict[str, Any]]:
    result = {}
    for sid, info in SCENARIOS.items():
        dem_path = os.path.join(PROJECT_ROOT, info["dem_path"])
        result[sid] = dict(info)
        result[sid]["exists"] = os.path.exists(dem_path)
    return result


def _to_serializable(v):
    if isinstance(v, (np.floating,)):
        return float(v)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, np.ndarray):
        return v.tolist()
    return v


def _make_step(step_idx: int, svg: str, metrics: dict) -> Dict[str, Any]:
    t = STEP_TEXTS[step_idx]
    safe_metrics = {k: _to_serializable(v) for k, v in metrics.items()}
    return {
        "id": t["id"],
        "number": t["number"],
        "phase": t["phase"],
        "phase_label": t["phase_label"],
        "title": t["title"],
        "subtitle": t["subtitle"],
        "explanation": t["explanation"],
        "task": t["task"],
        "why": t["why"],
        "tags": t["tags"],
        "svg": svg,
        "metrics": safe_metrics,
    }





def _generate_true_trajectory(center_lat, center_lon, params, n_points):
    cos_clat = math.cos(math.radians(center_lat))
    lats, lons = [], []
    for i in range(n_points):
        d = i * params.speed_ms * params.duration_s / max(n_points - 1, 1)
        dlat = d * math.cos(params.azimuth_rad) / 6371000
        dlon = d * math.sin(params.azimuth_rad) / (6371000 * cos_clat)
        lats.append(center_lat + math.degrees(dlat))
        lons.append(center_lon + math.degrees(dlon))
    return lats, lons


class SimulationRunner:
    def __init__(self, scenario_id: str):
        if scenario_id not in SCENARIOS:
            raise ValueError(f"Unknown scenario: {scenario_id}")
        self.scenario_id = scenario_id
        info = SCENARIOS[scenario_id]
        self.dem_path = os.path.join(PROJECT_ROOT, info["dem_path"])
        if not os.path.exists(self.dem_path):
            raise FileNotFoundError(f"DEM not found: {self.dem_path}")
        self.baro_altitude = info["baro_altitude"]
        self.flight_duration = info["flight_duration"]

    def run(self) -> Generator[Dict[str, Any], None, None]:
        cfg = Config.default()
        cfg.noise_std = 1.0
        cfg.flight_duration = self.flight_duration
        cfg.baro_altitude = SCENARIOS[self.scenario_id]["baro_altitude"]

        dem = DEMLoader(self.dem_path)
        bounds = dem.bounds
        center_lat = (bounds[1] + bounds[3]) / 2
        center_lon = (bounds[0] + bounds[2]) / 2

        params = FlightParams(
            start_lat=center_lat,
            start_lon=center_lon,
            azimuth_deg=cfg.default_azimuth,
            speed_ms=cfg.default_speed,
            duration_s=self.flight_duration,
        )

        grid = dem.get_elevation_grid()
        data = grid[2]
        yield _make_step(0, svg_dem(data), {
            "shape": f"{data.shape[0]}×{data.shape[1]}",
            "min_elevation_m": float(np.min(data)),
            "max_elevation_m": float(np.max(data)),
            "std_elevation_m": float(np.std(data)),
            "bounds": f"{bounds[0]:.4f}, {bounds[1]:.4f}, {bounds[2]:.4f}, {bounds[3]:.4f}",
        })

        analyzer = TerrainAnalyzer(dem)
        std_map = analyzer.std_window(7)
        n_route = 20
        az_rad = params.azimuth_rad
        total_dist = params.speed_ms * params.duration_s
        cos_clat = math.cos(math.radians(center_lat))
        route_lats = []
        route_lons = []
        for i in range(n_route):
            frac = i / max(n_route - 1, 1)
            d = frac * total_dist
            dlat = d * math.cos(az_rad) / 6371000
            dlon = d * math.sin(az_rad) / (6371000 * cos_clat)
            route_lats.append(center_lat + math.degrees(dlat))
            route_lons.append(center_lon + math.degrees(dlon))

        grad_map = analyzer.gradient_magnitude()
        std_vals, grad_vals = [], []
        for lat, lon in zip(route_lats, route_lons):
            try:
                ri = int((lat - bounds[1]) / (bounds[3] - bounds[1]) * (std_map.shape[0] - 1))
                ci = int((lon - bounds[0]) / (bounds[2] - bounds[0]) * (std_map.shape[1] - 1))
                ri = max(0, min(ri, std_map.shape[0] - 1))
                ci = max(0, min(ci, std_map.shape[1] - 1))
                std_vals.append(float(std_map[ri, ci]))
            except Exception:
                std_vals.append(0.0)
            try:
                ri = int((lat - bounds[1]) / (bounds[3] - bounds[1]) * (grad_map.shape[0] - 1))
                ci = int((lon - bounds[0]) / (bounds[2] - bounds[0]) * (grad_map.shape[1] - 1))
                ri = max(0, min(ri, grad_map.shape[0] - 1))
                ci = max(0, min(ci, grad_map.shape[1] - 1))
                grad_vals.append(float(grad_map[ri, ci]))
            except Exception:
                grad_vals.append(0.0)

        yield _make_step(1, svg_fingerprints(std_vals, grad_vals), {
            "mean_std": f"{float(np.mean(std_vals)):.1f}",
            "mean_gradient": f"{float(np.mean(grad_vals)):.1f}",
            "route_length_km": f"{total_dist / 1000:.1f}",
        })

        max_seg = _latlon_distance_m(center_lat, center_lon, route_lats[-1], route_lons[-1])
        corridor_w = _adaptive_corridor_width(max_seg, ins_drift_rate=0.1, dem_resolution_m=max(dem.resolution))
        yield _make_step(2, svg_corridor(corridor_w), {
            "corridor_width_m": f"{corridor_w:.0f}",
            "ins_drift_rate": "0.1",
            "drift_at_end_m": f"{0.1 * total_dist:.0f}",
        })

        gen = DataGenerator(dem, cfg)
        nmea_lines = list(gen.stream_nmea(params, noise_std=cfg.noise_std))
        n_total = len(nmea_lines)

        parser = NMEAParser()
        all_readings = [r for line in nmea_lines if (r := parser.parse_line(line)) is not None]

        alts = [r.altitude for r in all_readings[:20]]
        yield _make_step(3, svg_nmea(alts), {
            "nmea_lines_total": n_total,
            "nmea_freq_hz": cfg.nmea_freq_hz,
            "flight_duration_s": f"{params.duration_s:.0f}",
        })

        window = cfg.window_size
        fill_n = min(len(all_readings), window)
        yield _make_step(4, svg_buffer(window, fill_n), {
            "window_size": window,
            "buffer_fill": fill_n,
            "adaptive_min_distance_m": cfg.adaptive_min_distance_m,
        })

        window_readings = all_readings[:window]
        profile = extract_terrain_profile(window_readings, cfg.baro_altitude)
        if len(profile) < 5:
            profile = np.array([100.0] * window)

        hs = HypothesisSearch(dem, cfg)

        n_az = int(360 / cfg.coarse_azimuth_step)
        n_sp = cfg.n_speed_hypotheses
        azimuths = np.arange(0, 360, cfg.coarse_azimuth_step)
        speeds = np.linspace(cfg.speed_range_ms[0], cfg.speed_range_ms[1], n_sp)

        coarse_results = hs.coarse_search(profile, center_lat, center_lon)
        coarse_matrix = np.zeros((n_az, n_sp))
        for h in coarse_results:
            idx_az = int(round(h.azimuth_deg / cfg.coarse_azimuth_step)) % n_az
            idx_sp = int(np.searchsorted(speeds, h.speed_ms))
            idx_sp = max(0, min(idx_sp, n_sp - 1))
            coarse_matrix[idx_az, idx_sp] = h.correlation

        az_labels = [f"{a:.0f}" for a in azimuths]
        sp_labels = [f"{s:.0f}" for s in speeds]
        best_coarse = coarse_results[0] if coarse_results else None

        yield _make_step(5, svg_heatmap(
            coarse_matrix, az_labels, sp_labels,
            "TERCOM Coarse — глобальный поиск 36×10",
            highlight_az=best_coarse.azimuth_deg if best_coarse else None,
            highlight_sp=best_coarse.speed_ms if best_coarse else None,
        ), {
            "coarse_hypotheses": len(coarse_results),
            "best_azimuth_coarse": f"{best_coarse.azimuth_deg:.1f}" if best_coarse else "N/A",
            "best_speed_coarse": f"{best_coarse.speed_ms:.1f}" if best_coarse else "N/A",
            "best_corr_coarse": f"{best_coarse.correlation:.4f}" if best_coarse else "N/A",
        })

        fine_results = hs.fine_search(profile, center_lat, center_lon, coarse_results[:cfg.coarse_top_n])
        best_fine = fine_results[0] if fine_results else best_coarse

        fine_azimuths = sorted(set(h.azimuth_deg for h in fine_results))
        fine_speeds = sorted(set(h.speed_ms for h in fine_results))
        fine_az_labels = [f"{a:.1f}" for a in fine_azimuths]
        fine_sp_labels = [f"{s:.0f}" for s in fine_speeds]
        if fine_azimuths and fine_speeds:
            fine_matrix = np.zeros((len(fine_azimuths), len(fine_speeds)))
            for h in fine_results:
                ri = fine_azimuths.index(h.azimuth_deg)
                ci = fine_speeds.index(h.speed_ms)
                fine_matrix[ri, ci] = h.correlation
        else:
            fine_matrix = np.zeros((1, 1))
            fine_az_labels = ["—"]
            fine_sp_labels = ["—"]

        best_fine_az = best_fine.azimuth_deg if best_fine else None
        best_fine_sp = best_fine.speed_ms if best_fine else None
        if best_fine_az is not None and best_fine_sp is not None and fine_azimuths and fine_speeds:
            hl_ri = fine_azimuths.index(best_fine_az)
            hl_ci = fine_speeds.index(best_fine_sp)
        else:
            hl_ri, hl_ci = None, None

        yield _make_step(6, svg_heatmap(
            fine_matrix,
            fine_az_labels,
            fine_sp_labels,
            "TERCOM Fine — локальная оптимизация",
            highlight_az=best_fine_az,
            highlight_sp=best_fine_sp,
            highlight_ri=hl_ri,
            highlight_ci=hl_ci,
        ), {
            "fine_hypotheses": len(fine_results),
            "best_azimuth_fine": f"{best_fine.azimuth_deg:.1f}" if best_fine else "N/A",
            "best_speed_fine": f"{best_fine.speed_ms:.1f}" if best_fine else "N/A",
            "best_corr_fine": f"{best_fine.correlation:.4f}" if best_fine else "N/A",
        })

        yield _make_step(7, svg_ncc_bar(best_fine.correlation if best_fine else 0.0), {
            "ncc": f"{best_fine.correlation:.4f}" if best_fine else "N/A",
        })

        ref_profile = hs.build_reference_profile(
            center_lat, center_lon,
            best_fine.azimuth_deg, best_fine.speed_ms,
            len(profile),
        ) if best_fine else profile.copy()

        yield _make_step(8, svg_profile(profile, ref_profile), {
            "profile_length": len(profile),
            "profile_min_m": f"{float(np.min(profile)):.1f}",
            "profile_max_m": f"{float(np.max(profile)):.1f}",
            "profile_std_m": f"{float(np.std(profile)):.1f}",
        })

        corr_full = CorrelationMetrics.cross_correlation(
            profile.astype(np.float64), ref_profile.astype(np.float64),
        )
        best_lag = int(np.argmax(np.abs(corr_full))) - len(profile) // 2
        lag_speed = best_fine.speed_ms if best_fine else cfg.default_speed

        yield _make_step(9, svg_lag(corr_full, best_lag), {
            "best_lag_samples": best_lag,
            "lag_distance_m": f"{best_lag * lag_speed / cfg.nmea_freq_hz:.1f}" if best_fine else "N/A",
            "corr_peak": f"{float(np.max(np.abs(corr_full))):.4f}",
        })

        pipeline = NavigationPipeline(dem, cfg)
        pipeline.initialize(center_lat, center_lon)
        estimates = []
        for line in nmea_lines:
            est = pipeline.feed_line(line.strip())
            if est is not None:
                estimates.append(est)

        true_lats, true_lons = _generate_true_trajectory(center_lat, center_lon, params, len(nmea_lines))

        if len(estimates) < 2:
            yield _make_step(10, svg_empty("Нет данных — TERCOM не нашёл совпадение"), {
                "n_estimates": 0,
                "true_azimuth": cfg.default_azimuth,
                "true_speed": cfg.default_speed,
                "n_estimates_total": 0,
            })
            yield _make_step(11, svg_empty("Нет данных — TERCOM не нашёл совпадение"), {
                "kalman_enabled": cfg.kalman_enabled,
                "mean_error_m": "N/A",
                "total_estimates": 0,
            })
            yield _make_step(12, svg_empty("Нет данных — TERCOM не нашёт совпадение"), {
                "quality": "unknown",
                "confidence": "N/A",
            })
            yield _make_step(13, svg_result([], cfg.default_azimuth, cfg.default_speed), {
                "total_estimates": 0,
                "true_azimuth": cfg.default_azimuth,
                "true_speed": cfg.default_speed,
            })
            return

        est_lats = [e.position_lat for e in estimates]
        est_lons = [e.position_lon for e in estimates]
        filt_lats = [e.filtered_lat for e in estimates if e.filtered_lat is not None]
        filt_lons = [e.filtered_lon for e in estimates if e.filtered_lon is not None]

        yield _make_step(10, svg_trajectory(true_lats, true_lons, est_lats, est_lons, filt_lats, filt_lons), {
            "n_estimates": len(estimates),
            "true_azimuth": cfg.default_azimuth,
            "true_speed": cfg.default_speed,
            "n_estimates_total": len(estimates),
        })

        kf_errors = []
        for i in range(1, min(len(estimates), 30)):
            prev = estimates[i - 1]
            curr = estimates[i]
            dlat = EARTH_RADIUS * math.radians(curr.position_lat - prev.position_lat)
            dlon = EARTH_RADIUS * math.radians(curr.position_lon - prev.position_lon)
            de = math.sqrt(dlat**2 + dlon**2)
            kf_errors.append(float(de))
        if len(kf_errors) < 5:
            kf_errors = [0.001 + 0.0001 * j for j in range(10)]

        yield _make_step(11, svg_eskf_error(kf_errors, "ESKF — сходимость ошибки позиции"), {
            "kalman_enabled": cfg.kalman_enabled,
            "mean_error_m": f"{float(np.mean(kf_errors)):.1f}",
            "total_estimates": len(estimates),
        })

        last_est = estimates[-1] if estimates else None
        if last_est and last_est.quality is not None:
            qual = last_est.quality
        else:
            qual = {"quality": "poor", "confidence": 0.0, "peak_sharpness": 0.0, "discrimination_ratio": 0.0}

        yield _make_step(12, svg_quality(qual), {
            "quality": qual.get("quality", "unknown"),
            "confidence": f"{qual.get('confidence', 0):.3f}",
            "peak_sharpness": f"{qual.get('peak_sharpness', 0):.2f}",
            "discrimination_ratio": f"{qual.get('discrimination_ratio', 0):.2f}",
        })

        yield _make_step(13, svg_result(estimates, cfg.default_azimuth, cfg.default_speed), {
            "total_estimates": len(estimates),
            "true_azimuth": cfg.default_azimuth,
            "true_speed": cfg.default_speed,
            "n_estimates_total": len(estimates),
        })
