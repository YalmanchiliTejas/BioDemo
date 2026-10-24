"""Outbound-only site acquisition agent with durable store-and-forward.

Run: python -m src.lifesci.edge --config /etc/biodemo/edge.json [--once]
The config holds environment variable names, never shared secret values.
"""
import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import time
from urllib.request import Request, build_opener
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Request as ApiRequest
from pydantic import BaseModel, ConfigDict, Field

from .connectors import NoRedirect, _secret
from .ids import canonical_json, content_hash
from .integrations import SiteCollectorBuffer, record_to_dict


def signature(secret: str, timestamp: str, data: bytes) -> str:
    return hmac.new(secret.encode(), timestamp.encode() + b"\n" + data, hashlib.sha256).hexdigest()


class GatewayIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    gateway_id: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,80}$")
    site_id: str = Field(min_length=1)
    secret_env: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,100}$")
    enabled: bool = True


def install_edge_api(p, app, ctx_dep):
    @app.post("/v1/edge/gateways")
    def enroll(body: GatewayIn, ctx=Depends(ctx_dep)):
        p.identity.require(ctx, "configure", "connector", body.gateway_id, site_id=body.site_id)
        with p.store.transaction(ctx.actor_id) as tx:
            old = tx.get(ctx.tenant_id, "edge_gateway", body.gateway_id)
            if old and old.state["site_id"] != body.site_id:
                raise ValueError("gateway site cannot be changed")
            tx.put(ctx.tenant_id, "edge_gateway", body.gateway_id, {**body.model_dump(), "configured_by": ctx.actor_id},
                   expected_revision=old.revision if old else None, action="enroll_edge_gateway")
        return {"gateway_id": body.gateway_id, "site_id": body.site_id, "enabled": body.enabled}

    @app.post("/v1/edge/{tenant}/{gid}/records")
    async def receive(tenant: str, gid: str, request: ApiRequest):
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > 1_000_000:
                raise HTTPException(413, "edge record exceeds 1 MB")
        rec = p.store.read().get(tenant, "edge_gateway", gid)
        if not rec or not rec.state["enabled"]:
            raise HTTPException(403, "gateway unavailable")
        conf = rec.state
        owner = p.identity.context_for(tenant, conf["configured_by"])
        p.identity.require(owner, "configure", "connector", gid, site_id=conf["site_id"])
        timestamp = request.headers.get("x-edge-timestamp", "")
        try:
            if abs(time.time() - int(timestamp)) > 300:
                raise ValueError("expired")
        except ValueError:
            raise HTTPException(401, "invalid edge timestamp")
        secret = _secret(conf["secret_env"])
        if len(secret) < 16 or not hmac.compare_digest(signature(secret, timestamp, bytes(data)), request.headers.get("x-edge-signature", "")):
            raise HTTPException(401, "invalid edge signature")
        from .integrations import record_from_dict
        try:
            doc = json.loads(data)
            event_id = content_hash(doc)
            source = record_from_dict(doc)
            if source.site_id != conf["site_id"] or not source.source_record_id or not source.source_system:
                raise ValueError("source identity/site mismatch")
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(400, "invalid edge source record") from exc
        rid = f"{gid}:{event_id}"
        with p.store.transaction(f"edge:{gid}") as tx:
            receipt = tx.get(tenant, "edge_receipt", rid)
            if receipt:
                return receipt.state["ack"]
            # Service authority is ingestion only; the gateway can never dispatch
            # manufacturing writes or choose another site's ownership.
            from .identity import AccessContext
            ctx = AccessContext(tenant, f"edge:{gid}", "agent", frozenset({"agent"}), frozenset({conf["site_id"]}))
            result = p.evidence.ingest(ctx, source_system=f"edge:{gid}:{source.source_system}",
                source_record_id=source.source_record_id, content=canonical_json(source.payload).encode(),
                media_type="application/json", event_time=doc["occurred_at"], site_id=conf["site_id"],
                metadata={"gateway_id": gid, "edge_event_id": event_id, "source_system": source.source_system})
            ack = {"event_id": event_id, "evidence_id": result["evidence_id"], "revision": result["revision"]}
            tx.put(tenant, "edge_receipt", rid, {"site_id": conf["site_id"], "ack": ack}, expected_revision=None, action="edge_receipt")
            gateway = tx.require(tenant, "edge_gateway", gid)
            from .ids import iso, utc_now
            tx.put(tenant, "edge_gateway", gid, {**gateway.state, "last_received_at": iso(utc_now()), "last_event_id": event_id},
                   expected_revision=gateway.revision, action="edge_heartbeat")
        return ack


