# Pharmaceutical model-library implementation and verification

The library is integrated into the existing product and agent code. It is not a benchmark-only connector. The supplied FULL patch was checked and applied because the earlier chemical-reactor kit was absent. Existing changes were preserved. Scientific details, passports and API payloads are in [HYBRID_AND_UNCERTAINTY.md](HYBRID_AND_UNCERTAINTY.md), [CATALOG.md](CATALOG.md) and [the source-method audit](../research/pharmaceutical-hybrid-method-and-data-20261108.md).

## Implemented

- One existing `ModelCatalog`: 22 local adapters, including the 16 supplied reduced models, two primary-drying models, two existing fermentation models, the chemical batch reactor and the existing CHO solver. Existing external PenSim/SMPL tools remain on their established worker paths. Mechanistic, semimechanistic and empirical labels are retained.
- Existing `ProcessAnalysisService`: evidence-backed material/equipment/recipe configurations, receiving-configuration comparisons, identifiable scalar fitting, sensitivity, bounded hybrid training/adaptation, solver-propagated ensembles, empirical interval calibration/evaluation, transfer criteria and decision-focused experiment proposals. Other families do not use vial geometry, Kv-only fitting or temperature-only result schemas.
- Actual assistant integration: registered typed `model_library_*` operations in `conversation.py`, capability selection, the existing `tool_loop.py`, saved artifact rendering, and fenced mission execution. No second agent framework, registry or evidence store.
- Versioned evidence and immutable source/adapted checkpoints. Corrected originals invalidate dependent configurations, plans, fitted weights, interval calibrators, results and assessments. Current authorized source revisions rebuild configurations; an explicitly configured standing mission can reassess without a new human message. Numerical and source boundaries remain host-enforced.
- Six-unit bounded neural components only for chemical reaction-rate multipliers and the existing fermentation kLa relation. Species/energy equations or transport algebra remain unchanged. Physical features exclude names, arbitrary identifiers, time and future measurements. Source-weight regularization and a model-selection negative-transfer block preserve the source checkpoint.
- Separate measurement, parameter and learned-model propagation. Structural discrepancy remains explicit and unquantified. Whole-batch bootstrap/ensemble bands are labelled uncalibrated. A separate whole-run split-conformal layer requires disjoint original measured batches, justified independence, a compatible measurement basis and stated exchangeability assumptions. Insufficient data, synthetic perturbations and unresolved aggregate replicates cannot establish coverage. OOD inputs withhold unsupported intervals and risk probabilities.
- Model-defined yield/quality measurement bases, explicit acceptance thresholds, and withholding of unpredicted attributes. Conversion is not desired-product yield; nonsignificance is not noninferiority. Equation/mechanism changes create a reviewable model-extension proposal and cannot install executable code or change equations silently.

## Main changed files and seams

| Area | Files |
|---|---|
| Supplied reduced models | `backend/src/lifesci/process_models/`, `chemical_reactor/` |
| Existing equations reused | `fermentation/model.py`, `bioprocess/cho.py` via `cho_adapter.py`; existing lyophilization adapters |
| Catalogue and numerical contracts | `process_engineering/catalog.py`, `contracts.py`, `engine.py`, `service.py` |
| Learning, uncertainty and decisions | `hybrid.py`, `uncertainty.py`, `decisions.py` |
| Evidence-backed operations and API | `library_service.py`, `library_schemas.py`, `process_engineering/api.py`, existing `lifesci/api.py` |
| Production agent and follow-up | `conversation.py`, `conversation_schemas.py`, `tool_loop.py`, `workspace.py`, `responsibilities.py`, `capabilities.py` |
| UI | `PharmaceuticalModelLibrary.tsx`, `ModelLibraryResult.tsx`, existing `ProcessSimulationWorkbench.tsx` and `AnalysisArtifact.tsx` |
| Runnable examples and checks | `library_examples.py`, `backend/scripts/run_model_library_demo.py`, `verify_model_library_notebooks.py`, `backend/tests/lifesci/test_pharmaceutical_integration.py` |
| Scientific learning and evidence | notebooks 01–03; `fermentation/data/oxygen_transfer_darus_5953.*`; verification records below |

Paths in the middle rows are relative to `backend/src/lifesci/process_engineering/` unless explicitly stated; UI files are under `frontend/components/process/`.

## Run the product locally

From the repository root, using the existing virtual environment:

