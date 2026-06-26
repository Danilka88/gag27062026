import os
import sys
import json
import time
from typing import Optional, Tuple
import numpy as np
import click

from gagarin.dem_loader import DEMLoader
from gagarin.data_generator import DataGenerator, FlightParams
from gagarin.pipeline import NavigationPipeline
from gagarin.correlator import CorrelationMetrics, HypothesisSearch
from gagarin.geo_utils import offset_coords_batch
from gagarin.viz import (
    correlation_heatmap,
    trajectory_map,
    profile_comparison,
    navigation_dashboard,
    comparison_dashboard,
    save_html,
    build_dashboard_data,
)
from gagarin.config import Config


@click.group()
def cli():
    pass


@cli.command()
@click.option("--output", "-o", default="data/dem/dramatic_kamchatka.tif", help="Output path")
@click.option("--nx", default=400, type=int, help="Width in pixels")
@click.option("--ny", default=400, type=int, help="Height in pixels")
def generate_dem(output: str, nx: int, ny: int):
    _generate_dramatic_dem(output, nx, ny)
    click.echo(f"Dramatic DEM saved to {output}")


@cli.command()
@click.option("--place", default="kamchatka", help="Place name or lat,lon")
@click.option("--output-dir", "-o", default="data/dem", help="Output directory")
@click.option("--margin", "-m", default=0.15, type=float, help="Margin in degrees")
def download_dem(place: str, output_dir: str, margin: float):
    from download_dem import resolve_coordinates, download_region
    try:
        lat, lon = resolve_coordinates(place)
    except ValueError:
        parts = place.split(",")
        lat, lon = float(parts[0]), float(parts[1])
    click.echo(f"Center: {lat:.4f}, {lon:.4f}")
    files = download_region(lat, lon, output_dir, margin)
    click.echo(f"Downloaded {len(files)} tile(s)")


