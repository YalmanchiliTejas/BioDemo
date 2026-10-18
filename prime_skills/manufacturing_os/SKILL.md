---
name: manufacturing-os
description: Investigate a manufacturing evidence package with Prime Agent's persistent Python kernel and native child agents, using scoped BioDemo data tools and a validated Blackboard report.
---

# Manufacturing OS investigation

Import the Python API in Prime's persistent kernel:

```python
from manufacturing_os import context, inspect_data, search_evidence, verify_evidence, submit_report
case = context()
```

`context()` returns the incident objective, historical cutoff (`as_of`), seed
evidence, current Blackboard, tool names, `remaining_tool_calls`,
`max_tool_calls`, and a `query_data_contract`. The bridge fixes the scope and
cutoff; arguments cannot expand them. Every admitted retrieval/analysis attempt
consumes one call, including failed attempts. Rejected calls do not consume
allowance. Exact repeated evidence packets use a per-run cache. Budget exhaustion
returns a structured status and next step; do not repeat the rejected call.
Save progress, ask the lead to allocate named unfinished work, or validate and
submit an explicitly partial report when required work cannot be completed.

## Data model

- Sources are files (CSV/XLSX/PDF). Observations are rows/claims extracted
  from sources. "Evidence" always means an observation ID from `evidence_ids`.
  There is no table named `evidence`.
- Full observations (the scoped DuckDB view) have `id, source_id, name, value_text,
  value_number, unit, occurred_at, available_at, entity_id,
  validation_status, access_scope, source_ref, extraction_method`.
- `query_data` exposes a **numeric-only projection**: `id, source_id, name,
  value_number, unit, occurred_at, available_at, entity_id, access_scope`.
  It also exposes `sheet, source_row, row_id, time_value, time_basis,
  time_evidence_id`. `time_value` is actual elapsed hours from a source clock,
  or epoch hours for an explicitly zoned calendar clock. `occurred_at` remains
  a calendar timestamp; numeric cultivation hours never become row indices.
  Legacy text/source fields may be present, but use search_evidence for text.

## Which tool for what

0. Read `context().analysis_preparation` first. Statistics and anomaly patterns
   have already been computed. The complete artifact is available at
   `analysis_preparation_artifact`; inspect it programmatically rather than
   pasting the entire file into the model context. These are descriptive checks,
   not proof of process failure. Supplied source anchors can be cited.
1. `inspect_data(limit=100)` when needed: source list, per-source sheets/columns,
   variable names, sample evidence IDs. Cheap orientation.
2. `infer_schema()` when column names are unclear: proposed roles
   (time / entity_identifier / measurement / text) with sample evidence IDs.
3. `search_evidence(query="...", limit=20)` for **text**: document text,
   operator notes and deviation descriptions use a persistent FTS5/BM25 index.
   Automatic routing recognizes exact observation/entity/source IDs and known
   metric aliases. Numeric cells and routine Status fields are not full-text
   indexed. An empty narrative search does not mean the measurements are normal.
   Use `evidence_type="narrative"` for SOP/assay/process-design questions; use
   `evidence_type="structured", metric="Status"` for sensor status records.
   Add `value_text="Warning"` for an exact categorical value. Structured queries
   use metric names/aliases and explicit filters; prose is not a SQL predicate.
   Filter with `source_id`, `entity_id`, `metric` (original header or canonical
   alias), `sheet`, `source_row`, `time_min`, `time_max`, and `time_basis="elapsed_hours"`.
   Times are hours in the stated basis; never row indices. Mean and SEM,
   different units and sampling contexts remain separate source measurements.
   `mode="semantic"` searches persisted local embeddings of narrative chunks;
   `mode="hybrid"` combines BM25 and semantic ranks. These require the optional
   semantic extra and are useful for paraphrased narrative concepts, not numeric
   comparisons. Lexical search is the default. Pagination and ties are stable.
4. `query_data(sql=..., limit=50)` for **numbers**: aggregations, trends,
   joins over the numeric projection. Use for "average pH by batch",
   "values outside spec limits".
5. `verify_evidence(observation_id="...")` before citing a key claim: checks
   source hash and transcribes the exact source cell/text.
6. `get_process_context(entity_id="batch-id")` to gather all records + linked
   entities for one batch/equipment/sample.
7. `normalize_measurements(observation_ids=[...], target_unit="...")` only for
   unit conversion of already-retrieved numeric observations.
8. `reconcile_entities()` when the same batch/equipment appears under
   different spellings across sources.
9. `extract_region(source_id=..., sheet=..., row=..., column=...)` or
   `(source_id=..., page=...)` to transcribe one source cell/page directly.
