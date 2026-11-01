# Controlled benchmark before a manufacturer pilot

The job is to establish whether the current agent can turn authorized manufacturing
evidence into a correct, reviewable next step, and whether it reduces total human
effort compared with existing work. This is internal evidence for deciding to run a
read-only manufacturer pilot. It is not production validation.

The suite schedules the existing `case_runner.run_case`; it does not replace the
agent, source packages, objective scorers, or isolation mechanism. Frozen historical
results stay unchanged. There is no database migration.

## What is wired

- A frozen schedule over the eleven existing CHO/Fresenius objectives, plus optional
  filename variants: 22 case/condition packages by default. These are **eleven
  objectives on two inspected datasets**, not 22 independent manufacturing incidents.
- Two repeats by default, with randomized method order within each explicit pair:
  deterministic preparation/investigation, a single synthesis call, the full Prime
  manufacturing agent, and an observed manual engineer workflow. That is 132
  automated assignments and 44 manual assignments; `--limit` bounds a session.
- Identical raw evidence, objective, cutoff, quality policy, and execution budgets
  within a pair. Inputs hydrate from the existing checksum store when required.
- The full agent uses its existing SDK, ingestion, scientific/evidence tools and
  recursive workflow. Its frozen execution policy uses a 48-call soft allowance and
  72-call hard ceiling. Evaluation isolates SDK resources and requires a claim ledger;
  these differences from the demo runtime are recorded, not hidden.
- Both model arms default to the same pinned provider/model from the configured
  Prime settings. `--full-model` and `--baseline-model` allow explicit assignments.
  A `provider/model` baseline uses the installed provider registry for one synthesis
  invocation with no tools or memories. A bare OpenAI model name retains the existing
  Responses baseline. Different models confound an orchestration-only comparison.
- Code, SDK entry files, relevant runtime settings, source versions, references,
  policies, budgets and schedule are fingerprinted. Changed implementation/settings
  require a new suite. Provider-side model weights, dependency environments and
  backend sampling defaults are not fully frozen; these remain reproducibility limits.
- Independent blinded-review export/import and separate observed human-work logs.
  Missing observations stay null. Failed assignments remain visible; resuming does
  not retry them or select a successful replacement.
- Separate dataset/condition reports with manual/full-agent and automated-baseline
  comparisons, repeatability, objective checks, usage and all-attempt human effort.

## Start with a smoke comparison

Run from the repository root. macOS `sandbox-exec`, the installed Prime bundle,
configured inference authentication and the existing offload client are required
for isolated execution. Missing credentials/data are recorded failures, never scores.

```sh
.venv/bin/python -m benchmarks.common.pilot_benchmark freeze \
  --suite backend/results/pilot-benchmark/smoke-v1 \
  --manifest backend/benchmarks/manifests/fresenius/FRE-02-raw/case.json \
  --repeats 1 --no-filename-challenges --refresh-rendered \
  --full-model modal/zai-org/GLM-5.3

.venv/bin/python -m benchmarks.common.pilot_benchmark run \
  --suite backend/results/pilot-benchmark/smoke-v1 \
  --provider-env backend/.env.local --operator-id internal-benchmark

.venv/bin/python -m benchmarks.common.pilot_benchmark report \
  --suite backend/results/pilot-benchmark/smoke-v1
```

`--provider-env` reads inference configuration only; it does not inject Supabase or
database keys. Do not distribute this file. Actual provider/model selection must match
the intended demo deployment before extrapolating results to that deployment.

Use a fresh directory to freeze the full schedule:

```sh
.venv/bin/python -m benchmarks.common.pilot_benchmark freeze \
  --suite backend/results/pilot-benchmark/controlled-v1 \
  --full-model modal/zai-org/GLM-5.3 --refresh-rendered

.venv/bin/python -m benchmarks.common.pilot_benchmark run \
  --suite backend/results/pilot-benchmark/controlled-v1 \
  --provider-env backend/.env.local --operator-id internal-benchmark --limit 3
```

Repeat `run` to continue pending assignments. A `STOP` file in the suite prevents new
assignments after the current bounded attempt. A crash leaves its assignment marked
`running`; a runner exception leaves `runner_error`. Both block readiness. Preserve
the original receipt and use a separately frozen experiment for a retry; do not edit
state to erase failures. The suite lock prevents concurrent writers.

`--refresh-rendered` creates a separate Fresenius snapshot using the current rendering
libraries. It refuses any change to the objective, cutoff, required deliverables or
evaluator references. This is useful when older XLSX container bytes cannot be rebuilt
under the current environment. Both the earlier snapshot identity and the new identity
are recorded. Historical scores never migrate onto newly rendered packages.

The default quality rubric is intentionally a draft. Technical exploration can run
with it, but no case qualifies until an independent domain-approved policy is frozen
**before** the evaluated run. Supply that JSON with `freeze --quality-policy PATH`.
It must contain reviewer identities, the existing dimensions and integrity gates,
a finite minimum quality score and a noninferiority margin. This command validates
the recorded approval; it cannot establish that a real independent review occurred.

## Observe an engineer and review outputs

