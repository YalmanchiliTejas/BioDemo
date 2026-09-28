from __future__ import annotations

import json
import os
import shlex
import subprocess
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from urllib import request

from .intelligence import ToolGateway


ACTIVE_STATUSES = {"queued", "running"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ReasoningProvider(Protocol):
    provider_id: str

    def complete(self, request: dict[str, Any]) -> dict[str, Any]: ...


class CommandReasoningProvider:
    """Runs a user-supplied reasoning process with JSON over stdin/stdout."""

    provider_id = "command.reasoning"

    def __init__(self, command: list[str], *, timeout_seconds: float = 180) -> None:
        if not command:
            raise ValueError("reasoning command cannot be empty")
        self.command = command
        self.timeout_seconds = timeout_seconds

    def complete(self, value: dict[str, Any]) -> dict[str, Any]:
        process = subprocess.run(
            self.command,
            input=json.dumps(value, default=str),
            text=True,
            capture_output=True,
            timeout=self.timeout_seconds,
            check=False,
        )
        if process.returncode != 0:
            detail = process.stderr.strip() or f"exit code {process.returncode}"
            raise RuntimeError(f"reasoning command failed: {detail}")
        try:
            result = json.loads(process.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError("reasoning command did not return a JSON object") from exc
        if not isinstance(result, dict):
            raise RuntimeError("reasoning command response must be a JSON object")
        return result


class HttpReasoningProvider:
    """Calls a provider-neutral JSON reasoning endpoint."""

    provider_id = "http.reasoning"

    def __init__(self, url: str, *, token: str | None = None, timeout_seconds: float = 180) -> None:
        self.url = url
        self.token = token
        self.timeout_seconds = timeout_seconds

    def complete(self, value: dict[str, Any]) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        outbound = request.Request(
            self.url,
            data=json.dumps(value, default=str).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with request.urlopen(outbound, timeout=self.timeout_seconds) as response:
            result = json.loads(response.read().decode("utf-8"))
        if not isinstance(result, dict):
            raise RuntimeError("reasoning endpoint response must be a JSON object")
        return result


class PrimeJsonReasoningProvider:
    """Uses Prime Agent as a no-tool JSON reasoning process for any specialist."""

    provider_id = "prime.dynamic.reasoning"

    def __init__(self, command: list[str], working_directory: Path, *, timeout_seconds: float = 300) -> None:
        self.command = command
        self.working_directory = working_directory
        self.timeout_seconds = timeout_seconds

    def complete(self, value: dict[str, Any]) -> dict[str, Any]:
        system = (
            "You are the bounded reasoning core of a pharmaceutical manufacturing agent. "
            "You have no execution authority and no external tools. Analyze only the supplied JSON. "
            "Return exactly one JSON object conforming to output_schema, with no markdown fences or commentary."
        )
        prompt = "Produce the next structured agent decision for this request:\n" + json.dumps(value, default=str)
        process = subprocess.run(
            [
                *self.command,
                "--mode", "json",
                "--cwd", str(self.working_directory),
                "--no-tools",
                "--no-skills",
                "--no-extensions",
                "--no-prompt-templates",
                "--no-context-files",
                "--no-session",
                "--system-prompt", system,
                prompt,
            ],
            cwd=self.working_directory,
            text=True,
            capture_output=True,
            timeout=self.timeout_seconds,
            check=False,
        )
        if process.returncode != 0:
            detail = process.stderr.strip() or f"exit code {process.returncode}"
            raise RuntimeError(f"Prime dynamic reasoning failed: {detail}")
        assistant_text: str | None = None
        for line in process.stdout.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") != "message_end" or event.get("message", {}).get("role") != "assistant":
                continue
            assistant_text = "".join(
                part.get("text", "")
                for part in event.get("message", {}).get("content", [])
                if isinstance(part, dict) and part.get("type") == "text"
            ).strip()
        if not assistant_text:
            raise RuntimeError("Prime dynamic reasoning returned no assistant decision")
        if assistant_text.startswith("```"):
            assistant_text = assistant_text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        try:
            result = json.loads(assistant_text)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Prime dynamic reasoning did not return valid decision JSON") from exc
        if not isinstance(result, dict):
            raise RuntimeError("Prime dynamic reasoning decision must be a JSON object")
        return result


def reasoning_provider_from_env(repository: Path | None = None) -> ReasoningProvider | None:
    command = os.getenv("BIODEMO_DYNAMIC_AGENT_COMMAND")
    if command:
        return CommandReasoningProvider(
            shlex.split(command),
            timeout_seconds=float(os.getenv("BIODEMO_DYNAMIC_AGENT_TIMEOUT", "180")),
        )
    url = os.getenv("BIODEMO_DYNAMIC_AGENT_URL")
    if url:
        token = os.getenv("BIODEMO_DYNAMIC_AGENT_TOKEN")
        return HttpReasoningProvider(
            url,
            token=token,
            timeout_seconds=float(os.getenv("BIODEMO_DYNAMIC_AGENT_TIMEOUT", "180")),
        )
    provider = os.getenv("BIODEMO_DYNAMIC_AGENT_PROVIDER", "auto").lower()
    if provider in {"disabled", "none", "off"} or repository is None:
        return None
    bundle_root = Path(os.getenv("PRIME_AGENT_BUNDLE_ROOT", repository.parent / "prime-agent-bio")).expanduser().resolve()
    configured_command = os.getenv("BIODEMO_DYNAMIC_PRIME_COMMAND")
    command = shlex.split(configured_command) if configured_command else [str(bundle_root / "prime-agent.sh")]
    if provider in {"auto", "prime"} and Path(command[0]).is_file():
        return PrimeJsonReasoningProvider(
            command,
            repository,
            timeout_seconds=float(os.getenv("BIODEMO_DYNAMIC_AGENT_TIMEOUT", "300")),
        )
    return None


class DynamicAgentRuntime:
    """Persistent, tool-using reasoning runtime shared by every specialist."""

    def __init__(
        self,
        provider: ReasoningProvider,
        tools: ToolGateway,
        runtime_root: Path,
        *,
        max_tool_rounds: int = 2,
    ) -> None:
        self.provider = provider
        self.tools = tools
        self.runtime_root = runtime_root
        self.run_root = runtime_root / "dynamic-agent-runs"
        self.input_root = runtime_root / "dynamic-agent-inputs"
        self.case_root = runtime_root / "dynamic-agent-cases"
        self.max_tool_rounds = max_tool_rounds
        self._runs: dict[str, dict[str, Any]] = {}
        self._case_state: dict[tuple[str, str], dict[str, Any]] = {}
        self._completion_events: dict[str, threading.Event] = {}
        self._lock = threading.RLock()
        self._load()

    @classmethod
    def from_env(cls, tools: ToolGateway, repository: Path) -> DynamicAgentRuntime | None:
        if os.getenv("BIODEMO_DYNAMIC_AGENTS_ENABLED", "true").lower() not in {"1", "true", "yes"}:
            return None
        provider = reasoning_provider_from_env(repository)
        if provider is None:
            return None
        runtime_root = Path(
            os.getenv("BIODEMO_DYNAMIC_AGENT_STATE", repository / ".prime")
        ).expanduser().resolve()
        return cls(provider, tools, runtime_root)

    def start(
        self, case_id: str, context: dict[str, Any], agent: dict[str, Any]
    ) -> dict[str, Any]:
        tenant_id = str(context.get("identity", {}).get("tenant_id", "default"))
        with self._lock:
            active = next((
                run for run in self._runs.values()
                if run["case_id"] == case_id and run["tenant_id"] == tenant_id
                and run["status"] in ACTIVE_STATUSES
            ), None)
            if active:
                return dict(active)
            run_id = f"dynrun-{uuid.uuid4().hex[:16]}"
            run = {
                "run_id": run_id,
                "case_id": case_id,
                "tenant_id": tenant_id,
                "agent_id": agent["agent_id"],
                "harness": "dynamic_agent_runtime",
                "provider_id": self.provider.provider_id,
                "status": "queued",
                "summary": None,
                "error": None,
                "created_at": _now(),
                "started_at": None,
                "completed_at": None,
                "session_id": run_id,
            }
            self._runs[run_id] = run
            self._completion_events[run_id] = threading.Event()
            self._write_json(self._run_path(run_id), run)
            self._write_json(self._input_path(run_id), {"agent": agent, "context": context})
        threading.Thread(
            target=self._execute,
            args=(run_id, context, agent),
            name=f"dynamic-agent-{case_id}",
            daemon=True,
        ).start()
        return dict(run)

    def get(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            run = self._runs.get(run_id)
            return dict(run) if run else None

    def latest(self, case_id: str, tenant_id: str | None = None) -> dict[str, Any] | None:
        with self._lock:
            matches = [
                run for run in self._runs.values()
                if run["case_id"] == case_id
                and (tenant_id is None or run["tenant_id"] == tenant_id)
            ]
        return dict(max(matches, key=lambda item: item["created_at"])) if matches else None

    def case_state(self, case_id: str, tenant_id: str | None = None) -> dict[str, Any] | None:
        with self._lock:
            matches = [
                state for (tenant, candidate), state in self._case_state.items()
                if candidate == case_id and (tenant_id is None or tenant == tenant_id)
            ]
        return dict(matches[0]) if len(matches) == 1 else None

    def wait(self, run_id: str, timeout_seconds: float = 30) -> dict[str, Any]:
        with self._lock:
            event = self._completion_events.get(run_id)
        if event is not None and not event.wait(timeout_seconds):
            raise TimeoutError(f"dynamic agent run did not complete within {timeout_seconds} seconds")
        run = self.get(run_id)
        if run is None:
            raise KeyError(run_id)
        return run

    def status(self) -> dict[str, Any]:
        return {
            "configured": True,
            "provider_id": self.provider.provider_id,
            "max_tool_rounds": self.max_tool_rounds,
            "active_runs": sum(run["status"] in ACTIVE_STATUSES for run in self._runs.values()),
        }

    def record_outcome(
        self,
        case_id: str,
        tenant_id: str,
        actual_metrics: dict[str, float],
        actor_id: str,
        note: str = "",
    ) -> dict[str, Any]:
        with self._lock:
            state = self._case_state.get((tenant_id, case_id))
            if state is None:
                raise KeyError(f"dynamic agent state not found for {case_id}")
            projected = state.get("predicted_impact", {}).get("metrics", {})
            comparison = {
                name: {
                    "projected": float(projected[name]) if name in projected and isinstance(projected[name], (int, float)) else None,
                    "actual": float(actual),
                    "delta": float(actual) - float(projected[name]) if name in projected and isinstance(projected[name], (int, float)) else None,
                }
                for name, actual in actual_metrics.items()
                if isinstance(actual, (int, float)) and not isinstance(actual, bool)
            }
            outcome = {
                "recorded_at": _now(),
                "recorded_by": actor_id,
                "actual_metrics": {name: value["actual"] for name, value in comparison.items()},
                "projected_vs_actual": comparison,
                "note": note,
            }
            state.setdefault("outcomes", []).append(outcome)
            state["learning_status"] = "outcome_recorded_for_calibration"
            state["updated_at"] = _now()
            self._write_json(self._case_path(tenant_id, case_id), state)
            return dict(outcome)

    def _execute(self, run_id: str, context: dict[str, Any], agent: dict[str, Any]) -> None:
        self._update_run(run_id, status="running", started_at=_now())
        tenant_id = str(context.get("identity", {}).get("tenant_id", "default"))
        tool_results: list[dict[str, Any]] = []
        try:
            decision: dict[str, Any] = {}
            for round_index in range(self.max_tool_rounds + 1):
                raw = self.provider.complete(self._request(agent, context, tool_results, round_index))
                decision = self._normalize_decision(raw)
                requests = decision.pop("tool_requests", [])
                if not requests or round_index >= self.max_tool_rounds:
                    break
                tool_results.extend(self._execute_tools(requests))
            state = {
                "case_id": context.get("case", {}).get("case_id", run_id),
                "tenant_id": tenant_id,
                "agent_id": agent["agent_id"],
                "stage": decision["stage"],
                "status": "awaiting_human_review",
                "summary": decision["summary"],
                "confidence": decision["confidence"],
                "findings": decision["findings"],
                "evidence_gaps": decision["evidence_gaps"],
                "human_tasks": decision["human_tasks"],
                "action_proposals": decision["action_proposals"],
                "predicted_impact": decision["predicted_impact"],
                "tool_results": tool_results,
                "authority_boundary": "recommend_only_human_approval_required",
                "updated_at": _now(),
            }
            with self._lock:
                self._case_state[(tenant_id, str(state["case_id"]))] = state
                self._write_json(self._case_path(tenant_id, str(state["case_id"])), state)
            self._update_run(
                run_id,
                status="completed",
                summary=decision["summary"],
                completed_at=_now(),
            )
        except Exception as exc:
            self._update_run(
                run_id,
                status="failed",
                error=f"{type(exc).__name__}: {exc}",
                completed_at=_now(),
            )
        finally:
            with self._lock:
                event = self._completion_events.get(run_id)
            if event:
                event.set()

    def _request(
        self,
        agent: dict[str, Any],
        context: dict[str, Any],
        tool_results: list[dict[str, Any]],
        round_index: int,
    ) -> dict[str, Any]:
        return {
            "protocol": "biodemo.dynamic-agent.v1",
            "system": (
                "You are a bounded pharmaceutical manufacturing operating agent. "
                "Use only supplied tenant-scoped evidence. Distinguish evidence, inference, and unknowns. "
                "Never approve or execute a regulated action. Return strict JSON matching output_schema."
            ),
            "agent": agent,
            "objective": (
                "Investigate the case, identify material evidence gaps, compare safe next-step options, "
                "estimate operational impact, and prepare human tasks or action proposals for review."
            ),
            "context": context,
            "available_tools": self.tools.status(),
            "tool_results": tool_results,
            "round": round_index,
            "output_schema": {
                "stage": "string",
                "summary": "string",
                "confidence": "number from 0 to 1",
                "findings": [{"statement": "string", "kind": "evidence|inference", "citations": ["string"]}],
                "evidence_gaps": ["string"],
                "human_tasks": [{"title": "string", "assigned_role": "string", "reason": "string"}],
                "action_proposals": [{"operation": "string", "target_id": "string", "reason": "string", "risk": "low|medium|high|critical"}],
                "predicted_impact": {"description": "string", "metrics": {}},
                "tool_requests": [{"tool_name": "spc|anomaly|doe|recovery_plan|scenario|impact", "arguments": {}}],
            },
        }

    def _execute_tools(self, requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for value in requests[:6]:
            name = str(value.get("tool_name", ""))
            arguments = value.get("arguments", {})
            if not isinstance(arguments, dict):
                arguments = {}
            try:
                result = self.tools.execute(name, arguments)
                results.append({"tool_name": name, "status": "ok", "result": result})
            except Exception as exc:
                results.append({"tool_name": name, "status": "error", "error": str(exc)})
        return results

    @staticmethod
    def _normalize_decision(value: dict[str, Any]) -> dict[str, Any]:
        def list_of_dicts(key: str) -> list[dict[str, Any]]:
            raw = value.get(key, [])
            return [dict(item) for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []

        def list_of_strings(key: str) -> list[str]:
            raw = value.get(key, [])
            return [str(item) for item in raw if str(item).strip()] if isinstance(raw, list) else []

        confidence = value.get("confidence", 0.0)
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            confidence = 0.0
        impact = value.get("predicted_impact", {})
        return {
            "stage": str(value.get("stage") or "human_review"),
            "summary": str(value.get("summary") or "Dynamic analysis completed for human review."),
            "confidence": max(0.0, min(1.0, float(confidence))),
            "findings": list_of_dicts("findings"),
            "evidence_gaps": list_of_strings("evidence_gaps"),
            "human_tasks": list_of_dicts("human_tasks"),
            "action_proposals": list_of_dicts("action_proposals"),
            "predicted_impact": dict(impact) if isinstance(impact, dict) else {},
            "tool_requests": list_of_dicts("tool_requests"),
        }

    def _load(self) -> None:
        if self.run_root.is_dir():
            for path in self.run_root.glob("*.json"):
                try:
                    run = json.loads(path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    continue
                if run.get("status") in ACTIVE_STATUSES:
                    run.update(status="interrupted", error="Application restarted during agent run", completed_at=_now())
                    self._write_json(path, run)
                if run.get("run_id"):
                    self._runs[run["run_id"]] = run
        if self.case_root.is_dir():
            for path in self.case_root.glob("*/*.json"):
                try:
                    state = json.loads(path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    continue
                if state.get("tenant_id") and state.get("case_id"):
                    self._case_state[(state["tenant_id"], state["case_id"])] = state

    def _update_run(self, run_id: str, **changes: Any) -> None:
        with self._lock:
            self._runs[run_id].update(changes)
            self._write_json(self._run_path(run_id), self._runs[run_id])

    def _run_path(self, run_id: str) -> Path:
        return self.run_root / f"{run_id}.json"

    def _input_path(self, run_id: str) -> Path:
        return self.input_root / f"{run_id}.json"

    def _case_path(self, tenant_id: str, case_id: str) -> Path:
        safe_tenant = self._safe_identifier(tenant_id)
        safe_case = self._safe_identifier(case_id)
        return self.case_root / safe_tenant / f"{safe_case}.json"

    @staticmethod
    def _safe_identifier(value: str) -> str:
        if not value or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for character in value):
            raise ValueError("invalid persistent state identifier")
        return value

    @staticmethod
    def _write_json(path: Path, value: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(f"{path.suffix}.{os.getpid()}.tmp")
        temporary.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        os.replace(temporary, path)
