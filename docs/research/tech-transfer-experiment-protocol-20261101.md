# Measured technology-transfer assessment protocol v1

Prepared 2 November 2026, following the 1 November data audit. The historical filename preserves the research thread; the generated manifest records the actual UTC freeze timestamp.

Scope: offline preparation of one transfer workflow with scientific and effort outcomes. No new agent runs or comparative results are authorized by the preparation command. This is a retrospective exploratory protocol, not independent plant validation or a registration with an external registry. Researchers have read these public outcomes and earlier results; the freeze precedes the **new** inference, not all human exposure. Public-source pretraining cannot be ruled out.

## Job and hypotheses

A process engineer needs a source-linked assessment of transferring a donor process to receiving equipment: reconciled parameters, equipment/process differences, supported risks, prediction limits, and an actionable characterization plan. A recommendation remains a proposal for review; no production action is issued.

H1: access to the declared mechanistic characterization tool improves the same agent's measured scientific task scores relative to the agent without it. H2: the combined workflow reduces active human effort to reach the same assessment acceptance criteria relative to a conventional workflow. H3: the combined workflow adds value over a conventional model workflow. These are distinct hypotheses; better performance than an agent alone does not establish H2 or H3.

## Frozen dataset and tasks

Five cases represent **three literature studies**, with correlated receiver summaries and one paired raw-gas culture. Do not count five cases as five independent transfer campaigns or gas samples as replicated batches. No case is removed, replaced or extended based on model efficacy. Failures and unavailable predictions remain reported.

| Cases | Inputs | Held-out measured target | Permitted interpretation |
|---|---|---|---|
| SC-2-to-20L, SC-2-to-200L | Donor2L ring-sparger data, receiver equipment and water characterization methods | Receiver water kLa at the separately released characterization setting | Source-only hydrodynamic/correlation prediction discrepancy; not broth or biological success |
| PC-10-to-100L, PC-10-to-1000L | Donor10L enzyme summary, methods, receiver equipment and pressure/feed context | Published assay-derived receiving enzyme summary | Optional empirical endpoint error; no mechanistic productivity claim |
| TC-1-to-250L | All donor1L gas readings, receiver equipment/methods | Receiver CO2 recorded reading on a0–168h grid every6h (29 targets), nearest measured timestamp within0.03h | Descriptive pre-receiver signal prediction; unit unresolved; not OUR/OTR/DO/product yield |

The29 gas timestamps span a fixed elapsed-time grid through the published pilot duration, not peaks or model fit. Reference values are nearest actual observations, with actual timestamps disclosed in requests; no target interpolation, smoothing, normalization or imputation. Full receiver records remain evaluator-only for audit, not additional post hoc primary targets. Do not select a different gas channel/window after seeing comparative performance. Raw units are explicitly unspecified. Published durations/endpoints conflict in places; no synchronized harvest or product trajectory is inferred from gas-record duration. See the [qualified source notes](tech-transfer-data/paasikallio2017/qualification-notes.md).

## Deliverable and phased evidence

Every arm returns the same structured submission: requested facts with units/citations; supported risks with evidence; an assessment; characterization requests; and finite predictions or an explicit unavailable result. Unknown fields remain null. Extra narrative claims undergo source review; a correct-looking number with a false citation is not an accepted finding.

Sulfolobus phase1 assesses readiness from donor/equipment evidence. The worker must commit the phase1 artifact and hash before the host releases `phase2-input`. Phase2 supplies receiver rpm/flow/sparger as **prediction covariates**, never receiving kLa or author-calculated power. It does not score whether the agent independently selected the published recipe. Prediction settings must not influence the already committed readiness assessment.

Trichoderma receives **zero** receiving gas readings; this is transfer prediction, not early-receiver adaptation. A future adaptation study needs a new protocol specifying its observation cutoff. Pichia source and receiver endpoint times differ; empirical errors compare the published summaries and cannot be described as matched-time kinetics or causal pressure effects.

The staged packages are reviewed structured source extracts, not native manufacturing documents. Fact/extraction scores measure reconstruction from this prepared representation, not autonomous parsing of the original answer-bearing publications. End-to-end document ingestion requires a separate redacted original-document task and its preparation accounting. Prior parser checks do not supply agent extraction accuracy.

## Arms and fairness

- A, agent alone: existing GLM-5.3 runtime, staged evidence, retrieval and common arithmetic facilities; no registered fermentation characterization tool.
- M, conventional model workflow: an engineer uses the same evidence, ordinary calculations and frozen model implementation. Include human input preparation, interpretation, assessment assembly, review and correction in effort accounting. A numerical model component alone is not the complete comparator.
- B, agent plus model: same agent/system instructions, evidence, common tools and resource limits as A, plus the registered characterization tool. Tool execution and source preparation are charged to this workflow. Avoid special instructions that reveal rubric answers only to B.
- H, conventional human assessment: matched task/evidence and acceptance criteria, with observed human timing, required to claim human labor reduction. This can coincide with M if the evaluator records the actual methods used; do not count the same person/task as an independent second sample.

Use the existing Prime SDK, bridge, registered fermentation tools and evidence records for future inference; preparation adds no second agent runtime. Pin model identity/version, prompts, common tools, tool schema, request budgets, arm order, repeats and hardware in a separate **execution manifest before inference**. These are not fixed by this data-preparation freeze. Do not infer execution readiness from a complete data package.

Conventional model predictions use the existing `lifesci.fermentation.model.transfer_point` source-only correlation, with declared gas exponent0.5 and its uncalibrated geometry/sensitivity limitations. No receiver fitting is permitted. Water-to-broth or product kinetics are not added. A constant donor enzyme endpoint is the Pichia empirical baseline. Donor CO2 linear interpolation at receiver-request times is the Trichoderma empirical baseline; it is not a mechanistic predictor. Baseline interpolation uses two bracketing donor observations and does not extrapolate. These simple comparators show where tool access may not add predictive power; they do not establish an optimal industrial model.

