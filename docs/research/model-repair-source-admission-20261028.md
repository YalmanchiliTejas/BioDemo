# Source-admission correction before replacement inference

A read-only audit found that9/48 completed PenSim source trajectories in the seeds8001–8048 dataset contained oxygen-floor events. Receiving KEEP trajectories had passed, but the generator had not applied the same domain check to completed-source data. This was a benchmark admission bug. The earlier partial AI run was stopped on this defect before comparative scores were inspected:224 attempts retained,213 scored and11 interrupted/failed. It is superseded and must not be pooled into the replacement analysis.

The replacement keeps the previously frozen fitting algorithm, bounds, AI comparison, endpoints, sample count, scoring and analysis. It fixes the source process and applies admission to both source and receiver. All48 newly declared seeds9001–9048 per process are retained in coverage accounting; no rejected case is replaced.

- Every PenSim completed source now uses feed factor1 and air factor1.15 after60h, within the already declared action envelope. The same rule applies to every source before outcomes are generated. It raises source aeration to avoid the known low-oxygen domain; it is a changed study condition, not a repair to the invalid low-oxygen constitutive behavior.
- The completed-source operating plan is explicitly supplied to both arms. Source fitting uses that exact plan, rather than assuming default air. Receiver plans, constraints and decision choices remain as before.
- A source with any raw oxygen-floor event is rejected as a coverage failure for all three tasks. It is not fitted and is not replaced. Receiving KEEP and candidate-action qualification remains in force.
- Preflight independently replays every PenSim source and checks its observations, audit and admission before any AI session starts. The source-air change and domain restriction must appear in the report, along with the stopped-run denominator.

The source-only fit remains an effective model, not full-state assimilation or independently validated biology. Full230h viscosity remains unresolved. Shared source/receiver biology and fixed geometry still limit transfer claims. The chosen envelope provides a test within a numerically admitted region, not evidence that the model is valid everywhere or that physics will win.

This addendum is recorded before replacement generation/inference. Original protocol and all failed/superseded artifacts remain intact under `backend/results/external-simulators/model-repair-20261028/`. Replacement artifacts use `backend/results/external-simulators/model-repair-admitted-20261028/`.
