"""Prime Agent skill client for a per-run scoped Manufacturing OS bridge."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def _post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    # A resumed Prime session can keep the same Python kernel. Read the current
    # endpoint on every call rather than retaining a dead prior-run port/token.
    config_path = os.environ.get("BIODEMO_PRIME_BRIDGE_CONFIG")
    if config_path:
        config = json.loads(Path(config_path).read_text(encoding="utf-8"))
        base, token = config.get("url"), config.get("token")
    else:
        base = os.environ.get("BIODEMO_PRIME_BRIDGE_URL")
        token = os.environ.get("BIODEMO_PRIME_BRIDGE_TOKEN")
    if not base or not token:
        raise RuntimeError("Manufacturing OS bridge is not configured")
    request = Request(base.rstrip("/") + path,
                      data=json.dumps(payload).encode("utf-8"),
                      headers={"Authorization": f"Bearer {token}",
                               "Content-Type": "application/json"},
                      method="POST")
    try:
        with urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Manufacturing OS bridge rejected {path}: {detail}") from exc


def context() -> dict[str, Any]:
    return _post("/context", {})


def call_tool(name: str, **arguments: Any) -> dict[str, Any]:
    return _post("/tool", {"name": name, "arguments": arguments})


def submit_report(report: dict[str, Any]) -> dict[str, Any]:
    return _post("/report", report)


def inspect_data(**kwargs: Any) -> dict[str, Any]:
    return call_tool("inspect_data", **kwargs)


def infer_schema(**kwargs: Any) -> dict[str, Any]:
    return call_tool("infer_schema", **kwargs)


def reconcile_entities(**kwargs: Any) -> dict[str, Any]:
    return call_tool("reconcile_entities", **kwargs)


def normalize_measurements(**kwargs: Any) -> dict[str, Any]:
    return call_tool("normalize_measurements", **kwargs)


def query_data(**kwargs: Any) -> dict[str, Any]:
    return call_tool("query_data", **kwargs)


def search_evidence(**kwargs: Any) -> dict[str, Any]:
    return call_tool("search_evidence", **kwargs)


def verify_evidence(**kwargs: Any) -> dict[str, Any]:
    return call_tool("verify_evidence", **kwargs)


def extract_region(**kwargs: Any) -> dict[str, Any]:
    return call_tool("extract_region", **kwargs)


def get_process_context(**kwargs: Any) -> dict[str, Any]:
    return call_tool("get_process_context", **kwargs)


def get_state_at(**kwargs: Any) -> dict[str, Any]:
    return call_tool("get_state_at", **kwargs)


__all__ = ["context", "call_tool", "submit_report", "inspect_data",
           "infer_schema", "reconcile_entities", "normalize_measurements",
           "query_data", "search_evidence", "verify_evidence", "extract_region",
           "get_process_context", "get_state_at"]
