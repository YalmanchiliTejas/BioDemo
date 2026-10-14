"""Per-run, time-scoped HTTP bridge for a Prime Agent Python skill."""

from __future__ import annotations

import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from src.data.temporal_store import parse_time
from src.manufacturing_data import ManufacturingStore, ManufacturingTools
from src.manufacturing_data.session import ManufacturingSession
from src.state import BlackboardStore, CausalHypothesisGraph, DecisionGraph
from src.workflows import ManufacturingInvestigationWorkflow
from src.workflows.proposals import ProposalContext, create_investigation_task, request_new_evidence


class ManufacturingBridge:
    """The skill can only call the ten read tools and submit a validated report."""

    def __init__(self, *, store: ManufacturingStore, blackboards: BlackboardStore,
                 workflow: ManufacturingInvestigationWorkflow, scope: str,
                 incident_id: str, objective: str, as_of: str,
                 seed_ids: list[str], max_tool_calls: int = 48) -> None:
        if not incident_id or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for char in incident_id):
            raise ValueError("invalid incident id")
        parse_time(as_of)
        self.store, self.blackboards, self.workflow = store, blackboards, workflow
        self.scope, self.incident_id, self.objective, self.as_of = scope, incident_id, objective, as_of
        self.session = ManufacturingSession(store, as_of=as_of, scopes=(scope,))
        self.tools = ManufacturingTools(store, as_of=as_of, scopes=(scope,))
        self.seed_ids = list(dict.fromkeys(map(str, seed_ids)))
        if len(self.session.get(self.seed_ids)) != len(self.seed_ids):
            raise ValueError("seed evidence is unavailable at this scope and timestamp")
        self.board = blackboards.load_or_create(incident_id)
        if len(self.session.get(self.board.evidence_ids)) != len(set(self.board.evidence_ids)):
            raise ValueError("stored incident evidence is unavailable at this scope and timestamp")
        if any(parse_time(str(item["as_of"])) > parse_time(as_of)
               for item in self.board.rollout_history if item.get("as_of")):
            raise ValueError("stored incident state contains future information")
        if any(parse_time(str(item["recorded_at"])) > parse_time(as_of)
               for item in self.board.outcomes if item.get("recorded_at")):
            raise ValueError("stored incident outcome contains future information")
        self.seen_ids = set(self.seed_ids) | set(self.board.evidence_ids)
        self.max_tool_calls = max_tool_calls
        self.tool_calls = 0
        self.result: dict[str, Any] | None = None
        self._lock = threading.RLock()
        self.token = secrets.token_urlsafe(32)
        self.server: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None

    def context(self) -> dict[str, Any]:
        return {"incident_id": self.incident_id, "objective": self.objective,
                "as_of": self.as_of, "scope": self.scope,
                "seed_evidence": self.session.get(self.seed_ids),
                "blackboard": self.board.to_dict(),
                "tool_names": list(self.tools.handlers()),
                "remaining_tool_calls": self.max_tool_calls - self.tool_calls}

    def tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            handlers = self.tools.handlers()
            if name not in handlers:
                raise ValueError("tool is not an allowed manufacturing data tool")
            if self.tool_calls >= self.max_tool_calls:
                raise RuntimeError("Prime manufacturing tool budget exceeded")
            self.tool_calls += 1
            # The model cannot widen its historical cutoff or access scope.
            bounded = {**arguments, "as_of": self.as_of, "scopes": [self.scope]}
            result = handlers[name](**bounded)
            visible = self.session.visible_evidence_ids()
            ids = {str(value) for value in result.get("evidence_ids", [])}
            if not ids <= visible:
                raise ValueError("tool returned unavailable evidence")
            self.seen_ids.update(ids)
            return result

    def submit_report(self, report: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            if self.result is not None:
                raise ValueError("this Prime run already submitted a report")
            if not isinstance(report, dict):
                raise ValueError("report must be an object")
            for key in ("evidence_ids", "hypotheses", "findings", "resolved_questions",
                        "open_questions", "evidence_requests", "tasks", "decision_branches"):
                if not isinstance(report.get(key, []), list):
                    raise ValueError(f"{key} must be a list")
            if not str(report.get("assessment", "")).strip():
                raise ValueError("assessment is required")
            cited = list(dict.fromkeys(map(str, report.get("evidence_ids", []))))
            if not cited or not set(cited) <= self.seen_ids:
                raise ValueError("report cites evidence not retrieved in this run")
            if len(self.session.get(cited)) != len(cited):
                raise ValueError("report cites unavailable evidence")
            board = type(self.board).from_dict(self.board.to_dict())
            all_ids = list(dict.fromkeys(board.evidence_ids + cited))
            valid = set(all_ids)
            graph = CausalHypothesisGraph()
            for item in report.get("hypotheses", [])[:12]:
                if not isinstance(item, dict):
                    raise ValueError("hypotheses must be objects")
                if not str(item.get("hypothesis_id", "")).strip() or not str(item.get("statement", "")).strip():
                    raise ValueError("hypothesis id and statement are required")
                links = set(map(str, item.get("supporting_evidence_ids", []))) | set(map(str, item.get("contradicting_evidence_ids", [])))
                if not links <= valid:
                    raise ValueError("hypothesis cites evidence not retrieved in this run")
                graph.upsert(item, valid)
            errors = graph.validate(valid)
            if errors:
                raise ValueError("invalid causal graph: " + "; ".join(errors))
            board.causal_hypotheses = graph.to_list()
            board.evidence_ids = all_ids
            board.open_questions = [str(value) for value in report.get("open_questions", [])]
            for item in report.get("findings", [])[:100]:
                if not isinstance(item, dict):
                    raise ValueError("findings must be objects")
                item_ids = list(dict.fromkeys(map(str, item.get("evidence_ids", []))))
                if not set(item_ids) <= valid:
                    raise ValueError("finding cites evidence not retrieved in this run")
                finding = {"statement": str(item.get("statement", "")),
                           "evidence_ids": item_ids,
                           "uncertainties": [str(value) for value in item.get("uncertainties", [])]}
                if finding not in board.completed_investigations:
                    board.completed_investigations.append(finding)
            for item in report.get("resolved_questions", [])[:100]:
                if not isinstance(item, dict):
                    raise ValueError("resolved questions must be objects")
                item_ids = list(dict.fromkeys(map(str, item.get("evidence_ids", []))))
                if not set(item_ids) <= valid:
                    raise ValueError("resolved question cites evidence not retrieved in this run")
                resolved = {"question": str(item.get("question", "")),
                            "finding": str(item.get("finding", "")), "evidence_ids": item_ids}
                if resolved not in board.resolved_questions:
                    board.resolved_questions.append(resolved)
            severity = str(report.get("severity", "LOW")).upper()
            if severity not in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}:
                raise ValueError("invalid severity")
            board.severity = severity
            rows = self.session.get(all_ids)
            batches = sorted({str(row["batch_id"]) for row in rows if row.get("batch_id")})
            equipment = sorted({str(row["equipment_id"]) for row in rows if row.get("equipment_id")})
            board.scope = {"type": "multi_batch" if len(batches) > 1 else "single_batch" if batches else "undetermined",
                           "batch_ids": batches, "equipment_ids": equipment}
            context = ProposalContext(self.session, board)
            for item in report.get("evidence_requests", [])[:6]:
                if not isinstance(item, dict):
                    raise ValueError("evidence requests must be objects")
                request_new_evidence(context, item)
            for item in report.get("tasks", [])[:6]:
                if not isinstance(item, dict):
                    raise ValueError("tasks must be objects")
                task_ids = set(map(str, item.get("evidence_ids", [])))
                if not task_ids <= valid:
                    raise ValueError("task cites evidence not retrieved in this run")
                create_investigation_task(context, item)
            decisions = DecisionGraph()
            for item in report.get("decision_branches", [])[:12]:
                if not isinstance(item, dict):
                    raise ValueError("decision branches must be objects")
                if not str(item.get("decision_id", "")).strip() or not str(item.get("condition", "")).strip():
                    raise ValueError("decision id and condition are required")
                decisions.upsert(item)
            errors = decisions.validate({item["request_id"] for item in board.pending_evidence})
            if errors:
                raise ValueError("invalid decision graph: " + "; ".join(errors))
            board.decision_branches = decisions.to_list()
            board.status = "suspended_pending_evidence" if board.pending_evidence else "awaiting_human_review"
            output = {
                "assessment": str(report.get("assessment", "")), "severity": severity,
                "scope": board.scope, "causal_hypotheses": board.causal_hypotheses,
                "evidence_ids": all_ids, "related_batches": batches,
                "related_equipment": equipment, "resolved_questions": board.resolved_questions,
                "open_questions": board.open_questions, "actions_now": board.recommended_actions,
                "pending_evidence_requests": board.pending_evidence,
                "decision_branches": board.decision_branches, "teams": board.teams_involved,
                "continue_investigation": bool(board.open_questions or board.pending_evidence),
                "rollout_metrics": {"provider_id": "prime-agent", "tool_calls": self.tool_calls,
                                    "model_calls": None, "rlm_recursion_depth": None,
                                    "subtasks_spawned": None},
            }
            board.rollout_history.append({"as_of": self.as_of, "mode": "prime-agent",
                                          "new_evidence_ids": self.seed_ids,
                                          "metrics": output["rollout_metrics"], "status": board.status})
            self.blackboards.save(board)
            output["workflow"] = self.workflow.record_rollout(
                self.incident_id, self.as_of, self.objective, output)
            self.board, self.result = board, output
            return output

    def start(self) -> "ManufacturingBridge":
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                if not secrets.compare_digest(self.headers.get("Authorization", ""), f"Bearer {bridge.token}"):
                    self.send_error(403)
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if length > 1_000_000:
                        raise ValueError("request too large")
                    value = json.loads(self.rfile.read(length))
                    if self.path == "/context":
                        result = bridge.context()
                    elif self.path == "/tool":
                        result = bridge.tool(str(value["name"]), dict(value.get("arguments", {})))
                    elif self.path == "/report":
                        result = bridge.submit_report(value)
                    else:
                        self.send_error(404)
                        return
                    body = json.dumps(result, default=str).encode()
                    self.send_response(200)
                except (ValueError, KeyError, TypeError, RuntimeError, PermissionError) as exc:
                    body = json.dumps({"error": f"{type(exc).__name__}: {exc}"}).encode()
                    self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    @property
    def url(self) -> str:
        if self.server is None:
            raise RuntimeError("bridge has not started")
        return f"http://127.0.0.1:{self.server.server_port}"

    def close(self) -> None:
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
        if self.thread is not None:
            self.thread.join(timeout=2)
            self.thread = None
