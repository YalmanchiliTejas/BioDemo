# Manufacturing workflow benchmark execution — 2026-10-31

Raw receipts are archived in private DagsHub; the public presentation stays local.
Recovery pointer: `backend/benchmarks/assets/workflow-benchmark-20261031.json`. From `backend/`:

```sh
.tools/benchmark-offload/bin/python -m scripts.data_artifacts fetch \
  benchmarks/assets/workflow-benchmark-20261031.json results/workflow-benchmark-20261031
```

The local case-studies page now opens the workflow benchmark tab. Nothing was
deployed or pushed. This is a partial execution, not the proposed 60-task study.

## Results

| Ingestion layout | Executions | Field precision | Recall | F1 | p90 seconds | p99 seconds |
|---|---:|---:|---:|---:|---:|---:|
| Unseen | 100 | 100% | 100% | 100% | 0.870 | 1.179 |
| Returning | 100 | 100% | 100% | 100% | 2.222 | 3.934 |
| Changed | 100 | 99.67% | 100% | 99.83% | 2.264 | 2.623 |

These are actual deterministic IngestionService executions with local persistence,
not model inference or deployed API latency. They repeat three packages; they do
not represent 300 independent manufacturing incidents. Disjoint automated template
calibration and service setup are excluded from the timed target run. OS/interpreter
caches are uncontrolled. Some trials overlapped the investigation baseline, so the
recorded tails include that local machine contention.

All 300 completed, with zero observed silent omissions or incorrect automatic
acceptances. Changed layouts produced seven extra fields against the frozen key.
New and changed layouts still route most fields for review. Peak campaign process
RSS was 358.5 MiB. No human-time measurement was made. Public CHO measurements are
repackaged in invented company layouts/certificates with synthetic defects.

The deterministic investigation baseline executed all eleven CHO/Fresenius cases.
Five CHO reports completed; six Fresenius reports remained incomplete. Fresenius
critical-evidence recall ranged from 25% to 100%. CHO relevance precision/recall
remains null where defensible labels are absent. Citation location checks are not
claim-support judgments or scientific qualification.

The actual GLM 5.3 investigation runtime was attempted five times on FRE-02:

1. Missing credential in the isolated runtime; no paid dispatch.
2. The newly added gate rejected the SDK's token-limit field; no paid dispatch.
3. Conservative 12-request gate stopped the run after 12 paid requests.
4. Temporary concurrent reservations caused a premature admission rejection after
   75 paid requests; the gate was corrected to queue in-flight reservations.
5. The corrected queued gate forwarded 100 paid requests; the run reached that
   explicit ceiling without submitting a validated investigation report.

All five failures remain visible. No attempt is counted as a successful investigation.
The final attempt recorded 24 manufacturing bridge tool calls; model calls also cover
kernel work, children and orchestration. This is evidence to investigate finalization
and orchestration efficiency, not a production-wide GLM accuracy claim. No further
paid run was launched after the 100-request result.

## Cost and evidence

Modal's authenticated endpoint information confirmed shared billing. Rates were
verified at https://modal.com/library/zai/glm-5-3 : $1.40/M input, $0.26/M cached
input, $4.40/M output. All gates use full uncached rates for conservative estimates.
The first 12-request gate reserved at most $27. The subsequent two gates each had
a $10 held-cost cap. No cloud compute instances were provisioned.

Across the three inference attempts, 187 requests were forwarded. Proxy-settled
usage plus the earlier 12-call saved session gives approximately $10.14 at uncached
list rates. Two interrupted requests in the 75-call attempt lack complete proxy
usage and retain $4.50 of worst-case reservations. These are token-based estimates
and bounds, not a reconciled invoice or a claim that cached tokens were billed at
the uncached rate. Account-wide costs and earlier unrelated runs are separate.

Private receipts and logs: `backend/results/workflow-benchmark-20261031/`.
The top-level `report.md`, `summary.json` and `checksums.json` summarize the evidence.
Public presentation: `frontend/public/case-study-results/workflows/` contains only
the authored report, an explicitly selected result schema and file checksums.
Runtime logs, credentials and raw errors are excluded from the public export.

## Coverage still missing

Deviation detection lacks an admitted labeled agent suite. Manufacturing scheduling
lacks an executable resource optimizer admitted to this benchmark. Neither receives
a fabricated score. Independent relevance labels, blinded scientific review and a
larger application-level latency sample remain necessary for the proposed campaign.

## Reproduction and verification

Run from `backend/` using its existing virtual environment:

```sh
.venv/bin/python -m benchmarks.cmo_ingestion.workflow_campaign \
  --packages benchmarks/cmo_ingestion/demo \
  --output results/NEW-INGESTION-CAMPAIGN --repeats 100

.venv/bin/python scripts/summarize_workflow_benchmark.py \
  --root results/workflow-benchmark-20261031 \
  --public-output ../frontend/public/case-study-results/workflows
```

New campaigns require fresh output paths; existing trial receipts are preserved.
Do not launch additional paid agent trials by copying commands without accounting
for existing reservations and campaign spend.

Verification: 114 existing workflow/ingestion regression checks passed; three gate
checks passed, including concurrent reservation queuing, failed-request accounting,
both token-limit fields, missing-usage handling and secret-free receipts. Frontend
TypeScript passed. The unauthenticated browser verified the score table, retained
failures, coverage gaps and SHA-256 of both downloads. The mobile page has no root
horizontal overflow; its wide table scrolls within its own container.
