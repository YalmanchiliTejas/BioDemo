# Implementation plan, 2026-10-20

Inspected the 14-page `CMO Data Ingestion MVP — Build Spec.pdf` in Downloads,
`src/manufacturing_data`, the existing benchmark evaluators, FastAPI application,
and React UI before implementing. Original files, SHA-256 addressing, columnar
spreadsheet ingestion, scope filtering, OCR fallback, and source verification are
reusable. Confirmed mappings, ingestion review, and the requested evaluation
conditions are gaps. Existing investigation/RLM code is outside this task.

1. Acquire IndPenSim v2; verify publisher SHA-256; freeze source strings and
   coordinates; reproducibly generate held-out CSV/XLSX/PDF layouts.
2. Snapshot the FDA letter; record public facts separately; generate explicitly
   synthetic Sanofi-inspired packages and evaluator-only keys.
3. Add mapping/templates, validation, review, export, and optional inference
   adapters on top of the existing ingestion store. Preserve local-only defaults.
4. Score identical held-out packages after extraction; report unavailable
   configurations, actual runtime/usage, failures, and unmeasured human time.
5. Extend the existing React/FastAPI UI; run regression and browser checks;
   document reproduction, provenance, deployment, and limitations.

No evaluation key is an input to ingestion or template proposal. Calibration
templates used by automated tests are explicitly labeled protocol fixtures and
are not human confirmations or human-time evidence.
