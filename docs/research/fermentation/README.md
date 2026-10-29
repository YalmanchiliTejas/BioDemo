# Experimental fermentation transfer capability

This extends the existing Manufacturing OS. Open **Tech transfer → Published fermentation transfer projects** at `/tech-transfer/`. Sulfolobus and Pichia use the existing cards, tables, ScientificPlot, companion, authenticated process API, evidence registry, FlowService, ModelCatalog, bounded scientific runner and engineering review proposals. Existing simulation, case-study and other routes remain available.

## Deliverables and evidence

- [Repository audit](repository-audit.md) and [whole-repository file inventory](repository-inventory.json).
- [Sulfolobus acquisition and interpretation](sulfolobus-sources.md), [source manifest](sulfolobus/source-manifest.json), [reviewed transcription](sulfolobus/measurements.json).
- [Pichia acquisition and interpretation](pichia-sources.md), [source manifest](pichia/source-manifest.json), [reviewed transcription](pichia/measurements.json).
- [Executed technical/economic report](results/report.md), [frozen protocol and hashes](results/freeze-manifest.json), [machine-readable results](results/results.json).
- [Existing parser execution](results/ingestion-check.json), [scoped retrieval and original-source verification](results/retrieval-check.json), [real API/browser checks](results/ui/checks.json).

The research source archives include withheld answers. They and the evaluator-only full transcription are **not** agent input packages. Runtime public inputs are `backend/src/lifesci/fermentation/data/*.public.json`; receiving validation values are in the separate `validation.evaluator.json`.

## Scientific interpretation

**Sulfolobus:** two 2-L ring-sparger observations fit a power exponent; the gas exponent and receiver geometry effect remain unidentified. Receiver power uses a challenged constant-power-number/gassing-factor scaling with impeller count, diameter and speed. Vvm is used explicitly because tank diameter / superficial gas velocity are not available. Power is hydrodynamic power, not measured motor electricity. Search bounds and power screens are scenario assumptions, not rated limits. The deliberately source-only model underpredicts the measured 20-L and 200-L water kLa summaries; the discrepancy and broad assumption sensitivity remain visible. No 200-L viability is invented. The result supports receiver characterization, not an approved transfer recipe.

**Pichia:** gauge pressure is converted to absolute pressure. Henry-law driving force, OTR/OUR margins and isothermal compression work execute deterministically under editable characterization/price assumptions. Flow is explicitly normalized to 273.15 K and 101.325 kPa; article flow reference conditions are unknown. Enzyme production is not predicted from pressure: the displayed 10-L constant-endpoint comparator is explicitly empirical. Published receiver outcomes and the 30-L direct oxygen comparison are displayed separately. Feeding, DO, biomass, duration and scale confound causal attribution. Partial oxygen-delivery cost excludes unmeasured methanol, occupancy, capital, cooling and other terms unless supplied. No measured dollars or saved engineering hours are claimed.

Both parameter-fit and agent-input splits exclude the receiving outcome values. Researchers inspected the published papers to construct this retrospective benchmark; analyst blinding, independent pretraining and prospective validation are not claimed. No interpolation of raw experimental trajectories was invented.

## Prime / benchmark status

The existing `PrimeInvestigationAdapter`, `FullManufacturingOS`, persistent SDK host, native child agents, scoped ingestion/retrieval and bridge are reused. `additional_tools` exposes the same deterministic fermentation model; no new agent framework exists.

Current actual Prime attempts are **unresolved** because no qualified investigation-planning route exists. No qualification was manufactured. A **blinded** trial additionally fails closed before starting a worker because the current shared runner enforces filesystem isolation but cannot exclude external public-paper or local-API retrieval. Normal interactive Prime assistance is explicitly unscored; it uses the existing isolated filesystem path and review boundaries. A passing unit-test double verifies tool wiring only and is not an AI-performance result.

Manual baseline A documents conventional steps but has no observed human timing. Baseline B runs the engineer-prepared model. Method C records actual Prime attempts with unavailable scores when unresolved. Extraction/citation accuracy and unsupported-recommendation counts remain unavailable for incomplete agent runs. The full-source parser/retrieval checks are evaluator-side engineering checks, not autonomous extraction accuracy.

IndPenSim is retained. Its prior numerical feasibility report remains applicable; `pensimpy` and the earlier isolated executable environment are unavailable on this host, so no additional dynamic stress-run result is claimed. No simulator was rebuilt. Optional Bernemann equipment characterization is deferred.

