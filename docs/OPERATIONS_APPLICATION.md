# Operations application

The operations application implements the human, experience, control-plane, and
deterministic intelligence layers around the manufacturing digital thread. It can
launch the external Prime Agent deviation runtime and routes other case types to
bounded base specialists behind the same run contract.

## User workspaces

- **Command center:** open-case, task, approval, batch, and quality summaries.
- **Investigation workspace:** case queue, timeline, hypotheses, related entities,
  human tasks, and proposed actions.
- **Batch and shift console:** manufacturing progress, exception state, handoff
  notes, and resource readiness.
- **Science and quality:** process-signal workspace and permission-filtered
  knowledge retrieval with citations.
- **Source connectors:** monitored systems, synchronization health, field mappings,
  deviation-trigger event types, and automatic agent-start policy.
- **Approval inbox:** deterministic risk classification, independent approval
  roles, approve/reject decisions, and separation of duties.
- **Audit trail:** actor, action, object, timestamp, and decision meaning.
- **Agent control plane:** specialist roster, active harness, deterministic providers,
  allow-listed tools, and action-execution readiness.
- **Tenant switcher (demo):** two independently seeded sponsors and sites for visible
  isolation testing. Switching reloads every workspace with the selected scope.

## API

The FastAPI application is created by `benchmark.application.api.create_app`.
Its primary routes are:

| Route | Purpose |
|---|---|
| `GET /api/dashboard` | Operations summary and batch read model |
| `GET/POST /api/cases` | Investigation queue and case creation |
| `GET /api/cases/{id}` | Case timeline, tasks, and proposed actions |
| `GET/POST /api/tasks` | Human task service |
| `POST /api/tasks/{id}/complete` | Complete an assigned or role-owned human task |
| `GET/POST /api/actions` | Approval inbox and action proposals |
| `POST /api/actions/{id}/decision` | Independent approval/rejection |
| `POST /api/actions/{id}/execute` | Execute an approved action through the configured write boundary |
| `GET /api/context` | Authorized knowledge retrieval |
| `GET /api/audit` | Authorization audit history |
| `GET /api/health` | Runtime and extension status |
| `GET /api/session` | Current tenant, actor, role, site, and clearance scope |
| `GET /api/control-plane` | Specialist, model, tool, and execution status |
| `POST /api/intelligence/{spc|anomaly|doe}` | Run an allow-listed deterministic job |
| `POST /api/cases/{id}/agent` | Route a case to its bounded specialist |
| `GET /api/agent-runs/{id}` | Read durable agent-run and deviation-case status |
| `POST /api/agent/tools/{concept}` | Tenant-authorized read-only manufacturing retrieval |
| `GET/POST /api/connectors` | List or configure tenant source connectors |
| `POST /api/connectors/{id}/sync` | Run an immediate monitored-source synchronization |

The default identity headers are a development adapter only. A production API
gateway must validate OIDC/JWT claims and inject trusted tenant, actor, site,
role, and clearance values. Untrusted clients must not be allowed to set these
headers directly.

## Agent and tool extension points

`benchmark.application.extensions.ExtensionRegistry` exposes three replaceable ports:

- `CaseOrchestratorPort`
- `ModelRouterPort`
- `ToolExecutorPort`

The shipped `CaseOrchestrator` registers production/maintenance,
quality/deviation/RCA/OOS, process-science/formulation/experiment-design, and
CAPA/sponsor/release-evidence specialists. It auto-configures
`PrimeAgentDeviationOrchestrator` for the quality route when it finds the Prime Agent
deviation bundle. Other routes use deterministic evidence assembly in the base build.
The model-router and tool-executor ports are populated by `DeterministicModelRouter`
and `ToolGateway`; they expose SPC, median/MAD anomaly detection, and bounded
full-factorial DOE. The control-plane endpoint and UI report each provider honestly,
including the unconfigured LLM provider when Prime is absent.

For sibling development checkouts, the default bundle is `../prime-agent-bio`.
Override discovery with:

```bash
PRIME_AGENT_BUNDLE_ROOT=/path/to/prime-agent-bio \
PRIME_AGENT_COMMAND=/path/to/prime-agent-bio/prime-agent.sh \
BIODEMO_AGENT_API_BASE=http://127.0.0.1:8000 \
python3 -m benchmark serve
```

Set `PRIME_DEVIATION_AGENT_ENABLED=false` to disable it. Agent runs, authorized
input snapshots, JSON event logs, and structured deviation case state are stored
under `.prime/` and excluded from version control. The agent receives only context
assembled with the authenticated tenant, site, and clearance scope. Its
manufacturing tools call the read-only concept endpoint; raw database interfaces
are not exposed.

Every run stops at human gates. Proposed regulated actions must be submitted
through the existing approval inbox and action control plane; starting an agent does not
execute containment, testing, disposition, CAPA, notification, closure, or a
manufacturing change.

### Specialist routing

