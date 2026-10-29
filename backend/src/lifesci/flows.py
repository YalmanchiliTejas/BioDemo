"""Versioned, resumable data processing. Operators use the existing task gateway.

This is a bounded POC interpreter, not a Python/SQL sandbox or an instrument
gateway. A flow can calculate or draft; it has no manufacturing command API.
"""
from copy import deepcopy
from typing import Any

from .gateway.gateway import TaskRequest
from .ids import content_hash, new_id


def node_order(nodes: list[dict[str, Any]]) -> list[str]:
    if not 1 <= len(nodes) <= 50:
        raise ValueError("a flow needs 1–50 nodes")
    ids = [n["node_id"] for n in nodes]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate node IDs")
    pending = {n["node_id"]: set(n.get("depends_on", [])) for n in nodes}
    if any(deps - set(ids) for deps in pending.values()):
        raise ValueError("unknown dependency")
    order: list[str] = []
    while pending:
        ready = [nid for nid, deps in pending.items() if deps <= set(order)]
        if not ready:
            raise ValueError("flow dependencies contain a cycle")
        for nid in ready:
            order.append(nid)
            del pending[nid]
    return order


def resolve(value: Any, results: dict[str, Any], allowed: set[str]) -> Any:
    if isinstance(value, dict):
        if "$node" in value:
            if set(value) - {"$node", "path"} or value["$node"] not in allowed:
                raise ValueError("a node binding must name an explicit dependency")
            out = results[value["$node"]]["output"]
            for part in value.get("path", []):
                out = out[part]
            return deepcopy(out)
        return {k: resolve(v, results, allowed) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve(v, results, allowed) for v in value]
    return value


