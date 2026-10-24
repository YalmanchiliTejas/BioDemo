"""Synthetic development tenant for running the UI against the real API.

Everything created here is labelled synthetic (``metadata.synthetic = True`` and
"SYNTHETIC" in titles). It provides people with roles, one site, a few source
records and one mission, so connected mode has something real to read and act
on. It is never a substitute for a customer's systems of record.
"""

from __future__ import annotations

import json
from typing import Any

from .container import Platform
from .ownership import Ownership

TENANT = "demo-northfield"
SITE = "NF1"
PEOPLE = [
    ("priya", "msat", SITE), ("quinn", "qa", SITE), ("sam", "supervisor", SITE),
    ("olu", "operator", SITE), ("exec-svc", "system_executor", None),
]


def seed(platform: Platform) -> dict[str, Any]:
    idn = platform.identity
    for actor, role, site in PEOPLE:
        idn.assign_role(TENANT, actor, role, site_id=site)
    for op, system in [("place_hold", "MES"), ("request_retest", "LIMS"), ("submit_deviation", "QMS")]:
        platform.ownership.assign(TENANT, Ownership(op, SITE, "external", system, (op,)), by="devseed",
                                  reason="synthetic development configuration")
    olu = idn.context_for(TENANT, "olu")
    series = [7.00, 7.01, 6.99, 7.00, 7.01, 7.00, 6.99, 7.00, 6.98, 6.97, 6.96, 6.95, 6.94, 6.93]
    records = [
        ("HIST", "BR-04-pH-2026-10-20", json.dumps({"tag": "BR-04.pH", "unit": "pH", "values": series}),
         "application/json"),
        ("LIMS", "F-2408-titer", json.dumps({"batch": "F-2408", "titer_g_per_l": 3.1, "spec_min": 3.4}),
         "application/json"),
        ("MES", "F-2408-feed-log", "Feed 2 started 02:10, 40 min later than recipe target.", "text/plain"),
    ]
    refs = []
    for system, rid, content, media in records:
        e = platform.evidence.ingest(olu, source_system=system, source_record_id=rid, content=content.encode(),
                                     media_type=media, site_id=SITE, event_time="2026-10-20T00:00:00+00:00",
                                     metadata={"synthetic": True, "title": f"SYNTHETIC {system} {rid}"})
        refs.append({"kind": "evidence", "id": e["evidence_id"], "revision": e["revision"], "site_id": SITE})
    priya = idn.context_for(TENANT, "priya")
    existing = [m for m in platform.missions.list_for(priya) if m["objective"].startswith("SYNTHETIC")]
    mission = existing[0] if existing else platform.missions.start_or_resume(
        priya, objective="SYNTHETIC: understand the lower titer in F-2408", owner_id="priya",
        scope={"site_ids": [SITE], "batch": "F-2408"}, constraints=["no recipe change without QA approval"],
        subscriptions=[{"type": "evidence.", "site_id": SITE}])
    return {"tenant": TENANT, "site": SITE, "mission_id": mission["mission_id"], "evidence": refs,
            "people": [{"actor_id": a, "role": r} for a, r, _ in PEOPLE]}
