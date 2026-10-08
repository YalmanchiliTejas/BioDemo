from __future__ import annotations

import json
import os
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class Blackboard:
    incident_id: str
    status: str = "investigating"
    severity: str = "LOW"
    scope: dict[str, Any] = field(default_factory=lambda: {"type": "unknown", "batch_ids": [], "equipment_ids": []})
    observations: list[dict[str, Any]] = field(default_factory=list)
    causal_hypotheses: list[dict[str, Any]] = field(default_factory=list)
    resolved_questions: list[dict[str, Any]] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    pending_evidence: list[dict[str, Any]] = field(default_factory=list)
    completed_investigations: list[dict[str, Any]] = field(default_factory=list)
    recommended_actions: list[dict[str, Any]] = field(default_factory=list)
    decision_branches: list[dict[str, Any]] = field(default_factory=list)
    teams_involved: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    rollout_history: list[dict[str, Any]] = field(default_factory=list)
    last_updated_at: str = field(default_factory=now)

    def to_dict(self) -> dict[str, Any]:
        return deepcopy(asdict(self))

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Blackboard":
        permitted = cls.__dataclass_fields__
        return cls(**{key: deepcopy(item) for key, item in value.items() if key in permitted})


class BlackboardStore:
    """Atomic JSON persistence; no prompts or hidden reasoning are stored."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    @staticmethod
    def _safe(value: str) -> str:
        if not value or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for character in value):
            raise ValueError("invalid blackboard identifier")
        return value

    def path(self, incident_id: str) -> Path:
        return self.root / f"{self._safe(incident_id)}.json"

    def load(self, incident_id: str) -> Blackboard | None:
        path = self.path(incident_id)
        return Blackboard.from_dict(json.loads(path.read_text(encoding="utf-8"))) if path.is_file() else None

    def load_or_create(self, incident_id: str) -> Blackboard:
        return self.load(incident_id) or Blackboard(incident_id=incident_id)

    def save(self, blackboard: Blackboard) -> None:
        path = self.path(blackboard.incident_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        blackboard.last_updated_at = now()
        temporary = path.with_suffix(f".json.{os.getpid()}.tmp")
        temporary.write_text(json.dumps(blackboard.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, path)