class FlowService:
    def __init__(self, platform: Any) -> None:
        self.p = platform
        self.operators: dict[str, tuple[str, Any]] = {}

    def register_operator(self, name: str, version: str, handler: Any) -> None:
        """Host-owned, context-aware domain adapters; never load user code."""
        if name in self.operators or name in self.p.gateway.registry.policies:
            raise ValueError(f"operator already registered: {name}")
        self.operators[name] = (version, handler)

    def save(self, ctx: Any, flow_id: str, *, site_id: str, nodes: list[dict[str, Any]],
             expected_revision: int | None = None) -> dict[str, Any]:
        self.p.identity.require(ctx, "propose", "data_flow", flow_id, site_id=site_id)
        order = node_order(nodes)
        for n in nodes:
            if n["task_kind"] not in self.p.gateway.registry.policies and n["task_kind"] not in self.operators:
                raise ValueError(f"unknown task kind: {n['task_kind']}")
        with self.p.store.transaction(ctx.actor_id) as tx:
            old = tx.get(ctx.tenant_id, "data_flow", flow_id)
            if old and old.state["site_id"] != site_id:
                raise ValueError("flow site cannot be changed")
            rec = tx.put(ctx.tenant_id, "data_flow", flow_id,
                {"flow_id": flow_id, "site_id": site_id, "nodes": nodes, "order": order,
                 "definition_hash": content_hash(nodes), "runtime_version": "gateway-flow-v1",
                 "operator_versions": {n["task_kind"]: self.operators[n["task_kind"]][0]
                     for n in nodes if n["task_kind"] in self.operators}},
                expected_revision=expected_revision, action="save_data_flow", event_type="flow.saved")
        return {**rec.state, "revision": rec.revision}

    def create_run(self, ctx: Any, flow_id: str, *, inputs: list[dict[str, Any]]) -> dict[str, Any]:
        with self.p.store.transaction(ctx.actor_id) as tx:
            rec = tx.require(ctx.tenant_id, "data_flow", flow_id)
            self.p.identity.require(ctx, "propose", "data_flow", flow_id, site_id=rec.state["site_id"], tx=tx)
            rid = new_id("flowrun")
            if not inputs:
                # Literal calculations still have a durable source: the exact
                # configuration submitted by this person. This never implies
                # acquisition from a production system or instrument.
                tx.put(ctx.tenant_id, "flow_literal_input", rid,
                       {"site_id": rec.state["site_id"], "provided_by": ctx.actor_id,
                        "nodes": rec.state["nodes"], "source_type": "user_supplied_configuration"},
                       expected_revision=None, action="capture_flow_literals")
                inputs = [{"kind": "flow_literal_input", "id": rid, "revision": 1}]
            pinned = self.p.identity.validate_refs(ctx, inputs, require_current=True, tx=tx)
            state = {"run_id": rid, "flow_id": flow_id, "flow_revision": rec.revision,
                     "site_id": rec.state["site_id"], "definition": rec.state, "inputs": pinned,
                     "results": {}, "status": "pending", "issues": [], "requires_human_review": True}
            tx.put(ctx.tenant_id, "data_flow_run", rid, state, expected_revision=None,
                   action="create_flow_run", event_type="flow.run_created")
            for ref in pinned:
                tx.add_edge(ctx.tenant_id, (ref["kind"], ref["id"]), ("data_flow_run", rid), "flow_input")
        return state

    def run(self, ctx: Any, rid: str) -> dict[str, Any]:
        owner = new_id("flowworker")
        with self.p.store.transaction(ctx.actor_id) as tx:
            rec = tx.require(ctx.tenant_id, "data_flow_run", rid)
            self.p.identity.require(ctx, "propose", "data_flow", rec.state["flow_id"], site_id=rec.state["site_id"], tx=tx)
            if rec.state["status"] in ("stale", "quarantined"):
                raise ValueError("flow inputs were invalidated; prepare a new run")
            self.p.identity.validate_refs(ctx, rec.state["inputs"], require_current=True, tx=tx)
            token = tx.acquire_lease(ctx.tenant_id, "data_flow_run", rid, owner)
        try:
            definition = rec.state["definition"]
            by_id = {n["node_id"]: n for n in definition["nodes"]}
            for nid in definition["order"]:
                state = self.p.store.read().require(ctx.tenant_id, "data_flow_run", rid).state
                if state["results"].get(nid, {}).get("status") == "completed":
                    continue
                node = by_id[nid]
                self.p.identity.validate_refs(ctx, state["inputs"], require_current=True)
                try:
                    payload = resolve(node.get("payload", {}), state["results"], set(node.get("depends_on", [])))
                    name = node["task_kind"]
                    pinned = definition.get("operator_versions", {}).get(name)
                    if pinned:
                        registered = self.operators.get(name)
                        if not registered or registered[0] != pinned:
                            raise ValueError("domain operator changed; prepare a new flow")
                        result = registered[1](ctx, payload)
                    else:
                        result = self.p.gateway.run(TaskRequest(name, ctx, prompt=node.get("prompt", ""),
                            payload=payload, inputs=state["inputs"], timeout_s=60)).to_dict()
                except (KeyError, IndexError, TypeError, ValueError, PermissionError) as exc:
                    result = {"status": "blocked", "output": None, "issues": [f"node {nid}: {exc}"]}
                with self.p.store.transaction(ctx.actor_id) as tx:
                    tx.check_lease(ctx.tenant_id, "data_flow_run", rid, owner, token)
                    current = tx.require(ctx.tenant_id, "data_flow_run", rid)
                    if current.state["status"] in ("stale", "quarantined"):
                        raise PermissionError("flow invalidated during processing")
                    self.p.identity.require(ctx, "propose", "data_flow", state["flow_id"], site_id=state["site_id"], tx=tx)
                    self.p.identity.validate_refs(ctx, state["inputs"], require_current=True, tx=tx)
                    ok = result["status"] == "completed"
                    out = {**current.state, "results": {**current.state["results"], nid: result},
                           "status": "running" if ok else "blocked", "issues": result.get("issues", [])}
                    tx.put(ctx.tenant_id, "data_flow_run", rid, out, expected_revision=current.revision,
                           action="checkpoint_flow_node", event_type="flow.node_completed" if ok else "flow.node_blocked")
                    token = tx.acquire_lease(ctx.tenant_id, "data_flow_run", rid, owner)
                if not ok:
                    return out
            with self.p.store.transaction(ctx.actor_id) as tx:
                tx.check_lease(ctx.tenant_id, "data_flow_run", rid, owner, token)
                current = tx.require(ctx.tenant_id, "data_flow_run", rid)
                if current.state["status"] in ("stale", "quarantined"):
                    raise PermissionError("flow invalidated during processing")
                self.p.identity.validate_refs(ctx, current.state["inputs"], require_current=True, tx=tx)
                out = {**current.state, "status": "completed", "issues": []}
                tx.put(ctx.tenant_id, "data_flow_run", rid, out, expected_revision=current.revision,
                       action="complete_flow", event_type="flow.completed")
            return out
        finally:
            with self.p.store.transaction(ctx.actor_id) as tx:
                tx.check_lease(ctx.tenant_id, "data_flow_run", rid, owner, token)
                tx.expire_lease(ctx.tenant_id, "data_flow_run", rid)
