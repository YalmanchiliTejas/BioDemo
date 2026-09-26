from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ACTIVE_STATUSES = {"queued", "running"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PrimeAgentDeviationOrchestrator:
    """Starts bounded Prime Agent deviation runs and persists their status."""

    def __init__(
        self,
        command: list[str],
        bundle_root: Path,
        working_directory: Path,
        *,
        api_base_url: str,
    ) -> None:
        self.command = command
        self.bundle_root = bundle_root
        self.working_directory = working_directory
        self.api_base_url = api_base_url.rstrip("/")
        self.runtime_root = working_directory / ".prime"
        self.run_root = self.runtime_root / "deviation-agent-runs"
        self.input_root = self.runtime_root / "deviation-agent-inputs"
        self.case_root = self.runtime_root / "deviation-cases"
        self.skill_path = bundle_root / ".prime" / "agent" / "skills" / "deviation"
        self.system_prompt_path = bundle_root / ".prime" / "agent" / "APPEND_SYSTEM.md"
        self._lock = threading.Lock()
        self._runs: dict[str, dict[str, Any]] = {}
        self._completion_events: dict[str, threading.Event] = {}
        self._load_runs()

    @classmethod
    def from_env(cls) -> PrimeAgentDeviationOrchestrator | None:
        enabled = os.getenv("PRIME_DEVIATION_AGENT_ENABLED", "true").lower()
        if enabled not in {"1", "true", "yes"}:
            return None
        repository = Path(__file__).resolve().parents[2]
        default_bundle = repository.parent / "prime-agent-bio"
        bundle_root = Path(os.getenv("PRIME_AGENT_BUNDLE_ROOT", default_bundle)).expanduser().resolve()
        configured_command = os.getenv("PRIME_AGENT_COMMAND")
        if configured_command:
            command = shlex.split(configured_command)
        elif (bundle_root / "prime-agent.sh").is_file():
            command = [str(bundle_root / "prime-agent.sh")]
        elif installed := shutil.which("prime-agent"):
            command = [installed]
        else:
            return None
        skill = bundle_root / ".prime" / "agent" / "skills" / "deviation" / "SKILL.md"
        system_prompt = bundle_root / ".prime" / "agent" / "APPEND_SYSTEM.md"
        if not skill.is_file() or not system_prompt.is_file():
            return None
        return cls(
            command,
            bundle_root,
            repository,
            api_base_url=os.getenv("BIODEMO_AGENT_API_BASE", "http://127.0.0.1:8000"),
        )

    def start(self, case_id: str, context: dict[str, Any]) -> dict[str, Any]:
        tenant_id = str(context.get("identity", {}).get("tenant_id", "default"))
        with self._lock:
            active = next(
                (
                    run for run in self._runs.values()
                    if run["case_id"] == case_id and run.get("tenant_id", "default") == tenant_id
                    and run["status"] in ACTIVE_STATUSES
                ),
                None,
            )
            if active:
                return dict(active)
            run_id = f"devrun-{uuid.uuid4().hex[:16]}"
            run = {
                "run_id": run_id,
                "case_id": case_id,
                "tenant_id": tenant_id,
                "status": "queued",
                "session_id": None,
                "summary": None,
                "error": None,
                "created_at": _now(),
                "started_at": None,
                "completed_at": None,
            }
            self._runs[run_id] = run
            self._completion_events[run_id] = threading.Event()
            self._write_json(self._run_path(run_id), run)
            self._write_json(self._input_path(run_id), context)
        threading.Thread(
            target=self._execute,
            args=(run_id, context.get("identity", {})),
            name=f"deviation-agent-{case_id}",
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
                and (tenant_id is None or run.get("tenant_id", "default") == tenant_id)
            ]
            if not matches:
                return None
            return dict(max(matches, key=lambda run: run["created_at"]))

    def case_state(self, case_id: str, tenant_id: str | None = None) -> dict[str, Any] | None:
        if not case_id or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for character in case_id):
            raise ValueError("invalid case id")
        path = self.case_root / tenant_id / f"{case_id}.json" if tenant_id else self.case_root / f"{case_id}.json"
        if tenant_id and not path.is_file():
            legacy = self.case_root / f"{case_id}.json"
            path = legacy if legacy.is_file() else path
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def wait(self, run_id: str, timeout_seconds: float = 30) -> dict[str, Any]:
        with self._lock:
            event = self._completion_events.get(run_id)
        if event is None:
            run = self.get(run_id)
            if run is None:
                raise KeyError(run_id)
            return run
        if not event.wait(timeout_seconds):
            raise TimeoutError(f"agent run did not complete within {timeout_seconds} seconds")
        run = self.get(run_id)
        if run is None:
            raise KeyError(run_id)
        return run

    def _execute(self, run_id: str, identity: dict[str, Any]) -> None:
        self._update(run_id, status="running", started_at=_now())
        run = self.get(run_id)
        if run is None:
            return
        prompt = (
            f"Investigate Bio-Demo deviation case {run['case_id']}. "
            f"Read the authorized context snapshot at {self._input_path(run_id)}. "
            "Create or load the matching durable deviation CaseState, record supplied source records "
            "as typed evidence with provenance, and progress only as far as the available evidence "
            "supports. Use the Bio-Demo manufacturing tools for additional context. Spawn only relevant "
            "bounded investigators and run the hypothesis challenger before any root-cause recommendation. "
            "This is a headless application run: record proposals that need human review and stop at the "
            "required gate. Do not approve or execute containment, testing, disposition, CAPA, notification, "
            "closure, or manufacturing changes. End with a concise status, evidence gaps, and required human actions."
        )
        appended_prompt = self.system_prompt_path.read_text(encoding="utf-8")
        arguments = [
            *self.command,
            "--mode", "json",
            "--cwd", str(self.working_directory),
            "--skill", str(self.skill_path),
            "--append-system-prompt", appended_prompt,
            prompt,
        ]
        environment = os.environ.copy()
        environment.update({
            "PRIME_DEVIATION_API_BASE": self.api_base_url,
            "PRIME_DEVIATION_CASE_DIR": str(self.case_root / str(identity.get("tenant_id", "default"))),
            "PRIME_DEVIATION_TENANT_ID": str(identity.get("tenant_id", "demo-cdmo")),
            "PRIME_DEVIATION_ACTOR_ID": "deviation-agent",
            "PRIME_DEVIATION_ROLES": "agent",
            "PRIME_DEVIATION_SITE_IDS": ",".join(identity.get("site_ids", [])),
            "PRIME_DEVIATION_CLEARANCES": ",".join(identity.get("clearances", ["internal"])),
        })
        log_path = self.run_root / f"{run_id}.jsonl"
        last_summary: str | None = None
        try:
            self.run_root.mkdir(parents=True, exist_ok=True)
            (self.case_root / str(identity.get("tenant_id", "default"))).mkdir(parents=True, exist_ok=True)
            with log_path.open("w", encoding="utf-8") as log:
                process = subprocess.Popen(
                    arguments,
                    cwd=self.working_directory,
                    env=environment,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                )
                if process.stdout is None:
                    raise RuntimeError("Prime Agent did not expose an output stream")
                with process.stdout:
                    for line in process.stdout:
                        log.write(line)
                        log.flush()
                        event = self._parse_event(line)
                        if event.get("type") == "session" and event.get("id"):
                            self._update(run_id, session_id=event["id"])
                        summary = self._assistant_text(event)
                        if summary:
                            last_summary = summary
                return_code = process.wait()
            if return_code == 0:
                self._update(
                    run_id,
                    status="completed",
                    summary=last_summary,
                    completed_at=_now(),
                )
            else:
                self._update(
                    run_id,
                    status="failed",
                    error=f"Prime Agent exited with code {return_code}",
                    summary=last_summary,
                    completed_at=_now(),
                )
        except Exception as exc:
            self._update(
                run_id,
                status="failed",
                error=f"{type(exc).__name__}: {exc}",
                completed_at=_now(),
            )
        finally:
            with self._lock:
                event = self._completion_events.get(run_id)
            if event is not None:
                event.set()

    @staticmethod
    def _parse_event(line: str) -> dict[str, Any]:
        try:
            value = json.loads(line)
            return value if isinstance(value, dict) else {}
        except json.JSONDecodeError:
            return {}

    @staticmethod
    def _assistant_text(event: dict[str, Any]) -> str | None:
        if event.get("type") != "message_end":
            return None
        message = event.get("message", {})
        if message.get("role") != "assistant":
            return None
        content = message.get("content", [])
        text = "".join(
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        ).strip()
        return text or None

    def _load_runs(self) -> None:
        if not self.run_root.is_dir():
            return
        for path in self.run_root.glob("*.json"):
            try:
                run = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if run.get("status") in ACTIVE_STATUSES:
                run["status"] = "interrupted"
                run["error"] = "Application restarted while the agent run was active"
                run["completed_at"] = _now()
                self._write_json(path, run)
            if run.get("run_id"):
                self._runs[run["run_id"]] = run

    def _update(self, run_id: str, **changes: Any) -> None:
        with self._lock:
            run = self._runs[run_id]
            run.update(changes)
            self._write_json(self._run_path(run_id), run)

    def _run_path(self, run_id: str) -> Path:
        return self.run_root / f"{run_id}.json"

    def _input_path(self, run_id: str) -> Path:
        return self.input_root / f"{run_id}.json"

    @staticmethod
    def _write_json(path: Path, value: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(f"{path.suffix}.{os.getpid()}.tmp")
        temporary.write_text(
            json.dumps(value, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