@cli.command()
@click.argument("config_path", default="config.json", required=False)
@click.option("--compare", "-c", is_flag=True, help="Also run on dramatic DEM for comparison")
def run(config_path: str, compare: bool):
    cfg = _load_config(config_path)

    synthetic = os.path.join(cfg.dem_path, "synthetic_kamchatka.tif")
    dramatic = os.path.join(cfg.dem_path, "dramatic_kamchatka.tif")
    dem_paths = []
    if os.path.exists(synthetic):
        dem_paths.append(("synthetic", synthetic))
    if compare and os.path.exists(dramatic):
        dem_paths.append(("dramatic", dramatic))
    if not dem_paths:
        found = _find_dem(cfg.dem_path)
        if found:
            dem_paths.append(("discovered", found))

    all_data = {}
    for name, dem_path in dem_paths:
        if not dem_path:
            click.echo(f"No DEM found for {name}.", err=True)
            continue

        click.echo(f"\n{'='*60}")
        click.echo(f"Running on {name.upper()} DEM: {dem_path}")
        click.echo(f"{'='*60}")
        dem = DEMLoader(dem_path)
        click.echo(f"DEM loaded: {dem.bounds}")

        gen = DataGenerator(dem, cfg)

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

        click.echo(f"True azimuth: {cfg.default_azimuth:.1f}°, speed: {cfg.default_speed:.1f} m/s")
        nmea_path = os.path.join(cfg.output_path, f"flight_log_{name}.nmea")
        os.makedirs(cfg.output_path, exist_ok=True)
        gen.generate_nmea_file(nmea_path, params, noise_std=cfg.noise_std)
        click.echo(f"NMEA log: {nmea_path}")

        pipeline = NavigationPipeline(dem, cfg)
        pipeline.initialize(center_lat, center_lon)

        click.echo("\n--- Processing NMEA stream ---")
        results = []
        start = time.time()
        with open(nmea_path) as f:
            for line in f:
                est = pipeline.feed_line(line.strip())
                if est is not None:
                    results.append(est)
                    click.echo(
                        f"  az={est.azimuth_deg:.1f}° "
                        f"(true={cfg.default_azimuth:.1f}°) "
                        f"v={est.speed_ms:.1f} m/s "
                        f"(true={cfg.default_speed:.1f}) "
                        f"conf={est.confidence:.3f}"
                    )
        elapsed = time.time() - start

        click.echo(f"\n--- Results ({len(results)} estimates in {elapsed:.2f}s) ---")
        if results:
            first = results[0]
            click.echo("First estimate:")
            click.echo(f"  Azimuth:  {first.azimuth_deg:.1f}° (true: {cfg.default_azimuth:.1f}°)")
            click.echo(f"  Speed:    {first.speed_ms:.1f} m/s (true: {cfg.default_speed:.1f} m/s)")
            click.echo(f"  Correlation: {first.correlation:.4f}")
            click.echo(f"  Confidence: {first.confidence:.3f}")

        out_dir = os.path.join(cfg.output_path, name) if compare else cfg.output_path
        json_path = os.path.join(out_dir, "estimates.json")
        with open(json_path, "w") as f:
            json.dump(
                [{k: float(v) if isinstance(v, (np.floating,)) else v
                  for k, v in r.__dict__.items()
                  if v is None or isinstance(v, (int, float, str, bool, list, dict))}
                 for r in results],
                f, indent=2, default=str,
            )
        click.echo(f"Estimates: {json_path} ({len(results)} estimates)")
        _generate_visualizations(dem, results, params, cfg, gen, pipeline, out_dir, dem_name=name)
        click.echo(f"Visualizations saved to {out_dir}/")

        all_data[name] = dict(
            dem=dem, results=results, params=params, cfg=cfg, pipeline=pipeline,
        )

    if compare and "synthetic" in all_data and "dramatic" in all_data:
        click.echo("\n" + "=" * 60)
        click.echo("Generating comparison dashboard...")
        click.echo("=" * 60)

        syn = all_data["synthetic"]
        dram = all_data["dramatic"]
        syn_pipeline = syn["pipeline"]
        dram_pipeline = dram["pipeline"]
        cfg_cmp = syn["cfg"]

        n_sp = cfg_cmp.n_speed_hypotheses
        azimuths = np.arange(0, 360, cfg_cmp.coarse_azimuth_step)
        speeds = np.linspace(cfg_cmp.speed_range_ms[0], cfg_cmp.speed_range_ms[1], n_sp)
        traj_lats, traj_lons = _generate_trajectory(syn["params"], cfg_cmp)

        corr_syn, obs_syn, ref_syn = _build_correlation_matrix(syn["dem"], cfg_cmp, pipeline=syn_pipeline)
        corr_dram, obs_dram, ref_dram = _build_correlation_matrix(dram["dem"], cfg_cmp, pipeline=dram_pipeline)

        dash_syn = build_dashboard_data(
            syn["dem"], syn["results"], syn["params"], cfg_cmp,
            traj_lats, traj_lons,
            corr_syn, obs_syn, ref_syn,
            azimuths, speeds,
            dem_name="Synthetic",
        )
        dash_dram = build_dashboard_data(
            dram["dem"], dram["results"], dram["params"], cfg_cmp,
            traj_lats, traj_lons,
            corr_dram, obs_dram, ref_dram,
            azimuths, speeds,
            dem_name="Dramatic",
        )

        fig_cmp = comparison_dashboard(dash_syn, dash_dram)

        cmp_path = os.path.join(cfg.output_path, "comparison_dashboard.html")
        save_html(fig_cmp, cmp_path)
        click.echo(f"Comparison dashboard: {cmp_path}")


@cli.command()
@click.argument("nmea_path")
@click.option("--dem", "-d", default=None, help="Path to DEM file")
@click.option("--lat", type=float, default=None, help="Start latitude")
@click.option("--lon", type=float, default=None, help="Start longitude")
@click.option("--realtime", is_flag=True, help="Stream in real-time")
def analyze(
    nmea_path: str,
    dem: Optional[str],
    lat: Optional[float],
    lon: Optional[float],
    realtime: bool,
):
    cfg = Config.default()

    if not dem:
        dem = _find_dem(cfg.dem_path)
    if not dem:
        click.echo("No DEM found. Use --dem or run download-dem first.", err=True)
        sys.exit(1)

    click.echo(f"Loading DEM: {dem}")
    dem_loader = DEMLoader(dem)

    if lat is None or lon is None:
        bounds = dem_loader.bounds
        lat = (bounds[1] + bounds[3]) / 2
        lon = (bounds[0] + bounds[2]) / 2
        click.echo(f"Using center: ({lat:.4f}, {lon:.4f})")

    pipeline = NavigationPipeline(dem_loader, cfg)
    pipeline.initialize(lat, lon)

    if realtime:
        pipeline.stream_file(nmea_path)
    else:
        click.echo("Processing NMEA file...")
        results = pipeline.feed_file(nmea_path)
        click.echo(f"Processed {len(results)} estimates")

        if results:
            final = results[-1]
            click.echo(f"Final: az={final.azimuth_deg:.1f}°, v={final.speed_ms:.1f} m/s")

        json_path = os.path.join(cfg.output_path, "estimates.json")
        with open(json_path, "w") as f:
            json.dump(
                [{k: float(v) if isinstance(v, (np.floating,)) else v
                  for k, v in r.__dict__.items()
                  if v is None or isinstance(v, (int, float, str, bool, list, dict))}
                 for r in results],
                f, indent=2, default=str,
            )
        click.echo(f"Estimates saved to {json_path}")


