from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HIDDEN = (
    "data", "benchmark", "docs", "README.md", ".git", ".prime", "tests",
    "benchmarks/README.md", "benchmarks/cho/reference",
    "benchmarks/cho/raw/Dataset.zip", "benchmarks/cho/tasks", "benchmarks/cho/reports",
    "benchmarks/cho/data_inventory.json", "benchmarks/cho/dataset_profile.md",
    "benchmarks/cho/source_manifest.json", "benchmarks/fresenius/ground_truth",
    "benchmarks/fresenius/raw_package", "benchmarks/fresenius/tasks",
    "benchmarks/fresenius/source_manifest.json", "benchmarks/fresenius/reports",
    "results", "artifacts",
)


def _profile() -> str:
    lines = ["(version 1)", "(allow default)"]
    for relative in HIDDEN:
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
    staged_prefixes = ("fresenius-staged-", "fresenius-reliability-", "cho-perturbed-staged-")
    staged = package.name == "agent_input" and package.parent.name.startswith(staged_prefixes)
    if package != cho_originals and not staged:
        raise ValueError(f"agent input path is outside benchmark allowlist: {package}")
    with tempfile.TemporaryDirectory(prefix="benchmark-agent-") as temporary:
        temp = Path(temporary)
        profile = temp / "agent.sb"
        output = temp / "output.json"
        profile.write_text(_profile(), encoding="utf-8")
        for forbidden in ("data/v1.1/benchmark_ground_truth.json", "benchmarks/cho/raw/Dataset.zip",
                          "benchmarks/fresenius/raw_package/package_manifest.json", "README.md",
                          "docs/dataset_provenance.md"):
            if not (ROOT / forbidden).exists():
                continue
            probe = subprocess.run(["sandbox-exec", "-f", str(profile), sys.executable,
                                    "-c", f"from pathlib import Path; Path({forbidden!r}).read_bytes()"],
                                   text=True, capture_output=True, cwd=ROOT, timeout=20)
            if probe.returncode == 0 or "PermissionError" not in probe.stderr:
                raise RuntimeError("OS-level hidden-reference denial was not verified for " + forbidden + ": " + probe.stderr[-500:])
        request = {"input_package": str(package), "objective": objective,
                   "as_of": as_of, "configuration": configuration, "output_path": str(output)}
        process = subprocess.run(["sandbox-exec", "-f", str(profile), sys.executable,
                                  "-m", "benchmarks.common.agent_worker"],
                                 input=json.dumps(request), text=True, capture_output=True,
                                 cwd=ROOT, timeout=1200)
        if process.returncode:
            raise RuntimeError(f"isolated agent failed: {process.stderr[-1500:]}")
        return json.loads(output.read_text(encoding="utf-8"))
