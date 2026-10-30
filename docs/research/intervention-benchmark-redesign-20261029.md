# Intervention benchmark redesign — implementation work record

User direction29October: keep the physical models; test decisions under a changed receiving process. The earlier matching-equation/known-state comparison remains an upper-bound reference, not the main evidence of useful intervention.

## Job and engineering choices

Demonstrate disturbance → available evidence → investigation → comparison of interventions → reviewable recommendation → hidden simulated outcome. Reuse pinned PenSim equations, continuous-oxygen adapter and restricted research SDK. Keep application/plant execution separate. The simple alternative is another endpoint forecast comparison; the chosen sequential intervention benchmark adds clock-aware observations and a conventional optimizer comparator. Full production workflow deployment and physical experiments are separate. Easy to Start: reuse sources and runtime. Easy to Trust: independent receiver parameters, hidden truth, source provenance, explicit failures and clocks. Easy to Act: structured proposal plus observed virtual consequence. Easy to Adopt: retain existing OS/evidence boundaries and upper-bound archive. Report decision latency, tool use and modeled sampling effort; do not invent engineer savings.

## Required experiment arms

1. Agent without supplied model, with numerical analysis and the same observation/action interface.
2. Source-calibrated model plus a conventional fixed-grid optimizer, without an agent.
3. Same agent plus the same source-calibrated model.
4. Original operating recipe, evaluated as a reference.

Both model-bearing arms use the same model, update method, uncertainty assumptions and permitted measurements. All approaches receive the same initial observations, constraints, action menu and measurement affordances. Extra requested observations arrive only after clock advancement and have explicit assumed costs. Different requested observations are outcomes of policies, not preferential access.

## PenSim first implementation

New module `backend/benchmarks/interventions/pensim.py` reuses existing equations/controllers and the continuous nonnegative oxygen correction. A hidden receiving trajectory has independent initial/biological/oxygen-transfer factors and a mid-process kLa deterioration. The model gets source calibration and only available receiver measurements; no true receiver seed/factors, hidden states, action outcomes or future readings. Development parameter ranges are provisional simulator stress-test assumptions until the cited source audit and admission tests establish a justified envelope.

The menu includes keep, feed reduction, bounded increased aeration, combined changes, stronger feed reduction and stop. Limits are study assumptions, not certified manufacturing safety. Recoverability is determined privately against the complete permitted menu at the decision time; scenarios with no feasible action are distinct from numerical-domain failures. Debugging severe drops already reproduced invalid negative raw oxygen; such failures cannot be relabeled as scientifically valid unrecoverable batches or hidden by clipping. No final seed replacement to improve results.

Preselect the mix of normal, recoverable-intended and unrecoverable-intended disturbances before final generation. Report realized finite-menu feasibility too: a disturbance label does not guarantee recovery or impossibility. Keep development seeds separate from final seeds. Freeze code, prompts, calibration/update rules, action/measurement limits, noise assumptions and analysis before generating final cases. No repeated sample extension until favorable.

## Measurements and calibration

Primary-source review is recorded separately. Goldrick2019 reports online DO/offgas12min, offline penicillin/biomass/PAA/nitrogen/viscosity12h with4h analysis delay. Substrate is not a direct offline measurement. Do not expose S as a perfect measured state or all33 PenSim states. Any off-cycle assay and simulated sensor noise must be explicitly assumed, not attributed to the publication. Source calibration must be adapted to genuinely available source fields; the previous P/DO/S fitter cannot be silently reused as if S were directly measured. Model updates may use only records whose `available_at_h` is at or before the current decision clock.

## Separate outcomes

- Oxygen-constraint violation duration, minimum and deficit integral, before decision, after decision and across the whole process. Actions cannot erase earlier violations.
- Terminal product inventory mass in kg and concentration in g/L with volume in L. No harvest occurs before96h. Stop contributes zero counted production/released product, even if some product existed before stopping; retain the stopped inventory separately.
- Unnecessary stops: at least one permitted non-stop plan was feasible. Also report stops when the unchanged recipe itself was feasible.
- Correct stops within the finite menu: no permitted operating plan was feasible. This receives feasibility-recognition credit separately, never a production score.
- Physical decision delay, measurement count/assumed cost, wall time, model/tool calls and measured API usage/cost where available. Unknown costs remain unknown.
- Model admission/domain failures and failed agent submissions retained separately.

No combined decision score and no antibody-quality claim from simulated oxygen limits.

