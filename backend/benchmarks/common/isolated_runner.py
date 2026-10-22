from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import os
import signal
from pathlib import Path
from src.paths import DEFAULT_PRIME_BUNDLE


ROOT = Path(__file__).resolve().parents[2]


class IsolatedExecutionError(RuntimeError):
    def __init__(self, message, audit):
        super().__init__(message)
        self.isolation_audit = audit

HIDDEN = (
    "data", "benchmark", "docs", "README.md", ".git", ".prime", "tests",
    "benchmarks/README.md", "benchmarks/cho/reference",
    "benchmarks/cho/raw/Dataset.zip", "benchmarks/cho/tasks", "benchmarks/cho/reports",
    "benchmarks/cho/data_inventory.json", "benchmarks/cho/dataset_profile.md",
    "benchmarks/cho/source_manifest.json", "benchmarks/fresenius/ground_truth",
    "benchmarks/fresenius/raw_package", "benchmarks/fresenius/tasks",
    "benchmarks/fresenius/source_manifest.json", "benchmarks/fresenius/reports",
    "results", "artifacts", "README_benchmarks.md", "benchmarks/snapshots",
    "benchmarks/manifests", "benchmarks/rubrics", "benchmarks/traces", "runs",
)


def _profile(extra_hidden=(), package=None) -> str:
    lines = ["(version 1)", "(allow default)"]
    if package is not None and package.parent.name.startswith("benchmark-case-"):
        # Agent code, installed dependencies, its staged workspace, and SDK
        # credential files are readable. Other case packages and user documents
        # are not. Metadata traversal stays available for normal imports.
        roots = [ROOT / "src", ROOT / "benchmarks/common", ROOT / "benchmarks/baselines",
                 ROOT / "prime_skills", ROOT / ".venv", Path(sys.prefix), Path(sys.base_prefix), package.parent,
                 Path(os.environ.get("PRIME_AGENT_BUNDLE_ROOT", DEFAULT_PRIME_BUNDLE)),
                 Path("/usr"), Path("/System"), Path("/Library"), Path("/opt"), Path("/dev"),
                 Path("/private/var/db"), Path("/private/etc"), Path("/etc"), Path(__file__).parent]
        if shutil.which("node"):
            roots.append(Path(shutil.which("node")).resolve().parent.parent)
        # Prime's installed Python runtime is code, not investigation state.
        # Keep its interpreter and packages readable without opening other SDK
        # sessions, memories, user documents or evaluator references.
        kernel_venv = Path(os.environ.get("PRIME_AGENT_KERNEL_VENV", Path.home() / ".prime/agent/kernel-venv"))
        roots.append(kernel_venv)
        kernel_python = Path(os.environ.get("PRIME_AGENT_KERNEL_PYTHON", kernel_venv / "bin/python"))
        if kernel_python.exists():
            roots.append(kernel_python.resolve().parent.parent)
        if shutil.which("uv"):
            roots.append(Path(shutil.which("uv")).resolve().parent)
        literals = [ROOT, ROOT / "benchmarks", ROOT / "benchmarks/__init__.py", Path.home() / ".prime/agent/auth.json",
                    Path.home() / ".prime/agent/models.json", Path.home() / ".prime/agent/settings.json",
                    Path.home() / ".prime/agent/auth.json.lock"]
        clauses = []
        for name, paths in (("subpath", roots), ("literal", literals)):
            for item in paths:
                escaped = str(item.resolve()).replace('\\', '\\\\').replace('"', '\\"')
                clauses.append(f'(require-not ({name} "{escaped}"))')
        restricted = [Path.home(), Path(tempfile.gettempdir()), Path('/private/tmp')]
        areas = ' '.join(f'(subpath "{p.resolve()}")' for p in restricted)
        lines.append('(deny file-read-data (require-all (require-any ' + areas + ') ' + ' '.join(clauses) + '))')
    for relative in (*HIDDEN, *extra_hidden):
        path = ROOT / relative
        escaped = str(path).replace('\\', '\\\\').replace('"', '\\"')
        lines.append(f'(deny file-read* (subpath "{escaped}"))')
    return "\n".join(lines) + "\n"


