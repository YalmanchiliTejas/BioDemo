# Deterministic verification around the existing RLM

The Prime SDK, persistent Python kernel, native child sessions, Blackboard and
hypothesis/decision graphs remain the investigation architecture. BioDemo now
prepares numerical evidence before inference and verifies structured claims
before saving a report.

## Changes by priority

| Priority | Implemented change |
| --- | --- |
| P0 | Nested hypothesis/fact/metric/task citations are collected automatically. Original-source checks run in batches. Routine instrument Status rows no longer expand into millions of formal citations. |
| P0 | `calculate_metrics` recomputes means, sample SD/SEM, percentages, percent changes, differences, ratios and apparent yields. Explicit rounding is supported. Invalid denominators, units, duplicate inputs, unsupported SEM inputs and incorrect claimed values fail. |
| P0 | Native Excel numeric precision is retained. Mixed text/numeric columns preserve numeric XML values without changing text identifiers. Parquet partitions carry integrity checksums. |
| P0 | Source clock columns produce `time_value`, `time_basis` and `time_evidence_id`; row numbers are never used as time. `align_series` supports exact, bounded nearest and explicit linear interpolation, with lineage. |
| P1 | Each hypothesis needs evidence for both roles, or a declared `none_found`/`not_searched` status and absence reason. No search outcome is fabricated. |
| P1 | Durable reports separate `observed_facts`, `calculated_metrics`, `interpretations` and `causal_hypotheses`. Source checks and arithmetic receipts are saved. |
| P1 | Scope distinguishes runs, experiment groups and manufacturing batches. Cited coverage and proposed affected entities are separate. Severity is derived from versioned routing rules; the agent's proposal is retained separately. |
| P2 | The harness computes all-series descriptive statistics, extrema, source-clock quality, anomaly patterns and paired peak comparisons before starting the SDK. Context includes a compact summary; a complete artifact is available without another model call. |

## Files and execution flow

- `src/manufacturing_data/time_axis.py`: source-clock discovery.
- `src/manufacturing_data/analysis.py`: deterministic preparation, calculations and alignment.
- `src/manufacturing_data/verification.py`: batched immutable-original verification.
- `src/workflows/report_verification.py`: submission boundary and report categories.
- `src/workflows/triage.py`: explicit routing/severity rules and draft defaults.
- `src/prime_runtime/bridge.py`: scoped tools, supplied evidence and verified submission.

The added skill functions are `summarize_series`, `calculate_metrics` and
`align_series`. The existing ten data operations retain their names. The
manufacturing skill documents their specifications and the final report shape.
`analysis-preparation.json` is computed before model inference and copied into
evaluation `runtime-artifacts/`. It includes source hashes and partition
manifest fingerprints. Arithmetic is recomputed rather than trusting an
agent-supplied receipt or `verification` label.

## Source clocks and scientific assumptions

An elapsed clock needs a named source time column with an explicit convertible
unit (hours, minutes, seconds or days). A calendar clock needs an explicit time
zone. Missing/ambiguous clocks remain unresolved, including clocks hidden by a
field publication cutoff. Numeric "Time" without units is not guessed to mean
hours or a year. Process elapsed hours remain distinct from `occurred_at`
calendar timestamps.

Alignment requires one explicit entity and compatible time bases. Duplicate
timestamps fail rather than silently picking a record. Nearest ties stay
ambiguous. Linear interpolation retains both bracketing values, weights and
clock citations; it never extrapolates or overwrites measurements. Backwards
source clocks require investigation; explicit `allow_time_reordering=True`
permits chronological sorting but does not claim a reset was resolved.

Reported Mean/SEM columns establish source-reported summaries, not access to
raw replicates. Actual SEM reconstruction requires raw replicate observations
and a declared independence basis. Time-series sample deviation is descriptive;
it is not converted to biological replicate SEM. A concentration-change yield
is explicitly apparent: feed, dilution, volume and mass balance remain
unverified. Ratio and percentage comparisons at different clocks/entities need
an explicit comparison basis.

The layer verifies source identity/values, stored partition integrity and
specified arithmetic. It does not prove biological plausibility, sample
independence, semantic correctness of free prose, or causation. A conservative
literal-coverage diagnostic flags numbers not linked to source values or
verified metrics; matches do not certify a sentence's meaning. Unlinked
numbers keep the report in `requires_numerical_review`. Hypothesis confidence
is explicitly an uncalibrated agent judgment.

## Operational severity policy

Default rules are versioned **draft** rules. They never infer a GMP excursion
from raw numerical values without a supplied specification. Without qualifying
categorical source signals, severity is `UNKNOWN`, not an invented LOW/MEDIUM.
The requested severity remains `agent_proposed_severity`.

Pass an organization-reviewed policy through the workflow's `triage_policy`
argument or the benchmark CLI:

```bash
.venv/bin/python -m benchmarks.common.benchmark_runner \
  --benchmark cho --mode full_rlm --case CHO-04 --condition raw \
  --operational-triage-policy /path/to/site-routing-policy.json
```

The policy requires a version, draft/approved status, explicit ordered rules,
severity per level, and required review roles. An approved status also requires
named reviewers. `src/workflows/triage.py::DEFAULT_POLICY` supplies the schema.
The exact operational policy and its hash are recorded with the run; this is
separate from hidden evaluation labels. Changes to the policy, structured
metrics or evidence scope invalidate previous review approval.

## Migration and saved-run verification

The ingestion signature is `0.6.0-verified-columnar`. Re-ingest existing stores
before using the new analysis layer; fresh benchmark runs do this automatically.
The `b1:<source>:<sheet-index>:<row>:<column>` ID scheme is unchanged. The
previous reader's string coercion could round Excel numbers (including tiny
values to zero); native numeric reading repairs that on rebuild. Missing
partition checksums are treated as a migration requirement.

The saved CHO run `78c5effe0209466a91e4eebc080268f4` was replayed against a rebuilt
clone, without calling a model or changing the original evaluation output.
The separate artifacts are under `results/verification/<run-id>/`. All eight
hypotheses retain their original supporting and contradicting observations,
and all 38 original citations resolve. The replay additionally computes five
explicit VCD peak-percentage comparisons. The frozen transcription check now
covers all 1,300 comparable fields with no missing fields; this is a bounded
transcription check, not an all-cell or causal accuracy claim.

The old narrative's remaining numerical claims are not retroactively approved.
Existing reported SEMs cannot be independently reconstructed without raw
replicates. Model-call savings need a fresh live run; preprocessing adds machine
work and does not itself establish a reduction from the prior 107 calls.
The tool-call budget remains 48, and report submission/verification remains
available after that budget is exhausted.
