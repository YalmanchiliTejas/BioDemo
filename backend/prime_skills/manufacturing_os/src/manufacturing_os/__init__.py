"""Prime Agent skill client for a per-run scoped Manufacturing OS bridge."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class BridgeError(RuntimeError):
    """A rejected bridge request; the message carries the actionable reason."""


# Records this kernel has received, keyed by observation ID. Lookups through
# evidence() reuse them without another bridge call.
_EVIDENCE: dict[str, dict[str, Any]] = {}
_EVIDENCE_BATCH = 500


def _remember(result: Any) -> None:
    if not isinstance(result, dict):
        return
    records = list(result.get('records') or [])
    for packet in result.get('packets') or []:
        if isinstance(packet, dict):
            records.extend(packet.get('records') or [])
    for record in records:
        if isinstance(record, dict) and isinstance(record.get('id'), str):
            _EVIDENCE[record['id']] = record


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
        raise BridgeError("Manufacturing OS bridge is not configured")
    payload={**payload,'_caller':{'depth':int(os.environ.get('RLM_DEPTH','0'))}}
    request = Request(base.rstrip("/") + path,
                      data=json.dumps(payload).encode("utf-8"),
                      headers={"Authorization": f"Bearer {token}",
                               "Content-Type": "application/json"},
                      method="POST")
    # Errors are raised outside the except blocks with no chained context so the
    # cell output shows the reason, not several urllib traceback frames.
    error = None
    try:
        with urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(detail).get("error", detail)
        except (ValueError, AttributeError):
            pass
        error = f"Manufacturing OS bridge rejected {path}: {detail}"
    except URLError as exc:
        error = f"Manufacturing OS bridge unreachable for {path}: {exc.reason}"
    raise BridgeError(error)


def context() -> dict[str, Any]:
    return _post("/context", {})


def call_tool(name: str, **arguments: Any) -> dict[str, Any]:
    result = _post("/tool", {"name": name, "arguments": arguments})
    _remember(result)
    return result


def evidence(ids: list[str]) -> dict[str, Any]:
    """Records for observation IDs already retrieved by any agent in this run.

    Free: no tool budget is charged. Records cached in this kernel are returned
    without a bridge call; others come from the run-wide exposure set shared by
    the lead and specialists. IDs nobody has retrieved are listed in
    ``not_exposed`` and still need a scoped tool call.
    """
    if isinstance(ids, str):
        ids = [ids]
    wanted = list(dict.fromkeys(map(str, ids)))
    missing = [i for i in wanted if i not in _EVIDENCE]
    not_exposed: list[str] = []
    for start in range(0, len(missing), _EVIDENCE_BATCH):
        result = _post("/evidence", {"ids": missing[start:start + _EVIDENCE_BATCH]})
        _remember(result)
        not_exposed.extend(result.get("not_exposed") or [])
    return {"records": [_EVIDENCE[i] for i in wanted if i in _EVIDENCE],
            "not_exposed": not_exposed,
            "kernel_cache_hits": len(wanted) - len(missing),
            "budget_charged": False}


def submit_report(report: dict[str, Any]) -> dict[str, Any]:
    return _post('/subreport' if int(os.environ.get('RLM_DEPTH','0'))>0 else '/report', report)

def submit_subreport(report: dict[str, Any]) -> dict[str, Any]:
    return _post('/subreport',report)

def validate_report(report: dict[str, Any]) -> dict[str, Any]:
    return _post('/validate-report',report)


def work_queue(limit: int = 20) -> dict[str, Any]:
    return _post('/work-queue', {'limit': limit})


def allocate_work(**kwargs: Any) -> dict[str, Any]:
    return _post('/allocate-work', kwargs)


def save_progress(update: dict[str, Any]) -> dict[str, Any]:
    return _post('/progress', update)


def assemble_report(**kwargs: Any) -> dict[str, Any]:
    return _post('/assemble-report', kwargs)


def stopping_decision(**kwargs: Any) -> dict[str, Any]:
    return _post('/stopping-decision', kwargs)


def evidence_packet(requests: list[dict[str, Any]]) -> dict[str, Any]:
    return call_tool('evidence_packet', requests=requests)


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


def summarize_series(**kwargs: Any) -> dict:
    return call_tool("summarize_series", **kwargs)


def calculate_metrics(**kwargs: Any) -> dict:
    return call_tool("calculate_metrics", **kwargs)


def align_series(**kwargs: Any) -> dict:
    return call_tool("align_series", **kwargs)


__all__ = ["BridgeError", "context", "call_tool", "evidence", "submit_report", "inspect_data",
           "validate_report", "submit_subreport", "work_queue", "allocate_work", "save_progress",
           "assemble_report", "stopping_decision", "evidence_packet",
           "infer_schema", "reconcile_entities", "normalize_measurements",
           "query_data", "search_evidence", "verify_evidence", "extract_region",
           "get_process_context", "get_state_at", "summarize_series", "calculate_metrics", "align_series"]
