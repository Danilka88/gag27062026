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


def _generate_dem(
    path: str,
    nx: int = 400,
    ny: int = 400,
    lat_range: tuple[float, float] = (55.97, 56.23),
    lon_range: tuple[float, float] = (160.53, 160.77),
    seed: int = 42,
    peaks: Optional[list] = None,
    ridges: Optional[list] = None,
    ridge_intensity: float = 0.0,
    canyon: Optional[tuple] = None,
    river_valley: Optional[tuple] = None,
    noise_std: float = 15.0,
    base_amplitude: float = 0.0,
    base_frequencies: Optional[list] = None,
    elev_min: float = 0.0,
    elev_max: float = 3500.0,
    dome_strength: float = 0.4,
    island_mask: bool = False,
):
    import xarray as xr

    np.random.seed(seed)
    xs = np.linspace(0, 1, nx)
    ys = np.linspace(0, 1, ny)
    xx, yy = np.meshgrid(xs, ys)

    elev = np.zeros((ny, nx))

    if base_amplitude > 0 and base_frequencies:
        for freq, amp in base_frequencies:
            elev += amp * (np.sin(freq * np.pi * xx) * np.cos(freq * np.pi * yy) + 1) / 2
        elev *= base_amplitude / (np.max(elev) if np.max(elev) > 0 else 1)

    if peaks:
        for px, py, sigma, h in peaks:
            peak = h * np.exp(-((xx - px) ** 2 + (yy - py) ** 2) / (2 * sigma ** 2))
            crater = np.exp(-((xx - px) ** 2 + (yy - py) ** 2) / (2 * (sigma * 0.3) ** 2))
            peak = peak - crater * h * 0.3
            elev += peak

    if ridges:
        for cy in ridges:
            ridge = np.exp(-((yy - cy) ** 2) / 0.002)
            ridge *= ridge_intensity * (1 + np.sin(xx * 8 * np.pi) * 0.3)
            elev += ridge

    if canyon:
        cx, c_width, c_depth = canyon
        c = np.exp(-((xx - cx) ** 2) / c_width)
        c_height = c_depth * (1 + np.sin(yy * 6 * np.pi) * 0.2)
        elev -= c * c_height

    if river_valley:
        rx, ry, wx, wy, depth = river_valley
        r = np.exp(-((yy - ry) ** 2) / wy)
        r *= np.exp(-((xx - rx) ** 2) / wx)
        elev -= r * depth

    if noise_std > 0:
        noise = np.random.randn(ny, nx) * noise_std
        noise = np.maximum(noise, -2 * noise_std)
        elev += noise

    if island_mask:
        cx_iso, cy_iso, rx_iso, ry_iso = 0.5, 0.5, 0.38, 0.3
        island = ((xx - cx_iso) / rx_iso) ** 2 + ((yy - cy_iso) / ry_iso) ** 2 <= 1
        elev = elev * island
        edge = np.maximum(0, 1 - (((xx - cx_iso) / rx_iso) ** 2 + ((yy - cy_iso) / ry_iso) ** 2 - 0.85) / 0.15)
        elev *= edge

    elev = np.clip(elev, elev_min, elev_max)

    if dome_strength > 0:
        gauss = np.exp(-((xx - 0.5) ** 2 + (yy - 0.5) ** 2) / 0.5)
        elev = elev * ((1 - dome_strength) + dome_strength * gauss)

    elev = np.maximum(elev, 1)

    lats = np.linspace(lat_range[0], lat_range[1], ny)
    lons = np.linspace(lon_range[0], lon_range[1], nx)

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


def _generate_dramatic_dem(path: str, nx: int = 400, ny: int = 400):
    return _generate_dem(
        path, nx=nx, ny=ny,
        peaks=[
            (0.2, 0.3, 0.08, 2500),
            (0.5, 0.2, 0.12, 2000),
            (0.7, 0.5, 0.1, 2200),
            (0.3, 0.7, 0.15, 1800),
            (0.8, 0.8, 0.09, 1500),
            (0.5, 0.6, 0.06, 3000),
        ],
        ridges=[0.1, 0.25, 0.6, 0.9],
        ridge_intensity=800,
        canyon=(0.85, 0.005, 600),
        river_valley=(0.3, 0.8, 0.15, 0.008, 400),
        noise_std=15,
        elev_max=3500,
        dome_strength=0.4,
    )


