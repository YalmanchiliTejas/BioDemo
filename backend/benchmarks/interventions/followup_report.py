"""Recompute follow-up outcomes from immutable submissions and hidden replays."""
from pathlib import Path
import argparse
import json
import hashlib
import numpy as np
from benchmarks.external_simulators.experiment import dump, sha
from .followup_diagnosis import stopping_failures


def decision(record, menu_any):
    evaluation = record.get('evaluation')
    if not evaluation:
        return {'completed': 0, 'correct': 0, 'violating_operation': 0,
                'stop': 0, 'unnecessary_stop': 0, 'correct_stop': 0,
                'mass_kg': 0., 'feasible_mass_kg': 0., 'violation_h': None}
    outcome = evaluation['outcome']
    stopped = outcome['stopped']
    feasible = outcome['post_decision_feasible']
    return {'completed': 1, 'correct': int((stopped and not menu_any) or (not stopped and feasible)),
            'violating_operation': int(not stopped and not feasible), 'stop': int(stopped),
            'unnecessary_stop': int(stopped and menu_any), 'correct_stop': int(stopped and not menu_any),
            'mass_kg': outcome['product_mass_kg'],
            'feasible_mass_kg': outcome['product_mass_kg'] if feasible and not stopped else 0.,
            'violation_h': outcome['post_decision']['below_limit_h']}


def interval(values):
    values = np.asarray(values, dtype=float)
    if not len(values):
        return None
    rng = np.random.default_rng(20261101)
    ix = rng.integers(0, len(values), (20000, len(values)))
    return {'mean': float(values.mean()), 'interval95': np.quantile(values[ix].mean(axis=1), [.025, .975]).tolist(),
            'independent_scenarios': len(values), 'interpretation': 'unadjusted descriptive paired scenario bootstrap'}


