from __future__ import annotations

import argparse

from benchmark.pharma_simulation.robustness import run_robustness


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the benchmark across multiple generated seeds.")
    parser.add_argument("--seeds", type=int, default=20, help="Number of consecutive seeds to evaluate.")
    parser.add_argument("--start-seed", type=int, default=100)
    args = parser.parse_args()
    if not 1 <= args.seeds <= 50:
        parser.error("--seeds must be between 1 and 50")
    result = run_robustness(range(args.start_seed, args.start_seed + args.seeds))
    print(f"Completed {result['seed_count']} robustness runs")
    print("benchmark/pharma_simulation/artifacts/robustness_report.md")
