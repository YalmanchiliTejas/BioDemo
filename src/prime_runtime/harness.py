"""Prime SDK host adapter with a scoped manufacturing evidence bridge."""

from __future__ import annotations

import fcntl
import json
import os
import shlex
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any

from src.manufacturing_data import ManufacturingStore
from src.state import BlackboardStore
from src.workflows import ManufacturingInvestigationWorkflow

from .bridge import ManufacturingBridge


class PrimeManufacturingHarness:
    def __init__(self, *, command: list[str], store: ManufacturingStore,
                 blackboards: BlackboardStore, workflow: ManufacturingInvestigationWorkflow,
                 scope: str, runtime_root: Path, model: str | None = None,
                 timeout_seconds: float = 900) -> None:
        if not command:
            raise ValueError("Prime SDK host command is required")
        self.command, self.store, self.blackboards, self.workflow = command, store, blackboards, workflow
        self.scope, self.runtime_root, self.model = scope, Path(runtime_root), model
        self.timeout_seconds = timeout_seconds
        self.bundle = Path(os.getenv("PRIME_AGENT_BUNDLE_ROOT", Path(__file__).resolve().parents[3] / "prime-agent-bio"))
        self.skill_path = Path(__file__).resolve().parents[2] / "prime_skills" / "manufacturing_os" / "SKILL.md"
        self.message_skill_path = self.bundle / "packages" / "coding-agent" / "skills" / "agent-message" / "SKILL.md"
        self.system_path = Path(__file__).with_name("system_prompt.md")
        if not self.skill_path.is_file() or not self.message_skill_path.is_file():
            raise RuntimeError("Prime manufacturing and agent-message skills are required")

    @classmethod
    def from_env(cls, *, store: ManufacturingStore, blackboards: BlackboardStore,
                 workflow: ManufacturingInvestigationWorkflow, scope: str) -> "PrimeManufacturingHarness":
        bundle = Path(os.getenv("PRIME_AGENT_BUNDLE_ROOT", Path(__file__).resolve().parents[3] / "prime-agent-bio"))
        configured = os.getenv("BIODEMO_PRIME_SDK_COMMAND")
        package = bundle / "packages" / "coding-agent" / "dist" / "index.js"
        runner = Path(__file__).with_name("sdk_runner.mjs")
        node = shutil.which("node")
        command = shlex.split(configured) if configured else ([node, str(runner)] if node and package.is_file() else [])
        if not command:
            raise RuntimeError("Prime SDK is unavailable; set PRIME_AGENT_BUNDLE_ROOT or BIODEMO_PRIME_SDK_COMMAND")
        return cls(command=command, store=store, blackboards=blackboards,
                   workflow=workflow, scope=scope,
                   runtime_root=blackboards.root / "prime-runtime",
                   model=os.getenv("BIODEMO_PRIME_MODEL"),
                   timeout_seconds=float(os.getenv("BIODEMO_PRIME_TIMEOUT", "900")))

    def run(self, *, incident_id: str, problem: str, new_evidence_ids: list[str],
            as_of: str) -> dict[str, Any]:
        if not incident_id or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for char in incident_id):
            raise ValueError("invalid incident id")
        lock_dir = self.runtime_root / "locks"
        lock_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        lock = (lock_dir / f"{incident_id}.lock").open("a+")
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            lock.close()
            raise RuntimeError("a Prime investigation for this incident is already running") from exc
        bridge: ManufacturingBridge | None = None
        bridge_config: Path | None = None
        try:
            bridge = ManufacturingBridge(
                store=self.store, blackboards=self.blackboards, workflow=self.workflow,
                scope=self.scope, incident_id=incident_id, objective=problem,
                as_of=as_of, seed_ids=new_evidence_ids,
            ).start()
            workdir = self.runtime_root / "workspaces" / incident_id
            session_dir = self.runtime_root / "sessions" / incident_id
            log_dir = self.runtime_root / "logs"
            for path in (workdir, session_dir, log_dir):
                path.mkdir(parents=True, exist_ok=True, mode=0o700)
            bridge_config = self.runtime_root / "bridge-configs" / f"{incident_id}.json"
            bridge_config.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            bridge_config.write_text(json.dumps({"url": bridge.url, "token": bridge.token}) + "\n", encoding="utf-8")
            bridge_config.chmod(0o600)
            marker = self.runtime_root / "sessions" / f"{incident_id}.json"
            previous = json.loads(marker.read_text()) if marker.is_file() else {}
            prior_file = previous.get("session_file")
            if prior_file and not Path(prior_file).is_file():
                raise RuntimeError("saved Prime SDK session file is missing")
            prompt = (
                f"Investigate incident {incident_id} as of {as_of}. Objective: {problem}. "
                "Load the manufacturing_os skill. Call context(), investigate with the scoped tools, "
                "use native rlm.spawn for useful independent questions, then call submit_report(). "
                "Report unresolved evidence honestly. Do not claim completion unless submit_report succeeds."
            )
            request = {
                "bundle_root": str(self.bundle), "cwd": str(workdir),
                "session_dir": str(session_dir), "session_file": prior_file,
                "skill_paths": [str(self.skill_path), str(self.message_skill_path)],
                "system_prompt": self.system_path.read_text(encoding="utf-8"),
                "model": self.model, "prompt": prompt,
            }
            environment = os.environ.copy()
            environment.pop("BIODEMO_MANUFACTURING_STORE", None)
            environment.pop("BIODEMO_MANUFACTURING_SCOPE", None)
            environment["BIODEMO_PRIME_BRIDGE_CONFIG"] = str(bridge_config)
            process = subprocess.run(self.command, cwd=workdir, env=environment,
                                     input=json.dumps(request), text=True, capture_output=True,
                                     timeout=self.timeout_seconds, check=False)
            run_tag = uuid.uuid4().hex[:12]
            log_path = log_dir / f"{incident_id}-{run_tag}.jsonl"
            log_path.write_text(process.stdout, encoding="utf-8")
            log_path.chmod(0o600)
            error_path = log_dir / f"{incident_id}-{run_tag}.stderr"
            error_path.write_text(process.stderr, encoding="utf-8")
            error_path.chmod(0o600)
            session_id = session_file = None
            usage = {"model_calls": 0, "input_tokens": 0, "output_tokens": 0,
                     "cached_input_tokens": 0, "inference_cost_usd": 0.0}
            for line in process.stdout.splitlines():
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("type") == "session" and event.get("id"):
                    session_id, session_file = str(event["id"]), event.get("file")
                if event.get("type") == "message_end" and event.get("message", {}).get("role") == "assistant":
                    tokens = event["message"].get("usage")
                    if isinstance(tokens, dict):
                        usage["model_calls"] += 1
                        usage["input_tokens"] += int(tokens.get("input", 0))
                        usage["output_tokens"] += int(tokens.get("output", 0))
                        usage["cached_input_tokens"] += int(tokens.get("cacheRead", 0))
                        usage["inference_cost_usd"] += float((tokens.get("cost") or {}).get("total", 0.0))
            if process.returncode != 0:
                raise RuntimeError(f"Prime SDK host exited with code {process.returncode}; inspect the private run log")
            if bridge.result is None:
                raise RuntimeError("Prime Agent finished without submitting a validated investigation report")
            if not session_id or not session_file or not Path(session_file).is_file():
                raise RuntimeError("Prime SDK did not persist a resumable session")
            marker.write_text(json.dumps({"session_id": session_id, "session_file": session_file}) + "\n", encoding="utf-8")
            marker.chmod(0o600)
            bridge.result["rollout_metrics"].update(usage)
            bridge.result["rollout_metrics"].update({
                "prime_session_id": session_id, "prime_log": str(log_path),
                "prime_transport": "sdk", "usage_scope": "root_sdk_session_only; child usage not included",
            })
            return bridge.result
        finally:
            if bridge is not None:
                bridge.close()
            if bridge_config is not None:
                bridge_config.unlink(missing_ok=True)
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            lock.close()
