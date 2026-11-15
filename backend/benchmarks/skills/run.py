"""Run the skill benchmarks and write a report that says where the product is lacking, not only how often.

    .venv/bin/python -I backend/benchmarks/skills/run.py --output backend/results/<new-directory>
    .venv/bin/python -I backend/benchmarks/skills/run.py --download            # fetch the public datasets first
    ... --decision-model       # also run the Jev arm (reads TYPESAFE_API_KEY from backend/.env.local; costs cents)

Everything except the decision-model arm runs without any model and without the network. Each case ends in one
named outcome; the report groups them by skill and by what made the case hard.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))  # run with -I: nothing but this path and the environment's packages is importable

from benchmarks.skills import datasets, distillation, skills, worlds  # noqa: E402
from benchmarks.skills.core import Case, Row, markdown, summarize  # noqa: E402

HOST = {'cho': (worlds.cho_world, (skills.compare_cases, skills.analyst_cases)),
        'tablet': (worlds.tablet_world, (skills.fair_comparison_cases, skills.gap_cases, skills.trace_usage_cases)),
        'fda_drug_recalls': (worlds.recall_world, (skills.recall_cases,)),
        'distillation': (distillation.world, (distillation.detection_cases, distillation.change_cases, distillation.cause_cases))}
skills.SKILLS.update(distillation.SKILLS)
INTENTS, PER_INTENT, OUT_OF_SCOPE, PER_REQUEST = 20, 30, 600, 20


def run_host(selected) -> tuple[list[Row], dict]:
    rows, built = [], {}
    wanted = {skill.datasets[0] for key, skill in skills.SKILLS.items() if not selected or key in selected}
    for dataset, (make, builders) in HOST.items():
        if dataset not in wanted:
            continue
        started = time.perf_counter()
        world = make()
        cases = [c for build in builders for c in build(world) if not selected or c.skill in selected]
        built[dataset] = {'seconds_to_load': round(time.perf_counter() - started, 1), 'cases': len(cases), 'added_by_the_benchmark': world['added']}
        for case in cases:
            try:
                response, seconds = skills.timed(case, world)
                outcome, reason = case.score(case, response)
            except Exception as exc:  # a crash in the product is a result; a crash in the benchmark must be visible too
                outcome, reason, seconds = 'error', f'{type(exc).__name__}: {str(exc)[:160]}', None
            rows.append(Row(case.id, case.skill, case.dataset, case.arm, case.tags, outcome, reason, seconds))
        if dataset == 'distillation' and any(c.skill == 'rank_causes' for c in cases):
            built[dataset]['where_the_true_cause_sits'] = distillation.position_summary(rows, world)
        if dataset == 'distillation' and any(c.skill == 'detect_deviation' for c in cases):
            built[dataset]['anomalous_runs_with_limits_alone_no_trend_rule'] = distillation.limits_alone(world)
        world['p'].store.release_connections()
        print(f"{dataset}: {len(cases)} cases in {time.perf_counter() - started:.1f} s", flush=True)
    return rows, built


def run_decision_model(seed: int = 417) -> tuple[list[Row], dict]:
    """Real requests, 20 intents and "unknown". Half the requests fit none of the 20. What matters is not only how
    often the model is right, but whether its probability tells right from wrong: that decides if it may act alone."""
    from src.lifesci.envfile import parse_env
    from src.lifesci.gateway.decisions import UNKNOWN, DecisionRequest, Question
    local = BACKEND / '.env.local'
    for name, value in (parse_env(local.read_text()) if local.is_file() else {}).items():
        if name.startswith(('TYPESAFE_', 'LIFESCI_DECISION_')) and value:
            os.environ.setdefault(name, value)
    p = worlds.platform()
    ctx = worlds.person(p, 'INTENTS')
    adapter = p.gateway.decisions
    if not adapter.enabled:
        return [], {'status': 'not_run', 'reason': adapter.configuration_issue or 'the decision model is not configured'}
    data = json.loads(datasets.path('clinc150', 'data_full.json').read_text())
    rng = random.Random(seed)
    intents = sorted(rng.sample(sorted({label for _, label in data['test']}), INTENTS))
    items = [(text, label) for label in intents for text, _ in rng.sample([x for x in data['test'] if x[1] == label], PER_INTENT)]
    items += [(text, UNKNOWN) for text, _ in rng.sample(data['oos_test'], OUT_OF_SCOPE)]
    rng.shuffle(items)
    choices = {**{label: label.replace('_', ' ') for label in intents}, UNKNOWN: 'none of these'}
    rows, samples, latency, cost = [], [], [], 0.0
    for start in range(0, len(items), PER_REQUEST):
        batch = items[start:start + PER_REQUEST]
        questions = [Question(f'q{i}', 'choice', f'Which intent does this request express: "{text}"? Choose unknown if none fits.', choices=choices)
                     for i, (text, _) in enumerate(batch)]
        adapter.gateway._down_until.clear()  # each batch is measured on its own
        result = adapter.decide(DecisionRequest('benchmark_intent', ctx, {'task': 'match each request to one intent'}, questions))
        latency.append(result.latency_ms)
        cost += result.cost_usd or 0.0
        for i, (text, label) in enumerate(batch):
            scope = 'fits one of the intents' if label != UNKNOWN else 'fits none of the intents'
            if result.status != 'completed':
                rows.append(Row(f'intent:{start + i}', 'intent_abstention', 'clinc150', 'decision_model', (scope,), 'error', result.reason, None))
                continue
            answer = result.decisions[f'q{i}']
            samples.append({'probability': answer.probability, 'correct': answer.value == label, 'in_scope': label != UNKNOWN,
                            'chose_unknown': answer.value == UNKNOWN})
            outcome = ('correct' if answer.value == label else 'abstained_unnecessarily' if answer.value == UNKNOWN
                       else 'should_have_abstained' if label == UNKNOWN else 'wrong_value')
            reason = {'correct': '', 'abstained_unnecessarily': 'said unknown for a request that fits an intent',
                      'should_have_abstained': 'chose an intent for a request that fits none', 'wrong_value': 'chose the wrong intent'}[outcome]
            rows.append(Row(f'intent:{start + i}', 'intent_abstention', 'clinc150', 'decision_model', (scope,), outcome, reason,
                            result.latency_ms / 1000 / len(batch), {'probability': answer.probability}))
    p.store.release_connections()
    # Could a threshold on the probability make it safe to act without a person? Acting = choosing an intent.
    acted = sorted((s for s in samples if not s['chose_unknown']), key=lambda s: -s['probability'])
    sweep = []
    for threshold in (0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99):
        kept = [s for s in acted if s['probability'] >= threshold]
        sweep.append({'threshold': threshold, 'acted_on': len(kept), 'right': sum(s['correct'] for s in kept),
                      'precision': sum(s['correct'] for s in kept) / len(kept) if kept else None,
                      'share_of_in_scope_requests_handled': sum(s['correct'] for s in kept) / max(sum(s['in_scope'] for s in samples), 1)})
    bins = []
    for low in (0.0, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95):
        high = {0.0: 0.5, 0.5: 0.6, 0.6: 0.7, 0.7: 0.8, 0.8: 0.9, 0.9: 0.95, 0.95: 1.01}[low]
        inside = [s for s in acted if low <= s['probability'] < high]
        bins.append({'probability': f'{low:.2f}-{min(high, 1.0):.2f}', 'answers': len(inside),
                     'right': sum(s['correct'] for s in inside), 'observed_rate': sum(s['correct'] for s in inside) / len(inside) if inside else None})
    return rows, {'status': 'run', 'model': adapter.model, 'requests': len(latency), 'questions': len(items), 'intents': intents,
                  'mean_ms_per_request': sum(x for x in latency if x) / max(len([x for x in latency if x]), 1), 'cost_usd': round(cost, 5),
                  'threshold_sweep': sweep, 'reliability': bins,
                  'reading': 'observed_rate is how often answers in that probability band were right. If the probability were '
                             'calibrated, the observed rate would sit inside the band.'}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--download', action='store_true', help='Fetch the public datasets into backend/.cache and stop.')
    parser.add_argument('--skills', default='', help='Comma-separated skill ids; all when empty.')
    parser.add_argument('--decision-model', action='store_true')
    args = parser.parse_args(argv)
    if args.download:
        for dataset, spec in datasets.DATASETS.items():
            for name in spec['files']:
                if dataset != 'fda_device_recalls':
                    print(dataset, name, datasets.path(dataset, name, download=True).stat().st_size, 'bytes')
        return 0
    if not args.output or args.output.exists():
        parser.error('give a new --output directory')
    selected = {s for s in args.skills.split(',') if s}
    started = datetime.now(timezone.utc).isoformat()
    rows, built = run_host(selected)
    decision = {'status': 'not_requested'}
    if args.decision_model and (not selected or 'intent_abstention' in selected):
        more, decision = run_decision_model()
        rows += more
    summary = summarize(rows)
    used = sorted({r.dataset for r in rows})
    report = {'schema_version': 'skill-benchmarks-v1', 'started_at': started,
              'skills': {k: s.__dict__ for k, s in skills.SKILLS.items()}, 'datasets': datasets.provenance(used), 'worlds': built,
              'summary': summary, 'decision_model': decision,
              'outcomes': dict(Counter(r.outcome for r in rows)),
              'limits': ['Public data from laboratories, one manufacturer and regulators; not your sites.',
                         'The data was loaded directly as deliveries in review. Reading messy files is measured elsewhere.',
                         'Specifications and readable names were added where the report says so; nothing else was.',
                         'Host-arm cases use no model. They say nothing about the assistant.'],
              'rows': [r.__dict__ for r in rows]}
    args.output.mkdir(parents=True)
    (args.output / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False, default=lambda o: sorted(o) if isinstance(o, set) else str(o)) + '\n')
    text = '# Skill benchmarks\n\n' + f'Started {started}.\n\n' + markdown(summary, skills.SKILLS)
    if decision.get('status') == 'run':
        text += '\n### Can the decision model act without a person?\n\n| Act when probability is at least | Acted on | Right | Precision | In-scope requests handled |\n|---:|---:|---:|---:|---:|\n'
        for s in decision['threshold_sweep']:
            text += f"| {s['threshold']:.2f} | {s['acted_on']} | {s['right']} | {(s['precision'] or 0):.1%} | {s['share_of_in_scope_requests_handled']:.0%} |\n"
        text += '\n| Probability band | Answers | Right | Observed rate |\n|---|---:|---:|---:|\n'
        for b in decision['reliability']:
            text += f"| {b['probability']} | {b['answers']} | {b['right']} | {'n/a' if b['observed_rate'] is None else format(b['observed_rate'], '.0%')} |\n"
    text += '\nLimits: ' + ' '.join(report['limits']) + '\n'
    (args.output / 'report.md').write_text(text)
    print(text)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
