"""Versioned HTTP API for the life-sciences platform (LS-042).

- ``/v1`` prefix; additive changes only within a version.
- Identity (``LIFESCI_AUTH_MODE``): ``supabase`` verifies Supabase Auth access tokens,
  ``oidc`` reuses ``cloud_backend.auth.Verifier``; the ``development`` resolver reads tenant/actor headers but NEVER trusts role headers:
  roles always come from stored, revocable assignments.
- Commands accept ``Idempotency-Key``; the same key with a different body is 409.
- Cursor pagination on list endpoints; cursor-based event replay for reconnecting clients.
- Domain errors map to explicit status codes; unexpected errors never leak internals.
"""

import os
from contextlib import asynccontextmanager
from typing import Any, Callable, Protocol

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .container import Platform
from .identity import AccessContext, AuthorizationError
from .ids import content_hash
from .memory import MemoryAccessDenied, principal
from .store import ConflictError, CrossTenantError, LeaseError, NotFoundError

API_VERSION = "v1"

# --- request models ---------------------------------------------------------------
class EvidenceIn(BaseModel):
    source_system: str = Field(min_length=1, max_length=64)
    source_record_id: str = Field(min_length=1, max_length=256)
    content_text: str = Field(max_length=1_000_000)
    media_type: str = "text/plain"
    site_id: str | None = None
    event_time: str | None = None
    source_revision: str | None = None

class ProposalIn(BaseModel):
    target_system: str
    operation: str
    target_id: str
    payload: dict[str, Any] = {}
    basis: list[dict[str, Any]] = Field(min_length=1)
    rationale: str
    expected_result: str
    owner_id: str
    follow_up_measure: str | None = None
    constraints: list[str] = []
    site_id: str | None = None
    mission_id: str | None = None

class DecisionIn(BaseModel):
    expected_revision: int
    decision: str
    role: str
    comment: str | None = None
    authentication: dict[str, Any] | None = None

class MissionIn(BaseModel):
    objective: str = Field(min_length=3, max_length=4000)
    owner_id: str
    scope: dict[str, Any]
    constraints: list[str] = []
    subscriptions: list[dict[str, Any]] = []
    mission_id: str | None = None

class RuleIn(BaseModel):
    scope: str = Field(pattern="^(user|site|org)$")
    text: str = Field(min_length=1, max_length=2000)
    site_id: str | None = None
    reason: str = ""


