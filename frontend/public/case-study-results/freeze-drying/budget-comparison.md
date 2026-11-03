# Same-case sensitivity comparison

Post-hoc motivated, prospectively frozen joint budget/submission sensitivity; reused cases, no independent confirmation.

Each row compares the original four-call/120-second result with the eight-call/240-second result on the same six cases. The latter also restricts the last provider turn to submission. This bundles budget, wall time and completion policy. All three arms receive the same change. No original failure is replaced.

MAE is conditional on numerical predictions; coverage must be read alongside it. The common-prediction table compares identical cases when both sessions provided a numerical answer. One realization per arm and six reused cases cannot identify a stable causal effect.

| Task | Arm | Protocol | Completed | Predicted / eligible | MAE (h) | Feasible | Unsafe | Characterize |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| forecast | A | primary | 0/6 | 0/6 | — | 0 | 0 | 0 |
| forecast | A | sensitivity | 4/6 | 4/6 | 53.99 | 3 | 0 | 1 |
| forecast | B | primary | 6/6 | 6/6 | 0.16 | 6 | 0 | 0 |
| forecast | B | sensitivity | 6/6 | 6/6 | 0.16 | 6 | 0 | 0 |
| forecast | C | primary | 6/6 | 6/6 | 0.24 | 6 | 0 | 0 |
| forecast | C | sensitivity | 6/6 | 6/6 | 0.25 | 6 | 0 | 0 |
| pretransfer | A | primary | 3/6 | 3/6 | 51.09 | 1 | 0 | 2 |
| pretransfer | A | sensitivity | 4/6 | 4/6 | 9.05 | 3 | 1 | 0 |
| pretransfer | B | primary | 6/6 | 6/6 | 1.76 | 5 | 1 | 0 |
| pretransfer | B | sensitivity | 6/6 | 6/6 | 1.75 | 5 | 1 | 0 |
| pretransfer | C | primary | 6/6 | 6/6 | 1.81 | 4 | 1 | 1 |
| pretransfer | C | sensitivity | 6/6 | 6/6 | 1.81 | 5 | 1 | 0 |

| Task | Arm | Common predictions | Primary MAE (h) | Sensitivity MAE (h) |
| --- | --- | --- | --- | --- |
| forecast | A | 0 | — | — |
| forecast | B | 6 | 0.16 | 0.16 |
| forecast | C | 6 | 0.24 | 0.25 |
| pretransfer | A | 2 | 21.46 | 11.29 |
| pretransfer | B | 6 | 1.76 | 1.75 |
| pretransfer | C | 6 | 1.81 | 1.81 |

## Cost and execution evidence

Combined original, continuation and sensitivity admission accounting: $9.36440188, under the original $10 cap. Of this, $4.86440188 is a settled token-based estimate and $4.50000000 remains reserved for requests with unknown cost. This is not an invoice; it excludes local simulation and engineering. Interrupted proxy requests retain their entire reservation even without a finished event.

Actual provider-request journals record 6 final submission-only turns; their exposed tool list was verified. The policy does not guarantee successful submission.

The JSON companion preserves full warning confusion matrices, failures, coverage, ledger hashes and common-prediction denominators. The primary study remains separate.
