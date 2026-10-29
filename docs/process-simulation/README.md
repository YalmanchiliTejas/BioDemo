> Current interaction: [conversational process engineering](conversation.md). The scientific case and original comparison below remain applicable.

> New comparative experiment: [physical-model value synthetic pilot](../../backend/benchmarks/physics_value/README.md). Its [generated report](../../backend/results/physics-value/pilot-20261027-final/report.md) provides shared agent packets, hidden synthetic mechanisms and outcome replay for diagnosis, optimization, resolution and pre-transfer decisions. No agent-performance benefit is claimed by generating it.

# Freeze-drying process engineering demonstration

The initial freeze-drying demonstration added a shared, unqualified primary-drying model to the existing manufacturing AI OS. Its two flows are technology transfer and CDMO forecasting/investigation. [Executed report, figures and article outline](artifacts/report.md) and [scientific source acquisition](../research/freeze-drying-sources.md) distinguish published findings, our reconstructed calculations and unavailable evidence.

The follow-up [model-selection and pipeline workflow](model-selection.md) adds agent-selected registered adapters, direct input-context entry, a transient thermal alternative, separate training/holdout evaluation, reproducible pipelines, engineering/adapter review and an interactive 3D vial view. The original quick comparison and its historical results remain available.

From the repository root, using Python ≥3.11:

```sh
python3 -m venv .venv
.venv/bin/pip install -e './backend[process-demo]' pytest httpx
PYTHONPATH=backend .venv/bin/python -m src.lifesci.lyophilization.demo
```

The final command generates the demonstration, input/result records, proposed verification package, frozen comparison protocol/targets, actual agent adapter attempts, independent synthetic reference results, PNG/SVG plots and report in `docs/process-simulation/artifacts/`. Numerical outputs and sampling are reproducible; record IDs, timestamps, runtimes and rendering metadata can differ. The CLI uses the normal strict model-route gate; it never qualifies a route to obtain an answer. A completed Prime run additionally needs the existing SDK bundle, manufacturing-data dependencies and a genuinely qualified investigation route. All current A/B attempts are unresolved at that route gate. Scientific scores for those AI arms remain unavailable. The separate deterministic analytics and physics reference are executed.

Launch the real API in one terminal:

```sh
cd backend
LIFESCI_DATABASE_URL=sqlite:///.cache/lyophilization-demo.db ../.venv/bin/python -m src.lifesci serve --seed-demo --port 8100
```

Launch the existing Next app in another:

```sh
cd frontend
npm install
npm run dev
```

