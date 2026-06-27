import os
import sys
import json
from typing import Optional
import numpy as np
import click

from gagarin.dem_loader import DEMLoader
from gagarin.pipeline import NavigationPipeline
from gagarin.preprocess import MissionPreprocessor, Waypoint
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
@click.option("--waypoints", "-w", required=True, help="CSV file with lat,lon waypoints")
@click.option("--dem", "-d", default=None, help="Path to DEM file")
@click.option("--azimuth", "-az", type=float, default=45.0, help="Expected true azimuth (°)")
@click.option("--speed", "-sp", type=float, default=60.0, help="Expected true speed (m/s)")
@click.option("--ins-drift", type=float, default=0.1, help="INS drift rate (fraction of distance)")
@click.option("--output", "-o", default="mission_package", help="Output directory")
def prepare_route(waypoints: str, dem: str, azimuth: float, speed: float, ins_drift: float, output: str):
    cfg = Config.default()
    if not dem:
        dem = _find_dem(cfg.dem_path)
    if not dem:
        click.echo("No DEM found. Use --dem or run download-dem first.", err=True)
        sys.exit(1)

    click.echo(f"Loading DEM: {dem}")
    dem_loader = DEMLoader(dem)
    click.echo(f"DEM bounds: {dem_loader.bounds}")

    wps = []
    with open(waypoints) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("lat"):
                continue
            parts = line.split(",")
            wps.append(Waypoint(lat=float(parts[0]), lon=float(parts[1])))

    click.echo(f"Loaded {len(wps)} waypoints")

    preprocessor = MissionPreprocessor(dem_loader, cfg)
    click.echo("Computing terrain fingerprints along route...")
    fingerprints, corridor_w = preprocessor.compute_route_fingerprints(
        wps, azimuth, speed, ins_drift_rate=ins_drift,
    )
    click.echo(f"Computed {len(fingerprints)} fingerprints, corridor width: {corridor_w:.0f}m")

    pkg = preprocessor.build_mission_package(
        fingerprints, wps, azimuth, speed, corridor_w, output_dir=output,
    )
    click.echo(f"\nMission package saved to {pkg.path}/")
    click.echo(f"  Waypoints: {pkg.n_waypoints}")
    click.echo(f"  Fingerprints: {pkg.n_fingerprints}")
    click.echo(f"  Info map: {pkg.info_map_path}")
    click.echo(f"  DB: {pkg.path}/fingerprints.db")


@cli.command()
@click.argument("mission_dir", default="mission_package", required=False)
@click.option("--output", "-o", default=None, help="Output HTML path (default: data/output/mission_viewer.html)")
@click.option("--dashboard", "-d", default=None, help="Path to dashboard.html for nav link")
def viz_mission(mission_dir: str, output: Optional[str], dashboard: Optional[str]):
    from gagarin.viz import mission_viewer as render_mission
    cfg = Config.default()
    if output is None:
        output = os.path.join(cfg.output_path, "mission_viewer.html")
    if dashboard is None:
        dash_candidate = os.path.join(cfg.output_path, "dashboard.html")
        dashboard = dash_candidate if os.path.exists(dash_candidate) else None
    click.echo(f"Loading mission package from {mission_dir}...")
    out_path = render_mission(mission_dir, output, dashboard_path=dashboard)
    click.echo(f"Mission viewer: {out_path}")


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
