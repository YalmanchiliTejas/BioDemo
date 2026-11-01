> Completed actual-agent evaluation: [GLM 5.3 results and retained failures](../../docs/case_studies/agent-accuracy-20261101.md). The final cohort scored 53/60; earlier component tests below are not agent accuracy.

# Pre-demo evaluation with a $50 maximum

User constraint: no more than USD 50 total incremental out-of-pocket cost, including
compute, inference, OCR, storage, transfer, failed attempts and applicable fees.
This replaces the earlier unfunded 4,008-assignment proposal as the active plan.
Status: partial local execution on 2026-10-31. The ingestion service campaign,
deterministic investigation baseline and regression checks have run. A bounded
GLM investigation run is tracked separately; this is not the completed 60-task suite.
See `results/workflow-benchmark-20261031/report.md` and its underlying receipts.

Active scope: investigations, deviations, manufacturing scheduling and data ingestion,
as defined in [the workflow benchmark](manufacturing-workflow-benchmark.md). Physical
simulation is separate development work and excluded from headline workflow scores.

## Current local execution

The existing endpoint was verified through Modal's authenticated CLI as a shared
GLM 5.3 endpoint, not dedicated compute. The listed rates inspected on 2026-10-31
are $1.40/M input, $0.26/M cached input and $4.40/M output:
https://modal.com/library/zai/glm-5-3 . These supersede the earlier assumption that
this particular endpoint requires GPU-time pricing. Actual invoices remain separate.

`scripts/run_bounded_agent_benchmark.py` forwards unchanged model requests through
a loopback admission gate. It reserves $2.25 per forwarded request, covering the
registered 1,048,576-token context and at most 131,072 output tokens at uncached
list rates. Complete bounded provider usage can settle a reservation at uncached
rates; unknown/failed usage retains the full reservation. The metered run has a
$10 held-cost cap and 100-request ceiling. Its gate policy and every reservation,
settlement and denial are persisted. This controls this benchmark's forwarded token
traffic; it does not modify account settings or cap unrelated workspace charges.

Earlier attempts remain visible: missing runtime credential, incompatible token-limit
field in the newly added gate, and an intentionally conservative 12-request/$27
reservation cap. The first two forwarded no inference; the third forwarded 12
requests and stopped at its cap. They are not successful task completions.

No remote CPU/GPU machines were provisioned. The 300-trial ingestion campaign used
about 359 MiB peak process RSS and kept only per-trial metrics after removing its
own temporary stores. All source evidence and failed-attempt receipts remain local.
The spending allocations and proposed larger design below remain planning ceilings.

## Spending allocations

| Item | Maximum allocation |
|---|---:|
| Remote CPU worker, including image building/calibration | $10 |
| Model inference and paid OCR, including calibration and failures | $30 |
| Artifact storage and transfer | $2 |
| Contingency, taxes/fees and in-flight billing buffer | $8 |
| Total | $50 |

Allocations are ceilings, not price quotes or a promise to complete an arbitrary
run count. Credits can reduce cash cost only after their eligibility/balance is
verified. Do not assume zero-valued SDK price fields mean inference is free.
No paid expert annotation/review fits within this allocation: independent review
requires existing team time or a volunteer qualified reviewer. If unavailable,
scientific qualification remains pending rather than being replaced by an LLM judge.

## Substantial evaluation without paying for redundant repetitions

Run broad deterministic extraction, numerical-reference, provenance, permissions,
cutoff, action-boundary and failure/recovery checks across the available datasets.
These checks incur no inference charges, but remote CPU time still counts. Keep
this evidence distinct from measurements of the actual agent's behavior.

Target 60 distinct end-to-end tasks, with 15 in each of four workflow groups:
investigations, deviations, manufacturing scheduling and data ingestion. Include
normal cases, negative controls, changed evidence and trust/security failures.
These are authoring targets, not an assertion that 60 independent reviewed tasks
already exist. Preserve full authorized evidence packages and the intended demo
model/tools/settings. Do not truncate source evidence merely to fit inference cost.

Run the full agent on all 60 admitted tasks. Compare deterministic tools on all
tasks and a same-model single-pass baseline on a preselected stratified 30-task
subset. Preselect 12 tasks across the four groups for two extra full-agent repetitions.
This would yield 84 full-agent and 30 single-pass trials (114 paid-method attempts),
plus the deterministic trials. Predeclare the baseline subset and repetition IDs
before seeing evaluated outputs; do not selectively repeat only successes or failures.
Three repeats on twelve tasks measure some instability, not rare-event reliability.

