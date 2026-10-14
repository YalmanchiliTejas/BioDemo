"""Time- and scope-limited RLM view over ingested manufacturing observations."""

from __future__ import annotations

from typing import Iterable

from .store import ManufacturingStore


class ManufacturingSession:
    def __init__(self, store: ManufacturingStore, *, as_of: str, scopes: tuple[str, ...]) -> None:
        self.store = store
        self.as_of = as_of
        self.scopes = scopes
        self._entity_kinds: dict[str, str | None] = {}

    def _entity_kind(self, identifier: str) -> str | None:
        if identifier not in self._entity_kinds:
            with self.store.connect() as con:
                row = con.execute("SELECT kind FROM entities WHERE id=?", (identifier,)).fetchone()
            self._entity_kinds[identifier] = row["kind"] if row else None
        return self._entity_kinds[identifier]

    def _rlm_record(self, row: dict) -> dict:
        record = dict(row)
        record["_table"] = "observations"
        record["_evidence_id"] = row["id"]
        record["parameter"] = row["name"]
        record["value"] = row["value_number"] if row["value_number"] is not None else row["value_text"]
        kind = self._entity_kind(row["entity_id"]) if row["entity_id"] else None
        if kind in {"batch", "run"}:
            record["batch_id"] = row["entity_id"]
        elif kind == "equipment":
            record["equipment_id"] = row["entity_id"]
        return record

    def get(self, identifiers: Iterable[str]) -> list[dict]:
        rows = []
        for identifier in dict.fromkeys(map(str, identifiers)):
            found = self.store.visible(as_of=self.as_of, scopes=self.scopes,
                                       observation_id=identifier, limit=1)
            if found:
                rows.append(self._rlm_record(found[0]))
        return rows

    def visible_evidence_ids(self) -> set[str]:
        return {row["id"] for row in self.store.visible(as_of=self.as_of,
                                                         scopes=self.scopes, limit=None)}

