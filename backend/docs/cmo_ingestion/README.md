# IndPenSim + Sanofi ingestion demonstration

This extends the existing FastAPI/React application and manufacturing data
store. The workflow is Ingest → Classify → Parse → Map → Validate → Review →
Store/Export. No investigation/RLM is run. See [architecture decisions](../DECISIONS.md)
for differences from the uploaded build specification.

## Run locally

From the backend project root (`cd backend`), with Python 3.12+ and Tesseract installed:

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[app,manufacturing-data,benchmarks]'
mkdir -p benchmarks/cmo_ingestion/raw
curl -fLsS 'https://data.mendeley.com/public-files/datasets/pdnjz7zz5x/files/e7007dff-4061-494f-a9f5-16c20f457d1d/file_downloaded' -o benchmarks/cmo_ingestion/raw/100_Batches_IndPenSim.zip
.venv/bin/python -m benchmarks.cmo_ingestion.generate
.venv/bin/python -m benchmarks.cmo_ingestion.evaluate --output results/cmo_ingestion --calibration-protocol --configurations D preview
.venv/bin/python -m uvicorn benchmark.application.api:create_app --factory --host 127.0.0.1 --port 8000
```

In a second terminal:

```bash
cd ../frontend
npm ci
npm run dev
```

Start the API with `BIODEMO_ALLOWED_ORIGINS=http://127.0.0.1:5180` and open
<http://127.0.0.1:5180/cmo/> (**CMO deliveries**). In development the page calls
the API on port 8000; in production nginx proxies `/api/` on the same origin.
See the [tester guide](TESTER_GUIDE.md) and [Supabase hosting](../../deploy/supabase/README.md).
The retired Vite `?tab=ingestion` screen described below no longer exists. Generated packages and result directories must be fresh: the
generator/evaluator refuse to overwrite previous runs. For subsequent runs use
`--output /path/to/fresh-directory` and set `CMO_PACKAGES_ROOT` or
`CMO_REPORT_PATH` as needed. The UI never imports answer keys or static scores.

Suggested demonstration: select **calibration**, run Diagnostic, inspect source
cells/pages, supply reviewer and reason, confirm each mapping. Select
**returning** and configuration **D** to see deterministic template reuse with
zero model calls. Clairic + OpenAI Decisions is selected by default; only run it after configuring
the key and parser assets. Select **changed** to inspect missing fields, renamed columns,
conflicting duplicates, identifier errors, and missing pages. Unseen uses a
different form and has no confirmed template. Confirming a template does not
retroactively accept values from the previous run.

Uploads accept ZIPs with supported document/spreadsheet types, up to 64 MiB
compressed, 128 MiB expanded and 500 entries. Unsafe paths and executable types
are rejected. User uploads are never implicitly approved for hosted inference.
Originals are immutable by hash. Source previews recheck original hashes.
PDF pages render locally as images, with Docling bounding boxes highlighted
when present; spreadsheet previews highlight the exact source field. Reviewers
can correct values, units, parameters, batch IDs and elapsed process hours.

## Datasets, licensing and truth

