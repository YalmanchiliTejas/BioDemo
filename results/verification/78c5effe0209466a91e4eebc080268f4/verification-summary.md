# Verification of the saved CHO investigation

This is a deterministic replay against a rebuilt clone. No model was invoked and the original evaluation run was not changed. The original hypotheses are preserved; this document does not establish causal truth.

## What is repaired

- All 38 original snapshot observation IDs resolve and match immutable original source values.
- All 8 hypotheses retain supporting and contradicting observations.
- Frozen transcription checks: 1300 correct / 1300 comparable fields; 0 missing.
- Five explicit VCD peak percentage comparisons were recomputed from source observations.
- Cited coverage: 5 experiments, 10 runs. These are not manufacturing batch IDs or an adjudicated affected scope.
- Severity: UNKNOWN; default policy is draft, and no qualifying categorical source signal established severity.

## Hypothesis evidence checks

| Hypothesis | Support IDs | Contradicting IDs | Source checks |
| --- | ---: | ---: | --- |
| H-1 | 3 | 2 | All match original values |
| H-2 | 3 | 2 | All match original values |
| H-3 | 3 | 1 | All match original values |
| H-4 | 2 | 2 | All match original values |
| H-5 | 3 | 2 | All match original values |
| H-6 | 2 | 2 | All match original values |
| H-7 | 3 | 1 | All match original values |
| H-8 | 2 | 2 | All match original values |

## Deterministic peak comparisons

Definition: `100 × (higher VCD peak − lower VCD peak) / lower VCD peak`. This compares recorded peaks; it does not establish equivalent experimental design or explain a cause.

| Source | Exact percent difference |
| --- | ---: |
| EXP011_fed-batch.xlsx | 224.36363636% |
| EXP001_batch.xlsx | 64.89988221% |
| EXP008_batch.xlsx | 7.29991205% |
| EXP010_fed-batch.xlsx | 0.62240664% |
| EXP012_fed-batch.xlsx | 0.28557830% |

## Remaining review requirements

The old narrative contains 43 numeric literals not linked to a cited source value or an explicitly verified calculation by the conservative coverage diagnostic. These are review flags, not a count of proven errors. Matching a source number would not certify a sentence's meaning either.

Reported SEMs are source-reported values. Their underlying replicates are absent, so independent reconstruction of those SEMs remains unavailable. Concentration-based yields require a stated definition and matched source times and are explicitly apparent without feed/volume/mass-balance validation. Biological interpretations, evidence-role assignments and causation require review.

The old 107 model calls have not been remeasured. The next live run receives deterministic statistics and clock diagnostics before model inference, uses the new tools and report contract, and retains the 48-call tool budget.

## Artifacts

- [Verified source links, metric receipts, hypotheses and scope](report.json)
- [Independent frozen objective checks](objective-checks.json)
- [Complete deterministic preparation](analysis-preparation.json)
- [Implementation and migration notes](/Users/tejas/Desktop/BioDemo/docs/deterministic_verification.md)
- [Original evaluation output](/Users/tejas/Desktop/BioDemo/results/evaluation/78c5effe0209466a91e4eebc080268f4/output.json)
