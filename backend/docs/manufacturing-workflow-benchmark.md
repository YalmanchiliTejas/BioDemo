> Completed actual-agent evaluation: [GLM 5.3 results and retained failures](../../docs/case_studies/agent-accuracy-20261101.md). The final cohort scored 53/60; earlier component tests below are not agent accuracy.

# Manufacturing workflow benchmark

Status: active scope specification; partial execution is recorded in
`results/workflow-benchmark-20261031/report.md`. The proposed four-workflow campaign
is not complete. Physical simulation
accuracy and simulator availability are excluded from this benchmark. Earlier live
simulation attempts remain separate functional diagnostics, with their failures intact.
This document governs the task coverage and metrics of the $50 evaluation plan.

## Job and scope

Measure whether the deployed application can turn authorized manufacturing evidence
into correct, traceable investigation findings, deviation assessments, proposed
schedules, and ingested records. Use the actual application entry points, permission
checks, persistence and tools. The older Prime harness is a reusable source of cases
and scorers; it is not automatically equivalent to the deployed workflow runtime.

Keep all operations in isolated evaluation tenants or local fixtures. Scheduling
outputs are proposals; no production dispatch, deviation closure, batch release or
other consequential manufacturing action is authorized by a benchmark request.

## Workflow scorecards

| Workflow | Scored unit and reference | Primary correctness measures |
|---|---|---|
| Investigations | Relevant evidence IDs and source-supported findings against a frozen, reviewed reference | Evidence precision/recall/F1; critical evidence recall; supported-claim precision; citation correctness; correct handling of missing/conflicting evidence |
| Deviations | Labeled deviation events, affected entities and required escalation against reviewed cases | Event precision/recall/F1; critical-event recall; severity confusion matrix and per-class recall; false alarms on normal cases; escalation correctness |
| Scheduling | Proposed assignments against explicit resources, precedence, qualifications, calendars, material readiness and due dates | Hard-constraint violations; feasible-plan rate; unscheduled jobs; weighted tardiness; makespan; objective gap against a known optimum or stated bound; correct recognition of infeasible inputs |
| Data ingestion | Expected fields/records and document relationships against hidden source-linked answer keys | Field precision/recall/F1; value-and-unit correctness; record linkage precision/recall; provenance correctness; silent omissions; incorrect auto-acceptance; review coverage |

For set-based metrics, freeze matching rules and label granularity before execution.
Precision = TP/(TP+FP), recall = TP/(TP+FN), F1 = 2TP/(2TP+FP+FN).
Deduplicate predictions, enforce one-to-one matching, and publish TP/FP/FN counts.
Undefined denominators remain null. A returned field identity is not necessarily a
correct value: report identity recovery and value/unit correctness separately.
Score citation existence separately from whether its content supports the claim.
Do not infer root-cause correctness from a plausible narrative or retrieval recall.

Report each family separately, both micro counts and macro case averages with the
averaging/undefined-case policy declared. Include critical and normal cases so an
agent that flags everything cannot pass. Abstentions, unsupported assertions and
unanswerable cases need explicit frozen scoring rules. Valid abstentions can be
correct; erroneous abstentions on answerable cases reduce task completion/recall.
Scheduling needs feasibility and objective checks rather than forced precision/recall.
Do not claim an optimality gap when neither optimum nor a defensible bound is known.

## Performance and reliability

Record monotonic timestamps at submission, acceptance, first useful persisted result
and terminal outcome. End-to-end timing includes queueing, retrieval, tool calls,
internal retries, validation and persistence; distinguish it from model-only latency.
Report p50/p90/p95/p99 and maximum for each workflow, input-size bucket, model/version
and declared concurrency. Use nearest-rank empirical quantiles: sorted sample rank
ceil(p*n). Include sample count, cold/warm state, cache policy and test environment.