| Case types | Specialist | Base harness |
|---|---|---|
| `maintenance`, `production`, `equipment` | Production & Maintenance | Deterministic runtime + anomaly jobs |
| `deviation`, `oos`, `rca` | Quality, Deviation, RCA & OOS | Prime deviation harness when discovered; deterministic fallback |
| `science`, `formulation`, `experiment` | Process Science & Experiment Design | Deterministic runtime + SPC/DOE jobs |
| `capa`, `release`, `sponsor` | CAPA, Sponsor & Release Evidence | Deterministic runtime + SPC jobs |

Unknown case types fail into the quality specialist because it has the most conservative
human-gate policy. Adding a new specialist requires a catalog entry, a bounded job/tool
set, and tests for case routing and tenant-scoped run lookup.

## Tenancy and authorization

All working stores key records by `tenant_id`. API list and detail routes additionally
filter cases, tasks, proposals, connectors, audit entries, and agent state against the
actor's `site_ids`. Context retrieval applies tenant, site, and classification filters.
Cross-tenant detail requests return 404 so record existence is not disclosed.

The browser tenant picker exists only when the development server returns
`demo_tenants`. It swaps the complete identity scope and reloads every view. In
production, tenant membership must come from verified identity claims; clients must
not be allowed to choose arbitrary identity headers.

Action execution is a distinct permission (`system_executor`) and remains impossible
until every policy-required approval is recorded. The demo writer returns a
`DEMO-ACK-*` acknowledgement and ingests it through the evidence-first digital thread.
Production builds its writer from configured system connectors. It returns a
service-unavailable response when none have a write path, and rejects a proposal that
does not name `payload.source_system` or names a read-only/unconfigured system.

## Continuous source monitoring

The application starts `ConnectorMonitor` with the API lifecycle. Each enabled
connector polls independently on its configured interval and stores its cursor,
health, processed source-record ids, and configuration in
`BIODEMO_CONNECTOR_STATE` (default `.prime/connectors.json`). Repeated records do
not open duplicate cases. A failed connector reports its own error without stopping
the other connectors.

The initial adapter accepts paged HTTP JSON in either form:

```json
{
  "records": [
    {
      "source_record_id": "alarm-77",
      "timestamp": "2026-09-26T12:00:00Z",
      "event_type": "critical_process_alarm",
      "title": "V-204 pressure above approved limit",
      "entities": [
        {"entity_id": "BATCH-77", "entity_type": "batch"},
        {"entity_id": "V-204", "entity_type": "asset"}
      ]
    }
  ],
  "next_cursor": "page-18"
}
```

Vendor payloads can be adapted with a dotted-path field mapping such as
`{"source_record_id":"alarm.id","timestamp":"alarm.occurredAt"}`. The required
canonical fields are `source_record_id`, timezone-qualified `timestamp`, and
`event_type`; `entities` must be a list when supplied.

The connector UI stores only the name of a credential environment variable. For
example, configure `auth_header` as `Authorization`, `auth_token_env` as
`MES_API_TOKEN`, and set the actual token on the application host. Connector
administration requires the `system_admin` role.

Automatic kickoff is explicit per connector. Only records whose canonical
`event_type` occurs in `trigger_event_types` open a deviation. The raw record is
persisted as evidence first, the case id is derived deterministically from the
connector and source record, and `auto_start_agent` controls whether the new case
is immediately passed to Prime Agent. Signal thresholds and source semantics remain
site configuration; the monitor does not invent regulatory limits.

Run one application monitor instance for this file-backed first version. A
multi-worker deployment should move connector leases and deduplication state to a
shared transactional store before enabling monitoring in every worker.

## Runtime modes

Development mode is the default and seeds reviewable in-memory data:

```bash
python3 -m benchmark serve
```

Production mode uses the deployed digital-thread adapters and PostgreSQL stores:

```bash
APP_MODE=production \
POSTGRES_DSN=postgresql://biopharma:password@postgres:5432/biopharma \
python3 -m benchmark serve --host 0.0.0.0 --port 8000
```

Set `SEMANTIC_SEARCH=true` when Qdrant and the embedding dependencies are
available. Database, evidence-store, and connector environment variables are
documented in `KNOWLEDGE_BASE.md`.

## Verification

```bash
python3 -m unittest discover -s tests -v
node --check benchmark/application/static/app.js
python3 -m compileall -q benchmark
```

The application tests cover risk classification, separation of duties, pre-write
approval enforcement, site scope, tenant-isolated run ids and case state, human-task
completion, deterministic analytics, specialist routing, connector deduplication, and
the action acknowledgement feedback loop. For UI review, start the app, switch between
Northstar Therapeutics and Helix Biologics, and confirm that cases, tasks, batches,
approvals, audit, and agent state all reload rather than retaining the prior tenant.

The Compose stack includes the production application service on port `8000`.
It starts only after Neo4j, MongoDB, PostgreSQL, and the immutable evidence bucket
are ready.
