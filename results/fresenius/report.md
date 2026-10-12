# FRESENIUS benchmark report

## Dataset and provenance

Reconstructed synthetic manufacturing records derived from frozen `data/v1.1` canonical data. They are not Fresenius internal files.
Canonical agent-data SHA-256: `0ea0ab8575a459b482eeb48f2a790ab3b5ad97b47755865b8cb06cb8fb98d62d`. Current generated package `fresenius-source-package-v2.1`: 1029 records across 14 files.
Checksums and roles for every frozen input are recorded in `benchmarks/fresenius/source_manifest.json` and checked by the validation command.
Hidden source map: 25517 pointers; validation PASS.
Public FDA sources anchor the case chronology; synthetic records and hidden labels are separate.

The results below were measured on the earlier 11-file v1 package. The current 14-file v2.1 package adds image-only lab reports, discrete process-event charts, and an aliased lab export with local timestamps and valid ratio conversion. No agent result is claimed for v2.1.

Data-only validation of all 5 historical v2.1 snapshots: PASS; every source pointer resolves to a record visible at its cutoff. Byte-for-byte rebuild: True.

## Tasks, methods and actual results

Execution mode: `conventional`. OS-level agent filesystem isolation: `True`. Each task passed its package leakage audit before scoring.

| Task | Objective | Measured result | Runtime |
|---|---|---|---:|
| FRE-01 | Examine available manufacturing records and identify significant abnormalities requiring investigation. | 1023/1023 record IDs; critical-lab recall 1.0 | 0.399 s |
| FRE-02 | Investigate newly available laboratory result LAB-0225; assess scope, plausible explanations and human-reviewed next steps. | 758/758 record IDs; critical-lab recall 1.0 | 0.341 s |
| FRE-03 | Reassess available evidence across batches after new laboratory result LAB-0300. | 1023/1023 record IDs; critical-lab recall 1.0 | 0.392 s |
| FRE-04 | For newly available laboratory result LAB-0255, identify actions possible now, missing physical evidence and decisions for human review. | 862/862 record IDs; critical-lab recall 1.0 | 0.419 s |
| FRE-05 | Investigate newly available laboratory result LAB-0010; assess scope and evidence for any related-batch conclusions. | 37/37 record IDs; critical-lab recall N/A | 0.367 s |

## Failure examples and manual intervention

The cross-batch extraction surfaced 1023 records while only 3 incident-labeled action/OOS lab records were visible. This illustrates the baseline's lack of prioritization.
No manual corrections were made during execution. Source generation is programmatic preparation and is not counted as zero engineering labor.
Automated snapshot generation plus provenance validation took [0.774, 0.42, 0.543, 0.441, 0.038] seconds across the five tasks, separate from agent runtimes.
The baseline produced no competing hypotheses, scope decisions or recommended actions.

## Retrieval plus one-pass reasoning baseline

This baseline used the same staged source snapshots and one model call per task. The model received at most 80 retrieved source rows. The records were extracted by the conventional parser first.

| Task | Critical lab retrieval recall | Citation validity | Citations | Model input/output tokens | Runtime |
|---|---:|---:|---:|---:|---:|
| FRE-01 | 1.0 | 1.0 | 10 | 29702/726 | 12.968 s |
| FRE-02 | 1.0 | 1.0 | 75 | 28590/839 | 10.717 s |
| FRE-03 | 1.0 | 1.0 | 7 | 30822/601 | 16.023 s |
| FRE-04 | 1.0 | 1.0 | 1 | 33393/456 | 13.06 s |
| FRE-05 | N/A | 1.0 | 15 | 23542/691 | 11.461 s |

First-signal assessment excerpt: LAB-0225 is an upstream process sample for BATCH-075, reported at 1.23 action-limit ratios against an action limit of 1.0 and alert limit of 0.7. This is an action-level signal warranting prompt human-reviewed investigation. The supplied payload does not establish cause, batch disposition, or recurrence. The historical LAB-0010 result is also action-level, but it is for a different batch (SYN-0004); it does not establish recurrence for BATCH-075. The supplied environmental records are historical
The model's cited IDs are checked against the time-visible canonical set. Citation validity does not prove its interpretations are correct.

## First-signal repeatability

Trigger citation by run: [True, True, True]. Citation counts were [2, 2, 5]; pairwise citation Jaccard values were [1.0, 0.4, 0.4].
The spread in citation counts and overlaps measures evidence-selection stability. Three runs are too few for a reliable interval estimate.

## Cost and reproducibility

The conventional parser made zero model calls and incurred zero inference token cost. Single-pass model token counts are provider-reported; monetary cost is unknown. Runtime values are machine execution time, not human labor saved.
Source SHA-256: `0ea0ab8575a459b482eeb48f2a790ab3b5ad97b47755865b8cb06cb8fb98d62d`. Task-definition SHA-256: `19316e2b990253c6da29eb90252038dbd38f30a437c9c7e72cf47c022d3f106c`.
Python: `3.11.14`. Parser code SHA-256: `91669adb1146bdd3956314d7ced23631f3be5cf8cb2ef27dddda4a63a61a7d7e`.
Run the CLI commands in `benchmarks/README.md`; source and package manifests record checksums and versions.

## Limitations

The deterministic parser results do not establish autonomous investigation performance. Repeated-run confidence intervals are not meaningful for that baseline. The model repeat check is small and limited to FRE-02.
No full Manufacturing RLM score is reported because the existing RLM currently consumes structured factory records rather than these raw packages.
