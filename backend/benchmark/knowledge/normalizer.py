from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from .domain import CanonicalEvent, EntityRef, EvidenceRecord


class EventNormalizer:
    """Maps source records to a canonical, explicitly scoped event envelope."""

    def normalize(
        self, record: dict[str, Any], evidence: EvidenceRecord, *, tenant_id: str,
        source_system: str, site_id: str | None = None, classification: str = "internal",
    ) -> CanonicalEvent:
        occurred_at = _timestamp(record.get("timestamp") or evidence.event_time)
        source_record_id = str(record.get("source_record_id") or evidence.source_record_id)
        event_id = str(record.get("event_id") or _event_id(tenant_id, source_system, source_record_id, record))
        entities = tuple(sorted(self._entities(record), key=lambda item: (item.entity_type, item.entity_id)))
        summary = " | ".join(str(value) for value in (
            record.get("event_failure") or record.get("event_type"),
            record.get("actor_agent_action"), record.get("decision"),
        ) if value)
        return CanonicalEvent(
            event_id=event_id, tenant_id=tenant_id, source_system=source_system,
            source_record_id=source_record_id,
            event_type=str(record.get("event_failure") or record.get("event_type") or "unknown"),
            occurred_at=occurred_at, ingested_at=evidence.ingested_at,
            evidence_id=evidence.evidence_id, entities=entities, site_id=site_id,
            classification=classification, summary=summary,
            correlation_id=record.get("correlation_id") or record.get("scenario_id"),
            causation_id=record.get("causation_id"),
            attributes={
                "scenario_id": record.get("scenario_id"),
                "approval_required": bool(record.get("approval_required", False)),
                "tool_used": record.get("tool_used"),
            },
        )

    def _entities(self, record: dict[str, Any]) -> set[EntityRef]:
        entities: set[EntityRef] = set()
        for value in record.get("entities", []):
            if isinstance(value, dict) and value.get("entity_id") and value.get("entity_type"):
                entities.add(EntityRef(str(value["entity_id"]), str(value["entity_type"]), value.get("role", "affected")))
        for value in record.get("information_available") or []:
            if isinstance(value, str):
                for token in _identifier_tokens(value):
                    entities.add(EntityRef(token, _entity_type(token)))
        state = record.get("plant_state") or {}
        for asset_id in state.get("unavailable_assets", []):
            entities.add(EntityRef(str(asset_id), "asset"))
        if record.get("scenario_id"):
            entities.add(EntityRef(str(record["scenario_id"]), "scenario", "correlation"))
        return entities


def _timestamp(value: str | datetime) -> datetime:
    result = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("event timestamps must include a timezone")
    return result.astimezone(timezone.utc)


def _event_id(tenant_id: str, source: str, source_record_id: str, record: dict[str, Any]) -> str:
    raw = json.dumps([tenant_id, source, source_record_id, record], sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def _identifier_tokens(value: str) -> set[str]:
    tokens = value.replace(":", " ").replace("=", " ").replace(",", " ").split()
    return {token for token in tokens if "-" in token and token.replace("-", "").isalnum()}


def _entity_type(identifier: str) -> str:
    prefix = identifier.split("-", 1)[0].upper()
    return {
        "BATCH": "batch", "RM": "material_lot", "BUF": "material_lot",
        "BIOREACTOR": "asset", "CHROM": "asset", "PUMP": "asset", "QC": "asset",
        "DEV": "deviation", "CAPA": "capa", "OOS": "oos", "SCN": "scenario",
    }.get(prefix, "entity")
