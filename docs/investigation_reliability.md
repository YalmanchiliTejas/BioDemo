# Investigation coverage, scientific limits and orchestration repair

Implemented changes preserve ingestion, scoped Parquet/DuckDB queries, persistent text retrieval, deterministic statistics, the RLM, immutable evidence IDs and human approval gates. No experiment identifiers or expected anomalies appear in the prioritization or validation rules.

## Diagnosis from the latest frozen CHO-04 execution

Run `ec32259a437d4ccea9dc47bf4ef654c0` completed execution in **799.651 seconds**. Ingestion took 19.635 seconds, preparation 25.049 seconds, and the root SDK reported 129 model calls and 48 admitted manufacturing calls. Child usage is not included in those model totals. The tool log additionally contains 18 attempts rejected after budget exhaustion; failed admitted calls include a zero denominator, a cross-entity alignment, an unsupported query and a 106-metric request exceeding the existing 32-metric batch contract.

The principal orchestration bug is visible in the persisted sessions. A specialist (`01a14ad3-d76a-773a-b7a3-6e5e4337f2b8`) successfully called `submit_report` at **17:11:36 UTC**. The shared bridge accepted its EXP011 work as its sole durable report. At **17:15:57**, the lead attempted a broader report and received “this Prime run already submitted a report.” The old `submit_report` guarded only `self.result`, not caller role or report scope. Child and lead sessions share the same skill/bridge credentials and report endpoint. Completion of a specialist therefore prevented the lead from synthesizing the investigation.

All **76 final citation locations** came from one workbook, while machine preparation covered 12 sources / 24 reactor entities. The bridge populated `examined_scope` from deterministic extrema, not completed agent review. It did not require explicit dispositions for the other entities. Execution completion and source verification consequently looked like investigation completion.

Scientific checking in `report_verification.py` validated citation availability, original cell values and explicit arithmetic. It expressly did not certify prose, event onset, biological mechanisms or causal direction. A source number present somewhere in the report's citation set could also satisfy the conservative prose-literal diagnostic; that diagnostic is not a sentence-to-measurement proof. The old label `source_value_verified; statement interpretation requires review` and numerical hypothesis confidence were easy to overread. A truncated feed source, a sensor signal and actual physical delivery are distinct evidence questions; agreement between signals does not prove a mechanism. Source-clock ordering does not establish exact event onset or causation.

The previous preview selected the first 12 anomaly series after sorting flags and the first 12 paired peaks after sorting by percentage relative to the smaller peak. Shared clock defects appeared repeatedly for different columns. Small denominators exaggerated peak differences; zero denominators were omitted. This preview had neither source/family diversity nor explicit coverage obligations. The raw flags were legitimate screening outputs, not independently adjudicated manufacturing faults.

## Implemented changes and priorities

| Priority | Change | Benefit and trade-off |
|---|---|---|
| P0 | Separate specialist checkpoints from the lead report | A child cannot fill the final slot through the supported skill. Lead summaries remain available without transcript scraping. Caller depth is SDK-provided coordination metadata, not a new hostile-code security boundary. Existing evidence scope/authentication remains authoritative. |
| P0 | Explicit coverage and final-report status | Every scoped source/entity needs a reviewed/deferred/unresolved disposition with reason and matching evidence. Screening and citations do not count as completed review. Explicit partial reports persist as incomplete and cannot qualify. |
| P0 | Early, nonpublishing report preflight | Coverage and clock problems are returned before expensive original checks. A purported final report with missing work saves a checkpoint and returns `needs_more_work`, leaving the final slot open. Preflight never certifies original values or arithmetic. |
| P0 | Structured temporal claims | Same entity, actual comparable clocks, clock citations and declared tolerances are checked. Missing, duplicate or backward clocks remain unverified. False source ordering is rejected. |
| P1 | Grouped quality symptoms and balanced preview | All raw flags remain available. Repeated clock/flatline symptoms become review groups, without asserting one common cause. The preview balances sources, measurement families and categories. |
| P1 | Safer descriptive comparisons | Absolute differences and bounded symmetric peak differences expose small/zero-baseline behavior. Peak-to-last signals reveal trajectory differences without inventing thresholds, failure labels or clinical severity. |
| P1 | Qualitative hypothesis presentation | `confidence` is null; old numerical judgments remain in `legacy_agent_confidence` for audit. Evidence roles and unresolved checks are shown instead of probability-like percentages. |
| P1 | Shared budget and interruption handling | Specialists see a shared allowance and cannot consume the lead's reserved calls. Source-scoped checkpoints survive cancellation; partial stdout/stderr and tool history are retained on host timeout. No budget increase was introduced. |
| P1 | Honest demo output | Live and comparison views distinguish screened/reviewed/cited coverage, observations, interpretations, missing synthesis and partial results. A stale served-story work-count snapshot was regenerated from the existing measurement service; unknown/unassigned work remains unmeasured. |

Implementation locations:

