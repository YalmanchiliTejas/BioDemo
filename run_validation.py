from __future__ import annotations

import argparse
from pathlib import Path

from benchmark.application.dynamic_agents import reasoning_provider_from_env
from benchmark.pharma_simulation.generator import DEFAULT_OUTPUT
from benchmark.pharma_simulation.harness import run_validation


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Replay all batches and compute benchmark metrics.")
    parser.add_argument("--database", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--live", action="store_true", help="Use the configured structured-JSON reasoning provider for the agent conditions.")
    args = parser.parse_args()
    provider = reasoning_provider_from_env(Path.cwd()) if args.live else None
    if args.live and provider is None:
        parser.error("--live requires BIODEMO_DYNAMIC_AGENT_COMMAND, BIODEMO_DYNAMIC_AGENT_URL, or an auto-discovered provider")
    result = run_validation(args.database, args.output, live=args.live, provider=provider)
    print(f"Benchmark complete for fingerprint {result['dataset_fingerprint']}")
    print(args.output / "benchmark_results.md")
