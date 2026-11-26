# Freeze-drying with Purdue LyoHUB’s LyoPRONTO

Agent + LyoPRONTO made 41 feasible choices out of 48, compared with 16 without a prepared model and 43 with the Sievance model.

LyoPRONTO's agent arm had 4 unsafe selections, 0 characterization decisions and 3 failed/no-submission slots. These are simulated constraint outcomes, not observed manufacturing incidents.

**Classification:** synthetic research, reused 24 cases, one realization per case/task/arm. No manufacturing validation or Purdue affiliation/endorsement is claimed.

**Execution qualification:** 5 sessions (3 numerical-only and 2 LyoPRONTO) were unable to dispatch further requests after conservative admission capacity was exhausted. These stay in the denominator but are not evidence of solver quality. Full-cohort tool comparisons are confounded by this execution limit.

## Results

| Task | Agent tool | Submitted | Feasible | Unsafe | Characterize | Failed | Completion MAE | Predictions / eligible |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| forecast | Agent · no prepared model | 10/24 | 9/24 | 0 | 1 | 14 | 17.63 h | 10/24 |
| forecast | Agent + LyoPRONTO | 23/24 | 23/24 | 0 | 0 | 1 | 1.32 h | 23/24 |
| forecast | Agent + Sievance model | 24/24 | 23/24 | 1 | 0 | 0 | 1.12 h | 24/24 |
| pretransfer | Agent · no prepared model | 12/24 | 7/24 | 0 | 5 | 12 | 29.66 h | 12/24 |
| pretransfer | Agent + LyoPRONTO | 22/24 | 18/24 | 4 | 0 | 2 | 2.56 h | 22/24 |
| pretransfer | Agent + Sievance model | 24/24 | 20/24 | 3 | 1 | 0 | 1.86 h | 24/24 |

Feasibility requires completed primary drying without a thermal/capacity violation in the synthetic reference. Characterize earns no operating throughput. Failed execution and absent submissions stay in the denominator. Error is reported only where a numerical prediction and eligible reference both exist; different coverage limits comparisons.

## Matched prediction coverage

- forecast: 10/24 cases have predictions in all three arms; common-case MAE A/B/C: 17.63 / 1.38 / 1.02 h.
- pretransfer: 11/24 cases have predictions in all three arms; common-case MAE A/B/C: 29.12 / 2.35 / 1.50 h.

## Model-only controls

| Task | Model | Feasible | Unsafe | Characterize | MAE | Predictions |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| forecast | LyoPRONTO | 24/24 | 0 | 0 | 1.29 h | 24/24 |
| forecast | Sievance model | 23/24 | 1 | 0 | 1.12 h | 24/24 |
| pretransfer | LyoPRONTO | 19/24 | 5 | 0 | 2.42 h | 24/24 |
| pretransfer | Sievance model | 19/24 | 5 | 0 | 1.86 h | 24/24 |

## Protocol and interpretation

- Same GLM-5.3, public packets, actions, 8 model calls / 8 host calls / 240 s / 4096 output-token limit. The eighth provider call, if reached, requires submission. Earlier plain-text stopping can still leave no accepted structured decision after the shared follow-up prompt. All 144 sessions are fresh; failures are not retried.
- Both prepared models fit Kv/Rp using only <=6h remaining-ice observations; pretransfer remains nominal. Historical Sievance results used a thermal+ice fit, so this is not a pure one-variable change from the old study.
- Both prepared tools use precomputed public-input-only outputs. Their solver time is recorded in model-only controls, outside AI session wall time. A numerical analysis executes inside its session deadline; this workflow difference matters.
- This uses the restricted Prime SDK experiment host, with native kernel, child agents, external retrieval and workspace memory disabled. It is not an evaluation of the full deployed assistant or investigation system.
- No accepted submission is a workflow outcome, not proof the model lacks physics knowledge or wrote no useful text. The harness allows up to eight calls but may stop after a plain-text answer plus one follow-up; submission-only forcing occurs on the eighth request if reached.
- Sessions share a hosted endpoint and conservative admission proxy. Concurrency can queue requests within the wall-time limit; latency/failure outcomes include this execution environment, not only reasoning capability.
- Some effective fits may reach their fixed evaluation limit. Calibration statuses: {"B": {"forecast": {"converged": 19, "iteration_limit": 5}, "pretransfer": {"nominal_pretransfer_no_receiving_measurements": 24}}, "C": {"forecast": {"converged": 24}, "pretransfer": {"nominal_pretransfer_no_receiving_measurements": 24}}}. The frozen protocol retains those fits; it does not claim they all converged.
- LyoPRONTO is pinned to c6a9225a9e551ae4e7c11c1ef056b67c6204afbd, version 1.2.0. Native SI conversions preserve Kv/Rp/frozen height. cSolid=1.5*(1-porosity) g/mL assumes upstream solute density; native initial ice is approximately 0.85% higher. No silent mass rescaling.
- LyoPRONTO knownRp front temperature is not a weighted thermal node or hottest transient vial. Its lack of population/thermal-storage states can affect risk detection. Constraints are evaluated at returned solver nodes; no between-node maximum guarantee.
- Finite 1e6-unit/min ramps approximate steps; full schedule replays from t=0, preserving past actions. dt=None retains the terminal drying event; horizon noncompletion remains censored.
- Vapor/condenser/temperature checks are supplied by the local wrapper; they are not LyoPRONTO knownRp capabilities. Any overload invalidates pressure-controlled completion and subsequent unsupported thermal predictions.
- Same separately executed synthetic reference as the previous study. Shared physical laws and approximate population structure favor the Sievance model; these are not independent experimental observations. Reused cases and public data do not establish freedom from model-training exposure.
- Primary KEEP cases have 0 capacity positives and 3 thermal positives out of 24. In particular, zero capacity positives cannot establish detection sensitivity.
- Feasible recommendations do not establish correct rationale, calibrated uncertainty, causal identification, regulatory compliance or real manufacturing benefit. No equipment was operated.

## Cost and execution

513 admitted provider requests; 512 have usage receipts. Token-based estimate $5.778209; unknown request reservations $2.25; conservative total $8.028209 under the $10 cap. Each new request required a $2.25 worst-case reservation; remaining unreserved headroom was insufficient even though conservative accounting was below $10. Not an invoice; excludes local solver compute and engineering.

## Sources and reproduction

- [Official LyoHUB LyoPRONTO source](https://github.com/LyoHUB/LyoPRONTO/tree/c6a9225a9e551ae4e7c11c1ef056b67c6204afbd)
- [Original LyoPRONTO paper](https://doi.org/10.1208/s12249-019-1532-7)
- [Frozen protocol and study record](https://github.com/YalmanchiliTejas/BioDemo/issues/28)
- Source/input/output hashes: results.json, protocol.json and manifest.json. Reproduction archive includes public packets and local source, not upstream GPL software or the separately installed Prime SDK.
- Unmodified upstream dependency is GPL-3.0-or-later; this numerical study does not make it a production dependency.