- `src/manufacturing_data/screening.py`: pure source-statistic grouping, coverage units and deterministic priority selection.
- `src/manufacturing_data/analysis.py`: retains complete statistics/anomalies, includes zero-baseline comparisons, exposes compact diverse screening metadata.
- `src/manufacturing_data/tools.py`: scoped `summarize_series` anomaly results now obey the same entity/source/name/sheet filters as its statistics.
- `src/workflows/investigation_review.py`: coverage, candidate dispositions, required report structure, temporal checks and explicit incompleteness.
- `src/workflows/report_verification.py`: precise source-value/unit/time checks and a clearer boundary between checked values and statement interpretation.
- `src/state/causal_hypothesis_graph.py`, `blackboard.py`: qualitative evidence assessment, legacy confidence audit and persisted investigation review/synthesis.
- `src/prime_runtime/bridge.py`, `harness.py`: specialist/lead separation, exposure records, budget reserve, checkpoints, preflight and timeout logs.
- `prime_skills/manufacturing_os`: updated skill instructions and `submit_subreport` / `validate_report` client endpoints. SDK `RLM_DEPTH` distinguishes lead and child calls; the adjacent SDK already sets that environment variable per kernel.
- `src/workflows/manufacturing.py`: persists completeness/synthesis/temporal records and invalidates prior review approval when those material records change.
- `benchmarks/common/case_runner.py`, `quality.py`, `full_agent_adapter.py`: incomplete executions cannot qualify; checkpoint artifacts are copied; ingestion time is included in the remaining host budget.
- `src/prime_runtime/compare.py`, `benchmark/application/demo_runs.py`, `api.py`, static `summary.js` / `platform.js` / `incident.js`: durable artifacts and honest user-facing scope/uncertainty.

The 13 manufacturing evidence/analysis handlers are unchanged. New endpoints are report coordination, not arbitrary SQL or unbudgeted evidence search. They accept only already exposed citations. They cannot approve release, disposition, CAPA or process changes. Site triage policy remains separate from descriptive prioritization.

## Report contract

The lead declares `report_type`: `final_investigation` or `partial_investigation`. A specialist produces `sub_investigation` and never a final slot. Each `coverage` entry contains a scoped `unit_id`, status, reasoning summary and evidence IDs belonging to that source/entity. Accepted review statuses are `investigated` and `reviewed_no_material_signal`; `deferred` and `unresolved` remain incomplete. These states validate provenance and structure, not reasoning adequacy.

Each priority candidate needs a cited `candidate_reviews` disposition: investigated, contextualized, deferred or unresolved. Contextualizing an expected harvest decline is valid when supported and explained. The lead must supply `cross_scope_synthesis` and the required findings, competing hypotheses, uncertainty, follow-up and evidence-request structures. No requirement forces deep analysis of every normal series; the requirement is an accountable review decision for each scoped unit and selected candidate.

Structured `temporal_claims` use `claim_id`, `earlier_observation_id`, `later_observation_id`, relation before/coincident and explicit tolerance hours. Both source clock cells must be cited. Statements link their `temporal_claim_ids`. Receipt text distinguishes sampled order from event onset and causation. Heuristic prose warnings catch some unlinked temporal/causal language but cannot prove the semantics of unrestricted natural language.

`validate_report` checks the structure and source clock coordinates without publishing, consuming a retrieval call, recomputing all metrics or opening originals. `submit_report` still verifies original sources and recomputes metrics. Scientific/numerical/source issues preserve an incomplete status. Even `complete_for_available_evidence` means available-evidence structure is complete; independent scientific review is still required.

Preparation exposure is explicit: compact anchors become exposed when supplied; the larger anchor set becomes citable only when the complete artifact is written and made available. The bridge records its hash and exposure count. Merely discovering an ID in preparation does not silently make the entire prepared set citable when no artifact is provided.

## Frozen-case validation and measurements

The offline audit cloned metadata and hardlinked immutable originals into a temporary private store. It used existing authorized partitions and preserved source bytes, IDs and the original run files. No scorer reference answers, rubrics or expected anomalies were agent inputs. There was no model call.

Artifacts are in `results/verification/ec32259a437d4ccea9dc47bf4ef654c0-review-v2/`:

| Check | Measured result |
|---|---|
| Original citations rechecked | **76 / 76** source/value checks passed |
| Original structured arithmetic rechecked | **7** metrics verified |
| Retained original-source hashes | **12 / 12** match ingestion metadata |
| New preparation | **24.988 s**; original run preparation was 25.049 s (different execution conditions) |
| Source/arithmetic re-verification | **8.708 s** |
| Raw flags retained | **389 series, 533 individual flags** |
| Grouped quality review candidates | **44** groups, not claimed independent events |
| Priority preview diversity | **12 workbooks, 9 families**; 4 endpoint, 3 paired, 3 constant-series and 2 clock candidates |
| Prior report classification | **Incomplete**; dataset-wide review/synthesis not established |
| New complete RLM latency/completeness | **Not measured** |
| Scientific correctness, relevance recall/precision | **Unscored**, pending independent labels/review |

