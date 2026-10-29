# Implementation and execution

## What changed and what was reused

The first job is an inspectable directory-to-investigation benchmark, not a
replacement platform. Existing ingestion/store/tools, immutable originals,
typed Parquet/DuckDB queries, FTS5 retrieval, scope/time gates, report verification,
Prime SDK/native RLM and isolated benchmark worker remain the evidence plane.
Simple deterministic baselines establish where those components fail; a new
agent framework or parallel parser/index would obscure that comparison.

This reduces preparation (Easy to Start), retains exact source evidence and
explicit failures (Easy to Trust), provides executable follow-up and ranked
blockers (Easy to Act), and keeps the existing interfaces and systems of record
(Easy to Adopt). Trade-offs: macOS-only scored isolation, authored synthetic
mechanisms, fixed-baseline exploration limits and an optional simulator whose
numerical gate failed. These are measured constraints, not validated compliance.

| Exact repository path | Responsibility |
| --- | --- |
| `backend/benchmarks/autonomous/generate.py` | Four fictional scenario families; mixed-format serializers; opaque corpus; evaluator-only truth; seeds; byte-preserving distractor scaling. |
| `backend/benchmarks/autonomous/run.py` | All-file availability snapshots, existing OS-isolated worker, post-execution scorer, run/summary receipts and partial timeout coverage. |
| `backend/benchmarks/autonomous/check_extraction.py` | Independent structured source-reader round-trip checks. |
| `backend/benchmarks/autonomous/indpensim.py` | Verified original archive projection, original-row lineage, all 100 batch ingestion and descriptive fault screen. |
| `backend/benchmarks/autonomous/simulator.py` | Optional simulator gate, observable whitelist, bounded controls, matched/repeat runs, numerical validation and deadlines. |
| `backend/benchmarks/autonomous/export_demo.py` | Actual results export; original citation bytes checked against historical allowlist hashes; no hidden manifests. |
| `backend/benchmarks/autonomous/.gitignore` | Raw/generated corpora, workspaces and large result directories excluded by default. |
| `backend/benchmarks/common/directory_discovery.py` | Deterministic objective-specific retrieval/source expansion, provenance, duplicate support control and activity trace. |
| `backend/benchmarks/common/investigate_directory.py` | User directory + natural-language objective entry point; same isolated adapters; retained follow-up workspace. |
| `backend/benchmarks/common/agent_adapter.py` | Dispatch rules/RAG through existing interface; reuse existing one-pass model adapter; reject unavailable model credentials/invalid cited IDs. |
| `backend/benchmarks/common/full_agent_adapter.py` | Explicit partial-ingestion option and document backend; default strict behavior retained; bounded recursion setting forwarded. |
| `backend/src/manufacturing_data/ingest.py` | DOCX paragraph/table-cell provenance, flat JSON-array routing, explicit corrupt JSON errors; parser cache version advanced. |
| `backend/src/manufacturing_data/columnar.py` | Flat JSON record arrays enter the same wide Parquet/query plane; original decimal token strings remain intact. |
| `backend/src/manufacturing_data/verification.py` | Original DOCX paragraph/table-cell and JSON record/field verification. OCR stays pending independent review. |
| `backend/src/manufacturing_data/tools.py` | Optional bounded per-source lexical hit cap. |
| `backend/src/manufacturing_data/retrieval.py` | Source diversity, stable source-path lexical ties, rank-preserving evidence resolution and existing-index migration. |
| `backend/src/manufacturing_data/terminology.py` | Empty queries no longer match unmapped metric names and omit document content. |
| `backend/src/manufacturing_data/store.py` | Registered-source hash fingerprint for follow-up package binding, including failed/unsupported sources. |
| `backend/src/prime_runtime/harness.py`, `sdk_runner.mjs` | Optional native `rlmMaxDepth=0` boundary for bounded-agent comparison; full-RLM default unchanged. |
| `backend/src/prime_runtime/bridge.py` | Advertise source-diversity option in existing agent tool contract. |
| `backend/benchmark/application/api.py` | Optional expected-package fingerprint on existing rollout endpoint; mismatch rejected before inference; explicitly configured development CORS origins. |
| `backend/pyproject.toml` | Declare python-docx in manufacturing-data dependencies. Simulator dependencies remain isolated. |
| `backend/tests/test_autonomous_discovery.py` | Generator reproducibility, format/provenance failures, temporal denial, ranking/diversity, package fingerprints and scorer failure cases. |
| `backend/tests/test_indpensim_simulator.py` | Action/observation bounds, invalid-state closure and paired failure/timeout reporting. |
| `backend/tests/test_prime_runtime.py` | Existing API routing test now also checks mismatched/matching source-package binding. |
| `frontend/app/(app)/case-studies/page.tsx` | Existing design-system run viewer, FDA/synthetic disclosures, metrics, sources, evidence, activity, batch statistics, simulator failures and real API follow-up. |
| `frontend/lib/routes.ts` | Case-study navigation and search entry. |
| `frontend/public/case-study-results/.gitignore` | Generated demo data/source files stay out of Git. |
| `docs/case_studies/` | Audit, primary provenance, methods, measured results, limitations, commands and compact receipts. |

