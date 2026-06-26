import numpy as np
from gagarin.estimator import VelocityEstimator
from gagarin.correlator import MatchResult
from gagarin.config import Config
from gagarin.geo_utils import offset_coords


def test_estimate():
    cfg = Config.default()
    estimator = VelocityEstimator(cfg)

    match = MatchResult(
        azimuth_deg=45.0,
        speed_ms=50.0,
        correlation=0.95,
        lag_samples=0,
        confidence=0.85,
        terrain_roughness=25.0,
        reference_profile=np.zeros(100),
        observed_profile=np.zeros(100),
    )

    result = estimator.estimate(match, 56.0, 160.5)
    assert abs(result["azimuth_deg"] - 45.0) < 0.1
    assert abs(result["speed_ms"] - 50.0) < 0.1
    assert result["confidence"] == 0.85


def test_offset():
    import math
    lat, lon = offset_coords(56.0, 160.5, 0, 0.0)
    assert abs(lat - 56.0) < 1e-10
    assert abs(lon - 160.5) < 1e-10
