# Pharmaceutical manufacturing investigation MVP

Governing brief: [coding agent instructions](INSTRUCTIONS.md), copied from the
user-supplied file in Downloads. This is the current shared-workspace build;
its new scope supersedes the previous ingestion-only plan.

## Working first slice

Open `http://127.0.0.1:5180/?tab=cases`.

1. Create a project and case; state the manufacturing question.
2. Upload CSV, XLSX, native PDF, or a bounded ZIP; alternatively load the clearly
   labeled synthetic fermentation sample or configure a settled-file watch.
3. Open **Data review**. Inspect original cells/pages, confirm consequential
   mappings, correct or review measurements, and retain unresolved fields.
4. Open **Investigation**. Select a relevant reviewed variable and task starter.
   Run real approved calculations over a saved snapshot of accepted values.
5. Inspect stored-data trend charts, input lineage, original source citations,
   arithmetic, limitations, and missing-information requests.
6. Use **Review and handoff** to accept/reject/annotate a finding, record proposed
   actions and responsible roles, or export an editable Markdown handoff.
   CSV/XLSX exports of reviewed data are also available without investigation.

Analysis here is explicitly labeled **existing DeterministicAnalysis**: observed
batch/variable means, extrema, and last-minus-first differences where unique
source times exist. Timepoints are not independent biological replicates.
There is no causal confirmation, automatic release authorization, or unmeasured
claim of labor savings. No cached narrative is substituted for a live agent run.

## Startup

From the existing repository and Python environment:

```bash
.venv/bin/pip install -e '.[app,manufacturing-data]'
.venv/bin/python -m uvicorn benchmark.application.api:create_app --factory --host 127.0.0.1 --port 8000
```

In another terminal:

```bash
cd ui
npm ci
npm run dev
```

Use **one API process/worker** on macOS/Linux for this local slice. The process
controls use POSIX APIs; Windows has not been verified. Persistent SQLite migrations
are additive and applied at startup. The case tables share the existing
`CMO_INGESTION_ROOT` database; originals, package versions, calculations, and job
logs are under the same persistent directory. Keep that directory across restarts.
Docker is not needed. Existing deployment files are optional historical assets;
the new case worker/folder mount is not yet validated in a container deployment.

Administrator settings load from repository `.env.local`, without overwriting
shell variables:

```dotenv
# Defaults to .cache/cmo-ingestion; choose persistent customer storage.
CMO_INGESTION_ROOT=/absolute/path/to/persistent/storage
# Required for machine upload and any deployment beyond the loopback demo.
CMO_API_TOKEN=your-local-secret
# Optional: watched folders must be inside this administrator-controlled root.
PHARMA_WATCH_ROOT=/absolute/path/to/customer/drop-root
# Worker wall-time bound; default 180 seconds, maximum supported 600.
PHARMA_JOB_SECONDS=180
```

Restart after configuration changes. The case preparation/analysis slice makes
no model calls. Existing CMO Clairic/Decisions configurations remain available in
the ingestion work area; those cloud configurations transmit source content to
the configured providers. The case path currently uses native parsing and draft
aliases/confirmed templates. Irregular/OCR document coverage remains limited.

## Architecture and reuse

- Existing FastAPI application, React/Vite UI, SQLite, `ManufacturingStore`,
  original-source verification and CSV/openpyxl/PDF preview.
- Existing `cmo.IngestionService`: normalization, source-bound review, immutable
  revisions, versioned templates, changed-layout validation, and formula-safe export.
- Existing `DeterministicAnalysis`: actual arithmetic with source fingerprints;
  no generated code is executed in the main API process.
- New `cmo.CaseService` adds project/case, project-local package identity/version,
  durable jobs, immutable accepted-input snapshots, finding reviews and actions
  around the same ingestion pipeline. Imports under another filename reuse
  identical package content within the same project. Different customers do not
  share package identity or mapping scopes.
- File upload, authenticated package API, and folder transport all call
  `CaseService.import_bytes`. Watch checkpoints record source filename, size,
  modification version, settling time and resulting job; restart/retry is idempotent.
