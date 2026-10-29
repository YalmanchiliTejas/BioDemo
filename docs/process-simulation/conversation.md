# Conversational process engineering

The primary [process engineering page](http://127.0.0.1:5180/process-simulation/) now begins with a problem description. The engineer can answer questions and redirect the analysis in the same conversation. Model cards, source forms and separate save/execute buttons are no longer prerequisites. The [advanced workbench](http://127.0.0.1:5180/process-simulation/advanced/) retains the earlier manual controls and quick transfer/CDMO comparisons.

## What the agent assembles

A request goes through the existing `investigation_planning` model gateway. The model returns a typed conversational response and either focused questions or a dependency graph of registered scientific operations. There is no keyword intent router, canned response pretending to be reasoning, or new agent harness. The same versioned `FlowService` runs the graph, resolves dependency bindings, checkpoints individual steps and resumes completed work. Agent interpretation uses the existing `comparison_explanation` route.

The available operations create explicitly selected example inputs, derive independent operating scenarios, select models and numerical pipeline settings, execute those pipelines, compare executed results, interpret calculations, and prepare engineering/model-adapter review proposals. The agent can select different combinations, dependencies, model choices and parameters for each turn. Follow-ups receive the saved conversation, authorized source configurations and summaries of prior calculations. Earlier user instructions remain included when detailed artifact context is bounded to the most recent twelve turns.

This makes planning dynamic while leaving scientific calculations reproducible. The registered scientific adapters remain:

- `lyo.kv_rp`: quasi-steady heat/mass transfer with a moving sublimation front; SciPy root solving and RK45 ice balance.
- `lyo.transient_lumped`: finite thermal-storage and ice balances integrated with SciPy BDF; requires explicit thermal capacity and initial-temperature assumptions.

Both are unqualified primary-drying demonstration models. They share the same formulation, equipment and source representation. Neither predicts final residual moisture, potency, release suitability or a distributed 3D temperature field. New adapters are proposed for review, with equations, input units, source/license and verification requirements; generated code is never imported or executed. See [scientific/model details](model-selection.md) and the [source report](artifacts/report.md).

Example conversations can begin with “Assess this receiving facility” or “Investigate temperature drift.” With insufficient evidence, the agent can ask questions. Selecting **Try the freeze-drying example**, or explicitly allowing the reconstruction under **Context**, permits the published/reconstructed demonstration dataset. Otherwise the agent must ask for source context. Existing authorized contexts can be attached in that same disclosure. Arbitrary descriptions are not silently converted into a synthetic facility.

## Saved artifacts and review

The conversation is backed by a manufacturing mission. User instructions are recorded separately from measurements. Each turn retains its actual gateway records, issues, elapsed time, questions, dependency graph and artifact references. Reloading the page restores the conversation. The UI polls persisted progress rather than animating fabricated steps.

Artifacts include model selection and rationale, source/assumption records, numerical results, comparisons, and review proposals. Results display temperature, ice and sublimation charts, constraint timing, conditional uncertainty when requested, holdout discrepancy when observations exist, and an interactive WebGL vial cutaway. Scenario comparisons include temperature and vapor-capacity margin plots. The 3D scene uses saved geometry and solver frames; its scalar temperature color is explicitly distinguished from a spatial temperature solution.

Each pipeline pins the scientific model and solver/input manifests. Flow operators additionally pin a SHA-256 digest of the conversational adapter implementation. Source and user-instruction lineage reaches numerical plans/results, flow runs and review proposals. Changed or withdrawn evidence marks dependent artifacts stale/quarantined; current predictions are withheld from invalidated artifact views. The original scenario is not overwritten when a what-if is created. A follow-up can obtain a fresh context instead of reusing invalidated inputs.

Conversation endpoints are restricted to their owner and authorized site. Derived scientific artifacts retain the platform's existing site/evidence permissions. The local frontend uses the existing development identity `demo-northfield/priya` at NF1; the global prototype role switcher does not grant backend authority. Engineering review proposals use the existing approval policy and cannot dispatch production actions.

## Boundaries and recovery

The model may select up to ten registered steps, three numerical executions and one interpretation per turn. Each numerical pipeline admits at most 32 solver calls and 30 seconds; the turn admits at most 96 solver calls. Actual solver calls and timings are retained. Gateway routing, evidence validation and inference budgeting remain in the existing gateway. Wall-time admission is checked between solver calls; a single scientific-library call is not forcibly interrupted.

The attached observation context fixes the forecast evidence cutoff. A pipeline cannot claim an earlier cutoff after its planner has already seen later observations. Calibration and holdout partitioning remain separate. CDMO interventions must preserve observed schedule history through the cutoff; retrospective load/capacity changes of an ongoing run are rejected. A parameter scenario is an assumption, not an equipment characterization correction or calibrated failure probability.

Local execution uses FastAPI `BackgroundTasks` as a development runner. Queued/running turns, flow definitions, results and checkpoints are durable; a five-minute fenced lease excludes duplicate workers. Interrupted work can resume after the lease expires. This does **not** provide a production durable queue, token streaming, arbitrary-code sandbox, broad process-model library, historian connector discovery, or automatic scientific qualification. The existing mission/runtime boundaries remain available for a production scheduler integration.

## Actual verification and results — 26 October 2026

The real browser request reached the existing gateway, which reported **unavailable**: no qualified planning route completed the request. The saved thread shows that failure and allows retry. No live AI workflow or AI scientific performance is claimed. The manual numerical workbench continues to work independently of LLM availability. The default mode requires a genuinely qualified planning route (and an interpretation route if requested). Explicitly enabled development mode can execute unqualified test calls, with review flags and a visible label; it does not create a passing evaluation. See the [LLM connection guide](connect-llms.md).

The separate, clearly labeled **TEST PLANNER** UI fixture checks orchestration and rendering using a scripted provider and real numerical solvers. It produces a three-step source/select/simulate workflow, then a four-step lower-load/select/simulate/compare follow-up. Each turn executed one solver call. Both workflows completed, their outputs retained lineage, and the original result remained current after the parallel scenario was added. This is an integration contract test, not an executed LLM comparison or evidence of reasoning quality.

| Conditional quasi-steady calculation | Original 11,000 vials | 6,000-vial what-if |
|---|---:|---:|
| Primary-drying completion | 37.667 h | 37.667 h |
| Minimum critical-temperature margin | 3.969 °C | 3.969 °C |
| Minimum vapor-capacity margin | −0.670 kg/h | −0.070 kg/h |
| Sampled vapor-limit violation interval | 0–10.75 h | At 0 h |

**Neither scenario is equipment-feasible.** The second scenario still exceeds modeled vapor capacity at startup. Both drying times are conditional prescribed-pressure predictions; the present model does not calculate pressure-control loss beyond the equipment envelope. Reducing load reduces aggregate vapor demand but does not change representative-vial heat transfer in this model, explaining the identical conditional drying times. There are no independent experimental measurements for this transfer reconstruction, so observed prediction error remains unavailable. Sampling was disabled for this particular UI fixture; the existing uncertainty tests and advanced example cover seeded sampling.

[Executed comparison records](conversation-artifacts/contract-results.json), [standalone plots](conversation-artifacts/scenario-plots.png), [SVG](conversation-artifacts/scenario-plots.svg), and [browser checks](conversation-artifacts/browser-checks.json) retain the evidence. Screenshots distinguish [real route unavailability](conversation-artifacts/chat-route-unavailable.png) from the [test-planner/real-solver rendering](conversation-artifacts/chat-test-planner-real-solvers.png). No human review time, commercial yield, avoided failure or production validation was measured.

Checks executed:

- Full life-sciences regression suite: **382 passed**, 70.20 s, with local fixture networking permitted. The initial sandbox attempt failed because connector/PostgreSQL tests could not bind loopback sockets; the permitted rerun passed.
- Existing Prime/temporal/benchmark regression group: **47 passed**, 28.45 s. Total: **429 backend tests**, including twelve conversation tests and the additional flow-operator version test.
- Final focused conversation/flow checks: **20 passed**, including clarification → simulation → follow-up comparison, missing routes, unregistered code/models, source invalidation, hidden-future isolation, forecast-cutoff enforcement, review-only actions, interrupted-worker recovery, budgets and immutable scenario inputs.
- Frontend production build and TypeScript validation passed; 38 routes include conversation and advanced views. Whitespace checks passed.
- Real browser checks passed for chat entry, free-text gateway submission, unavailable-route disclosure, persistence, retry and 390px layout. Full numerical artifact/WebGL rendering uses explicitly identified test-planner records. Existing advanced model-selection and transfer/CDMO browser regressions also passed, without response interception or browser errors.

## Run it

To connect the planner/interpreter to your own LLM API, see [Connect your agent LLMs](connect-llms.md). Configuration supports explicitly labeled unqualified development testing; this is separate from route and scientific qualification.

Use the [existing environment and launch instructions](README.md). The current UI entry is `/process-simulation/`; numerical/manual entry is `/process-simulation/advanced/`.

```sh
# Terminal 1 — from the repository root
cd backend
LIFESCI_DATABASE_URL=sqlite:////private/tmp/biodemo-engineering-demo.db ../.venv/bin/python -m src.lifesci serve --seed-demo --port 8100
```

```sh
# Terminal 2
cd frontend
npm run dev
```

To generate the explicitly scripted UI contract, real calculations and standalone comparison plots in one command, against that **development** database:

```sh
cd backend
PYTHONPATH=. ../.venv/bin/python tests/lifesci/create_conversation_ui_fixture.py --database /private/tmp/biodemo-engineering-demo.db
```

This prints a conversation ID. It does not qualify the running server's model routes: its test provider and contract qualification exist only in the fixture process's isolated registry. Open the conversation through **Conversations**, where its title identifies it as a UI contract test. The optional full-render browser check can use the printed ID:

```sh
CHAT_FIXTURE_ID=<printed-id> node frontend/scripts/check_engineering_chat.cjs
```

Run this last command from the repository root with Playwright/Chromium installed (or set `PLAYWRIGHT_MODULE` to an existing module). Without `CHAT_FIXTURE_ID`, the check exercises the actual current unavailable-route path. A genuinely qualified live planner will require updating that environment-specific assertion; production source code never forces route unavailability. The original scientific comparison command remains `PYTHONPATH=backend .venv/bin/python -m src.lifesci.lyophilization.demo`; its scientific report continues to disclose unavailable AI arms.

## Design decision and next experiments

The job is to help a process engineer move from a problem description to an inspectable analysis and reviewable next step. A simple chat wrapper around the old fixed form would still require the engineer to assemble the workflow. A generated-code sandbox would broaden modeling but also add unreviewed execution and validation obligations. The implemented option uses conversational selection and composition of registered domain operations, preserving the numerical model and existing platform services.

| Principle | Implementation and trade-off | Observable measure |
|---|---|---|
| Easy to Start | Natural-language entry, saved context and questions when needed. Live value still depends on a qualified model connection and usable sources. | User turns/manual inputs before a meaningful result; current live attempt is unavailable, not a successful result. |
| Easy to Trust | Actual node statuses, source categories, pinned versions, measurements/predictions separated, invalidation and honest failures. | Inspectable manifests, constraint timing, missing observations, blocked unauthorized/invalid workflows. |
| Easy to Act | Follow-up scenarios and existing engineering-review proposals; approval/dispatch remain separate. | Persisted review package and exact evidence basis; no observed human review-effort metric yet. |
| Easy to Adopt | Existing shell, gateway, flow service, mission/evidence/action records and optional advanced controls. | No second agent harness or new frontend dependency; production scheduling and identity integration remain deployment work. |

Next experiments are to qualify planning and interpretation routes on frozen conversational tasks, measure clarification quality and recovery from invalid tool selections, validate the physical models against independent measurements, and observe engineer review effort. None of these are established by the UI fixture.

An article should separate: (1) the published Vanbillemont primary-drying transfer findings and characterization requirements; (2) our reconstructed equations, assumptions and model-scope comparison; (3) the implemented conversational planning/flow/evidence architecture; (4) measured numerical and integration results, including infeasible alternatives and unavailable live AI; (5) limitations of prescribed pressure, representative-vial visualization and synthetic evaluation; and (6) future hypotheses about model selection quality and engineer effort, with prespecified experiments rather than benefit claims.
