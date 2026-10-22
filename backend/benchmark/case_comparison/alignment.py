"""Trace normalization and divergence detection for synchronized replay.

Both workflows are normalized onto one declared clock for visualization only.
The underlying benchmark data is never modified. When two traces do not share a
comparable clock basis the caller marks the comparison
``comparable: false`` and the UI must not imply synchronization.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def seconds_between(start: str, end: str) -> float:
    return (parse_time(end) - parse_time(start)).total_seconds()


@dataclass(frozen=True)
class TraceEvent:
    """One normalized event in a workflow trace."""

    id: str
    track: str
    kind: str
    title: str
    detail: str
    timestamp: str | None = None
    offset_seconds: float | None = None
    severity: str = "normal"
    system: str = ""
    evidence: tuple[str, ...] = ()
    source: str = ""
    milestone: bool = False
    recorded: bool = True
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "track": self.track,
            "kind": self.kind,
            "title": self.title,
            "detail": self.detail,
            "timestamp": self.timestamp,
            "offset_seconds": self.offset_seconds,
            "severity": self.severity,
            "system": self.system,
            "evidence": list(self.evidence),
            "source": self.source,
            "milestone": self.milestone,
            "recorded": self.recorded,
            "meta": self.meta,
        }


def normalize_track(events: Iterable[TraceEvent], clock_start: str | None) -> list[dict[str, Any]]:
    """Attach offsets against the shared clock and sort; visualization only."""
    normalized: list[dict[str, Any]] = []
    for event in events:
        record = event.to_dict()
        offset = event.offset_seconds
        if offset is None and event.timestamp and clock_start:
            offset = seconds_between(clock_start, event.timestamp)
        record["offset_seconds"] = offset
        normalized.append(record)
    normalized.sort(key=lambda item: (
        item["offset_seconds"] if item["offset_seconds"] is not None else float("inf"),
        item["id"],
    ))
    return normalized


def _first_by_kind(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    milestones: dict[str, dict[str, Any]] = {}
    for event in events:
        if not event.get("milestone"):
            continue
        kinds = [event["kind"], *(event.get("meta", {}).get("milestones") or [])]
        for kind in kinds:
            if kind not in milestones:
                milestones[kind] = event
    return milestones


DIVERGENCE_VERDICTS = {
    "ai_first": "AI OS reached this milestone earlier",
    "traditional_first": "Traditional workflow reached this milestone earlier",
    "ai_only": "Reached by the AI OS only",
    "traditional_only": "Reached by the traditional workflow only",
    "timing_difference": "Same milestone reached at different times",
    "equal": "Same milestone reached at the same time",
}


def detect_divergences(
    traditional: list[dict[str, Any]],
    ai: list[dict[str, Any]],
    *,
    tolerance_seconds: float = 0.5,
) -> list[dict[str, Any]]:
    """Compare milestone kinds across two normalized traces.

    Only milestone events are compared, and only by their shared-clock offset.
    A milestone present in one trace and absent from the other is reported as
    one-sided rather than synchronized.
    """
    traditional_milestones = _first_by_kind(traditional)
    ai_milestones = _first_by_kind(ai)
    kinds: dict[str, None] = {}
    for kind in list(traditional_milestones) + list(ai_milestones):
        kinds.setdefault(kind, None)

    divergences: list[dict[str, Any]] = []
    for index, kind in enumerate(kinds, start=1):
        traditional_event = traditional_milestones.get(kind)
        ai_event = ai_milestones.get(kind)
        if traditional_event is None and ai_event is None:
            continue
        if traditional_event is not None and ai_event is not None:
            traditional_offset = traditional_event.get("offset_seconds")
            ai_offset = ai_event.get("offset_seconds")
            if traditional_offset is None or ai_offset is None:
                verdict = "timing_difference"
                significance = None
            else:
                significance = abs(ai_offset - traditional_offset)
                if significance <= tolerance_seconds:
                    verdict = "equal"
                else:
                    verdict = "ai_first" if ai_offset < traditional_offset else "traditional_first"
        elif ai_event is not None:
            verdict, significance = "ai_only", None
        else:
            verdict, significance = "traditional_only", None

        offsets = [
            event.get("offset_seconds")
            for event in (traditional_event, ai_event)
            if event is not None and event.get("offset_seconds") is not None
        ]
        divergences.append({
            "id": f"DIV-{index:02d}",
            "kind": kind,
            "label": (ai_event or traditional_event or {}).get("title", kind),
            "verdict": verdict,
            "verdict_label": DIVERGENCE_VERDICTS[verdict],
            "offset_seconds": min(offsets) if offsets else None,
            "difference_seconds": significance,
            "traditional": _ref(traditional_event),
            "ai": _ref(ai_event),
        })
    divergences.sort(key=lambda item: item["offset_seconds"] if item["offset_seconds"] is not None else float("inf"))
    return divergences


def _ref(event: dict[str, Any] | None) -> dict[str, Any] | None:
    if event is None:
        return None
    return {
        "event_id": event["id"],
        "title": event["title"],
        "timestamp": event.get("timestamp"),
        "offset_seconds": event.get("offset_seconds"),
        "detail": event.get("detail", ""),
    }


def event_index(events: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {event["id"]: event for event in events}