Distribute only authorized inputs, never the private suite directory. The evidence
export audits the packages and contains original source files, objective, cutoff,
deliverables and file hashes, without hidden reference answers:

```sh
.venv/bin/python -m benchmarks.common.pilot_benchmark export-inputs \
  --suite backend/results/pilot-benchmark/smoke-v1 \
  --destination /private/tmp/manufacturing-evidence-v1
```

An observer records the engineer's workflow using their normal tools and creates
`manual-output.json` in the existing output contract (`files`, `records` or
`observations`, `citations`, and `analysis` with the required deliverables). The
session receipt records `operator_id`, `evidence_ref`, ISO `started_at`/`ended_at`,
and explicit `authorized_evidence_only: true` and `no_future_leakage: true`
attestations. These are observed-human attestations, not automated isolation claims.
Choose the manual assignment ID from the private `protocol.json` schedule:

```sh
.venv/bin/python -m benchmarks.common.pilot_benchmark record-manual \
  --suite backend/results/pilot-benchmark/smoke-v1 \
  --assignment fresenius-FRE-02-raw-r1-manual \
  --output-json /private/tmp/manual-output.json --session /private/tmp/manual-session.json
```

Randomized method order supports scheduling; use different engineers or equivalent
tasks to mitigate learning from solving the same case twice. Record participant
background, permitted tools, hints and any deviations in the observer evidence.

Export model/runtime-free review packets and forms into a fresh directory:

```sh
.venv/bin/python -m benchmarks.common.pilot_benchmark export-reviews \
  --suite backend/results/pilot-benchmark/smoke-v1 \
  --destination /private/tmp/manufacturing-reviews-v1
```

The command returns a **private** identity-key path under the suite. Reviewers receive
the exported review directory plus the evidence export. Each packet's
`source_package_id` identifies its evidence directory. They do not receive the key,
run IDs, method assignments, model usage or reference labels. Report language can
still reveal a method; reviewers must disclose that and leave `blind_to_method`
false if compromised. Complete the shared rubric and return each review form:

```sh
.venv/bin/python -m benchmarks.common.pilot_benchmark import-review \
  --suite backend/results/pilot-benchmark/smoke-v1 \
  --review /private/tmp/manufacturing-reviews-v1/PACKET.review.json \
  --key backend/results/pilot-benchmark/smoke-v1/review-keys/KEY.json
```

`PACKET` and `KEY` are placeholders for generated filenames. The private mapping
binds the returned review to the exact output and frozen policy. Reviews persist
and are rechecked when reports refresh. Review disagreements require independent
adjudication under the existing scorer.

Use the existing seven-stage active-work timer for manual **and assisted** work:

```sh
.venv/bin/python -m benchmarks.common.human_work time \
  --run-id RUN_ID --case-id FRE-02 --participant engineer-1 \
  --stage verification --trace /private/tmp/observed-human-work.jsonl
```

The report writes `human-work-template.json` containing every recorded run ID.
Complete it from observations: setup, data preparation, investigation, verification,
corrections, coordination and ongoing configuration, including failed attempts.
Use `human_work import-trace` to convert timer observations, then combine rows in
the suite ledger. A measured zero requires explicit observation; do not fill unknown
values with zero. The existing ledger supports measured shared setup allocation.

```sh
.venv/bin/python -m benchmarks.common.pilot_benchmark report \
  --suite backend/results/pilot-benchmark/smoke-v1 \
  --human-logs /private/tmp/completed-human-work.json
```

The report remains `not_ready` if assignments, qualification, timing or matched
noninferior manual comparisons are missing. `ready_for_pilot_review` is evidence for
a human decision to start a bounded read-only pilot, not authorization to operate
manufacturing equipment or release product.

## Product measures and trade-offs

Easy to Start: measure setup/data-preparation time and manual corrections. Easy to
Trust: score original-source citations, numerical checks, counterevidence, uncertainty
and independent review. Easy to Act: review proposed next steps, ownership and approval
boundaries. Easy to Adopt: measure integration/setup, training and recurring configuration
without replacing existing systems of record. Human time spans all four pillars;
inference latency alone is never labor saved.

A simple alternative is to run existing cases individually and review them manually.
It has less scheduling overhead but permits accidental unmatched comparisons and
untracked repeats. The suite adds frozen pairing and review bookkeeping while
reusing the implementation. A prospective factory integration is the more ambitious
alternative; postpone its data/integration burden until these controlled tests expose
the current failure modes. No external messages or manufacturing-system writes occur.

Remaining coverage: the default suite exercises existing objectives and filename
robustness. It does **not** supply independent real incident labels or new cases for
contradictions, missing evidence, prompt injection, stale procedures, interrupted tools,
or corrected-evidence updates. Existing permission/temporal tests remain separate
automated checks; persistent update trials retain their existing `--prior-run` interface.
Add separately authored, reviewed and frozen case manifests with repeated `--manifest`
arguments before claiming those competencies. Do not call filename changes unseen
processes or report synthetic causal assignments as verified factory root causes.

```sh
.venv/bin/python -m pytest backend/tests/test_pilot_benchmark.py \
  backend/tests/test_case_evaluation_v2.py backend/tests/test_new_benchmarks.py -q
```
