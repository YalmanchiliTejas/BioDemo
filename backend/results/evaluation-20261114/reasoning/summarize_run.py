"""Summarize original receipts without changing attempts or grading verdicts."""
import hashlib
import json
from pathlib import Path
import statistics

BASE = Path(__file__).resolve().parent
RUN = BASE / "run"


def load(path):
    return json.loads(path.read_text())


def stats(values):
    return {"count": len(values), "minimum": min(values) if values else None,
            "median": statistics.median(values) if values else None,
            "maximum": max(values) if values else None,
            "total": sum(values)}


report = load(RUN / "report.json")
assert report["summary"]["coverage"]["observed"] == report["summary"]["coverage"]["planned"], "Run is not complete"
protocol = load(BASE / "pilot-protocol.json")
addendum = load(BASE / "protocol-addendum.json")
for filename, expected in protocol["fixture_sha256"].items():
    assert hashlib.sha256((BASE / "fixtures" / filename).read_bytes()).hexdigest() == expected, filename
requests = [load(path) for path in sorted((RUN / "requests").glob("*.json"))]
assert len(requests) == report["budget"]["requests"]
assert all(row["status"] != "started" for row in requests), "Unsettled provider request"
individual = []
for result in sorted(report["results"], key=lambda r: r["episode_id"]):
    episode = RUN / result["episode_id"]
    observation = load(episode / "observation.json") if (episode / "observation.json").exists() else {}
    turns = observation.get("turns", [])
    individual.append({
        "episode_id": result["episode_id"], "status": result["status"],
        "failures": result.get("failures", []), "critical_failures": result.get("critical_failures", []),
        "agent_answer_seconds": observation.get("timing", {}).get("elapsed_seconds"),
        "agent_plus_judge_seconds": result.get("elapsed_seconds"),
        "provider_requests_agent": sum(x["purpose"] == "agent" for x in result.get("provider_requests", [])),
        "provider_requests_judge": sum(x["purpose"] == "judge" for x in result.get("provider_requests", [])),
        "provider_error_count": sum(x["status"] == "error" for x in result.get("provider_requests", [])),
        "host_errors": observation.get("errors", []), "judge_error": result.get("judge_error"),
        "turn_statuses": [turn.get("status") for turn in turns],
        "has_final_reply": bool(turns and turns[-1].get("reply")),
        "judge_reason": (result.get("judge") or {}).get("reason"),
        "observation_path": str((episode / "observation.json").relative_to(BASE)),
        "result_path": str((episode / "result.json").relative_to(BASE)),
    })
coverage = report["summary"]["coverage"]
summary = {
    "designation": protocol["designation"], "model": protocol["model"],
    "expert_reviewed": False, "externally_heldout": False,
    "planned": coverage["planned"], "completed_receipts": coverage["observed"],
    "passed": report["summary"]["passed"], "failed": report["summary"]["failed"],
    "not_graded": report["summary"]["not_graded"], "unexecuted": coverage["missing"],
    "passes_per_planned": report["summary"]["passed"] / coverage["planned"],
    "passes_per_graded": report["summary"]["pass_rate"],
    "user_answer_latency_seconds": stats([r["agent_answer_seconds"] for r in individual if r["agent_answer_seconds"] is not None]),
    "episode_including_judge_seconds": stats([r["agent_plus_judge_seconds"] for r in individual if r["agent_plus_judge_seconds"] is not None]),
    "campaign_wall_seconds": report["elapsed_seconds"],
    "provider_requests": len(requests),
    "provider_error_count": sum(x["status"] == "error" for x in requests),
    "estimated_token_cost_or_retained_reservations_usd": report["budget"]["accounted_usd"],
    "unknown_usage_requests": report["budget"]["unknown_usage_requests"],
    "actual_invoice_cost_usd": None,
    "tokens": {key: sum((r.get("usage") or {}).get(key) or 0 for r in requests)
               for key in ("prompt_tokens", "completion_tokens")},
    "provider_usage_by_purpose": {purpose: {
        "requests": sum(r["purpose"] == purpose for r in requests),
        "accounted_estimate_usd": sum(r["accounted_usd"] for r in requests if r["purpose"] == purpose),
        "unknown_usage_requests": sum(not r["usage_known"] for r in requests if r["purpose"] == purpose),
        "prompt_tokens": sum((r.get("usage") or {}).get("prompt_tokens") or 0 for r in requests if r["purpose"] == purpose),
        "completion_tokens": sum((r.get("usage") or {}).get("completion_tokens") or 0 for r in requests if r["purpose"] == purpose),
        "total_provider_seconds": sum(r.get("elapsed_seconds") or 0 for r in requests if r["purpose"] == purpose),
    } for purpose in ("agent", "judge")},
    "returned_model_identities": sorted({r["returned_model"] for r in requests if r.get("returned_model")}),
    "fixture_hashes_unchanged": True, "individual_results": individual,
    "limitations": protocol["limitations"] + addendum["additional_limitations"],
}
out = BASE / "measured-summary.json"
assert not out.exists(), "Do not overwrite an existing summary"
out.write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps(summary, indent=2))