10. `get_state_at(limit=100)` to confirm what was visible at the cutoff.

Their arguments mirror the ManufacturingTools API:

```python
search_evidence(query="reactor pressure", limit=20)
search_evidence(query="viable cell density", entity_id="reactor-id",
                time_min=12, time_max=48, time_basis="elapsed_hours", limit=20)
search_evidence(query="assay holding time", evidence_type="narrative", limit=10)
get_process_context(entity_id="batch-id")
verify_evidence(observation_id="observation-id")
normalize_measurements(observation_ids=["id"], target_unit="milligram/liter")
query_data(sql="SELECT id, name, value_number, unit FROM observations WHERE name = 'pH'", limit=50)
extract_region(source_id="source-id", sheet="Sheet1", row=12, column="Result")
get_state_at(limit=100)
```

## query_data contract (read this before writing SQL)

- One statement, must start with `SELECT`. No `WITH` CTEs, no semicolons, no
  `read_parquet/read_csv/copy/attach/pragma/create/delete/insert/update/drop`.
- Must contain `FROM observations`. The only table is `observations`.
- Use the columns returned by `context().query_data_contract`; use
  `time_value/time_basis` for source-clock calculations and retain time IDs.
- `limit <= 1000` (plus `offset`). The bridge wraps your SQL as
  `SELECT * FROM (<your SQL>) LIMIT ? OFFSET ?`.
- Include `id` in the SELECT list whenever you want citations back: rows
  without `id` return `provenance_status: aggregate_lineage_unresolved` and
  cannot be cited.
- If a query fails, read the returned error and fix it; do not retry the same
  SQL unchanged. Common fixes from real runs:
  - `no table evidence` → use `FROM observations`.
  - `value_text not found` → that column is not in this view; use
    `search_evidence` or select only numeric columns.
  - `limit 1300` → use `limit <= 1000`.
  - `WITH v AS ...` → rewrite as a single SELECT with JOINs/subquery.

## Budget and finishing

- Call `context()` once at the start; re-check `remaining_tool_calls` as you go.
- Explore broadly first (inspect → search/query), then verify the 3-10
  observations you will actually cite. Do not spend 30+ calls on variants of
  one query.
- You MUST finish with `submit_report(report)` even on partial results, even
  after budget errors. A run that ends without it is a failure. Use this shape:

```python
submit_report({
  "assessment": "What the evidence currently supports and what remains unknown",
  "severity": "LOW",  # advisory proposal; final severity is policy-derived
  "evidence_ids": ["observation-id"],
  "findings": [{"statement": "Cited finding", "evidence_ids": ["observation-id"],
                "uncertainties": []}],
  "resolved_questions": [{"question": "What was measured?",
                           "finding": "Source value verified", "evidence_ids": ["observation-id"]}],
  "hypotheses": [{
    "hypothesis_id": "H-1", "statement": "Testable explanation",
    "causal_parent_ids": [], "causal_child_ids": [], "confidence": None,
    "supporting_evidence_ids": ["observation-id"],
    "contradicting_evidence_ids": [],
    "contradicting_evidence_status": "not_searched",
    "contradicting_evidence_absence_reason": "Counterevidence search remains pending",
    "unknowns": ["Missing evidence"],
    "tests_or_observations_that_would_discriminate": ["Independent check"]
  }],
  "open_questions": ["Missing evidence"],
  "evidence_requests": [{
    "evidence_type": "source review", "target": "batch-id",
    "reason": "Resolve conflict", "priority": "medium",
    "decision_dependency": "scope decision"
  }],
  "tasks": [{
    "owner": "QA", "action": "Review the investigation",
    "priority": "medium", "evidence_ids": ["observation-id"],
    "reason": "Human review is required"
  }],
  "decision_branches": [{
    "decision_id": "D-1", "condition": "Independent check confirms the signal",
    "if_true": [], "if_false": [],
    "actions_available_now": ["Review historical records"],
    "pending_dependencies": []
  }]
})
```

- The server rejects citations that were not seed evidence or returned by a
  tool in this run. Cite only IDs from `evidence_ids` you actually received.
- `verify_evidence` the 2-3 load-bearing claims before submitting.

Use the kernel to inspect and transform returned evidence. Keep source IDs and
observation IDs with claims. For independent questions, use Prime's native
`rlm.spawn(..., name="...")`; children can use the same skill. Ask children to
send back concise cited findings and contradictions with
`await agent_message.send(..., receiver_role="parent")`. Wait for their replies
before citing their findings. The lead owns synthesis.