Keep calibration cases separate from the final scored set. First measure actual
billing and peak resources on representative full-size inputs. Admit/freeze the
proposed final suite only if a conservative forecast, including provider-side
charges and complete in-flight reservations, fits the remaining allocations.
Do not promise 114 attempts from the current unknown billing. If infeasible,
revise the design before freezing or report that the requested scope cannot fit;
never quietly stop early and present a budget-selected sample as the full benchmark.

## Reliability of the evidence

Before evaluated runs, freeze task objectives, source hashes, access/cutoff limits,
answerability, independently checked numerical references, case/scenario clusters,
required deliverables and domain-reviewed criteria. Include normal cases, unrelated
abnormalities and appropriately unanswerable questions. Keep reference answers
inaccessible to the actual agent and verify that denial before scoring.

Retain every attempted case, invalid run, timeout, OOM, correction and retry. Use
blinded human review for scientific conclusions and action usefulness. Report
per-family numerators/denominators and uncertainty, not one pooled accuracy number.
Count source-sharing tasks and renamed copies as correlated observations; do not
claim 60 independent manufacturing incidents from two datasets. Existing inspected
datasets cannot establish untouched external generalization.

For statistical perspective only: if 60 independent representative Bernoulli
trials had zero failures, the exact one-sided 95% upper failure-probability bound
would be 1 - 0.05**(1/60), approximately 4.87%. It would not establish 99% reliability.
This calculation does not apply to correlated tasks, selected benchmark cases or
an unrepresentative deployment distribution. Repetition is not a substitute for
independent case coverage. The benchmark can reliably expose scoped failures while
remaining insufficient for production-safety or industry-wide performance claims.

Human effort savings additionally require observed manual and assisted workflows
on matched tasks, including preparation, verification and rework. With no observed
manual baseline, report technical behavior only and leave labor savings unmeasured.

## Execution and spending boundaries

Use the existing private artifact store. Run sequentially or at bounded concurrency
on temporary remote CPU compute; install reusable OCR weights once on the designated
remote machine rather than on the laptop or per trial. Keep only small receipts and
reports locally. Verify remote retention before removing temporary working copies.

At the inspected DigitalOcean public rate, the proposed 64-GiB memory-optimized host
is $0.50/hour, so $10 purchases at most 20 host-hours before additional charges.
This is not a campaign-duration forecast. A deadline must include provisioning,
image build, calibration, failed jobs and drain time. Verify account pricing/region,
then destroy temporary billable resources after retention checks; powering off alone
does not establish that billing has stopped.

Sources inspected 2026-10-31:
- https://www.digitalocean.com/pricing/droplets
- https://modal.com/docs/guide/billing
- https://modal.com/docs/guide/budgets

Modal workspace usage budgets are measured before credits; workspace spend limits
cap net charges after credits. Environment budgets alone do not cover every invoice
category. Only an authorized owner/manager can set the relevant limits. A shared
workspace limit affects other workloads; do not change it silently. The existing
proxy may have another billing owner, so first verify who is actually charged.

Before paid dispatch, require verified payer/rates and effective provider-side spend
control, plus a campaign admission ledger reserving worst-case in-flight costs.
Track all child/model calls and paid OCR. Unknown cost blocks new dispatch. Check
provider billing lag and leave headroom; a soft app-side estimate or email alert is
not a guarantee that total charges stay below $50. Unrelated account charges must
not be confused with campaign spend. Do not spend the contingency simply to increase
run count.

Known implementation prerequisites remain: Linux evaluation isolation, an approved
Linux Prime/OCR runtime, remote dispatch/artifact retention, resource telemetry and
real spend admission controls. Existing suite configuration does not enforce money
limits. No cloud resources, billing settings or manufacturing systems were changed
in preparing this plan.

## Product decision and trade-off

The job is credible pre-demo evidence within the user's budget and laptop constraints.
The simpler alternative reuses local deterministic tests and a bounded remote agent
campaign; an autoscaled GPU pool is the more ambitious and currently unfunded choice.
Keep full raw-input evaluation and the intended agent behavior, reduce redundant paid
repetition, and accept wider uncertainty intervals. Easy to Start is measured in
preparation effort; Easy to Trust in verifiable outputs and honest uncertainty; Easy
to Act in reviewer-approved next steps; Easy to Adopt in integration and review effort.
