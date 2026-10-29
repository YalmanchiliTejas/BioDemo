> The primary page now uses a [conversational workflow](conversation.md). The form-led model-selection controls described below are retained at `/process-simulation/advanced/`.

# Agent-selected physical models and reproducible review pipelines

The process-engineering workspace now separates **model choice**, **numerical execution**, **evaluation**, **visualization** and **human review**. The agent can choose registered models and generate a typed analysis plan. Solvers remain reproducible, independent scientific functions. Engineers can inspect the plan, author one directly, run it and review the evidence.

The user selected the boundary: **select registered models and propose new adapters for review**. This implementation does not execute newly generated solver code, download arbitrary model implementations or introduce another agent harness.

Read the [executed report and plots](model-selection-artifacts/report.md), [real browser verification](model-selection-artifacts/ui-verification.json), and [3D review screenshot](model-selection-artifacts/ui-vial-review.png). These are generated from actual calculations and interactions. The existing [published-source inventory](../research/freeze-drying-sources.md) and original frozen comparison/audit remain available.

## Use the workspace

Use the [existing launch/setup commands](README.md). After installing the updated frontend dependencies and restarting the API, open `http://127.0.0.1:5180/process-simulation/`.

1. Choose technology transfer or CDMO operation and inspect the input conditions.
2. Click **Start model selection**. This creates a versioned input context without running the hard-wired preset comparison. The old quick comparison remains optional.
3. Enter an engineering objective. **Ask agent to plan analysis** calls the existing `investigation_planning` gateway route with catalog metadata and authorized inputs. A successful response becomes a validated, persisted plan with agent provenance. Missing qualification/provider routing is displayed as unavailable; a plan is never fabricated.
4. Engineers can select models and **Save engineer-authored pipeline** using the same schema. To run the transient model, explicitly provide thermal assumptions or leave the model blocked until characterization is available. The example values are assumptions, not discovered facility properties.
5. Inspect the source/model versions, selection rationale, training/holdout boundary and pipeline phases, then **Execute saved pipeline**.
6. Review completion/constraint results, held-out discrepancy, coverage, uncertainty and model warnings. The validation-window chart uses the observed source controls; the full trajectory shows the prospective operating conditions.
7. Scrub the **3D engineering review** through executed states, rotate/zoom the camera, and export a review PNG. Export the complete pipeline JSON for numerical inspection.
8. **Ask agent to assess results** calls the existing `comparison_explanation` route. Any interpretation is a separate derived draft requiring review; it cannot qualify the model or approve a manufacturing action.
9. **Create engineering review** creates an existing version-bound proposal requiring an engineering reviewer. It does not dispatch anything. New-model requests use a separate adapter-review proposal and cannot modify the catalog.

The general app-shell agent dock is still a synthetic prototype. These planning/assessment buttons use the real gateway. The local demo uses the server's stored `demo-northfield/priya` identity, not authority from the shell's role selector. Existing source/site permissions and production identity boundaries remain in force.

## Current scientific model catalog

| Registered ID | Physical content | Additional inputs | Important limits |
|---|---|---|---|
| `lyo.kv_rp` | Existing quasi-steady shelf/vial heat transfer, Fourier frozen-layer conduction, evolving Rp and moving ice front | Published/reconstructed process inputs | No sensible-heat state, representative vial, prescribed pressure. |
| `lyo.transient_lumped` | Adds finite vial/product heat capacity and integrates interface-node temperature with ice mass using BDF | Vial heat capacity in J/K and initial product temperature in °C | Experimental lumped model, no resolved temperature field, constant ice specific heat approximation, forward sublimation only. |

Both adapters retain the source formulation/equipment assumptions. They do not predict final residual moisture, potency or release suitability. Above the imposed vapor/ice capacity ceiling, pressure-controlled forecasts are explicitly diagnostic extrapolations. An extra thermal state or lower synthetic discrepancy does not establish greater real-world accuracy.

The evaluator-only two-population reference from the earlier benchmark is **not** exposed as a selectable adapter. Hidden evaluation labels and future outputs do not enter the new planning prompts or observation partitions. The current catalog serves primary drying; another process family or resolved CFD/FEM analysis requires an implemented, reviewed adapter and suitable data/visualization contracts. A rendered 3D view does not provide those physics.

## Pipeline contract and scientific evaluation

A `PipelineSpec` contains a source context or prior calculation ID, operating candidate, objective, model IDs/rationales, optional explicitly classified thermal assumptions, calibration choice/window, evidence cutoff, temperature observable, requested views, uncertainty sample count/seed and solver budgets. IDs resolve only through the host catalog. Arbitrary import paths, scripts, unsupported model IDs, duplicate choices and invalid windows are rejected.

