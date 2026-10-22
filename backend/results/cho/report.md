# CHO benchmark report

## Dataset and provenance

Authentic CHO-K1 cultivation measurements from DOI 10.5281/zenodo.20829178; archive MD5 `71b2a35b7df2ed11644ec9f177453772` (published checksum matched).
License: CC-BY-4.0 (Zenodo record API metadata.license.id); attribution required for redistribution.
Inspected 12 original workbooks, 192 worksheets and 48 publication-aligned CSV files.
Raw sheets contain 3,251,506 data rows, 6,539 empty cells and 231 backward timestamp steps.
Evaluator-only descriptive summaries cover 24 cultivations; they contain no causal labels.
Evaluator-only R01/R02 references cover 12 experiments and 672 descriptive measurement comparisons. They do not claim statistical significance.
Agent input was the original workbooks. Aligned CSVs and the structural map remained evaluation-only.

## Tasks, methods and actual results

Execution mode: `conventional`. OS-level agent filesystem isolation: `True`. Each task passed its package leakage audit before scoring.

| Task | Objective | Measured result | Runtime |
|---|---|---|---:|
| CHO-01 | Identify experiments, reactors, measurements, units and frequencies from raw workbooks without manual tags. | 12 workbooks; 192 sheets; 1300/1300 time-zero values matched | 105.808 s |
| CHO-02 | Link measurements into an analysis-ready representation of each cultivation. | 10,986,364/10,996,791 trajectory values within tolerance; 497 unavailable | 151.255 s |
| CHO-03 | Identify measurements worth investigating for variation in cultivation performance, citing source data and uncertainty. | Investigation not scored | — s |
| CHO-04 | Compare cultivations and describe operating differences and abnormal trends with evidence. | Investigation not scored | — s |
| CHO-05 | Repeat interpretation under controlled source-format perturbations. | 17 perturbed sheets parsed; semantic consistency unscored | 12.76 s |

## Failure examples and manual intervention

Time-zero mismatches: [].
Unavailable time-zero comparisons: 44.
No manual workbook mappings were supplied to the extraction worker. The evaluator generated hidden structural matches by exact header equality.
The baseline produced no process hypotheses or relevance ranking.
The perturbation produced 17 parsed sheets versus 16 original sheets: the parser included the synthetic irrelevant worksheet, and it did not normalize the renamed or converted temperature channel.
A separate data-only perturbation check compared 2,084,974 cells and passed; this verifies source-format changes, not an agent's interpretation.

## Full trajectory reconstruction

A separate fixed-format normalization reads only original workbooks and reconstructs 24 cultivations on a one-minute inline grid. Against the publisher's aligned CSVs, 10,986,364/10,996,791 comparable values (99.905%) met normalized absolute error <= 0.01; 497 reference values had no reconstructed counterpart.
The normalized error divides absolute error by the larger of the reference channel range, the reference value magnitude and 1e-6. The publisher alignment is a reconstruction reference, not independently verified biological truth.
Largest mismatches by count (file, channel, failures, comparisons): [('EXP008_batch_R02_inline.csv', 'Reflection (arb. Unit)', 1681, 12763), ('EXP001_batch_R02_inline.csv', 'Cumulative NaOH weight (g)', 1296, 11839), ('EXP009_batch_R02_inline.csv', 'Reflection (arb. Unit)', 1237, 13500), ('EXP002_batch_R02_inline.csv', 'Cumulative NaOH weight (g)', 1053, 12339), ('EXP010_fed-batch_R02_inline.csv', 'Reflection (arb. Unit)', 522, 19099)].
The normalization sorts backward timestamps and does not interpolate across source gaps longer than six minutes. It uses sheet naming conventions and therefore does not demonstrate autonomous schema inference.

## Cost and reproducibility

The conventional parser made zero model calls and incurred zero inference token cost. Single-pass model token counts are provider-reported; monetary cost is unknown. Runtime values are machine execution time, not human labor saved.
Source SHA-256: `46a6b92b77883d56df3be015895d93c85b2b2547121af0b8bc0a92f3fbefd17b`. Task-definition SHA-256: `ae5a43b2ac55ef5c1b780ace312236436ef4f8a4b683f3d6274252cb99c82154`.
Python: `3.11.14`. Parser code SHA-256: `91669adb1146bdd3956314d7ced23631f3be5cf8cb2ef27dddda4a63a61a7d7e`.
Run the CLI commands in `benchmarks/README.md`; source and package manifests record checksums and versions.

## Limitations

The deterministic parser results do not establish autonomous investigation performance. Repeated-run confidence intervals are not meaningful for that baseline. The model repeat check is small and limited to FRE-02.
No full Manufacturing RLM score is reported because the existing RLM currently consumes structured factory records rather than these raw packages.
