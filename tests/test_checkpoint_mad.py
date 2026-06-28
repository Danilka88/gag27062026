import numpy as np
from gagarin.dem_loader import DEMLoader
from gagarin.checkpoint import _mad, _ncc, _search_position_grid, WindowEstimate, _eskf_filter_estimates
from gagarin.geo_utils import haversine_m


def test_mad_returns_zero_on_identical():
    a = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    assert _mad(a, a) == 0.0


def test_mad_mean_subtraction_removes_bias():
    a = np.array([100.0, 200.0, 300.0, 400.0])
    b = a + 500.0
    assert _mad(a, b) == 0.0


def test_mad_detects_shape_mismatch():
    a = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    b = np.array([1.0, 2.0, 3.0, 4.0, 10.0])
    assert _mad(a, a) == 0.0
    assert _mad(a, b) > _mad(a, a)


def test_search_position_grid_returns_six_values():
    dem = DEMLoader("data/dem/synthetic_kamchatka.tif")
    lat, lon = dem.pixel_to_lonlat(200, 200)
    ref = dem.elevation_batch(
        np.array([lat] * 20),
        np.array([lon] * 20),
    )
    result = _search_position_grid(dem, ref, lat, lon, 45.0, 60.0, 10.0)
    assert len(result) == 6


def test_search_position_grid_best_mad_is_low_at_correct_position():
    from gagarin.checkpoint import _extract_profile
    dem = DEMLoader("data/dem/synthetic_kamchatka.tif")
    lat, lon = dem.pixel_to_lonlat(200, 200)
    ref = _extract_profile(dem, lat, lon, 45.0, 60.0, 30, 10.0)
    _, _, mad, ncc, discr, _ = _search_position_grid(dem, ref, lat, lon, 45.0, 60.0, 10.0, pixel_radius=2)
    assert mad < 1.0
    assert abs(ncc) > 0.99


def test_minima_ratio_low_on_flat_region():
    from gagarin.checkpoint import _extract_profile
    dem = DEMLoader("data/dem/siberia.tif")
    lat, lon = dem.pixel_to_lonlat(200, 200)
    ref = _extract_profile(dem, lat, lon, 45.0, 60.0, 30, 10.0)
    _, _, mad, ncc, discr, _ = _search_position_grid(dem, ref, lat, lon, 45.0, 60.0, 10.0, pixel_radius=2)
    assert discr < 3.0  # flat terrain — poor discrimination


def test_pre_rejection_passes_good_estimate():
    from gagarin.checkpoint import _extract_profile, _process_windows
    from gagarin.config import Config
    dem = DEMLoader("data/dem/dramatic_kamchatka.tif")
    lat, lon = dem.pixel_to_lonlat(200, 200)
    ref = _extract_profile(dem, lat, lon, 45.0, 60.0, 40, 10.0)
    cfg = Config.default()
    ests, indices = _process_windows(dem, ref, lat, lon, 45.0, 60.0, 20, [45.0, 44.0, 46.0], 10.0, cfg)
    assert len(ests) > 0


def _make_est(lat, lon, az=0.0, sp=60.0, t=0.0, discr=5.0, corr=0.95):
    return WindowEstimate(
        position_lat=lat, position_lon=lon,
        azimuth_deg=az, speed_ms=sp,
        correlation=corr, confidence=0.9,
        discrimination_ratio=discr, peak_to_valley=50.0,
        terrain_std=30.0, quality={"quality": "good"},
        timestamp=t, mad_value=5.0,
    )


def test_eskf_filter_empty():
    ests, idx = _eskf_filter_estimates([], [])
    assert len(ests) == 0


def test_eskf_filter_single_estimate():
    e = _make_est(10.0, 20.0)
    ests, _ = _eskf_filter_estimates([e], [0])
    assert ests[0].filtered_lat == 10.0
    assert ests[0].filtered_lon == 20.0


def test_eskf_filter_smooths_noisy_estimates():
    np.random.seed(42)
    n = 6
    start_lat, start_lon = 10.0, 20.0
    az, sp = 0.0, 60.0
    ests = []
    for i in range(n):
        noise_lat = np.random.uniform(-0.002, 0.002)
        noise_lon = np.random.uniform(-0.002, 0.002)
        lat = start_lat + i * 0.002 + noise_lat
        lon = start_lon + noise_lon
        ests.append(_make_est(lat, lon, az=az, sp=sp, t=i * 4.0, discr=8.0))
    result, _ = _eskf_filter_estimates(ests, list(range(n)))

    raw_errs = [haversine_m(e.position_lat, e.position_lon,
                            10.0 + i*0.002, 20.0) for i, e in enumerate(ests)]
    flt_errs = [haversine_m(e.filtered_lat, e.filtered_lon,
                            10.0 + i*0.002, 20.0) for i, e in enumerate(result)]
    assert float(np.median(flt_errs)) < float(np.median(raw_errs)), \
        "ESKF should reduce median error on noisy estimates"


def test_eskf_filter_dr_propagation():
    e0 = _make_est(10.0, 20.0, az=0.0, sp=60.0, t=0.0, discr=10.0)
    e1 = _make_est(10.002, 20.0, az=0.0, sp=60.0, t=4.0, discr=10.0)
    ests, _ = _eskf_filter_estimates([e0, e1], [0, 1])
    assert ests[1].filtered_lat > ests[0].filtered_lat, "DR should propagate north"
    assert abs(ests[1].filtered_lon - ests[0].filtered_lon) < 0.001, "DR should not move east/west"


def test_eskf_filter_high_discr_beats_low_discr():
    lat0, lon0 = 10.0, 20.0
    lat1, lon1 = 10.002, 20.0
    dt = 4.0

    e_high0 = _make_est(lat0, lon0, az=0.0, sp=60.0, t=0.0, discr=10.0)
    e_high1 = _make_est(lat1, lon1, az=0.0, sp=60.0, t=dt, discr=10.0)
    ests_high, _ = _eskf_filter_estimates([e_high0, e_high1], [0, 1])
    high_err = haversine_m(ests_high[1].filtered_lat, ests_high[1].filtered_lon, lat1, lon1)

    e_low0 = _make_est(lat0, lon0, az=0.0, sp=60.0, t=0.0, discr=1.2)
    e_low1 = _make_est(lat1, lon1, az=0.0, sp=60.0, t=dt, discr=1.2)
    ests_low, _ = _eskf_filter_estimates([e_low0, e_low1], [0, 1])
    low_err = haversine_m(ests_low[1].filtered_lat, ests_low[1].filtered_lon, lat1, lon1)

    assert high_err < low_err, \
        f"high discr should trust measurement more: high_err={high_err:.4f}m > low_err={low_err:.4f}m"
