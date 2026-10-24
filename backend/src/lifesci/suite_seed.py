"""Explicit, isolated synthetic tenant for exercising complete suite workflows."""
from .ownership import Ownership

TENANT = "demo-suite"


def seed_suite(p):
    with p.store.transaction("synthetic-suite-seed") as tx:
        marker = tx.get(TENANT, "demo_seed", "suite-v1")
        if marker:
            return {**marker.state, "already_seeded": True}
        people = [("designer", "manufacturing_systems", "S1"), ("operator", "operator", "S1"),
                  ("quality", "qa", "S1"), ("reviewer", "qa_reviewer", "S1"), ("msat", "msat", "S1"),
                  ("receiver", "qa", "S2"), ("admin", "admin", None)]
        for actor, role, site in people:
            p.identity.assign_role(TENANT, actor, role, site_id=site, by="synthetic-suite-seed")
        for site in ("S1", "S2"):
            for kind in ("batch_record", "lab_record", "procedure", "recipe_instance", "result"):
                p.ownership.assign(TENANT, Ownership(kind, site, "native", None, (), True,
                    "SYNTHETIC local demonstration only; not qualified for production", None),
                    by="synthetic-suite-seed", reason="explicit synthetic tenant only")
        ctx = p.identity.context_for(TENANT, "designer")
        p.execution.create_batch(ctx, "SYNTHETIC-B1", product="SYNTHETIC product", modality="mAb", site_id="S1")
        p.lab.register_instrument(ctx, "SYNTHETIC-METER", {"instrument_class": "photometer", "status": "ready",
            "calibration_due": "2999-01-01", "synthetic": True, "note": "fixture, not real calibration evidence"}, site_id="S1")
        recipe = {"steps": [
            {"step_id": "setup", "title": "SYNTHETIC setup verification", "kind": "instruction", "parallel_group": "prep"},
            {"step_id": "clearance", "title": "SYNTHETIC line clearance", "kind": "instruction", "parallel_group": "prep"},
            {"step_id": "measure", "title": "SYNTHETIC pH observation", "kind": "data_entry", "depends_on": ["setup", "clearance"],
             "parameters": [{"name": "ph", "unit": "pH", "low": 6.8, "high": 7.4}]},
            {"step_id": "verify", "title": "SYNTHETIC independent verification", "kind": "signature", "depends_on": ["measure"],
             "required_signatures": ["performed", "verified"]}]}
        method = {"requires": {"instruments": [{"instrument_class": "photometer"}]}, "steps": [
            {"step_id": "assay", "title": "SYNTHETIC absorbance assay", "kind": "data_entry",
             "parameters": [{"name": "absorbance", "unit": "AU", "low": 0, "high": 2}],
             "calculation": {"name": "concentration", "expr": "absorbance * 100", "unit": "mg/L", "low": 0, "high": 200}}]}
        for pid, category, definition in [("SYNTHETIC-RECIPE", "recipe", recipe), ("SYNTHETIC-ASSAY", "lab_method", method)]:
            p.procedures.create_draft(ctx, pid, name=pid, category=category, site_id="S1", definition=definition)
            p.procedures.submit_for_publication(ctx, pid, rationale="Review synthetic POC definition before using it")
        p.cases.open(ctx, "SYNTHETIC-CASE", "designer", "quality", "S1")
        result = {"tenant": TENANT, "synthetic": True, "sites": ["S1", "S2"], "people": [a for a, _, _ in people],
                  "note": "Quality must review publication proposals in Actions; nothing is automatically approved."}
        tx.put(TENANT, "demo_seed", "suite-v1", result, expected_revision=None, action="seed_synthetic_suite")
    return result
