# Case-study implementation audit

Audited 2026-10-24 before implementation. Governing direction:
`Main_Culture_andETHOS.md`. The job is directory-to-investigation evaluation,
with minimal manual curation, inspectable evidence and no manufacturing writes.
Reuse the established domain store, tools, Prime runtime and evaluation isolation.
Adding another agent framework or a second parser/index would increase setup,
review and adoption effort without establishing better investigation quality.

| Area | Actual implementation | Verified/current gap and extension |
| --- | --- | --- |
| Prime orchestration | `backend/src/prime_runtime/harness.py`, `sdk_runner.mjs`, `bridge.py`; `backend/docs/prime_agent_reuse.md` | `PrimeManufacturingHarness.from_env` calls the installed adjacent Prime SDK; native Python kernel and `rlm.spawn` children. SDK checkout exists. Provider environment has no exported model/API credentials in this session; saved SDK authentication still needs a live preflight. Missing inference must be reported as unavailable, not replaced by rules under an agent label. |
| RLM lifecycle | `investigation_lifecycle.mjs`, `coordination.py`, `agent_view.py`; `backend/prime_skills/manufacturing_os/SKILL.md` | Existing descendant fan-in, synthesis reserve, checkpoints and report submission verification. Reuse for full-RLM trials; bounded-agent settings must actually disable recursion, not just rename the same workflow. |
| Generic ingestion | `backend/src/manufacturing_data/ingest.py`, `columnar.py`, `models.py`, `store.py` | CSV/XLSX/Parquet remain typed, columnar and numerically queryable. PDF/text/image OCR preserves page/line provenance. Unsupported formats are preserved and counted. DOCX is currently unsupported and needs an extension to this parser. Document availability defaults to file modification time, so historical replay needs an agent-input snapshot with byte-preserving, source-derived availability before indexing, not a prompt-only cutoff. |
| CMO pipeline | `backend/src/manufacturing_data/cmo/pipeline.py`, `schema.py`, `cases.py`, `case_api.py` | Reviewed numerical extraction/templates, durable project/case jobs, append-only review/action history, explicit unknown mappings. Existing case upload accepts CSV/XLSX/PDF and small ZIPs; it is not a 1,000-file autonomous causal investigation benchmark. Reuse generic ingestion beneath it instead of duplicating either pipeline. |
| Retrieval/linking | `backend/src/manufacturing_data/retrieval.py`, `tools.py`, `analysis.py`, `semantics.py` | FTS5/BM25 narrative retrieval, scoped SQL, source schema discovery, entities, numerical metrics and alignment. Numeric-native fields do not become text chunks. Extend discovery traces and question-dependent exploration over these tools, not a universal relevance classifier. |
| Evidence/verification | `models.py`, `store.py`, `tools.py`; `backend/src/workflows/`, `backend/src/prime_runtime/bridge.py` | Stable evidence IDs and document/page/sheet/cell/row references, original bytes, cutoff/scopes, bridge citation checks and deterministic calculation verification. Duplicate files need evaluator support by content identity; generated causal labels must remain outside this index. |
| Existing evaluation | `backend/benchmarks/common/{case_protocol,case_runner,agent_adapter,full_agent_adapter,isolated_runner,trace,objective_scores}.py`; `backend/benchmarks/baselines/` | Frozen inputs, allowlists, hashes, traces, full-RLM adapter, conventional and single-pass model baselines. macOS sandbox-exec provides inherited filesystem denial and negative probes. Reuse this isolation for evaluator-only manifests; source-generator/evaluator modules must be unreadable by model processes. |
| Existing case studies | `backend/benchmarks/fresenius/`, `backend/benchmarks/cho/`, configs and `backend/benchmark/case_comparison/` | Existing tasks and report contracts stay unchanged. Baseline tests below establish two pre-existing fixture/report failures. |
| Existing Sanofi/IndPenSim assets | `backend/benchmarks/cmo_ingestion/{generate,evaluate}.py`, `provenance/fda-sanofi-690604.html`, `provenance/mendeley-v2.json`, `raw/100_Batches_IndPenSim.zip` | Publisher archive/metadata already present. Existing generator creates extraction/template challenges and a sampled historical projection; it does not supply four hidden causal scenario families or autonomous discovery evaluation. Reuse hashes/headers and numerical source preservation. Independently verify the archive before new measurements. |
| Frontend | `frontend/app/`, `components/`, `lib/routes.ts`, `lib/agent/`; `frontend/package.json` | Current frontend is Next.js App Router, not the earlier React/Vite `frontend/src` layout. Existing fixture-backed manufacturing screens and agent interface remain intact. Add a functional case-study view/API integration after measured backend outputs exist. |

## Executed baseline

```bash
cd backend
.venv/bin/python -m pytest -q tests/test_new_benchmarks.py \
  tests/test_prime_runtime.py tests/test_columnar_ingestion.py \
  tests/test_cmo_ingestion.py tests/test_case_comparison.py
```

Result: **80 passed, 2 failed in 19.96 s** before changes. Failures:

- `ChoCaseTests.test_recorded_prime_pilot_is_wired`: missing recorded Prime pilot
  in `runs/cho-comparison`.
- `ReportTests.test_committed_static_report_is_current`: committed static report
  lists zero attempts while the current generated report lists seven.

Do not manufacture an agent run or rewrite historical scores to remove them.
Dependencies found: pypdf, python-docx, reportlab, Pillow, polars, duckdb,
openpyxl, pytesseract and docling. Runtime presence is not extraction accuracy:
new format/coverage tests and an actual complete benchmark remain required.

## Implementation boundaries and acceptance

Keep `ManufacturingStore` and `ManufacturingTools` as the shared evidence plane;
add a case-study generator and evaluation adapter under existing benchmark
conventions. Keep hidden labels outside source directories and model-readable
code, stage only eligible sources for historical replay, and verify OS denial
before scoring model runs. Deterministic retrieval is a named baseline, never a
claimed autonomous agent. Use actual Prime credentials where available and
record unavailable modes when not. Scientific root-cause labels are synthetic;
historical IndPenSim groups are observational and cannot establish randomized
intervention effects. Simulator control must pass an executed gate first.

Observable measures: extraction/field/provenance accuracy, critical recall and
precision, causal/counterevidence/abstention scores, future leakage, runtime,
tokens/cost and tool effort. No accuracy or cost benefit is assumed from the
architecture. Primary source/license and experiment verification are documented
separately in the provenance and results deliverables.
