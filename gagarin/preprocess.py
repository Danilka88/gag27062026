import json
import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import xarray as xr

from gagarin.dem_loader import DEMLoader
from gagarin.config import Config
from gagarin.geo_utils import offset_coords, EARTH_RADIUS
from gagarin.correlator import CorrelationMetrics, HypothesisSearch


MIN_CORRIDOR_WIDTH_M = 500.0
FINGERPRINT_OFFSETS_CELLS = [1, 2, 3, 5, 10, 15]
FINGERPRINT_PROFILE_N = 200
N_CROSS_PROFILES = 3


@dataclass
class Waypoint:
    lat: float
    lon: float


@dataclass
class Fingerprint:
    waypoint_index: int
    lat: float
    lon: float
    std_elevation: float
    gradient_magnitude: float
    roughness_std: float
    expected_ncc_self: float
    expected_ncc_offsets: list
    offset_distances_m: list
    minima_ratio: float
    roughness_difference: float
    profile_correlation_with_worst: float


@dataclass
class MissionPackage:
    path: str
    n_waypoints: int
    n_fingerprints: int
    corridor_width_m: float
    dem_name: str
    info_map_path: str


def _latlon_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return EARTH_RADIUS * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _lateral_offset(lat: float, lon: float, distance_m: float, azimuth_rad: float) -> Tuple[float, float]:
    lateral_az = azimuth_rad + math.pi / 2
    return offset_coords(lat, lon, distance_m, lateral_az)


def _adaptive_corridor_width(
    segment_length_m: float,
    ins_drift_rate: float = 0.1,
    dem_resolution_m: float = 30.0,
) -> float:
    return max(2 * ins_drift_rate * segment_length_m + 2 * dem_resolution_m, MIN_CORRIDOR_WIDTH_M)


def _interpolate_route(waypoints: List[Waypoint], step_m: float = 100.0) -> Tuple[List[Waypoint], List[float]]:
    if len(waypoints) < 2:
        return waypoints, [0.0]
    interpolated = [waypoints[0]]
    distances = [0.0]
    total = 0.0
    for i in range(len(waypoints) - 1):
        a, b = waypoints[i], waypoints[i + 1]
        seg_dist = _latlon_distance_m(a.lat, a.lon, b.lat, b.lon)
        n_steps = max(1, int(seg_dist / step_m))
        for j in range(1, n_steps + 1):
            frac = j / n_steps
            lat = a.lat + (b.lat - a.lat) * frac
            lon = a.lon + (b.lon - a.lon) * frac
            interpolated.append(Waypoint(lat=lat, lon=lon))
            total += seg_dist / n_steps
            distances.append(total)
    return interpolated, distances


