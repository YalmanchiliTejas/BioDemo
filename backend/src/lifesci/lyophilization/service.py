"""Versioned simulations and reviewed recommendations through existing services."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ..evidence import EvidenceRef
from .case import INPUT_REVISION, manifest, receiving_config, source_config
from .model import MODEL_VERSION, simulate, uncertainty
from .workflows import operations, transfer, verification_plan


class ProcessModelService:
    def __init__(self, platform):
        self.p = platform
        from ..process_engineering.service import ProcessAnalysisService
        self.analysis = ProcessAnalysisService(platform)

    def _inputs(self, ctx, *, audience="technology_transfer", site_id="NF1", shelf_c=-24.,
            load_vials=11000, capacity_kg_h=.65, samples=8, seed=2025,
            measurements=None, cutoff_h=6., cdmo_future_shelf_c=-14.) -> dict:
        self.p.identity.require(ctx, "propose", "process_simulation", site_id=site_id)
        if audience not in ("technology_transfer", "cdmo_operation"):
            raise ValueError("unknown simulation audience")
        from .reference import operation_config, demo_observations
        config = receiving_config(shelf_c=shelf_c, load_vials=load_vials, capacity_kg_h=capacity_kg_h) if audience == "technology_transfer" else operation_config(future_shelf_c=cdmo_future_shelf_c)
        if audience == "cdmo_operation":
            # The built-in observation fixture is explicitly synthetic and generated
            # by an independent reference; callers can supply actual cutoff evidence.
            observations = measurements if measurements is not None else demo_observations()
            from .workflows import visible_measurements
            observations = visible_measurements(observations, cutoff_h)
        else:
            observations = []
        bundle = {"input_revision": INPUT_REVISION, "config": config,
                  "sending_config": source_config(), "parameter_manifest": manifest(config),
                  "observation_provenance": "caller_supplied_unverified" if measurements is not None else "synthetic_assumption",
                  "observations": observations, "evidence_cutoff_h": cutoff_h if observations else None,
                  "uncertainty": {"samples": samples, "seed": seed}}
        source = self.p.evidence.ingest(ctx, source_system="process-model-inputs", source_record_id=f"{site_id}:{audience}",
            content=json.dumps(bundle, sort_keys=True, allow_nan=False).encode(), media_type="application/json",
            site_id=site_id, event_time=None, source_revision=INPUT_REVISION,
            metadata={"classification": "mixed_published_and_reconstructed", "not_production": True})
        refs = [EvidenceRef("evidence", source["evidence_id"], source["revision"], site_id)]
        return bundle, refs

    def context(self, ctx, **settings):
        bundle, refs = self._inputs(ctx, **settings)
        site = refs[0].site_id
        self.p.identity.require(ctx, "propose", "physical_analysis_context", site_id=site)
        with self.p.store.transaction(ctx.actor_id) as tx:
            self.p.identity.validate_refs(ctx, [r.to_dict() for r in refs], tx=tx)
            return self.p.evidence.record_derived(ctx, "physical_analysis_context", {
                "site_id": site, "classification": "analysis_inputs_not_predictions", "input_bundle": bundle,
                "has_observations": bool(bundle["observations"]),
                "workspace": {"audience": settings.get("audience", "technology_transfer"),
                              "options": [{"label": "Supplied operating conditions", "config": bundle["config"]}]}},
                inputs=refs, produced_by={"method": "process-input-context:1"})

    def run(self, ctx, *, audience="technology_transfer", site_id="NF1", shelf_c=-24.,
            load_vials=11000, capacity_kg_h=.65, samples=8, seed=2025,
            measurements=None, cutoff_h=6., cdmo_future_shelf_c=-14.) -> dict:
        bundle, refs = self._inputs(ctx, audience=audience, site_id=site_id, shelf_c=shelf_c, load_vials=load_vials,
            capacity_kg_h=capacity_kg_h, samples=samples, seed=seed, measurements=measurements, cutoff_h=cutoff_h,
            cdmo_future_shelf_c=cdmo_future_shelf_c)
        config, observations = bundle["config"], bundle["observations"]
        if audience == "technology_transfer":
            workspace = transfer(shelf_c=shelf_c, load_vials=load_vials, capacity_kg_h=capacity_kg_h, samples=samples, seed=seed)
        else:
            workspace = operations(config, observations, cutoff_h=cutoff_h)
            selected = workspace["recommended_index"]
            if selected is not None:
                workspace["options"][selected]["uncertainty"] = uncertainty(workspace["options"][selected]["config"], samples=samples, seed=seed)
        # Reject calculations whose input changed while the solver was running.
        # Transaction also closes the race between currentness check and commit.
        with self.p.store.transaction(ctx.actor_id) as tx:
            self.p.identity.validate_refs(ctx, [r.to_dict() for r in refs], tx=tx)
            return self.p.evidence.record_derived(ctx, "process_simulation", {
                "site_id": site_id, "model_version": MODEL_VERSION, "input_bundle": bundle,
                "source_revision_manifest": [r.to_dict() for r in refs],
                "implementation_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                                          for path in Path(__file__).parent.glob("*.py")},
                "workspace": workspace, "recommendation_refs": [], "verification": verification_plan(),
                "qualification": "unqualified scientific demonstration; independent of LLM-route qualification"},
                inputs=refs, produced_by={"method": MODEL_VERSION, "actor_id": ctx.actor_id})

    def get(self, ctx, run_id: str) -> dict:
        return self.p.evidence.read_derived(ctx, "process_simulation", run_id)

    def propose(self, ctx, run_id: str, *, owner_id: str) -> dict:
        with self.p.store.transaction(ctx.actor_id) as tx:
            run = self.get(ctx, run_id)
            ref = {"kind": "process_simulation", "id": run_id, "revision": run["revision"], "site_id": run["site_id"]}
            self.p.identity.validate_refs(ctx, [ref], tx=tx)
            workspace = run["workspace"]
            idx = workspace["recommended_index"]
            if idx is None:
                raise ValueError("No feasible reviewable candidate; characterize equipment or assess prior damage first")
            option = workspace["options"][idx]
            proposal = self.p.actions.propose(ctx, target_system="engineering-review", operation="change_recipe_parameter",
                target_id=option["config"]["equipment"]["equipment_id"],
                payload={"mode": "simulation_recommendation_only", "candidate": option["label"],
                         "config": option["config"], "verification": verification_plan(), "simulation_id": run_id},
                basis=[ref], rationale="Bounded primary-drying comparison; proposed characterization and verification before any production change.",
                expected_result=f"Conditional primary-drying completion {option['completion_time_h']:.2f} h; no release claim.",
                owner_id=owner_id, follow_up_measure="Independent temperature, pressure control and endpoint verification against proposed criteria",
                constraints=option["result"]["warnings"], change_evidence="New Kv/Rp, critical temperature or equipment capacity data; failed verification or stale sources",
                site_id=run["site_id"])
            # Link is already created by ActionService; keep recommendation refs
            # in a distinct derived record so the simulation's approved basis stays immutable.
            self.p.evidence.record_derived(ctx, "process_recommendation", {"site_id": run["site_id"],
                "simulation_id": run_id, "proposal_id": proposal["proposal_id"], "verification": verification_plan()},
                inputs=[EvidenceRef(**ref)], produced_by={"method": MODEL_VERSION})
            return proposal


def register_handlers(gateway) -> None:
    from ..gateway.registry import TaskPolicy
    def optimize(payload):
        if "measurements" in payload:
            return operations(payload["config"], payload["measurements"], cutoff_h=payload.get("cutoff_h", 6.))
        return transfer(**payload)
    for name, fn in (("primary_drying_simulation", lambda p: simulate(p["config"])),
                     ("primary_drying_optimization", optimize)):
        gateway.registry.add_policy(TaskPolicy(name, "moderate", "C0", deterministic=True, requires_human_review=True,
                                               description="Unqualified mechanistic primary drying; no production action"))
        gateway.register_handler(name, fn, MODEL_VERSION)
