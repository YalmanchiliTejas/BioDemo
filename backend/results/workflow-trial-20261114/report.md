# Workflow trial

Started 2026-11-15T06:22:34.501568+00:00. Target: an answer within 10 s.

**B, direct workflows:** 189/189 requests matched their reference; mean 0.010 s, p95 0.022 s, slowest 0.224 s; 0 over the target. Reasoning-model calls: 0 (blocked attempts: 0).

| Job | Requests | Passed | Mean s | p95 s | Slowest s | Over target |
|---|---:|---:|---:|---:|---:|---:|
| 01 find records | 18 | 18 | 0.026 | 0.106 | 0.106 | 0 |
| 02 select evidence | 27 | 27 | 0.004 | 0.004 | 0.004 | 0 |
| 03 reconcile | 18 | 18 | 0.020 | 0.224 | 0.224 | 0 |
| 04 compare | 81 | 81 | 0.009 | 0.013 | 0.031 | 0 |
| 05 suggest causes | 9 | 9 | 0.005 | 0.006 | 0.006 | 0 |
| 06 find gaps | 9 | 9 | 0.017 | 0.018 | 0.018 | 0 |
| 07 trace impact | 9 | 9 | 0.004 | 0.006 | 0.006 | 0 |
| 08 prepare review | 9 | 9 | 0.005 | 0.005 | 0.005 | 0 |
| trust gate | 9 | 9 | 0.004 | 0.004 | 0.004 | 0 |

**Typed sentences, host rules:** 261 requests: {"direct_correct": 81, "assistant_routine_missed": 99, "assistant_correct": 81}. A wrong task run directly is the serious error; a routine request left to the assistant is only slower.

**C, decision model:** not_run (LIFESCI_DECISION_ADAPTER=jev and TYPESAFE_API_KEY are not set; nothing was substituted.)

Limits: Small trial: three deliveries, one site, laboratory scale. Repeats measure variation, not new cases. Percentiles of a sample this size do not establish a production figure. Cause-finding is not scored: these deliveries record no reviewed cause. Job 05 is checked only for making no claim. The assistant (A) is not run here; its measured time is in results/evaluation-20261114. The deliveries are still in review, so every calculation here is on provisional values and says so.
