from gagarin.nmea_parser import NMEAParser


def test_parse_valid():
    parser = NMEAParser()
    line = "$GPGGA,123519.111,,,,,,,,545.4,M,46.9,M,,*7F"
    result = parser.parse_line(line)
    assert result is not None
    assert abs(result.altitude - 545.4) < 0.01
    assert result.timestamp > 0


def test_parse_invalid_checksum():
    parser = NMEAParser()
    line = "$GPGGA,123519.111,,,,,,,,545.4,M,46.9,M,,*00"
    result = parser.parse_line(line)
    assert result is None


def test_parse_empty():
    parser = NMEAParser()
    assert parser.parse_line("") is None
    assert parser.parse_line("  ") is None


def test_parse_wrong_type():
    parser = NMEAParser()
    line = "$GPGSA,A,3,,,,,,,,,,,,,0.6,0.4,0.5*37"
    result = parser.parse_line(line)
    assert result is None
