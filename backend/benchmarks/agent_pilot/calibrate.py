"""Measure whether the semantic judge agrees with a human before trusting its PASS.

  export: write a blind labeling sheet (judge verdicts hidden, shuffled order).
  score:  compare filled human labels with the judge; report agreement, Cohen's
          kappa and the dangerous cell: judge PASS where the human said FAIL.

Run from backend:
  .venv/bin/python -m benchmarks.agent_pilot.calibrate export RESULTS_DIR labels.csv [--limit 50]
  .venv/bin/python -m benchmarks.agent_pilot.calibrate score RESULTS_DIR labels.csv
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import random

COLUMNS = ['episode_id', 'case_id', 'prompt', 'required_facts', 'forbidden_claims', 'final_replies',
           'sources_read', 'human_verdict', 'human_unsupported_claims', 'labeler', 'notes']


def _episodes(results_dir: Path):
    for d in sorted(p for p in Path(results_dir).iterdir() if (p / 'result.json').exists()):
        yield d, json.loads((d / 'reference.json').read_text()), json.loads((d / 'result.json').read_text())


def export(results_dir, out, limit=50, seed=20261104):
    rows = []
    for d, case, _ in _episodes(results_dir):
        obs = json.loads((d / 'observation.json').read_text())
        replies = '\n---\n'.join(t.get('reply') or '' for t in obs.get('turns', []))
        sources = '\n---\n'.join(f"[{s['source_id']}] {s['content'][:1500]}" for s in obs.get('source_revisions', []))
        rows.append({'episode_id': d.name, 'case_id': case['id'], 'prompt': case['prompt'],
                     'required_facts': '; '.join(case['truth'].get('required_facts', [])),
                     'forbidden_claims': '; '.join(case['truth'].get('forbidden_claims', [])),
                     'final_replies': replies, 'sources_read': sources,
                     'human_verdict': '', 'human_unsupported_claims': '', 'labeler': '', 'notes': ''})
    random.Random(seed).shuffle(rows)  # order must not reveal family or pass/fail clustering
    with open(out, 'w', newline='') as f:
        w = csv.DictWriter(f, COLUMNS)
        w.writeheader()
        w.writerows(rows[:limit])
    return len(rows[:limit])


def kappa(pairs):
    n = len(pairs)
    if not n:
        return None
    po = sum(a == b for a, b in pairs) / n
    pa, pb = sum(a for a, _ in pairs) / n, sum(b for _, b in pairs) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def score(results_dir, labels):
    judged = {}
    for d, _, result in _episodes(results_dir):
        semantic = result.get('checks', {}).get('semantic_judge', {})
        if type(semantic.get('passed')) is bool:
            judged[d.name] = semantic['passed']
    pairs, disagreements, unlabeled, ungraded = [], [], 0, 0
    with open(labels, newline='') as f:
        for row in csv.DictReader(f):
            verdict = row['human_verdict'].strip().upper()
            if verdict not in ('PASS', 'FAIL'):
                unlabeled += 1
                continue
            if row['episode_id'] not in judged:
                ungraded += 1
                continue
            human, judge = verdict == 'PASS', judged[row['episode_id']]
            pairs.append((human, judge))
            if human != judge:
                disagreements.append({'episode_id': row['episode_id'], 'human': verdict,
                                      'judge': 'PASS' if judge else 'FAIL', 'notes': row['notes']})
    n = len(pairs)
    cell = lambda h, j: sum(p == (h, j) for p in pairs)
    return {'labeled_pairs': n, 'unlabeled_rows': unlabeled, 'judge_ungraded_rows': ungraded,
            'agreement': sum(h == j for h, j in pairs) / n if n else None, 'cohen_kappa': kappa(pairs),
            'confusion': {'human_pass_judge_pass': cell(True, True), 'human_fail_judge_fail': cell(False, False),
                          'human_fail_judge_pass': cell(False, True), 'human_pass_judge_fail': cell(True, False)},
            # The cell that lets nonsense reach customers.
            'judge_false_pass_rate': cell(False, True) / max(1, cell(False, True) + cell(False, False)),
            'disagreements': disagreements,
            'interpretation': 'Small n: one label moves agreement by 1/n. Trust judge PASS only when false-pass '
                              'rate is low on enough human FAIL labels to matter (aim for 15+).'}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    e = sub.add_parser('export'); e.add_argument('results', type=Path); e.add_argument('out', type=Path)
    e.add_argument('--limit', type=int, default=50)
    s = sub.add_parser('score'); s.add_argument('results', type=Path); s.add_argument('labels', type=Path)
    args = ap.parse_args()
    if args.cmd == 'export':
        if args.out.exists():
            ap.error('refusing to overwrite an existing labeling sheet')
        print(json.dumps({'rows': export(args.results, args.out, args.limit), 'sheet': str(args.out)}))
    else:
        print(json.dumps(score(args.results, args.labels), indent=2))


if __name__ == '__main__':
    main()
