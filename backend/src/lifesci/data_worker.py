"""Separate process for persisted, resumable data-flow work."""
import argparse
import os
import time
from .store import LeaseError


def tick(platform, tenants):
    finished = 0
    for tenant in tenants:
        for rec in platform.store.read().list(tenant, "data_flow_run", lambda s: s.get("queued", False)):
            state = rec.state
            ctx = platform.identity.context_for(tenant, state["queued_by"])
            try:
                result = platform.flows.run(ctx, rec.id)
                issues = result.get("issues", [])
            except LeaseError:
                continue  # another worker owns the flow's live fence
            except (PermissionError, ValueError) as exc:
                issues = [str(exc)]
            with platform.store.transaction("data-worker") as tx:
                current = tx.require(tenant, "data_flow_run", rec.id)
                if current.state.get("queue_request_id") != state["queue_request_id"]:
                    continue
                tx.put(tenant, "data_flow_run", rec.id,
                       {**current.state, "queued": False, "issues": issues,
                        "status": current.state["status"] if not issues or current.state["status"] in ("stale", "quarantined") else "blocked"},
                       expected_revision=current.revision, action="finish_queued_flow")
            finished += 1
            break  # one flow per tenant per pass; a backlog cannot monopolize the worker
    return finished


def main():
    from .__main__ import _load_env
    from .container import Platform
    _load_env()
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    tenants = [t.strip() for t in os.environ.get("LIFESCI_TENANTS", os.environ.get("DEPLOYMENT_TENANT", "")).split(",") if t.strip()]
    if not tenants:
        raise SystemExit("LIFESCI_TENANTS is required; workers do not enumerate other tenants")
    platform = Platform.from_env()
    try:
        while True:
            tick(platform, tenants)
            if args.once:
                break
            time.sleep(1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
