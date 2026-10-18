# Reproduce the benchmark

Run from the repository root. Python dependencies are defined in `pyproject.toml`;
use the existing `.venv`. macOS `sandbox-exec` must be permitted to start so the
agent cannot read evaluator mappings, labels, prior results or other tenant data.
Do not disable isolation for a publication result.

## Existing artifacts

```sh
.venv/bin/python -m benchmarks.common.benchmark_runner --benchmark all --action report
PYTHONPATH=. .venv/bin/python scripts/build_publication.py
PYTHONPATH=. .venv/bin/python scripts/export_publication_reviews.py
PYTHONPATH=. .venv/bin/python scripts/export_publication_figures.py
```

The second command writes `BENCHMARK_RESULTS.json`, `BENCHMARK_REPORT.md`,
`FAILURE_ANALYSIS.md`, `PUBLIC_DEMO_SUMMARY.md` and
`benchmark/application/static/publication-benchmark.html`. It reads every v2
`results/evaluation/*/run.json`, including infrastructure failures. It does not
modify old runs, scores, references, labels or reviews. `REPRODUCE.md` is the
maintained procedure, not a generated result.

## Matched automated trials

```sh
PYTHONPATH=. .venv/bin/python scripts/run_publication_trials.py \
  --cases CHO-04 FRE-02 --methods conventional retrieval_llm --load-local-env
```

`--load-local-env` reads selected credential/model keys as literal strings from
`.env.local`; it does not execute shell content or print credentials. Single-pass
AI uses the configured OpenAI key and `gpt-6-luna`, the existing benchmark model.
The raw model response, provider-reported model ID/usage, call timestamps and
source-backed evidence packet are persisted. Cost is unknown when price
telemetry is unavailable. Conventional inference cost is zero because it makes
no model calls; total compute cost is still unmeasured.

All methods receive only the frozen authorized package and the same objective.
The new baselines use the OS's ingestion, deterministic preparation, original
source/value verifier and coverage checks. Conventional uses fixed descriptive
assembly. Single-pass uses one synthesis call over a deterministic source packet;
there is no iterative retrieval. Full OS has adaptive evidence tools and recursive
investigation. These capability differences are the comparison, not proof of
equal scientific quality. The single-pass packet is an authorized-data subset;
its size and selection are saved and must be assessed for objective coverage.

## Five-trial reliability target

Once a funded, working provider is configured:

```sh
PYTHONPATH=. .venv/bin/python scripts/run_publication_trials.py \
  --cases CHO-04 --methods full_rlm --repeats 5 --load-local-env
PYTHONPATH=. .venv/bin/python scripts/run_publication_trials.py \
  --cases FRE-01 FRE-02 FRE-03 FRE-04 FRE-05 FRE-06 \
  --methods full_rlm --repeats 5 --load-local-env
```

Run CHO first and inspect its five results before running the Fresenius series.
An authentication/payment error stops the remaining repetitions of that method
and case; skipped trials are not fabricated attempts. The script rejects changes
to the pinned implementation files or case manifest during a series. Results
record the Git commit plus working-tree code hash, prompts/skill hashes, dataset
and policy hashes, environment and budgets. Historical runs lacking those pins
cannot be pooled as a fixed-version reliability test. Provider sampling and model
backend revisions are not fully controlled; their unknown status stays explicit.

The acceptance target is five structurally complete, source-verified CHO-04
investigations, followed by representative synthetic Fresenius cases. Five
successes would be a test result, not statistical proof of production reliability.
Require full coverage, candidate dispositions, source and calculation checks,
claim-local verification and a complete final submission. Pending independent
review must remain separate from technical completion.

## Checks

```sh
.venv/bin/python -m pytest -q \
  tests/test_publication_integrity.py tests/test_investigation_review.py \
  tests/test_case_evaluation_v2.py tests/test_prime_runtime.py \
  tests/test_deterministic_analysis.py tests/test_no_future_leakage.py
node --check src/prime_runtime/sdk_runner.mjs
```

For a historical source/arithmetic audit without a model call:

```sh
PYTHONPATH=. .venv/bin/python scripts/audit_investigation_run.py \
  --run results/evaluation/ec32259a437d4ccea9dc47bf4ef654c0 \
  --output results/verification/publication-source-audit
```

## Independent work still required

Freeze and independently approve the scientific rubric and thresholds before
qualification. Collect blinded domain reviews bound to exact output/policy
hashes; independently adjudicate disagreements and integrity gates. Annotate
claim support, relevant/critical evidence and material finding stability. Measure
all human effort stages if making productivity claims. Test a genuinely untouched
held-out dataset; inspected cases and renamed/reformatted inputs do not establish
generalization. Do not tune hidden labels or use them as agent inputs.

The review exporter writes claim/calculation/coverage packets and blank review
templates to `results/publication/review-packets/`. Keep
`EVALUATOR_ONLY_INDEX.json` and method/run labels from blinded reviewers. It binds
each packet to the exact original output and frozen policy hashes. No reviewer
scores, approvals or endorsements are generated. Report content may reveal its
method; reviewers must disclose any inferred unblinding.
