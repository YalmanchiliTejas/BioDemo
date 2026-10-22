"""Production API entry point; deliberately does not mount demonstration routes."""
import hashlib
import asyncio
import os
import re
import uuid

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from .auth import Verifier
from .store import Conflict, Store
from .crypto import master_key, object_key, seal, unseal, spaces_client


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class Job(Input):
    version_id: str = Field(min_length=1, max_length=1024)
    objective: str = Field(min_length=1, max_length=8000)
    as_of: str = Field(min_length=20, max_length=40)
    timeout_seconds: int = Field(default=900, ge=60, le=3600)
    max_tool_calls: int = Field(default=72, ge=1, le=200)


def input_key(tenant, project, sha):
    return f"{tenant}/{project}/inputs/{sha}.zip"


def create_app(store=None, verifier=None, s3=None, encryption_key=None):
    tenant = os.environ["DEPLOYMENT_TENANT"]
    bucket = os.environ["ARTIFACT_BUCKET"]
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", tenant):
        raise ValueError("Invalid deployment tenant")
    store = store or Store(os.environ["DATABASE_URL"])
    verifier = verifier or Verifier(os.environ["OIDC_ISSUER"], os.environ["OIDC_AUDIENCE"],
                                    os.environ["OIDC_JWKS_URL"], tenant)
    s3 = s3 or spaces_client()
    encryption_key = encryption_key or master_key()
    app = FastAPI(title="Manufacturing investigation control plane", docs_url=None, redoc_url=None, openapi_url=None)
    upload_lock = asyncio.Lock()

    @app.middleware("http")
    async def security_headers(request, call_next):
        # Bound bodies even for chunked requests; no document uploads through the API.
        if request.method == "POST":
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 16384:
                    return JSONResponse({"detail": "Request too large"}, status_code=413)
            request._body = bytes(body)
        try:
            response = await call_next(request)
            if response.status_code in (401, 403):
                match = re.match(r"^/v1/projects/([a-zA-Z0-9_-]{1,80})/", request.url.path)
                project = match.group(1) if match else "__security__"
                with store.connect() as con:
                    attempted = getattr(request.state, "identity", None)
                    store.audit(con, tenant, project, attempted.subject if attempted else "unverified", "access.denied", uuid.uuid4().hex,
                                {"status": response.status_code})
        except Exception:
            # Fail closed without echoing SQL parameters, secrets or source text.
            response = JSONResponse({"detail": "Service temporarily unavailable"}, status_code=503)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

    def identity(request: Request, authorization: str | None = Header(default=None)):
        access = verifier.verify(authorization)
        request.state.identity = access
        return access

    def scope(project, access, roles):
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", project):
            raise HTTPException(400, "Invalid project")
        if access.tenant != tenant:
            raise HTTPException(403, "Tenant permission required")
        access.require(project, roles)

    def row(project, ident, access):
        value = store.get(tenant, project, ident, access.subject)
        if not value:
            raise HTTPException(404, "Job not found")
        return value

    @app.get("/healthz")
    def health():
        return {"status": "ok"}

    @app.put("/v1/projects/{project}/inputs/{sha256}")
    async def upload(project: str, sha256: str, request: Request, access=Depends(identity)):
        scope(project, access, {"operator"})
        if not re.fullmatch(r"[a-f0-9]{64}", sha256):
            raise HTTPException(422, "Invalid SHA256")
        if upload_lock.locked():
            raise HTTPException(429, "Another input upload is in progress; retry shortly")
        async with upload_lock:
            return await persist_upload(project, sha256, request, access)

    async def persist_upload(project, sha256, request, access):
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > 64 * 1024 * 1024:
                raise HTTPException(413, "Input exceeds 64 MiB")
        if hashlib.sha256(data).hexdigest() != sha256:
            raise HTTPException(422, "Input digest mismatch")
        key = input_key(tenant, project, sha256)
        with store.connect() as con:
            store.audit(con, tenant, project, access.subject, "input.upload_authorized", sha256)
        stored = s3.put_object(Bucket=bucket, Key=key, Body=seal(object_key(encryption_key, key), key, bytes(data)))
        version = stored.get("VersionId")
        if not version or version == "null":
            raise HTTPException(503, "Object versioning must be enabled")
        return {"sha256": sha256, "version_id": version}

    @app.post("/v1/projects/{project}/jobs", status_code=202)
    def submit(project: str, value: Job, idempotency_key: str = Header(min_length=8, max_length=128),
               access=Depends(identity)):
        from datetime import datetime
        scope(project, access, {"operator"})
        try:
            if datetime.fromisoformat(value.as_of.replace("Z", "+00:00")).tzinfo is None:
                raise ValueError()
        except ValueError as exc:
            raise HTTPException(422, "as_of must be an ISO timestamp with timezone") from exc
        try:
            return store.submit(tenant, project, access.subject, idempotency_key, value.model_dump())
        except Conflict as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get("/v1/projects/{project}/jobs/{ident}")
    def get(project: str, ident: str, access=Depends(identity)):
        scope(project, access, {"viewer", "operator", "auditor"})
        return store.public(row(project, ident, access))

    @app.post("/v1/projects/{project}/jobs/{ident}/cancel")
    def cancel(project: str, ident: str, access=Depends(identity)):
        scope(project, access, {"operator"})
        row(project, ident, access)
        store.cancel(tenant, project, ident, access.subject)
        return store.public(row(project, ident, access))

    @app.get("/v1/projects/{project}/jobs/{ident}/result")
    def result(project: str, ident: str, access=Depends(identity)):
        scope(project, access, {"viewer", "operator", "auditor"})
        value = row(project, ident, access)
        if value["state"] != "succeeded":
            raise HTTPException(409, "Result is not available")
        with store.connect() as con:
            store.audit(con, tenant, project, access.subject, "result.download_authorized", ident)
        key = value["result_key"]
        response = s3.get_object(Bucket=bucket, Key=key, VersionId=value["result_version"])
        with response["Body"] as body:
            encrypted = body.read(16 * 1024 * 1024 + 33)
        if len(encrypted) > 16 * 1024 * 1024 + 32:
            raise HTTPException(502, "Result exceeds limit")
        return Response(unseal(object_key(encryption_key, key), key, encrypted), media_type="application/json")

    @app.get("/v1/projects/{project}/audit")
    def audit(project: str, access=Depends(identity)):
        scope(project, access, {"auditor"})
        return store.history(tenant, project, access.subject)

    return app