DEM_CONFIGS = [
    {
        "id": "synthetic_kamchatka",
        "name": "Камчатка — плавный рельеф",
        "description": "Плавный рельеф, σ=95 м — идеален для отладки TERCOM",
        "dem_name": "Synthetic Kamchatka",
        "lat_range": (55.97, 56.23),
        "lon_range": (160.53, 160.77),
        "noise_std": 3.0,
        "base_amplitude": 600,
        "base_frequencies": [(2, 1.0), (3, 0.5), (5, 0.25)],
        "elev_min": 80,
        "elev_max": 650,
        "dome_strength": 0.3,
        "baro_altitude": 1500.0,
    },
    {
        "id": "dramatic_kamchatka",
        "name": "Камчатка — вулканы и каньоны",
        "description": "6 вулканов + гребни + каньоны, σ=687 м — сложный рельеф",
        "dem_name": "Dramatic Kamchatka",
        "lat_range": (55.97, 56.23),
        "lon_range": (160.53, 160.77),
        "peaks": [
            (0.2, 0.3, 0.08, 2500),
            (0.5, 0.2, 0.12, 2000),
            (0.7, 0.5, 0.1, 2200),
            (0.3, 0.7, 0.15, 1800),
            (0.8, 0.8, 0.09, 1500),
            (0.5, 0.6, 0.06, 3000),
        ],
        "ridges": [0.1, 0.25, 0.6, 0.9],
        "ridge_intensity": 800,
        "canyon": (0.85, 0.005, 600),
        "river_valley": (0.3, 0.8, 0.15, 0.008, 400),
        "noise_std": 15,
        "elev_max": 3500,
        "dome_strength": 0.4,
        "baro_altitude": 3500.0,
    },
    {
        "id": "caucasus",
        "name": "Кавказ — высокогорье",
        "description": "Острые пики до 5000 м, глубокие ущелья — экстремальный рельеф",
        "dem_name": "Caucasus",
        "lat_range": (43.20, 43.46),
        "lon_range": (42.30, 42.54),
        "peaks": [
            (0.3, 0.4, 0.06, 4800),
            (0.5, 0.3, 0.08, 4200),
            (0.4, 0.6, 0.05, 3800),
            (0.7, 0.4, 0.07, 3500),
            (0.2, 0.7, 0.09, 3000),
            (0.6, 0.7, 0.06, 3200),
            (0.8, 0.5, 0.05, 4000),
            (0.3, 0.2, 0.07, 2800),
        ],
        "ridges": [0.2, 0.5, 0.8],
        "ridge_intensity": 500,
        "canyon": (0.6, 0.003, 800),
        "river_valley": (0.7, 0.5, 0.1, 0.006, 500),
        "noise_std": 25,
        "elev_max": 5200,
        "dome_strength": 0.3,
        "baro_altitude": 5500.0,
    },
    {
        "id": "ural",
        "name": "Урал — горный хребет",
        "description": "Пологий хребет 1000–1500 м — умеренный рельеф для тестов",
        "dem_name": "Ural",
        "lat_range": (55.00, 55.26),
        "lon_range": (59.50, 59.74),
        "peaks": [
            (0.5, 0.3, 0.12, 1400),
            (0.5, 0.5, 0.15, 1200),
            (0.5, 0.7, 0.10, 1300),
        ],
        "ridges": [0.3, 0.5, 0.7],
        "ridge_intensity": 350,
        "noise_std": 5,
        "elev_min": 100,
        "elev_max": 1600,
        "dome_strength": 0.2,
        "baro_altitude": 2000.0,
    },
    {
        "id": "altai",
        "name": "Алтай — плато и пики",
        "description": "Высокое плато 2000 м с пиками до 3500 м — контрастный рельеф",
        "dem_name": "Altai",
        "lat_range": (50.00, 50.26),
        "lon_range": (87.50, 87.74),
        "peaks": [
            (0.3, 0.3, 0.08, 3500),
            (0.6, 0.4, 0.10, 3000),
            (0.4, 0.6, 0.07, 2800),
            (0.7, 0.7, 0.09, 2500),
        ],
        "base_amplitude": 1800,
        "base_frequencies": [(1, 1.0), (2, 0.5)],
        "ridges": [0.2, 0.6],
        "ridge_intensity": 300,
        "river_valley": (0.5, 0.3, 0.12, 0.01, 400),
        "noise_std": 10,
        "elev_max": 3800,
        "dome_strength": 0.3,
        "baro_altitude": 4000.0,
    },
    {
        "id": "crimea",
        "name": "Крым — горы и море",
        "description": "Прибрежный гребень 1000 м, переход к уровню моря",
        "dem_name": "Crimea",
        "lat_range": (44.40, 44.66),
        "lon_range": (33.80, 34.04),
        "peaks": [
            (0.3, 0.3, 0.10, 1000),
            (0.5, 0.25, 0.12, 900),
            (0.7, 0.35, 0.08, 1100),
        ],
        "ridges": [0.3, 0.5],
        "ridge_intensity": 250,
        "noise_std": 4,
        "elev_min": 0,
        "elev_max": 1200,
        "dome_strength": 0.1,
        "baro_altitude": 1500.0,
    },
    {
        "id": "siberia",
        "name": "Западная Сибирь — равнина",
        "description": "Плоский рельеф 50–150 м с меандрирующей рекой",
        "dem_name": "Siberian Plain",
        "lat_range": (57.50, 57.76),
        "lon_range": (72.00, 72.24),
        "base_amplitude": 80,
        "base_frequencies": [(1, 1.0), (3, 0.3)],
        "river_valley": (0.4, 0.5, 0.12, 0.015, 50),
        "noise_std": 1.5,
        "elev_min": 30,
        "elev_max": 200,
        "dome_strength": 0.0,
        "baro_altitude": 300.0,
    },
    {
        "id": "sakhalin",
        "name": "Сахалин — островные сопки",
        "description": "Узкий остров с сопками 500–800 м и выходом к морю по краям",
        "dem_name": "Sakhalin",
        "lat_range": (47.00, 47.26),
        "lon_range": (142.50, 142.74),
        "peaks": [
            (0.5, 0.3, 0.10, 700),
            (0.5, 0.5, 0.12, 800),
            (0.5, 0.7, 0.08, 600),
        ],
        "ridges": [0.3, 0.5, 0.7],
        "ridge_intensity": 200,
        "noise_std": 4,
        "elev_min": 0,
        "elev_max": 900,
        "dome_strength": 0.15,
        "island_mask": True,
        "baro_altitude": 1200.0,
    },
    {
        "id": "karelia",
        "name": "Карелия — холмы и озёра",
        "description": "Мягкие холмы 100–300 м с озёрными впадинами",
        "dem_name": "Karelia",
        "lat_range": (62.00, 62.26),
        "lon_range": (33.00, 33.24),
        "base_amplitude": 200,
        "base_frequencies": [(2, 1.0), (3, 0.6), (4, 0.3)],
        "peaks": [
            (0.2, 0.3, 0.15, 300),
            (0.7, 0.6, 0.12, 250),
            (0.4, 0.7, 0.18, 280),
        ],
        "river_valley": (0.5, 0.5, 0.2, 0.02, 120),
        "noise_std": 3,
        "elev_min": 30,
        "elev_max": 400,
        "dome_strength": 0.1,
        "baro_altitude": 500.0,
    },
    {
        "id": "primorye",
        "name": "Приморье — сопки и побережье",
        "description": "Холмистый рельеф 300–800 м, плавные склоны к морю",
        "dem_name": "Primorye",
        "lat_range": (43.00, 43.26),
        "lon_range": (131.50, 131.74),
        "peaks": [
            (0.3, 0.4, 0.10, 700),
            (0.5, 0.3, 0.12, 800),
            (0.7, 0.5, 0.08, 600),
            (0.4, 0.7, 0.15, 500),
        ],
        "ridges": [0.2, 0.5, 0.8],
        "ridge_intensity": 150,
        "river_valley": (0.6, 0.3, 0.1, 0.008, 200),
        "noise_std": 5,
        "elev_min": 0,
        "elev_max": 900,
        "dome_strength": 0.2,
        "baro_altitude": 1200.0,
    },
]


@cli.command()
def generate_all():
    for cfg in DEM_CONFIGS:
        dem_id = cfg["id"]
        path = f"data/dem/{dem_id}.tif"
        click.echo(f"Generating {dem_id}... ", nl=False)
        kw = {k: v for k, v in cfg.items()
              if k not in ("id", "name", "description", "dem_name", "baro_altitude")}
        _generate_dem(path, **kw)
        click.echo("done")


if __name__ == "__main__":
    cli()
