"""Life-sciences platform commands.

  python -m src.lifesci serve [--port 8100] [--seed-demo]
  python -m src.lifesci seed-demo
  python -m src.lifesci db-migrate [--owner-url ...] [--app-role ...] [--verify]
  python -m src.lifesci worker            # Temporal mission worker (needs TEMPORAL_ADDRESS)

Configuration is read from ``backend/.env.local`` (git-ignored) when present. Set
``LIFESCI_ENV_FILE`` to use another file. Real environment variables take
precedence over file values.

Set LIFESCI_DATABASE_URL (sqlite:///path or postgresql://...) for persistence; the
development default is sqlite:///.cache/lifesci-dev.db. For PostgreSQL, run
``db-migrate`` once as the schema owner and set ``LIFESCI_DB_MIGRATE=0`` so the
runtime connects as the non-owner application role instead of attempting DDL.

With TEMPORAL_ADDRESS (e.g. 127.0.0.1:7233) set, ``serve`` routes mission wake-ups through
Temporal; API and worker must share LIFESCI_DATABASE_URL. Without OIDC_* variables the
development header resolver is used; roles still come from stored assignments.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

DEV_DB = "sqlite:///.cache/lifesci-dev.db"
DEFAULT_ENV_FILE = Path(__file__).resolve().parents[2] / ".env.local"


def _load_env() -> None:
    from .envfile import load_env_file

    path = Path(os.environ.get("LIFESCI_ENV_FILE", DEFAULT_ENV_FILE)).expanduser()
    loaded = load_env_file(path)
    if loaded:
        print(f"Loaded {len(loaded)} setting(s) from {path}", file=sys.stderr)


def _app_role_and_password(runtime_url: str | None, explicit_role: str | None) -> tuple[str, str]:
    if not runtime_url or not runtime_url.startswith(("postgresql://", "postgres://")):
        raise SystemExit("LIFESCI_DATABASE_URL must be the PostgreSQL runtime URL to create the app role")
    parts = urlsplit(runtime_url)
    role = explicit_role or unquote(parts.username or "")
    password = unquote(parts.password or "")
    if not role or not password:
        raise SystemExit("the runtime URL must contain the application role and its password")
    return role, password


def _migrate(args: argparse.Namespace) -> None:
    owner_url = args.owner_url or os.environ.get("LIFESCI_MIGRATION_DATABASE_URL")
    if not owner_url:
        raise SystemExit("set LIFESCI_MIGRATION_DATABASE_URL (schema owner) or pass --owner-url")
    if not owner_url.startswith(("postgresql://", "postgres://")):
        raise SystemExit("db-migrate needs a PostgreSQL owner URL")
    runtime_url = os.environ.get("LIFESCI_DATABASE_URL")
    role, password = _app_role_and_password(runtime_url, args.app_role or os.environ.get("LIFESCI_APP_ROLE"))

    from .store import ensure_postgres_role, migrate_postgres, verify_postgres_role

    try:
        ensure_postgres_role(owner_url, role, password)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    migrate_postgres(owner_url, app_role=role)
    print(f"Schema applied. Runtime role {role!r} has no superuser, createdb, createrole or bypassrls.")
    if runtime_url:
        who = verify_postgres_role(runtime_url)
        print(f"Runtime connection verified as {who!r}; unbound sessions see no tenant rows.")


def main() -> None:
    _load_env()
    parser = argparse.ArgumentParser(prog="python -m src.lifesci")
    sub = parser.add_subparsers(dest="cmd", required=True)
    serve = sub.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8100)
    serve.add_argument("--seed-demo", action="store_true", help="create the synthetic development tenant first")
    sub.add_parser("seed-demo")
    migrate = sub.add_parser("db-migrate", help="apply PostgreSQL schema/RLS and create the runtime role")
    migrate.add_argument("--owner-url", help="schema owner connection (default: LIFESCI_MIGRATION_DATABASE_URL)")
    migrate.add_argument("--app-role", help="runtime role (default: the role in LIFESCI_DATABASE_URL)")
    sub.add_parser("worker")
    args = parser.parse_args()

    if args.cmd == "db-migrate":
        _migrate(args)
        return

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
            from .orchestration.temporal import TemporalScheduler, attach
            scheduler = TemporalScheduler(client, platform, loop=asyncio.get_running_loop())
            attach(platform, scheduler)
            platform.runtime.start()
            try:
                await build_worker(client, platform).run()
            finally:
                await asyncio.to_thread(platform.runtime.close)
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
