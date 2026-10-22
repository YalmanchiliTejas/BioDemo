"""Worker process. Receives only a staged package path and objective on stdin."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from benchmarks.common.agent_adapter import run_investigation


def main() -> None:
    request = json.load(sys.stdin)
    output = run_investigation(request["input_package"], request["objective"],
                               request.get("as_of"), request.get("configuration"))
    Path(request["output_path"]).write_text(json.dumps(output, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
