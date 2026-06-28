import numpy as np
from gagarin.dem_loader import DEMLoader
from gagarin.checkpoint import _mad, _ncc, _search_position_grid


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


def test_search_position_grid_returns_five_values():
    dem = DEMLoader("data/dem/synthetic_kamchatka.tif")
    lat, lon = dem.pixel_to_lonlat(200, 200)
    ref = dem.elevation_batch(
        np.array([lat] * 20),
        np.array([lon] * 20),
    )
    result = _search_position_grid(dem, ref, lat, lon, 45.0, 60.0, 10.0)
    assert len(result) == 5


def test_search_position_grid_best_mad_is_low_at_correct_position():
    from gagarin.checkpoint import _extract_profile
    dem = DEMLoader("data/dem/synthetic_kamchatka.tif")
    lat, lon = dem.pixel_to_lonlat(200, 200)
    ref = _extract_profile(dem, lat, lon, 45.0, 60.0, 30, 10.0)
    _, _, mad, ncc, discr = _search_position_grid(dem, ref, lat, lon, 45.0, 60.0, 10.0, pixel_radius=2)
    assert mad < 1.0
    assert abs(ncc) > 0.99


def test_minima_ratio_low_on_flat_region():
    from gagarin.checkpoint import _extract_profile
    dem = DEMLoader("data/dem/siberia.tif")
    lat, lon = dem.pixel_to_lonlat(200, 200)
    ref = _extract_profile(dem, lat, lon, 45.0, 60.0, 30, 10.0)
    _, _, mad, ncc, discr = _search_position_grid(dem, ref, lat, lon, 45.0, 60.0, 10.0, pixel_radius=2)
    assert discr < 3.0  # flat terrain — poor discrimination