def report(root, output):
    raw = json.loads((root / 'results.json').read_text())
    if raw['status'] != 'complete':
        raise ValueError('Cannot publish unfinished results')
    protocol = json.loads((root / 'protocol.json').read_text())
    if raw['protocol_sha256'] != sha(root / 'protocol.json'):
        raise ValueError('Protocol hash mismatch')
    coverage = []
    cases = []
    identity = []
    input_matches = []
    schema_matches = []
    failed_attempts = []
    unsafe_predictions = stopping_failures({'cases': [dict(c, repeat=1) for c in raw['cases']]})
    for case in raw['cases']:
        by = {r['arm']: r for r in case['records']}
        for arm, r in by.items():
            audit = r.get('capability_audit') or {}
            identity.append({'case_id': case['case_id'], 'arm': arm, 'model': r.get('model'),
                             'sdk_model': audit.get('model'), 'model_calls': r.get('model_calls'),
                             'completed': bool(r.get('evaluation'))})
            if not r.get('evaluation'):
                failed_attempts.append({'case_id': case['case_id'], 'arm': arm, 'status': r.get('status'), 'error': r.get('error')})
        if case['status'] != 'attempted':
            coverage.append({'case_id': case['case_id'], 'error': case.get('error')})
            continue
        if set(by) == {'A', 'B'}:
            packets = [root / 'attempts' / case['case_id'] / arm / 'packet.json' for arm in ['A', 'B']]
            input_matches.append(sha(packets[0]) == sha(packets[1]))
            audits = [by[a].get('capability_audit') or {} for a in ['A', 'B']]
            schema_matches.append(bool(audits[0].get('shared_tool_schema_sha256')) and
                                  audits[0].get('shared_tool_schema_sha256') == audits[1].get('shared_tool_schema_sha256'))
        row = {'case_id': case['case_id'], 'stratum': case['stratum'], 'mismatch': case['mismatch'], 'arms': {}}
        for arm in ['A', 'B']:
            r = by.get(arm, {})
            row['arms'][arm] = decision(r, r.get('menu_any_feasible', False))
            row['arms'][arm]['wall_seconds'] = r.get('wall_seconds')
        model = case['model_only']
        menus = case['private_menu_by_clock']['52.0']
        any_feasible = any(v['post_decision_feasible'] for v in menus.values())
        row['menu_any_feasible_at_initial_decision'] = any_feasible
        row['original_recipe_feasible'] = case['original_recipe']['post_decision_feasible']
        row['arms']['model_only'] = decision({'evaluation': {'outcome': model['outcome']}}, any_feasible)
        cases.append(row)
    summaries = {}
    for arm in ['A', 'B', 'model_only']:
        rs = [c['arms'][arm] for c in cases]
        summaries[arm] = {k: int(sum(r[k] for r in rs)) for k in ['completed', 'correct', 'violating_operation', 'stop', 'unnecessary_stop', 'correct_stop']}
        summaries[arm].update(n_scenarios=len(rs), mean_mass_kg=float(np.mean([r['mass_kg'] for r in rs])) if rs else None,
                             mean_feasible_mass_kg=float(np.mean([r['feasible_mass_kg'] for r in rs])) if rs else None)
    contrasts = {key: interval([c['arms']['B'][key] - c['arms']['A'][key] for c in cases])
                 for key in ['correct', 'violating_operation', 'mass_kg', 'feasible_mass_kg']}
    groups = {}
    for field, levels in [('stratum', protocol['strata']), ('mismatch', ['step_only', 'continued_decay'])]:
        for level in levels:
            selected = [c for c in cases if c[field] == level]
            groups[level] = {'n': len(selected), 'primary_contrast': interval([c['arms']['B']['correct']-c['arms']['A']['correct'] for c in selected]),
                             'arms': {a: {k: sum(c['arms'][a][k] for c in selected) for k in ['correct', 'violating_operation', 'unnecessary_stop']} for a in ['A', 'B', 'model_only']}}
    ledger = [json.loads(line) for line in (root / 'modal-admission.jsonl').read_text().splitlines()]
    reserved = {r['ordinal']: r['reserved_usd'] for r in ledger if r['event'] == 'reserved'}
    settled = {r['ordinal']: r for r in ledger if r['event'] == 'settled'}
    response_models = sorted({name for r in settled.values() for name in r.get('response_models', [])})
    budget = {'admitted_requests': len(reserved), 'settled_usage_requests': len(settled),
              'response_models': response_models,
              'held_or_estimated_usd': sum(settled[n]['conservative_cost_usd'] if n in settled else amount for n, amount in reserved.items()),
              'unsettled_full_reservations': len(set(reserved)-set(settled)),
              'denied_requests': sum(r['event'] == 'denied' for r in ledger),
              'invoice_verified': False, 'cap_usd': json.loads((root/'modal-budget-policy.json').read_text())['maximum_campaign_reservation_usd']}
    integrity = {'all_recorded_models_match': bool(identity) and all(r['model'] == protocol['model'] for r in identity),
                 'all_sdk_audits_match': bool(identity) and all(r['sdk_model'] == protocol['model'] for r in identity),
                 'endpoint_response_models': response_models, 'all_pair_packets_match': bool(input_matches) and all(input_matches),
                 'all_shared_tool_schemas_match': bool(schema_matches) and all(schema_matches),
                 'frozen_source_unchanged': all(sha(Path(f)) == h for f,h in protocol['code_sha256'].items()),
                 'results_sha256': sha(root / 'results.json'), 'protocol_sha256': sha(root / 'protocol.json')}
    supported = bool(cases) and len(cases) == protocol['independent_scenarios'] and contrasts['correct']['interval95'][0] > 0 and contrasts['violating_operation']['mean'] <= 0
    integrity_ok = all(integrity[k] for k in ['all_recorded_models_match', 'all_sdk_audits_match', 'all_pair_packets_match', 'all_shared_tool_schemas_match', 'frozen_source_unchanged'])
    verdict = 'supports_the_prespecified_simulated_decision_hypothesis' if supported and integrity_ok else 'does_not_establish_the_prespecified_decision_benefit'
    value = {'classification': 'exploratory_simulated_decisions_not_manufacturing_validation', 'verdict': verdict,
             'planned_scenarios': protocol['independent_scenarios'], 'summaries': summaries, 'paired_contrasts': contrasts,
             'groups': groups, 'cases': cases, 'coverage_failures': coverage, 'failed_attempts': failed_attempts,
             'known_infeasible_model_plan_selections': unsafe_predictions, 'model_identity_receipts': identity,
             'budget': budget, 'integrity': integrity}
    output.mkdir(parents=True, exist_ok=True)
    dump(output / 'analysis.json', value)
    lines = ['# GLM-5.3 + mechanistic model: fresh constrained-decision evaluation', '',
             f'**Verdict: {verdict.replace("_", " ")}.**', '',
             'The same Modal GLM-5.3 agent receives identical measured-in-simulation evidence. Only B has the source-calibrated mechanistic tool. Both use the same feasibility-first policy. No submitted action is silently overridden.', '',
             f"{protocol['independent_scenarios']} prespecified independent simulated scenarios; {protocol['planned_agent_sessions']} planned agent sessions. {len(cases)} scenarios have complete menu adjudication. Failures are retained. Half include continuing oxygen-transfer decay absent from the step-only prediction model.", '',
             '| Outcome | Agent alone A | Agent + model B | Conventional model-only selector |', '|---|---:|---:|---:|']
    for key, label in [('completed','Completed decisions'), ('correct','Correct constrained decisions'), ('violating_operation','Constraint-violating operating decisions'), ('correct_stop','Correct stops'), ('unnecessary_stop','Unnecessary stops'), ('mean_mass_kg','Mean simulated product inventory (kg)'), ('mean_feasible_mass_kg','Mean constraint-feasible inventory (kg)')]:
        vals = [summaries[a][key] for a in ['A','B','model_only']]
        lines.append('| '+label+' | '+' | '.join(f'{v:.3f}' if isinstance(v,float) else str(v) for v in vals)+' |')
    lines += ['', 'Correct means feasible operation when available, or stopping when no menu plan is feasible. Failed submissions count incorrect. Constraint-feasible inventory counts zero for a violation or stop; it is not measured product quality or released yield.', '',
              '## Paired differences, B minus A', '', '| Metric | Mean | Descriptive 95% interval |', '|---|---:|---|']
    for key, result in contrasts.items():
        if result:
            lines.append(f"| {key} | {result['mean']:.4f} | [{result['interval95'][0]:.4f}, {result['interval95'][1]:.4f}] |")
    lines += ['', 'Intervals resample scenarios, not calls. They are unadjusted exploratory estimates, not calibrated physical confidence or industry-wide reliability.', '',
              '## Prespecified subgroups', '', '| Group | Scenarios | Correct A | Correct B | Violating A | Violating B |', '|---|---:|---:|---:|---:|---:|']
    for name,g in groups.items():
        lines.append(f"| {name} | {g['n']} | {g['arms']['A']['correct']} | {g['arms']['B']['correct']} | {g['arms']['A']['violating_operation']} | {g['arms']['B']['violating_operation']} |")
    lines += ['', '## Provenance, cost and limitations', '',
              f"- Endpoint-reported models: {', '.join(response_models) or 'not available; do not claim server identity verified'}. Configured model: {protocol['model']}.",
              f"- Forwarded model requests: {budget['admitted_requests']}; usage settled: {budget['settled_usage_requests']}; denied: {budget['denied_requests']}.",
              f"- Token-rate estimate plus unresolved full reservations: ${budget['held_or_estimated_usd']:.4f}; admission cap ${budget['cap_usd']:.2f}. This is not a verified invoice or account-wide spending total.",
              f"- Known central-model-infeasible operating selections by B: {len(unsafe_predictions)}. Remaining failures are not hidden.",
              '- Predictor and evaluator share a mechanistic equation family; parameter mismatch and added transfer decay do not establish independent biological validity.',
              '- Source fitting was reused unchanged. The earlier real CHO agent comparison remains negative; the CHO model was not promoted to a qualified intervention model.',
              '- Earlier trials informed policy development. The new scenario seeds and analysis were frozen before inference; this remains an exploratory synthetic follow-up.',
              '- A model-only selector is a diagnostic comparator, not a measured human workflow. No engineer-time savings or manufacturing outcomes were measured.',
              '- The full 230-hour PenSim process remains unqualified; this study ends at 96 hours.', '',
              'Machine-readable analysis, every failed session, packet hashes, actual SDK model events and request-admission ledger are retained with the run.']
    (output / 'report.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'verdict':verdict,'summaries':summaries,'budget':budget,'integrity':integrity}), flush=True)
    return value


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    a = parser.parse_args()
    report(a.root.resolve(), a.output.resolve())
