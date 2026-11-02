# Data readiness for a combined technology-transfer and agent evaluation

Audit date: 2026-11-01. Scope: establish what data exists and what it can test before building or running a new benchmark. No new agent inference, paid endpoint requests, production changes or public claims were made in this audit.

## Decision

Build a single transfer workflow with two separately scored outcomes: (1) scientific decision quality under equipment/scale changes and (2) the effort required to produce an evidence-backed transfer assessment. Existing data can bootstrap a retrospective research benchmark; it is not sufficient by itself to establish improved commercial transfer outcomes or reduced engineering labor.

## Locally available evidence

| Source | Evidence actually on disk | Usable evaluation | Missing evidence / boundary |
|---|---|---|---|
| Sulfolobus, Rastädter et al. (2023) | Original article/PDF, official supplement, equipment dimensions, reviewed measurements; 2 L calibration and 20/200 L receiving summaries | Extract/reconcile equipment and units; identify oxygen-transfer risks and missing characterization; compare predictions with two receiving water-kLa values | No raw batch or reoxygenation trajectories, broad gas-flow calibration, replicated receiving campaigns, certified equipment limits or human work timings. Water kLa does not validate broth biology. |
| Pichia, Liu et al. (2016) | Original article/PDF/XML, tables and reviewed measurements; 10 L calibration, 100/1,000 L receiving summaries; separate 30 L oxygen/pressure comparison | Reconcile scale, pressure and feeding changes; extract transfer package; check conditional oxygen balance and distinguish measured results from assumptions | No measured kLa/OUR or calibrated productivity kinetics, full raw trajectories or observed labor timings. Pressure, feed, biomass and operating duration are confounded. |
| Existing freeze-drying transfer demonstration | Literature archive, model inputs and receiving-site scenario | Test integration, provenance, conditional calculations and review workflow | Receiving capacity/observations include synthetic assumptions. Not an independent measured donor/receiver transfer campaign. |
| OWL CHO | Local manifest/profile; large raw/aligned data have archive descriptors and are currently absent from their mounted paths | Same-scale process-data ingestion/forecasting after selective restoration | Small working-volume study is not a donor/receiving-site transfer dataset. Do not restore hundreds of MB for this audit. |
| NISTCHO feeding | Small local CSV/XLSX dataset with acquisition/attribution record | Potential supporting condition-change and data-ingestion tasks | Feeding comparisons are not by themselves transfer outcomes across sites/scales. |
| IndPenSim / SMPL / current intervention scenarios | Existing code and simulated case artifacts | Controlled decision experiments after numerical/integration qualification | Synthetic evidence; cannot supply measured human labor or qualify a real transfer by itself. |

Local integrity check: all **15** manifest-listed Sulfolobus/Pichia files exist and match recorded SHA-256 values. See [machine-readable audit](tech-transfer-local-data-audit-20261101.json). Their current evaluator has **two Sulfolobus and two Pichia receiving summary rows**, not four independent transfer campaigns. File integrity is not scientific validation. Source manifests preserve attribution and access boundaries.

