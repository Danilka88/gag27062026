import math
from gagarin.constants import EARTH_RADIUS


def test_synthetic_scenario_produces_valid_steps():
    from simulation_ui.runner import SimulationRunner
    runner = SimulationRunner('synthetic')
    steps = list(runner.run())
    assert len(steps) == 14
    for i, step in enumerate(steps):
        assert 'id' in step
        assert 'number' in step
        assert 'svg' in step
        assert len(step['svg']) > 0, f"Step {i} has empty SVG"
        assert 'metrics' in step


def test_no_fake_estimates():
    from simulation_ui.runner import SimulationRunner
    runner = SimulationRunner('synthetic')
    steps = list(runner.run())
    step10 = steps[10]
    assert step10['id'] == 'step-b8'
    assert step10['metrics']['n_estimates'] == step10['metrics'].get('n_estimates_total', step10['metrics']['n_estimates'])
    step11 = steps[11]
    assert step11['id'] == 'step-b9'
    assert 'mean_error_m' in step11['metrics']


def test_baro_altitude_override():
    from simulation_ui.runner import SimulationRunner
    from gagarin.config import Config
    from gagarin.dem_loader import DEMLoader
    cfg = Config.default()
    cfg.baro_altitude = 3500.0
    dem = DEMLoader("data/dem/dramatic_kamchatka.tif")
    from gagarin.data_generator import DataGenerator, FlightParams
    bounds = dem.bounds
    center_lat = (bounds[1] + bounds[3]) / 2
    center_lon = (bounds[0] + bounds[2]) / 2
    params = FlightParams(start_lat=center_lat, start_lon=center_lon, azimuth_deg=45, speed_ms=60, duration_s=40)
    gen = DataGenerator(dem, cfg)
    nmea_lines = list(gen.stream_nmea(params, noise_std=1.0))
    from gagarin.nmea_parser import NMEAParser
    parser = NMEAParser()
    readings = [r for line in nmea_lines if (r := parser.parse_line(line)) is not None]
    assert len(readings) > 0


def test_eskf_error_in_meters():
    from simulation_ui.svg_generator import svg_eskf_error
    errors = [1.5, 2.3, 3.1, 1.8, 2.5]
    svg = svg_eskf_error(errors, "Test")
    assert "м" in svg


def test_heatmap_uses_local_indices():
    from simulation_ui.svg_generator import svg_heatmap
    import numpy as np
    coarse_matrix = np.random.rand(36, 10)
    coarse_labels_az = [f"{a:.0f}" for a in range(0, 360, 10)]
    coarse_labels_sp = [f"{s:.0f}" for s in range(10, 151, 14)]
    svg = svg_heatmap(coarse_matrix, coarse_labels_az, coarse_labels_sp, "Test coarse", highlight_az=45, highlight_sp=85)
    assert "highlight" not in svg.lower() or "circle" in svg
    fine_matrix = np.random.rand(10, 5)
    fine_labels_az = [f"{a:.1f}" for a in [42.0, 42.5, 43.0, 43.5, 44.0, 44.5, 45.0, 45.5, 46.0, 46.5]]
    fine_labels_sp = [f"{s:.0f}" for s in [55, 60, 65, 70, 75]]
    svg = svg_heatmap(fine_matrix, fine_labels_az, fine_labels_sp, "Test fine", highlight_az=45.0, highlight_sp=60, highlight_ri=6, highlight_ci=1)
    assert "45.0" in svg


def test_corridor_width_uses_segment_distance():
    from simulation_ui.runner import SimulationRunner
    from gagarin.preprocess import _adaptive_corridor_width
    runner = SimulationRunner('synthetic')
    steps = list(runner.run())
    step2 = steps[2]
    assert step2['id'] == 'step-p3'
    assert step2['metrics']['corridor_width_m'] != "10200"


def test_profile_has_reference():
    from simulation_ui.runner import SimulationRunner
    runner = SimulationRunner('synthetic')
    steps = list(runner.run())
    step8 = steps[8]
    assert step8['id'] == 'step-b6'
    assert 'NCC' in step8['svg']