Do not invent observations, use future information, or declare a root cause
confirmed from a candidate hypothesis. `submit_report` creates reviewable
state; it cannot approve or execute regulated actions.


## Deterministic verification tools and report sections

Use `summarize_series(entity_id="...", name="...")` for per-source means,
standard deviations, extrema and first/last values with real time coordinates.
Reported mean/SEM columns are transcribed source summaries; their underlying
replicates are not available merely because the header says Mean or SEM.

```python
from manufacturing_os import calculate_metrics, align_series, summarize_series
metrics = calculate_metrics(metrics=[{
    "metric_id": "peak-change", "operation": "percent_change",
    "numerator_ids": ["higher-peak-observation-id"],
    "denominator_ids": ["baseline-peak-observation-id"]
}])
aligned = align_series(
    left={"entity_id": "run-id", "name": "offline-variable"},
    right={"entity_id": "run-id", "name": "inline-variable"},
    method="nearest", tolerance_hours=0.25
)
```

Available operations: `mean, sem, sample_sd, sum, minimum, maximum, count,
percentage, percent_change, ratio, difference, yield`. Unary statistics accept
`evidence_ids` or `selection` with exact `name` and optional `source_id,
entity_id, sheet, time_start, time_end`. SEM requires declared
`sampling_basis="independent_replicates"`, actual raw replicate observations,
and one source time. A time-series SEM or SEM calculated from reported means
is rejected. Percent change is `100*(numerator-baseline)/baseline`; percentage
is `100*numerator/denominator`. State the denominator clearly.

Yield accepts two start/end `numerator_ids` and two start/end
`denominator_ids`, and a physical `definition`. Start/end entity and source
times must match exactly. It computes change in numerator / consumption in
denominator; concentration-based yield remains explicitly apparent, without
certifying feed, dilution, volume or mass balance. Zero/negative consumption
and mismatched clocks are rejected. Normalize incompatible units first.

Alignment offers exact, nearest and linear methods. Nearest ties, duplicate
source timestamps, missing clocks and different time bases are not silently
resolved. Linear interpolation retains both bracketing observations, weights,
and time IDs; it does not replace raw observations or extrapolate. Choose and
record a defensible tolerance rather than increasing it until a match appears.

Final reports use these separate fields:

- `observed_facts`: source statements, `observation_id` or `evidence_ids`, and
  optional `claimed_value` for a directly checked source value.
- `calculated_metrics`: metric specifications with `claimed_value`, or complete
  receipts returned by calculate_metrics (`value` is checked again). If a
  reported number is rounded, include explicit `display_decimals` in its spec.
- `interpretations`: conclusions about meaning, with `evidence_ids` and optional
  `metric_ids`. These require human review even when arithmetic checks pass.
- `hypotheses`: competing causal explanations, never verified causes. Both
  evidence roles require real IDs or an explicit `none_found`/`not_searched`
  status plus a nonempty absence reason. Do not claim a search found nothing
  when it was not performed.

Nested citations are combined automatically; you do not need to duplicate all
of them in the top-level evidence_ids. Submission checks immutable originals
in batches and does not expand routine instrument Status rows into millions of
citations. Runs and experiments are distinct from manufacturing batches.
`scope` describes cited evidence coverage; declare `affected_entity_ids`
separately, supported by citations. Proposed severity is retained separately
from the severity produced by the versioned operational routing policy.

The deterministic layer checks source identity, values, explicit arithmetic,
and alignment. It does not certify free prose, independence of samples,
biological plausibility, or causation. Report those limitations honestly.

## Coverage, specialist checkpoints and report completion

Only the lead owns the final report. Child `submit_report()` calls are routed to
`submit_subreport()` and cannot occupy its slot. A subreport is a scoped work
product with source verification pending final submission, not a completed
investigation. Use concise `observed_facts`, hypotheses, contradictions, open
questions and exact IDs. The lead reads `context().sub_investigations`; the full
checkpoint artifact preserves findings without copying child transcripts.

The tool limit is shared across lead and specialists. `context().budget` shows
remaining calls, elapsed/remaining time and the lead reserve. Specialists must
stop retrieval when their shared allowance is exhausted and save their work.
Reserve finalization time; do not spend the whole investigation on one entity.

`context().analysis_preparation.screening` contains deterministic coverage units,
grouped quality symptoms and diverse priority candidates with selection reasons.
Groups do not prove a common cause. End-of-run declines and constant signals may
be expected; percentage differences are not significance or triage severity.
All raw statistics/candidates remain in the complete artifact for exploration.