Sources: [Sulfolobus original paper](https://www.frontiersin.org/journals/bioengineering-and-biotechnology/articles/10.3389/fbioe.2023.1160012/full), [Pichia original paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC4726300/), [local Sulfolobus source audit](fermentation/sulfolobus-sources.md), [local Pichia source audit](fermentation/pichia-sources.md), [existing data-source inventory](physical-model-evaluation-datasets.md), [local freeze-drying transfer artifact](../process-simulation/artifacts/transfer.json).

## Additional paired-scale raw measurements located

The first-party [Zenodo record 5846028](https://zenodo.org/records/5846028) includes `Paasikallio2017_CO2_data.xlsx`, a 731,057-byte workbook with 1 L and 250 L culture sheets. Direct file inspection found 4,389 and 3,294 complete numeric rows, respectively, with Time(h), N2, O2, Ar, CO2 and Ethanol channels, plus sparse air-input annotations. The sampling interval is approximately three minutes. These are two cultures, not thousands of independent experiments. Workbook MD5 matches the published `f6c552f3fba234edd224c6f9e1417ecc`.

Despite the enclosing repository title referring to marine Trichoderma T2, this workbook concerns T. reesei VTT D-161646 from [Paasikallio et al. (2017)](https://pmc.ncbi.nlm.nih.gov/articles/PMC5504852/). The paper describes scale-up at 1/10/250 L; this workbook supplies gas traces at 1/250 L, not all three scales. Do not describe it as a recent manufacturing incident or a pharmaceutical product-transfer dataset. It is useful experimental bioprocess scale-up evidence.

Candidate task: reconstruct the donor/receiver package, reconcile vessel and gas-flow information, identify scale-dependent differences and data gaps, and evaluate a prespecified gas-dynamics prediction on held-out receiving data. Model applicability is not yet qualified. Missing product, biomass, feed and dissolved-oxygen time series prevent treating gas agreement as mechanistic product-yield validation. Medium/feed differences and measurement basis must be reconciled before choosing an equation or target. This is a stronger raw-data starting point, not a complete transfer-efficacy dataset.

## Existing runs must not be mistaken for new validation

[Recorded GLM research runs](fermentation/results/modal-live-20261027-02/reviewed-results.md) already exercised both transfer projects. Sulfolobus took 552.5 seconds and returned a partial investigation; Pichia took 593.9 seconds and completed for the available evidence. Eight deterministic tool outputs were replayed successfully; four interpretation issues were identified. These were exploratory runs using manually prepared excerpts, not a completed matched benchmark of scientific uplift or labor savings. The generic report ledger had zero verified calculated metrics; separate computational replay has a narrower meaning.

Prior manual preparation time and matched human completion times are unobserved. The current fermentation benchmark also fails closed for blinded execution until retrieval isolation is adequate. Do not merely rerun it and label its report a new accuracy/time benchmark. See [benchmark implementation](../../backend/src/lifesci/fermentation/benchmark.py).

## One workflow, two outcomes

Job: from a donor process package and receiving-equipment records, produce a reviewable transfer assessment: reconciled parameters/units, equipment differences, linked risks, supported operating options, explicit missing measurements and a proposed characterization plan. The deliverable is a proposal for human review, not equipment execution.

Compare agent without the mechanistic tool, conventional prepared model workflow, and agent with the same mechanistic tool. Account for which inputs each approach must have prepared; a model-only path that requires an engineer should include that engineer’s preparation/review time. Include a matched conventional human workflow to support human-effort claims. Separate human-assisted and autonomous outputs if assistance is needed.

- Scientific scores: numeric extraction/unit accuracy, source support, risk precision/recall against a prospectively frozen expert rubric, held-out receiving prediction error, unsupported recommendations and appropriate requests for missing characterization. Score operating success only when an independent measured outcome or separately qualified evaluator exists.
- Effort scores: active human minutes for finding/preparing data, configuration, review and corrections; end-to-end elapsed time to the same acceptance criteria; completion/rework rate; tool/model cost. Preserve failures and incomplete runs.
- Measure elapsed and human time separately. Existing wall-clock agent runs establish neither saved labor nor reduced transfer calendar time. Do not publish p90/p99 as reliable population estimates from two literature projects or treat time points / prompt variants as independent transfer campaigns.
- Freeze entire receiving runs or independent conditions for testing before tuning. Full papers contain receiving answers: keep outcome-bearing source material outside agent retrieval. Disclose literature pretraining and prior developer exposure; these are retrospective, not pristine unseen cases.
- Predetermine target-specific tolerances with a process reviewer. The same equations must not generate the target, guide the recommendation and certify it as experimental success.

## Product and engineering trade-off

The simple approach reuses existing transfer projects, ingestion, evidence records, registered physical tools and report review to test extraction, risk identification and characterization decisions. An ambitious complete dynamic scale-up model would need measurements the current summaries do not supply. Start with the former while qualifying richer multi-scale data; do not fill the gap with invented trajectories.

Easy to Start: reuse the existing source packages and small files. Easy to Trust: retain source hashes, negative results, uncertainty and evaluator separation. Easy to Act: score a usable transfer assessment and explicit next measurements. Easy to Adopt: preserve the current transfer workflow, source-system ownership and engineering approvals. Success is a reviewable assessment meeting fixed quality criteria with measured total human effort, not a longer report or a faster unreviewed response.

Public data verification and any newly found multi-scale measurements are documented separately in [the primary-source verification](tech-transfer-public-data-verification-20261101.md). Qualification of those files must precede selecting the scientific endpoint; data availability alone does not mean the existing model applies.
