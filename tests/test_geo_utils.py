import math
import numpy as np
from gagarin.geo_utils import offset_coords, offset_coords_batch


def test_offset_coords_zero_distance():
    lat, lon = offset_coords(56.0, 160.5, 0, 0.0)
    assert abs(lat - 56.0) < 1e-10
    assert abs(lon - 160.5) < 1e-10


def test_offset_coords_north():
    lat, lon = offset_coords(56.0, 160.5, 1000, 0.0)
    assert lat > 56.0
    assert abs(lon - 160.5) < 1e-10


def test_offset_coords_east():
    lat, lon = offset_coords(56.0, 160.5, 1000, math.radians(90))
    assert lon > 160.5
    assert abs(lat - 56.0) < 1e-6


def test_offset_coords_south():
    lat, lon = offset_coords(56.0, 160.5, 1000, math.radians(180))
    assert lat < 56.0
    assert abs(lon - 160.5) < 1e-10


def test_offset_coords_west():
    lat, lon = offset_coords(56.0, 160.5, 1000, math.radians(270))
    assert lon < 160.5
    assert abs(lat - 56.0) < 1e-6


def test_offset_coords_distance_sanity():
    """~111km/deg at equator, ~55.6km at 60° lat for lon"""
    lat, lon = offset_coords(56.0, 160.5, 111000, 0.0)
    dlat = (lat - 56.0) * 111000
    assert abs(dlat - 111000) < 500


def test_offset_coords_batch_output_shape():
    lats = np.array([56.0, 56.0])
    lons = np.array([160.5, 160.5])
    dists = np.array([0.0, 1000.0])
    result_lats, result_lons = offset_coords_batch(lats, lons, dists, 0.0, 56.0)
    assert result_lats.shape == (2,)
    assert result_lons.shape == (2,)
    assert result_lats[1] > result_lats[0]
