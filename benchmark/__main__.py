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
    ingest = sub.add_parser("knowledge-ingest", help="ingest a JSONL event log into the CDMO digital thread")
    ingest.add_argument("event_log", type=Path)
    ingest.add_argument("--source", default="benchmark")
    ingest.add_argument("--tenant", default="default")
    ingest.add_argument("--site")
    ingest.add_argument("--classification", default="internal")
    args = parser.parse_args()

    if args.command == "run":
        result = BenchmarkSimulation(seed=args.seed, mode=args.mode).run(args.output)
        print(json.dumps(result.metrics, indent=2, sort_keys=True))
    elif args.command == "replay":
        print(json.dumps(replay_summary(args.event_log), indent=2, sort_keys=True))
    else:
        from .integration.connectors import JsonlConnector
        from .knowledge.domain import AccessContext
        from .knowledge.runtime import integration_gateway_from_env

        gateway = integration_gateway_from_env()
        thread = gateway.digital_thread
        try:
            access = AccessContext(
                args.tenant, "knowledge-ingest", (args.site,) if args.site else (),
                ("system",), (args.classification,),
            )
            connector = JsonlConnector(
                f"jsonl:{args.source}:{args.event_log.resolve()}", args.source,
                args.event_log, site_id=args.site,
            )
            result = gateway.sync(connector, access=access)
            print(json.dumps({
                "ingested_events": result.records_ingested, "source": args.source,
                "tenant": args.tenant, "site": args.site,
                "checkpoint": result.final_checkpoint,
            }, indent=2))
        finally:
            close_graph = getattr(thread.knowledge.graph, "close", None)
            close_documents = getattr(thread.knowledge.documents, "close", None)
            close_workflow = getattr(thread.cases, "close", None)
            if close_graph:
                close_graph()
            if close_documents:
                close_documents()
            if close_workflow:
                close_workflow()


if __name__ == "__main__":
    main()
