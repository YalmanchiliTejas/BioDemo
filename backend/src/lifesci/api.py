"""Versioned HTTP API for the life-sciences platform (LS-042).

- ``/v1`` prefix; additive changes only within a version.
- Identity: production uses verified OIDC claims (reusing ``cloud_backend.auth.Verifier``);
  the development resolver reads tenant/actor headers but NEVER trusts role headers:
  roles always come from stored, revocable assignments.
- Commands accept ``Idempotency-Key``; the same key with a different body is 409.
- Cursor pagination on list endpoints; cursor-based event replay for reconnecting clients.
- Domain errors map to explicit status codes; unexpected errors never leak internals.
"""

import os
from typing import Any, Callable, Protocol

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .container import Platform
from .identity import AccessContext, AuthorizationError
from .ids import content_hash
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

class CorrectionIn(BaseModel):
    text: str
    source_ref: dict[str, Any] | None = None
    claim_ref: dict[str, Any] | None = None
    rejects_hypothesis: str | None = None

class AnswerIn(BaseModel):
    answer: str

class NoteIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


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


def dev_header_resolver(platform: Platform) -> IdentityResolver:
    """Development only. Roles are loaded from the store, not from headers."""
    def resolve(request: Any) -> AccessContext:
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
        identity = verifier.verify(request.headers.get("authorization"))
        return platform.identity.context_for(identity.tenant, identity.subject)
    return resolve


