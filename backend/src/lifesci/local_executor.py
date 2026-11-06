"""Run multi-agent investigations (the Prime RLM harness and its sub-agents) on this machine.

For laptop demos and development: no DigitalOcean stack, signing key or OIDC setup. Enable with
``INVESTIGATION_EXECUTOR=local`` on a machine with the Prime SDK (``PRIME_AGENT_BUNDLE_ROOT``, default
``~/Desktop/prime-agent-bio``) and the model provider configuration your harness already uses.
Refused on AWS Lambda. Same interface as the remote executor, so the platform, events and UI are identical.

Jobs and events are kept under ``INVESTIGATION_LOCAL_ROOT`` (default ``.cache/local-investigations``) so a
restarted API shows an interrupted run as failed instead of losing it.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import traceback
from pathlib import Path
from typing import Any

LOCAL_SCOPE = "investigation"


def local_executor_from_env(env: dict[str, str] | None = None) -> "LocalExecutor | None":
    env = os.environ if env is None else env
    if env.get("INVESTIGATION_EXECUTOR", "").strip().lower() != "local":
        return None
    if env.get("AWS_LAMBDA_FUNCTION_NAME"):
        raise RuntimeError("INVESTIGATION_EXECUTOR=local runs investigations in-process; it is not allowed on Lambda")
    env_bundle = env.get("PRIME_AGENT_BUNDLE_ROOT") or str(Path.home() / "Desktop" / "prime-agent-bio")
    os.environ.setdefault("PRIME_AGENT_BUNDLE_ROOT", env_bundle)
    return LocalExecutor(Path(env.get("INVESTIGATION_LOCAL_ROOT", ".cache/local-investigations")))


class LocalExecutor:
    def __init__(self, root: Path, *, runner=None) -> None:
        self.root = Path(root)
        (self.root / "inputs").mkdir(parents=True, exist_ok=True)
        (self.root / "jobs").mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()          # submit + event appends
        self._state = threading.RLock()        # every job.json read-modify-write
        self._threads: dict[str, threading.Thread] = {}
        self._cancel: dict[str, threading.Event] = {}
        self._harness: dict[str, Any] = {}
        self.runner = runner or self._run_prime  # tests inject a fake runner

    # --- storage ------------------------------------------------------------------
    def _job_dir(self, job_id: str) -> Path:
        return self.root / "jobs" / hashlib.sha256(job_id.encode()).hexdigest()[:32]

    def _read(self, job_id: str) -> dict[str, Any]:
        path = self._job_dir(job_id) / "job.json"
        if not path.is_file():
            raise KeyError("Unknown job")
        with self._state:
            job = json.loads(path.read_text())
            if job["state"] in ("queued", "running") and job_id not in self._threads:
                # The process that ran it is gone (API restart): say so rather than spin forever.
                job.update(state="failed", error="interrupted: the local API restarted during the run")
                self._write(job)
        return job

    def _write(self, job: dict[str, Any]) -> None:
        folder = self._job_dir(job["id"])
        folder.mkdir(parents=True, exist_ok=True)
        tmp = folder / f"job.json.{threading.get_ident()}.tmp"
        tmp.write_text(json.dumps(job, default=str))
        tmp.replace(folder / "job.json")

    def _transition(self, job_id: str, **changes) -> dict[str, Any] | None:
        """Locked state change that never moves a cancelled or finished job backwards."""
        with self._state:
            job = self._read_raw(job_id)
            if job["state"] in ("cancelled", "succeeded", "failed"):
                return None
            job.update(changes)
            self._write(job)
            return job

    def _append_event(self, job_id: str, event: dict[str, Any]) -> None:
        with self._lock, (self._job_dir(job_id) / "events.jsonl").open("a") as stream:
            stream.write(json.dumps(event, default=str) + "\n")

    # --- executor interface (same as the remote one) --------------------------------
    def upload(self, project: str, sha256: str, data: bytes) -> dict[str, Any]:
        if hashlib.sha256(data).hexdigest() != sha256:
            raise ValueError("Input digest mismatch")
        (self.root / "inputs" / f"{sha256}.zip").write_bytes(data)
        return {"version_id": sha256}

    def submit(self, project: str, idempotency_key: str, job: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            try:
                return self._read(idempotency_key)
            except KeyError:
                pass
            record = {"id": idempotency_key, "project": project, "state": "queued", "manifest": job,
                      "created_at": time.time(), "error": None}
            self._write(record)
            self._cancel[idempotency_key] = threading.Event()
            thread = threading.Thread(target=self._execute, args=(idempotency_key,), daemon=True,
                                      name=f"investigation-{idempotency_key[:12]}")
            self._threads[idempotency_key] = thread
        thread.start()
        return record

    def job(self, project: str, job_id: str) -> dict[str, Any]:
        job = self._read(job_id)
        return {k: job[k] for k in ("id", "state", "error", "created_at")}

    def events(self, project: str, job_id: str, after: int) -> dict[str, Any]:
        self._read(job_id)
        path = self._job_dir(job_id) / "events.jsonl"
        lines = path.read_text().splitlines() if path.is_file() else []
        out = []
        for line in lines:
            event = json.loads(line)
            if event["seq"] > after:
                out.append(event)
            if len(out) >= 500:
                break
        return {"events": out, "next": out[-1]["seq"] if out else after}

    def cancel(self, project: str, job_id: str) -> dict[str, Any]:
        self._read(job_id)
        self._cancel.get(job_id, threading.Event()).set()
        self._transition(job_id, state="cancelled")
        harness = self._harness.get(job_id)
        if harness is not None:
            harness.abort()
        return {"id": job_id, "state": self._read_raw(job_id)["state"]}

    def result(self, project: str, job_id: str) -> dict[str, Any]:
        path = self._job_dir(job_id) / "result.json"
        if not path.is_file():
            raise KeyError("No result")
        return json.loads(path.read_text())

    # --- execution ----------------------------------------------------------------
    def _execute(self, job_id: str) -> None:
        try:
            self._run_job(job_id)
        finally:
            self._harness.pop(job_id, None)
            self._threads.pop(job_id, None)

    def _run_job(self, job_id: str) -> None:
        job = self._transition(job_id, state="running", started_at=time.time())
        if job is None:
            return  # stopped before it started

        def write(event: dict[str, Any]) -> None:
            # Same allow-listed events the remote container prints; stored with a platform sequence number.
            self._append_event(job_id, {"seq": event["local_seq"], "attempt": 1, "at": event["at"], "kind": event["kind"],
                                        "agent_id": event.get("agent_id"), "parent_id": event.get("parent_id"),
                                        "payload": event.get("payload", {})})
        try:
            report = self.runner(job_id, job["manifest"], write, self._cancel[job_id], self._harness)
            with self._state:
                if self._cancel[job_id].is_set() or self._read_raw(job_id)["state"] != "running":
                    return
                (self._job_dir(job_id) / "result.json").write_text(json.dumps({
                    "run_id": job_id, "input_sha256": job["manifest"]["sha256"], "input_version_id": job["manifest"].get("version_id"),
                    "as_of": job["manifest"].get("as_of"), "review_status": "requires_human_review", "report": report}, default=str))
                self._transition(job_id, state="succeeded", finished_at=time.time())
        except Exception as exc:
            # Keep the detail on this machine only; the platform sees a short reason.
            (self._job_dir(job_id) / "error.log").write_text(traceback.format_exc())
            self._transition(job_id, state="failed", error=f"{type(exc).__name__}: {str(exc)[:200]}", finished_at=time.time())

    def _read_raw(self, job_id: str) -> dict[str, Any]:
        return json.loads((self._job_dir(job_id) / "job.json").read_text())

    def _run_prime(self, job_id: str, manifest: dict[str, Any], write, cancelled: threading.Event,
                   harnesses: dict[str, Any]) -> Any:
        from src.manufacturing_data import ManufacturingStore, ingest_package
        from src.prime_runtime.harness import PrimeManufacturingHarness
        from src.prime_runtime.investigation_events import EventEmitter
        from src.state import BlackboardStore
        from src.workflows import ManufacturingInvestigationWorkflow

        work = self._job_dir(job_id)
        store = ManufacturingStore(work / "store")
        ingested = ingest_package(self.root / "inputs" / f"{manifest['sha256']}.zip", store, access_scope=LOCAL_SCOPE)
        if ingested["errors"]:
            raise ValueError("Evidence preparation requires review: some files could not be read")
        boards = BlackboardStore(work / "blackboards")
        workflow = ManufacturingInvestigationWorkflow(work / "workflow", store, scope=LOCAL_SCOPE, blackboards=boards)
        harness = PrimeManufacturingHarness.from_env(store=store, blackboards=boards, workflow=workflow, scope=LOCAL_SCOPE)
        harness.timeout_seconds = max(30, int(manifest.get("timeout_seconds") or 600))
        harness.max_tool_calls = manifest.get("max_tool_calls") or 30
        harnesses[job_id] = harness
        emitter = EventEmitter(write)
        max_tokens = manifest.get("max_tokens")

        def on_event(raw):
            emitter.sdk(raw)
            if max_tokens and emitter.total_tokens > max_tokens:
                emitter.emit("error", {"code": "token_cap_exceeded"}, agent_id="lead")
                harness.abort()
        harness.on_event = on_event
        harness.on_bridge_event = lambda kind, payload, depth, key: emitter.bridge(kind, payload, depth=depth, key=key)
        emitter.set_phase("planning")
        emitter.emit("agent_started", {"depth": 0, "status": "running", "question": manifest["objective"]}, agent_id="lead")
        result = harness.run(incident_id=job_id, problem=manifest["objective"], new_evidence_ids=[], as_of=manifest.get("as_of"))
        emitter.emit("agent_finished", {"depth": 0, "status": "done"}, agent_id="lead")
        return result
