# Live Sievance app evaluation

Live product functional evaluation · exploratory

Recorded 4 actual attempts; 1 completed workflow turns.

| Attempt | Status | Wall seconds |
|---|---|---:|
| engturn_01M6A178ABCYYPB6B3DS8EQ2KD | blocked | 35.069 |
| engturn_01M6A1HMNGXM4BRN57XEXBFM7Z | agent_unavailable | 67.862 |
| engturn_01M6A20Y1NSWHA15J5S5KPDD9V | completed | 23.046 |
| engturn_01M6A2378KP257AYBZS1H98MJD | agent_unavailable | 60.253 |

## Numerical results

| Model | Completion h | Critical margin C | Capacity margin kg/h |
|---|---:|---:|---:|
| lyo.kv_rp | 37.666722442648705 | 3.9691253083395672 | -0.670048159210694 |

A returned trajectory with a vapor-capacity violation is an invalid-control diagnostic extrapolation, not a feasible operating plan.

## Limits

- This is an exploratory live-app functional evaluation, not the proposed extensive benchmark.
- Prompts were refined after failures; attempts are correlated and no untouched generalization claim is supported.
- Reconstructed/synthetic demo observations are not independent plant measurements.
- Numerical completion does not establish a feasible process or scientific model qualification.
- No independent scientific adjudication, matched human-time baseline or manufacturing action was performed.
- Prior paired physics studies below are separate experiments and are not replications of these app runs.

Actual provider billing was not returned by the app. Zero-valued gateway estimates do not mean free inference.

## Additional delivery checks

- 8d75bfd206c6447e98527df584870a88 · failed · ValueError: cmo_run_stages 0: elapsed_seconds cannot change after it is recorded

## Captures

- pensim-attempt.json · SHA-256 11b4db0df3ab83179227a9c0bf760e8678a7847a03276b22f6331b8ca009a303
- freeze-drying-final.json · SHA-256 d727bf4fcbcfa2824e8f6969b192e09ba5bcf0e5152bafbcd854093698541315
- cho-delivery-attempt.json · SHA-256 0f6c246e67c3d7ca59c63713187507654a7b8547fd72950aa9d91f3f4ee8312e
