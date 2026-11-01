# Actual GLM 5.3 agent accuracy

Actual GLM 5.3 through the Prime SDK and scoped Manufacturing OS tools. This cohort evaluates native task answers, separately from full QA-report completion. No deterministic answer substitution or model judge.

Developer-authored explicit operational rules and exhaustive scheduling references, not independently adjudicated factory incidents.

60/60 tasks attempted. 53 exactly correct agent answers. 53 machine-readable answers returned.

| Workflow | Attempted / planned | Exactly correct | Precision | Recall | F1 | Answers returned | p90 seconds | p99 seconds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| deviations | 15/15 | 15 | 100.00% | 100.00% | 100.00% | 15 | 110.79 | 114.30 |
| ingestion | 15/15 | 14 | 100.00% | 91.43% | 95.52% | 14 | 104.69 | 105.87 |
| investigations | 15/15 | 15 | 100.00% | 100.00% | 100.00% | 15 | 45.18 | 60.28 |
| scheduling | 15/15 | 9 | — | — | — | 9 | 76.48 | 76.48 |

Local agent pipeline at concurrency two. Answer percentiles include emitted structured answers; failures remain in task accuracy and terminal durations. At 15 cases per workflow, empirical p99 is the maximum and is exploratory. Per-task timing starts at its inference admission phase; it excludes campaign waiting during budget reconciliation. Only tasks with zero prior provider usage and no generated content were resumed.

Every input/answer pair is inspectable in cases.json, including failures. Gold keys were outside agent inputs and OS-denied during execution. The deterministic parser accepts one unambiguous structured JSON answer, including when surrounded by prose; it never interprets prose or selects an answer using the key.

Precision/recall measure returned batch/result IDs and correct normalized values. Scheduling uses independent constraint/optimality checks. These do not measure independently established root causes, regulatory compliance or production scheduling qualification.

Calibration and earlier interrupted large-case investigations are excluded from these scored-task percentages and retained in their separate receipts.

Provider calls admitted: 495. Usage-based list-rate estimate: $5.3338; invoice not reconciled.

Frozen protocol SHA-256: 1bfa6875c8da38d61254b50547fc5e497ff63188b4743a34a63bc9284feaf86c