A separate pure-Python screening rebuild from the earlier saved statistics took 0.143–0.225 seconds over three trials. That saved v1 input omitted zero-baseline comparisons, so its exact preview differs from the complete v2 audit; it measures builder overhead, not new scientific accuracy. A first full audit overlapped regression tests and took 48.856 seconds for preparation; the less-contended repeat took 24.988 seconds. This variation is retained in the engineering record rather than presented as a guaranteed speedup.

The implementation prevents the demonstrated specialist-slot failure in regression tests and does not add LLM calls or source scans for screening candidate grouping. It does not demonstrate that the next live investigation will finish under 300 seconds. No Modal token is available to the current execution environment, so a fresh provider-backed frozen-case trial could not be performed here.

## Acceptance criteria for subsequent live trials

1. No specialist submission occupies the lead slot. Every child result is identified as a sub-investigation; parent/child role and budget admission are traceable.
2. All source/entity units receive explicit dispositions. A complete CHO-04 report has **24 reviewed units** spanning its scoped 12 workbooks, with a cross-source synthesis. Any unresolved required unit/candidate remains incomplete.
3. Every material citation resolves at the permitted cutoff/scope and matches its original location/value. Target citation validity is **100%**; source workbooks and package hashes remain unchanged.
4. All declared structured metrics pass arithmetic/unit checks. Unknown raw replicates are never reconstructed from reported Mean/SEM headers. Undefined ratios remain undefined.
5. Temporal-order claims have validated source clocks or explicit unverified status. Duplicate/reset clocks cannot be presented as a verified sequence. No sampled ordering receipt is treated as causal proof.
6. Each causal hypothesis has support and contradiction search outcomes; not-searched counterevidence blocks complete status. Lack of an external recipe/calibration record remains a named uncertainty, not evidence of a failed controller or physical feed cessation.
7. Preview covers distinct sources/families and quality/process categories while retaining all raw observations/candidates. A flag count is never displayed as a count of manufacturing failures.
8. Preserve the 48-call admitted limit and lead reserve. Record rejected attempts separately. Do not count checkpoints or report preflight as evidence retrieval. Persist useful incomplete progress on interruption.
9. Run at least three isolated trials of the unchanged frozen case; report completion rate, tool admission/rejection counts, root and child model usage where available, latency median/range, citation validity and independent completeness/contradiction review. Aim for under 300 seconds; report achieved latency honestly if quality requires more time.
10. Existing independent-review policy and unresolved domain-approved quality threshold stay visible. No quality score, relevance judgment, human-effort saving or manufacturing authorization is invented.

## Reproduce

```sh
PYTHONPATH=. .venv/bin/python scripts/audit_investigation_run.py \
  --run results/evaluation/ec32259a437d4ccea9dc47bf4ef654c0 \
  --output results/verification/ec32259a437d4ccea9dc47bf4ef654c0-review-v2
.venv/bin/python -m pytest -q tests/test_investigation_review.py tests/test_deterministic_analysis.py tests/test_prime_runtime.py tests/test_demo_runs.py
```

HTTP/integration tests need permission to bind localhost. The full regression command and result are recorded with the final implementation summary.

## Remaining limits

Coverage and claims remain model-authored explanations; deterministic structure/source checks do not prove scientific adequacy or catch all misleading prose. New general patterns can be investigated beyond the heuristic preview. Empty initial narrative units may require targeted retrieval before a review decision. Clock corruption can require external corrected records; the validator deliberately does not invent reconstruction. The caller-depth guard coordinates cooperating SDK kernels and is not a substitute for access controls against hostile Python. Checkpoints preserve recoverable work but do not automatically restart a cancelled model session. Worker process-group cancellation remains the isolation layer's responsibility. Live latency, full child token accounting, relevance recall and domain-reviewed final quality remain to be measured.

## Final test record

The affected regression run passed **114 tests with 2 skipped** in 65.09 seconds:

```sh
.venv/bin/python -m pytest -q tests/test_investigation_review.py tests/test_prime_runtime.py tests/test_deterministic_analysis.py tests/test_manufacturing_data.py tests/test_retrieval.py tests/test_columnar_ingestion.py tests/test_case_evaluation_v2.py tests/test_no_future_leakage.py tests/test_demo_runs.py tests/test_prime_compare.py tests/test_demo_presentation.py --disable-warnings --maxfail=2
```

A subsequently added final-slot correction regression and the non-HTTP review subset passed **10 tests**. The actual HTTP child-depth/lead-finalization and host-timeout checkpoint tests passed in the earlier full run. Compilation, JavaScript syntax checks and `git diff --check` passed.

The historical comparison suite passed **37 tests and failed 1**: `ChoCaseTests.test_recorded_prime_pilot_is_wired` requires absent `runs/cho-comparison/comparison.json`. This is an unavailable recorded pilot fixture, not a fabricated substitute for the new frozen-case audit. The stale static-report mismatch was corrected by regenerating the report from available recorded artifacts; its currency test passes. No relevance labels, pilot results or quality scores were manufactured to satisfy that remaining fixture-dependent test.
