# Life sciences platform code inventory

Read-only inventory of code present in this checkout. References are repository
paths and line numbers; tests are listed as evidence of intended coverage and
were not run. “Implemented” means a concrete primitive exists, not that it is
deployed, connected to a customer's systems, or validated for regulated use.

## Repository and runtime shape

- The repository describes a Python backend and React/Vite frontend; the README
  runs them separately and names local backend/frontend startup paths
  (`README.md:1-26`). Python is 3.11+; cloud, manufacturing-data, and app
  dependencies are optional extras (`backend/pyproject.toml:1-22,48-55`).
- Backend tests live under `backend/tests`; frontend scripts are targeted
  presentation/model checks (`backend/pyproject.toml`, `backend/tests/`,
  `frontend/package.json:1-16`). Tests were not executed for this inventory.
- Product direction is broad and explicitly calls for source traceability,
  authorization, human approval for consequential actions, and interoperability
  (`Main_Culture_andETHOS.md:1-20,31-87`). Findings below distinguish capabilities
  from integration/deployment evidence.

## Capability map

| Area | Code-evidenced primitives | Boundary / gap visible in code |
|---|---|---|
| Ingestion and lineage | Folder/ZIP ingestion, checksums, pipeline version, per-file extraction routes/fallback records, preserved source refs, SQLite metadata plus Parquet/Arrow and DuckDB query layer (`backend/src/manufacturing_data/README.md:18-41,52-89`; `backend/src/manufacturing_data/ingest.py:26-44,47-82`). | Supported input formats and optional OCR/model runtimes are bounded; OCR/VLM statements remain unverified pending source review (`README.md:25-41`). No evidence here of live MES/LIMS ingestion in this path. |
| Normalization and scientific analysis | Canonical terminology matching; unit normalization tool; deterministic stats, source-clock alignment, numerical checks, hashes and source/partition lineage (`backend/src/manufacturing_data/terminology.py:15-37`; `tools.py:55-64`; `analysis.py:1-4,43-53`). | Analysis explicitly establishes arithmetic/provenance, not biological causation (`analysis.py:1-4`). Entity/schema mappings are candidates pending corroboration (`manufacturing_data/README.md:84-90`). |
| Evidence and review | Evidence IDs resolve to source rows/cells/pages/regions; scope and `as_of` cutoffs constrain tools; verification distinguishes matched values from claim meaning and marks interpretations for human review (`models.py:9-35`; `tools.py:65-96`; `backend/src/workflows/report_verification.py:93-108,145-159`). | Automatic checks do not establish causal/scientific correctness; unresolved or visual source checks can remain human-review-pending (`report_verification.py:93-108,152-159`). |
| Prime runtime and persistent session | Prime SDK host, scoped bridge, session files, continuation by prior session file, file locks, checkpoints, tool/model logs and usage telemetry (`backend/src/prime_runtime/harness.py:27-44,66-120,134-160,195-209`; `sdk_runner.mjs:68-88`). | Persistence is local to configured runtime storage; measured usage excludes child sessions and may miss calls (`harness.py:204-209`; `telemetry.py:6-39`). Cloud worker invokes the harness, but this is not evidence of a hosted multi-user Prime service (`backend/src/cloud_backend/agent.py:17-58`). |
| Workflows and proposals | Investigation workflow, explicit coverage/review queue, deterministic report validation, task/evidence proposals and review states (`backend/src/workflows/manufacturing.py:32-57`; `coordination.py:64-120`; `proposals.py:12-48`). | Proposals are not approvals or executions; policy and action control live in separate application layer. |
| Review, approval, audit | Risk policy assigns roles; self-approval is blocked; approval and execution are separate transitions; audit records are append-only at application layer (`backend/benchmark/application/control.py:46-60,63-129`; `postgres.py:34-90`). | Production connector execution requires configured write connector and prior approved proposal (`execution.py:44-75,78-90`). Demo writer emits a synthetic acknowledgement (`execution.py:18-41`). |
| Connectors | JSONL replay, in-process webhook inbox, generic cursor-based REST pull/write; connector catalog lists MES/eBR, PAT, LIMS, CDS, QMS, SCADA, historian, CMMS, ERP, WMS and ELN (`backend/benchmark/integration/connectors.py:13-55,57-100`; `catalog.py:11-22`). | REST is a generic configured API adapter, not vendor-specific validated integration. Webhook inbox is explicitly in-process; production HTTP handlers are described as future enqueue callers (`connectors.py:37-48`). Actual credentials, endpoints, schemas and customer access are deployment config/unknown. |
| Cloud jobs, auth, audit | FastAPI job API; verified OIDC RS256/JWKS claims, tenant/project roles; asynchronous queued job schema, object encryption, audit, dispatcher and Docker worker isolation (`backend/src/cloud_backend/api.py:34-44,47-85,123-150`; `auth.py:20-46`; `schema.sql:1-24`; `runtime_roles.sql:1-18`). | Cloud API explicitly excludes demo routes (`api.py:1`). Schema has tenant/project columns and DB grants; no PostgreSQL RLS policy appears in `schema.sql` or `runtime_roles.sql`. Deployment security/validation docs are not proof of a deployed environment. |
| Browser experience and local simulation | React workspaces save versioned user work to browser `localStorage`, with recovery/export behavior (`frontend/src/os/WorkspaceProvider.tsx:23-38,50-85`); lab scenario is labeled invented fixture (`frontend/src/lab/scenario.ts:1-8`). | Lab sidebar says assistant activity is scripted and production would use FastAPI/Prime (`frontend/src/lab/chrome.tsx:65-72`). Browser state is local demo state, not a shared backend system of record. |
| Batch, recipe, lab, sample, instrument | Synthetic pharma simulation includes batch/process/lab sample timelines and deterministic consistency checks (`backend/benchmark/pharma_simulation/validation.py:28-44,66-94`; `simulation_config.yaml:1-18,88-113`). Ingestion entity taxonomy includes batch, run, equipment, sample, site and event (`models.py:6-7`). | Simulation data is benchmark material; the frontend fixture expressly labels values and connector responses invented (`frontend/src/lab/scenario.ts:1-2`). No code evidence in reviewed paths of actual equipment control, validated recipe execution, or live instrument/LIMS connectivity. |
| Multisite and collaboration | Domain access context carries tenant, actor, site IDs, roles, clearances; proposals carry site and are checked against access scope (`backend/benchmark/knowledge/domain.py:25-40`; `control.py:68-72,87-99`). Cloud identity is tenant/project scoped (`cloud_backend/auth.py:9-17,29-45`). | This supports scoped data/action primitives, not evidence of operational cross-site partnership features, federation, or customer organizations. |
| Notifications and model routing | Connector runner supports repeated polling; model/provider selection is configured through Prime environment/model registry (`backend/benchmark/integration/runner.py:14-44`; `sdk_runner.mjs:68-88`). | No production notification service (email/SMS/chat) identified in reviewed code; in-app scripted toast/UI behavior is not external notification delivery (`frontend/src/lab/chrome.tsx:32`). Provider routing is Prime configuration, not evidence of policy-based multi-model routing or availability/failover strategy. |

