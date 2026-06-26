from typing import Optional
from dataclasses import dataclass

import pynmea2


@dataclass
class NMEAReading:
    timestamp: float
    altitude: float


class NMEAParser:
    def parse_line(self, line: str) -> Optional[NMEAReading]:
        line = line.strip()
        if not line:
            return None
        try:
            msg = pynmea2.parse(line)
        except (pynmea2.ChecksumError, pynmea2.ParseError):
            return None
        if msg.sentence_type != "GGA":
            return None
        try:
            alt = float(msg.altitude)
        except (TypeError, ValueError):
            return None
        ts = self._timestamp_to_seconds(msg.timestamp)
        return NMEAReading(timestamp=ts, altitude=alt)

    @staticmethod
    def _timestamp_to_seconds(t: Optional["pynmea2.types.Timestamp"]) -> float:
        if t is None:
            return 0.0
        return t.hour * 3600.0 + t.minute * 60.0 + t.second + (t.microsecond / 1e6)
