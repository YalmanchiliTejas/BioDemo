# Operations application

The operations application implements the human and experience layers around the
manufacturing digital thread. It deliberately does not implement an agent,
evaluation harness, model router, or executable tool catalog.

## User workspaces

- **Command center:** open-case, task, approval, batch, and quality summaries.
- **Investigation workspace:** case queue, timeline, hypotheses, related entities,
  human tasks, and proposed actions.
- **Batch and shift console:** manufacturing progress, exception state, handoff
  notes, and resource readiness.
- **Science and quality:** process-signal workspace and permission-filtered
  knowledge retrieval with citations.
- **Approval inbox:** deterministic risk classification, independent approval
  roles, approve/reject decisions, and separation of duties.
- **Audit trail:** actor, action, object, timestamp, and decision meaning.

## API

The FastAPI application is created by `benchmark.application.api.create_app`.
Its primary routes are:

| Route | Purpose |
|---|---|
| `GET /api/dashboard` | Operations summary and batch read model |
| `GET/POST /api/cases` | Investigation queue and case creation |
| `GET /api/cases/{id}` | Case timeline, tasks, and proposed actions |
| `GET/POST /api/tasks` | Human task service |
| `GET/POST /api/actions` | Approval inbox and action proposals |
| `POST /api/actions/{id}/decision` | Independent approval/rejection |
| `GET /api/context` | Authorized knowledge retrieval |
| `GET /api/audit` | Authorization audit history |
| `GET /api/health` | Runtime and extension status |

The default identity headers are a development adapter only. A production API
gateway must validate OIDC/JWT claims and inject trusted tenant, actor, site,
role, and clearance values. Untrusted clients must not be allowed to set these
headers directly.

## Agent and tool extension points

`benchmark.application.extensions.ExtensionRegistry` exposes three ports:

- `CaseOrchestratorPort`
- `ModelRouterPort`
- `ToolExecutorPort`

They are intentionally `None` in the shipped application. The health endpoint
and UI report them as not configured. The future implementations can be injected
without changing case, approval, integration, knowledge, or UI contracts.

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

The Compose stack includes the production application service on port `8000`.
It starts only after Neo4j, MongoDB, PostgreSQL, and the immutable evidence bucket
are ready.