Publish completed-run latency with its denominator and, alongside it, all-attempt
success/error/timeout rates, time-to-failure, retry counts and the fraction of all
attempts producing a correct usable result by each declared deadline. A fast failure
is not a fast successful result. Right-censored timeout observations cannot establish
a successful-completion p99; mark that tail unidentifiable rather than dropping them
or substituting the timeout duration as successful latency.

A small end-to-end set produces an exploratory empirical p99, often dominated by
one observation. For example, the nearest-rank p99 of 60 values is the maximum.
Do not market this as a stable production p99. Plan a separate, larger repeated
latency campaign only after actual per-attempt costs are known. Replaying tools or
cached model responses measures those components, not end-to-end agent latency.
Repeated cases measure temporal variability, not independent incident coverage.

Record per-attempt peak memory, payload size, tool/model calls, input/output tokens
and actual billable cost where available. Unknown billing stays unknown. API load
checks without inference are useful and must carry their own labels and charts.

## Cases, comparisons and the $50 constraint

Authoring target: 60 distinct tasks, 15 per workflow. This is not a claim that all
cases, labels or executable scheduling capabilities already exist. Cover normal,
ambiguous, incomplete, conflicting, corrected, permission-limited and failure/retry
conditions. Scheduling cases include feasible and infeasible resource plans;
ingestion includes changed templates, duplicates and malformed records. Keep public
data, synthetic defects and authorized real incidents explicitly distinguished.

Split by source/incident/template family before authoring variants. Keep calibration
separate from held-out evaluation. Hide reference answers from the runtime and
freeze sources, labels, matching tolerances, model settings, budgets and deadlines.
Use paired identical inputs for the actual agent, deterministic workflow and a
same-model single-pass baseline where applicable. A scheduling heuristic is a more
useful scheduling baseline than an unrelated chat response. Preserve every attempt
and retry. Report case/incident clusters and uncertainty; variants are not new sites.

Reuse the budget plan's admission process, not a promised run count. Its 60-agent,
30-single-pass and 24-extra-agent design remains provisional, subject to actual cost
calibration. Cheap deterministic coverage can be broad, but it cannot substitute for
agent runs or make a small sample's p99 reliable. If the tail-latency campaign does
not fit $50, publish its limitation and the measured percentiles/sample counts.
Do not spend more or silently weaken the evidence to obtain a headline p99.

## Existing code and remaining work

- `benchmarks/common/objective_scores.py` already scores investigation evidence;
  `metric_registry.py` supplies set precision/recall. Reuse their canonical IDs.
- `benchmarks/cmo_ingestion/evaluate.py` already scores field recall, values/units,
  provenance, omissions, auto-acceptance and runtime. The new
  `benchmarks/cmo_ingestion/workflow_campaign.py` adds precision/F1, per-attempt
  timing, nearest-rank quantiles and bounded temporary stores for configuration D.
  It has executed 300 trials over three packages; API/LLM latency remains separate.
- `benchmarks/common/pilot_benchmark.py` freezes paired trials and review packets,
  but targets existing CHO/Fresenius cases and the Prime runtime. Application adapters,
  deviation labels, manufacturing schedule fixtures/checkers and unified latency
  collection still need implementation and verification.
- Existing orchestration wakeup schedulers are not evidence of a manufacturing
  resource-scheduling capability. Verify the actual product path before scoring it.
- The earlier live-app walkthrough is not this benchmark. Preserve its scope and
  failures; do not relabel simulator runs as manufacturing investigation results.

## Product measures and trade-offs

Easy to Start: preparation time and corrections before useful output. Easy to Trust:
source support, critical misses, false positives and reviewer effort. Easy to Act:
usable next steps, feasible proposals and correct escalation with approval boundaries.
Easy to Adopt: integration effort, permissions and compatibility with existing records.
Measure total review/rework time when observing users; machine latency alone is not
human time saved.

The simple option reuses existing scorers with small, isolated application adapters.
A full multi-user production load rig is the ambitious alternative, deferred until
coverage, costs and runtime stability are established. The trade-off under $50 is
limited paid sampling and weaker tail estimates, not omission of failures or provenance.
