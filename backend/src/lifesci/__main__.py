"""Life-sciences platform commands.

  python -m src.lifesci serve [--port 8100] [--seed-demo]
  python -m src.lifesci seed-demo
  python -m src.lifesci db-migrate [--owner-url ...] [--app-role ...] [--verify]
  python -m src.lifesci supabase-sql      # regenerate deploy/supabase/migrations from the schema
  python -m src.lifesci cmo-import-legacy SOURCE [--tenant demo-cdmo]
  python -m src.lifesci worker            # Temporal mission worker (needs TEMPORAL_ADDRESS)
  python -m src.lifesci grant-role (--email E | --user-id UUID) --role ROLE [--site S] [--tenant T] [--by A] [--reason R]
  python -m src.lifesci revoke-role (--email E | --user-id UUID) --role ROLE [--site S] [--tenant T] [--by A] [--reason R]
  python -m src.lifesci list-roles [--tenant T] [--all]

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


def _roles(args: argparse.Namespace, platform) -> None:  # noqa: ANN001
    import uuid

    from .identity import DEFAULT_ROLE_POLICY

    tenant = args.tenant or os.environ.get("DEPLOYMENT_TENANT", "").strip()
    if not tenant:
        raise SystemExit("set DEPLOYMENT_TENANT or pass --tenant")
    print(f"Tenant {tenant!r} in the {platform.store.backend} store", file=sys.stderr)
    if args.cmd == "list-roles":
        rows = sorted(platform.store.read().list(tenant, "role_assignment"), key=lambda r: r.id)
        items = [r.state for r in rows if args.all or not r.state.get("revoked_at")]
        print(json.dumps(items, indent=2))
        return
    if args.role not in DEFAULT_ROLE_POLICY:
        raise SystemExit(f"unknown role {args.role!r}; choose one of: {', '.join(sorted(DEFAULT_ROLE_POLICY))}")
    if args.email:
        from .supabase_auth import lookup_user_id_by_email
        try:
            user_id = lookup_user_id_by_email(args.email)
        except (LookupError, RuntimeError, ValueError, OSError) as exc:
            raise SystemExit(str(exc)) from exc
    else:
        try:
            user_id = str(uuid.UUID(args.user_id))
        except ValueError as exc:
            raise SystemExit(f"--user-id must be the Supabase user UUID; got {args.user_id!r}") from exc
    by = args.by or os.environ.get("USER") or "operator-cli"
    who = f"{args.email} ({user_id})" if args.email else user_id
    scope = f"site {args.site}" if args.site else "all sites"
    if args.cmd == "grant-role":
        state = platform.identity.assign_role(tenant, user_id, args.role, site_id=args.site, by=by, reason=args.reason)
        print(f"Assigned {args.role!r} for {scope} to {who} in tenant {tenant!r} (since {state['assigned_at']})")
        return
    from .store import NotFoundError
    try:
        platform.identity.revoke_role(tenant, user_id, args.role, site_id=args.site, by=by, reason=args.reason)
    except NotFoundError as exc:
        raise SystemExit(f"{who} has no {args.role!r} assignment for {scope} in tenant {tenant!r}") from exc
    print(f"Revoked {args.role!r} for {scope} from {who} in tenant {tenant!r}")


def main() -> None:
    _load_env()
    parser = argparse.ArgumentParser(prog="python -m src.lifesci")
    sub = parser.add_subparsers(dest="cmd", required=True)
    serve = sub.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8100)
    serve.add_argument("--seed-demo", action="store_true", help="create the synthetic development tenant first")
    sub.add_parser("seed-demo")
    sub.add_parser("seed-suite", help="create a separate synthetic demo-suite tenant with native POC workflows")
    migrate = sub.add_parser("db-migrate", help="apply PostgreSQL schema/RLS and create the runtime role")
    migrate.add_argument("--owner-url", help="schema owner connection (default: LIFESCI_MIGRATION_DATABASE_URL)")
    migrate.add_argument("--app-role", help="runtime role (default: the role in LIFESCI_DATABASE_URL)")
    sub.add_parser("worker")
    sub.add_parser("supabase-sql", help="regenerate the Supabase SQL-editor migrations from the schema")
    legacy = sub.add_parser("cmo-import-legacy",
                            help="copy CMO records from the pre-normalization cmo.sqlite file or PostgreSQL tables")
    legacy.add_argument("source", help="path to the old cmo.sqlite, or a postgresql:// URL holding the old cmo_* tables")
    legacy.add_argument("--tenant", default=None, help="customer for records without a case tenant (default: CMO_DEFAULT_TENANT or demo-cdmo)")
    for name, verb in (("grant-role", "assign"), ("revoke-role", "revoke")):
        cmd = sub.add_parser(name, help=f"{verb} a stored role for a Supabase user (roles never come from tokens)")
        who = cmd.add_mutually_exclusive_group(required=True)
        who.add_argument("--email", help="look up the Supabase user id (needs SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)")
        who.add_argument("--user-id", help="Supabase user UUID (the token's sub)")
        cmd.add_argument("--role", required=True)
        cmd.add_argument("--site", default=None, help="limit the role to one site (default: tenant-wide)")
        cmd.add_argument("--tenant", default=None, help="default: DEPLOYMENT_TENANT")
        cmd.add_argument("--by", default=None, help="operator recorded in the audit trail (default: $USER)")
        cmd.add_argument("--reason", default=None)
    list_roles = sub.add_parser("list-roles", help="list active stored role assignments")
    list_roles.add_argument("--tenant", default=None, help="default: DEPLOYMENT_TENANT")
    list_roles.add_argument("--all", action="store_true", help="include revoked assignments")
    args = parser.parse_args()

    if args.cmd == "db-migrate":
        _migrate(args)
        return
    if args.cmd == "supabase-sql":
        from .supabase_sql import write
        for path in write():
            print(f"wrote {path}")
        return
    if args.cmd == "cmo-import-legacy":
        from ..manufacturing_data.cmo.legacy import import_legacy
        from ..manufacturing_data.cmo.persistence import Repository, database_url
        root = Path(os.environ.get("CMO_INGESTION_ROOT", Path(__file__).resolve().parents[2] / ".cache" / "cmo-ingestion"))
        print(json.dumps(import_legacy(args.source, Repository(database_url(root)), default=args.tenant), indent=2))
        return

    os.environ.setdefault("LIFESCI_DATABASE_URL", DEV_DB)
    from .container import Platform
    from .devseed import seed

    platform = Platform.from_env()
    if args.cmd in ("grant-role", "revoke-role", "list-roles"):
        _roles(args, platform)
        return
    if args.cmd == "seed-suite":
        from .suite_seed import seed_suite
        print(json.dumps(seed_suite(platform), indent=2))
        return
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
