"""Export the completed study without credentials, private configuration or invented metrics."""
import csv
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'docs/case_studies/decision-followup-20261101'
RUN = ROOT / 'backend/results/interventions/decision-followup-final-20261101'
TARGET = ROOT / 'frontend/public/case-study-results/decision-followup'


def export():
    analysis = json.loads((SOURCE/'analysis.json').read_text())
    protocol = json.loads((RUN/'protocol.json').read_text())
    raw = json.loads((RUN/'results.json').read_text())
    if raw['status'] != 'complete' or analysis['coverage_failures'] or analysis['failed_attempts']:
        raise ValueError('This exporter requires the completed, fully adjudicated cohort')
    checks = analysis['integrity']
    if not all(checks[k] for k in ['all_recorded_models_match', 'all_sdk_audits_match', 'all_pair_packets_match', 'all_shared_tool_schemas_match', 'frozen_source_unchanged']):
        raise ValueError('Study integrity check failed')
    labels = {'keep':'Keep recipe', 'reduce_feed':'Reduce feed 20%', 'increase_air':'Increase air 15%',
              'combined':'Reduce feed 20% + air 15%', 'strong_feed_reduction':'Reduce feed 40% + air 15%', 'stop':'Stop run'}
    actions = {a:{k:0 for k in labels} for a in ['A','B']}
    cases = []
    failures = []
    for case in sorted(raw['cases'], key=lambda c:c['case_id']):
        row = {'case':case['case_id'], 'condition':case['stratum'], 'mismatch':case['mismatch']}
        for record in case['records']:
            arm = record['arm']
            action = record['submission']['action_id']
            outcome = record['evaluation']['outcome']
            actions[arm][action] += 1
            row.update({f'{arm}_action':labels[action], f'{arm}_feasible':outcome['post_decision_feasible'],
                        f'{arm}_stopped':outcome['stopped'], f'{arm}_mass_kg':outcome['product_mass_kg']})
            if arm=='B' and not outcome['stopped'] and not outcome['post_decision_feasible']:
                calls = [t for t in record['tools'] if t['name']=='physical_forward_model' and t['arguments']['action_id']==action]
                prediction = calls[-1]['result']['outcome_prediction'] if calls else None
                failures.append({'case':case['case_id'], 'action':labels[action],
                    'predicted_minimum_do':prediction['post_decision']['minimum_do_mg_l'] if prediction else None,
                    'simulated_minimum_do':outcome['post_decision']['minimum_do_mg_l'],
                    'violation_hours':outcome['post_decision']['below_limit_h'],
                    'any_feasible_plan':record['menu_any_feasible']})
        cases.append(row)
    first = raw['cases'][0]
    threshold = json.loads((RUN/'attempts'/first['case_id']/'A/packet.json').read_text())['minimum_do_mg_l']
    prior = json.loads((ROOT/'frontend/public/case-study-results/combined-physics/summary.json').read_text())
    payload = {'version':'decision-followup-public-v1',
        'date':datetime.fromisoformat(protocol['frozen_utc']).astimezone(ZoneInfo('America/Phoenix')).strftime('%B %-d, %Y'),
        'model':'GLM-5.3', 'provider':'Modal', 'classification':'Exploratory simulation',
        'scenarios':protocol['independent_scenarios'], 'sessions':protocol['planned_agent_sessions'],
        'summaries':analysis['summaries'], 'contrasts':analysis['paired_contrasts'], 'groups':analysis['groups'],
        'requests':analysis['budget']['admitted_requests'], 'response_models':analysis['budget']['response_models'],
        'actions':actions, 'action_labels':labels, 'cases':cases, 'failures':failures,
        'oxygen_limit_mg_l':threshold, 'earlier_cho':prior['cho'],
        'protocol_sha256':checks['protocol_sha256'], 'source_sha256':hashlib.sha256((SOURCE/'analysis.json').read_bytes()).hexdigest(),
        'source_record':'docs/case_studies/decision-followup-20261101/analysis.json'}
    TARGET.mkdir(parents=True,exist_ok=True)
    (TARGET/'summary.json').write_text(json.dumps(payload,indent=2)+'\n')
    data = ROOT/'frontend/data/decision-study.json'
    data.parent.mkdir(parents=True,exist_ok=True)
    data.write_text(json.dumps(payload,indent=2)+'\n')
    for name in ['report.md','analysis.json','decision-results.png','decision-results.svg']:
        shutil.copy2(SOURCE/name,TARGET/name)
    shutil.copy2(ROOT/'output/pdf/sievance-evaluation-20261101.pdf',TARGET/'summary.pdf')
    shutil.copy2(ROOT/'docs/research/decision-followup-protocol-20261101.md',TARGET/'methodology.md')
    with (TARGET/'decisions.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=list(cases[0]));writer.writeheader();writer.writerows(cases)
    print(json.dumps({'exported':str(TARGET),'scenarios':len(cases),'source_sha256':payload['source_sha256']}))


if __name__=='__main__':
    export()