## Tests present (not run)

- Ingestion and data: `backend/tests/test_manufacturing_data.py`,
  `test_columnar_ingestion.py`, `test_source_review.py`,
  `test_deterministic_analysis.py`, `test_retrieval.py`.
- Prime, persistent sessions and review: `test_prime_runtime.py`,
  `test_prime_provider_config.mjs`, `test_investigation_review.py`,
  `test_investigation_lifecycle.mjs`, `test_source_review.py`.
- Cloud and access boundaries: `backend/tests/cloud/test_security_backend.py`,
  `test_dispatcher.py`, `test_docker_isolation.py`.
- Connectors, workflow and manufacturing domain: `test_digital_thread.py`,
  `test_pharma_cases.py`, `test_cmo_ingestion.py`, `test_case_comparison.py`,
  `test_integration.py`, `test_investigation_review.py`.
- Frontend has model/presentation scripts, including
  `frontend/scripts/test_workspace_model.cjs` and
  `frontend/scripts/test_presentation.mjs`; presence does not establish
  production behavior.

## Additional implementation detail

### Data preparation and scientific evidence

The manufacturing store exposes tool calls for inspection, schema inference,
entity reconciliation, normalization, SQL-like tabular querying, lexical or
semantic evidence search, source verification, page/region extraction, process
context and historical state (`backend/src/manufacturing_data/README.md:84-90`).
The tool layer applies session-level scope and historical cutoff again at call
time; callers cannot widen scopes or advance an established cutoff
(`backend/src/manufacturing_data/tools.py:65-96`).

