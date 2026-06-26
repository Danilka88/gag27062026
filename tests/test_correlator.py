import numpy as np
import pytest

from gagarin.correlator import TERCOMCorrelator
from gagarin.config import Config


def make_dummy_dem():
    import xarray as xr
    import rioxarray

    nx, ny = 200, 200
    data = np.zeros((ny, nx))
    cx, cy = nx // 2, ny // 2
    for y in range(ny):
        for x in range(nx):
            data[y, x] = (
                50 * np.sin(0.05 * x) * np.cos(0.05 * y)
                + 20 * np.exp(-((x - cx) ** 2 + (y - cy) ** 2) / 2000)
                + 100
            )

    ds = xr.DataArray(
        data,
        dims=("y", "x"),
        coords={
            "y": np.linspace(55.9, 56.2, ny),
            "x": np.linspace(160.5, 160.8, nx),
        },
    )
    ds.rio.write_crs("EPSG:4326", inplace=True)
    ds.rio.set_spatial_dims("x", "y", inplace=True)
    return ds


@pytest.fixture
def dem_loader():
    from gagarin.dem_loader import DEMLoader
    ds = make_dummy_dem()
    loader = DEMLoader.__new__(DEMLoader)
    loader._ds = ds
    from pyproj import Transformer
    loader._transformer_lonlat_to_xy = Transformer.from_crs("EPSG:4326", "EPSG:4326", always_xy=True)
    loader._transformer_xy_to_lonlat = Transformer.from_crs("EPSG:4326", "EPSG:4326", always_xy=True)
    return loader


def test_ncc():
    correlator = TERCOMCorrelator.__new__(TERCOMCorrelator)
    a = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    b = a.copy()
    assert abs(correlator._ncc(a, b) - 1.0) < 1e-10
    c = -a
    assert abs(correlator._ncc(a, c) - (-1.0)) < 1e-10
    d = np.array([2.0, 3.0, 4.0, 5.0, 6.0])
    assert abs(correlator._ncc(a, d) - 1.0) < 1e-10


def test_cross_correlation_shape():
    correlator = TERCOMCorrelator.__new__(TERCOMCorrelator)
    a = np.random.randn(50)
    b = np.random.randn(50)
    result = correlator._cross_correlation(a, b)
    assert len(result) == 50


def test_confidence():
    correlator = TERCOMCorrelator.__new__(TERCOMCorrelator)
    flat = np.ones(100) * 0.3
    assert correlator._compute_confidence(flat, 0.0) == 0.0

    peaked = np.zeros(100)
    peaked[50] = 1.0
    conf = correlator._compute_confidence(peaked, 20.0)
    assert 0 < conf <= 1.0
