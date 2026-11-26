"""Provider usage receipts without copying prompts, source text or credentials."""
from hashlib import sha256
import json
from pathlib import Path


def session_usage(directory):
    """Keep native per-session own usage separate from attributed aggregates.

    Assistant entries can include child usage folded into the parent. Subtract
    explicit attributions before adding sessions to avoid double counting.
    In-flight/unpersisted calls and unpriced models remain unmeasured.
    """
    sessions=[]
    for path in sorted(Path(directory).rglob('*.jsonl')):
        entries=[]
        for line in path.read_text(errors='replace').splitlines():
            try:entries.append(json.loads(line))
            except ValueError:continue
        messages={e.get('id'):e for e in entries if e.get('type')=='message' and e.get('message',{}).get('role')=='assistant'}
        attribution={}
        for e in entries:
            if e.get('type')=='child_usage_attributed':
                target=e.get('targetId');u=e.get('childUsage') or {}
                for key in ('input','output','cacheRead','cacheWrite'):
                    attribution.setdefault(target,{}).setdefault(key,0)
                    attribution[target][key]+=u.get(key,0)
        totals={k:0 for k in ('input','output','cacheRead','cacheWrite')};calls=[]
        for identifier,e in messages.items():
            m=e['message'];u=m.get('usage') or {}
            own={k:max(0,u.get(k,0)-attribution.get(identifier,{}).get(k,0)) for k in totals}
            for k in totals:totals[k]+=own[k]
            calls.append({'message_id':identifier,'recorded_at':e.get('timestamp'),
                          'provider':m.get('provider'),'model':m.get('model'),'own_tokens':own,
                          'provider_reported_cost':(u.get('cost') or {}).get('total')})
        if messages:sessions.append({'session_file':str(path.relative_to(directory)),'own_tokens':totals,'calls':calls})
    return {'version':'provider-session-telemetry-v1','sessions':sessions,
            'model_calls_recorded':sum(len(s['calls']) for s in sessions),
            'tokens_recorded':{k:sum(s['own_tokens'][k] for s in sessions) for k in ('input','output','cacheRead','cacheWrite')},
            'total_cost_usd':None,'coverage':'Persisted SDK session files only; interrupted/unpersisted calls and local compute may be missing.',
            'timing_limit':'Native timestamps are completion receipts, not provider-call starts; root host records explicit start/end separately.'}

def host_receipt(stdout, *, trace_sink, model, system_prompt):
    """Read resumable session, task response and root usage from SDK events."""
    prompt_version = sha256(system_prompt.encode()).hexdigest()
    session_id = session_file = None
    task_response = None
    usage = {"model_calls": 0, "input_tokens": 0, "output_tokens": 0,
             "cached_input_tokens": 0, "inference_cost_usd": None,
             "total_cost_usd":None, "cost_status":"unknown_provider_or_child_telemetry",
             "root_reported_cost_usd":0.0}
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == "session" and event.get("id"):
            session_id, session_file = str(event["id"]), event.get("file")
            if event.get("model"):
                usage["model_id"] = event["model"]
        if event.get('type')=='task_answer':
            task_response=event.get('response')
        if event.get("type") == "message_end" and event.get("message", {}).get("role") == "assistant":
            tokens = event["message"].get("usage")
            if isinstance(tokens, dict):
                usage["model_calls"] += 1
                usage["input_tokens"] += int(tokens.get("input", 0))
                usage["output_tokens"] += int(tokens.get("output", 0))
                usage["cached_input_tokens"] += int(tokens.get("cacheRead", 0))
                usage["root_reported_cost_usd"] += float((tokens.get("cost") or {}).get("total", 0.0))
                if trace_sink is not None:
                    trace_sink.emit(actor="agent", stage="analysis", action="model_usage",
                                         model_id=usage.get("model_id", model),
                                         prompt_version=prompt_version,
                                         input_tokens=tokens.get("input"), output_tokens=tokens.get("output"),
                                         estimated_cost_usd=(tokens.get("cost") or {}).get("total"),
                                         started_at=event.get('started_at'),ended_at=event.get('ended_at'),
                                         usage_scope="root_sdk_session_only")
    return session_id, session_file, task_response, usage
