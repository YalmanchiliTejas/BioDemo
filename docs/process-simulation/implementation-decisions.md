# Job, repository audit and implementation choices

The governing direction is [Main_Culture_andETHOS.md](../../Main_Culture_andETHOS.md), read with the root glossary, all three proposed ADRs and current life-sciences architecture/implementation/model-routing documents. A process model is a scientific calculation, not a qualified model route. A recommendation, approval, action intent and outcome remain separate records.

## Job and context

Tech-transfer teams need to inspect equipment differences and propose a verifiable receiving-site protocol. CDMO teams need cutoff-limited forecasts, plausible deviation explanations and bounded adjustments. Both need the same process physics, interpretable plots and reviewable evidence within the existing AI OS. One focused implementation is preferable to multiple disconnected simulators.

## What inspection found

| Existing area | Working code / actual boundary |
|---|---|
| `science.py` | Deterministic NumPy/SciPy statistics, control charts, cohort comparison, process analytics, units, calculation envelopes and C0 gateway handlers; no primary-drying physics. |
| `evidence.py`, `identity.py`, `actions.py` | Original bytes/revisions, derived lineage, tenant/site permissions, transitive stale marking, version-bound proposals/approvals, action intents and outcomes. Reused directly. |
| `missions.py`, `runtime.py`, `prime_adapter.py` | Persistent missions and bounded runtime work separate from model sessions; existing Prime adapter enforces evaluated routing. No new harness introduced. |
| `quality.py`, `network.py` | Classified claims and review packages; scoped site views, transfer packages/readiness and proposed schedules. A calculated transfer recommendation does not establish transfer readiness. |
| Gateway / API | `container.py` composes services, registers deterministic handlers and installs suite APIs. Added an additive API installer and two deterministic task kinds. |
| Current Next frontend | Most routes render fixtures. `lib/agent/agent-context.tsx` advances template tasks on timers; it is not backend agent execution. `case-studies` reads exported JSON and can call a separate benchmark API. The new process workspace posts to the actual life-sciences API. |
| Historical frontend documents | `connected-mode.md` describes a retired Vite proxy/client; current Next static export has no such proxy or client. We did not claim those historical routes were connected. |
| Synthetic simulation | `benchmark/simulation.py` is event/scenario-driven manufacturing simulation. Pharma benchmark material is synthetic investigation data. Existing autonomous PenSim work is a separate fermentation feasibility gate and was preserved. None supplies a freeze-drying solver. |
| Dependencies/tests | SciPy/NumPy already appear in the life-sciences extra. Added a small `process-demo` extra for the standalone demo and plotting. Existing regression and scientific tests are used alongside focused additions. |

## Alternatives and trade-offs

The simple choice was a dedicated quasi-steady Kv–Rp module with a structured facility view and bounded candidate enumeration. The ambitious alternative was a complete heterogeneous dryer/chamber/condenser model, CAD/utility-network visualization and an autonomous transfer agent. The simple implementation can be inspected, tested and integrated within the intended scope; the ambitious one requires additional characterized inputs and validation data that are unavailable. The independent evaluator is deliberately richer to reveal the simple model's failures, not to qualify it.

Using LyoPRONTO was considered after API/license inspection. Independently implementing the published equations avoids copying GPL implementation code under an assumed permissive license and keeps the scientific kernel independent of the agent. This costs us some existing optimization breadth; one shared, bounded process model is the intended scope.

| Pillar | Implementation | Cost / observable effort measure |
|---|---|---|
| Easy to Start | Prepopulated sending/receiving inputs and one run button; no upload or LLM credential needed for calculation | Real equipment characterization still required. Observe required manual inputs, request-to-first-result runtime and setup steps. No measured user time-saving claim. |
| Easy to Trust | Visible provenance categories, source archive, versioned inputs, warnings, plots, reproducible solver/seed and retained failed comparisons | More scientific review material. Observe lineage coverage, stale blocking and disclosed misses; human review time not measured. |
| Easy to Act | Bounded alternatives, explicit trade-offs, named reviewer roles, experimental criteria, existing proposed action and outcome semantics | Model feasibility is insufficient for manufacturing authorization; no writer is added. Observe successful persisted proposal and stale-basis rejection. |
| Easy to Adopt | Existing API, identity, evidence, proposal service, Next components and Prime harness | Local demo identity is separate from the prototype shell selector; production SSO and scientific qualification remain work. Observe launch prerequisites and code changes; no migration claim. |

Numerical simulation remains a pure capability. All consequential operations still require the platform's current authorization and ownership checks. The new workspace is a demonstration surface, not a new MES/LIMS/QMS record owner. A source correction invalidates dependents through the existing evidence graph; the scientific record is not silently recomputed under an old approval.

## Comparison boundary

The protocol fixes task, cutoff, parameter shifts, candidate bounds, budgets and scoring. A retains all its usual tools and may write code. B gains process-model tools through the same host bridge and budget; route qualification is not bypassed. The visible packet contains only allowlisted channels available by the cutoff; labels, shifts and future reference outputs are evaluator-only. Virtual timestamps apply only to newly authored synthetic fixture files. Existing SDK filesystem access is not described as hermetic isolation.

The first independent reference exposed a non-equilibrium initialization artifact; its outputs remain archived. A separately frozen correction changes initialization only. No scenario was tuned to force the physics model to win. Corrected failures remain in the report, and no failed agent attempt is replaced by a mock.
