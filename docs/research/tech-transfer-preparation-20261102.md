# Technology-transfer experiment: preparation receipt

Prepared 2 November 2026. Completed the dataset audit, common transfer-assessment task, outcome/input separation, and descriptive scoring protocol. **No new GLM trial or human-efficiency experiment was run.**

## Prepared package

| Item | Recorded count/status |
|---|---|
| Source studies | 3; retrospective public literature, previously inspected by researchers |
| Transfer cases | 5; correlated cases must retain study grouping |
| Requested source facts | 28 |
| Source-supported reference risks | 25 across cases; researcher-authored, process-expert review pending |
| Numeric targets | 33: 2 receiving water-kLa summaries, 2 empirical enzyme endpoints, 29 receiving CO2 readings |
| Raw gas observations retained | 4,389 donor; 3,294 receiver; no imputation |
| Frozen files | 16, approximately657KB total including manifest |
| New model requests / provider spend | 0 / $0 |
| Observed human labor savings | Unmeasured |

[Frozen package manifest](../../backend/results/tech-transfer/preparation-v1-20261102/freeze-manifest.json), SHA-256:

`5aa91dfaffa24945bbbf50b36da30fe06c59bf1801dd1d581d68354292a17255`

The [protocol](tech-transfer-experiment-protocol-20261101.md) specifies common deliverables, comparisons, source/receiver boundaries, phased characterization queries, missing-data handling, metric definitions, human-effort accounting, scientific limits and the remaining total$50 ceiling. The filename follows the earlier research thread; the freeze manifest records the actual UTC timestamp.

## What passed

- `prepare validate`: all16 generated file hashes and all frozen source hashes verified.
- Focused data-boundary, scoring and existing fermentation regression checks: **24 passed**. These are software tests, not GLM performance evidence.
- [Deterministic baseline receipt](../../backend/results/tech-transfer/baseline-check-v1-20261102/receipt.json): all five numerical components executed, with33/33 requested numeric predictions scored against the declared observed targets. This checks calculation/scoring plumbing; it is neither a complete conventional workflow nor an agent run.
- No new model/dependency download, endpoint request, production-account change or deployment occurred. A small primary-source archive was added for traceability.

The conventional water-kLa component retains its receiving discrepancies; it was not fitted to those receiving answers. Empirical donor-enzyme and donor-gas comparators remain explicitly empirical. The five component outputs supply no measured human preparation, risk-assessment performance, acceptance event or labor reduction.

## Scientific qualification

The [measurement qualification](tech-transfer-data/paasikallio2017/qualification-notes.md) confirms timestamps and raw gas profiles. It does **not** confirm the exact concentration basis needed for physical molar balances. Product kinetics, broth oxygen limitation, absolute OUR/CER/OTR and product yield are not qualified. No new Trichoderma kinetic model was invented. That case is useful for reconstruction, applicability/missing-input recognition and descriptive gas prediction; it cannot establish mechanistic product-prediction uplift.

Sulfolobus supplies real receiving **water** characterization, with an explicitly challenged source-only model. Pichia supplies empirical assay-derived endpoints, not a pressure-to-productivity validation. A positive transfer-assessment score cannot be relabeled as safe operation, saved batches, commercial transfer success or generalized prediction accuracy.

## Exact next boundary

This package is prepared for an integration rehearsal after a separate execution manifest is completed. It is **not ready to be called a blinded comparative trial** merely because the directories are separated. Before paid inference:

1. Pin and freeze runtime/model identity, prompts, tool schemas, arm order/repeats and request/time/token limits.
2. Verify the worker cannot read original answer-bearing sources, evaluator data or prior outcomes, cannot retrieve external answers, and cannot receive phase2 settings before its readiness-assessment commitment.
3. Obtain process review of the factual/reference-risk rubric and declared scope. Until then, any review is a researcher-authored exploratory assessment.
4. Verify remaining account budget and a genuine bounded provider charge within the remaining total$50, including pilot/retries. A local ledger with unknown pricing does not bound provider charges.
5. Record an actual comparable conventional human assessment before claiming engineering labor savings. Existing runtime measurements do not substitute for this observation.

The package includes blank execution/submission/review/timing templates. Missing measurements remain null. Instructions and reproducible commands are in the [module README](../../backend/benchmarks/tech_transfer/README.md).

GitHub tracking could not be updated because the repository-required `gh` CLI is absent. No issue creation or external publication is claimed.
