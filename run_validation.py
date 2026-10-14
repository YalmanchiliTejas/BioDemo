from __future__ import annotations

import argparse
from pathlib import Path

from benchmark.pharma_simulation.generator import DEFAULT_OUTPUT
from benchmark.pharma_simulation.harness import run_validation


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Replay all batches and compute benchmark metrics.")
    parser.add_argument("--database", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = run_validation(args.database, args.output)
    print(f"Benchmark complete for fingerprint {result['dataset_fingerprint']}")
    print(args.output / "benchmark_results.md")