class TerrainAnalyzer:
    def __init__(self, dem: DEMLoader):
        self.dem = dem
        self._data = dem.get_elevation_grid()[2].astype(np.float64)

    def gradient_magnitude(self) -> np.ndarray:
        gy, gx = np.gradient(self._data)
        return np.sqrt(gx ** 2 + gy ** 2)

    def std_window(self, window: int = 5) -> np.ndarray:
        from scipy.ndimage import uniform_filter
        mean = uniform_filter(self._data, size=window)
        mean_sq = uniform_filter(self._data ** 2, size=window)
        var = np.maximum(mean_sq - mean ** 2, 0)
        return np.sqrt(var)

    def laplacian(self) -> np.ndarray:
        from scipy.ndimage import laplace
        return laplace(self._data)

    def info_map(self) -> np.ndarray:
        g = self.gradient_magnitude()
        s = self.std_window(7)
        combined = (g / (np.max(g) + 1e-12)) + (s / (np.max(s) + 1e-12))
        return combined / 2.0

    def elevation_at(self, lat: float, lon: float) -> float:
        return self.dem.elevation(lat, lon)

    def elevation_batch(self, lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
        return self.dem.elevation_batch(lats, lons)


class MissionPreprocessor:
    def __init__(self, dem: DEMLoader, config: Optional[Config] = None):
        self.dem = dem
        self.cfg = config or Config.default()
        self._hs = HypothesisSearch(dem, self.cfg)
        self._analyzer = TerrainAnalyzer(dem)

    def compute_route_fingerprints(
        self,
        waypoints: List[Waypoint],
        azimuth_deg: float,
        speed_ms: float,
        ins_drift_rate: float = 0.1,
    ) -> Tuple[List[Fingerprint], float]:
        if len(waypoints) < 2:
            raise ValueError("Need at least 2 waypoints")

        max_seg = max(
            _latlon_distance_m(waypoints[i].lat, waypoints[i].lon,
                               waypoints[i + 1].lat, waypoints[i + 1].lon)
            for i in range(len(waypoints) - 1)
        )
        corridor_w = _adaptive_corridor_width(max_seg, ins_drift_rate,
                                              max(self.dem.resolution))

        interpolated, _ = _interpolate_route(waypoints, step_m=200.0)

        azimuth_rad = math.radians(azimuth_deg)
        n = FINGERPRINT_PROFILE_N
        dem_res = max(self.dem.resolution)
        max_offset_cells = max(FINGERPRINT_OFFSETS_CELLS)
        max_offset_m = max_offset_cells * dem_res
        max_offset_m = min(max_offset_m, corridor_w / 2)

        fingerprints = []
        for idx, wp in enumerate(interpolated):
            lat, lon = wp.lat, wp.lon

            if not self._in_dem_bounds(lat, lon):
                continue

            ref_self = self._hs.build_reference_profile(lat, lon, azimuth_deg, speed_ms, n)
            if np.std(ref_self) < 1.0:
                continue

            offsets = []
            ncc_offsets = []
            for cell in FINGERPRINT_OFFSETS_CELLS:
                offset_m = cell * dem_res
                if offset_m > max_offset_m:
                    break
                lat_off, lon_off = _lateral_offset(lat, lon, offset_m, azimuth_rad)
                lat_off_neg, lon_off_neg = _lateral_offset(lat, lon, -offset_m, azimuth_rad)
                offsets.append(offset_m)
                offsets.append(-offset_m)

                if self._in_dem_bounds(lat_off, lon_off):
                    ref_off = self._hs.build_reference_profile(lat_off, lon_off, azimuth_deg, speed_ms, n)
                    ncc_off = CorrelationMetrics.ncc(ref_self, ref_off) if np.std(ref_off) >= 1.0 else -1.0
                else:
                    ncc_off = -1.0
                ncc_offsets.append(ncc_off)

                if self._in_dem_bounds(lat_off_neg, lon_off_neg):
                    ref_off_neg = self._hs.build_reference_profile(lat_off_neg, lon_off_neg, azimuth_deg, speed_ms, n)
                    ncc_off_neg = CorrelationMetrics.ncc(ref_self, ref_off_neg) if np.std(ref_off_neg) >= 1.0 else -1.0
                else:
                    ncc_off_neg = -1.0
                ncc_offsets.append(ncc_off_neg)

            if not ncc_offsets:
                continue

            ncc_self = 1.0
            valid = [v for v in ncc_offsets if v >= -1.0]
            valid.sort(reverse=True)
            minima_ratio = valid[0] / valid[1] if len(valid) > 1 and valid[1] > -0.99 else 1.0

            worst_ncc = min(ncc_offsets) if ncc_offsets else -1.0
            roughness_diff = abs(np.std(ref_self) - (
                np.std(self._hs.build_reference_profile(
                    _lateral_offset(lat, lon, max_offset_m, azimuth_rad)[0],
                    _lateral_offset(lat, lon, max_offset_m, azimuth_rad)[1],
                    azimuth_deg, speed_ms, n
                )) if self._in_dem_bounds(*_lateral_offset(lat, lon, max_offset_m, azimuth_rad)) else 0.0
            ))

            std_elev = float(np.std(ref_self))
            grad_mag = float(self._analyzer.gradient_magnitude()[
                max(0, min(int(self.dem.resolution[1] * (lat - self.dem.bounds[1])), self._analyzer.gradient_magnitude().shape[0] - 1)),
                max(0, min(int(self.dem.resolution[0] * (lon - self.dem.bounds[0])), self._analyzer.gradient_magnitude().shape[1] - 1))
            ]) if self._in_dem_bounds(lat, lon) else 0.0

            fp = Fingerprint(
                waypoint_index=idx,
                lat=lat, lon=lon,
                std_elevation=std_elev,
                gradient_magnitude=grad_mag,
                roughness_std=float(np.std(ref_self)),
                expected_ncc_self=ncc_self,
                expected_ncc_offsets=ncc_offsets,
                offset_distances_m=offsets,
                minima_ratio=minima_ratio,
                roughness_difference=roughness_diff,
                profile_correlation_with_worst=worst_ncc if worst_ncc != -1.0 else 0.0,
            )
            fingerprints.append(fp)

        return fingerprints, corridor_w

    def build_mission_package(
        self,
        fingerprints: List[Fingerprint],
        waypoints: List[Waypoint],
        azimuth_deg: float,
        speed_ms: float,
        corridor_width_m: float,
        output_dir: str = "mission_package",
        dem_name: str = "source",
    ) -> MissionPackage:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        dem_dir = out / "dem"
        dem_dir.mkdir(exist_ok=True)

        info_map = self._analyzer.info_map()
        info_map_path = str(dem_dir / "info_map.tif")
        self._save_geotiff(info_map, info_map_path)

        db_path = out / "fingerprints.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA journal_mode=WAL")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS waypoints (
                id INTEGER PRIMARY KEY,
                lat REAL NOT NULL,
                lon REAL NOT NULL,
                distance_along_track REAL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS features (
                waypoint_id INTEGER PRIMARY KEY,
                std_elevation REAL,
                gradient_magnitude REAL,
                roughness_std REAL,
                expected_ncc_self REAL,
                expected_ncc_offsets TEXT,
                offset_distances_m TEXT,
                minima_ratio REAL,
                roughness_difference REAL,
                profile_correlation_with_worst REAL,
                FOREIGN KEY (waypoint_id) REFERENCES waypoints(id)
            )
        """)
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS waypoints_rtree
            USING rtree(id, min_lat, max_lat, min_lon, max_lon)
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS mission_config (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        config_data = dict(
            n_fingerprints=str(len(fingerprints)),
            n_waypoints=str(len(waypoints)),
            azimuth_deg=str(azimuth_deg),
            speed_ms=str(speed_ms),
            corridor_width_m=str(corridor_width_m),
            dem_resolution_x=str(self.dem.resolution[0]),
            dem_resolution_y=str(self.dem.resolution[1]),
            dem_bounds=str(self.dem.bounds),
            dem_name=dem_name,
        )
        conn.executemany(
            "INSERT OR REPLACE INTO mission_config (key, value) VALUES (?, ?)",
            list(config_data.items()),
        )

        dist = 0.0
        for i, wp in enumerate(waypoints):
            if i > 0:
                dist += _latlon_distance_m(waypoints[i - 1].lat, waypoints[i - 1].lon,
                                           wp.lat, wp.lon)
            conn.execute(
                "INSERT OR REPLACE INTO waypoints (id, lat, lon, distance_along_track) VALUES (?, ?, ?, ?)",
                (i, wp.lat, wp.lon, dist),
            )
            conn.execute(
                "INSERT OR REPLACE INTO waypoints_rtree (id, min_lat, max_lat, min_lon, max_lon) VALUES (?, ?, ?, ?, ?)",
                (i, wp.lat, wp.lat, wp.lon, wp.lon),
            )

        for fp in fingerprints:
            offsets_json = json.dumps(fp.expected_ncc_offsets)
            dists_json = json.dumps(fp.offset_distances_m)
            conn.execute(
                """INSERT OR REPLACE INTO features
                   (waypoint_id, std_elevation, gradient_magnitude, roughness_std,
                    expected_ncc_self, expected_ncc_offsets, offset_distances_m,
                    minima_ratio, roughness_difference, profile_correlation_with_worst)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (fp.waypoint_index, fp.std_elevation, fp.gradient_magnitude,
                 fp.roughness_std, fp.expected_ncc_self, offsets_json, dists_json,
                 fp.minima_ratio, fp.roughness_difference, fp.profile_correlation_with_worst),
            )

        conn.commit()
        conn.close()

        metadata = dict(
            n_waypoints=len(waypoints),
            n_fingerprints=len(fingerprints),
            corridor_width_m=corridor_width_m,
            azimuth_deg=azimuth_deg,
            speed_ms=speed_ms,
            dem_name=dem_name,
        )
        with open(out / "metadata.json", "w") as f:
            json.dump(metadata, f, indent=2)

        return MissionPackage(
            path=str(out),
            n_waypoints=len(waypoints),
            n_fingerprints=len(fingerprints),
            corridor_width_m=corridor_width_m,
            dem_name=dem_name,
            info_map_path=info_map_path,
        )

    def _in_dem_bounds(self, lat: float, lon: float) -> bool:
        b = self.dem.bounds
        return b[1] <= lat <= b[3] and b[0] <= lon <= b[2]

    def _save_geotiff(self, data: np.ndarray, path: str):
        b = self.dem.bounds
        lats = np.linspace(b[1], b[3], data.shape[0])
        lons = np.linspace(b[0], b[2], data.shape[1])
        ds = xr.DataArray(
            data.astype(np.float32),
            dims=("y", "x"),
            coords={"y": lats, "x": lons},
        )
        ds.rio.write_crs("EPSG:4326", inplace=True)
        ds.rio.set_spatial_dims("x", "y", inplace=True)
        ds.rio.to_raster(path)


def load_mission_package(path: str) -> dict:
    p = Path(path)
    meta_path = p / "metadata.json"
    if meta_path.exists():
        with open(meta_path) as f:
            meta = json.load(f)
    else:
        meta = {}

    db_path = p / "fingerprints.db"
    if not db_path.exists():
        return {**meta, "waypoints": [], "features": [], "db_path": None}

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    waypoints = [dict(r) for r in conn.execute("SELECT * FROM waypoints ORDER BY id")]
    features = [dict(r) for r in conn.execute("SELECT * FROM features ORDER BY waypoint_id")]
    config_rows = dict(conn.execute("SELECT key, value FROM mission_config"))

    conn.close()

    for f in features:
        if isinstance(f.get("expected_ncc_offsets"), str):
            f["expected_ncc_offsets"] = json.loads(f["expected_ncc_offsets"])
        if isinstance(f.get("offset_distances_m"), str):
            f["offset_distances_m"] = json.loads(f["offset_distances_m"])

    return {
        **meta,
        "waypoints": waypoints,
        "features": features,
        "config": config_rows,
        "db_path": str(db_path),
    }
