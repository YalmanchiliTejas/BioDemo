from __future__ import annotations

from typing import Any

from .temporal_store import TemporalFactoryStore


def state_at(
    store: TemporalFactoryStore,
    timestamp: str,
    *,
    mode: str = "full_os",
    current_evidence_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Compatibility helper exposing only time-valid, mode-permitted evidence."""
    session = store.session(
        as_of=timestamp,
        mode=mode,
        current_evidence_ids=current_evidence_ids or [],
    )
    records = session.records()
    return {
        "as_of": timestamp,
        "context_condition": mode,
        "records": records,
        "visible_evidence_ids": sorted(row["_evidence_id"] for row in records),
    }
