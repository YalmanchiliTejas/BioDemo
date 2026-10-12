from __future__ import annotations

from pathlib import Path

from src.data.temporal_store import TemporalFactoryStore


FROZEN_AGENT_DATA = Path(__file__).resolve().parents[2] / "data/v1.1/agent_data.json"


def state_at(timestamp: str, path: Path = FROZEN_AGENT_DATA) -> list[dict]:
    """Use the existing field-aware temporal store, including future-field redaction."""
    return TemporalFactoryStore(path).session(as_of=timestamp).records()
