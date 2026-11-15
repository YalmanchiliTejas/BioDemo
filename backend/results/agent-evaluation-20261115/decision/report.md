# Skill benchmarks

Started 2026-11-15T20:26:03.352105+00:00.

| Skill | Arm | Cases | Correct | 95% interval | Wrong answers | Cannot do yet | Slowest |
|---|---|---:|---:|---|---:|---:|---:|
| Decide or abstain (decision model) | decision_model | 1200 | 0 (0%) | 0%–0% | 0 | 0 | n/a |

### Decide or abstain (decision model) · decision_model

Asked which of 20 intents a real request means, does the decision model pick the right one, say "unknown" for a request that fits none, and is its probability a usable signal?

How it fails: error 1200.

| Condition | Cases | Correct | What goes wrong |
|---|---:|---:|---|
| fits none of the intents | 600 | 0 (0%) | error 600 |
| fits one of the intents | 600 | 0 (0%) | error 600 |

Most common reasons:
- 1200 × error: decision model unavailable (unavailable)

### Can the decision model act without a person?

| Act when probability is at least | Acted on | Right | Precision | In-scope requests handled |
|---:|---:|---:|---:|---:|
| 0.50 | 0 | 0 | 0.0% | 0% |
| 0.60 | 0 | 0 | 0.0% | 0% |
| 0.70 | 0 | 0 | 0.0% | 0% |
| 0.80 | 0 | 0 | 0.0% | 0% |
| 0.90 | 0 | 0 | 0.0% | 0% |
| 0.95 | 0 | 0 | 0.0% | 0% |
| 0.99 | 0 | 0 | 0.0% | 0% |

| Probability band | Answers | Right | Observed rate |
|---|---:|---:|---:|
| 0.00-0.50 | 0 | 0 | n/a |
| 0.50-0.60 | 0 | 0 | n/a |
| 0.60-0.70 | 0 | 0 | n/a |
| 0.70-0.80 | 0 | 0 | n/a |
| 0.80-0.90 | 0 | 0 | n/a |
| 0.90-0.95 | 0 | 0 | n/a |
| 0.95-1.00 | 0 | 0 | n/a |

Limits: Public data from laboratories, one manufacturer and regulators; not your sites. The data was loaded directly as deliveries in review. Reading messy files is measured elsewhere. Specifications and readable names were added where the report says so; nothing else was. Host-arm cases use no model. They say nothing about the assistant.
