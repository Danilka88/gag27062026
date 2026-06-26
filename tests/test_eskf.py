import numpy as np
from gagarin.eskf import ErrorStateKalmanFilter


def test_initial_state():
    kf = ErrorStateKalmanFilter(init_lat=56.0, init_lon=160.5, dt=0.1)
    state = kf.get_state()
    assert abs(state["lat"] - 56.0) < 1e-10
    assert abs(state["lon"] - 160.5) < 1e-10
    assert state["speed_ms"] == 0.0


def test_predict_updates_covariance():
    kf = ErrorStateKalmanFilter(dt=0.1)
    P_before = kf.P.copy()
    kf.predict()
    assert not np.array_equal(kf.P, P_before)


def test_update_position_no_degree_double_conversion():
    kf = ErrorStateKalmanFilter(init_lat=56.0, init_lon=160.5, dt=0.1)
    kf.predict()
    kf.update_position(56.001, 160.501)
    kf.reset()
    state = kf.get_state()
    assert abs(state["lat"] - 56.001) < 0.002
    assert abs(state["lon"] - 160.501) < 0.002


def test_update_velocity():
    kf = ErrorStateKalmanFilter(dt=0.1)
    for _ in range(5):
        kf.predict()
        kf.update_velocity(50.0, 0.0)
        kf.reset()
    state = kf.get_state()
    assert abs(state["speed_ms"] - 50.0) < 5.0


def test_predict_update_reset_cycle():
    kf = ErrorStateKalmanFilter(init_lat=56.0, init_lon=160.5, dt=0.1)
    for _ in range(3):
        kf.predict()
        kf.update_position(56.001, 160.501)
        kf.update_velocity(50.0, 0.0)
        kf.reset()
    state = kf.get_state()
    assert abs(state["lat"] - 56.001) < 0.001


def test_set_position():
    kf = ErrorStateKalmanFilter()
    kf.set_position(56.0, 160.5)
    state = kf.get_state()
    assert abs(state["lat"] - 56.0) < 1e-10
    assert abs(state["lon"] - 160.5) < 1e-10


def test_kalman_gain_not_nan():
    kf = ErrorStateKalmanFilter(init_lat=56.0, init_lon=160.5, dt=0.1)
    kf.predict()
    kf.update_position(56.001, 160.501)
    assert not np.any(np.isnan(kf.P))
    assert not np.any(np.isnan(kf.dx))