## Reproduction

Use the existing repository environment and API; no new service is required. From the repository root:

```sh
PYTHONPATH=backend .venv/bin/python -m src.lifesci.fermentation.benchmark --output docs/research/fermentation/results
PYTHONPATH=backend .venv/bin/python -m src.lifesci.fermentation.ingestion --output docs/research/fermentation/results/ingestion-check.json
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/lifesci/test_fermentation.py -q
```

The ingestion command uses the existing PDF/DOCX parsers. Repeated execution can report unchanged files because the existing content-addressed store avoids duplicate parsing; it does not change original source bytes.

Start the established seeded `src.lifesci serve` API and frontend as documented in `docs/process-simulation/README.md`. The additive endpoints are:

- `GET /v1/process-model/fermentation/projects`
- `POST /v1/process-model/fermentation/projects/{sulfolobus|pichia}/evaluate`
- `POST /v1/process-model/fermentation/projects/{case}/agent-assessment`
- `GET /v1/process-model/fermentation/results/{id}`
- `POST /v1/process-model/fermentation/results/{id}/review`

All use the existing identity/context and idempotency contracts. Evidence corrections invalidate derived calculations and proposals. Failed calculations remain in the existing flow/result records. Review creates a proposal requiring the engineering role; it never dispatches a manufacturing change.

Browser verification against a running API/frontend:

```sh
PLAYWRIGHT_MODULE=/path/to/playwright node frontend/scripts/check_fermentation.cjs http://127.0.0.1:5181
```

The browser test uses real deterministic API responses, checks that an oxygen-price change can reverse the cost result, verifies review without dispatch and credential/route recovery, and captures desktop/mobile evidence. Existing companion and scientific-workbench browser checks remain separate.

## Hosted Modal research assessments and case pages

**Latest actual run:** [reviewed results](results/modal-live-20261027-02/reviewed-results.md). Both hosted executions completed: Sulfolobus returned a partial investigation; Pichia completed its review for the available evidence. All8 deterministic calls replayed and195 staged source citations were checked. Four interpretation issues and the generic numerical-lineage gap remain explicit; agent uplift and real engineering savings are not claimed.

The case-study entry point is `/case-studies/`, with direct links such as `/case-studies/#pichia`. Recorded scientific comparisons load before opening the existing live technology-transfer workbench. Full source evidence, assumptions, model versions, frozen splits and hashes remain inspectable. The original factory and IndPenSim exports remain available.

Prime can use the saved hosted Modal model for a **read-only research draft** without a production task qualification. This opt-in is local to fermentation research; it does not change the production gateway's routing policy or create a qualification. The default blinded benchmark still fails closed until its external-retrieval boundary is sufficient. A useful exploratory assessment and a published blinded agent-uplift score have different requirements.

Set `MODAL_PROXY_TOKEN` (or `BIODEMO_MODAL_PROXY_TOKEN`) in the backend launch environment or ignored `backend/.env.local`, then restart the backend. Existing environment variables override the local file. The SDK retains credential resolution; no token is copied into evidence, requests, public exports or reports. Optionally set `BIODEMO_PRIME_RESEARCH_MODEL=modal/zai-org/GLM-5.3`; otherwise the single Modal model in Prime's existing saved model registry is reused. Hosted billing remains unknown, not a measured zero-dollar cost. Wall time and tool calls are bounded; the gateway ledger reservation is not a Modal compute-billing cap.

Run exploratory attempts into a **fresh output directory** and preserve failed attempts:

```sh
PYTHONPATH=backend .venv/bin/python -m src.lifesci.fermentation.benchmark --research --output docs/research/fermentation/results/my-research-run
```

This CLI also loads `backend/.env.local` through the existing environment loader. Its agent workspace is outside the evaluator-only research archive, and worker paths are absolute. Receiving answers are not staged into the agent package. Research runs use a600-second wall-clock cap and48 host-tool calls per case; the initial120-second attempts are retained as failures. Research results remain ineligible for blinded scores and require independent scientific review.

Refresh only the presentation copy of the original deterministic benchmark and check the case-page interactions:

```sh
cd frontend
npm run export-fermentation
cd ..
PLAYWRIGHT_MODULE=/path/to/playwright node frontend/scripts/check_case_studies.cjs http://127.0.0.1:5181
```

See [hosted-modal-and-case-pages.md](hosted-modal-and-case-pages.md) for the decision and verification record. The original unresolved qualification attempts remain historical records; they do not imply Modal cannot be used for research.
