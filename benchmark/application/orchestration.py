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
        "campaign-recovery", "Campaign Recovery", "operations",
        ("campaign", "recovery", "schedule_disruption"), ("anomaly",),
        "Compares constrained recovery plans and stages schedule changes for review.",
    ),
    AgentDefinition(
        "qc-flow", "QC Flow", "quality_control",
        ("qc", "lab", "testing", "sample"), ("spc", "anomaly"),
        "Coordinates sample, testing, capacity, and release dependencies across QC.",
    ),
    AgentDefinition(
        "production-maintenance", "Maintenance Coordination", "operations",
        ("maintenance", "production", "equipment"), ("anomaly",),
        "Connects asset condition to batch risk and prepares bounded maintenance work.",
    ),
    AgentDefinition(
        "material-inventory", "Material & Inventory", "supply",
        ("material", "inventory", "supply", "shortage"), ("anomaly",),
        "Traces material readiness, constraints, alternates, and affected campaigns.",
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
    AgentDefinition(
        "capacity-planning", "Capacity Planning", "planning",
        ("capacity", "planning", "schedule"), ("spc", "anomaly"),
        "Evaluates constrained capacity options across equipment, people, materials, and QC.",
    ),
)


class CaseOrchestrator:
    """Demo case router; Manufacturing OS investigations use Prime SDK separately."""

    def __init__(
        self,
        tools: ToolGateway,
    ) -> None:
        self.tools = tools
        self._runs: dict[str, dict[str, Any]] = {}
        self._case_state: dict[tuple[str, str], dict[str, Any]] = {}
        self._lock = threading.RLock()

    def catalog(self) -> list[dict[str, Any]]:
        values = []
        for definition in AGENTS:
            value = asdict(definition)
            value["harness"] = "demo_case_router"
            values.append(value)
        return values

    def start(self, case_id: str, context: dict[str, Any]) -> dict[str, Any]:
        case = context.get("case", {})
        case_type = str(case.get("case_type", "deviation")).lower()
        agent = self._agent_for(case_type)
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
                "agent_id": agent.agent_id, "harness": "demo_case_router",
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
        return dict(local) if local else None

    def latest(self, case_id: str, tenant_id: str | None = None) -> dict[str, Any] | None:
        values: list[dict[str, Any]] = []
        with self._lock:
            values.extend(
                run for run in self._runs.values()
                if run["case_id"] == case_id and (tenant_id is None or run["tenant_id"] == tenant_id)
            )
        return dict(max(values, key=lambda value: value["created_at"])) if values else None

    def case_state(self, case_id: str, tenant_id: str | None = None) -> dict[str, Any] | None:
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

    def runtime_status(self) -> dict[str, Any]:
        return {"mode": "demo_case_router", "configured": True, "provider_id": None}
