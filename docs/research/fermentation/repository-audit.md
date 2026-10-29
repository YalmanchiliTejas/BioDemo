# Fermentation transfer repository audit

Audit performed before implementation. Governing direction: `Main_Culture_andETHOS.md`; one root glossary and three proposed ADRs retain official record ownership, versioned evidence and persistent missions outside reasoning workers. `repository-inventory.json` inventories the current repository across backend, frontend, docs, assets, tests and deployment. Generated run/results directories contain historical artifacts, not alternative production APIs. Existing working-tree modifications are preserved.

| Existing capability | Inspected implementation | Reuse / boundary |
|---|---|---|
| Prime persistent agent and native subagents | `backend/src/prime_runtime/{harness.py,sdk_runner.mjs,bridge.py}`, `backend/prime_skills/manufacturing_os`, `backend/docs/prime_agent_reuse.md` | Sole reasoning runtime; existing `additional_tools` connects host-owned deterministic fermentation tools. Persistent sessions, Blackboard, workflow and native rlm.spawn stay intact. |
| Qualified routing, budgets, traces | `src/lifesci/prime_adapter.py`, `gateway/`, `lyophilization/comparison.py` | Use existing PrimeInvestigationAdapter; unresolved routes stay unresolved. No fake agent scores or automatic qualification. Root usage does not necessarily include child/OCR costs. |
| Ingestion / document extraction | `src/manufacturing_data/{ingest.py,store.py,tools.py}`, CMO pipeline | Existing package ingestion, PDF/text/table extraction, exact source references and content hashes. Published structured excerpts must be reviewed transcriptions, never called autonomous extraction. |
| Retrieval and evidence | `manufacturing_data/retrieval.py`, `lifesci/evidence.py`, identity/store | Reuse scoped retrieval and versioned evidence / derived artifacts / invalidation. Full papers contain held-out answers: keep original archives evaluator-side; stage only authorized excerpts during blinded agent evaluation. |
| Physics | `lifesci/lyophilization/{model.py,workflows.py,reference.py}`, `process_engineering/{catalog.py,engine.py,service.py}` | Existing drying solvers remain unchanged. ModelCatalog, SolverBudget and deterministic flow operators are reusable. Existing adapters and runner are specifically Kv–Rp/temperature/vial based; no oxygen-transfer model exists. Add bounded fermentation algebra as registered model adapters, without another numerical integration framework. |
| Workflow / transfer / review | `lifesci/{flows.py,network.py,missions.py,actions.py,records.py}` | Reuse FlowService, evidence records and version-bound `review_physical_analysis` proposals. Simulation never dispatches manufacturing instructions. TransferService and official repositories retain ownership. |
| Benchmarking | `benchmarks/common/{case_protocol.py,full_agent_adapter.py,case_runner.py}`, `lyophilization/comparison.py` | Frozen inputs/hashes, deterministic evaluation and existing Prime host. Existing case protocol enumerates CHO/Fresenius; preserve those contracts. Separate manual timing (unobserved), physics-only execution and actual Prime attempts. Filesystem isolation is required before any blinded live Prime run; a prompt alone is not isolation. |
| CHO / Fresenius | `benchmarks/cho`, `benchmarks/fresenius`, `benchmark/case_comparison`, `README_benchmarks.md` | Preserve aligned experimental CHO versus reconstructed Fresenius classification, hidden references, cases, APIs and tests. |
| IndPenSim / Sanofi | `benchmarks/autonomous/simulator.py`, `benchmarks/cmo_ingestion`, `docs/case_studies` | Reuse existing simulator if executable. Prior feasibility report documents nonfinite full runs around134h; valid prefixes are not complete-batch validation. Sanofi operational files are synthetic, informed by FDA public facts. Never use these as experimental transfer truth. |
| Frontend | `frontend/app/(app)/tech-transfer`, `components/process`, `ScientificPlot`, `EngineeringChat`, `Companion` | Add source-grounded projects to existing transfer portfolio; reuse cards, tables, plot, process request client and companion. Preserve all URLs including simulation and advanced URL. No second chat or dashboard framework. |

## Engineering decision

Job: a process engineer needs to compare receiving vessels and review supportable operating options from published experiments. A small registered characterization adapter and transfer panel fits this job. A new fermentation simulator framework or replacement agent/frontend would repeat infrastructure and add validation burden; reject those alternatives.

Easy to Start: selectable literature projects and explicit missing inputs. Easy to Trust: experimental summaries versus fitted coefficients versus scenario assumptions, frozen validation split, hashes and failed runs. Easy to Act: conditional strategies, follow-up measurements and existing review proposals. Easy to Adopt: existing OS routes, API namespace, identity and records; read-only relative to production.

Measure prediction discrepancy, extraction/citation checks, unsupported recommendations, computation and explicitly assumed operating costs. Human preparation time and experiment-elimination claims remain unavailable until actually observed. Trade-off: summary-only publications and uncharacterized equipment prevent unique receiving-site predictions; uncertainty/sensitivity and inconclusive findings are scientific outputs, not silently filled gaps.

Tracker CLI `gh` is unavailable in the current shell; no issue was created or claimed. This audit and research reports are evidence deliverables, not a replacement issue tracker.

## Implementation outcome

New code is limited to the fermentation domain adapter, allowlisted literature inputs/evaluator split, additive domain API/service, benchmark/report and ingestion-verification entry points, an existing-view frontend component and focused tests. Two model adapters use deterministic algebra; no new integration solver or kinetic model was required.

Existing abstractions extended:

- `process_engineering/catalog.py`: optional process-family selection. The default two drying adapters and their API behavior remain unchanged.
- `lifesci/container.py`: composes the fermentation service and installs additive routes under the existing process-model namespace.
- `benchmarks/common/full_agent_adapter.py`: an optional bounded fermentation tool on the existing Prime host. Other benchmark modes retain their existing path.
- `frontend/app/(app)/tech-transfer/page.tsx`: selectable literature projects beside existing transfer records.
- `ScientificPlot`: an explicit coordinate name for volume comparisons; time plots retain their previous default and companion behavior.
- Existing evidence, FlowService, SolverBudget, mission and ActionService methods are called directly. No dispatch, approval bypass or alternate system of record was added.

Executed reuse checks: original PDF/DOCX parsing indexed three source files into an evaluator-only store; existing scoped lexical retrieval verified nine excerpts against originals. Native parser fallback was used where Docling weights were unavailable; no new parser or downloaded model was introduced.

Verification details are in `results/verification.json`. The platform/Prime regression run passed414 tests, and the focused fermentation suite passed14. Real-API browser checks passed for the new cases and the existing companion/navigation. A separate case-study regression run passed114, skipped2 and failed4 CHO checks because local aligned references and a recorded pilot are absent. The aligned-reference archive descriptor exists; no descriptor for the missing pilot was found. No archive references, historical reports or scientific values were regenerated to make these checks pass.