The trusted runner expands the plan into:

```text
validate sources/models
  → calibrate using the training window, if requested
  → simulate each selected model
  → evaluate distinct cutoff-visible holdout observations
  → sample declared parameter uncertainty
  → build charts and the 3D review artifact
```

The example partitions observations at 3 h and 6 h. Measurements are allowlisted and must satisfy both observation time and availability time. Calibration fits only a bounded Kv multiplier on the early temperature window; it does not simultaneously identify Rp, equipment capacity or a causal explanation. Later observations never enter that fit. Earlier CDMO diagnosis had fitted parameters on the full cutoff window, so the new pipeline deliberately discards those fitted modifiers and starts from the original coefficients.

Holdout evaluation executes the fitted model using the original observed control history. It does not compare unexecuted interventions against measurements. Prospective trajectories are calculated separately. RMSE is accompanied by point count and coverage; incomplete overlap is excluded from ranking. Without observations, no measured error or model ranking is reported. Synthetic and caller-unverified observations retain their provenance. The current scoring targets the explicitly selected temperature observable; mass-rate/pressure and final product quality need separate evaluation.

Uncertainty uses common seeded positive Kv/Rp draws across models. The example does not sample thermal-capacity uncertainty. Frequencies and quantiles describe the assumed distributions; they are not calibrated real failure probabilities. Model and runner source digests, solver/environment versions, parameters, training/holdout rows, schedules, random seed and numerical failures remain in the exported record.

Budgets limit requested model count, solver-call admission and wall-time admission before each bounded solver call. They are not a claim of hard process-kill isolation. Exhaustion, missing parameters and failed calculations produce explicit partial/blocked results rather than invented metrics. Application plans do not authorize production actions.

## What the 3D view represents

Three.js renders a representative cylindrical vial using the retained inner/outer diameters and calculated frozen-fill height. Ice and dried-layer heights come from each saved solver state. Color encodes one interface temperature. The white plane marks the modeled drying front. The glass body height and shelf are schematic.

There is no interpolation into a claimed spatial temperature field, facility CAD model or vapor-flow simulation. A real distributed model would need independently supported geometry, boundary conditions, material fields, mesh/time convergence and validation evidence. The current view exposes its geometry provenance and model limits next to the controls. It renders on demand, supports manual camera/time controls, disposes its WebGL resources and leaves numeric results available if WebGL is unavailable.

## Existing agent integration

The API planner uses `ModelGateway` and its existing qualification, spend, telemetry and current-evidence checks. The assessment uses the existing schema for comparison explanations. Scientific validation is separate from qualification of either LLM route.

For an existing Prime host authorized for this work:

```python
# Use an appropriately narrowed delegated context, not an unrestricted service identity.
harness.additional_tools.update(platform.process_models.analysis.agent_tools(agent_ctx))
```

The optional host callbacks are:

| Tool | Result |
|---|---|
| `physical_models_catalog` | Registered model metadata, versions, input sufficiency and limitations |
| `physical_analysis_prepare` | Saved validated plan, pinned inputs/software and agent authorship |
| `physical_analysis_execute` | Bounded scientific calculations and review artifacts |
| `physical_analysis_read` | Permission-checked model results for subsequent agent reasoning |
| `physical_model_propose_adapter` | Review proposal only; never registration or execution |

These callbacks use the existing bridge's shared call accounting and fixed historical cutoff. Ordinary evidence/analysis tools remain available. Source availability is checked recursively against the bridge cutoff; generated catalog/assumption records are treated as calculation metadata rather than newly observed future manufacturing measurements. MSAT and engineering role skills list these capabilities; agents gain no approval authority.

## Additive API

| Route | Purpose |
|---|---|
| `POST /v1/process-model/contexts` | Version inputs without selecting/executing a predictive adapter |
| `GET /v1/process-model/catalog` | Inspect registered models; optionally check an authorized source context |
| `POST /v1/process-model/pipelines/agent-plan` | Actual gateway planning attempt and validated plan, if available |
| `POST /v1/process-model/pipelines` | Save an engineer/agent-authored typed plan |
| `GET /v1/process-model/pipelines/{id}` | Inspect the saved plan |
| `POST /v1/process-model/pipelines/{id}/execute` | Execute the pinned plan |
| `GET /v1/process-model/analyses/{id}` | Inspect results, partitions, geometry frames and provenance |
| `POST /v1/process-model/analyses/{id}/agent-assessment` | Separate agent interpretation of calculated evidence |
| `POST /v1/process-model/analyses/{id}/review` | Existing engineering-review proposal |
| `POST /v1/process-model/adapter-proposals` | Propose a reviewed new adapter specification |

