"""Capture generated demo conversations through an already authenticated browser.

Credentials stay inside the browser. Only explicitly enabled demo threads may be
exported; account identifiers and auth-bearing fields are removed recursively.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

PRIVATE_KEYS = {'access_token', 'refresh_token', 'authorization', 'password', 'email',
                'tenant_id', 'actor_id', 'owner_id', 'user_id', 'partner_org_id',
                'api_key', 'headers', 'endpoint', 'base_url'}


def redact(value):
    if isinstance(value, dict):
        return {k: redact(v) for k, v in value.items() if k.lower() not in PRIVATE_KEYS}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


def capture(browser, session, thread_id=None, delivery_run_id=None):
    script = """(async()=>{
      const entry=Object.entries(localStorage).find(([k])=>k.startsWith('sb-')&&k.endsWith('-auth-token'));
      if(!entry)throw Error('Sign in to the app first');
      const s=JSON.parse(entry[1]);
      const org=localStorage.getItem('sievance.organization:'+s.user.id);
      const headers={Authorization:'Bearer '+s.access_token,'X-Organization-Id':org};
      const get=async path=>{const r=await fetch('https://api.sievance.com'+path,{headers});if(!r.ok)throw Error('Demo API HTTP '+r.status);return r.json();};
      const id=THREAD_ID;
      const thread=await get('/v1/process-model/conversations/'+encodeURIComponent(id));
      if(thread.demo_enabled!==true)throw Error('Export is limited to explicitly enabled demo threads');
      const artifacts=[];
      for(const turn of thread.turns??[])for(const a of turn.artifacts??[]){
        const value=await get('/v1/process-model/conversations/'+encodeURIComponent(id)+'/artifacts/'+encodeURIComponent(a.kind)+'/'+encodeURIComponent(a.id));
        artifacts.push({turn_id:turn.id,kind:a.kind,id:a.id,data:value});
      }
      return {thread,artifacts};
    })()""".replace('THREAD_ID', json.dumps(thread_id))
    if delivery_run_id:
        script = """(async()=>{
          const entry=Object.entries(localStorage).find(([k])=>k.startsWith('sb-')&&k.endsWith('-auth-token'));
          if(!entry)throw Error('Sign in first');
          const s=JSON.parse(entry[1]);
          const headers={Authorization:'Bearer '+s.access_token,'X-Organization-Id':localStorage.getItem('sievance.organization:'+s.user.id)};
          const r=await fetch('https://api.sievance.com/api/cmo-ingestion/runs/'+encodeURIComponent(RUN_ID),{headers});
          if(!r.ok)throw Error('Demo delivery HTTP '+r.status);
          const delivery=await r.json();
          if(delivery.cmo!=='Sievance public demo 2026-10-31')throw Error('Only this explicitly labeled demo workspace may be exported');
          return {delivery};
        })()""".replace('RUN_ID', json.dumps(delivery_run_id))
    encoded = base64.b64encode(script.encode()).decode()
    result = subprocess.run([str(browser), '--session', session, 'eval', '-b', encoded],
                            capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise RuntimeError('Browser demo capture failed: ' + result.stderr[-500:])
    return redact(json.loads(result.stdout))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--browser', type=Path, required=True)
    parser.add_argument('--session', required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--thread-id')
    source.add_argument('--delivery-run-id')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Use a new output path; original captures are never overwritten')
    record = {'version': 'sievance-live-delivery-v1' if args.delivery_run_id else 'sievance-live-demo-v1', 'captured_at': datetime.now(timezone.utc).isoformat(),
              'origin': 'https://www.sievance.com', 'execution': 'live_authenticated_app',
              'data_classification': 'explicitly_enabled_published_or_synthetic_demo',
              'scientific_review': 'not_independently_reviewed', 'provider_billed_cost_usd': None,
              **capture(args.browser, args.session, args.thread_id, args.delivery_run_id)}
    record['capture_sha256'] = hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps({'output': str(args.output), 'sha256': record['capture_sha256'],
                      'turns': len(record.get('thread', {}).get('turns', [])), 'artifacts': len(record.get('artifacts', []))}))


if __name__ == '__main__':
    main()
