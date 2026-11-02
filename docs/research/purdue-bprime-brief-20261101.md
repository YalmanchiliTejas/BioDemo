# Sievance: exploratory evidence and proposed validation discussion

**Superseded:** this earlier conversation-oriented draft does not reflect the user's requested deliverable. Use the [completed evaluation and results-based drafts](../case_studies/decision-followup-20261101/README.md).

Draft for review, 2026-11-01. No Purdue affiliation, endorsement or partnership is claimed. No message has been sent or post published. Existing results are preliminary retrospective evaluations, not manufacturing validation.

## Purpose

Seek expert criticism of the evaluation design and identify one bounded manufacturing decision for an independently reviewed test of an agent coupled to a mechanistic model. Do not present a named historical incident as prevented or estimate savings without incident-specific data and causal evidence.

## What has actually been tested

| Evidence | Finding | Interpretation |
|---|---|---|
| Retrospective real CHO forecasts: 16 scored cultures across eight conditions; 64 planned/completed agent attempts | Viable-cell MAE: agent alone 1.3944 versus agent with physics 1.4702 million cells/mL. Glucose MAE: 0.5988 versus 0.7216 g/L. | This selected simple model increased average error. Descriptive intervals and a small number of conditions limit generalization. Does not establish benefit from this model or failure of mechanistic modeling in general. |
| PenSim/SMPL experiments: 429/432 completed attempts | Several forecast metrics improved with model access; decision improvements were limited. Full 230-hour PenSim process remains unqualified. | Evidence about these simulator tasks. Changed commands in unchanged geometry do not establish real-site transfer performance. Simulator/model assumptions may limit independence. |
| Published Sulfolobus oxygen-summary replay | Both agents chose characterization before action; neither called the available physics tool. | No observed model-access benefit. Correctly exposing missing inputs can still be useful, but it is not a demonstrated prevention result. |

Sources: [existing CHO/simulator report](../../frontend/public/case-study-results/combined-physics/cho-report.md), [CHO protocol](cho-real-prediction-protocol-audit.md), [oxygen-summary replay](../../frontend/public/case-study-results/combined-physics/physical-report.md). These report findings were inspected; this brief does not constitute a fresh independent audit of every archived attempt.

The 64 CHO agent attempts are not 64 independent biological experiments. Six fed-batch cultures were excluded because input coverage was insufficient; two further cultures lacked the required glucose target. Both reactors of a held-out experimental condition were excluded from fitting. Public-data/model-pretraining exposure cannot be excluded.

## How to make the next experiment stronger

1. **Freeze and audit the existing evidence.** Preserve protocol, data/version hashes, splits, submitted predictions, model/tool versions, failed attempts, scoring code and usage receipts. Confirm every proposed public number against its underlying artifact. Correct or withdraw numbers that cannot be reproduced. Diagnose why CHO forecasts worsened before spending credits on repetition. Any model revision makes the inspected cases development data.
2. **Choose one decision and prediction target with a domain expert.** A potential first study is lyophilization temperature/primary-drying endpoint prediction across a declared change in vial, loading or operating condition. This is a proposal, not a predetermined solution or proof that the existing model covers the selected conditions.
3. **Qualify the physical model before evaluating the agent.** Review units, balances, solver behavior, parameter provenance, identifiability and domain limits. Compare model-only forecasts with independent measured runs. Declare tolerances before examining held-out results; no tolerance is fabricated here.
4. **Freeze the comparison.** Use a simple established calculation/rules baseline, model-only, agent-only and agent-plus-model. Give equivalent evidence, document tool access, and keep later measurements/outcomes unavailable. Model-value and agent-value questions require separate comparisons.
5. **Have an independent evaluator own the holdout.** Prefer newly collected or genuinely withheld whole runs/conditions. Keep biological/experimental replicates and repeated AI sessions distinct. Determine required sample size from the intended effect and variability with scientific/statistical review; a convenient number of prompts is not a power calculation.
6. **Measure the intended job.** For a drying pilot, physical-unit temperature/endpoint errors and uncertainty coverage are primary. If a recommendation is evaluated, use independently measured outcomes or expert-adjudicated bounded decisions; do not score it using its own forward model. For risk flags, define labels before estimating precision/recall. Measure preparation/review effort rather than assert time saved. Treat p90/p99 latency as a separate operational question requiring an adequate request sample.