For compatibility, pipeline requests call their source field `simulation_id`; it accepts a new input-context ID or an existing simulation ID. The stored reference records its actual kind. Commands support existing idempotency keys. Source/equipment corrections invalidate contexts, plans, results, interpretations and proposals through the existing evidence graph. Catalog/runner refreshes publish versioned software evidence; execution rejects changed digests or stale sources before calculation and rechecks lineage before commit.

## Reproduce and verify

```sh
PYTHONPATH=backend .venv/bin/python -m src.lifesci.process_engineering.demo
```

This creates `model-selection-artifacts/`: source/catalog snapshots, actual agent planning and assessment attempts, the saved plan, executed results, engineering proposal, PNG/SVG charts and report. If the agent route is unavailable, the numerical example is explicitly engineer-authored. No numerical demonstration is presented as measured AI performance. Record IDs, timestamps and runtimes vary; numerical configurations, partitions and seeded outputs remain reproducible.

```sh
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/lifesci -q --tb=short
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/test_prime_runtime.py backend/tests/test_no_future_leakage.py backend/tests/test_pharma_cases.py backend/tests/test_new_benchmarks.py -q --tb=short
cd frontend
npm run lint
npm run build
```

With the local API/UI running, install/select Playwright as described in [verification.md](verification.md), then from the repository root:

```sh
node frontend/scripts/check_model_selection.cjs
```

`PLAYWRIGHT_MODULE` can select an existing installed package. The test uses real API responses and WebGL, not intercepted fixtures. It captures the 3D review, validates model execution and source invalidation, and records actual planning/assessment status. The retained unit tests use a fake provider only to verify qualified-route output contracts and invalid-model rejection; those tests are not measured AI performance or qualification evidence.

## Product decisions and measured boundary

The job is to help process engineers choose an adequate model and verify a repeatable analysis for transfer/operation. We compared leaving a single fixed solver against a broad generated-code modeling sandbox. The selected middle option is a reviewed catalog with agent-authored plans and trusted numerical stages, consistent with the user's explicit preference and [Main_Culture_andETHOS.md](../../Main_Culture_andETHOS.md).

| Pillar | Choice and trade-off | Observable measure |
|---|---|---|
| Easy to Start | Direct input-context entry; an agent or engineer can prepare a plan. Missing thermal characterization still needs explicit input. | No prerequisite preset-model run; required manual inputs and calculation runtime can be inspected. |
| Easy to Trust | Pinned model/runner versions, preserved data partitions, explicit source/geometry categories, honest unavailable routes. | Holdout coverage, stale-result rejection, balance tests and disclosed gaps. |
| Easy to Act | Model/adapter review proposals with engineering approval policy, separate from registration, qualification and production execution. | Persisted proposals and invalidation behavior; no human review-time saving was measured. |
| Easy to Adopt | Existing gateway, Prime bridge, permissions, evidence store, API and Next charts; one optional lazy-loaded 3D renderer. | Existing regression checks, launch steps and dependency changes; no system migration. |

The present live environment still lacks qualified LLM routes for these planning/assessment tasks. Actual attempts are retained as unavailable. Raw experimental validation remains unavailable. These boundaries do not stop model execution and engineering review, and they do prevent claiming an observed AI uplift or qualified process model.

## Implementation files

| Path | Responsibility |
|---|---|
| `backend/src/lifesci/process_engineering/catalog.py` | Versioned registered model metadata and input sufficiency checks |
| `transient.py` in the same module | Experimental finite-thermal-capacity physical solver |
| `schemas.py`, `engine.py` | Typed pipeline specification, training/holdout partition, budgets, uncertainty and geometry artifacts |
| `service.py`, `api.py` | Actual agent requests, durable lineage, execution, result assessment and adapter/engineering review |
| `demo.py` | Executed reproducibility package, actual unavailable-agent records and standalone plots/report |
| `backend/src/lifesci/lyophilization/service.py`, `api.py` | Shared source preparation and direct input-context entry; original comparisons retained |
| `backend/src/lifesci/actions.py`, `roles.py`, `container.py` | Engineering review policy, capability declarations and existing composition |
| `frontend/components/process/AnalysisWorkbench.tsx`, `VialScene.tsx` | Editable plans, result review and lazy-loaded state-driven 3D scene |
| `frontend/lib/process-api.ts`, `frontend/app/(app)/process-simulation/page.tsx` | Live client API and workspace entry |
| `backend/tests/lifesci/test_process_engineering.py`, `frontend/scripts/check_model_selection.cjs` | Scientific/permission/pipeline tests and real browser/3D workflow check |
