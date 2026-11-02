# Measured transfer experiment preparation

This is an offline preparation/scoring module for the existing manufacturing agent and fermentation tools. It performs no network requests, loads no account credentials and invokes no LLM. Follow the [protocol](../../../docs/research/tech-transfer-experiment-protocol-20261101.md) and [source qualification](../../../docs/research/tech-transfer-data/paasikallio2017/qualification-notes.md).

From the repository root, using the existing environment:

```sh
PYTHONPATH=backend .venv/bin/python -m benchmarks.tech_transfer.prepare prepare --output backend/results/tech-transfer/preparation-v1-20261102
PYTHONPATH=backend .venv/bin/python -m benchmarks.tech_transfer.prepare validate --output backend/results/tech-transfer/preparation-v1-20261102
PYTHONPATH=backend .venv/bin/python -m benchmarks.tech_transfer.baselines --study backend/results/tech-transfer/preparation-v1-20261102 --output backend/results/tech-transfer/baseline-check-v1-20261102
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/test_tech_transfer_preparation.py backend/tests/lifesci/test_fermentation.py -q
```

Preparation refuses an existing directory. Validation checks source and frozen-file hashes and rejects unexpected files. Write all execution outputs, reviews, scores and timing observations outside the frozen directory. Material changes to sources/code/protocol require a new preparation version. The baseline command is only a deterministic numerical-component smoke check: no human preparation, completed transfer assessment or GLM execution is implied. It does not qualify a production model.

## Package boundaries

- `agent-input/<case>/`: reviewed donor/equipment evidence and donor CSV. No original full paper/workbook or receiving outcomes. Prepared-source fact accuracy does not establish autonomous raw-document extraction.
- `phase2-input/SC-*/`: receiver characterization rpm/airflow covariates, released only after a committed readiness assessment. No measured receiver kLa is supplied. These inputs test characterization prediction, not independent recipe discovery.
- `evaluator-only/`: receiving measurements, reference facts/risks/targets, and data qualification receipt. Keep the entire folder, all full source archives and past answer-bearing reports unavailable to evaluated agents.
- `templates/`: blank submission, human-review, execution-manifest and human-effort templates. Null time, cost and review fields are genuinely unmeasured; never replace them with zero for presentation.
- `protocol.md`, `freeze-manifest.json`: exact protocol snapshot and all content hashes. The freeze is local and retrospective, not externally preregistered.

Directory separation does not implement a sandbox. `isolation_enforced` remains false. The existing runner must demonstrate provider-only network isolation, file denial and phase commitments before comparative trials. Complete and freeze the separate execution manifest, pinning prompts/tools/model/repeats/order/budgets. Verify a real provider cost bound within the remaining total$50 before any pilot or inference. Dataset preparation and its tests do not perform those runs.

## Structured submission and scoring

Copy `templates/submission.json` into a fresh execution directory. Each fact uses a requested ID, typed value, exact requested unit and `citations` list such as `S1.equipment[1].working_volume_l`. Each prediction uses a requested ID, finite numeric `value` and exact requested `unit`; omit unavailable predictions and explain them in the assessment. Risks use locally assigned IDs, `description` and `citations`. `assessment` and `characterization_requests` preserve actionable reasoning and unknowns. Attach real returned model identity, request IDs, receipts and the phase1 commitment from actual execution; a filled JSON object is not execution evidence by itself.

A reviewer creates a separate review object with matching `case_id`, named `reviewer` and one entry per submitted risk: `submission_id`, `label` (`reference`, `unsupported`, `valid_out_of_scope`), `reference_id` when matched, and a rationale. Narrative entailment, source support and overall acceptance remain explicit human judgments, not automatic LLM scores. The reference set is a researcher-authored rubric awaiting process-expert review.

```sh
PYTHONPATH=backend .venv/bin/python -m benchmarks.tech_transfer.prepare score --output backend/results/tech-transfer/preparation-v1-20261102 --submission /path/to/actual-submission.json --review /path/to/review.json --result /path/to/new-score.json
```

The result records submission/manifest/review hashes. Missing forecasts retain incomplete coverage; missing risk review and timing remain null. Separate metrics preserve water-kLa, empirical enzyme and raw gas units; no combined accuracy score is manufactured. Report individual experimental cases and study grouping. These few studies cannot establish reliable population p90/p99, generalized tech-transfer performance or labor savings without observed matched human work.

GitHub tracker note: the repository requires the `gh` CLI for issue operations. It was unavailable during preparation; no issue was created or claimed.
