"""Prime SDK host adapter with a scoped manufacturing evidence bridge."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from src.manufacturing_data import ManufacturingStore
from src.state import BlackboardStore
from src.workflows import ManufacturingInvestigationWorkflow
from src.paths import DEFAULT_PRIME_BUNDLE

from .bridge import ManufacturingBridge, finalization_reserve

DEFAULT_COMPACTION_TARGET_TOKENS = 128_000


class PrimeManufacturingHarness:
    def __init__(self, *, command: list[str], store: ManufacturingStore,
                 blackboards: BlackboardStore, workflow: ManufacturingInvestigationWorkflow,
                 scope: str, runtime_root: Path, model: str | None = None) -> None:
        if not command:
            raise ValueError("Prime SDK host command is required")
        self.command, self.store, self.blackboards, self.workflow = command, store, blackboards, workflow
        self.scope, self.runtime_root, self.model = scope, Path(runtime_root), model
        self.trace_sink = None
        self.max_tool_calls = 72
        self.execution_policy = {'mode':'adaptive_v1','soft_tool_calls':48}
        self.timeout_seconds = 900
        self.evaluation_mode = False
        # History is summarized above this size; "off" keeps the model's full window.
        target = os.getenv("BIODEMO_COMPACTION_TARGET_TOKENS", str(DEFAULT_COMPACTION_TARGET_TOKENS))
        self.compaction_target_tokens = None if target.strip().lower() == "off" else int(target)
        self.bundle = Path(os.getenv("PRIME_AGENT_BUNDLE_ROOT", DEFAULT_PRIME_BUNDLE))
        self.skill_path = Path(__file__).resolve().parents[2] / "prime_skills" / "manufacturing_os" / "SKILL.md"
        self.message_skill_path = self.bundle / "packages" / "coding-agent" / "skills" / "agent-message" / "SKILL.md"
        self.system_path = Path(__file__).with_name("system_prompt.md")
        if not self.skill_path.is_file() or not self.message_skill_path.is_file():
            raise RuntimeError("Prime manufacturing and agent-message skills are required")

    @classmethod
    def from_env(cls, *, store: ManufacturingStore, blackboards: BlackboardStore,
                 workflow: ManufacturingInvestigationWorkflow, scope: str) -> "PrimeManufacturingHarness":
        bundle = Path(os.getenv("PRIME_AGENT_BUNDLE_ROOT", DEFAULT_PRIME_BUNDLE))
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
                   model=os.getenv("BIODEMO_PRIME_MODEL"))

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
                max_tool_calls=self.max_tool_calls, trace_sink=self.trace_sink,
            ).start()
            bridge.configure_execution(self.execution_policy)
            workdir = self.runtime_root / "workspaces" / incident_id
            session_dir = self.runtime_root / "sessions" / incident_id
            log_dir = self.runtime_root / "logs"
            for path in (workdir, session_dir, log_dir):
                path.mkdir(parents=True, exist_ok=True, mode=0o700)
            bridge.time_budget_seconds=self.timeout_seconds
            bridge.finalization_reserve_seconds=finalization_reserve(self.timeout_seconds)
            bridge.require_claim_ledger=self.evaluation_mode
            bridge.checkpoint_path=workdir/'investigation-checkpoint.json'
            bridge._checkpoint()
            if self.trace_sink:
                with self.trace_sink.interval(actor='pipeline',stage='analysis',action='deterministic_preparation') as detail:
                    bridge.prepare_analysis(workdir / 'analysis-preparation.json')
                    detail.update(series_count=bridge.preparation['series_count'])
            else:
                bridge.prepare_analysis(workdir / 'analysis-preparation.json')
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
                "Only the lead submits the final report; children save submit_subreport(). "
                "Cover every scoped screening unit with an explicit review disposition and synthesize across sources. "
                "Use context analysis_preparation and summarize_series before exploring. Use calculate_metrics and align_series for numerical claims. "
                "Report unresolved evidence honestly. Do not claim completion unless submit_report succeeds."
            )
            request = {
                "bundle_root": str(self.bundle), "cwd": str(workdir),
                "session_dir": str(session_dir), "session_file": prior_file,
                "skill_paths": [str(self.skill_path), str(self.message_skill_path)],
                "system_prompt": self.system_path.read_text(encoding="utf-8"),
                "model": self.model, "prompt": prompt,
                "evaluation_mode": self.evaluation_mode,
                "timeout_seconds":max(0,self.timeout_seconds-(time.monotonic()-bridge.started_monotonic)) if self.timeout_seconds is not None else None,
                "finalization_reserve_seconds":bridge.finalization_reserve_seconds,
                "specialist_wrapup_seconds":bridge.specialist_wrapup_seconds,
                "compaction_target_tokens":self.compaction_target_tokens,
            }
            environment = os.environ.copy()
            environment.pop("BIODEMO_MANUFACTURING_STORE", None)
            environment.pop("BIODEMO_MANUFACTURING_SCOPE", None)
            environment["BIODEMO_PRIME_BRIDGE_CONFIG"] = str(bridge_config)
            run_tag = uuid.uuid4().hex[:12]
            log_path = log_dir / f"{incident_id}-{run_tag}.jsonl"
            error_path = log_dir / f"{incident_id}-{run_tag}.stderr"
            tools_path = log_dir / f"{incident_id}-{run_tag}.tools.jsonl"
            try:
                process = subprocess.run(self.command, cwd=workdir, env=environment,
                                         input=json.dumps(request), text=True, capture_output=True,
                                         check=False, timeout=request['timeout_seconds'])
            except subprocess.TimeoutExpired as exc:
                for destination,content in ((log_path,exc.stdout),(error_path,exc.stderr)):
                    destination.write_text(content.decode(errors='replace') if isinstance(content,bytes) else content or '')
                    destination.chmod(0o600)
                bridge._checkpoint()
                raise
            finally:
                from .telemetry import session_usage
                telemetry=session_usage(session_dir)
                (log_dir/f'{incident_id}-{run_tag}.usage.json').write_text(json.dumps(telemetry,indent=2)+'\n')
                tools_path.write_text(
                    "\n".join(json.dumps(entry, default=str) for entry in bridge.tool_history) + "\n",
                    encoding="utf-8")
                tools_path.chmod(0o600)
            log_path.write_text(process.stdout, encoding="utf-8")
            log_path.chmod(0o600)
            error_path = log_dir / f"{incident_id}-{run_tag}.stderr"
            error_path.write_text(process.stderr, encoding="utf-8")
            error_path.chmod(0o600)
            session_id = session_file = None
            usage = {"model_calls": 0, "input_tokens": 0, "output_tokens": 0,
                     "cached_input_tokens": 0, "inference_cost_usd": None,
                     "total_cost_usd":None, "cost_status":"unknown_provider_or_child_telemetry",
                     "root_reported_cost_usd":0.0}
            for line in process.stdout.splitlines():
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("type") == "session" and event.get("id"):
                    session_id, session_file = str(event["id"]), event.get("file")
                    if event.get("model"):
                        usage["model_id"] = event["model"]
                if event.get("type") == "message_end" and event.get("message", {}).get("role") == "assistant":
                    tokens = event["message"].get("usage")
                    if isinstance(tokens, dict):
                        usage["model_calls"] += 1
                        usage["input_tokens"] += int(tokens.get("input", 0))
                        usage["output_tokens"] += int(tokens.get("output", 0))
                        usage["cached_input_tokens"] += int(tokens.get("cacheRead", 0))
                        usage["root_reported_cost_usd"] += float((tokens.get("cost") or {}).get("total", 0.0))
                        if self.trace_sink is not None:
                            self.trace_sink.emit(actor="agent", stage="analysis", action="model_usage",
                                                 model_id=usage.get("model_id", self.model),
                                                 prompt_version=hashlib.sha256(self.system_path.read_bytes()).hexdigest(),
                                                 input_tokens=tokens.get("input"), output_tokens=tokens.get("output"),
                                                 estimated_cost_usd=(tokens.get("cost") or {}).get("total"),
                                                 started_at=event.get('started_at'),ended_at=event.get('ended_at'),
                                                 usage_scope="root_sdk_session_only")
            if process.returncode != 0:
                raise RuntimeError(f"Prime SDK host exited with code {process.returncode}; "
                                   f"stdout: {log_path} stderr: {error_path} tools: {tools_path}")
            if bridge.result is None:
                raise RuntimeError("Prime Agent finished without submitting a validated investigation report")
            if not session_id or not session_file or not Path(session_file).is_file():
                raise RuntimeError("Prime SDK did not persist a resumable session")
            marker.write_text(json.dumps({"session_id": session_id, "session_file": session_file}) + "\n", encoding="utf-8")
            marker.chmod(0o600)
            bridge.result["rollout_metrics"].update(usage)
            bridge.result["rollout_metrics"].update({
                "prime_session_id": session_id, "prime_log": str(log_path),
                "prime_tool_calls": str(tools_path),
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
