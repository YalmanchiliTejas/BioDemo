"""Wall-clock injection; the product scheduler and monotonic limits remain real."""
from dataclasses import dataclass
from src.lifesci.ids import parse_iso, use_clock

@dataclass
class MissionClock:
    timestamp: str

    def now(self):
        return parse_iso(self.timestamp)

    def advance(self, timestamp):
        if parse_iso(timestamp) < self.now():
            raise ValueError('mission clock cannot go backwards')
        self.timestamp = timestamp

    def activate(self):
        return use_clock(self.now)
