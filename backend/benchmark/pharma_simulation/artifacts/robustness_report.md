# Multi-seed robustness report

Seeds evaluated: **20** (`100` through `119`)

All dataset causal/statistical checks passed: **True**  
All public-fact consistency checks passed: **True**

| Condition | Metric | Mean | Min | Max |
|---|---|---:|---:|---:|
| current_event_only | incident_detection_recall | 60.0% | 60.0% | 60.0% |
| current_event_only | precision | 100.0% | 100.0% | 100.0% |
| current_event_only | false_positive_rate | 0.0% | 0.0% | 0.0% |
| current_event_only | median_time_to_detection_minutes | 0.0 min | 0.0 min | 0.0 min |
| current_event_only | triage_accuracy | 60.0% | 60.0% | 60.0% |
| current_event_only | evidence_grounding_accuracy | 100.0% | 100.0% | 100.0% |
| current_event_only | future_leakage_rate | 0.0% | 0.0% | 0.0% |
| current_event_only | investigation_scope_recall | 76.7% | 76.7% | 76.7% |
| full_context | incident_detection_recall | 100.0% | 100.0% | 100.0% |
| full_context | precision | 100.0% | 100.0% | 100.0% |
| full_context | false_positive_rate | 0.0% | 0.0% | 0.0% |
| full_context | median_time_to_detection_minutes | 0.0 min | 0.0 min | 0.0 min |
| full_context | triage_accuracy | 100.0% | 100.0% | 100.0% |
| full_context | evidence_grounding_accuracy | 100.0% | 100.0% | 100.0% |
| full_context | future_leakage_rate | 0.0% | 0.0% | 0.0% |
| full_context | investigation_scope_recall | 100.0% | 100.0% | 100.0% |

> Each seed changes normal variation, durations, missingness, benign-scenario placement, line assignment, and irrelevant contextual records while preserving fixed public facts and scenario semantics.

These are synthetic robustness results, not estimates of real-world manufacturing prevalence or performance.
