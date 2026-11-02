"""Evaluator-only recoverability labels after commitments, no agent feedback."""
from pathlib import Path
from collections import Counter
import json,argparse
from benchmarks.external_simulators.experiment import dump
from .pensim import ACTIONS,simulate,outcomes


def analyze(root):
    p=json.loads((root/'protocol.json').read_text());cases=json.loads((root/'private-catalogue.json').read_text());data=json.loads((root/'results.json').read_text())
    records=[]
    for item in cases:
        configs=next((c['private_action_replays_by_clock'] for c in data['cases'] if c['case_id']==item['case_id'] and c.get('private_action_replays_by_clock')), {})
        key=str(float(p['decision_h']))
        action_results=configs.get(key)
        if action_results is None:
            action_results={}
            for a in ACTIONS:
                try:action_results[a]=outcomes(simulate(p['paths'],**item['hidden'],action=a))
                except Exception as exc:action_results[a]={'model_domain_failure':str(exc),'post_decision_feasible':False}
        feasible=[a for a,v in action_results.items() if a!='stop' and v.get('post_decision_feasible')]
        failures=[a for a,v in action_results.items() if 'model_domain_failure' in v]
        actual='original_recipe_feasible' if 'keep' in feasible else 'recoverable_with_permitted_adjustment' if feasible else 'unknown_due_to_model_domain' if failures else 'no_feasible_operating_plan'
        records.append({'case_id':item['case_id'],'intended_stratum':item['stratum'],'realized_recoverability':actual,'feasible_actions':feasible,'domain_failed_actions':failures})
    receipt={'scope':'Private finite-menu replay at initial decision52h after all recommendations were fixed. Numerical failures do not imply necessary stopping.','independent_scenarios':len(records),'counts':dict(Counter(r['realized_recoverability'] for r in records)),'cases':records}
    dump(root/'recoverability.json',receipt);print(receipt['counts'])
    return receipt
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);a=p.parse_args();analyze(a.root)