- Fixed ingestion/calculation jobs run in separate processes with CPU, file-size,
  wall-time limits and a per-job process lock. Jobs persist stages and failures;
  cancellation terminates the worker process group. A service restart fences old
  leases, marks work interrupted, and requires explicit retry (maximum three
  attempts). This is a single-instance local scheduler, not a distributed queue.
- Corrections/review changes mark dependent results stale by snapshot revision.
  Earlier finding inputs and reviews remain saved. Stale findings cannot receive
  a fresh acceptance and are marked in handoff exports.
- Proposed actions advance through reviewed → in progress → outcome recorded,
  with actor/time/reason history. No action sends a request or writes externally.

Raw values, normalized values, source references and review status remain
separate. Only accepted/auto-accepted/corrected values enter calculations; pending
values and open issues are listed as excluded/gaps. Conflicting or repeated
batch/time/variable records across packages are excluded from calculation until
resolved in Data review; they are never silently averaged as independent samples. An actual excursion can be
recorded as a reasoned correction with a range warning; unusual values are not
automatically called parsing errors. Arithmetic validity is separate from
scientific validity, factual source review and a causal conclusion.

## API and connector contract

The existing development identity adapter supplies `X-Tenant-Id` and
`X-Actor-Id`. A configured `CMO_API_TOKEN` additionally requires `X-CMO-Token`.
These identity headers must come from a trusted authenticated boundary in a
customer deployment. The loopback demo is not production authentication or a
validated electronic-signature system. Do not expose it to customer networks
without that boundary. Projects, jobs, source previews, review and exports enforce
the selected tenant context; case-owned CMO run routes also enforce ownership.

```bash
curl -sS -X POST http://127.0.0.1:8000/api/pharma/projects \
  -H "X-CMO-Token: $CMO_API_TOKEN" -H 'X-Tenant-Id: pilot-customer' \
  -H 'Content-Type: application/json' -d '{"name":"Fermentation review"}'

curl -sS -X POST http://127.0.0.1:8000/api/pharma/projects/PROJECT_ID/cases \
  -H "X-CMO-Token: $CMO_API_TOKEN" -H 'X-Tenant-Id: pilot-customer' \
  -H 'Content-Type: application/json' \
  -d '{"title":"Yield change","problem":"Compare reviewed product observations and identify missing context."}'

curl -sS -X POST 'http://127.0.0.1:8000/api/pharma/package-upload/CASE_ID?filename=export.zip' \
  -H "X-CMO-Token: $CMO_API_TOKEN" -H 'X-Tenant-Id: pilot-customer' \
  -H 'Content-Type: application/zip' --data-binary @export.zip
```

Machine upload always requires a configured token. `POST /cases/{id}/files` is
the equivalent web transport; both return `job_id`, `package_id`, `version` and
`duplicate`. Poll `GET /jobs/{id}`; cancel or retry with corresponding POST routes.
The source adapter boundary is receipt → bounded fetch → project-local content
identity/version → persisted import job → status/error. A folder adds a discovery
checkpoint and settling delay. ZIPs reject traversal, symlinks, encryption, duplicate
paths, nested archives, executables and excessive expansion; uploads are capped
at 64 MiB, expanded ZIPs at 128 MiB and 500 members.

Configure a folder with `POST /cases/{id}/watches` using
`{"path":"/allowed/drop","settle_seconds":10}` and an administrator/supervisor
identity. The server rejects folders outside `PHARMA_WATCH_ROOT`. Ordinary users
can inspect watch status/errors in Overview without setting up model providers.
These are file transports, not native SAP/MES/QMS/historian integrations.

## Actual verification

[Milestone verification and failures](../../results/pharma_mvp/VERIFICATION.md):
133 regression tests and 21 Node tests passed; the later 15-test case suite
also verified actual child-process cancellation. The UI build and browser check passed.
The four socket-bound tests initially blocked by the sandbox passed on the
permitted rerun. This is the first slice, not completion of all remaining gates.