```sh
PYTHONPATH=backend .venv/bin/python backend/scripts/run_model_library_demo.py \
  --db /private/tmp/my-pharma-library.sqlite --port 8197
```

This creates an isolated SQLite development workspace with 19 clearly labelled synthetic configurations. It does not load production configuration or install model-provider credentials. Existing matching current demo contexts are reused; model software evidence is refreshed before reuse.

In another terminal:

```sh
cd frontend
NEXT_DIST_DIR=.next/pharma-library-dev NEXT_PUBLIC_LOCAL_LOGIN=1 \
NEXT_PUBLIC_LIFESCI_API_URL=http://127.0.0.1:8197 \
npx next dev -p 5189 -H 127.0.0.1
```

Open `http://127.0.0.1:5189/process-simulation/`, use the development account, choose **Pharmaceutical model library**, select **Two-size-class milling reduction**, select its **SYNTHETIC** configuration, and click **Prepare and run analysis**. Inspect the native mass-fraction trajectory, solver status, model version and evidence lineage. A source correction requires refresh/reassessment; stale results are not current predictions. The library tab also exposes operations, dataset/checkpoint references and model-extension proposals. Backend API documentation is at `http://127.0.0.1:8197/v1/docs` in development mode.

For direct local API inspection use the seeded development identity:

```sh
curl -sS http://127.0.0.1:8197/v1/process-model/catalog \
  -H 'X-Tenant-Id: demo-northfield' -H 'X-Actor-Id: priya'
```

These headers are for the explicitly local development API. Production continues to use its existing authentication and stored role assignments. Assistant reasoning additionally requires its normal configured and qualified model gateway; the numerical preview deliberately disables providers.

## Run the examples and verification

Use fresh output directories to preserve prior receipts:

```sh
PYTHONPATH=backend .venv/bin/python -m src.lifesci.process_models list
MPLCONFIGDIR=/private/tmp/sievance-pharma-mpl MPLBACKEND=Agg PYTHONPATH=backend \
.venv/bin/python -m src.lifesci.process_models examples --output /private/tmp/pharma-baseline-new
PYTHONPATH=backend .venv/bin/python -m src.lifesci.process_engineering.library_examples \
  --output /private/tmp/pharma-hybrid-new
MPLCONFIGDIR=/private/tmp/sievance-pharma-mpl MPLBACKEND=Agg PYTHONPATH=backend \
.venv/bin/python backend/scripts/verify_model_library_notebooks.py \
  --output /private/tmp/pharma-notebooks-new
```

The notebook verifier executes every Python cell sequentially in one namespace per notebook, saves figures and records source hashes. It is explicitly **not** a Jupyter-kernel execution claim. The notebooks can also be opened normally in Jupyter or VS Code.

```sh
PYTHONPATH=backend .venv/bin/python -m pytest \
  backend/tests/lifesci/test_pharmaceutical_integration.py \
  backend/tests/lifesci/test_process_model_library.py \
  backend/tests/lifesci/test_chemical_reactor.py \
  backend/tests/lifesci/test_process_engineering.py \
  backend/tests/lifesci/test_engineering_conversation.py \
  backend/tests/lifesci/test_fermentation.py \
  backend/tests/lifesci/test_capabilities.py \
  backend/tests/lifesci/test_missions.py backend/tests/test_engineering_work.py \
  backend/tests/lifesci/test_bioprocess.py backend/tests/lifesci/test_tool_loop.py \
  backend/tests/lifesci/test_memory_privacy.py backend/tests/lifesci/test_agent_memory.py -q
cd frontend
npm run lint
npm run build
```

Actual recorded outcomes: **211 tests and 48 subtests passed**; all 16 new model examples and existing local example smokes ran; both synthetic hybrid/adaptation campaigns ran; all three notebooks executed (30 Python cells); TypeScript and the production Next build passed. Local browser verification exercised the real API to save/display a milling trajectory with correct native units. The native agent and standing-mission paths are tested with scripted model responses; no paid inference or measured agent-performance claim is made.

See [execution.json](verification/execution.json), [notebook execution records](verification/notebooks.json), and [synthetic hybrid outcomes](verification/hybrid-synthetic-summary.json). Development trials and earlier supplied kit records are not customer validation. On this machine, Matplotlib's optional system-font discovery emitted a nonfatal native-library warning; the Agg plots and numerical examples still completed.

## Data needed for real calibration