Structured observations retain source IDs and coordinates, while source and
partition hashes are attached to deterministic analysis results
(`backend/src/manufacturing_data/README.md:59-73`; `analysis.py:48-53,78-88`).
The analysis implementation records observed-timepoint basis and flags source
clock issues, so computed summaries need not be mistaken for independent
replicates (`analysis.py:72-89`).

### Durable workflows and system boundaries

Investigation state is stored as scoped SQLite cases and an appendable update
ledger (`backend/src/workflows/manufacturing.py:27-57`). The Prime system prompt
forbids the model from approving or executing disposition, release, CAPA,
external notification or manufacturing changes, and treats those boundaries as
distinct from investigation completion (`backend/src/prime_runtime/system_prompt.md:4-12`).

The cloud service accepts bounded job metadata, not source document uploads;
its middleware limits POST bodies and avoids logging request content
(`backend/src/cloud_backend/api.py:47-71`). The job schema uses idempotency keys,
attempt/fencing fields and result object versions (`backend/src/cloud_backend/schema.sql:2-12`).
The dispatcher and worker files show queue dispatch and an isolated Docker
execution path (`backend/src/cloud_backend/dispatcher.py:60-99`; `backend/src/cloud_backend/agent.py:17-58`).

### Frontend scope

The demo workspace model contains work items, notes and proposed action status
transitions, with import/export support in its browser shell
(`frontend/src/os/workspace-model.ts`; `frontend/src/os/WorkspaceShell.tsx:240-260`).
The provider stamps a demo actor label and writes state to browser storage
(`frontend/src/os/WorkspaceProvider.tsx:87-105`). This is useful interaction
scaffolding but does not establish authenticated identities or server-side
collaboration.

The lab review interface contains sample review progression and evidence views;
the lab state is persisted in browser storage and falls back to session-only
behavior on storage errors (`frontend/src/lab/state.tsx:85-107`). Scenario data
is explicitly synthetic (`frontend/src/lab/scenario.ts:1-2`). The user-facing
prototype describes external sending as absent for its site request interaction
(`frontend/src/lab/evidence.tsx:160-170`).

## Integration and deployment confidence limits

The source tree includes config-driven REST connectors and a connector catalog,
but no inspected connector implementation identifies a named customer tenant,
live service URL, field mapping or production secret. Thus “connector exists”
means generic integration code can be configured, not that an integration is
operational (`backend/benchmark/integration/connectors.py:57-109`; `catalog.py:11-22`).

Likewise, cloud code includes deployable-shaped API, database, object storage and
worker components. Whether they are currently deployed, monitored, backed up,
tested under a specific customer's identity provider or validated for use in a
regulated production environment is unknown from code presence alone. The
included code and tests do not constitute a compliance claim.

The checked cloud SQL schema declares ordinary tenant/project columns and
restricted runtime grants. The inspected files do not declare PostgreSQL row
level security policies; application authorization and store queries provide
the visible enforcement path (`backend/src/cloud_backend/schema.sql:2-24`;
`runtime_roles.sql:11-18`; `backend/src/cloud_backend/api.py:74-88`).

## Summary for architecture planning

The repository contains substantial local primitives for messy-file ingestion,
source-linked evidence, deterministic numerical analysis, resumable Prime
investigation sessions, explicit review states, proposal approval controls,
generic connectors, and an isolated cloud-job control plane. Multiple layers
are demos, benchmarks, or generic adapters; the UI explicitly includes scripted
and invented data. Deployment credentials, real system integrations, hosted
multi-tenant operation, cross-site collaboration, notification delivery,
validated manufacturing execution, and customer-specific model routing are
not established by this code inventory. Absence in inspected paths is reported
as “not evidenced,” not proof that no implementation exists elsewhere.
