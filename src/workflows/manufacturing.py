"""Durable, evidence-constrained workflow after a manufacturing RLM rollout.

This module prepares reviewable investigation state. It never executes a
manufacturing, disposition, testing, or release action.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.manufacturing_data import ManufacturingStore, ManufacturingTools
from src.state import BlackboardStore


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


class ManufacturingInvestigationWorkflow:
    """Turns a completed RLM rollout into a reviewable, time-scoped case."""

    def __init__(self, root: str | Path, manufacturing_store: ManufacturingStore,
                 *, scope: str = "default", blackboards: BlackboardStore | None = None) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = self.root / "investigations.sqlite"
        self.manufacturing_store = manufacturing_store
        self.scope = scope
        self.blackboards = blackboards
        with self._connect() as con:
            con.executescript("""
                CREATE TABLE IF NOT EXISTS cases (
                    incident_id TEXT NOT NULL, scope TEXT NOT NULL,
                    report_json TEXT NOT NULL, updated_at TEXT NOT NULL,
                    PRIMARY KEY (scope, incident_id)
                );
                CREATE TABLE IF NOT EXISTS updates (
                    update_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    incident_id TEXT NOT NULL, scope TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    actor_id TEXT NOT NULL, occurred_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS updates_case ON updates(scope, incident_id, update_id);
            """)
        self.db.chmod(0o600)

    def _connect(self):
        connection = sqlite3.connect(self.db)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _safe_id(value: str) -> str:
        if not value or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for char in value):
            raise ValueError("invalid incident id")
        return value

    def _visible(self, identifiers: list[str], as_of: str) -> dict[str, dict]:
        rows = {}
        for identifier in dict.fromkeys(map(str, identifiers)):
            found = self.manufacturing_store.visible(
                scopes=(self.scope,), as_of=as_of, observation_id=identifier, limit=1,
            )
            if found:
                rows[identifier] = found[0]
        if len(rows) != len(set(identifiers)):
            raise ValueError("report cites evidence unavailable at this scope and timestamp")
        return rows

    def _related_status_ids(self, as_of: str, entities: list[str]) -> list[str]:
        """Discover explicit status fields for entities already in RLM scope."""
        entities = list(dict.fromkeys(str(value) for value in entities if value))
        if not entities:
            return []
        placeholders = ",".join("?" for _ in entities)
        with self.manufacturing_store.connect() as con:
            rows = con.execute(
                "SELECT o.id FROM observations o JOIN sources s ON s.id=o.source_id "
                "WHERE o.access_scope=? AND o.entity_id IN (" + placeholders + ") "
                "AND (lower(o.name) LIKE '%status%' OR lower(o.name) LIKE '%severity%' "
                "OR lower(o.name) LIKE '%classification%' OR lower(o.name) LIKE '%disposition%') "
                "AND (o.available_at IS NULL OR julianday(o.available_at)<=julianday(?)) "
                "AND (s.available_at IS NULL OR julianday(s.available_at)<=julianday(?)) "
                "AND s.extraction_status='indexed'",
                (self.scope, *entities, as_of, as_of),
            ).fetchall()
        return [row["id"] for row in rows]

    @staticmethod
    def _signal(row: dict) -> str | None:
        name = str(row["name"]).lower().replace("_", " ")
        value = str(row.get("value_text") or "").strip().lower().replace("_", " ")
        if row["validation_status"] == "rejected":
            return None
        # Require a categorical source field; do not infer a GMP excursion
        # from a raw numeric value without a supplied specification.
        if not any(term in name for term in ("status", "severity", "classification", "disposition")):
            return None
        if value in {"critical", "out of specification", "oos", "fail", "failed"}:
            return "critical"
        if value in {"action", "action limit", "deviation", "nonconforming"}:
            return "action"
        if value in {"alert", "warning"}:
            return "alert"
        return None

    @staticmethod
    def _triage(signals: list[dict]) -> dict:
        reliable = [s for s in signals if s["validation_status"] in {"source_transcribed", "normalized"}]
        batches = {str(s["entity_id"]) for s in reliable if s.get("entity_id")}
        levels = {s["signal"] for s in reliable}
        if "critical" in levels:
            level, reason = "L3", "An explicit critical or failed source status is present."
        elif len(batches) >= 2 and ("action" in levels or "critical" in levels):
            level, reason = "L2", "Action-level source statuses recur across at least two linked entities."
        elif levels:
            level, reason = "L1", "An explicit alert or action source status needs investigation."
        else:
            level, reason = "unclassified", "No verified categorical deviation status is available."
        roles = {"L1": ["qa"], "L2": ["qa", "msat"],
                 "L3": ["qa", "sponsor_qa"]}.get(level, [])
        return {"level": level, "reason": reason, "provisional": True,
                "required_review_roles": roles, "policy": "illustrative; site SOP controls final triage"}

    def _test_hypotheses(self, hypotheses: list[dict], visible: dict[str, dict],
                         as_of: str) -> list[dict]:
        tools = ManufacturingTools(self.manufacturing_store, as_of=as_of, scopes=(self.scope,))
        verified: dict[str, dict] = {}
        tested = []
        for hypothesis in hypotheses:
            support = list(dict.fromkeys(map(str, hypothesis.get("supporting_evidence_ids", []))))
            contradiction = list(dict.fromkeys(map(str, hypothesis.get("contradicting_evidence_ids", []))))
            checks = []
            for identifier in dict.fromkeys(support + contradiction):
                if identifier not in visible:
                    raise ValueError("hypothesis cites unavailable evidence")
                if identifier not in verified:
                    verified[identifier] = tools.verify_evidence(observation_id=identifier)
                check = verified[identifier]
                checks.append({"evidence_id": identifier,
                               "role": "support" if identifier in support else "contradiction",
                               "source_ref": visible[identifier]["source_ref"],
                               "source_integrity": check["source_integrity"],
                               "value_matches": check["value_matches"],
                               "validation_status": check["validation_status"]})
            source_checked = [c for c in checks if c["source_integrity"] and c["value_matches"] is True]
            if not checks:
                status = "untested"
            elif len(source_checked) != len(checks):
                status = "requires_source_review"
            elif contradiction:
                status = "mixed_or_contradicted"
            else:
                status = "observational_support_only"
            tested.append({"hypothesis_id": hypothesis["hypothesis_id"],
                           "statement": hypothesis["statement"], "status": status,
                           "evidence_checks": checks,
                           "unknowns": hypothesis.get("unknowns", []),
                           "discriminating_tests": hypothesis.get("tests_or_observations_that_would_discriminate", []),
                           "root_cause_confirmed": False})
        return tested

    def record_rollout(self, incident_id: str, as_of: str, objective: str,
                       rollout: dict) -> dict:
        incident_id = self._safe_id(incident_id)
        cited_ids = list(dict.fromkeys(map(str, rollout.get("evidence_ids", []))))
        discovered_ids = self._related_status_ids(as_of, rollout.get("related_batches", []))
        evidence_ids = list(dict.fromkeys(cited_ids + discovered_ids))
        visible = self._visible(evidence_ids, as_of)
        signals = []
        for identifier, row in visible.items():
            classification = self._signal(row)
            if classification:
                signals.append({"evidence_id": identifier, "signal": classification,
                                "entity_id": row["entity_id"],
                                "source_ref": row["source_ref"],
                                "validation_status": row["validation_status"]})
        triage = self._triage(signals)
        tests = self._test_hypotheses(rollout.get("causal_hypotheses", []), visible, as_of)
        with self._connect() as con:
            prior = con.execute("SELECT report_json FROM cases WHERE incident_id=? AND scope=?",
                                (incident_id, self.scope)).fetchone()
            previous = json.loads(prior[0]) if prior else None
            from src.data.temporal_store import parse_time
            if previous and parse_time(previous["as_of"]) > parse_time(as_of):
                raise ValueError("cannot update an investigation with an earlier historical state")
            task_status = {x["task_id"]: x["status"] for x in previous["tasks"]} if previous else {}
            tasks = [{**item, "status": task_status.get(item["task_id"], "open")}
                     for item in rollout.get("actions_now", []) if item.get("task_id")]
            approval = previous["approval"] if previous else {
                "status": "pending" if triage["required_review_roles"] else "not_requested",
                "required_roles": triage["required_review_roles"], "decisions": []}
            changed = bool(previous and (
                previous["triage"]["level"] != triage["level"] or
                set(evidence_ids) != set(previous["evidence_ids"]) or
                _json(tests) != _json(previous["hypothesis_tests"]) or
                _json(rollout.get("decision_branches", [])) != _json(previous["decision_branches"])))
            if changed:
                approval = {"status": "pending" if triage["required_review_roles"] else "not_requested",
                            "required_roles": triage["required_review_roles"], "decisions": []}
            status = ("closed" if previous and previous["status"] == "closed" and not changed
                      else "reviewed" if approval["status"] == "approved"
                      else "awaiting_review" if triage["required_review_roles"]
                      else "investigating")
            report = {"incident_id": incident_id, "scope": self.scope, "as_of": as_of,
                      "objective": objective, "assessment": rollout.get("assessment"),
                      "deviation_signals": signals, "triage": triage,
                      "hypothesis_tests": tests, "evidence_ids": evidence_ids,
                      "rlm_cited_evidence_ids": cited_ids,
                      "workflow_discovered_evidence_ids": [item for item in discovered_ids
                                                           if item not in cited_ids],
                      "evidence_requests": rollout.get("pending_evidence_requests", []),
                      "tasks": tasks, "approval": approval,
                      "decision_branches": rollout.get("decision_branches", []),
                      "outcomes": previous["outcomes"] if previous else [],
                      "status": status,
                      "updated_at": _now()}
            con.execute("INSERT OR REPLACE INTO cases VALUES (?,?,?,?)",
                        (incident_id, self.scope, _json(report), report["updated_at"]))
            con.execute("INSERT INTO updates (incident_id,scope,event_type,actor_id,occurred_at,payload_json) VALUES (?,?,?,?,?,?)",
                        (incident_id, self.scope, "rollout", "manufacturing-rlm", report["updated_at"],
                         _json({"as_of": as_of, "signal_count": len(signals), "triage": triage["level"]})))
        if self.blackboards:
            blackboard = self.blackboards.load(incident_id)
            if blackboard is not None:
                blackboard.evidence_ids = list(dict.fromkeys(blackboard.evidence_ids + discovered_ids))
                if status == "closed":
                    blackboard.status = "closed"
                self.blackboards.save(blackboard)
        return report

    def get(self, incident_id: str) -> dict:
        incident_id = self._safe_id(incident_id)
        with self._connect() as con:
            row = con.execute("SELECT report_json FROM cases WHERE incident_id=? AND scope=?",
                              (incident_id, self.scope)).fetchone()
        if not row:
            raise KeyError(incident_id)
        return json.loads(row[0])

    def history(self, incident_id: str) -> list[dict]:
        self.get(incident_id)
        with self._connect() as con:
            rows = con.execute("SELECT * FROM updates WHERE incident_id=? AND scope=? ORDER BY update_id",
                               (incident_id, self.scope)).fetchall()
        return [{**dict(row), "payload": json.loads(row["payload_json"])} for row in rows]

    def _save_update(self, report: dict, event_type: str, actor_id: str, payload: dict) -> dict:
        report["updated_at"] = _now()
        with self._connect() as con:
            con.execute("UPDATE cases SET report_json=?,updated_at=? WHERE incident_id=? AND scope=?",
                        (_json(report), report["updated_at"], report["incident_id"], self.scope))
            con.execute("INSERT INTO updates (incident_id,scope,event_type,actor_id,occurred_at,payload_json) VALUES (?,?,?,?,?,?)",
                        (report["incident_id"], self.scope, event_type, actor_id,
                         report["updated_at"], _json(payload)))
        return report

    def decide_review(self, incident_id: str, *, actor_id: str, roles: tuple[str, ...],
                      role: str, decision: str, note: str = "") -> dict:
        report = self.get(incident_id)
        approval = report["approval"]
        if approval["status"] != "pending":
            raise ValueError("no pending investigation review")
        if role not in roles or role not in approval["required_roles"]:
            raise PermissionError("actor lacks a required review role")
        if actor_id == "manufacturing-rlm":
            raise PermissionError("the agent cannot approve its own report")
        if decision not in {"approved", "rejected"}:
            raise ValueError("decision must be approved or rejected")
        if any(item["role"] == role for item in approval["decisions"]):
            raise ValueError("this review role has already decided")
        if any(item["actor_id"] == actor_id for item in approval["decisions"]):
            raise PermissionError("distinct reviewers are required for distinct roles")
        approval["decisions"].append({"actor_id": actor_id, "role": role,
                                       "decision": decision, "note": note, "decided_at": _now()})
        approved = {item["role"] for item in approval["decisions"] if item["decision"] == "approved"}
        approval["status"] = ("rejected" if decision == "rejected" else
                              "approved" if set(approval["required_roles"]) <= approved else "pending")
        if approval["status"] == "approved":
            report["status"] = "reviewed"
        elif approval["status"] == "rejected":
            report["status"] = "investigating"
        return self._save_update(report, "review_decision", actor_id,
                                 {"role": role, "decision": decision, "note": note})

    def update_task(self, incident_id: str, task_id: str, *, actor_id: str,
                    roles: tuple[str, ...], status: str, note: str = "") -> dict:
        if not set(roles) & {"qa", "sponsor_qa", "supervisor", "msat", "operator"}:
            raise PermissionError("operations or quality role required")
        if status not in {"open", "in_progress", "completed", "cancelled"}:
            raise ValueError("invalid task status")
        report = self.get(incident_id)
        task = next((item for item in report["tasks"] if item["task_id"] == task_id), None)
        if task is None:
            raise KeyError(task_id)
        task["status"] = status
        task["updated_by"] = actor_id
        task["note"] = note
        return self._save_update(report, "task_update", actor_id,
                                 {"task_id": task_id, "status": status, "note": note})

    def record_outcome(self, incident_id: str, *, actor_id: str,
                       roles: tuple[str, ...], finding: str,
                       evidence_ids: list[str], note: str = "") -> dict:
        if not set(roles) & {"qa", "sponsor_qa"}:
            raise PermissionError("QA role required to record an investigation outcome")
        if not finding.strip() or not evidence_ids:
            raise ValueError("outcome needs a finding and source evidence")
        report = self.get(incident_id)
        self._visible(evidence_ids, _now())
        outcome = {"finding": finding, "evidence_ids": list(dict.fromkeys(evidence_ids)),
                   "note": note, "recorded_by": actor_id, "recorded_at": _now(),
                   "human_recorded": True}
        report["outcomes"].append(outcome)
        if self.blackboards:
            blackboard = self.blackboards.load(incident_id)
            if blackboard is None:
                raise KeyError("matching Blackboard is unavailable")
            blackboard.outcomes.append(outcome)
            self.blackboards.save(blackboard)
        return self._save_update(report, "outcome", actor_id, outcome)

    def fulfill_evidence_request(self, incident_id: str, request_id: str, *,
                                 actor_id: str, roles: tuple[str, ...],
                                 evidence_ids: list[str], note: str = "") -> dict:
        if not set(roles) & {"qa", "sponsor_qa", "msat", "supervisor"}:
            raise PermissionError("quality or responsible operations role required")
        if not evidence_ids:
            raise ValueError("source evidence is required")
        report = self.get(incident_id)
        request = next((item for item in report["evidence_requests"]
                        if item.get("request_id") == request_id), None)
        if request is None:
            raise KeyError(request_id)
        if request.get("status") not in {None, "pending"}:
            raise ValueError("evidence request is already resolved")
        self._visible(evidence_ids, _now())
        request["status"] = "fulfilled"
        request["answer"] = note
        request["evidence_ids"] = list(dict.fromkeys(evidence_ids))
        request["fulfilled_by"] = actor_id
        request["fulfilled_at"] = _now()
        for branch in report["decision_branches"]:
            branch["pending_dependencies"] = [item for item in branch.get("pending_dependencies", [])
                                               if item != request_id]
        if self.blackboards:
            blackboard = self.blackboards.load(incident_id)
            if blackboard is None:
                raise KeyError("matching Blackboard is unavailable")
            blackboard_request = next((item for item in blackboard.pending_evidence
                                       if item.get("request_id") == request_id), None)
            if blackboard_request is None:
                raise KeyError("matching Blackboard evidence request is unavailable")
            blackboard_request.update({key: request[key] for key in
                                       ("status", "answer", "evidence_ids", "fulfilled_by", "fulfilled_at")})
            blackboard.evidence_ids = list(dict.fromkeys(blackboard.evidence_ids + evidence_ids))
            for branch in blackboard.decision_branches:
                branch["pending_dependencies"] = [item for item in branch.get("pending_dependencies", [])
                                                   if item != request_id]
            self.blackboards.save(blackboard)
        return self._save_update(report, "evidence_fulfilled", actor_id,
                                 {"request_id": request_id, "evidence_ids": evidence_ids, "note": note})

    def close(self, incident_id: str, *, actor_id: str, roles: tuple[str, ...],
              note: str = "") -> dict:
        if not set(roles) & {"qa", "sponsor_qa"}:
            raise PermissionError("QA role required to close an investigation")
        report = self.get(incident_id)
        if report["status"] == "closed":
            raise ValueError("investigation is already closed")
        if report["approval"]["status"] not in {"approved", "not_requested"}:
            raise ValueError("investigation review is still pending")
        if not report["outcomes"]:
            raise ValueError("a human-recorded outcome is required")
        if any(item["status"] not in {"completed", "cancelled"} for item in report["tasks"]):
            raise ValueError("investigation tasks remain open")
        if any(item.get("status", "pending") == "pending" for item in report["evidence_requests"]):
            raise ValueError("evidence requests remain pending")
        report["status"] = "closed"
        report["closed_by"] = actor_id
        report["closed_at"] = _now()
        if self.blackboards:
            blackboard = self.blackboards.load(incident_id)
            if blackboard is None:
                raise KeyError("matching Blackboard is unavailable")
            blackboard.status = "closed"
            self.blackboards.save(blackboard)
        return self._save_update(report, "closed", actor_id, {"note": note})