def _find_dem(dem_dir: str) -> Optional[str]:
    dem_dir = os.path.join(os.path.dirname(__file__), dem_dir)
    if not os.path.isdir(dem_dir):
        return None
    for f in sorted(os.listdir(dem_dir)):
        if f.endswith(".tif"):
            return os.path.join(dem_dir, f)
    return None


def _load_config(path: str) -> Config:
    cfg = Config.default()
    full_path = os.path.join(os.path.dirname(__file__), path)
    if os.path.exists(full_path):
        with open(full_path) as f:
            data = json.load(f)
        cfg = cfg.merge(data)
        click.echo(f"Loaded config from {full_path}")
    return cfg


def _generate_trajectory(params: FlightParams, cfg: Config) -> Tuple[np.ndarray, np.ndarray]:
    dt = 1.0 / cfg.nmea_freq_hz
    n = int(params.duration_s * cfg.nmea_freq_hz)
    distances = np.arange(n) * params.speed_ms * dt
    start_lats = np.full(n, params.start_lat)
    start_lons = np.full(n, params.start_lon)
    return offset_coords_batch(start_lats, start_lons, distances, params.azimuth_rad, params.start_lat)


def _build_correlation_matrix(
    dem: DEMLoader, cfg: Config,
    pipeline: NavigationPipeline = None,
    gen: DataGenerator = None,
    params: FlightParams = None,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    n_az = int(360 / cfg.coarse_azimuth_step)
    n_sp = cfg.n_speed_hypotheses
    azimuths = np.arange(0, 360, cfg.coarse_azimuth_step)
    speeds = np.linspace(cfg.speed_range_ms[0], cfg.speed_range_ms[1], n_sp)
    hs = HypothesisSearch(dem, cfg)
    center_lat = (dem.bounds[1] + dem.bounds[3]) / 2
    center_lon = (dem.bounds[0] + dem.bounds[2]) / 2

    corr_matrix = np.zeros((n_az, n_sp))
    obs_profile = np.array([])
    ref_profile = np.array([])

    if pipeline and pipeline.last_result is not None:
        obs_profile = pipeline.last_result.observed_profile
        ref_profile = pipeline.last_result.reference_profile
        for i, az in enumerate(azimuths):
            for j, sp in enumerate(speeds):
                ref = hs.build_reference_profile(center_lat, center_lon, az, sp, len(obs_profile))
                if len(ref) == len(obs_profile) and np.std(ref) >= 1.0:
                    corr_matrix[i, j] = CorrelationMetrics.ncc(obs_profile, ref)

    elif gen and params:
        gen.rng = np.random.default_rng(cfg.seed)
        radar_alts = gen.generate_profile(params, noise_std=cfg.noise_std)
        if len(radar_alts) >= cfg.window_size:
            obs_profile = cfg.baro_altitude - radar_alts[:cfg.window_size]
            for i, az in enumerate(azimuths):
                for j, sp in enumerate(speeds):
                    ref = hs.build_reference_profile(center_lat, center_lon, az, sp, cfg.window_size)
                    if len(ref) == cfg.window_size and np.std(ref) >= 1.0:
                        corr_matrix[i, j] = CorrelationMetrics.ncc(obs_profile, ref)

    return corr_matrix, obs_profile, ref_profile


def _generate_visualizations(
    dem: DEMLoader,
    results: list,
    params: FlightParams,
    cfg: Config,
    gen: DataGenerator = None,
    pipeline: NavigationPipeline = None,
    out_dir: str = None,
    dem_name: str = "DEM",
):
    out = out_dir or cfg.output_path
    os.makedirs(out, exist_ok=True)

    n_sp = cfg.n_speed_hypotheses
    azimuths = np.arange(0, 360, cfg.coarse_azimuth_step)
    speeds = np.linspace(cfg.speed_range_ms[0], cfg.speed_range_ms[1], n_sp)

    traj_lats, traj_lons = _generate_trajectory(params, cfg)
    corr_matrix, obs_profile, ref_profile = _build_correlation_matrix(
        dem, cfg, pipeline, gen, params,
    )

    first_est = results[0] if results else None

    if results:
        fig_heatmap = correlation_heatmap(
            azimuths, speeds, corr_matrix,
            first_est.azimuth_deg if first_est else None,
            first_est.speed_ms if first_est else None,
        )
        save_html(fig_heatmap, os.path.join(out, "correlation_heatmap.html"))
        click.echo("  [viz] correlation_heatmap.html")

        est_positions = [(r.position_lat, r.position_lon) for r in results[:5]]

        fig_map = trajectory_map(
            dem,
            traj_lats, traj_lons,
            est_positions,
            params.start_lat, params.start_lon,
        )
        save_html(fig_map, os.path.join(out, "trajectory_map.html"))
        click.echo("  [viz] trajectory_map.html")

        fig_profile = profile_comparison(
            obs_profile, ref_profile,
            first_est.azimuth_deg if first_est else 0,
            first_est.speed_ms if first_est else 0,
            first_est.correlation if first_est else 0,
        )
        save_html(fig_profile, os.path.join(out, "profile_comparison.html"))
        click.echo("  [viz] profile_comparison.html")

    dash_data = build_dashboard_data(
        dem, results, params, cfg,
        traj_lats, traj_lons,
        corr_matrix, obs_profile, ref_profile,
        azimuths, speeds,
        dem_name=dem_name,
    )
    fig_dash = navigation_dashboard(dash_data)
    save_html(fig_dash, os.path.join(out, "dashboard.html"))
    click.echo("  [viz] dashboard.html")


def _generate_dramatic_dem(path: str, nx: int = 400, ny: int = 400):
    import xarray as xr

    np.random.seed(42)
    xs = np.linspace(0, 1, nx)
    ys = np.linspace(0, 1, ny)
    xx, yy = np.meshgrid(xs, ys)

    elev = np.zeros((ny, nx))

    peaks = [
        (0.2, 0.3, 0.08, 2500),
        (0.5, 0.2, 0.12, 2000),
        (0.7, 0.5, 0.1, 2200),
        (0.3, 0.7, 0.15, 1800),
        (0.8, 0.8, 0.09, 1500),
        (0.5, 0.6, 0.06, 3000),
    ]

    for px, py, sigma, h in peaks:
        peak = h * np.exp(-((xx - px) ** 2 + (yy - py) ** 2) / (2 * sigma ** 2))
        crater = np.exp(-((xx - px) ** 2 + (yy - py) ** 2) / (2 * (sigma * 0.3) ** 2))
        peak = peak - crater * h * 0.3
        elev += peak

    ridge_ys = [0.1, 0.25, 0.6, 0.9]
    for cy in ridge_ys:
        ridge = np.exp(-((yy - cy) ** 2) / 0.002)
        ridge *= 800 * (1 + np.sin(xx * 8 * np.pi) * 0.3)
        elev += ridge

    canyon_x = 0.85
    canyon = np.exp(-((xx - canyon_x) ** 2) / 0.005)
    canyon_height = 600 * (1 + np.sin(yy * 6 * np.pi) * 0.2)
    elev -= canyon * canyon_height

    river = np.exp(-((yy - 0.8) ** 2) / 0.008)
    river *= np.exp(-((xx - 0.3) ** 2) / 0.15)
    elev -= river * 400

    noise = np.random.randn(ny, nx) * 15
    noise = np.maximum(noise, -30)
    elev += noise

    elev = np.clip(elev, 0, 3500)
    gauss = np.exp(-((xx - 0.5) ** 2 + (yy - 0.5) ** 2) / 0.5)
    elev = elev * (0.6 + 0.4 * gauss)
    elev = np.maximum(elev, 10)

    lats = np.linspace(55.97, 56.23, ny)
    lons = np.linspace(160.53, 160.77, nx)

    ds = xr.DataArray(
        elev.astype(np.float32),
        dims=("y", "x"),
        coords={"y": lats, "x": lons},
    )
    ds.rio.write_crs("EPSG:4326", inplace=True)
    ds.rio.set_spatial_dims("x", "y", inplace=True)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    ds.rio.to_raster(path)
    return elev, lats, lons


if __name__ == "__main__":
    cli()