## Data and access proposal

Begin with existing authorized or public records; avoid making a new wet-lab campaign a mandatory prerequisite for an initial protocol review. Public [Telstar freeze-drying logs](https://figshare.dmu.ac.uk/articles/dataset/Process_logs_from_the_Telstar_freeze-dryer/29285027) are a possible development source. Their shelf/pressure/product-temperature traces do not automatically supply all formulation, geometry, endpoint or calibration inputs. Previously inspected public data cannot serve as a pristine blind test.

For a later independent pilot, request de-identified completed runs and minimum material/equipment context, with agreed use, retention and publication permissions. Keep source-system records unchanged. Separate observations, calculated predictions, agent hypotheses and approved decisions. Any operational change requires explicit human authorization.

This jointly addresses the four governing product pillars: reuse existing records to reduce setup; make evidence and uncertainty inspectable; produce specific proposed experiments/actions; and fit the study into existing records and approvals. A richer physical model has a data/validation burden; select it only if the chosen decision requires the added fidelity.

## Why approach B-PRIME?

Purdue describes B-PRIME as helping small biotechnology/biomanufacturing companies meet pharmaceutical supplier requirements, jointly involving LyoHUB and the Young Institute. That makes a request for technical evaluation and pilot scoping plausible; it does not establish eligibility or access to data/facilities. [Purdue's official announcement](https://engineering.purdue.edu/Engr/AboutUs/News/Spotlights/2026/2026-0928-purdue-b-prime-biotech-accelerator-sba-scale-award).

**Concrete ask:** a short technical discussion to critique the proposed experiment, identify an appropriate reviewer, and determine whether a suitable de-identified dataset or future independent pilot could be available. Do not ask initially for endorsement, broad partnership or funding based on the current benchmarks.

## Outreach draft

Subject: Technical feedback on validating agent-assisted mechanistic manufacturing analysis

Hello [Name],

I'm building Sievance to help manufacturing teams connect process evidence, mechanistic calculations and reviewable investigation actions.

We have completed exploratory comparisons of an agent with and without mechanistic tools. Simulator forecasts improved in several tasks, but our selected model did not improve forecasts on a small real CHO dataset. We are treating this as a model-applicability and evaluation-design question, rather than a validated manufacturing result.

Given B-PRIME's work with LyoHUB and manufacturing readiness, I would value a short technical discussion about designing one bounded validation study—for example, predicting product temperature and primary-drying endpoint on withheld lyophilization runs.

Would you be open to a 20-minute conversation, or a referral to the appropriate researcher? I can share a concise protocol and preliminary results, including the negative findings. My immediate ask is critique of the evaluation design and guidance on suitable data, rather than an endorsement.

Best,
Tejas

## LinkedIn draft

We're building Sievance to help pharmaceutical manufacturing teams connect process evidence, mechanistic models and reviewable actions.

Our early evaluations have produced mixed results. Mechanistic tools improved several simulator forecasts, but our selected simple model did not improve predictions on a small real CHO dataset.

That distinction is shaping our next step: testing model applicability and agent contribution separately, using withheld experimental runs and independent process-engineering review.

We're looking to connect with researchers and manufacturing teams interested in a narrowly scoped validation study, particularly in lyophilization or cell culture. The goal is measurable predictive accuracy and useful engineering decisions—not an avoided-loss claim inferred from a historical failure story.

If you work on experimental datasets or evaluation methods in this area, I'd welcome a conversation.

## Release boundary

The drafts make research-stage claims only. Do not use “validated digital twin,” “proven scale-up prevention,” “saved millions,” “regulatory compliant,” or Purdue endorsement. A scientific reviewer should approve a future validation claim against the actual protocol/results, not a polished demo. No additional paid runs or downloads are required to send this preliminary discussion request; any subsequent pilot needs separate scope and budget agreement.