## Subsequent scope

SMPL: expose a published/reviewed subset of measured variables; infer an uncertainty distribution over unobserved states and parameters from source/available data. Do not reuse the exact17-state initial condition as the main test. Keep the present exact-state run as its upper bound.

RealCHO: withhold whole experiments, retain growth/glucose endpoints and source-cell provenance. No product/intervention/transfer claim without corresponding measured outcomes. Current observational evidence is not a substitute for a corrective intervention experiment.

Physical follow-up: the research note must verify an accessible published failure plus corrective experiment with actual intervention and outcome measurements. A simulator-derived IndPenSim dataset does not satisfy this requirement. Retrospective replay of a published correction is not a new executed lab intervention or customer endorsement.

## Status

Implemented and tested: hidden-parameter/disturbance simulation adapter, permitted interventions, separate mass/concentration/violation/stop outcomes, source-clock-safe noisy DO and delayed product observations, conventional model-output grid selector. Development-only envelope probes are retained under `backend/results/interventions/development-20261029/`. Source-only calibration, sequential session, full three-arm runner, frozen final-case protocol and physical-data replay remain required before any final result claim.

## Implementation update

The development harness now has a host-owned sequential session and a restricted three-approach adapter. Measurement requests advance the process clock before evidence is released. A recommendation is frozen before hidden outcomes are evaluated. The model-only optimizer and both agents share the public evidence/action interface; an injected point model fits P/DO source evidence with explicit regularization, then updates an effective transfer multiplier from available receiver oxygen readings. Candidate onset times are fixed, not supplied from hidden truth. This first model is a point estimate: uncertainty quantification/ensemble qualification remains a release requirement, not an implemented probability claim.

Development scripts retain a source-only model-optimizer example and a first sequential assay→recommendation→outcome receipt. Three strata were probed independently of AI scores: normal, recoverable and no-feasible-action conditions exist, while sufficiently severe drops cause numerical-domain failures that must remain separate. The same drop can be recoverable for one latent biological realization and unrecoverable for another. Final sampling must freeze disturbance/biology strata, and report realized feasibility rather than resampling to force desired labels.

The physical NISTCHO files are acquired with a CC BY4.0 source/CRC/hash manifest under `backend/benchmarks/assets/nistcho-feeding-2026/`. The failure/prevention contrast is confounded with campaign (FB4 versus FB2), and replicate counts differ. It can support a carefully labelled retrospective physical intervention case; it is not a randomized same-campaign rescue or a causal validation of the PenSim oxygen intervention. See the primary-source note for details.

The first actual two-agent plus conventional-optimizer development replay is complete. See [workflow replay](intervention-development-workflow-20261029.md). Both model-bearing approaches chose the same successful action in this development case; no added agent value or final generalization claim follows.

## Revised primary claim after user steering

The next primary comparison is AI without a supplied model versus the same AI plus physics. Original recipe remains a reference. The already executed conventional optimizer result and its matched outcome remain in the development scientific record. It is not deleted or relabelled. This narrower primary comparison tests whether model access helps the agent, not whether agents are necessary or outperform conventional software. The change in comparator scope precedes final-case evaluation and must appear in any resulting report. No marketing claim of agent-specific added value follows from omitting a new optimizer arm.

The model interface now includes a fixed five-member parameter sensitivity set (central plus four fixed perturbations). These ranges are assumptions inspired by simulator parameter variability, not calibrated feasibility probabilities. Final validation and source-batch holdout checks remain necessary.

## Current remaining-stage boundaries

SMPL now has a partial-measurement projection, source-prior initial-state ensemble and local copies of original balances with explicit uncertain kinetic multipliers. Reactor assays have availability clocks; separator concentrations remain latent. Unit tests check absence of hidden separator readings, stable earlier observations, positive/physical uncertain states, identity with original dynamics at unit multipliers, and the external product inventory balance. This is an implemented numerical interface, not an executed comparative SMPL study.

The observational realCHO harness already holds entire EXP conditions out of training and evaluates growth/glucose only; its negative findings remain preserved. It is not promoted into product/intervention evidence.

Detailed NISTCHO protocol inspection did not qualify mechanistic physical replay: duplicate glucose replicate identifiers, calculated/possibly imputed post-feed rows and conflicting dose formulas require curation or executed feed logs. A descriptive observed-treatment comparison is supported; a physical intervention simulator or same-vessel rescue claim is not. The exact limitations are in the source note.
