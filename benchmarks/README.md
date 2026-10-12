# Manufacturing OS benchmarks

Two separate benchmarks share `InvestigationInput`, `run_investigation`, the conventional parser, the leakage audit, and the runner. `cho` reads original experimental workbooks. `fresenius` renders the repository's frozen v1.1 synthetic simulation into source files and stages time-valid snapshots.

Downloaded CHO source files, publication-aligned references, normalized outputs, and generated Fresenius packages/maps are preserved in this workspace and ignored by Git. A clean checkout must regenerate them with the commands below. Keep evaluation-only references outside any agent-readable package.

| Capability | Existing repository | Added here | Still open |
|---|---|---|---|
| Fresenius source data | Frozen v1.1 canonical records and temporal store | CSV/XLSX/PDF source package, scanned lab reviews, discrete event charts, local-time lab export, hidden source map and replay tasks | Broader unrelated-document perturbations |
| Agent | Structured-record RLM, Blackboard and graphs | Shared raw-package contract and isolated baseline worker | Raw-source RLM adapter |
| CHO | No source dataset | Verified original archive, full inventory, structural and descriptive references, fixed-format full trajectory reconstruction | Autonomous relevance, process comparison and causal evaluation |
| Evaluation | Structured simulation metrics | Raw-package leakage checks, extraction metrics, one-pass model baselines and reports | Objective relevance labels where defensible, human baseline and broad model repeatability |

Install dependencies with `pip install -e '.[benchmarks]'`. On macOS the score runner uses `sandbox-exec` to deny the agent worker access to evaluation roots. If that OS isolation cannot be applied, the scored run fails. `--no-isolation` permits development runs and marks their results ineligible for publication.

Commands:

```sh
python -m benchmarks.common.benchmark_runner --benchmark cho --action download
python -m benchmarks.common.benchmark_runner --benchmark cho --action inventory
python -m benchmarks.common.benchmark_runner --benchmark cho --action validate
python -m benchmarks.common.benchmark_runner --benchmark cho --action references
python -m benchmarks.common.benchmark_runner --benchmark cho --action perturb
python -m benchmarks.common.benchmark_runner --benchmark cho --action data-check
python -m benchmarks.common.benchmark_runner --benchmark cho --action normalize
python -m benchmarks.common.benchmark_runner --benchmark cho --action compare
python -m benchmarks.common.benchmark_runner --benchmark fresenius --action generate
python -m benchmarks.common.benchmark_runner --benchmark fresenius --action validate
python -m benchmarks.common.benchmark_runner --benchmark fresenius --action data-check
python -m benchmarks.common.validate_splits
python -m benchmarks.common.benchmark_runner --benchmark cho --action audit
python -m benchmarks.common.benchmark_runner --benchmark fresenius --action audit
python -m benchmarks.common.benchmark_runner --benchmark cho --mode baseline
python -m benchmarks.common.benchmark_runner --benchmark cho --mode retrieval_llm
python -m benchmarks.common.benchmark_runner --benchmark fresenius --mode baseline
python -m benchmarks.common.benchmark_runner --benchmark fresenius --mode retrieval_llm
python -m benchmarks.common.reliability
python -m benchmarks.common.benchmark_runner --benchmark cho --action report
python -m benchmarks.common.benchmark_runner --benchmark fresenius --action report
```

For incremental work later, add `--task CHO-03` or `--task FRE-02` to a run command. A single-task run writes its own result file and leaves the five-task result untouched. The CHO one-pass path has a working implementation and a source-summary unit test, but its full model run has not completed; no CHO one-pass score is reported yet. The existing Fresenius agent scores were measured on the earlier v1 export package; the current v2.1 package has only data validation, not agent scores.

`--mode retrieval_llm` uses one bounded reasoning call per task: the OpenAI Responses API with `OPENAI_API_KEY`, or the authenticated Codex CLI when no key is present. For CHO, the parser first computes numeric sheet summaries from the original workbook rows and retrieves at most 96 source sheets across all experiments. For Fresenius, it retrieves at most 80 source records from the staged snapshot. `--mode full_rlm` fails visibly until a raw-source adapter to the existing structured RLM is implemented. No surrogate full-RLM score is produced.

Agent-visible files live in `cho/raw/workbooks` or a staged Fresenius snapshot. Evaluation references live in `cho/reference`, `fresenius/ground_truth`, and `data/v1.1`. The full Fresenius `raw_package` is an archive for inspection only; historical tasks always stage a fresh snapshot as of the task timestamp. Do not hand the full archive to an agent during replay.

The current baseline measures file parsing and source ID recovery. It is intentionally weak on relevance and investigation, and the report reflects that.