- Original independent source and receiver batches/runs with an experimentally justified grouping/independence basis; identifiers alone do not establish independence.
- Material/chemistry identity, formulation and product attributes; characterized equipment geometry, heat/mass-transfer and utility boundaries; actual recipe, feeds and control histories.
- Matched measurements with units, timestamps, availability times, original source revisions and sensor/assay uncertainty. Chemical rate learning requires reactant, desired product, impurity and temperature observations. Transport learning requires measured kLa with power, gas flow and usable equipment geometry.
- Training, model-selection, interval-calibration and untouched evaluation partitions frozen before fitting. Receiving-site adaptation needs additional original receiver runs and a fresh compatible interval calibrator. At nominal 90% split-conformal coverage, at least nine eligible independent calibration groups are needed for a finite order statistic; nine alone does not establish exchangeability or practical accuracy.
- Explicit product-yield and quality acceptance criteria on the model's actual measurement basis. A model that lacks the required attribute must withhold the transfer conclusion.

The retained independent CC-BY DaRUS dataset (DOI `10.18419/DARUS-5953`) provides 24 oxygen-transfer mean/std observations from one 30 L apparatus. Original bytes, units, citation and checksums are retained. Numeric impeller geometry and individual trial independence remain unresolved. Those means/std are not expanded into invented replicate batches; they provide **zero eligible independent calibration batches** for the current transfer claim.

## Remaining limitations

The models are reduced, conditional engineering models, not qualified customer twins or release/safety studies. The fermentation hybrid is a transport-algebra model, not organism growth, product yield or viability kinetics. The two-stage chemical kinetic estimation differs from the paper's full nonlinear TVP trajectory optimization; source-weight regularization also uses a smooth L1 approximation. These departures are documented rather than represented as a reproduction of the paper's results.

The synthetic neural comparisons demonstrate implementation behavior, not real accuracy or workload savings. Empirical interval calibration is implemented and contract-tested, but no eligible customer calibration set has been supplied. Structural discrepancy and domain shift do not receive fabricated probabilities. Experiment ranking is a feasible decision-discrimination heuristic, not validated causal information gain. Statistical yield noninferiority requires compatible independent difference-interval evidence; absent that evidence, the conclusion is withheld.

External PenSim/SMPL worker execution, production deployment, customer validation and live paid-model reliability evaluation were not performed as part of these checks. Long operations remain bounded by solver/evaluation and admission/completion checks; this is not a new hard-kill distributed training system. Human approval remains separate from calculation, proposal and execution.

## Visitor demo integration (2026-11-08)

The no-sign-up `/demo/` flow now seeds 19 evidence-backed synthetic configurations per new visitor workspace (the 16 reduced models, the competing-reaction model, and both fermentation transport models). This performs no solver or inference calls during provisioning. The existing 22-model catalogue remains shared software; configurations and results remain tenant-isolated. Freeze-drying examples remain in their existing tab; CHO uses its existing delivery/forecast scenario rather than an invented library configuration.

The demo banner links to **Try the model library**. The simulation page opens the library for demo visitors and preselects the synthetic chemical configuration; selecting another supported model chooses its matching configuration. Click **Prepare and run analysis** to execute the existing bounded pipeline and inspect native units, constraints, assumptions, model versions and evidence lineage. Raw source-packet entry/import controls are hidden for demo visitors, consistent with the existing no-confidential-data notice. Existing demo roles, expiry, assistant-message limits and solver budgets are retained.

Hybrid learning and interval calibration remain explicit operations requiring partitioned run datasets/checkpoints. The seeded configurations alone do not demonstrate adaptation or establish calibrated accuracy. No customer validation or manufacturing approval is implied. Returning demo tenants now receive an idempotent library-seed upgrade on workspace access or before an assistant turn. Existing uploads, conversations, expiry and message counts are retained; stale authored examples are replaced without refreshing user assessments silently.

Verification: `PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/lifesci/test_demo_workspaces.py backend/tests/lifesci/test_pharmaceutical_integration.py -q` — **50 passed**. Tests cover all four persona roles discovering 22 models and 19 configurations, executing the chemical solver, synthetic provenance, idempotent provisioning, visitor isolation, and existing demo expiry/caps. `npm run lint` and `npm run build` in `frontend` passed (58 routes). Browser verification followed `/demo/` → role/notice → private workspace → banner library link → **Prepare and run analysis**: completed, one solver call, native mole/temperature/product-yield observables and saved lineage. No assistant inference was invoked.

