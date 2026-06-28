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
from gagarin.geo_utils import haversine_m
from simulation_ui.texts import STEPS as STEP_TEXTS
from simulation_ui.svg_generator import (
    svg_dem, svg_nmea, svg_buffer, svg_profile,
    svg_heatmap, svg_ncc_bar, svg_lag, svg_trajectory,
    svg_eskf_error, svg_quality, svg_result, svg_corridor,
    svg_fingerprints, svg_empty, svg_aggregated_profile,
    svg_rolling_discrimination, svg_r_matrix,
    svg_recovery_drift, svg_recovery_heatmap, svg_recovery_position,
    svg_replanned_route,
    svg_battery_bar,
    svg_landing_zone,
    svg_analysis_overview,
)
from gagarin.recovery import LostRecoveryModule
from gagarin.replanning import RouteReplanner
from gagarin.landing import LandingZoneFinder

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SCENARIOS = {
    "synthetic": {
        "name": "Камчатка — плавный рельеф",
        "description": "Плавный рельеф, σ=99 м — 12 км на NE, low noise, идеальная корреляция",
        "dem_path": "data/dem/synthetic_kamchatka.tif",
        "dem_name": "Синтетическая Камчатка",
        "dem_size": "400×400",
        "dem_std": "99 м",
        "baro_altitude": 1500.0,
        "flight_duration": 200.0,
        "azimuth_deg": 45,
        "speed_ms": 60,
        "noise_std": 1.0,
    },
    "dramatic": {
        "name": "Камчатка — вулканы и каньоны",
        "description": "6 вулканов, σ=688 м — 20 км на NW через все кратеры, умеренный шум",
        "dem_path": "data/dem/dramatic_kamchatka.tif",
        "dem_name": "Драматическая Камчатка",
        "dem_size": "400×400",
        "dem_std": "688 м",
        "baro_altitude": 3500.0,
        "flight_duration": 250.0,
        "azimuth_deg": 315,
        "speed_ms": 80,
        "noise_std": 2.0,
    },
    "caucasus": {
        "name": "Кавказ — высокогорье",
        "description": "Пики до 5000 м, σ=953 м — 12.5 км на E вдоль Главного хребта",
        "dem_path": "data/dem/caucasus.tif",
        "dem_name": "Кавказ",
        "dem_size": "400×400",
        "dem_std": "953 м",
        "baro_altitude": 5500.0,
        "flight_duration": 250.0,
        "azimuth_deg": 90,
        "speed_ms": 50,
        "noise_std": 1.0,
    },
    "ural": {
        "name": "Урал — горный хребет",
        "description": "Пологий хребет 1000–1500 м, σ=495 м — 12 км на N вдоль хребта, шум 3 м",
        "dem_path": "data/dem/ural.tif",
        "dem_name": "Урал",
        "dem_size": "400×400",
        "dem_std": "495 м",
        "baro_altitude": 2000.0,
        "flight_duration": 200.0,
        "azimuth_deg": 0,
        "speed_ms": 60,
        "noise_std": 3.0,
    },
    "altai": {
        "name": "Алтай — плато и пики",
        "description": "Плато 2000 м + пики 3500 м, σ=817 м — 17.5 км на SE",
        "dem_path": "data/dem/altai.tif",
        "dem_name": "Алтай",
        "dem_size": "400×400",
        "dem_std": "817 м",
        "baro_altitude": 4000.0,
        "flight_duration": 250.0,
        "azimuth_deg": 135,
        "speed_ms": 70,
        "noise_std": 1.5,
    },
    "crimea": {
        "name": "Крым — горы и море",
        "description": "Прибрежный гребень 1000 м, σ=326 м — 8 км на S от гор к морю, шум 3 м",
        "dem_path": "data/dem/crimea.tif",
        "dem_name": "Крым",
        "dem_size": "400×400",
        "dem_std": "326 м",
        "baro_altitude": 1500.0,
        "flight_duration": 200.0,
        "azimuth_deg": 180,
        "speed_ms": 40,
        "noise_std": 3.0,
    },
    "siberia": {
        "name": "Западная Сибирь — равнина",
        "description": "Плоский рельеф 30–86 м, σ=17 м — 24 км, TERCOM должен сорваться",
        "dem_path": "data/dem/siberia.tif",
        "dem_name": "Сибирская равнина",
        "dem_size": "400×400",
        "dem_std": "17 м",
        "baro_altitude": 300.0,
        "flight_duration": 300.0,
        "azimuth_deg": 45,
        "speed_ms": 80,
        "noise_std": 1.0,
    },
    "sakhalin": {
        "name": "Сахалин — островные сопки",
        "description": "Узкий остров с сопками 500–800 м, σ=358 м — 10 км вдоль оси",
        "dem_path": "data/dem/sakhalin.tif",
        "dem_name": "Сахалин",
        "dem_size": "400×400",
        "dem_std": "358 м",
        "baro_altitude": 1200.0,
        "flight_duration": 200.0,
        "azimuth_deg": 90,
        "speed_ms": 50,
        "noise_std": 2.5,
    },
    "karelia": {
        "name": "Карелия — холмы и озёра",
        "description": "Мягкие холмы 100–300 м, σ=85 м — 8 км на W через озёра, шум 3 м",
        "dem_path": "data/dem/karelia.tif",
        "dem_name": "Карелия",
        "dem_size": "400×400",
        "dem_std": "85 м",
        "baro_altitude": 500.0,
        "flight_duration": 200.0,
        "azimuth_deg": 270,
        "speed_ms": 40,
        "noise_std": 3.0,
    },
    "primorye": {
        "name": "Приморье — сопки и побережье",
        "description": "Холмистый рельеф 300–800 м, σ=222 м — 15 км на SW вдоль побережья",
        "dem_path": "data/dem/primorye.tif",
        "dem_name": "Приморье",
        "dem_size": "400×400",
        "dem_std": "222 м",
        "baro_altitude": 1200.0,
        "flight_duration": 250.0,
        "azimuth_deg": 225,
        "speed_ms": 60,
        "noise_std": 1.5,
    },
}


