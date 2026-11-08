# Can the workspace agent use LyoPRONTO correctly?

15/24 fresh native-model cases passed all applicable checks. 24 recorded sessions; every planned case remains in the denominator. One session per authored case, not a general reliability estimate. No comparison with our physical model is made.

- Scheduled calculations: 6/6
- Constrained recipe selection: 5/6
- Missing characterization: 0/6
- Units and model limits: 4/6

## What changed
The old experiment swapped a tool inside BioDemo's reused synthetic world. This experiment replaces the inputs, tasks, reference, scoring and execution harness. LyoPRONTO knownRp in native units is both the agent's modeling tool and the independently executed numerical reference. No BioDemo physical model, old scorer, fitting channel or synthetic hot-vial correction enters the evaluation. The actual application conversation/ToolLoop/gateway/evidence/result path runs with a research-only typed connector in local isolated workspaces; it is not a deployed production integration.

## What a pass establishes
A supported task was completed using native simulation evidence or correctly identified missing/scope evidence. Numerical checks use drying-event completion, returned bottom temperature, per-area-to-whole-batch flux conversion and native equipment line a+b*P_Torr. Missing results and errors fail. Constrained decisions must select a complete feasible allowed recipe within 5% of the fastest feasible grid candidate. Infeasibility claims require execution of all candidates. Constraints are checked at returned nodes, not continuous maxima. A same-simulator reference measures scientific tool competence, not independent experimental prediction accuracy, causal proof, product quality, batch release or global optimization.

## Execution and costs
Model GLM-5.3; LyoPRONTO 1.2.0 commit c6a9225a9e551ae4e7c11c1ef056b67c6204afbd. Limits: 10 model calls, 16 tool calls, 300 seconds per loop and 12 native solver calls. 77 solver calls; mean session time 81.3 sec. 153 admitted provider requests. Known-usage token estimate $3.5840; retained unknown reservations $0.0000; conservative accounting $3.5840 under the $10 admission estimate. These are not provider invoices and exclude engineering and local solver compute. Shared provider queueing is included. No failed scored attempt was silently rerun.

## Failure checks
{
  "missing_evidence_identified": 7,
  "recorded_assessment": 1,
  "no_invented_recommendation": 1
}

### Frozen-grader limitation, identified after inference began
The frozen missing-evidence check requires exact strings in missing_inputs. 7 failed answers contain all required canonical field identifiers as complete tokens in their missing-input text or rationale, but do not use the exact required list entries. These are flagged per case as literal_field_mismatch; do not interpret that check as proof of a scientific misunderstanding. 1 out-of-scope answers also include a completion value supported by their native simulation context, with no recipe selection. The frozen envelope requires null completion for every unsupported task, so these fail that rule; the failure alone does not establish that the value or a plant claim was invented. These are flagged as context_metric_policy_mismatch. Scores are not changed retrospectively. The supplied statuses and numerical checks retain their original rules. This audit is post hoc and is not an independently blinded semantic review. Recognizing a field does not validate the explanation: the R0 missing-input answer describes it as a zero-pressure resistance term, whereas the native Rp = R0 + A1*L/(1+A2*L) makes R0 the zero-dried-layer-thickness intercept. The deterministic field-name score does not catch that terminology error.


## Evidence and reproduction
The protocol, environment versions, source hashes, public inputs and raw native reference trajectories were frozen before agent inference. Development qualification rejected an initial 6-minute horizon because its shelf ramp exceeded stage time; the final 60-minute truncation case preserves valid native schedule semantics. This happened before any agent inference. A scripted zero-inference application/solver preflight and 11 tests preceded the run. This is a small authored suite derived from one upstream example, not experimental data, a sealed broad generalization benchmark or a test of full production deployment. Scope/missing-evidence cases explicitly ask for appropriate status; those scores measure adherence on supplied questions, not spontaneous discovery of hidden incidents. Provider sampling defaults were used without a pinned inference seed; repeated agent answers may differ. The deterministic grader checks structured numerical decisions; it does not independently judge every sentence of rationale or final prose.

Private references were outside the agent workspace and tools; no shell tool was exposed. The tools preserve evidence IDs and source revisions, and save drafts requiring review. No manufacturing operation or approval was authorized.

Run source in reproduce.zip requires the application repository and separate unmodified GPL-3.0-or-later LyoPRONTO checkout at the recorded pin. No upstream or proprietary SDK software is redistributed. See https://github.com/LyoHUB/LyoPRONTO and https://github.com/YalmanchiliTejas/BioDemo/issues/29.

The rejected tool-swap experiment remains at /research/lyohub/archive/tool-swap/ with its original evidence. Its model rankings do not establish superiority.