Open [Process simulation](http://127.0.0.1:5180/process-simulation/). The default is now a conversational engineering workspace: describe the problem, answer missing-input questions, and inspect agent-composed workflow artifacts. Live planning requires a qualified model route; the current environment reports it unavailable. The prior manual and numerical comparisons remain at `/process-simulation/advanced/` and run without LLM credentials. See [the conversational workflow and actual verification report](conversation.md). `NEXT_PUBLIC_LIFESCI_API_URL` changes the API base at frontend build/start time. Local requests use the explicitly labeled development tenant/actor `demo-northfield/priya`; stored server roles determine permissions. The global role selector and agent dock still belong to the synthetic prototype and do not grant API authority. Production identity integration and route qualification are deployment work, not claims made by this demonstration. CORS permits the two local frontend origins in development; production origins require `LIFESCI_CORS_ORIGINS`.

For a static production preview:

```sh
cd frontend
npm run build
python -m http.server 5180 --bind 127.0.0.1 --directory dist
```

## Use the two flows in the advanced workbench

- Technology transfer: run the source conditions on reconstructed receiving equipment, inspect constraint timing, select a bounded alternative, inspect uncertainty and provenance, then **Draft for review**. Default full loading exceeds the explicitly synthetic 0.65 kg/h receiving vapor limit. The selected nominal option lowers shelf temperature and loading; no equipment change is claimed to have been executed.
- CDMO operation: fit observations available through 6 h, inspect three hypotheses, and compare the known planned shelf change with interventions starting at the cutoff. The interactive illustration defaults to a −14°C shelf at 8 h so its future-control consequences are visible; the frozen evaluation cases retain −18°C. Kv/Rp explanations remain ambiguous and capacity cannot be inferred from temperature alone.
- **Check currentness** rereads the versioned record; **Export record** downloads actual calculations and any newly created proposal. Drafting calls the existing proposal service; required independent MSAT and QA decisions, exact-content approval, authentication and evidence checks remain enforced by that service. The proposal is not dispatched. Existing proposal read/decision/outcome APIs remain available under `/v1/proposals`; this feature adds no hardware writer or new approval authority.

Changing stored input/equipment source bytes creates an evidence revision and transitively marks dependent calculations, recommendations and proposals stale. Editing form fields marks the local view outdated; recalculation ingests the revised source. A stale calculation cannot support a new proposal. Source/input revision references and implementation digests are retained in each workspace record.

## Implementation and scientific boundaries

`backend/src/lifesci/lyophilization/model.py` is independent of any agent. It uses SI balances, Murphy–Koop ice vapor pressure, evolving Rp, pressure-dependent Kv, Fourier frozen-layer conduction, SciPy Brent roots and piecewise RK45 integration with a drying-completion event. Step and linear schedules are supported by the model. Vapor-rate and cumulative condenser-ice constraints are checked; once either is exceeded, the imposed-pressure curve is explicitly an invalid-control diagnostic extrapolation. There is no chamber/condenser dynamics model in the predictive tool. Parameter variability uses seeded synthetic distributions; the reported intervals and frequencies do not establish calibrated risk.

Initial primary-drying product temperature is algebraic equilibrium in the predictive model; there is no adjustable initial sensible-heat state. The independent evaluator includes finite thermal capacity, two vial populations and a pressure response. Its initial equilibrium correction and original failed version are preserved in [initial-reference-audit](initial-reference-audit/report.md); scenarios and scoring were not altered to force success. The corrected benchmark retains missed thermal and capacity warnings and reference-infeasible recommendations. Representative-vial results cannot establish whole-batch protection.

The facility representation contains IDs/revisions, shelf area, loading, characterized Kv coefficients, vapor/ice capacities, utility edges and missing inputs. Utility/network details and condenser storage are reconstructed assumptions. City names have no numerical effect. Shared utility constraints, energy, residual moisture, potency, final appearance and product release are outside the implemented model. The published full-cycle product measurements cannot be inferred from primary-drying completion.

LyoPRONTO's current API and GPL-3.0-or-later license were inspected; its implementation is neither imported nor copied. The source inventory records the pinned upstream commit and retained paper/table/supplement provenance.

## Verification

```sh
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/lifesci -q --tb=short
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/test_prime_runtime.py backend/tests/test_no_future_leakage.py backend/tests/test_pharma_cases.py backend/tests/test_new_benchmarks.py -q --tb=short
cd frontend
npm run lint
npm run build
```

Some existing integration tests launch local HTTP/MQTT/OPC-UA/PostgreSQL fixtures and need permission to bind local ports. The new tests cover SI validation, ice vapor pressure, heat/mass balances, monotonic physical limits, completion, schedules, solver failure, constraints, seeded sampling, provenance coverage, cutoff/hidden-field isolation, API authorization, idempotency, derived lineage, source invalidation and registered tool budgets. See [verification record](verification.md) for actual runs and browser evidence.

## Files

| Path | Responsibility |
|---|---|
| `backend/src/lifesci/lyophilization/model.py`, `case.py` | Shared physics and classified source reconstruction |
| `workflows.py`, `service.py`, `api.py` | Audience comparisons, durable evidence/proposals, authenticated endpoints |
| `reference.py`, `protocol.json`, `comparison.py`, `demo.py` | Independent synthetic evaluator, frozen protocol, existing-agent attempts, report/plots |
| `backend/src/lifesci/container.py`, `api.py` | Existing composition and development CORS |
| `backend/src/prime_runtime/bridge.py`, `harness.py` | Optional host-owned deterministic tools in the existing harness, with its normal tools/budgets preserved |
| `frontend/app/(app)/process-simulation/page.tsx`, `frontend/lib/routes.ts` | Live workspace, shared plots and navigation |
| `backend/tests/lifesci/test_lyophilization.py` | Scientific, record, API and tool integration checks |
| `frontend/scripts/check_process_simulation.cjs` | Real browser/API workflow and stale-proposal check |

This work preserves unrelated in-progress files and does not replace the platform's investigations, quality, maintenance or coordination services.
