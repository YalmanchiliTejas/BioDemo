# Workflow trial

Started 2026-11-15T15:54:21.469301+00:00. Target: an answer within 10 s.

**B, direct workflows:** 246/246 requests matched their reference; mean 0.012 s, p95 0.034 s, slowest 0.204 s; 0 over the target. Reasoning-model calls: 0 (blocked attempts: 0).

| Job | Requests | Passed | Mean s | p95 s | Slowest s | Over target |
|---|---:|---:|---:|---:|---:|---:|
| 01 find records | 18 | 18 | 0.024 | 0.096 | 0.096 | 0 |
| 02 select evidence | 27 | 27 | 0.003 | 0.004 | 0.004 | 0 |
| 03 reconcile | 18 | 18 | 0.017 | 0.204 | 0.204 | 0 |
| 04 compare | 99 | 99 | 0.009 | 0.014 | 0.036 | 0 |
| 05 suggest causes | 9 | 9 | 0.005 | 0.006 | 0.006 | 0 |
| 06 find gaps | 18 | 18 | 0.026 | 0.055 | 0.055 | 0 |
| 07 trace impact | 12 | 12 | 0.007 | 0.015 | 0.015 | 0 |
| 08 prepare review | 9 | 9 | 0.005 | 0.005 | 0.005 | 0 |
| 08 propose action | 9 | 9 | 0.017 | 0.018 | 0.018 | 0 |
| prepared profile | 9 | 9 | 0.012 | 0.034 | 0.034 | 0 |
| template as a flow | 9 | 9 | 0.030 | 0.034 | 0.034 | 0 |
| trust gate | 9 | 9 | 0.004 | 0.005 | 0.005 | 0 |

**Typed sentences, host rules:** 261 requests: {"direct_correct": 81, "assistant_routine_missed": 99, "assistant_correct": 81}. A wrong task run directly is the serious error; a routine request left to the assistant is only slower.

**C, decision model:** run

Limits: Small trial: three deliveries, one site, laboratory scale. Repeats measure variation, not new cases. Percentiles of a sample this size do not establish a production figure. Cause-finding is not scored: these deliveries record no reviewed cause. Job 05 is checked only for making no claim. The assistant and the explanation model are not run here; they are measured by benchmarks.workflow_trial.live. The deliveries are still in review, so every calculation here is on provisional values and says so.
