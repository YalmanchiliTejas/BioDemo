# Development replay of the revised intervention workflow

This is one already inspected development scenario, not a frozen held-out benchmark or evidence of average efficacy. It verifies the restricted research-agent harness and separate outcome recording. It is not an end-to-end deployment of the production OS or a real intervention.

A hidden PenSim receiver differs in initial conditions, oxygen-transfer coefficient, growth and production parameters from the source-calibrated point model. Transfer deteriorates at48h. The approaches see online oxygen and only product assays whose laboratory delay has elapsed at52h. They cannot read true receiver parameters or future outcomes. The source model was fitted to DO/product, without perfect substrate values.

| Approach | Recommendation | Post-decision oxygen constraint | Product inventory at96h |
|---|---|---|---:|
| Original recipe | Keep | Violated |262.99kg |
| Agent without supplied model | Increase air | Violated |286.64kg |
| Model + conventional optimizer | Stronger feed reduction | Satisfied |586.42kg |
| Same agent + model | Stronger feed reduction | Satisfied |586.42kg |

The agent-plus-model trace contains four explicit model comparisons before its reviewable recommendation and hidden-outcome replay. It did not request the optional extra assay. A separate sequential harness check requested an assay, advanced the process by4h before releasing it, then froze a recommendation before revealing the virtual outcome. These are different development receipts, not one fabricated agent investigation trace.

This case demonstrates a working intervention comparison and also shows why the optimizer comparator is necessary: the agent-plus-model matched conventional software here. It does not establish additional agent value. A real time/cost comparison or customer claim cannot be inferred from this one selected illustration.

## Reproducible records

- `backend/results/interventions/development-workflow-20261029-v2/results.json`: all four approaches, tool events and hidden action replays at the actual decision clock.
- `backend/results/interventions/development-20261029/sequential-harness.json`: delayed-assay receipt.
- `backend/results/interventions/development-20261029/oxygen-envelope.json`, `recovery-window.json`, `recovery-check.json`: development-only checks including normal, recoverable, no-feasible-action and numerical-domain failures.
- `backend/benchmarks/interventions/`: versioned engine, session, source/receiver point model, conventional selector and restricted SDK adapter.
- `backend/tests/test_intervention_pensim.py`: separate mass/concentration, stop accounting, pre/post violation persistence, delayed-assay boundaries, hidden substrate and future-data rejection checks; five tests passed.

The first setup failed before any AI request because a development file was incorrectly read as a frozen dataset. Its directory remains retained. The corrected run completed both actual AI sessions without retrying or selecting by outcome.

## Required before the new main benchmark

Qualify the source calibration across multiple source batches and held-out source times, quantify receiving uncertainty without using future measurements, fix the measurement/noise/cost/action policy and intended stratum proportions, freeze code/prompts/evaluation hashes, then generate fresh independent scenarios. Report realized recoverability and numerical-domain failures without replacing seeds. Repeat AI sessions within each scenario and cluster comparisons by independent scenario. Keep the previous matching-model test as an upper bound. Only then report aggregate intervention findings.

SMPL's uncertain-state measurement interface and the grouped physical CHO/NISTCHO evaluation remain subsequent stages; neither is represented as completed by this replay. The acquired NISTCHO failure/prevention feeding data are physical, but campaign confounding and absence of same-vessel rescue remain explicit in the source manifest.
