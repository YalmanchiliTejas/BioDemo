"""Click-triggered real Prime investigations for the local demo."""
from __future__ import annotations

import copy
import json
import os
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from src.prime_runtime.compare import run_comparison
from src.paths import DEFAULT_PRIME_BUNDLE


class DemoRuns:
    def __init__(self, repository: Path, *, runner: Callable = run_comparison):
        self.repository = repository
        self.root = repository / "runs" / "demo-agent"
        self.runner = runner
        self._lock = threading.RLock()
        self._jobs: dict[str, dict] = {}

    def availability(self, case_id: str) -> dict:
        if case_id not in {"fresenius", "cho"}:
            raise KeyError("unknown demo case")
        bundle = Path(os.getenv("PRIME_AGENT_BUNDLE_ROOT", DEFAULT_PRIME_BUNDLE))
        configured = bool(os.getenv("BIODEMO_PRIME_SDK_COMMAND")) or (
            shutil.which("node") is not None and (bundle / "packages/coding-agent/dist/index.js").is_file())
        reason = None if configured else "Prime SDK is unavailable. Configure PRIME_AGENT_BUNDLE_ROOT or BIODEMO_PRIME_SDK_COMMAND."
        if case_id == "cho" and not list((self.repository / "benchmarks/cho/raw/workbooks").glob("*.xlsx")):
            reason = "CHO source workbooks are unavailable. Download the source dataset first."
        return {"available": reason is None, "reason": reason}

    def _save(self, job: dict) -> None:
        folder = self.root / job["id"]
        folder.mkdir(parents=True, exist_ok=True)
        temporary = folder / "run.tmp"
        temporary.write_text(json.dumps(job, indent=2, default=str) + "\n")
        temporary.replace(folder / "run.json")

    def get(self, identifier: str, tenant: str) -> dict:
        if len(identifier) != 32 or any(c not in "0123456789abcdef" for c in identifier):
            raise KeyError("agent run not found")
        with self._lock:
            job = self._jobs.get(identifier)
            path = self.root / identifier / "run.json"
            if job is None and path.is_file():
                job = json.loads(path.read_text())
                if job["status"] in {"queued", "running"}:
                    job.update(status="failed", phase="Interrupted by server restart",
                               error="The server restarted before this run completed. Start a new investigation.")
                    self._save(job)
                self._jobs[identifier] = job
            if not job or job["tenant"] != tenant:
                raise KeyError("agent run not found")
            return copy.deepcopy(job)

    def start(self, case_id: str, tenant: str, *, as_of: str | None) -> dict:
        readiness = self.availability(case_id)
        if not readiness["available"]:
            raise RuntimeError(readiness["reason"])
        with self._lock:
            for job in self._jobs.values():
                if job["tenant"] == tenant and job["case_id"] == case_id and job["status"] in {"queued", "running"}:
                    return copy.deepcopy(job)
            identifier = uuid.uuid4().hex
            job = {"id": identifier, "case_id": case_id, "tenant": tenant,
                   "status": "queued", "phase": "Preparing source files", "as_of": as_of,
                   "started_at": datetime.now(timezone.utc).isoformat(), "finished_at": None,
                   "result": None, "error": None}
            self._save(job)
            self._jobs[identifier] = job
            threading.Thread(target=self._execute, args=(identifier,), daemon=True,
                             name=f"demo-agent-{identifier[:8]}").start()
            return copy.deepcopy(job)

    def _update(self, identifier: str, **changes) -> None:
        with self._lock:
            self._jobs[identifier].update(changes)
            self._save(self._jobs[identifier])

    def _execute(self, identifier: str) -> None:
        job = self._jobs[identifier]
        output = self.root / identifier
        try:
            self._update(identifier, status="running")
            if job["case_id"] == "fresenius":
                from benchmarks.fresenius.build_multimodal_package import build_package
                package = output / "source"
                build_package(package, as_of=job["as_of"], map_output=output / "evaluation-only-source-map.json")
                objective = "Investigate the available manufacturing evidence at this cutoff. Assess microbiological risk, cross-batch scope, competing explanations, missing evidence and next steps for human review. Do not assume a confirmed root cause."
            else:
                package = self.repository / "benchmarks/cho/raw/workbooks"
                objective = "Investigate the raw CHO cultivation workbooks. Identify experiments, reactors, units and alignment gaps. Compare cultivation behavior using source evidence; distinguish descriptive associations from causal or optimization claims and report uncertainty and required validation."
            result = self.runner(package=package, objective=objective, output=output / "artifacts",
                                 as_of=job["as_of"], scope=f"demo-{identifier}",
                                 progress=lambda phase: self._update(identifier, phase=phase))
            report = json.loads((output / "artifacts/agent_report.json").read_text())
            complete=report.get('report_status')=='complete_for_available_evidence'
            self._update(identifier, status="completed" if complete else "incomplete",
                         phase="Evidence reviewed · scientific review required" if complete else "Partial investigation · coverage or verification remains unresolved",
                         finished_at=datetime.now(timezone.utc).isoformat(), result={
                             "assessment": report.get("assessment"), "severity": report.get("severity"),
                             "report_status":report.get("report_status","incomplete"),
                             "investigation_review":report.get("investigation_review",{}),
                             "cross_scope_synthesis":report.get("cross_scope_synthesis",""),
                             "observed_facts":report.get("observed_facts",[]),
                             "interpretations":report.get("interpretations",[]),
                             "hypotheses": report.get("causal_hypotheses", []),
                             "open_questions": report.get("open_questions", []),
                             "evidence_count": len(report.get("evidence_ids", [])),
                             "investigation_seconds": result.get("with_agent", {}).get("investigation_seconds"),
                             "artifact_directory": str(output / "artifacts"),
                         })
        except Exception as exc:
            self._update(identifier, status="failed", phase="Investigation failed", error=str(exc),
                         finished_at=datetime.now(timezone.utc).isoformat())
