from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.evaluation import run_benchmark


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the leakage-gated Manufacturing OS RLM benchmark")
    parser.add_argument("--data-dir", type=Path, default=Path("data/v1.1"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/rlm_benchmark_results.json"))
    args = parser.parse_args()
    print(json.dumps(run_benchmark(args.data_dir, args.output), indent=2))
