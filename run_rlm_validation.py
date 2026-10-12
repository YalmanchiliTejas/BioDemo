from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.evaluation import run_benchmark


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the leakage-gated Manufacturing OS RLM benchmark")
    parser.add_argument("--data-dir", type=Path, default=Path("data/v1.1"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/rlm_benchmark_results.json"))
    parser.add_argument("--agentic", action="store_true", help="Use a live model for Lead RLM reasoning")
    parser.add_argument("--provider", choices=("codex", "openai"), default="codex")
    parser.add_argument("--model", default="gpt-6-luna")
    parser.add_argument("--mode", action="append", choices=("current_event_only", "lims_only", "lims_qms", "full_os"), help="Run only this mode; repeat for multiple modes")
    parser.add_argument("--smoke", action="store_true", help="Run one rollout per context mode")
    parser.add_argument("--max-rollouts-per-mode", type=int, default=None)
    args = parser.parse_args()
    rollout_limit = 1 if args.smoke else args.max_rollouts_per_mode
    if rollout_limit is not None and rollout_limit < 1:
        parser.error("--max-rollouts-per-mode must be positive")
    print(json.dumps(run_benchmark(
        args.data_dir, args.output,
        agentic=args.agentic, provider_kind=args.provider, model=args.model,
        max_rollouts_per_mode=rollout_limit,
        modes=args.mode,
    ), indent=2))