## Scoring fixed before new inference

Do not use a single composite score that mixes units or hides failures.

1. **Fact accuracy**: correct requested value/type and exact unit plus a nonempty source citation, divided by all requested facts. Numeric tolerance1e-8 is for representation/conversion only, not scientific uncertainty. Missing facts fail this metric. Citation presence is automated; citation support is reviewed separately. Null is correct only for a reference marked unavailable. Do not invent measurements to improve completion.
2. **Risk precision/recall**: a named human reviewer maps each submitted risk to the frozen source-supported reference set, unsupported, or valid outside the reference scope, with rationale. Unique matched references are true positives; duplicate matched claims and unsupported claims enter the precision denominator. Recall divides unique matches by all reference risks. Valid out-of-scope findings are retained separately and do not inflate core recall. Empty precision denominator is null, not100%. Until every submitted risk is adjudicated, both metrics remain null. Reference risks are researcher-authored, not an exhaustive domain gold standard; obtain process-expert review before interpreting them as scientifically accepted labels.
3. **Prediction quality**: signed and absolute error per target; MAE and RMSE separately for water kLa(h^-1), enzyme empirical endpoints(mg/L), and CO2 recorded units. Show submitted/expected coverage. No prediction is scored as zero error when missing; incomplete coverage must remain visible beside any error. A successful abstention on unsupported biology is reviewed in the assessment, not imputed as a correct numeric forecast.
4. **Evidence and action quality**: reviewer checks citation entailment, measurements versus assumptions, model applicability, unsupported causal/safety claims and whether proposed characterization addresses the declared gaps. Preserve item-level judgments. Automated risk matching or deterministic replay alone is not scientific acceptance.
5. **Effort and execution**: observed active minutes for preparation, configuration, review and correction; separate end-to-end elapsed seconds, completions, rework, provider cost and request identity. Missing observations stay null. The scorer never invents time saved. Compare only assessments accepted under the same criteria, while retaining failure time and acceptance rate. Record asynchronous waiting/interruptions separately. Dataset construction and shared infrastructure preparation are reported separately from per-case effort; amortization requires an explicit reuse assumption.

This exploratory dataset is too small for a reliable p90/p99 latency or transfer-population estimate. Report individual cases and study-level results; gas errors within a trajectory are correlated. No significance claim, bootstrap treating rows as batches, or commercial success threshold is prespecified. A stronger manufacturing efficacy experiment requires additional independent runs and expert-set process tolerances; numeric error on these few summaries cannot establish it.

## Human acceptance and timing procedure

Use `templates/human-effort.csv`. Record preparation/configuration/investigation effort within preparation or configuration consistently, active time separately from waiting, and correction cycles with artifact hashes. An assessment is accepted only after a reviewer verifies the required factual reconciliation, traceable claims, explicit unknowns, no unsupported production authorization, and a characterization plan consistent with available evidence. Acceptance is a human review event, not an automatic score threshold. Record rejection reasons and retries. Do not set minutes to zero because a timed observation was never made.

Randomize/counterbalance arm order before execution. Use different matched assessors or appropriately separated matched tasks to reduce carryover; the developer who has seen all outcomes cannot provide a blinded conventional baseline. If only developer timing is available, label it a demonstration rather than reliable human-efficiency evidence. Time saved and percentage reduction require paired comparable observations, consistent start/end boundaries and accepted deliverables. Completion failures cannot disappear from the denominator.

## Isolation, provenance and budget

`agent-input`, `phase2-input` and `evaluator-only` are separated and hashed by preparation, but directory names are **not** an access control. A future runner must deny the original workbook, full source articles, research notes, evaluator files, past receiving reports, repository-wide reads and external answer retrieval. Allow only the model provider network path and explicitly allowlisted tools. Demonstrate denied-file and denied-network probes before paid trials, then enforce phase1 commitment. Record public-literature/pretraining and developer exposure even with isolation.

Every source, protocol, packet and scorer is hashed. Refuse overwrite or changed frozen inputs; material changes create a new version. Future attempts, baseline predictions, reviews and scores live outside the frozen directory and carry manifest/submission hashes. Preserve earlier studies and their failures. No cherry-picking a more favorable process/model after looking at scores.

Total remaining user-authorized ceiling is **$50 including pilot, retries and the main study**, not $50 per arm. No billable inference is performed here. Before any run, verify remaining budget and a provider-enforced or conservatively bounded worst-case request cost including all agent/child/tool-model calls. A local dollar ledger with unknown Modal rates is not an enforceable provider cap. Pilot must rehearse identity, isolation, schema, phase commitments, timeout/cost accounting and scoring; label it separately and do not pool it into efficacy. Freeze the main execution manifest after pilot fixes and before comparative inference. Do not claim GLM ran from tool fixtures or deterministic calculations.

## Engineering choice under the four pillars

Easy to Start: reuse small available sources, existing agent/tools and offline preparation. Easy to Trust: measured targets, unknown units, source hashes, outcome boundaries and incomplete reviews remain explicit. Easy to Act: produce a reviewable transfer assessment and specific characterization requests, not only a text report. Easy to Adopt: retain existing source ownership, review proposals and production authorization boundaries.

Chosen alternative: a small measured, retrospective transfer-assessment study with targeted scientific scores. Rejected for this data: constructing a new complete organism/scale-up simulator and treating its self-generated outputs as validation. Trade-off: current evidence supports a useful but limited workflow experiment, not broad manufacturing accuracy, saved batches, product yield, avoided investment loss or reduced completed transfer calendar time.