def create_app(platform: Platform | None = None, resolver: IdentityResolver | None = None) -> Any:
    platform = platform or Platform.from_env()
    auth_mode = "oidc" if (resolver is None and os.environ.get("OIDC_ISSUER")) else "development_headers"
    if resolver is None:
        resolver = oidc_resolver(platform) if os.environ.get("OIDC_ISSUER") else dev_header_resolver(platform)
    app = FastAPI(title="BioDemo life-sciences platform", version="1.0", docs_url=None if os.environ.get(
        "OIDC_ISSUER") else "/v1/docs", openapi_url="/v1/openapi.json")

    def ctx_dep(request: Request) -> AccessContext:
        return resolver(request)

    @app.exception_handler(AuthorizationError)
    async def _auth(_: Request, exc: AuthorizationError):  # noqa: ANN202
        return JSONResponse({"error": "forbidden", "detail": str(exc)}, status_code=403)

    @app.exception_handler(PermissionError)
    async def _perm(_: Request, exc: PermissionError):  # noqa: ANN202
        return JSONResponse({"error": "forbidden", "detail": str(exc)}, status_code=403)

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
        if not ctx.roles and not platform.identity.live_grants(ctx.tenant_id, ctx.actor_id):
            raise HTTPException(403, "no role assignments or grants for this person in this tenant")
        return {"tenant_id": ctx.tenant_id, "actor_id": ctx.actor_id, "actor_kind": ctx.actor_kind,
                "roles": sorted(ctx.roles), "site_ids": sorted(ctx.site_ids), "auth_mode": auth_mode}

    @app.post(f"/{API_VERSION}/evidence", status_code=201)
    def ingest(body: EvidenceIn, ctx: AccessContext = Depends(ctx_dep),
               idem: str | None = Header(None, alias="Idempotency-Key")) -> dict[str, Any]:
        return idempotent(ctx, idem, "evidence", body.model_dump(), lambda: platform.evidence.ingest(
            ctx, source_system=body.source_system, source_record_id=body.source_record_id,
            content=body.content_text.encode(), media_type=body.media_type, site_id=body.site_id,
            event_time=body.event_time, source_revision=body.source_revision))

    @app.get(f"/{API_VERSION}/records/{{kind}}")
    def list_records(kind: str, cursor: str | None = None, limit: int = 50,
                     ctx: AccessContext = Depends(ctx_dep)) -> dict[str, Any]:
        if kind in ("idempotency", "model_cache", "role_assignment", "grant", "budget"):
            raise HTTPException(404, "not a public record kind")
        limit = max(1, min(limit, 200))
        tx = platform.store.read()
        rows = [r for r in tx.list(ctx.tenant_id, kind) if (cursor is None or r.id > cursor)]
        rows.sort(key=lambda r: r.id)
        visible = []
        for r in rows:
            if platform.identity.check(ctx, "read", kind, r.id, site_id=r.state.get("site_id")):
                visible.append({"id": r.id, "revision": r.revision, "state": r.state})
                if len(visible) == limit:
                    break
        next_cursor = visible[-1]["id"] if len(visible) == limit else None
        return {"items": visible, "next_cursor": next_cursor}

    @app.get(f"/{API_VERSION}/records/{{kind}}/{{record_id}}")
    def get_record(kind: str, record_id: str, ctx: AccessContext = Depends(ctx_dep)) -> dict[str, Any]:
        rec = platform.store.read().require(ctx.tenant_id, kind, record_id)
        platform.identity.require(ctx, "read", kind, record_id, site_id=rec.state.get("site_id"))
        if rec.state.get("inputs") is not None:
            return platform.evidence.read_derived(ctx, kind, record_id)
        return {"id": rec.id, "revision": rec.revision, "state": rec.state,
                "audit": [a.__dict__ for a in platform.store.read().audit(ctx.tenant_id, kind, record_id, 50)]}

    @app.post(f"/{API_VERSION}/proposals", status_code=201)
    def propose(body: ProposalIn, ctx: AccessContext = Depends(ctx_dep),
                idem: str | None = Header(None, alias="Idempotency-Key")) -> dict[str, Any]:
        return idempotent(ctx, idem, "proposals", body.model_dump(),
                          lambda: platform.actions.propose(ctx, **body.model_dump()))

    @app.post(f"/{API_VERSION}/proposals/{{proposal_id}}/decisions")
    def decide(proposal_id: str, body: DecisionIn, ctx: AccessContext = Depends(ctx_dep),
               idem: str | None = Header(None, alias="Idempotency-Key")) -> dict[str, Any]:
        return idempotent(ctx, idem, f"decisions:{proposal_id}", body.model_dump(),
                          lambda: platform.actions.decide(ctx, proposal_id, **body.model_dump()))

    def _proposal_view(tx: Any, rec: Any, ctx: AccessContext) -> dict[str, Any]:
        approvals = [a.state for a in tx.find(ctx.tenant_id, "approval", "proposal_id", rec.id)]
        outcomes = [o.state for o in tx.find(ctx.tenant_id, "outcome", "proposal_id", rec.id)]
        can = [r for r in rec.state["required_roles"] if r in ctx.roles and ctx.actor_id != rec.state["requested_by"]
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
        return idempotent(ctx, idem, "missions", body.model_dump(),
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
        return idempotent(ctx, idem, f"notes:{mission_id}", body.model_dump(),
                          lambda: platform.missions.add_note(ctx, mission_id, body.body))

    @app.get(f"/{API_VERSION}/missions/{{mission_id}}/proposals")
    def mission_proposals(mission_id: str, ctx: AccessContext = Depends(ctx_dep)) -> dict[str, Any]:
        platform.missions.get(ctx, mission_id)  # authorization on the mission
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
        return idempotent(ctx, idem, f"outcomes:{proposal_id}", body.model_dump(),
                          lambda: platform.actions.record_outcome(ctx, proposal_id, **body.model_dump()))

    @app.get(f"/{API_VERSION}/missions/{{mission_id}}/stream")
    def mission_stream(mission_id: str, after: int = 0, ctx: AccessContext = Depends(ctx_dep)) -> dict[str, Any]:
        return platform.missions.stream(ctx, mission_id, after_seq=after)

    @app.post(f"/{API_VERSION}/missions/{{mission_id}}/corrections", status_code=201)
    def correct(mission_id: str, body: CorrectionIn, ctx: AccessContext = Depends(ctx_dep)) -> dict[str, Any]:
        return platform.missions.record_correction(ctx, mission_id, **body.model_dump())

    @app.post(f"/{API_VERSION}/missions/{{mission_id}}/decisions/{{decision_id}}")
    def answer(mission_id: str, decision_id: str, body: AnswerIn, ctx: AccessContext = Depends(ctx_dep)) -> dict[str, Any]:
        return platform.missions.answer_decision(ctx, mission_id, decision_id, body.answer)

    @app.post(f"/{API_VERSION}/tasks")
    def run_task(body: TaskIn, ctx: AccessContext = Depends(ctx_dep)) -> dict[str, Any]:
        from .gateway import TaskRequest
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

    platform.extend_api(app, ctx_dep, idempotent)
    return app