def run_isolated(input_package: Path, objective: str, as_of: str | None,
                 configuration: dict) -> dict:
    """Execute baseline with macOS filesystem denial of all evaluation roots."""
    if sys.platform != "darwin" or not shutil.which("sandbox-exec"):
        raise RuntimeError("OS-level agent isolation currently requires macOS sandbox-exec")
    package = input_package.resolve()
    cho_originals = (ROOT / "benchmarks/cho/raw/workbooks").resolve()
    staged_prefixes = ("fresenius-staged-", "fresenius-reliability-", "cho-perturbed-staged-", "benchmark-case-")
    staged = package.name == "agent_input" and package.parent.name.startswith(staged_prefixes)
    if package != cho_originals and not staged:
        raise ValueError(f"agent input path is outside benchmark allowlist: {package}")
    with tempfile.TemporaryDirectory(prefix="benchmark-agent-") as temporary:
        temp = Path(temporary)
        profile = temp / "agent.sb"
        output = temp / "output.json"
        profile.write_text(_profile(configuration.get("hidden_paths", ()), package), encoding="utf-8")
        probes = []
        canary = temp / "unauthorized-tenant.txt"
        canary.write_text("evaluator-only permission canary")
        probe_paths = ["data/v1.1/benchmark_ground_truth.json", "benchmarks/cho/raw/Dataset.zip",
                       "benchmarks/fresenius/raw_package/package_manifest.json", "README.md",
                       "docs/dataset_provenance.md", "README_benchmarks.md", "benchmarks/rubrics/investigation-v2.json",
                       "benchmarks/snapshots/pre-evaluation-v2/manifest.json", *configuration.get("hidden_paths", ())]
        if package.parent.name.startswith("benchmark-case-"):
            probe_paths.append(str(canary))
        for forbidden in probe_paths:
            if not (ROOT / forbidden).exists():
                continue
            probe = subprocess.run(["sandbox-exec", "-f", str(profile), sys.executable,
                                    "-c", f"from pathlib import Path; Path({forbidden!r}).read_bytes()"],
                                   text=True, capture_output=True, cwd=ROOT, timeout=20)
            if probe.returncode == 0 or "PermissionError" not in probe.stderr:
                raise RuntimeError("OS-level hidden-reference denial was not verified for " + forbidden + ": " + probe.stderr[-500:])
            probes.append(forbidden)
        request = {"input_package": str(package), "objective": objective,
                   "as_of": as_of, "configuration": configuration, "output_path": str(output)}
        receipt = {"pass": True, "mechanism": "sandbox-exec inherited by child processes", "denied_read_probes": probes}
        environment = os.environ.copy()
        if package.parent.name.startswith("benchmark-case-"):
            scratch = package.parent / "tmp"
            scratch.mkdir(exist_ok=True)
            environment.update(TMPDIR=str(scratch), IPYTHONDIR=str(package.parent / "ipython"),
                               MPLCONFIGDIR=str(package.parent / "matplotlib"))
            if configuration.get("mode") == "full_rlm" and not environment.get("PRIME_AGENT_KERNEL_PYTHON"):
                installed = Path(environment.get("PRIME_AGENT_KERNEL_VENV", Path.home() / ".prime/agent/kernel-venv")) / "bin/python"
                if installed.is_file():
                    # Pin the SDK's supported preinstalled-runtime interface.
                    # Scored trials must not bootstrap/mutate a shared user
                    # environment or wait on its global installation lock.
                    environment["PRIME_AGENT_KERNEL_PYTHON"] = str(installed)
        process = subprocess.Popen(["sandbox-exec", "-f", str(profile), sys.executable,
                                    "-m", "benchmarks.common.agent_worker"],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, cwd=ROOT, env=environment, start_new_session=True)
        try:
            stdout, stderr = process.communicate(json.dumps(request), timeout=configuration.get("budgets", {}).get("wall_clock_seconds", 1200))
        except subprocess.TimeoutExpired as exc:
            # Bound the SDK host and its kernel/worker descendants together.
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.communicate(timeout=5)
            # The killed worker cannot run its adapter finally block. Recover
            # its durable checkpoints/logs here, without upgrading its status.
            state=Path(configuration.get('state_directory',package.parent/'state'))
            artifacts=Path(configuration.get('artifact_directory',package.parent/'runtime-artifacts'))
            artifacts.mkdir(parents=True,exist_ok=True)
            for candidate in (state/'blackboards/prime-runtime').rglob('*'):
                if candidate.is_file() and (candidate.parent.name=='logs' or candidate.name in {'analysis-preparation.json','investigation-checkpoint.json'}):
                    shutil.copyfile(candidate,artifacts/candidate.name)
            raise IsolatedExecutionError("isolated case exceeded wall-clock budget; process group terminated; checkpoint and host logs recovered in runtime-artifacts; inspect coverage and finalization before retrying; scores withheld", receipt) from exc
        if process.returncode:
            raise IsolatedExecutionError(f"isolated agent failed: {stderr[-1500:]}", receipt)
        result = json.loads(output.read_text(encoding="utf-8"))
        result["isolation_audit"] = receipt
        return result