- [IndPenSim v2, DOI 10.17632/pdnjz7zz5x.2](https://data.mendeley.com/datasets/pdnjz7zz5x/2),
  Stephen Goldrick, CC BY 4.0. Attribute Goldrick et al. (2015), *The development
  of an industrial-scale fed-batch fermentation simulation*, and Goldrick et al.
  (2019), *Modern day control challenges for industrial-scale fermentation
  processes*. This is simulated fermentation, not patient or actual plant data.
  The publisher archive is 503,792,426 bytes, SHA-256
  `bc434c6cf96444fee3c915d434ac84e2a9c6492be4daebcfa4aed9cdff181f00`.
- The complete original archive is retained. Generation scans all 100 batches;
  default seeded reservoir sampling retains four timepoints per batch and 14
  fields, including three of the available Raman channels. Original decimal
  strings, physical CSV row/column, batch and elapsed hours are retained in
  `generated/reference/indpensim.json`. No calendar timestamps are invented.
  The CSV's PAT header has two unquoted commas. An exact, checked header-only
  repair aligns names with data; numerical rows are never changed.
- Source Raman units are undeclared. They remain `unspecified` and require
  review. No physical spectroscopy unit is invented. Derived layouts explicitly
  record Celsius/feed unit conversions, decimal commas, aliases, reordered
  headers, missing values, and artificial conflicts. Injected values are marked
  as perturbations in the independent key, not original IndPenSim measurements.
- [FDA Sanofi warning letter, January 15, 2025, MARCS-CMS 690604](https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/warning-letters/sanofi-690604-01152025)
  grounds contamination, high-pressure/leakage, equipment-suitability, and
  deficient-investigation themes. `generated/reference/sanofi-public-facts.json`
  records section references. All operational identifiers, measurements and
  relationships are invented. Every generated document has a synthetic
  disclosure. These are not internal Sanofi records or a reconstruction of
  undisclosed numerical facts.
- Sanofi forms include batch, environmental monitoring, microbiology, CoA,
  maintenance, deviation, investigation PDFs and bioreactor exports. Microbiology
  is a raster-only, rotated PDF. Layout B uses different headers, separators,
  units and CSV instead of Excel. These are deliberately bounded form families,
  not representative coverage of all manufacturing systems.
- Public-source snapshots are in `benchmarks/cmo_ingestion/provenance/`.
  Transformed packages are adaptations without source-author endorsement.
  CC BY license: <https://creativecommons.org/licenses/by/4.0/>.

Packages split source batches modulo four across calibration, returning,
unseen and changed, spreading each control regime across conditions. Calibration
and evaluation batches are disjoint. Truth lives in each package's
`evaluation/answer_key.json`, outside `raw/`. It includes expected fields,
locations, original-source pointers, relationships, transformations, and defects.
The pipeline cannot import the benchmark generator or evaluator. Evaluation
completes all extraction before opening any keys and checks input/code hashes.
Never edit mappings or extraction rules based on held-out key failures.

CSV/PDF content and XLSX timestamps/ZIP metadata are deterministic on the same
dependency/platform versions. Raster fonts and OCR results can differ across
platforms. Record dependency versions when reproducing a result.

## Clairic + OpenAI Decisions configuration

The default configuration is **clairic_decisions**: Docling parses documents,
Cloudflare Clairic extracts structured fields from unfamiliar document layouts, and OpenAI
Decisions classifies unfamiliar document types and maps source headers onto the
public vocabulary. Native CSV/Excel extraction remains deterministic. Jev, GLM,
Chat Completions and Responses are not called. The optional **decisions** baseline
uses native structured extraction without Clairic. Historical A/B/C configurations remain labeled in previous reports
and are unavailable for new runs. D and Diagnostic remain local and deterministic.

Settings load automatically from repository `.env.local`, with shell values taking
precedence. Fill `OPENAI_API_KEY`, `CLOUDFLARE_ACCOUNT_ID`, and `CLOUDFLARE_AUTH_TOKEN`.
Include `https://api.cloudflare.com` and `https://api.openai.com` in
`CMO_ALLOWED_ORIGINS`. Restart the API/evaluator after
changes. See [configuration example](../../deploy/cmo-ingestion/.env.example).

```dotenv
OPENAI_API_KEY=your-key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-6-luna
CMO_DECISIONS_URL=https://api.openai.com/v1/decisions
CMO_DECISIONS_MIN_CONFIDENCE=0.95
CMO_DECISIONS_INPUT_USD_PER_MILLION=0.10
CMO_ALLOWED_ORIGINS=https://api.openai.com,https://api.cloudflare.com
CLOUDFLARE_ACCOUNT_ID=your-account-id
CLOUDFLARE_AUTH_TOKEN=your-cloudflare-token
```

The adapter sends `model`, shared `input`, and named choice `questions` to
`POST /v1/decisions`, in groups of at most 100. It validates answer names, choices
and confidence locally. Unknown fields, refusals, low confidence and ambiguous
identifier columns require review. Confidence is a routing signal, not measured
value accuracy. This API chooses among supplied categories; it cannot invent new
schema fields or extract arbitrary prose. Source parsing uses Docling/native readers; Clairic extraction cites parsed evidence IDs and always requires source review.
Full decisions and confidence are available in each layout and local audit.
Confirmed structural templates bypass classification and mapping calls.

[Official API contract](https://developers.openai.com/api/reference/resources/decisions/methods/create).
Usage receipts record actual tokens and request duration. Costs use the configured
input rate, exclude cached reads, and include no output charge. They are estimates
before account/region modifiers; absent rates or usage produce unknown cost.
Live service access and model quality have not been verified by the offline tests.
Previous report scores do not describe this new configuration.

`CMO_ALLOWED_ORIGINS` is an explicit origin allowlist; redirects are refused.
Hosted inference requires synthetic or explicitly approved data. User uploads and
original IndPenSim records are not implicitly approved. An approved invocation can
use `IngestionService.run(..., approved=True)`. A customer-controlled endpoint may
use `CMO_DECISIONS_URL` only if it implements this same Decisions contract; generic
vLLM/Ollama Chat Completions endpoints are not compatible. Local D/Diagnostic
parsing and template reuse continue without hosted inference.

### Native Cloudflare Clairic extraction

The adapter posts directly to
`https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/ai/run/@cf/cloudflare/clairic`
with bearer `CLOUDFLARE_AUTH_TOKEN`, `model: "clairic"`, source text in `state`,
and typed `fields`. No bridge, custom URL, or model configuration is required.
`CMO_CLAIRIC_URL`, `CMO_CLAIRIC_MODEL`, `CMO_CLAIRIC_KEY`, and output pricing are
legacy settings and are ignored.

[Cloudflare model contract](https://developers.cloudflare.com/workers-ai/models/clairic/).
The revised `cmo-clairic-scalar-2` adapter splits repeated batch/lot records into
small contexts and asks for independent, meaningful scalar fields: batch ID,
process-hour number and its literal text, measurement label, measurement number,
and its literal text. This follows the named typed-field approach in
[Cloudflare's extraction example](https://blog.cloudflare.com/clairic-extraction-model?ref=explainx).
It does not ask the model to align lists or reproduce character-offset filters.
Requests use no estimates, forecasts, computed measurements or guessed units.

Each text value must match its returned span in the original record. Context
positions are retained relative to the original Docling source element. Typed
numbers are compared with the literal source number, including decimal commas.
A clipped measurement label can be expanded only to its literally adjacent,
printed bracketed unit; the raw response and confidence remain unchanged and
this adjustment is flagged for review. Scalar records containing multiple
measurements are explicitly flagged as incomplete coverage.

Null stays missing; `guess` is never promoted to a measurement. Invalid label or
value spans cannot produce candidates. Low confidence, uncertain presence,
missing batch/time and conflicting typed numbers produce per-record review
items. Source-backed candidates remain visible and pending. A failed record no
longer discards the other records in a document. Every model-derived measurement
still requires original-source inspection even when confidence exceeds 0.95.
The UI shows retained review answers, confidence and source spans; saved runs can
be opened with `?tab=ingestion&run=RUN_ID`.

Clairic usage and complete responses are audited locally. Optional
`CMO_CLAIRIC_INPUT_USD_PER_MILLION=0.10` enables input-only cost estimates.
Blank rates mean unknown cost; missing usage is never invented. Native Cloudflare
access was executed on synthetic records. Independent development results are
in `results/cmo_ingestion/development/`; package replays are debugging results,
not fresh held-out accuracy estimates. No evaluation keys were used to tune this
change. Confirmed printable forms skip extraction calls only when native parsing
reproduces the confirmed structure. Unknown record boundaries, missing identifiers,
unstructured tables, OCR corruption, and multiple measurements in a record still
require review. There is no demonstrated reduction in completed human minutes yet.

Install Docling and provision its local weights **before** processing documents:

```bash
.venv/bin/pip install -e '.[manufacturing-documents]'
HF_HOME=/private/tmp/cmo-docling-hf .venv/bin/docling-tools models download layout tableformer --output-dir .cache/cmo-docling-models
```

Set `DOCLING_ARTIFACTS_PATH` in `.env.local` to that directory's absolute path.
Parsing disables Hugging Face downloads/telemetry, remote services, and uses the
local Tesseract CLI for Docling OCR. Decisions requires the API key and these assets. D and Diagnostic use the existing
native pypdf/Tesseract and spreadsheet parsers; Diagnostic is not configuration A.

## Evaluation and human work

For a new Decisions evaluation use a fresh output directory and
`--configurations clairic_decisions decisions D preview`. This executes paid API requests on eligible
packages; offline tests use intercepted transport and are not benchmark results.

`results/cmo_ingestion/report.json` and `.md` contain executed results, including
unavailable configurations. The UI reads that report via the API. Results are
separate per dataset, configuration and condition, with extraction recall,
value/unit accuracy, provenance, classification, mapping, relationship recall,
defect detection, auto acceptance and incorrect auto acceptance, review counts,
runtime, model calls/tokens and inference cost. Null denominators remain null.
See [measured outcomes and failures](RESULTS.md) for an interpretation of the
executed run and the unfulfilled targets.

The `--calibration-protocol` flag confirms public-vocabulary draft mappings on
disjoint calibration inputs using an **automated study fixture**, recorded as
such. It does not manufacture human confirmations or human-time measurements.
Unseen starts with an empty template store. All configurations see the same
held-out raw bytes; unavailable backends get no numerical scores.

Human minutes are null until real interaction. Partial visible/focused activity
is logged using server time; automated browser runs do not accrue human time.
No completed-work or time-savings claim follows from that partial timer. Follow
the [human study protocol](HUMAN_STUDY.md) to measure total work and the manual
baseline. The initial targets are not promised outcomes. No equivalent Invert
comparison has been performed.

## Verified downstream interface

`GET /api/cmo-ingestion/runs/{id}/verified` returns schema `verified-cmo-1` only
when package review is complete, with normalized values, immutable provenance,
review status, and batch-evidence relationships. Otherwise it returns 409.
This is the future investigation-system integration boundary; no investigation
is automatically launched. CSV long/wide and Excel exports contain accepted
subsets with source references. The UI and `X-Package-Complete` header make
partial exports explicit. Wide export refuses conflicting accepted values.

## Checks and deployment

```bash
.venv/bin/python -m pytest -q tests/test_cmo_ingestion.py tests/test_manufacturing_data.py tests/test_columnar_ingestion.py tests/test_source_review.py tests/test_new_benchmarks.py tests/test_ui_benchmark_export.py
cd ui
npm run build
```

`frontend/scripts/check_cmo_ingestion.cjs` exercises the live UI with Playwright. Run
from the backend project root against a temporary, isolated API review store, with
Playwright available in Node's module path (or set `CMO_PLAYWRIGHT_MODULE` to its
installed module path). It records its actions as automated verification and
does not accrue human minutes. Screenshots are under `results/cmo_ingestion/ui/`.

The repository's original application remains the API entrypoint. A Compose
recipe builds the existing React UI and API:

```bash
docker compose -f deploy/cmo-ingestion/compose.yml up --build
```

Generate packages/reports first. UI: <http://127.0.0.1:8080/?tab=ingestion>.
The default Compose runtime network is internal, with no external egress; host
model endpoints therefore require customer-specific network setup or a model
service on that internal network. Models are provisioned separately, mounted
read-only. Use `CMO_API_TOKEN` for ingestion API access. Put TLS, SSO and role
authorization at a customer-controlled gateway before any nonlocal deployment;
use encrypted storage volumes and retain backups of immutable sources/audit.
This recipe is a local demo, not a validated regulated production deployment.

Current limitations: native form parser coverage is narrow; OCR can omit/misread
fields; missing whole records cannot be inferred without a delivery schedule;
CoA printed-spec interpretation and complete equipment/event semantics are not
implemented; optional real backend results require configuration; PDF box
highlighting, durable distributed jobs, native Bedrock/Azure adapters, regulated
signatures, and customer-only aggregate evaluation remain unimplemented.
