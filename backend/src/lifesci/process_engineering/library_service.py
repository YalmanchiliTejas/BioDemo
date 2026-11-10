"""Family-aware operations mixed into the EXISTING ProcessAnalysisService.

All configurations, datasets, plans, checkpoints and results use existing
EvidenceService records and dependency invalidation. This is not a second
registry, agent runtime or evidence store.
"""

from copy import deepcopy
import json
import math
from time import perf_counter

from ..evidence import EvidenceRef
from ..ids import content_hash
from .library_schemas import ConfigurationIn, DatasetIn, LibraryPipelineSpec, ModelExtensionIn
from .contracts import value_at, predict, contract, fit_runs, completed
from .engine import SolverBudget
from . import capability, hybrid, uncertainty, decisions


class LibraryOperations:
    def _library_memory(self, ctx, kind, state, seen=None):
        seen = set() if seen is None else seen
        if len(seen) > 2048:
            raise PermissionError("Scientific lineage exceeds bounded privacy traversal")
        self.p.memory.require_record(ctx, kind, state)
        for ref in state.get("inputs", []):
            key = (ref["kind"], ref["id"])
            if key in seen:
                continue
            seen.add(key)
            rec = self.p.store.read().require(ctx.tenant_id, *key)
            self._library_memory(ctx, rec.kind, rec.state, seen)

    @staticmethod
    def is_library_record(kind, state):
        if kind in ("physical_model_dataset", "physical_model_checkpoint", "physical_interval_calibration"):
            return True
        if kind in ("physical_analysis_plan", "physical_analysis_result"):
            return isinstance(state.get("spec"), dict) and state["spec"].get("mode") == "model_library"
        return (
            kind == "physical_analysis_context"
            and isinstance(state.get("workspace"), dict)
            and state["workspace"].get("audience") == "model_library"
        )

    def _library_record(self, ctx, kind, rid):
        record = self.p.evidence.read_derived(ctx, kind, rid)
        self.p.identity.validate_refs(
            ctx, [{"kind": kind, "id": rid, "revision": record["revision"], "site_id": record["site_id"]}]
        )
        self._library_memory(ctx, kind, record)
        return record

    def _json_source(self, ctx, ref):
        ref = ref.model_dump() if hasattr(ref, "model_dump") else ref
        self.p.identity.validate_refs(ctx, [ref])
        if ref["kind"] == "evidence":
            rec = self.p.store.read().require(ctx.tenant_id, "evidence", ref["id"])
            self._library_memory(ctx, "evidence", rec.state)
            return json.loads(self.p.evidence.original(ctx, ref["id"], revision=ref["revision"]))
        raise ValueError(
            "Configurations and run imports require original JSON evidence, not an assistant reply or arbitrary record kind"
        )

    def create_configuration(self, ctx, request):
        request = ConfigurationIn.model_validate(request)
        self.p.identity.require(ctx, "propose", "physical_analysis_context", site_id=request.site_id)
        refs = [r.model_dump() for r in request.basis]
        self.p.identity.validate_refs(ctx, refs)
        # Full configuration from a versioned JSON packet; no invented measured
        # equipment/material/recipe values hidden inside caller parameters.
        source = self._json_source(ctx, refs[0])
        document = value_at(source, request.source_path) if request.source_path else source
        if document != request.config:
            raise ValueError(
                "Configuration differs from its evidence source; ingest a labelled scenario/assumption first"
            )
        if (
            str(request.config.get("evidence_classification", source.get("evidence_classification", ""))).startswith(
                "synthetic"
            )
            and request.classification != "synthetic_assumption"
        ):
            raise ValueError("Synthetic inputs must retain synthetic classification")
        adapter = self.catalog.get(request.model_id)
        app = adapter.applicability(request.config)
        if not app["applicable"]:
            raise ValueError("Configuration not applicable: " + str(app))
        catalog_ref = self._catalog_ref(ctx, request.site_id)
        with self.p.store.transaction(ctx.actor_id) as tx:
            self.p.identity.validate_refs(ctx, refs, tx=tx)
            return self.p.evidence.record_derived(
                ctx,
                "physical_analysis_context",
                {
                    "site_id": request.site_id,
                    "label": request.label,
                    "model_id": request.model_id,
                    "process_family": adapter.describe()["process_family"],
                    "configuration_contract": contract(adapter),
                    "input_bundle": {
                        "family": adapter.describe()["process_family"],
                        "config": request.config,
                        "observations": [],
                        "observation_provenance": request.classification,
                        "parameter_manifest": {
                            "category": request.classification,
                            "source_refs": refs,
                            "assumptions": request.assumptions,
                        },
                    },
                    "workspace": {
                        "audience": "model_library",
                        "label": request.label,
                        "options": [{"config": request.config}],
                    },
                    "configuration_request": request.model_dump(),
                    "classification": request.classification,
                    "model_version": adapter.version,
                    "model_digest": adapter.digest,
                    "review_state": "draft_requires_review",
                },
                inputs=[*[EvidenceRef(**r) for r in refs], catalog_ref],
                produced_by={"method": "evidence_backed_model_configuration"},
            )

    def import_runs(self, ctx, request):
        request = DatasetIn.model_validate(request)
        self.p.identity.require(ctx, "propose", "physical_model_dataset", site_id=request.site_id)
        source = self._json_source(ctx, request.source)
        runs = value_at(source, request.source_path)
        if len(json.dumps(runs)) > 4 * 1024 * 1024:
            raise ValueError("Run packet exceeds 4 MiB; import a bounded study")
        roles = hybrid.partition(runs, site_holdout=request.site_holdout)
        refs = [EvidenceRef(**request.source.model_dump())]
        for run in runs:
            # Separate per-site original evidence makes inherited permissions
            # and revocation effective for every downstream multi-site result.
            self.p.identity.require(ctx, "propose", "evidence", site_id=run["site_id"])
            item = self.p.evidence.ingest(
                ctx,
                source_system="pharmaceutical-run-packet",
                source_record_id=content_hash({"source": request.source.model_dump(), "run_id": run["run_id"]}),
                content=json.dumps(run, sort_keys=True).encode(),
                media_type="application/json",
                site_id=run["site_id"],
                event_time=None,
                metadata={
                    "classification": run["evidence_classification"],
                    "batch_id": run["batch_id"],
                    "origin_source_ref": request.source.model_dump(),
                    "independence": "asserted by source provenance; not inferred from IDs",
                },
            )
            refs.append(EvidenceRef("evidence", item["evidence_id"], item["revision"], run["site_id"]))
        with self.p.store.transaction(ctx.actor_id) as tx:
            self.p.identity.validate_refs(ctx, [r.to_dict() for r in refs], tx=tx)
            return self.p.evidence.record_derived(
                ctx,
                "physical_model_dataset",
                {
                    "site_id": request.site_id,
                    "label": request.label,
                    "runs": runs,
                    "site_holdout": request.site_holdout,
                    "partition_counts": {k: len({(r["site_id"], r["batch_id"]) for r in v}) for k, v in roles.items()},
                    "packet_hash": content_hash(runs),
                    "limitations": [
                        "Independence must be justified by experimental provenance; assigning IDs cannot establish it."
                    ],
                },
                inputs=refs,
                produced_by={"method": "whole_batch_model_dataset_import"},
            )

    def refresh_configuration(self, ctx, context_id):
        # The stale derived value is never used as scientific evidence. Read the
        # original authorized packet at its CURRENT revision and rebuild instead.
        prior = self.p.store.read().require(ctx.tenant_id, "physical_analysis_context", context_id)
        self.p.identity.require(ctx, "read", "physical_analysis_context", context_id, site_id=prior.state["site_id"])
        self._library_memory(ctx, "physical_analysis_context", prior.state)
        request = deepcopy(prior.state.get("configuration_request"))
        if not request:
            raise ValueError("Legacy context uses its existing reconstruction path")
        for ref in request["basis"]:
            rec = self.p.store.read().require(ctx.tenant_id, ref["kind"], ref["id"])
            ref["revision"] = rec.revision
        source = self._json_source(ctx, request["basis"][0])
        request["config"] = value_at(source, request["source_path"]) if request["source_path"] else source
        fresh = self.create_configuration(ctx, request)
        return {
            "context": fresh,
            "supersedes_context_id": context_id,
            "next_step": "Prepare/execute the affected analysis against this new evidence snapshot. Stale fitted/calibrated artifacts must be rebuilt, not silently reused.",
        }

    def prepare_library(self, ctx, request, *, basis_refs=(), agent_run_id=None, authored_by_agent=False):
        spec = LibraryPipelineSpec.model_validate(request)
        source = self._library_record(ctx, "physical_analysis_context", spec.simulation_id)
        if source.get("model_id") != spec.model_id:
            raise ValueError("Context and model ID differ")
        self.p.identity.require(ctx, "propose", "physical_analysis_plan", site_id=source["site_id"])
        adapter = self.catalog.get(spec.model_id)
        self._validate_library_options(spec)
        if spec.operation in ("train_hybrid", "adapt_hybrid") and not hybrid.capabilities(adapter.id)["supported"]:
            raise ValueError("Hybrid adaptation unsupported for this adapter")
        references = [
            EvidenceRef("physical_analysis_context", source["id"], source["revision"], source["site_id"]),
            *basis_refs,
        ]
        snapshot = {"config": deepcopy(source["input_bundle"]["config"])}
        for key, kind in [
            ("dataset_id", "physical_model_dataset"),
            ("checkpoint_id", "physical_model_checkpoint"),
            ("calibration_id", "physical_interval_calibration"),
            ("receiver_context_id", "physical_analysis_context"),
        ]:
            rid = getattr(spec, key)
            if rid:
                rec = self._library_record(ctx, kind, rid)
                if rec["site_id"] != source["site_id"]:
                    raise PermissionError(
                        "Attach receiving-site data through explicitly authorized source records in this workspace"
                    )
                if key in ("checkpoint_id", "calibration_id") and rec["runner_manifest"] != self._runner_manifest():
                    raise ValueError("Fitted/calibrated implementation changed; rebuild")
                if key == "receiver_context_id" and rec.get("model_id") != spec.model_id:
                    raise ValueError("Receiver model differs")
                snapshot[key] = rec
                references.append(EvidenceRef(kind, rid, rec["revision"], rec["site_id"]))
        if (
            spec.operation in ("fit", "train_hybrid", "adapt_hybrid", "calibrate_intervals", "evaluate_intervals")
            and not spec.dataset_id
        ):
            raise ValueError("A partitioned evidence dataset is required")
        if spec.operation == "adapt_hybrid" and not spec.checkpoint_id:
            raise ValueError("Adaptation requires an immutable source checkpoint")
        if spec.operation in ("predict_intervals", "evaluate_intervals") and not spec.calibration_id:
            raise ValueError("Frozen interval calibration artifact required, including explicit uncalibrated status")
        references.append(self._catalog_ref(ctx, source["site_id"]))
        pinned = {
            **adapter.describe(),
            "analysis_contract": contract(adapter),
            "hybrid_adaptation": hybrid.capabilities(adapter.id),
        }
        with self.p.store.transaction(ctx.actor_id) as tx:
            self.p.identity.validate_refs(ctx, [r.to_dict() for r in references], tx=tx)
            return self.p.evidence.record_derived(
                ctx,
                "physical_analysis_plan",
                {
                    "site_id": source["site_id"],
                    "pipeline_version": "family_analysis_1",
                    "spec": spec.model_dump(),
                    "source_snapshot": snapshot,
                    "pinned_models": [pinned],
                    "runner_manifest": self._runner_manifest(),
                    "steps": [{"id": spec.operation, "implementation": "family_analysis_1"}],
                    "plan_hash": content_hash(
                        {
                            "spec": spec.model_dump(),
                            "snapshot": snapshot,
                            "model": pinned,
                            "runner": self._runner_manifest(),
                        }
                    ),
                    "authored_by": {
                        "actor_id": ctx.actor_id,
                        "gateway_run_id": agent_run_id,
                        "kind": "agent" if authored_by_agent else "person",
                    },
                    "review_state": "plan_ready_for_execution",
                },
                inputs=references,
                produced_by={"method": "family_analysis_prepare"},
            )

    @staticmethod
    def _validate_library_options(spec):
        fields = {
            "simulate": {"prediction_mode"},
            "compare": {"metrics"},
            "fit": {"parameter", "bounds"},
            "sensitivity": {"parameter", "values", "observations"},
            "train_hybrid": {"ensemble_size", "seed"},
            "adapt_hybrid": {"ensemble_size", "seed"},
            "calibrate_intervals": {"prediction_mode", "alpha", "samples", "seed", "distributions"},
            "predict_intervals": {"observations"},
            "evaluate_intervals": set(),
            "assess_transfer": {"criteria", "tolerances"},
            "experiments": {"candidates", "decision"},
        }
        extra = set(spec.options) - fields[spec.operation]
        if extra:
            raise ValueError("Unsupported operation options: " + str(sorted(extra)))

    def execute_library(self, ctx, plan, *, commit_guard=None):
        spec = LibraryPipelineSpec.model_validate(plan["spec"])
        snapshot = plan["source_snapshot"]
        adapter = self.catalog.get(spec.model_id)
        if (
            plan["runner_manifest"] != self._runner_manifest()
            or plan["pinned_models"][0]["implementation_digest"] != adapter.digest
        ):
            raise ValueError("Model/runner changed; regenerate the plan")
        self.p.identity.require(ctx, "propose", "physical_analysis_result", site_id=plan["site_id"])
        ref = EvidenceRef("physical_analysis_plan", plan["id"], plan["revision"], plan["site_id"])
        self.p.identity.validate_refs(ctx, [ref.to_dict()])
        budget = SolverBudget(spec.max_solver_calls, spec.max_wall_seconds)
        status = "completed"
        error = None
        output = {}
        artifacts = []
        try:
            output = self._library_compute(spec, snapshot, adapter, budget)
            if perf_counter() - budget.started > budget.seconds:
                raise RuntimeError("Operation exceeded wall-time budget; scientific result withheld")
            with self.p.store.transaction(ctx.actor_id) as tx:
                self.p.identity.validate_refs(ctx, [ref.to_dict()], tx=tx)
                if commit_guard:
                    commit_guard(tx)
                for name, kind in [
                    ("checkpoint", "physical_model_checkpoint"),
                    ("interval_calibration", "physical_interval_calibration"),
                ]:
                    if name in output:
                        item = self.p.evidence.record_derived(
                            ctx,
                            kind,
                            {
                                "site_id": plan["site_id"],
                                name: output[name],
                                "runner_manifest": plan["runner_manifest"],
                                "review_state": "draft_requires_review",
                                "plan_id": plan["id"],
                            },
                            inputs=[ref],
                            produced_by={"method": spec.operation},
                        )
                        artifacts.append(
                            {
                                "kind": kind,
                                "id": item["id"],
                                "revision": self.p.store.read().require(ctx.tenant_id, kind, item["id"]).revision,
                            }
                        )
        except (ValueError, RuntimeError, KeyError, TypeError, ArithmeticError) as exc:
            status = "failed"
            error = {"type": type(exc).__name__, "message": str(exc)}
            output = {}
        with self.p.store.transaction(ctx.actor_id) as tx:
            if commit_guard:
                commit_guard(tx)
            # A correction/cancellation during computation cannot commit stale authority.
            self.p.identity.validate_refs(ctx, [ref.to_dict()], tx=tx)
            return self.p.evidence.record_derived(
                ctx,
                "physical_analysis_result",
                {
                    "site_id": plan["site_id"],
                    "plan_id": plan["id"],
                    "pipeline_version": "family_analysis_1",
                    "spec": spec.model_dump(),
                    "plan_hash": plan["plan_hash"],
                    "runner_manifest": plan["runner_manifest"],
                    "model_manifest": plan["pinned_models"],
                    "execution_status": status,
                    "output": output,
                    "error": error,
                    "artifacts": artifacts,
                    "resource_usage": {
                        "solver_calls": budget.calls,
                        "maximum_solver_calls": budget.maximum,
                        "runtime_seconds": perf_counter() - budget.started,
                        "wall_time_policy": "Admission and completion checks plus bounded numerical evaluations; not a hard worker-kill deadline.",
                    },
                    "models": [
                        {"model_id": adapter.id, "status": status, "error": error["message"] if error else None}
                    ],
                    "review_state": "requires_engineering_review",
                    "warnings": [
                        "Conditional scientific calculation; not manufacturing approval, process validation or a calibrated risk probability."
                    ],
                },
                inputs=[ref, *[EvidenceRef(a["kind"], a["id"], a["revision"], plan["site_id"]) for a in artifacts]],
                produced_by={"method": spec.operation},
            )

    def _library_compute(self, spec, snapshot, adapter, budget):
        cfg = snapshot["config"]
        options = spec.options
        data = snapshot.get("dataset_id")
        roles = hybrid.partition(data["runs"], site_holdout=data["site_holdout"]) if data else None
        cp = (snapshot.get("checkpoint_id") or {}).get("checkpoint")
        cal = (snapshot.get("calibration_id") or {}).get("interval_calibration")
        if cp and cp["model_id"] != adapter.id:
            raise ValueError("Checkpoint belongs to another family/model")
        mode = options.get("prediction_mode", "hybrid" if cp else "physics")
        if (
            mode == "hybrid"
            and cp
            and cp.get("negative_transfer")
            and spec.operation not in ("adapt_hybrid", "train_hybrid")
        ):
            raise ValueError(
                "Negative transfer detected; adapted prediction promotion withheld. Review source/refit/physics alternatives."
            )
        def run(c):  # one model for every operation: the attached checkpoint when there is one, else physics
            return budget.run(adapter, c) if mode == "physics" else budget.call(lambda: hybrid.run_hybrid(adapter, c, cp, mode=mode))

        if spec.operation == "simulate":
            result = run(cfg)
            if not completed(result):
                return {"simulation": result, "scientific_status": "stopped_or_failed", "decision": "withheld"}
            return {"simulation": result}
        if spec.operation in ("compare", "assess_transfer"):
            if "receiver_context_id" not in snapshot:
                raise ValueError("Receiving configuration required")
            receiver = snapshot["receiver_context_id"]["input_bundle"]["config"]
            a, b = run(cfg), run(receiver)
            if spec.operation == "assess_transfer":
                intervals = {}
                if cal and cal.get("q") is not None:
                    grid = [{"observable": o, "unit": u, "coordinate": x, "value": 0.0} for o, u, x in cal["basis"]]
                    for side, c in (("donor_interval", cfg), ("receiver_interval", receiver)):
                        try:
                            intervals[side] = uncertainty.interval_prediction(
                                adapter, c, grid, cal, checkpoint=cp, budget=budget, components=False)
                        except ValueError:
                            intervals[side] = None  # a different model version or basis: no range, so no verdict
                tolerances = _tolerances(adapter, cfg, receiver, options.get("tolerances") or [])
                corners = {}
                for side, c, wanted in (("receiver_corners", receiver, True),
                                        ("donor_corners", cfg, any(k.get("method") == "noninferiority" for k in options["criteria"]))):
                    used = [t for t in tolerances if t["applies_to"] in (side.split("_")[0], "both")]
                    corners[side] = _corners(run, c, used) if used and wanted else []
                out = decisions.transfer_assessment(adapter, a, b, options["criteria"], **intervals, **corners)
                return {**out, "tolerances": tolerances, "what_changes": capability.changes(cfg, receiver),
                        "equipment_capability": capability.capabilities(adapter, cfg, a, receiver, b),
                        "sending_result": _summary(a), "receiving_result": _summary(b)}
            comparisons = {}
            for metric in options["metrics"]:
                try:
                    comparisons[metric] = {
                        "source": value_at(a, metric),
                        "receiver": value_at(b, metric),
                        "unit": contract(adapter)["observables"].get(metric),
                    }
                except (KeyError, TypeError):
                    comparisons[metric] = {"status": "unsupported_observable"}
            return {
                "source": a,
                "receiver": b,
                "metrics": comparisons,
                "classification": "conditional_receiving_site_comparison_not_validation",
            }
        if spec.operation == "fit":
            return fit_runs(adapter, roles["train"], options["parameter"], options["bounds"], budget)
        if spec.operation == "sensitivity":
            values = options["values"]
            if not 1 <= len(values) <= 24:
                raise ValueError("1..24 explicit sensitivity scenarios required")
            rows = []
            for value in values:
                c = deepcopy(cfg)
                from .contracts import set_value

                set_value(c, options["parameter"], value)
                try:
                    p, r = predict(adapter, c, options["observations"], runner=lambda c: budget.run(adapter, c))
                    rows.append(
                        {
                            "value": value,
                            "predictions": p.tolist(),
                            "violations": r.get("violations", []),
                            "status": "completed",
                        }
                    )
                except (ValueError, KeyError, RuntimeError) as exc:
                    rows.append({"value": value, "status": "failed", "error": str(exc)})
            return {
                "scenarios": rows,
                "calibration_status": "uncalibrated",
                "scope": "Declared sensitivity range, not calibrated uncertainty",
            }
        if spec.operation in ("train_hybrid", "adapt_hybrid"):
            return {
                "checkpoint": hybrid.train(
                    adapter,
                    data["runs"],
                    parent=cp if spec.operation == "adapt_hybrid" else None,
                    seed=options.get("seed", 1),
                    ensemble_size=options.get("ensemble_size", 3),
                    site_holdout=data["site_holdout"],
                    budget=budget,
                )
            }
        if spec.operation == "calibrate_intervals":
            return {
                "interval_calibration": uncertainty.calibrate_intervals(
                    adapter,
                    roles["calibration"],
                    checkpoint=cp,
                    mode=mode,
                    alpha=options.get("alpha", 0.1),
                    samples=options.get("samples", 8),
                    seed=options.get("seed", 1),
                    distributions=options.get("distributions", ()),
                    budget=budget,
                )
            }
        if spec.operation == "predict_intervals":
            return uncertainty.interval_prediction(
                adapter, cfg, options["observations"], cal, checkpoint=cp, budget=budget
            )
        if spec.operation == "evaluate_intervals":
            return uncertainty.evaluate_intervals(adapter, roles["test"], cal, checkpoint=cp, budget=budget)
        if spec.operation == "experiments":
            return decisions.rank_experiments(
                adapter, cfg, options["candidates"], options["decision"], checkpoint=cp, budget=budget
            )
        raise ValueError("Unsupported family operation")

    def library_review(self, ctx, result_id, owner_id):
        result = self._library_record(ctx, "physical_analysis_result", result_id)
        if result["execution_status"] != "completed":
            raise ValueError("Cannot propose scientific acceptance of a failed analysis")
        ref = {
            "kind": "physical_analysis_result",
            "id": result_id,
            "revision": result["revision"],
            "site_id": result["site_id"],
        }
        return self.p.actions.propose(
            ctx,
            target_system="engineering-review",
            operation="review_physical_analysis",
            target_id=result_id,
            payload={
                "analysis_id": result_id,
                "model_manifest": result["model_manifest"],
                "operation": result["spec"]["operation"],
                "questions": [
                    "Are measurement bases and product-quality criteria compatible?",
                    "Are independent batches and calibration assumptions justified?",
                    "Review domain limits, negative transfer, numerical failures and missing mechanisms.",
                ],
            },
            basis=[ref],
            rationale=result["spec"]["objective"],
            expected_result="Review model evidence and required characterization; no manufacturing dispatch.",
            owner_id=owner_id,
            site_id=result["site_id"],
            constraints=result["warnings"],
            follow_up_measure="Independent receiving-site prediction error and decision resolution",
        )

    def propose_model_extension(self, ctx, request):
        """Turn an identified missing/changed mechanism into a review proposal.

        The registered equations, digest, checkpoints and calibrations are left
        untouched; an approved proposal is a specification for a new versioned
        adapter, not an instruction to modify the current one.
        """
        request = ModelExtensionIn.model_validate(request)
        context = self._library_record(ctx, "physical_analysis_context", request.context_id)
        if context.get("model_id") != request.model_id:
            raise ValueError("Extension must target the model of the supplied configuration")
        if request.model_id not in self.catalog.adapters:
            raise ValueError("Model is not registered; use a new adapter proposal instead")
        adapter = self.catalog.get(request.model_id)
        current = contract(adapter)
        clashes = sorted({p.name for p in request.new_parameters} & set(current["fit_parameters"]))
        if clashes:
            raise ValueError(
                "Existing parameters are refitted with the 'fit' operation, not a mechanism extension: " + ", ".join(clashes)
            )
        basis = [b.model_dump() for b in request.basis]
        for ref in basis:
            if ref["site_id"] != context["site_id"]:
                raise PermissionError("Extension evidence must belong to the configuration's site")
            if ref["kind"] in ("physical_analysis_result", "physical_model_checkpoint", "physical_interval_calibration"):
                self._library_record(ctx, ref["kind"], ref["id"])
        context_ref = {
            "kind": "physical_analysis_context",
            "id": context["id"],
            "revision": context["revision"],
            "site_id": context["site_id"],
        }
        self.p.identity.validate_refs(ctx, [context_ref, *basis])
        return self.p.actions.propose(
            ctx,
            target_system="engineering-review",
            operation="review_model_extension",
            target_id=request.model_id,
            payload={
                "extension_request": request.model_dump(),
                "current_model": {
                    "model_id": adapter.id,
                    "version": adapter.version,
                    "implementation_digest": adapter.digest,
                    "model_kind": current.get("model_kind"),
                    "axis": current["axis"],
                    "observables": current["observables"],
                    "fit_parameters": current["fit_parameters"],
                    "hybrid_adaptation": hybrid.capabilities(adapter.id),
                },
                "registry_status": "unchanged",
                "execution_permission": "none",
                "required_checks": [
                    "Dimensional consistency of every changed term and new parameter",
                    "Stated limiting case reproduces the current registered model",
                    "Species, mass and energy balances still close in unit tests",
                    "New parameters are identifiable from the named measurements",
                    "Release as a new model version; checkpoints and interval calibrations bound to the current digest must be rebuilt",
                ],
            },
            basis=[context_ref, *basis],
            rationale=request.mechanism_change,
            expected_result="Reviewed extension specification; implementation, registration and validation remain separate explicit steps.",
            owner_id=request.owner_id,
            site_id=context["site_id"],
            constraints=[
                "Registered equations are not modified by this proposal.",
                "No generated solver code is executed or dynamically imported.",
            ],
            follow_up_measure="Held-out prediction error of the extended model against the unchanged model on independent batches",
        )

    def library_interpret(self, ctx, result_id):
        from ..gateway import TaskRequest

        result = self.get_result(ctx, result_id)
        ref = EvidenceRef("physical_analysis_result", result_id, result["revision"], result["site_id"])
        self.p.identity.require(ctx, "propose", "physical_analysis_interpretation", site_id=result["site_id"])
        summary = {
            k: result[k] for k in ("spec", "model_manifest", "execution_status", "error", "resource_usage", "warnings")
        }
        # No freeze-drying summaries are imposed on other model families.
        summary["family_result"] = result["output"]
        response = self.p.gateway.run(
            TaskRequest(
                "comparison_explanation",
                ctx,
                system="Interpret this family-specific scientific result. Return JSON with summary and limitations. Never invent unpredicted quality, manufacturing approval, calibrated risk probabilities or customer validation. Distinguish synthetic calibration from real coverage.",
                prompt=json.dumps(summary, sort_keys=True),
                inputs=[ref.to_dict()],
                use_cache=False,
                timeout_s=45.0,
                prompt_version="family_analysis_1",
            )
        )
        if response.status != "completed":
            return {"status": "agent_unavailable", "gateway_run": response.to_dict(), "interpretation": None}
        data = response.output or {}
        if (
            not isinstance(data.get("summary"), str)
            or not isinstance(data.get("limitations"), list)
            or not all(isinstance(x, str) for x in data["limitations"])
        ):
            return {"status": "invalid_agent_interpretation", "gateway_run": response.to_dict(), "interpretation": None}
        with self.p.store.transaction(ctx.actor_id) as tx:
            self.p.identity.validate_refs(ctx, [ref.to_dict()], tx=tx)
            artifact = self.p.evidence.record_derived(
                ctx,
                "physical_analysis_interpretation",
                {
                    "site_id": result["site_id"],
                    "analysis_id": result_id,
                    "summary": data["summary"],
                    "limitations": data["limitations"],
                    "classification": "agent_interpretation_requires_review",
                    "review_state": "draft_requires_review",
                },
                inputs=[ref],
                produced_by={"method": "comparison_explanation", "gateway_run_id": response.run_id},
            )
        return {"status": "interpretation_created", "gateway_run": response.to_dict(), "interpretation": artifact}

    @staticmethod
    def library_agent_view(record):
        """Do not feed stored final-evaluation/calibration observations into planning."""
        result = deepcopy(record)
        if "runs" in result:
            result.pop("runs")
        for value in (result.get("source_snapshot") or {}).values():
            if isinstance(value, dict):
                value.pop("runs", None)
        return result