This is verified local code, not a public deployment. Local visitor entry: `http://127.0.0.1:5189/demo/` with the isolated API on port 8197. Public availability requires shipping both frontend and backend together; this change does not provision or claim a deployment.

## Persona scenarios and custom deliveries (2026-11-08 follow-up)

Per user direction, the existing assistant scenario cards now include one library scenario for each persona: reactor predictions and permitted neural terms (Process Engineer), fermentation oxygen-transfer screening and receiving-site characterization (MSAT), model evidence/quality/uncertainty review (QA), and a conditional transfer-decision brief (Executive). They reuse the seeded configurations and existing agent tools, without prescribing unsupported training or calibrated claims.

Demo visitors can now use the existing Deliveries upload flow. Both the UI restriction and API restriction were removed; normal authorization, tenant scope, intake checks, source hashes and per-file/delivery limits remain. Demo runs still force local `preview` processing, so arbitrary custom formats can require manual mappings and hosted extraction is unavailable. A delivery must pass the existing verification checks before **Ask the assistant** attaches its measurement dataset. Uploading a delivery does not automatically create a scientifically characterized model configuration or independently calibrated dataset. The demo notice now discloses optional uploaded files, processing storage and conversation/feedback retention. Access expiry is distinguished from deletion of originals: database purge does not delete durable delivery originals/local caches.

Browser verification found and fixed an additional adoption issue: anonymous visitors have no email, which left mapping-review buttons disabled. The shared header now supplies the authenticated demo actor ID to the existing reviewer UI; the server continues to record the authenticated identity. Browser flow verified: custom CSV upload → confirm mapping → reprocess → **Verified. 2 values ready.** → **Ask the assistant** → the custom delivery's two sourced values attached to the companion. This used a small authored test CSV, not customer data or a live inference evaluation.

Verification: demo/library/CMO isolation/upload-race regression selection **60 passed**; an additional rerun of the four persona custom-upload cases, including expired-workspace rejection, **4 passed**. Frontend type checks and the final production build passed (58 routes). All four custom-data API cases confirm no hosted model calls and do not relabel uploaded data as synthetic. These remain local changes pending shipping both application layers.

## Scenario discovery failure and correction (2026-11-08)

The reported failure had reproducible host-side gaps: older visitor tenants received current scenario text without the new example configurations; ordinary `--seed-demo` startup did not install them; and the agent's catalogue returned model contracts without saved configuration identifiers. Three focused regressions went red on missing searchable contexts, missing standard-startup contexts and a native tool loop blocked at catalogue discovery.

The shared seed is now idempotent and is also part of normal development startup. Returning anonymous demo workspaces are upgraded before discovery or before enqueueing a turn; current contexts are reused, missing/stale authored examples repaired, and unrelated existing data retained. Demo control records and visitor records are written in separate tenant transactions. The existing model catalogue tool returns authorized current configuration references with model IDs, versions and synthetic classification. Workspace reads expose the model identity, contract and units. The model must still read/attach a discovered configuration before preparing execution. Neither discovery nor execution enables the separately gated reconstructed freeze-drying tool.

A scripted native-agent regression executes the actual Process Engineer scenario through catalogue → configuration read → bounded preparation → solver execution, for both fresh and legacy sessions. Each saves a completed result with one solver call, no fitting/checkpoint creation, and `demo_enabled=false`. This establishes host integration, not live LLM reliability or scientific validation. Additional regressions cover normal development startup, idempotent legacy upgrades and repair of a stale example without altering original evidence or resetting message counts. The local preview API was restarted with the fix; remote deployment has not been performed.

Executed discovery-fix verification:

```sh
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/lifesci/test_demo_workspaces.py backend/tests/lifesci/test_pharmaceutical_integration.py backend/tests/lifesci/test_engineering_conversation.py backend/tests/lifesci/test_workspace_source_search.py backend/tests/lifesci/test_workspace_links_search.py backend/tests/lifesci/test_tool_loop.py backend/tests/lifesci/test_memory_privacy.py backend/tests/lifesci/test_agent_memory.py backend/tests/lifesci/test_capabilities.py -q
```

**143 passed in 119.15 s.** The five focused startup/discovery/legacy-repair cases passed in 4.24 s. Browser verification on the existing local visitor session: chemical simulation completed, one solver call, no alert elements. No production qualification status was changed and no live LLM rerun was claimed.