class EdgeAgent:
    def __init__(self, config: dict, transport=None):
        from .container import Platform
        from .store import RecordStore
        self.config = config
        if config["state_path"] in (":memory:", "sqlite:///:memory:"):
            raise ValueError("edge state_path must be persistent")
        if not 1 <= int(config.get("max_pending", 10000)) <= 1000000:
            raise ValueError("max_pending must be between 1 and 1000000")
        self.tenant = config["tenant_id"]
        self.gid = config["gateway_id"]
        url = urlsplit(config["server_url"])
        if url.scheme != "https" and not (url.scheme == "http" and url.hostname in ("127.0.0.1", "localhost", "::1")):
            raise ValueError("edge uplink requires HTTPS (HTTP only on loopback)")
        if url.username or url.query or url.fragment or url.path not in ("", "/"):
            raise ValueError("server_url must name a server origin")
        self.p = Platform(RecordStore(config["state_path"]), providers={})
        self.p.identity.assign_role(self.tenant, "local-acquisition", "admin", site_id=config["site_id"])
        self.ctx = self.p.identity.context_for(self.tenant, "local-acquisition")
        self.transport = transport or self._send
        self.buffer = SiteCollectorBuffer(self.p.store, self.tenant, self.gid, self._uplink)
        for c in config["connectors"]:
            if c["transport"] not in ("file", "mqtt", "opcua", "rest") or c.get("write_operations"):
                raise ValueError("edge acquisition is read-only")
            self.p.connectors.configure(self.ctx, {**c, "site_id": config["site_id"], "owner": "local-acquisition"})

    def _send(self, data: bytes, headers: dict) -> dict:
        from urllib.parse import quote
        path = f"/v1/edge/{quote(self.tenant, safe='')}/{quote(self.gid, safe='')}/records"
        req = Request(self.config["server_url"].rstrip("/") + path, data=data, headers=headers)
        with build_opener(NoRedirect()).open(req, timeout=20) as response:
            return json.loads(response.read())

    def _uplink(self, record):
        doc = record_to_dict(record)
        data, stamp = canonical_json(doc).encode(), str(int(time.time()))
        secret = _secret(self.config["secret_env"])
        if len(secret) < 16:
            raise ValueError("edge shared secret must have at least 16 characters")
        ack = self.transport(data, {"Content-Type": "application/json", "X-Edge-Timestamp": stamp,
                                    "X-Edge-Signature": signature(secret, stamp, data)})
        if ack.get("event_id") != content_hash(doc):
            raise ValueError("server did not acknowledge the exact queued event")

    def tick(self) -> dict:
        captured, rejects = 0, []
        # Bound disk use while offline; preserve the unacknowledged queue and do
        # not advance source checkpoints when the configured capacity is reached.
        if len(self.buffer.pending()) < int(self.config.get("max_pending", 10000)):
            for c in self.config["connectors"]:
                rec = self.p.connectors.record(self.ctx, c["connector_id"])
                source = self.p.connectors._build(self.tenant, rec)
                checkpoint = self.p.store.read().get(self.tenant, "edge_checkpoint", rec.id)
                capacity = max(0, int(self.config.get("max_pending", 10000)) - len(self.buffer.pending()))
                if not capacity:
                    break
                batch = source.pull(checkpoint.state["cursor"] if checkpoint else None, min(100, capacity))
                with self.p.store.transaction("local-acquisition") as tx:
                    for record in batch.records:
                        self.buffer.receive(record)
                        captured += 1
                    tx.put(self.tenant, "edge_checkpoint", rec.id, {"cursor": batch.next_checkpoint},
                           expected_revision=checkpoint.revision if checkpoint else None, action="edge_capture_checkpoint")
                rejects.extend(getattr(source, "rejects", []))
        return {"captured": captured, "rejects": rejects, **self.buffer.flush()}

    def close(self):
        self.p.connectors.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text())
    import fcntl
    lock_path = Path(config["state_path"].removeprefix("sqlite:///"))
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(lock_path) + ".lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        agent = EdgeAgent(config)
        delay = max(1, int(config.get("poll_seconds", 5)))
        try:
            while True:
                try:
                    result = agent.tick()
                    print(json.dumps(result), flush=True)
                    delay = min(60, delay * 2) if result["error"] else max(1, int(config.get("poll_seconds", 5)))
                except (OSError, ValueError) as exc:
                    print(json.dumps({"error": type(exc).__name__, "queue_preserved": True}), flush=True)
                    delay = min(60, delay * 2)
                if args.once:
                    break
                time.sleep(delay)
        except KeyboardInterrupt:
            pass
        finally:
            agent.close()


if __name__ == "__main__":
    main()
