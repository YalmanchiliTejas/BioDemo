# Live evaluations — 16 November 2026

**Real GLM-5.3 calls were made to the configured Modal endpoint. This batch did not demonstrate reliable end-to-end completion.**

| Measure | Recorded result |
|---|---:|
| Native cases planned / recorded | 24 / 24 |
| Cases receiving a model response | 15 |
| Frozen-grader passes | 9/24 |
| Passed and finished the assistant turn | 8/24 |
| Mean time, passed and finished | 110.1 s |
| Mean time, all recorded outcomes including failures | 128.6 s |
| CHO investigation | Incomplete; no final report |
| Affected regression tests after restoration | 55 passed, 1 failed |

## What was exercised

- **Lyo:** 24 authored synthetic cases, six each for calculations, recipe selection, missing inputs, and model scope. These use the existing application tool loop and real pinned LyoPRONTO solver through a research connector. They measure tool use, not predictive accuracy on plant data or the complete deviation/QA workflow.
- **CHO:** One investigation over all 12 original public cultivation workbooks, using the existing Prime SDK harness. It has no causal ground-truth score. Ingestion and analysis began, but the investigation did not produce a final report.
- The separate scripted preflight used zero inference requests and is excluded from all live results.

## Native outcomes

| Family | Strict passes / cases | Mean episode seconds |
|---|---:|---:|
| missing_inputs | 0/6 | 139.3 |
| recipe_selection | 3/6 | 138.1 |
| report | 4/6 | 86.0 |
| scope_limits | 2/6 | 151.2 |

The frozen scores are unchanged. Inspection found three exact-string grading rejections: the agent explicitly named the required missing parameter and appended an explanation, which the schema permits but the grader rejects. One of those turns also timed out. These are documented separately rather than silently rescored.

Two completed answers contain numerical errors: one saved a whole-batch rate of **3.24067 kg/h instead of 0.06538 kg/h**; another selected the correct recipe but reported incorrect thermal and equipment-capacity margins. One other case saved a correctly graded assessment, then timed out before completing its reply; it is excluded from the finished-success count.

Later cases timed out waiting for admission behind an unresolved provider response. The batch success fraction therefore mixes answer quality, application completion, and the evaluation budget gate. It must not be described as general model accuracy.

See [case-by-case results](native/agent/results.json), [failure inspection](failure-review.json), and [timing and cost metrics](metrics.json).

## Timing

Episode time starts after workspace seeding and includes the assistant turn, tools, admission waits, and grading. It excludes setup and runtime cleanup. The passing-case mean is conditional on success; failed tasks do not have a successful completion time. No human review or correction time was measured. Concurrent request/tool totals are not wall-clock completion time.

## Inference and budget

| Campaign | Forwarded requests | Usage receipts | Known-usage estimate | Unknown-usage hold |
|---|---:|---:|---:|---:|
| native | 86 | 85 | $1.5134 | $2.25 |
| cho | 74 | 73 | $0.8180 | $2.25 |

Known usage totals **$2.3315**; including unknown-usage reservations, the conservative total is **$6.8315**, within the $10 first-batch cap. These are token-rate estimates and reservations, not an invoice. [Published pricing](https://modal.com/library/zai/glm-5-3) was checked before running.

The CHO gate recorded request 74 as HTTP 200 followed by `BrokenPipeError`, without usage counters. It retained $2.25 and rejected further dispatch under the $4 campaign cap. The SDK described the resulting local 402 as insufficient balance; that does **not** establish a Modal account billing problem. The failed attempt is preserved in [CHO artifacts](../../runs/cho-comparison/). No successful pilot fixture was fabricated and no failed case was silently rerun.

## Restored files and checks

- Restored 48 publisher-aligned CHO CSVs and the raw dataset archive/workbooks using the repository artifact tool with checksum verification.
- Restored the external LyoPRONTO checkout at commit `c6a9225a9e551ae4e7c11c1ef056b67c6204afbd` in `/private/tmp/lyohub-rerun-source`.
- Regenerated the existing static benchmark report from recorded artifacts; its previous version is retained in `prior-static-report/`.
- Reran `test_lyopronto_native.py`, `test_lyohub_study.py`, and `test_case_comparison.py`: **55 passed, 1 failed**. The remaining assertion requires the missing completed CHO pilot. [Test log](logs/restored-tests-after-live.log). The full backend suite was not rerun.
- Production databases were disabled. There were no manufacturing-control actions, official quality approvals, commits, pushes, or deployments.

## Reproduction and evidence

The [driver](execute.py), [outer protocol](protocol.json), [frozen native protocol](native/frozen/protocol.json), provider admission ledgers, per-case SQLite stores, model receipts, and solver outputs are retained here. The inner native protocol allows $10; the outer gate applied the stricter $6 native / $4 CHO split. Repeating a paid run requires a fresh output directory and an explicit new budget; the existing artifacts must not be overwritten.
