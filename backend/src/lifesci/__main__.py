"""Life-sciences platform commands.

  python -m src.lifesci serve [--port 8100] [--seed-demo]
  python -m src.lifesci seed-demo
  python -m src.lifesci worker            # Temporal mission worker (needs TEMPORAL_ADDRESS)

With TEMPORAL_ADDRESS (e.g. 127.0.0.1:7233) set, ``serve`` routes mission wake-ups through
Temporal; API and worker must share LIFESCI_DATABASE_URL.

Set LIFESCI_DATABASE_URL (sqlite:///path or postgresql://...) for persistence; the
development default is sqlite:///.cache/lifesci-dev.db. Without OIDC_* variables the
development header resolver is used; roles still come from stored assignments.
"""

from __future__ import annotations

import argparse
import json
import os

DEV_DB = "sqlite:///.cache/lifesci-dev.db"


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m src.lifesci")
    sub = parser.add_subparsers(dest="cmd", required=True)
    serve = sub.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8100)
    serve.add_argument("--seed-demo", action="store_true", help="create the synthetic development tenant first")
    sub.add_parser("seed-demo")
    sub.add_parser("worker")
    args = parser.parse_args()
    os.environ.setdefault("LIFESCI_DATABASE_URL", DEV_DB)
    from .container import Platform
    from .devseed import seed

    platform = Platform.from_env()
    if args.cmd == "seed-demo" or getattr(args, "seed_demo", False):
        print(json.dumps(seed(platform), indent=2))
    address = os.environ.get("TEMPORAL_ADDRESS")
    namespace = os.environ.get("TEMPORAL_NAMESPACE", "default")
    if args.cmd == "worker":
        if not address:
            raise SystemExit("TEMPORAL_ADDRESS is required for the mission worker")
        import asyncio

        from temporalio.client import Client

        from .orchestration.temporal import build_worker

        async def run() -> None:
            client = await Client.connect(address, namespace=namespace)
            await build_worker(client, platform).run()
        asyncio.run(run())
    if args.cmd == "serve":
        import uvicorn

        from .api import create_app
        if address:
            from .orchestration.temporal import TemporalScheduler, attach
            attach(platform, TemporalScheduler.connect(address, platform, namespace=namespace))
        uvicorn.run(create_app(platform), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
