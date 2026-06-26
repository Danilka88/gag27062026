from dataclasses import dataclass
from typing import Optional, List, Tuple
import math
import numpy as np

from gagarin.dem_loader import DEMLoader
from gagarin.estimator import NavigationEstimate
from gagarin.data_generator import FlightParams
from gagarin.config import Config
from gagarin.viz.utils import get_grid_or_fallback


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


@dataclass
class TerrainData:
    lons: np.ndarray
    lats: np.ndarray
    elevation: np.ndarray

    @property
    def elevation_range(self) -> Tuple[float, float]:
        return float(np.min(self.elevation)), float(np.max(self.elevation))

    @property
    def elevation_std(self) -> float:
        return float(np.std(self.elevation))

    def elevation_at(self, pts_lats: np.ndarray, pts_lons: np.ndarray) -> np.ndarray:
        lat_idx = np.searchsorted(self.lats, pts_lats) - 1
        lon_idx = np.searchsorted(self.lons, pts_lons) - 1
        lat_idx = np.clip(lat_idx, 0, len(self.lats) - 2)
        lon_idx = np.clip(lon_idx, 0, len(self.lons) - 2)

        lat_frac = (pts_lats - self.lats[lat_idx]) / (self.lats[lat_idx + 1] - self.lats[lat_idx] + 1e-12)
        lon_frac = (pts_lons - self.lons[lon_idx]) / (self.lons[lon_idx + 1] - self.lons[lon_idx] + 1e-12)

        v00 = self.elevation[lat_idx, lon_idx]
        v10 = self.elevation[lat_idx + 1, lon_idx]
        v01 = self.elevation[lat_idx, lon_idx + 1]
        v11 = self.elevation[lat_idx + 1, lon_idx + 1]

        return (
            v00 * (1 - lat_frac) * (1 - lon_frac)
            + v10 * lat_frac * (1 - lon_frac)
            + v01 * (1 - lat_frac) * lon_frac
            + v11 * lat_frac * lon_frac
        )


@dataclass
class TrajectoryData:
    lats: np.ndarray
    lons: np.ndarray
    elevations: np.ndarray


@dataclass
class EstimateData:
    idx: int
    azimuth_deg: float
    speed_ms: float
    position_lat: float
    position_lon: float
    correlation: float
    confidence: float
    filtered_lat: Optional[float] = None
    filtered_lon: Optional[float] = None
    filtered_speed_ms: Optional[float] = None
    quality: str = "unknown"


@dataclass
class CorrData:
    matrix: np.ndarray
    azimuths: np.ndarray
    speeds: np.ndarray

    def best_azimuth(self) -> float:
        idx = np.unravel_index(np.argmax(self.matrix), self.matrix.shape)
        return float(self.azimuths[idx[0]])

    def best_speed(self) -> float:
        idx = np.unravel_index(np.argmax(self.matrix), self.matrix.shape)
        return float(self.speeds[idx[1]])


@dataclass
class ProfileData:
    observed: np.ndarray
    reference: np.ndarray
    azimuth_deg: float
    speed_ms: float
    correlation: float


@dataclass
class ErrorData:
    azimuth_errors: np.ndarray
    speed_errors: np.ndarray
    position_errors_km: np.ndarray

    @property
    def mean_azimuth_error(self) -> float:
        return float(np.mean(np.abs(self.azimuth_errors))) if len(self.azimuth_errors) > 0 else 0.0

    @property
    def mean_speed_error(self) -> float:
        return float(np.mean(np.abs(self.speed_errors))) if len(self.speed_errors) > 0 else 0.0

    @property
    def mean_position_error_km(self) -> float:
        return float(np.mean(self.position_errors_km)) if len(self.position_errors_km) > 0 else 0.0

    @property
    def final_drift_km(self) -> float:
        return float(self.position_errors_km[-1]) if len(self.position_errors_km) > 0 else 0.0


@dataclass
class DashboardData:
    dem_name: str
    terrain: TerrainData
    trajectory: TrajectoryData
    estimates: List[EstimateData]
    correlation: CorrData
    profile: ProfileData
    errors: ErrorData
    true_azimuth: float
    true_speed: float


def build_dashboard_data(
    dem: DEMLoader,
    results: List[NavigationEstimate],
    params: FlightParams,
    cfg: Config,
    traj_lats: np.ndarray,
    traj_lons: np.ndarray,
    corr_matrix: np.ndarray,
    obs_profile: np.ndarray,
    ref_profile: np.ndarray,
    azimuths: np.ndarray,
    speeds: np.ndarray,
    dem_name: str = "DEM",
) -> DashboardData:
    lons, lats, elevation = get_grid_or_fallback(dem)
    terrain = TerrainData(lons=np.asarray(lons), lats=np.asarray(lats), elevation=elevation)

    traj_elev = dem.elevation_batch(np.asarray(traj_lats), np.asarray(traj_lons))
    trajectory = TrajectoryData(
        lats=np.asarray(traj_lats), lons=np.asarray(traj_lons), elevations=traj_elev,
    )

    estimates_data = []
    for i, r in enumerate(results):
        q = r.quality.get("quality", "unknown") if r.quality else "unknown"
        estimates_data.append(EstimateData(
            idx=i,
            azimuth_deg=r.azimuth_deg,
            speed_ms=r.speed_ms,
            position_lat=r.position_lat,
            position_lon=r.position_lon,
            correlation=r.correlation,
            confidence=r.confidence,
            filtered_lat=r.filtered_lat,
            filtered_lon=r.filtered_lon,
            filtered_speed_ms=r.filtered_speed_ms,
            quality=q,
        ))

    corr = CorrData(matrix=corr_matrix, azimuths=azimuths, speeds=speeds)

    first = results[0] if results else None
    profile = ProfileData(
        observed=obs_profile, reference=ref_profile,
        azimuth_deg=first.azimuth_deg if first else 0,
        speed_ms=first.speed_ms if first else 0,
        correlation=first.correlation if first else 0,
    )

    az_err = np.array([e.azimuth_deg - params.azimuth_deg for e in results]) if results else np.array([])
    sp_err = np.array([e.speed_ms - params.speed_ms for e in results]) if results else np.array([])

    pos_err = np.array([
        haversine_km(
            e.position_lat, e.position_lon,
            traj_lats[min(int((i + 1) * len(traj_lats) / max(len(results), 1)), len(traj_lats) - 1)],
            traj_lons[min(int((i + 1) * len(traj_lons) / max(len(results), 1)), len(traj_lons) - 1)],
        )
        for i, e in enumerate(results)
    ]) if results else np.array([])

    errors = ErrorData(azimuth_errors=az_err, speed_errors=sp_err, position_errors_km=pos_err)

    return DashboardData(
        dem_name=dem_name,
        terrain=terrain,
        trajectory=trajectory,
        estimates=estimates_data,
        correlation=corr,
        profile=profile,
        errors=errors,
        true_azimuth=params.azimuth_deg,
        true_speed=params.speed_ms,
    )
