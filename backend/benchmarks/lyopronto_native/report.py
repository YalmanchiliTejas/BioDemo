"""Publish bounded native-agent results, including every planned case and failure."""
import argparse
from collections import Counter
import csv
import hashlib
import io
import json
import re
from pathlib import Path
import statistics
import zipfile

from .suite import ROOT,write,digest

LABELS={'report':'Scheduled calculations','recipe_selection':'Constrained recipe selection','missing_inputs':'Missing characterization','scope_limits':'Units and model limits'}
BASE=ROOT/'backend/results/lyopronto-native-20261108'


def publish(base=BASE/'frozen-v3',run=BASE/'agent-v1-executed'):
    out=ROOT/'frontend/public/research-results/lyopronto-native';out.mkdir(parents=True,exist_ok=True)
    protocol=json.loads((base/'protocol.json').read_text());results=json.loads((run/'results.json').read_text())
    found={r['case_id']:r for r in results['records']};rows=[];references={};inputs={}
    for path in sorted((base/'public').glob('*.json')):
        case=json.loads(path.read_text());ref=json.loads((base/'reference'/path.name).read_text());r=found.get(case['id'])
        inputs[case['id']]=case;references[case['id']]=ref
        rows.append({'id':case['id'],'family':case['family'],'passed':bool(r and r['verdict']['passed']),
            'expected_status':ref['required_status'],'answer_status':r['assessment']['answer_status'] if r and r['assessment'] else None,
            'turn_status':r['trace']['turn_status'] if r else 'not_started','seconds':r['elapsed_seconds'] if r else None,
            'solver_calls':r['solver_calls'] if r else 0,'assessment':r['assessment'] if r else None,
            'checks':r['verdict']['checks'] if r else {},'error':r['error'] if r else 'No recorded attempt',
            'failed_checks':[k for k,v in r['verdict']['checks'].items() if not v] if r else ['not_started'],
            'source_sha256':digest(case['source']),'reference_sha256':digest(ref),
            'context_metric_policy_mismatch':bool(r and r['assessment'] and r['verdict']['checks'].get('no_invented_recommendation') is False
                and r['assessment']['selected_recipe'] is None and r['assessment']['answer_status']=='out_of_scope'
                and any(n['summary']['last_dried_percent']>=99.99999 and abs(n['summary']['last_elapsed_h']-(r['assessment']['completion_h'] or 0))<.01 for n in r['trace']['native_simulations'])),
            'literal_field_mismatch':bool(r and r['assessment'] and r['verdict']['checks'].get('missing_evidence_identified') is False
                and all(re.search(r'(?<![\w.])'+re.escape(field)+r'(?![\w.])',' '.join(r['assessment']['missing_inputs'])+' '+r['assessment']['rationale']) for field in ref.get('required_missing',[])))})
    families=[{'id':k,'label':v,'total':sum(r['family']==k for r in rows),'passed':sum(r['passed'] and r['family']==k for r in rows),'literal_field_mismatches':sum(r['literal_field_mismatch'] and r['family']==k for r in rows)} for k,v in LABELS.items()]
    budget=results['budget'];settled=sum(r['accounted_usd'] for r in budget['records'] if r['usage_known'])
    data={'version':protocol['version'],'date':'2026-11-08','issue':'https://github.com/YalmanchiliTejas/BioDemo/issues/29',
        'total':len(rows),'passed':sum(r['passed'] for r in rows),'recorded':len(found),'families':families,'rows':rows,
        'model':'GLM-5.3','upstream_commit':protocol['upstream_commit'],'protocol_sha256':digest(protocol),
        'failures':dict(Counter(k for r in rows for k in r['failed_checks'])),
        'literal_field_mismatches':sum(r['literal_field_mismatch'] for r in rows),
        'context_metric_policy_mismatches':sum(r['context_metric_policy_mismatch'] for r in rows),
        'solver_calls':sum(r['solver_calls'] for r in rows),
        'mean_seconds':statistics.mean(r['seconds'] for r in rows if r['seconds'] is not None),
        'cost':{'requests':budget['requests'],'accounted_usd':budget['accounted_usd'],'settled_estimate_usd':settled,
            'unknown_reservations_usd':budget['accounted_usd']-settled,'unknown_requests':budget['unknown_usage_requests'],
            'limit_estimate_usd':budget['estimated_budget_usd'],'invoice_usd':None},
        'limits':protocol['agent_limits']}
    write(ROOT/'frontend/data/lyopronto-native-study.json',data);write(out/'results.json',data)
    write(out/'protocol.json',protocol);write(out/'public-inputs.json',inputs);write(out/'native-reference.json',references)
    write(out/'usage-receipts.json',budget)
    # Publish numerical evidence and reasoning, not local stores or configuration.
    write(out/'agent-evidence.json',[{'case_id':r['case_id'],'assessment':r['assessment'],'native_simulations':r['trace']['native_simulations'],
        'reply':r['trace']['reply'],'turn_status':r['trace']['turn_status'],'error':r['error'],'tool_steps':r['trace']['tool_steps']} for r in results['records']])
    stream=io.StringIO();writer=csv.DictWriter(stream,fieldnames=['id','family','passed','expected_status','answer_status','turn_status','seconds','solver_calls','failed_checks'])
    writer.writeheader()
    for row in rows:writer.writerow({k:';'.join(row[k]) if k=='failed_checks' else row[k] for k in writer.fieldnames})
    (out/'per-case.csv').write_text(stream.getvalue())
    text=f'''# Can the workspace agent use LyoPRONTO correctly?

{data['passed']}/{data['total']} fresh native-model cases passed all applicable checks. {data['recorded']} recorded sessions; every planned case remains in the denominator. One session per authored case, not a general reliability estimate. No comparison with our physical model is made.

'''
    text+='\n'.join(f"- {f['label']}: {f['passed']}/{f['total']}" for f in families)
    text+=f'''

## What changed
The old experiment swapped a tool inside BioDemo's reused synthetic world. This experiment replaces the inputs, tasks, reference, scoring and execution harness. LyoPRONTO knownRp in native units is both the agent's modeling tool and the independently executed numerical reference. No BioDemo physical model, old scorer, fitting channel or synthetic hot-vial correction enters the evaluation. The actual application conversation/ToolLoop/gateway/evidence/result path runs with a research-only typed connector in local isolated workspaces; it is not a deployed production integration.

## What a pass establishes
A supported task was completed using native simulation evidence or correctly identified missing/scope evidence. Numerical checks use drying-event completion, returned bottom temperature, per-area-to-whole-batch flux conversion and native equipment line a+b*P_Torr. Missing results and errors fail. Constrained decisions must select a complete feasible allowed recipe within 5% of the fastest feasible grid candidate. Infeasibility claims require execution of all candidates. Constraints are checked at returned nodes, not continuous maxima. A same-simulator reference measures scientific tool competence, not independent experimental prediction accuracy, causal proof, product quality, batch release or global optimization.

## Execution and costs
Model GLM-5.3; LyoPRONTO 1.2.0 commit {data['upstream_commit']}. Limits: 10 model calls, 16 tool calls, 300 seconds per loop and 12 native solver calls. {data['solver_calls']} solver calls; mean session time {data['mean_seconds']:.1f} sec. {data['cost']['requests']} admitted provider requests. Known-usage token estimate ${settled:.4f}; retained unknown reservations ${data['cost']['unknown_reservations_usd']:.4f}; conservative accounting ${data['cost']['accounted_usd']:.4f} under the $10 admission estimate. These are not provider invoices and exclude engineering and local solver compute. Shared provider queueing is included. No failed scored attempt was silently rerun.

## Failure checks
{json.dumps(data['failures'],indent=2)}

### Frozen-grader limitation, identified after inference began
The frozen missing-evidence check requires exact strings in missing_inputs. {data['literal_field_mismatches']} failed answers contain all required canonical field identifiers as complete tokens in their missing-input text or rationale, but do not use the exact required list entries. These are flagged per case as literal_field_mismatch; do not interpret that check as proof of a scientific misunderstanding. {data['context_metric_policy_mismatches']} out-of-scope answers also include a completion value supported by their native simulation context, with no recipe selection. The frozen envelope requires null completion for every unsupported task, so these fail that rule; the failure alone does not establish that the value or a plant claim was invented. These are flagged as context_metric_policy_mismatch. Scores are not changed retrospectively. The supplied statuses and numerical checks retain their original rules. This audit is post hoc and is not an independently blinded semantic review. Recognizing a field does not validate the explanation: the R0 missing-input answer describes it as a zero-pressure resistance term, whereas the native Rp = R0 + A1*L/(1+A2*L) makes R0 the zero-dried-layer-thickness intercept. The deterministic field-name score does not catch that terminology error.


## Evidence and reproduction
The protocol, environment versions, source hashes, public inputs and raw native reference trajectories were frozen before agent inference. Development qualification rejected an initial 6-minute horizon because its shelf ramp exceeded stage time; the final 60-minute truncation case preserves valid native schedule semantics. This happened before any agent inference. A scripted zero-inference application/solver preflight and 11 tests preceded the run. This is a small authored suite derived from one upstream example, not experimental data, a sealed broad generalization benchmark or a test of full production deployment. Scope/missing-evidence cases explicitly ask for appropriate status; those scores measure adherence on supplied questions, not spontaneous discovery of hidden incidents. Provider sampling defaults were used without a pinned inference seed; repeated agent answers may differ. The deterministic grader checks structured numerical decisions; it does not independently judge every sentence of rationale or final prose.

Private references were outside the agent workspace and tools; no shell tool was exposed. The tools preserve evidence IDs and source revisions, and save drafts requiring review. No manufacturing operation or approval was authorized.

Run source in reproduce.zip requires the application repository and separate unmodified GPL-3.0-or-later LyoPRONTO checkout at the recorded pin. No upstream or proprietary SDK software is redistributed. See https://github.com/LyoHUB/LyoPRONTO and {data['issue']}.

The rejected tool-swap experiment remains at /research/lyohub/archive/tool-swap/ with its original evidence. Its model rankings do not establish superiority.
'''
    (out/'report.md').write_text(text)
    with zipfile.ZipFile(out/'reproduce.zip','w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted((ROOT/'backend/benchmarks/lyopronto_native').glob('*')):
            if p.is_file():z.write(p,str(p.relative_to(ROOT)))
        z.write(ROOT/'backend/tests/test_lyopronto_native.py','backend/tests/test_lyopronto_native.py')
        for name in ('protocol.json','public-inputs.json','native-reference.json'):z.write(out/name,name)
    manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.iterdir()) if p.is_file() and p.name!='manifest.json'}
    write(out/'manifest.json',manifest)
    doc=ROOT/'docs/research/lyopronto-native-20261108';doc.mkdir(parents=True,exist_ok=True)
    for name in ('report.md','protocol.json','results.json','per-case.csv','manifest.json'):(doc/name).write_bytes((out/name).read_bytes())
    return {k:data[k] for k in ('total','passed','families','cost','failures')}


if __name__=='__main__':print(json.dumps(publish(),indent=2))
