from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


def replay_summary(path: Path) -> dict:
    events = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return {
        "event_count": len(events),
        "first_timestamp": events[0]["timestamp"] if events else None,
        "last_timestamp": events[-1]["timestamp"] if events else None,
        "events_by_type": dict(Counter(event["event_failure"] for event in events)),
        "scenario_sequence": [event["scenario_id"] for event in events if event.get("scenario_id")],
    }
