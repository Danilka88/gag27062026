from gagarin.config import Config


def test_default_creates_valid_config():
    cfg = Config.default()
    assert cfg.window_size > 0
    assert cfg.nmea_freq_hz > 0


def test_merge_overrides_field():
    cfg = Config.default()
    merged = cfg.merge({"window_size": 500})
    assert merged.window_size == 500


def test_merge_keeps_other_fields():
    cfg = Config.default()
    original = cfg.window_size
    merged = cfg.merge({"nmea_freq_hz": 20})
    assert merged.window_size == original
    assert merged.nmea_freq_hz == 20


def test_merge_returns_new_instance():
    cfg = Config.default()
    merged = cfg.merge({"window_size": 500})
    assert merged is not cfg
    assert cfg.window_size != 500


def test_post_init_rejects_negative_window():
    import pytest
    with pytest.raises(ValueError, match="window_size"):
        Config(window_size=0)


def test_post_init_rejects_negative_nmea_freq():
    import pytest
    with pytest.raises(ValueError, match="nmea_freq_hz"):
        Config(nmea_freq_hz=-1)


def test_post_init_rejects_negative_coarse_step():
    import pytest
    with pytest.raises(ValueError, match="coarse_azimuth_step"):
        Config(coarse_azimuth_step=0)


def test_post_init_rejects_zero_flight_duration():
    import pytest
    with pytest.raises(ValueError, match="flight_duration"):
        Config(flight_duration=0)


def test_merge_unknown_keys_warns():
    import pytest
    cfg = Config.default()
    with pytest.warns(UserWarning, match="Unknown config"):
        cfg.merge({"nonexistent_key": 123})
