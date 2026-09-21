from __future__ import annotations

import argparse
import json
from pathlib import Path

from .evaluation.replay import replay_summary
from .simulation import BenchmarkSimulation


def main() -> None:
    parser = argparse.ArgumentParser(description="Biopharma factory benchmark")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run a 30-day campaign")
    run.add_argument("--mode", default="traditional", choices=["traditional"])
    run.add_argument("--seed", type=int, default=20250921)
    run.add_argument("--output", type=Path, default=Path("runs/baseline"))
    replay = sub.add_parser("replay", help="summarize a JSONL event log")
    replay.add_argument("event_log", type=Path)
    args = parser.parse_args()

    if args.command == "run":
        result = BenchmarkSimulation(seed=args.seed, mode=args.mode).run(args.output)
        print(json.dumps(result.metrics, indent=2, sort_keys=True))
    else:
        print(json.dumps(replay_summary(args.event_log), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

