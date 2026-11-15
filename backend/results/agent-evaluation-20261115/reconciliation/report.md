# Workflow trial

Started 2026-11-15T20:25:24.620907+00:00. Target: an answer within 10 s.

**B, direct workflows:** 410/410 requests matched their reference; mean 0.012 s, p95 0.036 s, slowest 0.205 s; 0 over the target. Reasoning-model calls: 0 (blocked attempts: 0).

| Job | Requests | Passed | Mean s | p95 s | Slowest s | Over target |
|---|---:|---:|---:|---:|---:|---:|
| 01 find records | 30 | 30 | 0.025 | 0.089 | 0.095 | 0 |
| 02 select evidence | 45 | 45 | 0.004 | 0.004 | 0.004 | 0 |
| 03 reconcile | 30 | 30 | 0.013 | 0.011 | 0.205 | 0 |
| 04 compare | 165 | 165 | 0.009 | 0.015 | 0.040 | 0 |
| 05 suggest causes | 15 | 15 | 0.006 | 0.007 | 0.007 | 0 |
| 06 find gaps | 30 | 30 | 0.029 | 0.058 | 0.075 | 0 |
| 07 trace impact | 20 | 20 | 0.009 | 0.021 | 0.029 | 0 |
| 08 prepare review | 15 | 15 | 0.005 | 0.006 | 0.006 | 0 |
| 08 propose action | 15 | 15 | 0.019 | 0.027 | 0.027 | 0 |
| prepared profile | 15 | 15 | 0.010 | 0.034 | 0.034 | 0 |
| template as a flow | 15 | 15 | 0.032 | 0.037 | 0.037 | 0 |
| trust gate | 15 | 15 | 0.005 | 0.006 | 0.006 | 0 |

**Typed sentences, host rules:** 435 requests: {"direct_correct": 135, "assistant_routine_missed": 165, "assistant_correct": 135}. A wrong task run directly is the serious error; a routine request left to the assistant is only slower.

**C, decision model:** not_run (LIFESCI_DECISION_ADAPTER=jev and TYPESAFE_API_KEY are not set; nothing was substituted.)

Limits: Small trial: three deliveries, one site, laboratory scale. Repeats measure variation, not new cases. Percentiles of a sample this size do not establish a production figure. Cause-finding is not scored: these deliveries record no reviewed cause. Job 05 is checked only for making no claim. The assistant and the explanation model are not run here; they are measured by benchmarks.workflow_trial.live. The deliveries are still in review, so every calculation here is on provisional values and says so.
