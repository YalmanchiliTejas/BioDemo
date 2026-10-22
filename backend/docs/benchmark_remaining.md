# Benchmark status and remaining work

Data preparation is complete for the current source versions. No agent run was performed while finishing the v2.1 Fresenius package or the new CHO references and checks. The rows below separate validated data from scores that must wait for later agent execution.

| Capability | CHO | Fresenius |
|---|---|---|
| Source and provenance | Original Zenodo archive verified; 12 workbooks and 48 reference CSVs inspected | Frozen v1.1 simulation verified; all original input checksums recorded |
| Agent-facing package | Original workbooks | Synthetic CSV, XLSX, text PDF, scanned lab PDF, discrete event charts and local-time lab export with time-limited snapshots |
| Hidden evaluation layer | Aligned data, structural mapping, objective comparisons and perturbation manifest | Canonical records, labels and 25,517 source pointers for the full v2.1 package |
| Conventional baseline | Five tasks executed; 24 cultivations reconstructed and scored against aligned CSVs | Five replay tasks executed on v1; all visible record IDs recovered. V2.1 has data validation only. |
| Retrieval and one-pass model | Source-only sheet-summary path implemented and unit-tested; full run interrupted, so no score | Five tasks executed; three first-signal repeats measured |
| Full raw-source RLM | Adapter contract exists; integration and score pending | Adapter contract exists; integration and score pending |
| Investigation scoring | Citation checks are ready; relevance, process comparison and semantic robustness remain unscored | Extraction, critical-lab retrieval and citation timing scored; action and hypothesis quality remain unscored |

When agent evaluation resumes, the next CHO step is an isolated `--benchmark cho --mode retrieval_llm --task CHO-03` run, followed by inspection of cited source sheets. Single-task execution is available to keep experiments bounded. Its result must not be described as causal accuracy: the publication supplies measurements and alignment, not verified causal labels.

The next common implementation step is a benchmark adapter for the Prime SDK runtime. It must preserve each task's source package and `as_of` boundary, cite source locations, and use the same evaluation interface. Until then, `full_rlm` refuses to publish a score.

Broader unrelated Fresenius documents can be added as deterministic source-format changes linked to the existing canonical records. CHO's perturbed workbook has passed a cell-by-cell equivalence check; a future agent-output semantic-equivalence scorer is still needed. Neither extension should alter underlying observations or introduce unsupported outcomes.
