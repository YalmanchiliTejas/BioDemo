# Agent correctness and completion time

Fresh live GLM-5.3 runs on the current product tool loop. Accuracy and latency use every planned attempt; failures remain in the denominator. Question/task replies were also reviewed against their saved results for material factual errors.

| Capability | Correct after review / attempts | Mean, all attempts | Mean, correct | Mean, failed | p95, all |
|---|---:|---:|---:|---:|---:|
| Answer numerical questions | 17/18 (94.4%) | 15.87 s | 16.06 s | 12.75 s | 49.89 s |
| Save and explain a comparison | 17/18 (94.4%) | 38.46 s | 35.76 s | 84.41 s | 85.54 s |
| Set up recurring tasks | 19/20 (95.0%) | 8.41 s | 7.10 s | 33.30 s | 23.07 s |

Combined correctness after review: **53/56 (94.6%)**. Average completion time: **20.47 s**; correct attempts: **19.17 s**.

The automatic objective checks passed 55/56. Review found material factual errors in 2 replies; those attempts are counted as incorrect above.

Timing starts immediately before submission to the local application service and ends after the completed turn is retrieved. Setup, evaluation scoring and future routine execution are outside that timer.

## Correctness scope

Authored evaluations: six CHO evidence cases with question/task forms, three repeats; four recurring prompts, five repeats. Repeats are correlated.
Question/task correctness requires the frozen objective checks plus no material factual error found in Codex review of each saved reply against its result. Automated figure coverage remains reported separately. This is development trace review, not independent scientific validation.
Known conflicting measurements must remain flagged; a correct needs-information result does not mean the conflict was resolved.
Recurring correctness means a correct saved draft plus behavior after explicit test-person activation. Local clocks are advanced; no production scheduler or elapsed-day validation.

## Component checks — separate from agent completion

- Domain functions: 810/1493 correct. These execute directly without the agent.
- Decision routing: 1152/1200 correct; 0.237 s per batch of 20. This is not individual question completion time.
- Direct workflows: 410/410 matched expected behavior. Expected refusals and needs-information responses count as appropriate behavior, not completed manufacturing work.

## Repeated cases

| Capability | Case | Correct / repeats |
|---|---|---:|
| Answer numerical questions | cho-changed:glucose:question | 2/3 |
| Answer numerical questions | cho-changed:viable_cell_density:question | 3/3 |
| Answer numerical questions | cho-returning:glucose:question | 3/3 |
| Answer numerical questions | cho-returning:viable_cell_density:question | 3/3 |
| Answer numerical questions | cho-unseen:glucose:question | 3/3 |
| Answer numerical questions | cho-unseen:viable_cell_density:question | 3/3 |
| Save and explain a comparison | cho-changed:glucose:task | 3/3 |
| Save and explain a comparison | cho-changed:viable_cell_density:task | 3/3 |
| Save and explain a comparison | cho-returning:glucose:task | 3/3 |
| Save and explain a comparison | cho-returning:viable_cell_density:task | 3/3 |
| Save and explain a comparison | cho-unseen:glucose:task | 3/3 |
| Save and explain a comparison | cho-unseen:viable_cell_density:task | 2/3 |
| Set up recurring tasks | case-event | 4/5 |
| Set up recurring tasks | daily-interval | 5/5 |
| Set up recurring tasks | hourly | 5/5 |
| Set up recurring tasks | quarter-hour | 5/5 |

## Errors found in reply review

- cho-changed--glucose--question--repeat-3: Says 10 of 19 samples paired (90%), contradicting both its opening 9 pairs and saved result. There are 9 matched times; the two non-conflicted series have 10 and 9 samples, and the tool reports share_of_samples_matched=0.9. 10/19 is not 90%.
- cho-unseen--viable_cell_density--task--repeat-1: Claims trajectories cross twice, but stored differences change sign across several additional adjacent samples. The requested mean, maximum difference and time are correct. Lists CHO-010-R02 among companions not used for this comparison although R02 is one of the two compared batches.
- case-event-r4: failed one_saved_routine; saved 2 routines with run limits [2, 3].

## Cost and background work

GLM: $3.4117 estimated across 165 provider calls; decision routing: $0.0188 reported. Hosted invoice cost is unknown.

Recurring functional success is separate from the no-background-inference check: 0/20 passed the full lifecycle including that check; 19 background model runs were observed.

The original raw outcome field labels background inference wrong_value. Functional correctness uses unchanged definition_pass and lifecycle_behavior_pass fields; the saved snapshot preserves the executed runner.

## Limits and unrun work

- Agent time spans enqueue through final turn retrieval, excluding fixture setup, scoring and subsequent lifecycle/memory work; browser and deployed queue delays are not measured.
- Three answer workers overlap one recurring worker on the shared model endpoint; these are observed local campaign timings, not production guarantees.
- Background memory inference is separated from functional correctness and included in the token cost.
- BFCL V4, IBM paraphrase robustness and MuSiQue remain unrun; no established full-agent benchmark score is claimed.
- Sandbox connectivity failures and the pre-inference cache-name collision are retained as infrastructure attempts, not substituted for live results.
- Costs are token-rate estimates/reported decision costs, not reconciled hosted invoices.

## Saved evidence

- [answers](/Users/tejas/Desktop/BioDemo/backend/results/agent-evaluation-20261115/answers-live/report.json)
- [recurring](/Users/tejas/Desktop/BioDemo/backend/results/agent-evaluation-20261115/recurring-timed-20261115/report.json)
- [domain](/Users/tejas/Desktop/BioDemo/backend/results/agent-evaluation-20261115/domain/report.json)
- [decision](/Users/tejas/Desktop/BioDemo/backend/results/agent-evaluation-20261115/decision-network/report.json)
- [workflows](/Users/tejas/Desktop/BioDemo/backend/results/agent-evaluation-20261115/reconciliation/report.json)
- [wording_review](/Users/tejas/Desktop/BioDemo/backend/results/agent-evaluation-20261115/answers-live/wording-review.json)
- [recurring_wording_review](/Users/tejas/Desktop/BioDemo/backend/results/agent-evaluation-20261115/recurring-wording-review.json)
