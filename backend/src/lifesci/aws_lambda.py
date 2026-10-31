"""AWS Lambda entry point (handler ``src.lifesci.aws_lambda.handler``).

One function serves three kinds of event:

* HTTP requests from the function URL, through the same FastAPI app as ``serve``;
* background tasks it sent to itself (``tasks.TaskRunner``): CMO delivery
  checks and assistant turns, each with Lambda's full time limit;
* the schedule (``{"biodemo_task": {"kind": "runtime_tick"}}``), which replaces
  the long-lived runtime thread: mission timers, connector polls, data flows.

The app is built once per instance and reused while the instance stays warm.
Only ``/tmp`` is writable, so working files, caches and the home directory are
moved there. Configuration that would silently lose data on Lambda (an
in-memory database, no durable file storage, development identity headers)
stops the function at start-up instead.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

log = logging.getLogger(__name__)
_state: dict[str, Any] = {}


class ConfigurationError(RuntimeError):
    pass


def check_configuration(environ: dict[str, str] | None = None) -> None:
    env = os.environ if environ is None else environ
    problems = []
    if not env.get("LIFESCI_DATABASE_URL", "").startswith(("postgresql://", "postgres://")):
        problems.append("LIFESCI_DATABASE_URL must be the PostgreSQL (Supabase) runtime URL; anything else loses data between requests")
    if env.get("LIFESCI_DB_MIGRATE", "1").strip().lower() not in {"0", "false", "no"}:
        problems.append("LIFESCI_DB_MIGRATE must be 0: the runtime role cannot change the schema (run db-migrate separately)")
    if not (env.get("SUPABASE_URL") and env.get("SUPABASE_SERVICE_ROLE_KEY")):
        problems.append("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required: uploaded files must be kept in Supabase Storage")
    if not env.get("DEPLOYMENT_TENANT"):
        problems.append("DEPLOYMENT_TENANT is required so scheduled work knows which customer it serves")
    if problems:
        raise ConfigurationError("Lambda configuration is unsafe:\n- " + "\n- ".join(problems))


def _prepare_filesystem() -> None:
    work = os.environ.setdefault("LIFESCI_WORK_DIR", "/tmp/biodemo")
    os.makedirs(work, exist_ok=True)
    os.environ["HOME"] = work  # some features read ~/.prime; the image's home is read-only
    os.environ.setdefault("XDG_CACHE_HOME", os.path.join(work, ".cache"))
    os.environ.setdefault("CMO_INGESTION_ROOT", os.path.join(work, "cmo"))
    os.environ.setdefault("LIFESCI_SIMULATOR_ROOT", os.path.join(work, "simulators"))
    os.chdir(work)  # features that write relative .cache paths


def _boot() -> dict[str, Any]:
    if not _state:
        check_configuration()
        _prepare_filesystem()
        from mangum import Mangum

        from .api import create_app
        from .container import Platform

        app = create_app(Platform.from_env())
        # No lifespan: the runtime thread would be frozen between requests. The schedule calls runtime_tick.
        _state.update(app=app, http=Mangum(app, lifespan="off"))
    return _state


def handler(event: dict[str, Any], context: Any) -> Any:
    state = _boot()
    tasks = state["app"].state.tasks
    if tasks.is_task(event):
        kind = event["biodemo_task"].get("kind")
        result = tasks.run(event)
        log.info("task %s finished", kind)
        try:
            json.dumps(result)
        except TypeError:
            result = None
        return {"task": kind, "result": result}
    return state["http"](event, context)