No Fresenius/CHO task/reference definitions were changed. Baseline fixture/report
failures are preserved and documented rather than replaced by fabricated runs.

## Environment

Run Python commands from `backend` using the existing `.venv`. Dependencies are
the existing `manufacturing-data`, `benchmarks`, `documents` and `app` extras.
OCR needs the existing Tesseract executable. The synthetic scanned-PDF writer
uses the macOS Arial font; scored isolation currently requires macOS sandbox-exec.
The adjacent existing Prime SDK checkout must be built/configured. No application
environment mutation is required for the optional simulator: see its separate
[isolated installation report](indpensim_feasibility.md).

## Generate, ingest, investigate and evaluate

Bulk data now lives in private DagsHub storage. Prefer the remote commands in
[storage and cold execution](storage.md); the local destinations below remain
explicit development options. Existing migrated input paths resolve from their
registered remote descriptors when absent locally.

Use new destinations: source corpora and case outputs reject overwrite.

```sh
cd backend
.venv/bin/python -m benchmarks.autonomous.generate /private/tmp/manufacturing-100 --count 100 --seed 417 --scenario-seed 718
.venv/bin/python -m benchmarks.autonomous.run /private/tmp/manufacturing-100 /private/tmp/manufacturing-results-100 --modes keyword_rules linked_rules --retain-workspace

# Controlled growth: same critical source bytes, only more distractors.
.venv/bin/python -m benchmarks.autonomous.generate /private/tmp/manufacturing-1000 --base /private/tmp/manufacturing-100 --count 1000 --seed 912
.venv/bin/python -m benchmarks.autonomous.run /private/tmp/manufacturing-1000 /private/tmp/manufacturing-results-1000 --questions microbiological --modes keyword_rules linked_rules --seconds 300
.venv/bin/python -m benchmarks.autonomous.generate /private/tmp/manufacturing-10000 --base /private/tmp/manufacturing-100 --count 10000 --seed 912
.venv/bin/python -m benchmarks.autonomous.run /private/tmp/manufacturing-10000 /private/tmp/manufacturing-results-10000 --questions microbiological --modes linked_rules --seconds 180

# Initial requested distribution, with its own randomly assigned format/layout.
.venv/bin/python -m benchmarks.autonomous.generate /private/tmp/manufacturing-independent-1000 --count 1000

# Actual inference, when credentials are funded/configured. Failures stay failed.
.venv/bin/python -m benchmarks.autonomous.run /private/tmp/manufacturing-100 /private/tmp/manufacturing-model-results --questions microbiological --modes bounded_agent full_rlm directory_rag --seconds 300

# A real directory and question: no scenario manifest or evaluator labels needed.
.venv/bin/python -m benchmarks.common.investigate_directory /path/to/authorized/raw-directory 'Investigate recurring bioreactor failures across these campaigns.' /private/tmp/investigation.json --mode full_rlm --seconds 300
```

