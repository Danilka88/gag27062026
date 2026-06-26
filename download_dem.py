import os
import sys
from typing import Tuple
import click
import requests

S3_BASE_URL = "https://copernicus-dem-30m.s3.eu-central-1.amazonaws.com"


TILE_INDEX_URL = "https://copernicus-dem-30m.s3.eu-central-1.amazonaws.com/tileIndex.txt"


def _lat_to_tile_y(lat: float) -> str:
    hemisphere = "N" if lat >= 0 else "S"
    deg = int(abs(lat))
    return f"{hemisphere}{deg:02d}"


def _lon_to_tile_x(lon: float) -> str:
    hemisphere = "E" if lon >= 0 else "W"
    deg = int(abs(lon))
    return f"{hemisphere}{deg:03d}"


def resolve_tile_url(lat: float, lon: float) -> str:
    tile_y = _lat_to_tile_y(lat)
    tile_x = _lon_to_tile_x(lon)
    tile_name = f"Copernicus_DSM_COG_10_{tile_y}_00_{tile_x}_00_DEM"
    return f"{S3_BASE_URL}/{tile_name}/{tile_name}.tif"


def download_tile(lat: float, lon: float, output_dir: str) -> str:
    url = resolve_tile_url(lat, lon)
    os.makedirs(output_dir, exist_ok=True)
    tile_y = _lat_to_tile_y(lat)
    tile_x = _lon_to_tile_x(lon)
    local_path = os.path.join(output_dir, f"Copernicus_DSM_COG_10_{tile_y}_00_{tile_x}_00_DEM.tif")

    if os.path.exists(local_path):
        print(f"[DEM] Already cached: {local_path}")
        return local_path

    print(f"[DEM] Downloading {url}")
    print(f"[DEM]   -> {local_path}")
    resp = requests.get(url, stream=True, timeout=300)
    if resp.status_code != 200:
        raise RuntimeError(
            f"Failed to download tile at ({lat}, {lon}): HTTP {resp.status_code}. "
            f"Tile may not exist in GLO-30 Public dataset. "
            f"URL: {url}"
        )
    total = int(resp.headers.get("content-length", 0))
    downloaded = 0
    with open(local_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
            downloaded += len(chunk)
            if total and total > 10_000_000:
                pct = 100.0 * downloaded / total
                print(f"\r[DEM] Progress: {pct:.1f}%", end="", flush=True)
    if total > 10_000_000:
        print()
    print(f"[DEM] Done: {local_path} ({downloaded / 1e6:.1f} MB)")
    return local_path


def download_region(
    center_lat: float,
    center_lon: float,
    output_dir: str,
    margin_deg: float = 0.15,
) -> str:
    lat_min = center_lat - margin_deg
    lat_max = center_lat + margin_deg
    lon_min = center_lon - margin_deg
    lon_max = center_lon + margin_deg

    lat_tiles = set()
    lon_tiles = set()
    for lat in (lat_min, lat_max):
        lat_tiles.add(_lat_to_tile_y(lat))
    for lon in (lon_min, lon_max):
        lon_tiles.add(_lon_to_tile_x(lon))

    downloaded = []
    for lat_str in lat_tiles:
        for lon_str in lon_tiles:
            hemisphere_lat = lat_str[0]
            deg_lat = int(lat_str[1:])
            hemisphere_lon = lon_str[0]
            deg_lon = int(lon_str[1:])
            if hemisphere_lat == "S":
                deg_lat = -deg_lat
            if hemisphere_lon == "W":
                deg_lon = -deg_lon
            path = download_tile(float(deg_lat), float(deg_lon), output_dir)
            downloaded.append(path)

    return downloaded


def resolve_coordinates(place_name: str) -> Tuple[float, float]:
    known = {
        "kamchatka": (56.06, 160.64),
        "kluchevskoy": (56.06, 160.64),
        "carpathians": (48.5, 24.0),
        "altai": (50.0, 87.0),
        "himalayas": (28.0, 87.0),
    }
    key = place_name.lower().strip()
    if key in known:
        return known[key]

    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": place_name, "format": "json", "limit": 1}
    headers = {"User-Agent": "gagarin-tercom/0.1.0"}
    resp = requests.get(url, params=params, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if not data:
        raise ValueError(f"Place not found: {place_name}")
    return (float(data[0]["lat"]), float(data[0]["lon"]))


@click.command()
@click.argument("place", default="kamchatka")
@click.option("--output-dir", "-o", default="data/dem", help="Output directory for DEM tiles")
@click.option("--margin", "-m", default=0.15, type=float, help="Margin in degrees around center")
def main(place: str, output_dir: str, margin: float):
    try:
        lat, lon = resolve_coordinates(place)
    except ValueError:
        print(f"Unknown place: {place}. Trying as direct lat,lon...")
        parts = place.split(",")
        if len(parts) == 2:
            lat, lon = float(parts[0]), float(parts[1])
        else:
            sys.exit(1)

    print(f"[DEM] Center: {lat:.4f}, {lon:.4f}")
    print(f"[DEM] Bbox: lat±{margin}, lon±{margin}")
    files = download_region(lat, lon, output_dir, margin_deg=margin)
    print(f"[DEM] Downloaded {len(files)} tile(s)")


if __name__ == "__main__":
    main()