def get_scenarios() -> Dict[str, Dict[str, Any]]:
    result = {}
    for sid, info in SCENARIOS.items():
        dem_path = os.path.join(PROJECT_ROOT, info["dem_path"])
        result[sid] = dict(info)
        result[sid]["exists"] = os.path.exists(dem_path)
    return dict(sorted(result.items(), key=lambda x: x[1].get("name", "")))


def _serialize(v):
    if isinstance(v, dict):
        return {k: _serialize(v) for k, v in v.items()}
    if isinstance(v, (list, tuple)):
        return [_serialize(item) for item in v]
    if isinstance(v, np.floating):
        return float(v)
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.ndarray):
        return _serialize(v.tolist())
    return v


def _make_step(step_idx: int, svg: str, metrics: dict) -> Dict[str, Any]:
    t = STEP_TEXTS[step_idx]
    safe_metrics = {k: _serialize(v) for k, v in metrics.items()}
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
        dlat = d * math.cos(params.azimuth_rad) / EARTH_RADIUS
        dlon = d * math.sin(params.azimuth_rad) / (EARTH_RADIUS * cos_clat)
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
        self.azimuth_deg = info.get("azimuth_deg", 45)
        self.speed_ms = info.get("speed_ms", 60)
        self.noise_std = info.get("noise_std", 1.0)

    def run(self, overrides: dict = None) -> Generator[Dict[str, Any], None, None]:
        cfg = Config.default()
        info = SCENARIOS[self.scenario_id]
        cfg.noise_std = info.get("noise_std", 1.0)
        cfg.default_azimuth = info.get("azimuth_deg", 45)
        cfg.default_speed = info.get("speed_ms", 60)
        cfg.flight_duration = self.flight_duration
        cfg.baro_altitude = info["baro_altitude"]
        if overrides:
            for k, v in overrides.items():
                if hasattr(cfg, k):
                    setattr(cfg, k, v)

        dem = DEMLoader(self.dem_path)
        bounds = dem.bounds
        center_lat = (bounds[1] + bounds[3]) / 2
        center_lon = (bounds[0] + bounds[2]) / 2

        params = FlightParams(
            start_lat=center_lat,
            start_lon=center_lon,
            azimuth_deg=cfg.default_azimuth,
            speed_ms=cfg.default_speed,
            duration_s=cfg.flight_duration,
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
            dlat = d * math.cos(az_rad) / EARTH_RADIUS
            dlon = d * math.sin(az_rad) / (EARTH_RADIUS * cos_clat)
            route_lats.append(center_lat + math.degrees(dlat))
            route_lons.append(center_lon + math.degrees(dlon))

        grad_map = analyzer.gradient_magnitude()
        std_vals, grad_vals = [], []
        for lat, lon in zip(route_lats, route_lons):
            def _sample(grid):
                ri = int((lat - bounds[1]) / (bounds[3] - bounds[1]) * (grid.shape[0] - 1))
                ci = int((lon - bounds[0]) / (bounds[2] - bounds[0]) * (grid.shape[1] - 1))
                ri = max(0, min(ri, grid.shape[0] - 1))
                ci = max(0, min(ci, grid.shape[1] - 1))
                return float(grid[ri, ci])
            std_vals.append(_sample(std_map))
            grad_vals.append(_sample(grad_map))

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

        max_nmea_pts = 120
        if len(all_readings) > max_nmea_pts:
            nmea_step = len(all_readings) // max_nmea_pts
            alts = [r.altitude for r in all_readings[::nmea_step]]
        else:
            alts = [r.altitude for r in all_readings]
        yield _make_step(3, svg_nmea(alts), {
            "nmea_lines_total": n_total,
            "nmea_shown": len(alts),
            "nmea_freq_hz": cfg.nmea_freq_hz,
            "flight_duration_s": f"{params.duration_s:.0f}",
            "noise_std_m": cfg.noise_std,
            "speed_ms": params.speed_ms,
            "azimuth_deg": params.azimuth_deg,
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
            f"TERCOM Coarse — глобальный поиск {n_az}×{n_sp}",
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

        all_profiles = [profile.copy()]
        agg_window = cfg.window_size
        for i in range(1, 5):
            start_idx = i * agg_window // 5
            end_idx = min(start_idx + agg_window, len(all_readings))
            if end_idx - start_idx >= 5:
                wr = all_readings[start_idx:end_idx]
                p = extract_terrain_profile(wr, cfg.baro_altitude)
                all_profiles.append(p)
        min_len = min(len(p) for p in all_profiles) if all_profiles else 0
        if min_len > 0 and len(all_profiles) > 1:
            all_profiles = [p[:min_len] for p in all_profiles]
            aggregated = np.mean(all_profiles, axis=0)
        else:
            aggregated = profile.copy()

        yield _make_step(10, svg_aggregated_profile(all_profiles[:min(5, len(all_profiles))], aggregated), {
            "n_windows_aggregated": len(all_profiles),
            "aggregated_std": f"{float(np.std(aggregated)):.1f}",
            "stability_gain": f"{float(np.std(profile) / np.std(aggregated)):.2f}x",
        })

        if len(all_profiles) >= 2:
            rolling_corr = float(np.corrcoef(all_profiles[0], all_profiles[-1])[0, 1]) if min_len > 1 else 0.0
            rolling_corr = 1.0 if np.isnan(rolling_corr) else rolling_corr
        else:
            rolling_corr = 0.0

        yield _make_step(11, svg_rolling_discrimination(
            all_profiles[-1] if all_profiles else profile,
            all_profiles[0] if all_profiles else profile,
            rolling_corr,
        ), {
            "rolling_correlation": f"{rolling_corr:.3f}",
            "согласованность": "высокая" if rolling_corr > 0.9 else "средняя" if rolling_corr > 0.7 else "низкая",
            "прогноз_отката": "нет" if rolling_corr > 0.7 else "да",
        })

        r_scale = 1.0 if best_fine and best_fine.correlation >= 0.8 else 5.0 if best_fine and best_fine.correlation < 0.5 else 3.0
        base_r = max((1.0 - best_fine.correlation) * 200.0, 20.0) if best_fine else 100.0

        yield _make_step(12, svg_r_matrix(base_r, r_scale), {
            "r_scale": f"{r_scale:.1f}x",
            "адаптивный_отклик": "игнорирован" if r_scale > 3 else "применён",
            "уровень_доверия": "высокий" if r_scale < 2 else "низкий",
        })

        pipeline = NavigationPipeline(dem, cfg)
        pipeline.initialize(center_lat, center_lon)
        estimates = []
        estimate_indices = []
        for idx, line in enumerate(nmea_lines):
            est = pipeline.feed_line(line.strip())
            if est is not None:
                estimates.append(est)
                estimate_indices.append(idx)

        true_lats, true_lons = _generate_true_trajectory(center_lat, center_lon, params, len(nmea_lines))

        if len(estimates) < 2:
            yield _make_step(13, svg_empty("Нет данных — TERCOM не нашёл совпадение"), {
                "n_estimates": 0,
                "true_azimuth": cfg.default_azimuth,
                "true_speed": cfg.default_speed,
                "n_estimates_total": 0,
            })
            yield _make_step(14, svg_empty("Нет данных — TERCOM не нашёл совпадение"), {
                "kalman_enabled": cfg.kalman_enabled,
                "mean_error_m": "N/A",
                "total_estimates": 0,
            })
            yield _make_step(15, svg_empty("Нет данных — TERCOM не нашёл совпадение"), {
                "quality": "unknown",
                "confidence": "N/A",
            })
            yield _make_step(16, svg_result([], cfg.default_azimuth, cfg.default_speed), {
                "total_estimates": 0,
                "true_azimuth": cfg.default_azimuth,
                "true_speed": cfg.default_speed,
            })
            yield _make_step(18, "", {"trajectory": None})
            return

        est_lats = [e.position_lat for e in estimates]
        est_lons = [e.position_lon for e in estimates]
        filt_lats = [e.filtered_lat for e in estimates if e.filtered_lat is not None]
        filt_lons = [e.filtered_lon for e in estimates if e.filtered_lon is not None]

        yield _make_step(13, svg_trajectory(true_lats, true_lons, est_lats, est_lons, filt_lats, filt_lons), {
            "n_estimates": len(estimates),
            "true_azimuth": cfg.default_azimuth,
            "true_speed": cfg.default_speed,
            "n_estimates_total": len(estimates),
        })

        position_drift = []
        for i in range(1, min(len(estimates), 30)):
            prev = estimates[i - 1]
            curr = estimates[i]
            dlat = EARTH_RADIUS * math.radians(curr.position_lat - prev.position_lat)
            dlon = EARTH_RADIUS * math.radians(curr.position_lon - prev.position_lon)
            de = math.sqrt(dlat**2 + dlon**2)
            position_drift.append(float(de))
        if len(position_drift) < 5:
            position_drift = [0.001 + 0.0001 * j for j in range(10)]

        yield _make_step(14, svg_eskf_error(position_drift, "Дрейф позиции между оценками TERCOM"), {
            "kalman_enabled": cfg.kalman_enabled,
            "mean_drift_m": f"{float(np.mean(position_drift)):.1f}",
            "total_estimates": len(estimates),
        })

        last_est = estimates[-1] if estimates else None
        if last_est and last_est.quality is not None:
            qual = last_est.quality
        else:
            qual = {"quality": "poor", "confidence": 0.0, "peak_sharpness": 0.0, "discrimination_ratio": 0.0}

        yield _make_step(15, svg_quality(qual), {
            "quality": qual.get("quality", "unknown"),
            "confidence": f"{qual.get('confidence', 0):.3f}",
            "peak_sharpness": f"{qual.get('peak_sharpness', 0):.2f}",
            "discrimination_ratio": f"{qual.get('discrimination_ratio', 0):.2f}",
        })

        yield _make_step(16, svg_result(estimates, cfg.default_azimuth, cfg.default_speed), {
            "total_estimates": len(estimates),
            "true_azimuth": cfg.default_azimuth,
            "true_speed": cfg.default_speed,
            "n_estimates_total": len(estimates),
        })

        est_elevations = []
        for e in estimates:
            try:
                est_elevations.append(float(dem.elevation(e.position_lat, e.position_lon)))
            except Exception:
                est_elevations.append(0.0)

        true_elevations = []
        for lat, lon in zip(true_lats, true_lons):
            try:
                true_elevations.append(float(dem.elevation(lat, lon)))
            except Exception:
                true_elevations.append(0.0)

        first_est = estimates[0] if estimates else None
        first_est_idx = estimate_indices[0] if estimate_indices else None

        trajectory_data = {
            "trajectory": {
                "true_path": [[round(float(lat), 6), round(float(lon), 6)] for lat, lon in zip(true_lats, true_lons)],
                "estimates": [
                    {
                        "lat": float(e.position_lat), "lon": float(e.position_lon),
                        "correlation": float(e.correlation),
                        "quality": e.quality.get("quality", "unknown") if e.quality else "unknown",
                        "speed_ms": float(e.speed_ms), "azimuth_deg": float(e.azimuth_deg),
                        "elevation": float(elev), "nmea_index": int(idx),
                    }
                    for e, elev, idx in zip(estimates, est_elevations, estimate_indices)
                ],
                "filtered_path": [[round(float(lat), 6), round(float(lon), 6)] for lat, lon in zip(filt_lats, filt_lons)],
                "start": {"lat": float(true_lats[0]), "lon": float(true_lons[0])},
                "end": {"lat": float(true_lats[-1]), "lon": float(true_lons[-1])},
                "n_nmea": len(nmea_lines),
                "true_azimuth_deg": cfg.default_azimuth,
                "true_speed_ms": cfg.default_speed,
                "first_estimate": {
                    "lat": float(first_est.position_lat),
                    "lon": float(first_est.position_lon),
                    "nmea_index": int(first_est_idx),
                } if first_est else None,
                "elevation_profile": true_elevations,
                "buffer_window_size": cfg.window_size,
            },
        }
        yield _make_step(18, "", _serialize(trajectory_data))

        recovery = LostRecoveryModule(dem, cfg)
        lost_segments = recovery.detect_lost_segments(estimates, min_consecutive=5)
        lost_start, lost_end = None, None
        recovery_info = None
        if lost_segments:
            lost_start, lost_end = lost_segments[-1]
            drift_m = haversine_m(true_lats[lost_start], true_lons[lost_start],
                                  true_lats[lost_end], true_lons[lost_end])
            yield _make_step(19, svg_recovery_drift(lost_start, lost_end, len(nmea_lines), drift_m), {
                "lost_start": lost_start,
                "lost_end": lost_end,
                "drift_accumulated_m": f"{drift_m:.1f}",
                "lost_duration_s": f"{(lost_end - lost_start) / cfg.nmea_freq_hz:.1f}",
            })

            last_good_idx = lost_start - 1 if lost_start > 0 else 0
            last_good_est = estimates[min(last_good_idx, len(estimates) - 1)]
            dr_lat = last_good_est.position_lat
            dr_lon = last_good_est.position_lon

            true_target_lat = true_lats[lost_end]
            true_target_lon = true_lons[lost_end]

            rec_window = cfg.window_size
            rec_end = min(lost_end, len(all_readings) - 1)
            rec_start = max(0, rec_end - rec_window + 1)
            rec_readings = all_readings[rec_start:rec_end + 1]
            rec_profile = extract_terrain_profile(rec_readings, cfg.baro_altitude)
            if len(rec_profile) < 5:
                rec_profile = np.array([100.0] * max(rec_window, 5))

            rec_result = recovery.recover(
                rec_profile, dr_lat, dr_lon,
                last_good_est.azimuth_deg if last_good_est else cfg.default_azimuth,
                last_good_est.speed_ms if last_good_est else cfg.default_speed,
                search_radius_m=500.0, grid_size=7,
            )

            rec_error = haversine_m(rec_result.recovered_lat, rec_result.recovered_lon,
                                    true_target_lat, true_target_lon)

            yield _make_step(20, svg_recovery_heatmap(
                500.0, rec_result.correlation, rec_result.confidence,
                rec_result.best_ri, rec_result.best_ci,
            ), {
                "best_correlation": f"{rec_result.correlation:.4f}",
                "confidence": f"{rec_result.confidence:.2f}",
                "recovered_lat": f"{rec_result.recovered_lat:.6f}",
                "recovered_lon": f"{rec_result.recovered_lon:.6f}",
                "grid_size": 7,
                "search_radius_m": 500.0,
            })

            yield _make_step(21, svg_recovery_position(
                true_target_lat, true_target_lon,
                rec_result.recovered_lat, rec_result.recovered_lon,
                dr_lat, dr_lon, rec_error,
            ), {
                "recovery_error_m": f"{rec_error:.1f}",
                "true_lat": f"{true_target_lat:.6f}",
                "true_lon": f"{true_target_lon:.6f}",
                "dr_lat": f"{dr_lat:.6f}",
                "dr_lon": f"{dr_lon:.6f}",
            })

            finish_lat = true_lats[-1]
            finish_lon = true_lons[-1]
            replanner = RouteReplanner()
            route = replanner.replan(rec_result.recovered_lat, rec_result.recovered_lon,
                                      finish_lat, finish_lon, n_waypoints=20)

            new_lats = [p[0] for p in route.waypoints]
            new_lons = [p[1] for p in route.waypoints]

            yield _make_step(22, svg_replanned_route(
                route_lats, route_lons,
                rec_result.recovered_lat, rec_result.recovered_lon,
                new_lats, new_lons,
                finish_lat, finish_lon,
                route.total_distance_m / 1000.0,
            ), {
                "new_distance_km": f"{route.total_distance_m / 1000:.2f}",
                "n_waypoints": route.n_waypoints,
                "recovery_lat": f"{rec_result.recovered_lat:.6f}",
                "recovery_lon": f"{rec_result.recovered_lon:.6f}",
                "finish_lat": f"{finish_lat:.6f}",
                "finish_lon": f"{finish_lon:.6f}",
            })

            max_flight_s = cfg.flight_duration
            elapsed_s = lost_end / cfg.nmea_freq_hz
            remaining_s = max_flight_s - elapsed_s
            reserve_s = max_flight_s * cfg.battery_reserve_pct / 100.0
            available_s = remaining_s - reserve_s

            current_speed = last_good_est.speed_ms if last_good_est else cfg.default_speed
            max_range_m = available_s * current_speed

            start_lat = true_lats[0]
            start_lon = true_lons[0]

            dist_to_finish_m = haversine_m(rec_result.recovered_lat, rec_result.recovered_lon,
                                            finish_lat, finish_lon)
            dist_to_start_m = haversine_m(rec_result.recovered_lat, rec_result.recovered_lon,
                                           start_lat, start_lon)

            total_flight_range_m = current_speed * max_flight_s
            to_finish_pct = dist_to_finish_m / max(total_flight_range_m, 1) * 100.0
            to_start_pct = dist_to_start_m / max(total_flight_range_m, 1) * 100.0
            remaining_pct = remaining_s / max_flight_s * 100.0

            if dist_to_finish_m <= max_range_m:
                decision = "finish"
            elif dist_to_start_m <= max_range_m:
                decision = "return"
            else:
                decision = "land"

            yield _make_step(23, svg_battery_bar(
                remaining_pct, to_finish_pct, to_start_pct, decision, cfg.battery_reserve_pct,
            ), {
                "remaining_pct": f"{remaining_pct:.1f}",
                "to_finish_pct": f"{to_finish_pct:.1f}",
                "to_start_pct": f"{to_start_pct:.1f}",
                "decision": decision,
                "max_range_m": f"{max_range_m:.0f}",
                "dist_to_finish_m": f"{dist_to_finish_m:.0f}",
                "dist_to_start_m": f"{dist_to_start_m:.0f}",
            })

            if decision == "land":
                finder = LandingZoneFinder(dem)
                landing_zone = finder.find_landing_zone(
                    rec_result.recovered_lat, rec_result.recovered_lon,
                    search_radius_m=500.0, window_size_m=30.0,
                    flatness_threshold_m=5.0, min_area_m2=400.0,
                )

                if landing_zone:
                    lons, lats, data = dem.get_geographic_grid()
                    yield _make_step(24, svg_landing_zone(
                        lons, lats, data,
                        rec_result.recovered_lat, rec_result.recovered_lon,
                        landing_zone.lat, landing_zone.lon,
                        landing_zone.polygon_lats, landing_zone.polygon_lons,
                        landing_zone.flatness_m, landing_zone.area_m2,
                    ), {
                        "zone_lat": f"{landing_zone.lat:.6f}",
                        "zone_lon": f"{landing_zone.lon:.6f}",
                        "flatness_m": f"{landing_zone.flatness_m:.1f}",
                        "area_m2": f"{landing_zone.area_m2:.0f}",
                        "cell_count": landing_zone.cell_count,
                    })

                    zone_replanner = RouteReplanner()
                    zone_route = zone_replanner.replan(
                        rec_result.recovered_lat, rec_result.recovered_lon,
                        landing_zone.lat, landing_zone.lon, n_waypoints=15,
                    )
                    zone_new_lats = [p[0] for p in zone_route.waypoints]
                    zone_new_lons = [p[1] for p in zone_route.waypoints]

                    yield _make_step(25, svg_replanned_route(
                        route_lats, route_lons,
                        rec_result.recovered_lat, rec_result.recovered_lon,
                        zone_new_lats, zone_new_lons,
                        landing_zone.lat, landing_zone.lon,
                        zone_route.total_distance_m / 1000.0,
                    ), {
                        "new_distance_km": f"{zone_route.total_distance_m / 1000:.2f}",
                        "n_waypoints": zone_route.n_waypoints,
                        "decision": "land",
                        "zone_lat": f"{landing_zone.lat:.6f}",
                        "zone_lon": f"{landing_zone.lon:.6f}",
                    })
                else:
                    yield _make_step(24, svg_empty("Зона посадки не найдена"), {"decision": "land", "zone_found": False})
            elif decision == "return":
                return_replanner = RouteReplanner()
                return_route = return_replanner.replan(
                    rec_result.recovered_lat, rec_result.recovered_lon,
                    start_lat, start_lon, n_waypoints=20,
                )
                return_new_lats = [p[0] for p in return_route.waypoints]
                return_new_lons = [p[1] for p in return_route.waypoints]

                yield _make_step(24, svg_replanned_route(
                    route_lats, route_lons,
                    rec_result.recovered_lat, rec_result.recovered_lon,
                    return_new_lats, return_new_lons,
                    start_lat, start_lon,
                    return_route.total_distance_m / 1000.0,
                ), {
                    "new_distance_km": f"{return_route.total_distance_m / 1000:.2f}",
                    "n_waypoints": return_route.n_waypoints,
                    "decision": "return",
                })
            else:
                yield _make_step(24, svg_replanned_route(
                    route_lats, route_lons,
                    rec_result.recovered_lat, rec_result.recovered_lon,
                    new_lats, new_lons,
                    finish_lat, finish_lon,
                    route.total_distance_m / 1000.0,
                ), {
                    "new_distance_km": f"{route.total_distance_m / 1000:.2f}",
                    "n_waypoints": route.n_waypoints,
                    "decision": "finish",
                })

        recovery_info = {
            "lost_duration_s": f"{(lost_end - lost_start) / cfg.nmea_freq_hz:.1f}",
            "drift_m": float(drift_m),
            "recovery_error_m": float(rec_error),
            "decision": decision,
        }

        segments = []
        for i, est in enumerate(estimates):
            true_idx = min(i, len(true_lats) - 1)
            err_m = haversine_m(est.position_lat, est.position_lon,
                                true_lats[true_idx], true_lons[true_idx])
            is_lost = any(ls[0] <= i <= ls[1] for ls in (lost_segments or []))
            segments.append({
                "corr": float(est.correlation),
                "quality": est.quality.get("quality", "unknown") if est.quality else "unknown",
                "error_m": float(err_m),
                "is_lost": is_lost,
            })

        n = len(segments)
        sampled = []
        for ci in range(min(n, 50)):
            idx = int(ci * n / max(n, 50))
            idx = min(idx, n - 1)
            sampled.append(segments[idx])

        errs = [s["error_m"] for s in segments]
        quals = [s["quality"] for s in segments]
        corrs = [s["corr"] for s in segments]
        total_dist = haversine_m(true_lats[0], true_lons[0], true_lats[-1], true_lons[-1])

        stats = {
            "n_estimates": n,
            "mean_corr": float(np.mean(corrs)),
            "good_pct": sum(1 for q in quals if q == "good") / max(n, 1) * 100.0,
            "max_error_m": float(max(errs)),
            "total_distance_km": total_dist / 1000.0,
        }

        yield _make_step(26, svg_analysis_overview(sampled, stats, recovery_info), {
            "n_segments": n,
            "mean_corr": f"{stats['mean_corr']:.3f}",
            "good_pct": f"{stats['good_pct']:.1f}",
            "max_error_m": f"{stats['max_error_m']:.0f}",
            "total_distance_km": f"{stats['total_distance_km']:.2f}",
            "recovery_present": str(recovery_info is not None),
        })
