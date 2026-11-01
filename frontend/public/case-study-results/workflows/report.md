# Manufacturing workflow execution results

Partial evaluation. Physical simulations excluded. Results remain local; no deployment performed.

## Ingestion: 300 actual service executions

| Layout | Completed / attempted | Field precision | Recall | F1 | p90 seconds | p99 seconds |
|---|---:|---:|---:|---:|---:|---:|
| unseen | 100/100 | 100.00% | 100.00% | 100.00% | 0.870 | 1.179 |
| returning | 100/100 | 100.00% | 100.00% | 100.00% | 2.222 | 3.934 |
| changed | 100/100 | 99.67% | 100.00% | 99.83% | 2.264 | 2.623 |

Three packages, 100 executions each. Accuracy counts describe the package, not 100 independent incidents.
Changed layouts: 2,106 true-positive fields, seven extra fields, zero missed present fields.
Timing covers target IngestionService.run with local persistence, excluding setup and disjoint calibration.
Source/code integrity passed: True. Peak campaign process RSS: 358.5 MiB.
New/changed layouts route most fields to review. No measured human-time savings.

## Deterministic investigation baseline

| Case | Status | Critical evidence recall | Citation location validity |
|---|---|---:|---:|
| CHO-01 | completed | unscored | 100.00% |
| CHO-02 | completed | unscored | 100.00% |
| CHO-03 | completed | unscored | 100.00% |
| CHO-04 | completed | unscored | 100.00% |
| CHO-05 | completed | unscored | 100.00% |
| FRE-01 | incomplete | 25.00% | 99.76% |
| FRE-02 | incomplete | 50.00% | 99.68% |
| FRE-03 | incomplete | 25.00% | 99.76% |
| FRE-04 | incomplete | 33.33% | 99.72% |
| FRE-05 | incomplete | 25.00% | 99.76% |
| FRE-06 | incomplete | 100.00% | 95.56% |

These are fixed deterministic reports, not GLM agent performance. Independent qualification remains pending.
Citation location validity does not establish that a narrative claim is true or supported.

## Actual GLM agent attempts

- FRE-02: **failed**, category `credential_not_loaded`, receipt `agent-investigation/runs/8f484289dbe746df993064ddeb8831af/run.json`. Failures and retries retained.
- FRE-02: **failed**, category `benchmark_gate_token_field_incompatibility`, receipt `agent-investigation-auth-retry/runs/fe77159432cb4eafa493b6581ccf0564/run.json`. Failures and retries retained.
- FRE-02: **failed**, category `benchmark_request_cap`, receipt `agent-investigation-gate-compatible/runs/8f41a417e22d4a33a038b32cce98abb3/run.json`. 12/12 model requests forwarded. Failures and retries retained.
- FRE-02: **failed**, category `benchmark_reservation_concurrency`, receipt `agent-investigation-metered/runs/6733176bbd9e461399bcced06fe790dd/run.json`. 75/100 model requests forwarded. Failures and retries retained.
- FRE-02: **failed**, category `benchmark_request_cap`, receipt `agent-investigation-queued/runs/edbf3a384dc44c459003a9657a527ce3/run.json`. 100/100 model requests forwarded. Failures and retries retained.

Forwarded Modal requests: 187; retained conservative reservations: $41.40. Actual invoice not reconciled.
Saved session-usage estimate at uncached list rates: $7.5485; see per-attempt nulls where telemetry is unavailable.

## Coverage gaps and regression checks

Regression checks: 114 tests, 0 failures, 0 errors. These are not agent accuracy observations.
Deviation detection precision/recall and manufacturing scheduling are not benchmarked yet.
The proposed 60-task, four-workflow agent campaign is not complete.

## Limits

- 300 ingestion trials repeat only three public-data packages.
- Local service quantiles exclude setup/calibration, network/API and model inference; OS caches uncontrolled.
- Ingestion layouts, companies, certificates and injected defects are synthetic.
- Evidence precision/recall without defensible labels remains null.
- Scientific and human review remain pending; no labor savings or production validation.
- Modal reservations are conservative bounds, not an invoice.
