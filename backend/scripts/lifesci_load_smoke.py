"""Single-process load smoke for src.lifesci (measures; does not establish capacity).

Usage: .venv/bin/python scripts/lifesci_load_smoke.py [--url sqlite:///tmp/x.db] [--n 2000]
Prints p50/p95 latencies for ingest, authorization checks with many grants,
proposal->approval, and dependency invalidation fan-out.
"""

from __future__ import annotations

import argparse
import statistics
import time

from src.lifesci.actions import ActionService
from src.lifesci.evidence import EvidenceRef, EvidenceService
from src.lifesci.identity import IdentityService
from src.lifesci.ownership import Ownership, OwnershipRegistry
from src.lifesci.store import RecordStore

T = "load-tenant"


def pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return xs[min(int(len(xs) * p), len(xs) - 1)] * 1000


def timed(fn, n: int) -> list[float]:
    out = []
    for i in range(n):
        t = time.perf_counter()
        fn(i)
        out.append(time.perf_counter() - t)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=":memory:")
    ap.add_argument("--n", type=int, default=2000)
    args = ap.parse_args()
    s = RecordStore(args.url)
    idn, own = IdentityService(s), OwnershipRegistry(s)
    ev, act = EvidenceService(s, idn), ActionService(s, idn, own)
    idn.assign_role(T, "op", "operator", site_id="S1")
    idn.assign_role(T, "sup", "supervisor", site_id="S1")
    own.assign(T, Ownership("place_hold", "S1", "external", "MES", ("place_hold",)), by="a", reason="load")
    op, sup = idn.context_for(T, "op"), idn.context_for(T, "sup")
    results = {}
    results["ingest"] = timed(lambda i: ev.ingest(op, source_system="HIST", source_record_id=str(i),
                                                  content=f"v={i}".encode(), media_type="t", site_id="S1",
                                                  event_time=None), args.n)
    for i in range(args.n):
        idn.grant(T, grantee_id=f"partner-{i % 50}", resource_kind="batch", resource_id=f"B{i}", actions=["read"])
    partner = idn.context_for(T, "u", actor_kind="partner", partner_org_id="partner-7")
    results["partner_check_with_grants"] = timed(lambda i: idn.check(partner, "read", "batch", f"B{i}"), 200)
    results["role_check"] = timed(lambda i: idn.check(op, "read", "batch", "B1", site_id="S1"), 500)

    def flow(i: int) -> None:
        p = act.propose(op, target_system="MES", operation="place_hold", target_id=f"B{i}", payload={},
                        basis=[{"kind": "evidence", "id": f"HIST:{i}", "revision": 1, "site_id": "S1"}],
                        rationale="r", expected_result="e", owner_id="sup", site_id="S1")
        act.decide(sup, p["proposal_id"], expected_revision=1, decision="approved", role="supervisor")
    results["propose_and_approve"] = timed(flow, min(args.n, 300))
    root = EvidenceRef("evidence", "HIST:0", 1, "S1")
    for i in range(200):
        ev.record_derived(op, "finding", {"i": i}, inputs=[root], produced_by={})
    t = time.perf_counter()
    n_stale = len(ev.ingest(op, source_system="HIST", source_record_id="0", content=b"corrected", media_type="t",
                            site_id="S1", event_time=None)["invalidated"])
    results[f"correction_invalidating_{n_stale}"] = [time.perf_counter() - t]
    print(f"backend={s.backend} n={args.n}")
    for k, xs in results.items():
        print(f"{k:36s} p50={pct(xs, .5):8.2f}ms p95={pct(xs, .95):8.2f}ms  (n={len(xs)}, mean {statistics.mean(xs)*1000:.2f}ms)")


if __name__ == "__main__":
    main()
