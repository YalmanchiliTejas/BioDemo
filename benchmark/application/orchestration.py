from __future__ import annotations

import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from .intelligence import ToolGateway


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class AgentDefinition:
    agent_id: str
    name: str
    domain: str
    case_types: tuple[str, ...]
    jobs: tuple[str, ...]
    description: str


AGENTS = (
    AgentDefinition(
        "production-maintenance", "Production & Maintenance", "operations",
        ("maintenance", "production", "equipment"), ("anomaly",),
        "Triages equipment and production signals and prepares bounded human work.",
    ),
    AgentDefinition(
        "quality-deviation", "Quality, Deviation, RCA & OOS", "quality",
        ("deviation", "oos", "rca"), ("spc", "anomaly"),
        "Assembles evidence, challenges hypotheses, and stops at quality gates.",
    ),
    AgentDefinition(
        "process-science", "Process Science & Experiment Design", "science",
        ("science", "formulation", "experiment"), ("spc", "doe"),
        "Analyzes process behavior and creates reviewable experiment designs.",
    ),
    AgentDefinition(
        "capa-release", "CAPA, Sponsor & Release Evidence", "cross_functional",
        ("capa", "release", "sponsor"), ("spc",),
        "Checks evidence completeness and stages CAPA or release review packages.",
    ),
)


class CaseOrchestrator:
    """Routes cases to a specialist while preserving the Prime deviation harness."""

    def __init__(self, tools: ToolGateway, deviation_harness: Any | None = None) -> None:
        self.tools = tools
        self.deviation_harness = deviation_harness
        self._runs: dict[str, dict[str, Any]] = {}
        self._case_state: dict[tuple[str, str], dict[str, Any]] = {}
        self._lock = threading.RLock()

    def catalog(self) -> list[dict[str, Any]]:
        values = []
        for definition in AGENTS:
            value = asdict(definition)
            value["harness"] = (
                "prime_agent" if definition.agent_id == "quality-deviation" and self.deviation_harness
                else "deterministic_runtime"
            )
            values.append(value)
        return values

    def start(self, case_id: str, context: dict[str, Any]) -> dict[str, Any]:
        case = context.get("case", {})
        case_type = str(case.get("case_type", "deviation")).lower()
        agent = self._agent_for(case_type)
        if agent.agent_id == "quality-deviation" and self.deviation_harness is not None:
            run = self.deviation_harness.start(case_id, context)
            return {**run, "agent_id": agent.agent_id, "harness": "prime_agent"}
        tenant_id = str(context.get("identity", {}).get("tenant_id", "default"))
        with self._lock:
            active = next((
                run for run in self._runs.values()
                if run["case_id"] == case_id and run["tenant_id"] == tenant_id
                and run["status"] in {"queued", "running"}
            ), None)
            if active:
                return dict(active)
            run_id = f"run-{uuid.uuid4().hex[:16]}"
            evidence_count = len(context.get("digital_thread", {}).get("events", [])) + len(
                context.get("digital_thread", {}).get("documents", [])
            )
            summary = (
                f"{agent.name} assembled {evidence_count} authorized evidence records. "
                "Findings are staged for human review; no regulated action was executed."
            )
            run = {
                "run_id": run_id, "case_id": case_id, "tenant_id": tenant_id,
                "agent_id": agent.agent_id, "harness": "deterministic_runtime",
                "status": "completed", "summary": summary, "error": None,
                "created_at": _now(), "started_at": _now(), "completed_at": _now(),
                "session_id": None,
            }
            state = {
                "case_id": case_id, "agent_id": agent.agent_id,
                "stage": "human_review", "evidence_count": evidence_count,
                "jobs": list(agent.jobs), "required_human_action": "Review the assembled evidence and assign follow-up tasks.",
                "updated_at": _now(),
            }
            self._runs[run_id] = run
            self._case_state[(tenant_id, case_id)] = state
            return dict(run)

    def get(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            local = self._runs.get(run_id)
        if local:
            return dict(local)
        if self.deviation_harness:
            run = self.deviation_harness.get(run_id)
            if run:
                return {**run, "agent_id": "quality-deviation", "harness": "prime_agent"}
        return None

    def latest(self, case_id: str, tenant_id: str | None = None) -> dict[str, Any] | None:
        values: list[dict[str, Any]] = []
        with self._lock:
            values.extend(
                run for run in self._runs.values()
                if run["case_id"] == case_id and (tenant_id is None or run["tenant_id"] == tenant_id)
            )
        if self.deviation_harness:
            external = self.deviation_harness.latest(case_id, tenant_id)
            if external:
                values.append({**external, "agent_id": "quality-deviation", "harness": "prime_agent"})
        return dict(max(values, key=lambda value: value["created_at"])) if values else None

    def case_state(self, case_id: str, tenant_id: str | None = None) -> dict[str, Any] | None:
        if self.deviation_harness:
            external = self.deviation_harness.case_state(case_id, tenant_id)
            if external:
                return external
        with self._lock:
            matches = [
                value for (tenant, candidate), value in self._case_state.items()
                if candidate == case_id and (tenant_id is None or tenant == tenant_id)
            ]
        return dict(matches[0]) if len(matches) == 1 else None

    @staticmethod
    def _agent_for(case_type: str) -> AgentDefinition:
        return next(
            (agent for agent in AGENTS if case_type in agent.case_types),
            next(agent for agent in AGENTS if agent.agent_id == "quality-deviation"),
        )
