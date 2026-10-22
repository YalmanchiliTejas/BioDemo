# Architecture decisions

## 2026-10-20: CMO ingestion benchmarks in the existing application

The reference is the 14-page `CMO Data Ingestion MVP — Build Spec.pdf`, read
from Downloads before coding. Preserve the existing `ingest_package` and
`ManufacturingStore`, FastAPI application, and React/Vite UI. No investigation
agent, RLM integration, or separate hosted product is introduced.

Explicit departures from the specification:

- Reuse SQLite plus immutable originals and Parquet, rather than introducing
  Postgres, MinIO, Redis/RQ, and a second storage pipeline. Mapping, review,
  versioned templates, and audit receipts are additions around that store.
  Background jobs currently use local threads; interrupted jobs are not resumed.
- Retain the existing Polars/Calamine CSV/Excel ingestion. Original-source
  verification and the cell viewer use openpyxl/CSV. Replacing this with pandas
  would discard the existing tested columnar implementation.
- D and the diagnostic baseline explicitly select the existing pypdf/Tesseract
  backend. OpenAI Decisions requires Docling and locally provisioned assets.
  Legacy A/B/C results are historical; those configurations cannot run now.
- Per the subsequent user decision, classification and mapping now use OpenAI Decisions,
  with named choices for document types and canonical header meanings. Jev and
  generative mapping were removed. Clairic uses the native Cloudflare Workers AI extraction
  API in the default clairic_decisions configuration. Unknown categories require
  human review. A local endpoint must implement the Decisions contract; local
  deterministic processing is retained. Offline contract tests do not establish
  live API access or benchmark quality.
- Local demonstration approvals record actor, reason, source hashes, and an
  append-only hash-chained audit. Corrections retain superseded versions. This
  is not the spec's SSO, role authorization, password reauthentication, or
  regulated electronic-signature implementation. Expose only on loopback or
  behind customer identity infrastructure. An optional API token protects the
  ingestion routes. No Part 11/Annex 11 compliance claim is made.
- PDF provenance evaluation scores physical page plus measurement identity;
  spreadsheets score exact row/header/cell. Docling page/box provenance is
  retained, but multi-page/unlocalized elements cannot be auto verified. OCR
  requires human source inspection. The MVP viewer opens original PDF pages
  and renders original PDF pages locally, highlighting Docling boxes when
  available. A PDF line citation without a box has no invented highlight.
- This evaluator covers the two public/synthetic benchmark families. The spec's
  separate customer cleaned-spreadsheet evaluation and metrics-only external
  reporting mode remain future work. Do not share raw benchmark report details
  as a customer metrics-only artifact.
- Human work is unmeasured until an actual study. Browser focus/activity
  heartbeats provide partial observed time, not a completed-work outcome;
  automated browser checks do not accrue human minutes.
- Raman units are not declared in the source CSV. Exports say `unspecified`,
  keep original channel values, and require unit review. Only three channels
  are sampled for the demonstration; the complete source archive is preserved.

The spec's numerical goals are targets. A failure to hit them is reported, not
removed through answer-key-dependent tuning. See the executed benchmark report
for measured coverage and the study protocol for remaining human work.

## 2026-10-21: Shared pharmaceutical case workspace

The new [weekend implementation brief](pharma_mvp/INSTRUCTIONS.md) supersedes the
old ingestion-only scope: integrate the existing investigation engine now, while
retaining factual extraction, immutable originals, source provenance, customer
scoping, review and versioned templates. Optional OCR/provider breadth is deferred.

Extend the existing SQLite/FastAPI/React application. Keep imported source data,
verified measurement snapshots, and findings/reviews distinct. Reuse approved
deterministic analysis first and the existing Prime SDK as the agent path; never
substitute a cached narrative for a live investigation. The checklist and gaps
are maintained in [the MVP README](pharma_mvp/README.md). Existing benchmark reports
remain historical results and do not describe this new case workflow.

The first shared-case slice uses `cmo.CaseService` tables in the existing CMO
SQLite database and reuses `IngestionService` for all three intake transports.
Analysis snapshots contain accepted values with original source hashes and
references. Existing `DeterministicAnalysis` computes actual statistics over
those snapshots; it does not infer causal root causes. The real Prime smoke
run encountered an HTTP 402 provider-balance error and did not produce a report.
Completing the autonomous case path is an explicit remaining gate. Folder/API
imports, job cancellation/restart, finding staleness, source ownership and
editable handoff are included now; multi-instance scheduling, verified identity,
DOCX and broader OCR remain bounded/deferred as documented in the MVP README.