TOLERANCE_BASES = ("spec_tolerance", "fit_uncertainty", "engineering_assumption", "measured_range")
MAX_TOLERANCES = 4  # 2**4 = 16 corner runs per site


def _tolerances(adapter, donor, receiver, raw):
    """Stated low/high values for uncertain inputs, each with where it comes from; checked against the model."""
    from .contracts import input_units

    if len(raw) > MAX_TOLERANCES:
        raise ValueError(f"At most {MAX_TOLERANCES} tolerances (2^n corner runs); keep the most uncertain terms")
    units, out = input_units(adapter), []
    for t in raw:
        if not isinstance(t, dict) or set(t) - {"path", "unit", "low", "high", "basis", "source", "applies_to"}:
            raise ValueError("Tolerance fields: path, unit, low, high, basis, source, applies_to")
        path, side = t.get("path"), t.get("applies_to", "receiver")
        if units.get(path) is None or units[path] != t.get("unit"):
            raise ValueError(f"Tolerance {path!r}: not a model input, or unit differs from {units.get(path)!r}")
        if t.get("basis") not in TOLERANCE_BASES or not str(t.get("source") or "").strip():
            raise ValueError(f"Tolerance {path!r}: basis must be one of {TOLERANCE_BASES}, with its source")
        if side not in ("receiver", "donor", "both"):
            raise ValueError("applies_to must be receiver, donor or both")
        lo, hi = float(t["low"]), float(t["high"])
        for c in ([receiver] if side == "receiver" else [donor] if side == "donor" else [donor, receiver]):
            nominal = float(value_at(c, path))
            if not (math.isfinite(lo) and math.isfinite(hi) and lo <= nominal <= hi and lo < hi):
                raise ValueError(f"Tolerance {path!r}: need low <= configured value ({nominal:g}) <= high")
        out.append({"path": path, "unit": t["unit"], "low": lo, "high": hi, "basis": t["basis"],
                    "source": str(t["source"])[:300], "applies_to": side})
    return out


def _corners(run, config, tolerances):
    from itertools import product
    from .contracts import set_value
    from .engine import BudgetExceeded

    out = []
    for values in product(*[(t["low"], t["high"]) for t in tolerances]):
        c = deepcopy(config)
        for t, v in zip(tolerances, values):
            set_value(c, t["path"], v)
        assignment = {t["path"]: v for t, v in zip(tolerances, values)}
        try:
            out.append({"assignment": assignment, **_summary(run(c))})
        except BudgetExceeded:
            raise
        except (ValueError, RuntimeError, ArithmeticError) as exc:
            out.append({"assignment": assignment, "status": "failed", "error": str(exc), "violations": []})
    return out


def _summary(result):
    """A run without its trajectory: enough to read outcomes, small enough to store per corner."""
    return {k: v for k, v in result.items() if k not in ("trajectory", "limitations", "solver")}