`BIODEMO_PRIME_MODEL=provider/model` selects a configured Prime model; normal SDK
authentication applies. `directory_rag` uses the existing OpenAI baseline and
requires `OPENAI_API_KEY`; supply its model through the common configuration
interface if overriding the existing default. Do not put credentials in run
manifests. The executed provider returned HTTP 402; this is not a request to
charge a different account or change billing automatically.

For the standalone directory command, optional `--as-of` uses trusted filesystem
availability and conservatively withholds structured files containing future
availability rows. It does not rewrite genuine files. A source owner must supply
trustworthy historical document publication times; arbitrary mtimes are not a
general historical-access policy. The controlled benchmark uses explicit,
internally consistent source publication times and physically excludes future files.

Each `run.json` includes a retained workspace when requested. Use that path for
independent extraction checks:

```sh
.venv/bin/python -m benchmarks.autonomous.check_extraction /private/tmp/manufacturing-100 /path/from/retained_workspace /private/tmp/extraction-check.json
```

## IndPenSim

The official archive already exists locally and is hash-verified before projection.
If absent, retrieve the file URL in `benchmarks/cmo_ingestion/provenance/mendeley-v2.json`
from its official Mendeley landing page; never substitute a different dataset version.

```sh
cd backend
.venv/bin/python -m benchmarks.autonomous.indpensim project benchmarks/cmo_ingestion/raw/100_Batches_IndPenSim.zip /private/tmp/indpensim-historical
.venv/bin/python -m benchmarks.autonomous.indpensim investigate /private/tmp/indpensim-historical /private/tmp/indpensim-investigation
```

This preserves all rows of selected variables, not a reservoir sample. The screen
is deliberately descriptive; view its false positives/missed batches. The
simulator command, its isolated Python 3.11 environment and all paired failed
episodes are in [the feasibility document](indpensim_feasibility.md). No optimization
policy comparison is enabled after a failed gate.

## Demo and follow-up API

```sh
cd backend
.venv/bin/python -m benchmarks.autonomous.export_demo --results /private/tmp/manufacturing-results-100 /private/tmp/manufacturing-results-1000 /private/tmp/manufacturing-results-10000 /private/tmp/manufacturing-model-results --corpus /private/tmp/manufacturing-100 --output ../frontend/public/case-study-results --indpensim /private/tmp/indpensim-investigation/investigation.json --simulator /private/tmp/biodemo-indpensim-simulator-results/summary.json
cd ../frontend
npm run dev
```

Open `http://127.0.0.1:5180/case-studies`. The export contains summary comparisons
for all specified runs; original evidence drill-down is enabled for the corpus
whose hash matches `--corpus`. Export another corpus separately for its source
drill-down. Source bytes are verified against the frozen allowlist before publication.
Never serve `evaluator/` or a dataset root as static web content.

For real follow-up, start the **existing API** with the retained source store:

```sh
cd backend
BIODEMO_MANUFACTURING_STORE=/path/from/retained_workspace/state/store BIODEMO_MANUFACTURING_SCOPE=evaluation BIODEMO_ALLOWED_ORIGINS=http://127.0.0.1:5180 .venv/bin/python -m uvicorn benchmark.application.api:create_app --factory --host 127.0.0.1 --port 8000
```

The page uses `POST /api/manufacturing-os/rollouts`, the original objective,
historical cutoff, stable incident context and package fingerprint. An incorrect
store returns HTTP 409 before inference. Session state lives in the established
Prime/Blackboard workflow; no imitation chat response is generated. For another
API origin, set `NEXT_PUBLIC_BENCHMARK_API_URL` before starting/building Next.js.
The existing header identity adapter is for development; organizational deployment
must use the product's authenticated boundary, not expose a demo identity adapter.

## Verification

```sh
cd backend
.venv/bin/python -m pytest -q tests/test_new_benchmarks.py tests/test_prime_runtime.py tests/test_columnar_ingestion.py tests/test_cmo_ingestion.py tests/test_case_comparison.py tests/test_retrieval.py tests/test_autonomous_discovery.py tests/test_indpensim_simulator.py tests/test_pharma_cases.py
cd ../frontend
npm run lint
npm run build
```

See [results](results.md) for actual outcomes and the two pre-existing failures.