```bash
.venv/bin/python -m pytest -q tests/test_pharma_cases.py tests/test_application.py \
  tests/test_cmo_ingestion.py tests/test_cmo_openai.py \
  tests/test_manufacturing_data.py tests/test_new_benchmarks.py

# API must already be running. Creates only independent synthetic fixture cases.
.venv/bin/python -m scripts.check_pharma_vertical_slice --output runs/pharma-check-001

# Optional installed Playwright; use the JSON path from the preceding check.
CMO_PLAYWRIGHT_MODULE=/path/to/playwright node ../frontend/scripts/check_pharma_workspace.cjs \
  runs/pharma-check-001/result.json

cd ui
npm run build
```

The [executed vertical-slice artifact](../../results/pharma_mvp/vertical-slice-001/result.json)
records a real local API/worker run: 12 CSV-source checks, a renamed duplicate
reused, 12 returning values auto-accepted with zero model calls after **explicitly
labeled automated study-template confirmation**, four descriptive findings,
a finding annotation, proposed MSAT action and editable handoff. Wall time was
6.53 seconds on this machine. This is an automated fixture protocol, not actual
human review or a completed fresh-user study. The browser confirmed saved-case
recovery, the study-template label, four charts from stored inputs, a successful
original-source citation and handoff/actions without page errors.

The [saved handoff](../../results/pharma_mvp/vertical-slice-001/handoff.md) and
[browser receipt](../../results/pharma_mvp/vertical-slice-001/browser.json) are
actual artifacts. No generator answer keys are available to runtime retrieval or
analysis. Existing CHO/Fresenius regression coverage is retained.

## Existing Prime engine: actual blocker

The real existing `PrimeManufacturingHarness` was executed against a separate,
tiny invented package with a 120-second/12-tool-call bound. Its configured
`prime-inference/z-ai/glm-5.3` endpoint returned **402 insufficient balance**.
The run timed out without a validated report; no agent findings were claimed.
The SDK host has been changed to treat payment errors as fatal in product runs
as well as evaluations. The follow-up native run failed explicitly after 8.53
seconds instead of timing out, with no report claimed.

Reproduce only after provisioning the approved existing provider:

```bash
.venv/bin/python -m scripts.smoke_pharma_engine --output runs/pharma-engine-check-001 --seconds 120
```

Keep private provider/session logs local. There is no new model-provider adapter
or hidden fallback from a failed agent to a synthetic report. The deterministic
path is visibly selected and scientifically limited. A successful Prime report,
case-scoped agent integration with strict token/tool budgets and restricted
execution, and broader competing-explanation synthesis remain Day 2 work.

## Checklist and remaining gates

- [x] Read brief, inspect repository and preserve unrelated dirty changes.
- [x] Run actual bounded existing engine; record provider failure and logs.
- [x] Shared durable projects/cases, scoped intake, original versions and data review.
- [x] Real intake → reviewed data → approved calculation → finding review → export.
- [x] Idempotent uploads, changed-content versions, settled-file transport/checkpoints.
- [x] Bounded separate worker, cancellation, explicit restart recovery and retries.
- [x] Immutable input snapshots, source citations, corrections marking findings stale.
- [x] Review history, proposed actions, editable handoff, source-linked CSV/XLSX.
- [x] Four work areas; persisted-data charts; browser and source-link verification.
- [x] Tests for arithmetic, source ownership, revisions, ZIPs and folder checkpointing.
- [ ] Complete a successful Prime case and connect broader agent findings to this workspace.
- [ ] Verify strict agent token budgets, generated-code isolation and safe partial report recovery.
- [ ] Broader irregular-document and mapping accuracy beyond the bounded native layouts.
- [ ] Actual fresh-user installation and timed preparation/review/handoff studies.
- [ ] Full intervention follow-up comparisons; DOCX and native enterprise connectors deferred.

No regulatory validation, production readiness, causal efficacy, human productivity
improvement, or superiority over named vendors is established by these fixtures.