class RuleDecisionIn(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class InvestigationBudgetIn(BaseModel):
    max_tool_calls: int | None = Field(default=None, ge=1, le=200)
    minutes: int | None = Field(default=None, ge=1, le=60)
    max_tokens: int | None = Field(default=None, ge=1000, le=5_000_000)

class InvestigationIn(BaseModel):
    objective: str = Field(default="", max_length=8000)
    site_id: str = Field(default="NF1", min_length=1, max_length=100)
    case_id: str | None = Field(default=None, max_length=160)
    conversation_id: str | None = Field(default=None, max_length=160)
    proposal_id: str | None = Field(default=None, max_length=160)
    dataset_ids: list[str] = Field(default_factory=list, max_length=10)
    record_refs: list[dict[str, Any]] = Field(default_factory=list, max_length=50)
    budget: InvestigationBudgetIn | None = None

class CorrectionIn(BaseModel):
    text: str
    source_ref: dict[str, Any] | None = None
    claim_ref: dict[str, Any] | None = None
    rejects_hypothesis: str | None = None

class AnswerIn(BaseModel):
    answer: str

class MemoryRequestIn(BaseModel):
    owner_email: str = Field(min_length=3, max_length=320)
    scopes: list[str] = Field(min_length=1, max_length=3)
    reason: str = Field(min_length=1, max_length=1000)
    days: int = Field(30, ge=1, le=90)


class MemoryDecisionIn(BaseModel):
    days: int | None = Field(None, ge=1, le=90)
    reason: str = Field("", max_length=1000)


# Evidence that only the platform itself writes: a person's chat instructions and verified CMO deliveries.
RESERVED_SOURCES = ("engineering-user-instruction", "verified-source-snapshot", "scientific-model-catalog",
                    "process-analysis-assumptions", "process-model-inputs", "fermentation-transfer",
                    "pharmaceutical-run-packet", "simulated-bioprocess-case")
RESERVED_SOURCE_PREFIXES = ("cmo-", "edge:")
HIDDEN_KINDS = ("idempotency", "model_cache", "role_assignment", "grant", "budget", "partner_membership", "organization",
                "organization_member", "account_organizations", "connector_credential", "memory_grant", "alert_inbox")


class NoteIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class ObligationIn(BaseModel):
    description: str = Field(min_length=1, max_length=4000)
    due_at: str
    every_minutes: int | None = Field(default=None, ge=1)
    task_kind: str | None = None
    payload: dict[str, Any] = {}
    inputs: list[dict[str, Any]] = []
    artifact_kind: str | None = None
    case_id: str | None = None


class ConnectorIn(BaseModel):
    model_config = {"extra": "forbid"}
    connector_id: str = Field(min_length=1, max_length=80)
    family: str
    transport: str
    site_id: str = Field(min_length=1)
    owner: str = Field(min_length=1)
    vendor: str = "generic"
    version: str = "1"
    options: dict[str, Any] = {}
    mapping: dict[str, Any] | None = None
    write_operations: list[str] = []
    enabled: bool = True
    mapping_confirmed: bool = False
    source_group: str | None = Field(default=None, min_length=1, max_length=120)
    # Write-only: sealed server-side for guided connections and never returned.
    credentials: dict[str, str] | None = None


class DiscoverIn(BaseModel):
    model_config = {"extra": "forbid"}
    resource: str | None = Field(default=None, max_length=300)
    search: str | None = Field(default=None, max_length=120)


class SourceReviewIn(BaseModel):
    model_config = {"extra": "forbid"}
    record_id: str = Field(min_length=1)
    expected_revision: int = Field(ge=1)
    decision: str
    reason: str = Field(min_length=1, max_length=4000)


class OutcomeIn(BaseModel):
    observation: str = Field(min_length=1)
    measure: str = Field(min_length=1)
    observed_value: Any = None
    evidence: list[dict[str, Any]] = Field(min_length=1)
    attribution_limits: str = Field(min_length=1)


class ReviseIn(BaseModel):
    expected_revision: int
    changes: dict[str, Any]
    reason: str = Field(min_length=1)


class TaskIn(BaseModel):
    task_kind: str
    prompt: str = ""
    payload: dict[str, Any] = {}
    inputs: list[dict[str, Any]] = []
    mission_id: str | None = None



class IdentityResolver(Protocol):
    def __call__(self, request: Any) -> AccessContext: ...


# Loopback addresses, plus the in-process test client's placeholder host.
LOCAL_CLIENTS = frozenset({"127.0.0.1", "::1", "localhost", "testclient"})


def dev_header_resolver(platform: Platform) -> IdentityResolver:
    """Development only. Roles are loaded from the store, not from headers."""
    def resolve(request: Any) -> AccessContext:
        # Header identity is a local convenience. A server that is reachable from another machine must not
        # take a caller's word for who they are, so remote callers are refused unless that is asked for.
        client = getattr(request, "client", None)
        host = getattr(client, "host", None)
        if host not in LOCAL_CLIENTS and os.environ.get("LIFESCI_DEV_AUTH_ALLOW_REMOTE") != "1":
            raise HTTPException(401, "This server uses development sign-in and only accepts local requests. "
                                     "Set LIFESCI_AUTH_MODE=supabase or oidc for shared use.")
        tenant = request.headers.get("x-tenant-id")
        actor = request.headers.get("x-actor-id")
        if not tenant or not actor:
            raise HTTPException(401, "missing tenant/actor")
        kind = request.headers.get("x-actor-kind", "person")
        if kind not in ("person", "agent"):
            kind = "person"
        return platform.identity.context_for(tenant, actor, actor_kind=kind)
    return resolve


def oidc_resolver(platform: Platform) -> IdentityResolver:
    from src.cloud_backend.auth import Verifier

    verifier = Verifier(os.environ["OIDC_ISSUER"], os.environ["OIDC_AUDIENCE"], os.environ["OIDC_JWKS_URL"],
                        os.environ["DEPLOYMENT_TENANT"])

    def resolve(request: Any) -> AccessContext:
        from dataclasses import replace
        from .identity import Authentication
        identity = verifier.verify(request.headers.get("authorization"))
        # These tokens carry no sign-in time, so they cannot satisfy a required re-authentication.
        return replace(platform.identity.context_for(identity.tenant, identity.subject),
                       authentication=Authentication("oidc"))
    return resolve


AUTH_MODES = {"supabase": "supabase", "oidc": "oidc", "development": "development_headers"}


def configured_auth_mode() -> str:
    """LIFESCI_AUTH_MODE, defaulting to oidc when OIDC_ISSUER is set and development otherwise."""
    mode = os.environ.get("LIFESCI_AUTH_MODE", "").strip().lower() or (
        "oidc" if os.environ.get("OIDC_ISSUER") else "development")
    if mode not in AUTH_MODES:
        raise RuntimeError(f"LIFESCI_AUTH_MODE must be one of {', '.join(AUTH_MODES)}; got {mode!r}")
    return AUTH_MODES[mode]


def runtime_tick(platform: Platform) -> dict[str, int]:
    """One pass of the background runtime, for hosts without a long-lived process (a schedule on Lambda)."""
    from . import data_worker

    platform.runtime.tick()
    tenants = list(platform.runtime.tenants())
    return {"tenants": len(tenants), "data_flows_finished": data_worker.tick(platform, tenants)}


def create_app(platform: Platform | None = None, resolver: IdentityResolver | None = None) -> Any:
    auth_mode = configured_auth_mode()
    if resolver is None and auth_mode == "development_headers" and os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
        raise RuntimeError("Development header authentication cannot run on AWS Lambda; "
                           "set LIFESCI_AUTH_MODE=supabase (or oidc) and its settings")
    platform = platform or Platform.from_env()
    if resolver is None:
        if auth_mode == "supabase":
            from .supabase_auth import supabase_resolver
            resolver = supabase_resolver(platform)
        elif auth_mode == "oidc":
            resolver = oidc_resolver(platform)
        else:
            resolver = dev_header_resolver(platform)
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        platform.runtime.start()
        try:
            yield
        finally:
            platform.runtime.close()

    app = FastAPI(lifespan=lifespan, title="Sievance API", version="1.0", docs_url=None if auth_mode != "development_headers" else "/v1/docs",
                  openapi_url="/v1/openapi.json")
    # Work that outlives a request: a thread here, an asynchronous invocation on Lambda (see tasks.py).
    from .tasks import TaskRunner
    app.state.tasks = TaskRunner()
    app.state.tasks.register("runtime_tick", lambda payload: runtime_tick(platform))
    # The statically exported Next workspace can connect to the existing API.
    # Production cross-origin access must be configured explicitly.
    from fastapi.middleware.cors import CORSMiddleware
    origins = os.environ.get("LIFESCI_CORS_ORIGINS", "http://127.0.0.1:5180,http://localhost:5180" if auth_mode == "development_headers" else "")
    if origins:
        app.add_middleware(CORSMiddleware, allow_origins=origins.split(","), allow_methods=["GET", "POST"],
                           allow_headers=["Authorization", "Content-Type", "X-Tenant-Id", "X-Actor-Id", "Idempotency-Key", "X-CMO-Token", "X-Organization-Id", "X-Demo-Visitor"],
                           expose_headers=["X-Package-Complete", "X-Open-Issues", "X-Values-Pending", "X-Page-Width",
                                           "X-Page-Height", "X-Page-Count"])

    def ctx_dep(request: Request) -> AccessContext:
        requested = request.headers.get("x-organization-id") or request.headers.get("x-tenant-id")
        demo = getattr(platform, "demo", None)
        if demo is not None and requested and requested.startswith("demo_") and demo.expired(requested):
            raise HTTPException(410, "This demo workspace has expired. Start a new one, or talk to us.")
        ctx = resolver(request)
        platform.runtime.track(ctx.tenant_id)
        return ctx

    def demo_visitor(request: Request) -> str:
        """Only anonymous demo sign-ins may create demo workspaces; real accounts never get one."""
        verifier = getattr(resolver, "verifier", None)
        if verifier is not None:
            claims = verifier.verify(request.headers.get("authorization"))
            if claims.get("is_anonymous") is not True:
                raise HTTPException(403, "Demo workspaces are for demo visitors; you are signed in with an organization account")
            return claims["sub"]
        if auth_mode == "development_headers" and request.headers.get("x-demo-visitor") == "1" and request.headers.get("x-actor-id"):
            return request.headers["x-actor-id"]
        raise HTTPException(403, "Demo workspaces are not available on this deployment")

    @app.exception_handler(AuthorizationError)
    async def _auth(_: Request, exc: AuthorizationError):  # noqa: ANN202
        return JSONResponse({"error": "forbidden", "detail": str(exc)}, status_code=403)

    @app.exception_handler(PermissionError)
    async def _perm(_: Request, exc: PermissionError):  # noqa: ANN202
        return JSONResponse({"error": "forbidden", "detail": str(exc)}, status_code=403)

    from .demo import DemoLimit

    @app.exception_handler(DemoLimit)
    async def _demo_limit(_: Request, exc: DemoLimit):  # noqa: ANN202
        return JSONResponse({"error": "limit_reached", "detail": str(exc)}, status_code=429)

    @app.exception_handler(ConflictError)
    async def _conflict(_: Request, exc: ConflictError):  # noqa: ANN202
        return JSONResponse({"error": "conflict", "detail": str(exc)}, status_code=409)

    @app.exception_handler(LeaseError)
    async def _lease(_: Request, exc: LeaseError):  # noqa: ANN202
        return JSONResponse({"error": "conflict", "detail": str(exc)}, status_code=409)

    @app.exception_handler(NotFoundError)
    async def _nf(_: Request, exc: NotFoundError):  # noqa: ANN202
        return JSONResponse({"error": "not_found", "detail": str(exc)}, status_code=404)

    @app.exception_handler(ValueError)
    async def _bad(_: Request, exc: ValueError):  # noqa: ANN202
        return JSONResponse({"error": "invalid", "detail": str(exc)}, status_code=400)

    from .media import MediaUnavailable
    @app.exception_handler(MediaUnavailable)
    async def _media_unavailable(_: Request, exc: MediaUnavailable):
        return JSONResponse({"error": "unavailable", "detail": str(exc)}, status_code=503)

    def idempotent(ctx: AccessContext, key: str | None, route: str, body: Any, run: Callable[[], Any]) -> Any:
        if not key:
            return run()
        if not 8 <= len(key) <= 128:
            raise HTTPException(400, "Idempotency-Key must be 8-128 characters")
        rid = content_hash([ctx.actor_id, route, key])[:40]
        digest = content_hash(body)
        existing = platform.store.read().get(ctx.tenant_id, "idempotency", rid)
        if existing:
            if existing.state["request_hash"] != digest:
                raise ConflictError("Idempotency-Key reused with a different request")
            return existing.state["response"]
        response = run()
        with platform.store.transaction(ctx.actor_id) as tx:
            if tx.get(ctx.tenant_id, "idempotency", rid) is None:
                tx.put(ctx.tenant_id, "idempotency", rid, {"request_hash": digest, "response": response},
                       expected_revision=None, action="idempotency")
        return response

    def command(ctx: AccessContext, key: str | None, route: str, body: Any, run: Callable[[], Any]) -> Any:
        """Store-only commands: the change and its replay receipt commit together, and a concurrent retry
        with the same key waits for that commit instead of running the command a second time."""
        if not key:
            return run()
        with platform.store.transaction(ctx.actor_id):
            return idempotent(ctx, key, route, body, run)

    from .demo import DemoExpired, demo_routes
    demo_routes(app, platform, ctx_dep, demo_visitor)

    @app.exception_handler(DemoExpired)
    async def _demo_expired(_: Request, __: DemoExpired):  # noqa: ANN202
        return JSONResponse({"error": "expired", "detail": "This demo workspace has expired. Start a new one, or talk to us."}, status_code=410)

    from .signals import signal_routes
    from .alerts import alert_routes
    signal_routes(app, platform, ctx_dep)
    alert_routes(app, platform, ctx_dep)
    from .triage import triage_routes
    triage_routes(app, platform, ctx_dep)
    from .organization_api import install_organization_api
    install_organization_api(app, platform, resolver, ctx_dep, os.environ.get("LIFESCI_MULTI_TENANT") == "1",
                             development=auth_mode == "development_headers")

    # --- routes ---------------------------------------------------------------------
    @app.get(f"/{API_VERSION}/health")
    def health() -> dict[str, Any]:
        from .assurance import degraded_mode
        report = degraded_mode(platform.gateway)
        return {"status": "ok", "api_version": API_VERSION, "backend": platform.store.backend,
                "models_available": report.models_available, "continuing": list(report.continuing),
                "blocked_task_kinds": list(report.blocked), "outbox_pending": platform.store.pending_outbox()}

    @app.get(f"/{API_VERSION}/me")
    def me(ctx: AccessContext = Depends(ctx_dep)) -> dict[str, Any]:
        if not ctx.roles and not platform.identity.live_grants(ctx.tenant_id, ctx.actor_id) and not (
            ctx.actor_kind == "partner" and platform.identity.live_grants(ctx.tenant_id, ctx.partner_org_id)
        ):
            raise HTTPException(403, "no role assignments or grants for this person in this tenant")
        return {"tenant_id": ctx.tenant_id, "actor_id": ctx.actor_id, "actor_kind": ctx.actor_kind,
                "roles": sorted(ctx.roles), "site_ids": sorted(ctx.site_ids), "auth_mode": auth_mode}

    @app.post(f"/{API_VERSION}/evidence", status_code=201)
    def ingest(body: EvidenceIn, ctx: AccessContext = Depends(ctx_dep),
               idem: str | None = Header(None, alias="Idempotency-Key")) -> dict[str, Any]:
        if body.source_system in RESERVED_SOURCES or body.source_system.startswith(RESERVED_SOURCE_PREFIXES):
            raise HTTPException(403, "this source is written only by the platform")
        # Reading evidence is not authority to add or correct it.
        platform.identity.require(ctx, "propose", "evidence", site_id=body.site_id)
        current = platform.store.read().get(ctx.tenant_id, "evidence", f"{body.source_system}:{body.source_record_id}")
        if current is not None and current.state.get("metadata") and current.state["metadata"].get("intake") != "manual":
            # Records a connector, gateway or platform service brought in are corrected by that source only.
            raise HTTPException(403, "this record is maintained by its source; a correction must come from that source")
        return command(ctx, idem, "evidence", body.model_dump(), lambda: platform.evidence.ingest(
            ctx, source_system=body.source_system, source_record_id=body.source_record_id,
            content=body.content_text.encode(), media_type=body.media_type, site_id=body.site_id,
            event_time=body.event_time, source_revision=body.source_revision,
            metadata={"intake": "manual", "submitted_by": ctx.actor_id}))

    @app.get(f"/{API_VERSION}/records/{{kind}}")
    def list_records(kind: str, cursor: str | None = None, limit: int = 50,
                     ctx: AccessContext = Depends(ctx_dep)) -> dict[str, Any]:
        if kind in HIDDEN_KINDS:
            raise HTTPException(404, "not a public record kind")
        limit = max(1, min(limit, 200))
        tx = platform.store.read()
        rows = [r for r in tx.list(ctx.tenant_id, kind) if (cursor is None or r.id > cursor)]
        rows.sort(key=lambda r: r.id)
        visible = []
        for r in rows:
            if kind == "transfer_package" and not any(platform.identity.check(ctx, "read", kind, r.id, site_id=r.state[s])
                                                       for s in ("sending_site", "receiving_site")):
                continue
            if (platform.identity.check(ctx, "read", kind, r.id, site_id=r.state.get("site_id"))
                    and platform.memory.readable(ctx, kind, r.state)):
                if "inputs" in r.state:
                    try:
                        platform.evidence.read_derived(ctx, kind, r.id)
                    except (PermissionError, ValueError, KeyError):
                        continue
                if platform.process_models.analysis.is_library_record(kind,r.state):
                    try:platform.process_models.analysis._library_memory(ctx,kind,r.state)
                    except PermissionError:continue
                visible.append({"id": r.id, "revision": r.revision, "state": r.state})
                if len(visible) == limit:
                    break
        next_cursor = visible[-1]["id"] if len(visible) == limit else None
        return {"items": visible, "next_cursor": next_cursor}

    @app.get(f"/{API_VERSION}/records/{{kind}}/{{record_id:path}}")
    def get_record(kind: str, record_id: str, ctx: AccessContext = Depends(ctx_dep)) -> dict[str, Any]:
        if kind in HIDDEN_KINDS:
            raise HTTPException(404, "not a public record kind")
        rec = platform.store.read().require(ctx.tenant_id, kind, record_id)
        if platform.process_models.analysis.is_library_record(kind,rec.state):platform.process_models.analysis._library_memory(ctx,kind,rec.state)
        if kind == "transfer_package" and not any(platform.identity.check(ctx, "read", kind, rec.id, site_id=rec.state[s])
                                                   for s in ("sending_site", "receiving_site")):
            raise HTTPException(403, "transfer outside actor site scope")
        platform.identity.require(ctx, "read", kind, record_id, site_id=rec.state.get("site_id"))
        if not platform.memory.readable(ctx, kind, rec.state):
            raise MemoryAccessDenied()
        if rec.state.get("inputs") is not None:
            return platform.evidence.read_derived(ctx, kind, record_id)
        return {"id": rec.id, "revision": rec.revision, "state": rec.state,
                "audit": [a.__dict__ for a in platform.store.read().audit(ctx.tenant_id, kind, record_id, 50)]}

    @app.post(f"/{API_VERSION}/proposals", status_code=201)
    def propose(body: ProposalIn, ctx: AccessContext = Depends(ctx_dep),
                idem: str | None = Header(None, alias="Idempotency-Key")) -> dict[str, Any]:
        return command(ctx, idem, "proposals", body.model_dump(),
                          lambda: platform.actions.propose(ctx, **body.model_dump()))

    @app.post(f"/{API_VERSION}/proposals/{{proposal_id}}/decisions")
    def decide(proposal_id: str, body: DecisionIn, ctx: AccessContext = Depends(ctx_dep),
               idem: str | None = Header(None, alias="Idempotency-Key")) -> dict[str, Any]:
        return command(ctx, idem, f"decisions:{proposal_id}", body.model_dump(),
                          lambda: platform.actions.decide(ctx, proposal_id, **body.model_dump()))

    def _proposal_view(tx: Any, rec: Any, ctx: AccessContext) -> dict[str, Any]:
        approvals = [a.state for a in tx.find(ctx.tenant_id, "approval", "proposal_id", rec.id)]
        outcomes = [o.state for o in tx.find(ctx.tenant_id, "outcome", "proposal_id", rec.id)]
        can = [r for r in rec.state["required_roles"] if r in ctx.roles and ctx.actor_id != rec.state["requested_by"]
               and ctx.actor_id not in rec.state.get("revised_by", [])
               and ctx.actor_kind != "agent" and rec.state["status"] == "proposed"
               and not any(a["role"] == r and a["content_hash"] == rec.state["content_hash"] for a in approvals)]
        return {**rec.state, "revision": rec.revision, "updated_at": rec.updated_at, "approvals": approvals,
                "outcomes": outcomes, "can_decide": can}

    @app.get(f"/{API_VERSION}/proposals")
    def list_proposals(mission_id: str | None = None, status: str | None = None, limit: int = 100,
                       ctx: AccessContext = Depends(ctx_dep)) -> dict[str, Any]:
        tx = platform.store.read()
        recs = tx.find(ctx.tenant_id, "proposal", "mission_id", mission_id) if mission_id else \
            tx.list(ctx.tenant_id, "proposal")
        items = [_proposal_view(tx, r, ctx) for r in recs
                 if (status is None or r.state["status"] == status)
                 and platform.identity.check(ctx, "read", "proposal", r.id, site_id=r.state.get("site_id"))]
        items.sort(key=lambda p: p["updated_at"], reverse=True)
        return {"items": items[:max(1, min(limit, 500))]}

    @app.get(f"/{API_VERSION}/proposals/{{proposal_id}}")
    def get_proposal(proposal_id: str, ctx: AccessContext = Depends(ctx_dep)) -> dict[str, Any]:
        tx = platform.store.read()
        rec = tx.require(ctx.tenant_id, "proposal", proposal_id)
        platform.identity.require(ctx, "read", "proposal", proposal_id, site_id=rec.state.get("site_id"))
        return _proposal_view(tx, rec, ctx)

    @app.post(f"/{API_VERSION}/missions", status_code=201)
    def start_mission(body: MissionIn, ctx: AccessContext = Depends(ctx_dep),
                      idem: str | None = Header(None, alias="Idempotency-Key")) -> dict[str, Any]:
        if body.owner_id != principal(ctx):
            raise HTTPException(403, "a mission is started for yourself")
        return command(ctx, idem, "missions", body.model_dump(),
                          lambda: platform.missions.start_or_resume(ctx, **body.model_dump()))

    @app.get(f"/{API_VERSION}/missions")
    def list_missions(ctx: AccessContext = Depends(ctx_dep)) -> dict[str, Any]:
        return {"items": platform.missions.list_for(ctx)}

    @app.get(f"/{API_VERSION}/missions/{{mission_id}}")
    def get_mission(mission_id: str, ctx: AccessContext = Depends(ctx_dep)) -> dict[str, Any]:
        return platform.missions.get(ctx, mission_id)

    @app.post(f"/{API_VERSION}/missions/{{mission_id}}/notes", status_code=201)
    def add_note(mission_id: str, body: NoteIn, ctx: AccessContext = Depends(ctx_dep),
                 idem: str | None = Header(None, alias="Idempotency-Key")) -> dict[str, Any]:
        return command(ctx, idem, f"notes:{mission_id}", body.model_dump(),
                          lambda: platform.missions.add_note(ctx, mission_id, body.body))

    @app.post(f"/{API_VERSION}/missions/{{mission_id}}/obligations", status_code=201)
    def add_obligation(mission_id: str, body: ObligationIn, ctx: AccessContext = Depends(ctx_dep),
                       idem: str | None = Header(None, alias="Idempotency-Key")) -> dict[str, Any]:
        platform.missions.get(ctx, mission_id)
        platform.identity.require(ctx, "propose", "mission", mission_id)
        return command(ctx, idem, f"obligations:{mission_id}", body.model_dump(),
            lambda: platform.missions.add_obligation(ctx, mission_id, **body.model_dump()))

    @app.post(f"/{API_VERSION}/missions/{{mission_id}}/obligations/{{obligation_id}}/retry")
    def retry_obligation(mission_id: str, obligation_id: str, ctx: AccessContext = Depends(ctx_dep)):
        platform.identity.require(ctx, "propose", "mission", mission_id)
        def retry(s):
            if not any(o["obligation_id"] == obligation_id and o["status"] == "open" for o in s["obligations"]):
                raise ValueError("no open obligation to retry")
            return {**s, "obligations": [{**o, "surfaced_due_at": None, "runtime_status": "pending"}
                    if o["obligation_id"] == obligation_id else o for o in s["obligations"]]}
        out = platform.missions._update(ctx, mission_id, retry, action="retry_obligation")
        platform.missions.scheduler.schedule_wakeup(ctx.tenant_id, mission_id, "obligation_retry")
        return out

    @app.get(f"/{API_VERSION}/missions/{{mission_id}}/proposals")
    def mission_proposals(mission_id: str, ctx: AccessContext = Depends(ctx_dep)) -> dict[str, Any]:
        # Proposals are organization records with their own approvers (e.g. QA), not the mission owner's memory:
        # each one is authorized by itself, exactly as GET /proposals?mission_id= does.
        tx = platform.store.read()
        items = [_proposal_view(tx, r, ctx) for r in tx.find(ctx.tenant_id, "proposal", "mission_id", mission_id)
                 if platform.identity.check(ctx, "read", "proposal", r.id, site_id=r.state.get("site_id"))]
        items.sort(key=lambda p: p["created_at"], reverse=True)
        return {"items": items}

    @app.post(f"/{API_VERSION}/proposals/{{proposal_id}}/revisions")
    def revise(proposal_id: str, body: ReviseIn, ctx: AccessContext = Depends(ctx_dep)) -> dict[str, Any]:
        return platform.actions.revise(ctx, proposal_id, **body.model_dump())

    @app.post(f"/{API_VERSION}/proposals/{{proposal_id}}/outcomes", status_code=201)
    def outcome(proposal_id: str, body: OutcomeIn, ctx: AccessContext = Depends(ctx_dep),
                idem: str | None = Header(None, alias="Idempotency-Key")) -> dict[str, Any]:
        return command(ctx, idem, f"outcomes:{proposal_id}", body.model_dump(),
                          lambda: platform.actions.record_outcome(ctx, proposal_id, **body.model_dump()))

    @app.get(f"/{API_VERSION}/missions/{{mission_id}}/stream")
    def mission_stream(mission_id: str, after: int = 0, ctx: AccessContext = Depends(ctx_dep)) -> dict[str, Any]:
        return platform.missions.stream(ctx, mission_id, after_seq=after)

    @app.post(f"/{API_VERSION}/missions/{{mission_id}}/corrections", status_code=201)
    def correct(mission_id: str, body: CorrectionIn, ctx: AccessContext = Depends(ctx_dep)) -> dict[str, Any]:
        return platform.missions.record_correction(ctx, mission_id, **body.model_dump())

    # --- memory sharing: a colleague reads someone's assistant memory only under their approved grant --------
    def _emails(tenant: str) -> dict[str, str]:
        return {r.id: r.state.get("email") for r in platform.store.read().list(tenant, "organization_member")}

    def _grant_view(g: dict[str, Any], emails: dict[str, str]) -> dict[str, Any]:
        return {**g, "owner_email": emails.get(g["owner_id"]), "grantee_email": emails.get(g["grantee_id"])}

    @app.get(f"/{API_VERSION}/memory-grants")
    def list_memory_grants(ctx: AccessContext = Depends(ctx_dep)) -> dict[str, Any]:
        emails, grants = _emails(ctx.tenant_id), platform.memory.list_for(ctx)
        return {k: [_grant_view(g, emails) for g in v] for k, v in grants.items()}

    @app.post(f"/{API_VERSION}/memory-grants", status_code=201)
    def request_memory_grant(body: MemoryRequestIn, ctx: AccessContext = Depends(ctx_dep)) -> dict[str, Any]:
        emails = _emails(ctx.tenant_id)  # this organization's members only
        owner = next((i for i, e in emails.items() if (e or "").lower() == body.owner_email.strip().lower()), None)
        if owner is None:
            raise HTTPException(404, "No member with that email in this organization")
        grant = platform.memory.request(ctx, owner_id=owner, scopes=body.scopes, reason=body.reason, days=body.days)
        alerts = getattr(platform, "alerts", None)
        if alerts is not None:
            who = emails.get(ctx.actor_id) or ctx.actor_id
            alerts.notify(ctx.tenant_id, owner, key=grant["grant_id"], kind="memory_request",
                          title=f"{who} asks to read your assistant memory ({', '.join(grant['scopes'])})",
                          link="/settings/?tab=memory")
        return _grant_view(grant, emails)

    @app.post(f"/{API_VERSION}/memory-grants/{{grant_id}}/approve")
    def approve_memory_grant(grant_id: str, body: MemoryDecisionIn, ctx: AccessContext = Depends(ctx_dep)) -> dict[str, Any]:
        return _grant_view(platform.memory.approve(ctx, grant_id, days=body.days, reason=body.reason), _emails(ctx.tenant_id))

    @app.post(f"/{API_VERSION}/memory-grants/{{grant_id}}/deny")
    def deny_memory_grant(grant_id: str, body: MemoryDecisionIn, ctx: AccessContext = Depends(ctx_dep)) -> dict[str, Any]:
        return _grant_view(platform.memory.deny(ctx, grant_id, reason=body.reason), _emails(ctx.tenant_id))

    @app.post(f"/{API_VERSION}/memory-grants/{{grant_id}}/revoke")
    def revoke_memory_grant(grant_id: str, body: MemoryDecisionIn, ctx: AccessContext = Depends(ctx_dep)) -> dict[str, Any]:
        return _grant_view(platform.memory.revoke(ctx, grant_id, reason=body.reason), _emails(ctx.tenant_id))

    @app.get(f"/{API_VERSION}/memory/{{owner_id}}/conversations")
    def shared_conversations(owner_id: str, ctx: AccessContext = Depends(ctx_dep)) -> dict[str, Any]:
        return {"conversations": platform.engineering_conversations.shared_list(ctx, owner_id)}

    @app.get(f"/{API_VERSION}/memory/{{owner_id}}/conversations/{{thread_id}}")
    def shared_conversation(owner_id: str, thread_id: str, ctx: AccessContext = Depends(ctx_dep)) -> dict[str, Any]:
        return platform.engineering_conversations.shared_get(ctx, owner_id, thread_id)

    @app.get(f"/{API_VERSION}/memory/{{owner_id}}/corrections")
    def shared_corrections(owner_id: str, ctx: AccessContext = Depends(ctx_dep)) -> dict[str, Any]:
        platform.memory.require_read(ctx, owner_id, "corrections")
        out = [{**c, "mission_id": r.id} for r in platform.store.read().list(ctx.tenant_id, "mission")
               if r.state.get("owner_id") == owner_id for c in r.state.get("corrections", [])
               if c.get("by") in (owner_id, f"agent:{owner_id}")]
        return {"corrections": sorted(out, key=lambda c: c.get("at", ""), reverse=True)}

    @app.get(f"/{API_VERSION}/memory/{{owner_id}}/rules")
    def shared_rules(owner_id: str, ctx: AccessContext = Depends(ctx_dep)) -> dict[str, Any]:
        platform.memory.require_read(ctx, owner_id, "rules")
        return {"rules": [{**r.state, "revision": r.revision} for r in platform.store.read().list(ctx.tenant_id, "assistant_rule")
                          if r.state.get("scope") == "user" and r.state.get("owner_id") == owner_id]}

    # --- the assistant's own memory (agent_memory.py): owner's notes, entity pages, consolidation ---
    @app.get(f"/{API_VERSION}/assistant-memory")
    def my_memory(ctx: AccessContext = Depends(ctx_dep)) -> dict[str, Any]:
        me = principal(ctx)
        state = platform.store.read().get(ctx.tenant_id, "memory_state", me)
        return {"notes": platform.agent_memory.notes(ctx), "pages": platform.agent_memory.pages(ctx),
                "index": platform.agent_memory.index(ctx, me),
                "last_consolidated_at": state.state.get("last_dream_at") if state else None,
                "last_report": state.state.get("last_report") if state else None,
                "rule_suggestions": state.state.get("rule_suggestions", []) if state else [],
                "semantic_search": platform.agent_memory.embedder is not None}

    @app.get(f"/{API_VERSION}/memory/{{owner_id}}/notes")
    def shared_notes(owner_id: str, ctx: AccessContext = Depends(ctx_dep)) -> dict[str, Any]:
        return {"notes": platform.agent_memory.notes(ctx, owner_id), "pages": platform.agent_memory.pages(ctx, owner_id)}

    class NoteStatusIn(BaseModel):
        status: str
        reason: str = ""

    @app.post(f"/{API_VERSION}/assistant-memory/notes/{{note_id}}/status")
    def note_status(note_id: str, body: NoteStatusIn, ctx: AccessContext = Depends(ctx_dep)) -> dict[str, Any]:
        return platform.agent_memory.set_status(ctx, note_id, body.status, body.reason)

    @app.post(f"/{API_VERSION}/assistant-memory/consolidate")
    def consolidate(ctx: AccessContext = Depends(ctx_dep)) -> dict[str, Any]:
        if ctx.actor_kind != "person" or ctx.delegated_from:
            raise PermissionError("only the person can consolidate their memory")
        platform.identity.require(ctx, "read", "model_run")
        if getattr(platform, "demo", None) is not None:
            platform.demo.consume_message(ctx)
        return platform.agent_memory.dream(ctx.tenant_id, ctx.actor_id)

    @app.get(f"/{API_VERSION}/assistant-rules")
    def list_rules(site_id: str | None = None, status: str | None = None,
                   ctx: AccessContext = Depends(ctx_dep)) -> dict[str, Any]:
        return {"items": platform.rules.visible(ctx, site_id=site_id, status=status)}

    @app.post(f"/{API_VERSION}/assistant-rules", status_code=201)
    def propose_rule(body: RuleIn, ctx: AccessContext = Depends(ctx_dep)) -> dict[str, Any]:
        return platform.rules.propose(ctx, **body.model_dump())

    @app.post(f"/{API_VERSION}/assistant-rules/{{rule_id}}/activate")
    def activate_rule(rule_id: str, body: RuleDecisionIn, ctx: AccessContext = Depends(ctx_dep)) -> dict[str, Any]:
        return platform.rules.activate(ctx, rule_id, body.reason)

    @app.post(f"/{API_VERSION}/assistant-rules/{{rule_id}}/retire")
    def retire_rule(rule_id: str, body: RuleDecisionIn, ctx: AccessContext = Depends(ctx_dep)) -> dict[str, Any]:
        return platform.rules.retire(ctx, rule_id, body.reason)

    @app.get("/.well-known/investigation-jwks.json")
    def investigation_jwks() -> dict[str, Any]:
        if not platform.investigations.issuer:
            raise HTTPException(404, "Investigation execution is not configured")
        return platform.investigations.issuer.jwks()

    @app.post(f"/{API_VERSION}/investigation-runs", status_code=201)
    def start_investigation(body: InvestigationIn, ctx: AccessContext = Depends(ctx_dep)) -> dict[str, Any]:
        return platform.investigations.start(ctx, body.model_dump())

    @app.get(f"/{API_VERSION}/investigation-runs")
    def list_investigations(case_id: str | None = None, conversation_id: str | None = None,
                            ctx: AccessContext = Depends(ctx_dep)) -> dict[str, Any]:
        return {"items": platform.investigations.list(ctx, case_id=case_id, conversation_id=conversation_id)}

    @app.get(f"/{API_VERSION}/investigation-runs/{{run_id}}")
    def get_investigation(run_id: str, ctx: AccessContext = Depends(ctx_dep)) -> dict[str, Any]:
        return platform.investigations.get(ctx, run_id)

    @app.get(f"/{API_VERSION}/investigation-runs/{{run_id}}/events")
    def investigation_events(run_id: str, after: int = 0, ctx: AccessContext = Depends(ctx_dep)) -> dict[str, Any]:
        return platform.investigations.events(ctx, run_id, after)

    @app.post(f"/{API_VERSION}/investigation-runs/{{run_id}}/stop")
    def stop_investigation(run_id: str, ctx: AccessContext = Depends(ctx_dep)) -> dict[str, Any]:
        return platform.investigations.stop(ctx, run_id)

    @app.post(f"/{API_VERSION}/investigation-runs/{{run_id}}/send-for-review")
    def send_investigation_for_review(run_id: str, ctx: AccessContext = Depends(ctx_dep)) -> dict[str, Any]:
        return platform.investigations.send_for_review(ctx, run_id)

    @app.get(f"/{API_VERSION}/investigation-runs/{{run_id}}/report")
    def investigation_report(run_id: str, ctx: AccessContext = Depends(ctx_dep)) -> dict[str, Any]:
        return platform.investigations.report(ctx, run_id)

    @app.get(f"/{API_VERSION}/cases/{{case_id}}/similar")
    def similar_cases(case_id: str, site_id: str, include_open: bool = False,
                      ctx: AccessContext = Depends(ctx_dep)) -> dict[str, Any]:
        # The workspace tools authorize by site and owner; outside a conversation the caller is the owner.
        scope = {"site_id": site_id, "owner_id": ctx.delegated_from or ctx.actor_id}
        return platform.engineering_conversations.workspace.similar_cases(ctx, scope, case_id=case_id, include_open=include_open)

    @app.post(f"/{API_VERSION}/missions/{{mission_id}}/decisions/{{decision_id}}")
    def answer(mission_id: str, decision_id: str, body: AnswerIn, ctx: AccessContext = Depends(ctx_dep)) -> dict[str, Any]:
        return platform.missions.answer_decision(ctx, mission_id, decision_id, body.answer)

    @app.post(f"/{API_VERSION}/tasks")
    def run_task(body: TaskIn, ctx: AccessContext = Depends(ctx_dep)) -> dict[str, Any]:
        from .gateway import TaskRequest
        # A signed-in account with no role in this organization gets no model work.
        platform.identity.require(ctx, "read", "model_run")
        if getattr(platform, "demo", None) is not None:
            platform.demo.consume_message(ctx)  # demo workspaces spend their message allowance here too
        return platform.gateway.run(TaskRequest(body.task_kind, ctx, prompt=body.prompt, payload=body.payload,
                                                inputs=body.inputs, mission_id=body.mission_id)).to_dict()

    @app.get(f"/{API_VERSION}/tasks/{{run_id}}/trace")
    def trace(run_id: str, ctx: AccessContext = Depends(ctx_dep)) -> dict[str, Any]:
        platform.identity.require(ctx, "read", "model_run", run_id)
        return platform.gateway.trace(ctx.tenant_id, run_id)

    @app.get(f"/{API_VERSION}/events")
    def events(after: int = 0, limit: int = 200, ctx: AccessContext = Depends(ctx_dep)) -> dict[str, Any]:
        platform.identity.require(ctx, "read", "event_stream")
        items = platform.store.events_since(ctx.tenant_id, after, limit=max(1, min(limit, 1000)))
        return {"events": [{"seq": s, **e.to_dict()} for s, e in items],
                "cursor": items[-1][0] if items else after}

    @app.get(f"/{API_VERSION}/connectors/catalog")
    def connector_catalog(ctx: AccessContext = Depends(ctx_dep)):
        platform.identity.require(ctx, "configure", "connector")
        return platform.connectors.catalog()

    @app.get(f"/{API_VERSION}/connectors")
    def connectors(ctx: AccessContext = Depends(ctx_dep)):
        return {"items": platform.connectors.list_for(ctx)}

    @app.post(f"/{API_VERSION}/connectors", status_code=201)
    def configure_connector(body: ConnectorIn, ctx: AccessContext = Depends(ctx_dep)):
        return platform.connectors.configure(ctx, body.model_dump())

    @app.post(f"/{API_VERSION}/connectors/{{connector_id}}/preview")
    def preview_connector(connector_id: str, ctx: AccessContext = Depends(ctx_dep)):
        try:
            return platform.connectors.preview(ctx, connector_id)
        except PermissionError:
            raise
        except (ImportError, OSError) as exc:
            raise HTTPException(503, "Connector unavailable; check its driver, endpoint and credentials") from exc

    @app.post(f"/{API_VERSION}/connectors/{{connector_id}}/discover")
    def discover_connector(connector_id: str, body: DiscoverIn, ctx: AccessContext = Depends(ctx_dep)):
        return platform.connectors.discover(ctx, connector_id, body.resource, body.search)

    @app.post(f"/{API_VERSION}/connectors/{{connector_id}}/sync")
    def sync_connector(connector_id: str, ctx: AccessContext = Depends(ctx_dep)):
        try:
            return platform.connectors.sync(ctx, connector_id)
        except PermissionError:
            raise
        except (ImportError, OSError) as exc:
            raise HTTPException(503, "Connector unavailable; check its driver, endpoint and credentials") from exc

    @app.get(f"/{API_VERSION}/connectors/{{connector_id}}/verification")
    def source_verification(connector_id: str, ctx: AccessContext = Depends(ctx_dep)):
        platform.connectors.record(ctx, connector_id, action="read")
        return platform.connectors.intake.verification.list_for(ctx, connector_id)

    @app.post(f"/{API_VERSION}/connectors/{{connector_id}}/verification/review")
    def review_source(connector_id: str, body: SourceReviewIn, ctx: AccessContext = Depends(ctx_dep)):
        platform.connectors.record(ctx, connector_id, action="read")
        return platform.connectors.intake.verification.review(ctx, connector_id, **body.model_dump())

    @app.post(f"/{API_VERSION}/connectors/{{connector_id}}/verification/publish")
    def publish_source(connector_id: str, ctx: AccessContext = Depends(ctx_dep)):
        platform.connectors.record(ctx, connector_id, action="read")
        return platform.connectors.intake.verification.publish(ctx, connector_id)

    @app.post(f"/{API_VERSION}/connectors/{{connector_id}}/intents/{{intent_id}}/dispatch")
    def dispatch_connector(connector_id: str, intent_id: str, ctx: AccessContext = Depends(ctx_dep)):
        return platform.connectors.dispatch(ctx, connector_id, intent_id)

    @app.post(f"/{API_VERSION}/connectors/{{connector_id}}/intents/{{intent_id}}/reconcile")
    def reconcile_connector(connector_id: str, intent_id: str, ctx: AccessContext = Depends(ctx_dep)):
        return platform.connectors.dispatch(ctx, connector_id, intent_id, reconcile=True)

    @app.post(f"/{API_VERSION}/webhooks/{{tenant_id}}/{{connector_id}}", status_code=202)
    async def receive_webhook(tenant_id: str, connector_id: str, request: Request):
        declared = request.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > 1_000_000:
            raise HTTPException(413, "Webhook exceeds 1 MB")
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > 1_000_000:
                raise HTTPException(413, "Webhook exceeds 1 MB")
        from starlette.concurrency import run_in_threadpool
        return await run_in_threadpool(platform.connectors.receive, tenant_id, connector_id, bytes(data),
                                       dict(request.headers))

    platform.extend_api(app, ctx_dep, idempotent)
    from .edge import install_edge_api
    install_edge_api(platform, app, ctx_dep)
    from .cmo_datasets import install_cmo_api
    install_cmo_api(platform, app, ctx_dep)
    return app
