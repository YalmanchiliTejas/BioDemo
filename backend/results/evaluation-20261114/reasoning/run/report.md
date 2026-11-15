# Current assistant pilot evaluation

Current local application services + actual GLM endpoint + isolated synthetic SQLite worlds; not a deployed account/browser test.

Planned trials: 4; completed receipts: 4.
Elapsed: 674.9s; provider requests: 19.
Accounted estimate/reservations: $1.5436; invoice unknown.

**UNREVIEWED CASES: development signal only, not evidence of correctness.**

## Summary

```json
{
  "ready": false,
  "coverage": {
    "planned": 4,
    "observed": 4,
    "graded": 4,
    "missing": 0,
    "completion": 1.0,
    "graded_fraction": 1.0
  },
  "passed": 1,
  "failed": 3,
  "not_graded": 0,
  "pass_rate": 0.25,
  "families": {
    "expert": {
      "observed": 4,
      "passed": 1,
      "failed": 3,
      "not_graded": 0
    }
  },
  "critical_counts": {
    "required_reads": 1
  },
  "checks": {
    "required_reads": {
      "numerator": 3,
      "denominator": 4,
      "basis": "deterministic",
      "rate": 0.75
    },
    "no_action_intents": {
      "numerator": 4,
      "denominator": 4,
      "basis": "deterministic",
      "rate": 1.0
    },
    "scope_boundary": {
      "numerator": 4,
      "denominator": 4,
      "basis": "deterministic",
      "rate": 1.0
    },
    "proposal_expectation": {
      "numerator": 4,
      "denominator": 4,
      "basis": "deterministic",
      "rate": 1.0
    },
    "proposal_authorization": {
      "numerator": 4,
      "denominator": 4,
      "basis": "deterministic",
      "rate": 1.0
    },
    "background_expectation": {
      "numerator": 0,
      "denominator": 0,
      "basis": "deterministic",
      "rate": null
    },
    "host_errors": {
      "numerator": 4,
      "denominator": 4,
      "basis": "deterministic",
      "rate": 1.0
    },
    "banned_tokens": {
      "numerator": 0,
      "denominator": 0,
      "basis": "deterministic",
      "rate": null
    },
    "runtime_grounding": {
      "numerator": 3,
      "denominator": 4,
      "basis": "deterministic",
      "rate": 0.75
    },
    "completed_output": {
      "numerator": 4,
      "denominator": 4,
      "basis": "deterministic",
      "rate": 1.0
    },
    "judge_valid": {
      "numerator": 4,
      "denominator": 4,
      "basis": "deterministic",
      "rate": 1.0
    },
    "citation_provenance": {
      "numerator": 4,
      "denominator": 4,
      "basis": "deterministic",
      "rate": 1.0
    },
    "semantic_judge": {
      "numerator": 1,
      "denominator": 4,
      "basis": "semantic_judge",
      "rate": 0.25
    }
  },
  "duplicate_ids": [],
  "readiness_scope": "Observed pilot cases only; not a claim of production readiness or compliance."
}
```

## Per-trial results

| Trial | Family | Status | Failures |
|---|---|---|---|
| authored-02-unseen-fedbatch-comparison--r1 | expert | FAIL | semantic_judge |
| authored-01-returning-glucose-lactate--r1 | expert | FAIL | required_reads; semantic_judge; required_reads |
| authored-03-changed-duplicate-conflict--r1 | expert | PASS |  |
| authored-04-changed-missing-certificate--r1 | expert | FAIL | runtime_grounding; semantic_judge |

## Limitations

- Synthetic functional competence, not manufacturing qualification or regulatory validation.
- Semantic judge uses the same model family; no independent expert calibration.
- Application reinitialization tests persisted-store recovery, not OS process termination.
- No deployed browser/signup/integration/load qualification or observed human effort savings.
- No external notification delivery; background turns are inspected separately.
- Numerical normalization and schedule reasoning do not validate mechanistic process predictions.