Final report additions:

```python
from manufacturing_os import validate_report, submit_subreport
report['report_type'] = 'final_investigation'  # or partial_investigation
report['coverage'] = [{
    'unit_id': 'unit-id-from-screening',
    'status': 'investigated',  # reviewed_no_material_signal/deferred/unresolved
    'reason': 'What was examined, comparison basis and remaining limitations',
    'evidence_ids': ['source-anchor-id']
}]
report['candidate_reviews'] = [{
    'candidate_id': 'candidate-id-from-screening',
    'status': 'contextualized',  # investigated/deferred/unresolved
    'reason': 'Why this signal warrants deeper work or is expected/ambiguous',
    'evidence_ids': ['candidate-source-anchor-id']
}]
report['cross_scope_synthesis'] = 'Shared patterns, exceptions, and limits across reviewed sources'
preflight = validate_report(report)  # cheap, nonpublishing; no retrieval budget charge
# Inspect preflight['issues']; missing coverage must remain explicitly incomplete.
```

Include one coverage disposition per scoped unit and one per preview priority
candidate. An empty/deferred disposition cannot count as completed review. A
numerically valid specialist report does not satisfy dataset-wide coverage.
Exact times and event-order claims need structured `temporal_claims`: `claim_id`,
`earlier_observation_id`, `later_observation_id`, `relation` before/coincident,
`tolerance_hours`. Cite the corresponding `time_evidence_id` clock cells and
link `temporal_claim_ids` from the relevant statement. Different entities or
unresolved clocks cannot establish temporal order through this check.

A source log ending proves only that the source log ends. It does not establish
that delivery stopped, a recipe changed or a biological mechanism caused a
collapse. Express these as competing hypotheses with missing independent checks.
Do not supply numeric hypothesis confidence: no statistical calibration exists.
Legacy confidence values are retained for audit and never shown as probabilities.

## Shared work and saved synthesis

The API exports `work_queue`, `allocate_work`, `evidence_packet`, `save_progress`,
`assemble_report`, `stopping_decision`, `validate_report`, and `submit_subreport`.
These coordination operations do not consume retrieval calls. The lead alone
allocates work and assembles the shared draft. Children save scoped subreports.

Start with `work_queue()` and batch unread sources using
`evidence_packet(requests=[{'source_id': sid, 'limit': 32}, ...])` (1–8 selectors).
Selectors support `unit_id, source_id, sheet, row, page, name, limit, offset`.
Packets include narrative cells, original coordinates and pagination. Inspect
truncation; a first read never automatically qualifies all source units.

`save_progress({'coverage': [...], 'claims': [...], ...})` upserts by section ID
and preserves omitted keyed records. List sections such as `open_questions`
are explicitly replaced. `assemble_report(subreport_ids=[...])['report']`
imports named specialist checkpoints and rejects conflicting keyed findings.
It produces a draft that still requires validation and original-source checks.

Lead allocations use `allocate_work(task_ids=[...], owner='...', reason='...',
calls=1)`. `extend=True` requests a bounded adaptive extension, only when the
frozen execution policy allows it. Shared hard limits and wall deadlines remain.
Specialists encountering lead reserve save their findings and notify the lead;
they must not repeatedly retry tools. Finalization closes exploration.

Use `stopping_decision(candidate_id=..., evidence_ids=[...], reason=...,
next_evidence=..., expected_to_change_action=False, available_in_scope=False)`
only after actual investigation. If further available evidence may change the
action, investigate it. If it is unavailable, retain specific evidence requests
and open questions. Operational convergence is not scientific qualification.

Claims may declare `display_decimals` (0–12) for linked computed `metric_ids`.
This permits only that explicit rounding of verified arithmetic. Temporal
claims can use `clock_basis='record_timestamps'` for cited timestamp cells with
explicit timezones; this establishes record ordering only. For process entity
alignment add `require_process_alignment=True`, or retain strict
`clock_basis='process_clock'` checks. Never use ingestion metadata as onset time.

## Source verification versus investigation completion

Exact JSON/text `line:N` anchors are now verified against original bytes. An
image-only PDF citation may return `human_review_pending`; pending review links
appear in `verification.pending_source_reviews`. Disclose the limitation and
route it to a human. A final investigation with completed scope and deliverables
can be saved while visual source review remains pending. This is not a technical
verification pass or scientific qualification. Do not claim unverified OCR is
confirmed, and never create human-review receipts as an agent. Source mismatches,
incorrect calculations and unsupported claims remain blockers. Use partial reports
for actual unfinished investigation work, not solely for disclosed visual review.
