from typing import Optional
import numpy as np

from gagarin.constants import EARTH_RADIUS


def _kalman_gain(P: np.ndarray, H: np.ndarray, R: np.ndarray) -> np.ndarray:
    S = H @ P @ H.T + R
    return np.linalg.solve(S, H @ P).T


class ErrorStateKalmanFilter:
    def __init__(
        self,
        init_lat: float = 0.0,
        init_lon: float = 0.0,
        dt: float = 0.1,
    ):
        self.dt = dt

        self.lat = init_lat
        self.lon = init_lon
        self.vx = 0.0
        self.vy = 0.0

        self.dim = 6
        self.dx = np.zeros(self.dim)
        self.P = np.eye(self.dim) * 10.0

        self.Q = np.eye(self.dim)
        self.Q[0:2, 0:2] *= 0.1
        self.Q[2:4, 2:4] *= 1.0
        self.Q[4:6, 4:6] *= 0.01

        self.R_pos = np.eye(2) * 5.0
        self.R_vel = np.eye(2) * 2.0

    def predict(self):
        dt = self.dt
        F = np.eye(self.dim)
        F[0, 2] = dt
        F[1, 3] = dt
        F[2, 4] = dt
        F[3, 5] = dt

        self.dx = F @ self.dx
        self.P = F @ self.P @ F.T + self.Q

    def _update(self, z: np.ndarray, H: np.ndarray, R: np.ndarray):
        K = _kalman_gain(self.P, H, R)
        self.dx = self.dx + K @ z
        self.P = (np.eye(self.dim) - K @ H) @ self.P

    def update_position(self, lat: float, lon: float, R: Optional[np.ndarray] = None):
        cos_lat = np.cos(np.radians(self.lat))
        pred_lat = self.lat + np.degrees(self.dx[0] / EARTH_RADIUS)
        pred_lon = self.lon + np.degrees(self.dx[1] / (EARTH_RADIUS * cos_lat))

        z = np.array([lat - pred_lat, lon - pred_lon])

        H = np.zeros((2, self.dim))
        H[0, 0] = 1.0 / EARTH_RADIUS
        H[1, 1] = 1.0 / (EARTH_RADIUS * cos_lat)

        self._update(z, H, R if R is not None else self.R_pos)

    def update_velocity(self, vx: float, vy: float, R: Optional[np.ndarray] = None):
        pred_vx = self.vx + self.dx[2]
        pred_vy = self.vy + self.dx[3]
        z = np.array([vx - pred_vx, vy - pred_vy])

        H = np.zeros((2, self.dim))
        H[0, 2] = 1.0
        H[1, 3] = 1.0

        self._update(z, H, R if R is not None else self.R_vel)

    def reset(self):
        cos_lat = np.cos(np.radians(self.lat))
        self.lat += np.degrees(self.dx[0] / EARTH_RADIUS)
        self.lon += np.degrees(self.dx[1] / (EARTH_RADIUS * cos_lat))
        self.vx += self.dx[2]
        self.vy += self.dx[3]
        self.dx.fill(0.0)

    def get_state(self) -> dict:
        return {
            "lat": self.lat,
            "lon": self.lon,
            "vx": self.vx,
            "vy": self.vy,
            "speed_ms": np.sqrt(self.vx ** 2 + self.vy ** 2),
        }

    def set_position(self, lat: float, lon: float):
        self.lat = lat
        self.lon = lon
