"""Provider usage receipts without copying prompts, source text or credentials."""
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
