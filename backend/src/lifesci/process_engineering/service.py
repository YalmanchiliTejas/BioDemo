"""Reasoning proposes model/pipeline choices; existing services own all records."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

from ..evidence import EvidenceRef
from ..gateway import TaskRequest
from ..ids import content_hash, parse_iso
from .catalog import ModelCatalog
from .engine import execute, visible_rows
from .schemas import AdapterProposalIn, AgentPlanIn, PipelineSpec

PIPELINE_VERSION = "physical-analysis-pipeline-1"


class ProcessAnalysisService:
    def __init__(self, platform):
        self.p = platform
        self.catalog = ModelCatalog()

    def _source(self, ctx, simulation_id, index):
        kind = "physical_analysis_context" if self.p.store.read().get(ctx.tenant_id, "physical_analysis_context", simulation_id) else "process_simulation"
        source = self.p.evidence.read_derived(ctx, kind, simulation_id)
        source["source_record_kind"] = kind
        self.p.identity.validate_refs(ctx, [{"kind": kind, "id": simulation_id, "revision": source["revision"], "site_id": source["site_id"]}])
        options = source["workspace"]["options"]
        if not 0 <= index < len(options):
            raise ValueError("candidate index is not present in the source simulation")
        config = deepcopy(options[index]["config"])
        if source["workspace"]["audience"] == "cdmo_operation":
            # Existing diagnosis fitted parameters on the entire cutoff window.
            # Reusing them would contaminate a new training/holdout partition.
            config = deepcopy(source["input_bundle"]["config"])
            config["schedule"] = deepcopy(options[index]["config"]["schedule"])
            config["load_vials"] = options[index]["config"]["load_vials"]
        return source, config

    def models(self, ctx, simulation_id=None, candidate_index=0):
        if simulation_id:
            _, config = self._source(ctx, simulation_id, candidate_index)
            return {"models": self.catalog.snapshot(config), "catalog_hash": content_hash(self.catalog.snapshot())}
        self.p.identity.require(ctx, "read", "scientific_model_catalog")
        return {"models": self.catalog.snapshot(), "catalog_hash": content_hash(self.catalog.snapshot())}

    def _catalog_ref(self, ctx, site_id):
        record = self.p.evidence.ingest(ctx, source_system="scientific-model-catalog", source_record_id=site_id,
            content=json.dumps({"models": self.catalog.snapshot(), "runner": self._runner_manifest()}, sort_keys=True).encode(), media_type="application/json", site_id=site_id,
            event_time=None, metadata={"classification": "versioned_scientific_software", "qualification": "unqualified"})
        return EvidenceRef("evidence", record["evidence_id"], record["revision"], site_id)

    @staticmethod
    def _runner_manifest():
        return {"version": PIPELINE_VERSION, "files_sha256": {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                for name in ("engine.py", "schemas.py", "catalog.py", "service.py")}}

    def prepare(self, ctx, spec: PipelineSpec | dict, *, agent_run_id=None, authored_by_agent=False, basis_refs=()):
        spec = PipelineSpec.model_validate(spec)
        source, config = self._source(ctx, spec.simulation_id, spec.candidate_index)
        site = source["site_id"]
        self.p.identity.require(ctx, "propose", "physical_analysis_plan", site_id=site)
        cutoff = source["input_bundle"].get("evidence_cutoff_h")
        if cutoff is not None and spec.evidence_cutoff_h > cutoff:
            raise ValueError("pipeline cannot advance beyond the source evidence cutoff")
        if spec.thermal_assumptions:
            config["thermal"] = spec.thermal_assumptions.model_dump()
        history = deepcopy(source["input_bundle"]["config"])
        if spec.thermal_assumptions:
            history["thermal"] = spec.thermal_assumptions.model_dump()
        observations = visible_rows(source["input_bundle"]["observations"], spec.evidence_cutoff_h)
        if spec.calibration != "none" and len([r for r in observations if r["time_h"] <= spec.calibration_until_h]) < 3:
            raise ValueError("calibration requested without three cutoff-visible training observations")
        pinned = []
        for choice in spec.models:
            adapter = self.catalog.get(choice.model_id)
            pinned.append({**adapter.describe(), "rationale": choice.rationale, "applicability": adapter.applicability(config)})
        catalog_ref = self._catalog_ref(ctx, site)
        # Corrections to extra assumptions invalidate plans/results just like any source correction.
        assumptions = self.p.evidence.ingest(ctx, source_system="process-analysis-assumptions",
            source_record_id=f"{site}:{spec.simulation_id}:{spec.candidate_index}",
            content=json.dumps({"thermal": spec.thermal_assumptions.model_dump() if spec.thermal_assumptions else None}, sort_keys=True).encode(),
            media_type="application/json", site_id=site, event_time=None,
            metadata={"category": "synthetic_assumption", "note": "Caller-supplied uncharacterized thermal inputs; not measured facility properties"})
        refs = [EvidenceRef(source["source_record_kind"], spec.simulation_id, source["revision"], site), catalog_ref,
                EvidenceRef("evidence", assumptions["evidence_id"], assumptions["revision"], site), *basis_refs]
        steps = [{"id": name, "depends_on": [] if i == 0 else [names[i-1]], "implementation": PIPELINE_VERSION}
                 for names in [["validate_sources_and_models", "calibrate_training_window", "simulate_selected_models", "evaluate_holdout", "sample_uncertainty", "build_review_visuals"]]
                 for i, name in enumerate(names)]
        with self.p.store.transaction(ctx.actor_id) as tx:
            self.p.identity.validate_refs(ctx, [r.to_dict() for r in refs], tx=tx)
            return self.p.evidence.record_derived(ctx, "physical_analysis_plan", {
                "site_id": site, "pipeline_version": PIPELINE_VERSION, "spec": spec.model_dump(),
                "runner_manifest": self._runner_manifest(),
                "authored_by": {"kind": "agent" if authored_by_agent or agent_run_id or ctx.actor_kind == "agent" else "person", "actor_id": ctx.actor_id, "gateway_run_id": agent_run_id},
                "pinned_models": pinned, "steps": steps, "review_state": "plan_ready_for_execution",
                "source_snapshot": {"config": config, "history_config": history, "observations": observations,
                    "prior_diagnostic_fits_reused": False,
                    "observation_provenance": source["input_bundle"]["observation_provenance"],
                    "parameter_provenance": source["input_bundle"]["parameter_manifest"],
                    "additional_inputs": [{"parameter": "thermal."+k, "value": v, "unit": "J/K" if k == "vial_heat_capacity_j_k" else "°C", "category": "synthetic_assumption"}
                                          for k, v in (config.get("thermal") or {}).items()]},
                "plan_hash": content_hash({"spec": spec.model_dump(), "models": pinned, "runner": self._runner_manifest(), "config": config, "observations": observations})},
                inputs=refs, produced_by={"method": PIPELINE_VERSION, "gateway_run_id": agent_run_id})

    def get_plan(self, ctx, plan_id):
        return self.p.evidence.read_derived(ctx, "physical_analysis_plan", plan_id)

    def execute(self, ctx, plan_id):
        plan = self.get_plan(ctx, plan_id)
        self.p.identity.require(ctx, "propose", "physical_analysis_result", site_id=plan["site_id"])
        self._catalog_ref(ctx, plan["site_id"])
        ref = EvidenceRef("physical_analysis_plan", plan_id, plan["revision"], plan["site_id"])
        self.p.identity.validate_refs(ctx, [ref.to_dict()])
        if plan["runner_manifest"] != self._runner_manifest():
            raise ValueError("pipeline implementation changed; regenerate the plan")
        for pin in plan["pinned_models"]:
            adapter = self.catalog.get(pin["id"])
            if adapter.version != pin["version"] or adapter.digest != pin["implementation_digest"]:
                raise ValueError("model implementation changed; regenerate the plan before execution")
        output = execute(plan, self.catalog)
        with self.p.store.transaction(ctx.actor_id) as tx:
            self.p.identity.validate_refs(ctx, [ref.to_dict()], tx=tx)
            return self.p.evidence.record_derived(ctx, "physical_analysis_result", {"site_id": plan["site_id"], "plan_id": plan_id,
                "pipeline_version": PIPELINE_VERSION, "plan_hash": plan["plan_hash"], "spec": plan["spec"],
                "runner_manifest": plan["runner_manifest"],
                "source_snapshot": plan["source_snapshot"], "model_manifest": plan["pinned_models"], **output},
                inputs=[ref], produced_by={"method": PIPELINE_VERSION, "actor_id": ctx.actor_id})

    def get_result(self, ctx, result_id):
        return self.p.evidence.read_derived(ctx, "physical_analysis_result", result_id)

    def agent_plan(self, ctx, request: AgentPlanIn | dict):
        request = AgentPlanIn.model_validate(request)
        source, config = self._source(ctx, request.simulation_id, request.candidate_index)
        self.p.identity.require(ctx, "propose", "physical_analysis_plan", site_id=source["site_id"])
        if request.thermal_assumptions:
            config["thermal"] = request.thermal_assumptions.model_dump()
        ref = {"kind": source["source_record_kind"], "id": request.simulation_id, "revision": source["revision"], "site_id": source["site_id"]}
        prompt = {"job": request.objective, "catalog": self.catalog.snapshot(config), "configuration": config,
            "observations": source["input_bundle"]["observations"], "observation_provenance": source["input_bundle"]["observation_provenance"],
            "required_output": {"models": [{"model_id": "registered ID", "rationale": "why appropriate, what it misses, and required characterization"}],
                                "calibration": "none or kv_scale", "calibration_until_h": 3., "temperature_observable": "interface_temperature_c or bottom_temperature_c", "samples": 4,
                                "views": ["trajectories", "validation", "vial_3d"]},
            "constraints": ["Select 1–2 registered models, using only supplied evidence. Explain missing parameters rather than inventing them.",
                            "Keep calibration earlier than holdout. Do not claim a complex model is validated or generates a full 3D field.",
                            "Do not set permissions, qualifications, source IDs, budgets or new thermal inputs."]}
        result = self.p.gateway.run(TaskRequest("investigation_planning", ctx,
            system="You plan reproducible physical analyses for process engineers. Return only the requested JSON fields. Distinguish predictions, assumptions and observations.",
            prompt=json.dumps(prompt, sort_keys=True), inputs=[ref], use_cache=False, timeout_s=45., prompt_version=PIPELINE_VERSION))
        if result.status != "completed":
            return {"status": "agent_unavailable", "gateway_run": result.to_dict(), "plan": None,
                    "note": "No agent plan was fabricated. Engineers can author a plan using the same catalog and runner."}
        output = result.output or {}
        allowed = {"models", "calibration", "calibration_until_h", "temperature_observable", "samples", "views"}
        if set(output)-allowed:
            return {"status": "invalid_agent_plan", "gateway_run": result.to_dict(), "plan": None, "issues": ["planner output contains unsupported fields"]}
        try:
            spec = PipelineSpec.model_validate({**output, "simulation_id": request.simulation_id,
                "candidate_index": request.candidate_index, "objective": request.objective,
                "thermal_assumptions": request.thermal_assumptions.model_dump() if request.thermal_assumptions else None,
                "evidence_cutoff_h": source["input_bundle"].get("evidence_cutoff_h") or 6.})
            plan = self.prepare(ctx, spec, agent_run_id=result.run_id)
        except ValueError as exc:
            return {"status": "invalid_agent_plan", "gateway_run": result.to_dict(), "plan": None, "issues": [str(exc)]}
        return {"status": "plan_created", "gateway_run": result.to_dict(), "plan": plan}

    def propose_review(self, ctx, result_id, owner_id):
        result = self.get_result(ctx, result_id)
        ref = {"kind": "physical_analysis_result", "id": result_id, "revision": result["revision"], "site_id": result["site_id"]}
        with self.p.store.transaction(ctx.actor_id) as tx:
            self.p.identity.validate_refs(ctx, [ref], tx=tx)
            if not any(m["status"] == "completed" for m in result["models"]):
                raise ValueError("review package requires at least one completed model calculation")
            return self.p.actions.propose(ctx, target_system="engineering-review", operation="review_physical_analysis",
                target_id=result_id, payload={"mode": "scientific_review_only", "analysis_result_id": result_id,
                    "model_manifest": result["model_manifest"], "plan_hash": result["plan_hash"],
                    "questions": ["Are model scope and observable appropriate?", "Characterize thermal capacity and initial state before relying on transient forecasts.",
                                  "Obtain independent temperature, vapor-rate and pressure-control measurements; evaluate final quality separately."]},
                basis=[ref], rationale="Review the agent/human-selected models, held-out discrepancies, assumptions and spatial representation before engineering use.",
                expected_result="Document engineer review, missing characterization and acceptance criteria; no manufacturing change or qualification implied.",
                owner_id=owner_id, constraints=result["warnings"], site_id=result["site_id"],
                follow_up_measure="Independent characterization and prespecified holdout prediction error")

    def propose_adapter(self, ctx, request):
        request = AdapterProposalIn.model_validate(request)
        source, _ = self._source(ctx, request.simulation_id, 0)
        if request.model_id in self.catalog.adapters:
            raise ValueError("model ID already registered; changes require a reviewed versioned adapter update")
        ref = {"kind": source["source_record_kind"], "id": request.simulation_id, "revision": source["revision"], "site_id": source["site_id"]}
        return self.p.actions.propose(ctx, target_system="engineering-review", operation="review_scientific_model_adapter",
            target_id=request.model_id, payload={"adapter_request": request.model_dump(), "registry_status": "not_registered",
                "execution_permission": "none", "required_checks": ["Review equations and dimensional consistency", "Verify license and source provenance",
                    "Implement a host-owned adapter with unit/limiting/balance tests", "Freeze independent validation evidence and intended-use limits before qualification"]},
            basis=[ref], rationale=request.intended_use_and_limits,
            expected_result="Reviewed adapter specification; registration and scientific qualification remain separate explicit steps.",
            owner_id=request.owner_id, site_id=source["site_id"], constraints=["No generated solver code is executed or dynamically imported."])

    def interpret(self, ctx, result_id):
        """Use the same gateway for engineering interpretation after calculations."""
        result = self.get_result(ctx, result_id)
        ref = EvidenceRef("physical_analysis_result", result_id, result["revision"], result["site_id"])
        self.p.identity.require(ctx, "propose", "physical_analysis_interpretation", site_id=result["site_id"])
        self.p.identity.validate_refs(ctx, [ref.to_dict()])
        summary = {"objective": result["spec"]["objective"], "source_provenance": result["observation_provenance"],
            "model_manifest": result["model_manifest"], "ranking_basis": result["ranking_basis"], "warnings": result["warnings"],
            "models": [{k: m[k] for k in ("model_id", "status", "rationale", "calibration", "holdout_evaluation", "uncertainty") if k in m} |
                {"predictions": {k: m["prediction"][k] for k in ("completion_time_h", "minimum_critical_margin_c", "violations", "warnings")} if m.get("prediction") else None,
                 "error": m.get("error"), "missing_inputs": m.get("applicability")} for m in result["models"]]}
        response = self.p.gateway.run(TaskRequest("comparison_explanation", ctx,
            system="You assist process engineers reviewing physical models. Return JSON with explanation (string), source_refs (list containing the supplied analysis reference), model_tradeoffs (list of strings), limitations (list of strings), and verification_experiments (list of strings). Distinguish observations, calculations and hypotheses. Model rank or LLM qualification never establishes scientific validation. Do not invent measurements, spatial fields, calibrated probabilities or manufacturing outcomes.",
            prompt=json.dumps(summary, sort_keys=True), inputs=[ref.to_dict()], use_cache=False, timeout_s=45., prompt_version=PIPELINE_VERSION))
        if response.status != "completed":
            return {"status": "agent_unavailable", "gateway_run": response.to_dict(), "interpretation": None}
        data = response.output or {}
        required = {"explanation", "source_refs", "model_tradeoffs", "limitations", "verification_experiments"}
        if set(data) != required or not isinstance(data["explanation"], str) or not isinstance(data["source_refs"], list) or any(not isinstance(data[key], list) or
                not all(isinstance(item, str) for item in data[key]) for key in required-{"explanation", "source_refs"}):
            return {"status": "invalid_agent_interpretation", "gateway_run": response.to_dict(), "interpretation": None}
        data = {"summary": data["explanation"], **{k: v for k, v in data.items() if k != "explanation"}}
        with self.p.store.transaction(ctx.actor_id) as tx:
            self.p.identity.validate_refs(ctx, [ref.to_dict()], tx=tx)
            artifact = self.p.evidence.record_derived(ctx, "physical_analysis_interpretation", {
                "site_id": result["site_id"], "analysis_id": result_id, "classification": "agent_interpretation_requires_review",
                "gateway_run_id": response.run_id, "review_state": "draft_requires_review", **data},
                inputs=[ref], produced_by={"method": "comparison_explanation", "gateway_run_id": response.run_id})
        return {"status": "interpretation_created", "gateway_run": response.to_dict(), "interpretation": artifact}

    def agent_tools(self, ctx):
        """Attach these host-owned callbacks to the existing Prime harness.

        All ordinary Prime tools and shared call budgets remain in place.
        Source availability is checked against the bridge's immutable as_of.
        """
        def available(kind, rid, as_of):
            def visit(ref, seen):
                key = (ref["kind"], ref["id"])
                if key in seen:
                    return
                rec = self.p.store.read().require(ctx.tenant_id, *key)
                generated = rec.state.get("source_system") in {"scientific-model-catalog", "process-analysis-assumptions"}
                if not generated and rec.state.get("recorded_at") and as_of and parse_iso(rec.state["recorded_at"]) > parse_iso(as_of):
                    raise PermissionError("physical-analysis source was not available at the agent evidence cutoff")
                for source in rec.state.get("inputs", []):
                    visit(source, seen | {key})
            visit({"kind": kind, "id": rid}, set())
        def available_source(source_id, as_of):
            source, _ = self._source(ctx, source_id, 0)
            available(source["source_record_kind"], source_id, as_of)
        def catalog(*, simulation_id=None, candidate_index=0, as_of=None, scopes=None):
            if simulation_id:
                available_source(simulation_id, as_of)
            return {"evidence_ids": [], **self.models(ctx, simulation_id, candidate_index)}
        def prepare(*, spec, as_of=None, scopes=None):
            available_source(spec["simulation_id"], as_of)
            return {"evidence_ids": [], "plan": self.prepare(ctx, spec, authored_by_agent=True)}
        def run(*, plan_id, as_of=None, scopes=None):
            available("physical_analysis_plan", plan_id, as_of)
            return {"evidence_ids": [], "analysis": self.execute(ctx, plan_id)}
        def read(*, result_id, as_of=None, scopes=None):
            available("physical_analysis_result", result_id, as_of)
            return {"evidence_ids": [], "analysis": self.get_result(ctx, result_id)}
        def propose_adapter(*, request, as_of=None, scopes=None):
            available_source(request["simulation_id"], as_of)
            return {"evidence_ids": [], "proposal": self.propose_adapter(ctx, request)}
        return {"physical_models_catalog": catalog, "physical_analysis_prepare": prepare,
                "physical_analysis_execute": run, "physical_analysis_read": read,
                "physical_model_propose_adapter": propose_adapter}
