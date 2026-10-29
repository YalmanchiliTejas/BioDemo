"""Replay actual deterministic tools/decisions without making model calls.

This checks reproducibility, not independent scientific correctness of prose.
General-purpose numerical outputs are retained but not executed a second time.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path

from .generate import digest, dump
from .run_agents import HostTools


def canonical(value):
    return json.dumps(value, sort_keys=True, allow_nan=False)


def review(dataset: Path, run: Path, *, allow_running=False):
    dataset, run = Path(dataset).resolve(), Path(run).resolve()
    source = (run / 'results.json').read_bytes()
    data = json.loads(source)
    if data['status'] != 'complete' and not allow_running:
        raise ValueError('wait until the run is complete before the publication review')
    for name, expected in data['protocol']['runner_sha256'].items():
        if digest(Path(__file__).with_name(name)) != expected:
            raise ValueError('runner changed since execution: '+name)
    counts = {'attempts_reviewed': 0, 'physical_calls_replayed': 0, 'measurements_replayed': 0,
              'submission_tool_calls_replayed': 0, 'accepted_decisions_replayed': 0,
              'numerical_calls_retained_without_reexecution': 0}
    failures = []
    for record in data['records']:
        identity, task, arm = record['case_id'], record['task'], record['arm']
        path = run / 'attempts' / identity / task / arm
        host = HostTools(dataset, identity, task, arm, run / 'review-scratch', data['protocol']['tool_calls'])
        for index, event in enumerate(json.loads((path / 'tools.json').read_text())):
            name = event['name']
            if name == 'python_analysis':
                # Python is a separate stateless worker. Its scratch files are
                # not inputs to host physics or scoring. Retain the actual
                # result and budget position without rerunning arbitrary code.
                host.history.append(deepcopy(event))
                counts['numerical_calls_retained_without_reexecution'] += 1
                continue
            actual = host.call(name, event['arguments'])
            if canonical(actual) != canonical(event['result']):
                failures.append({'case_id': identity, 'task': task, 'arm': arm,
                                 'event': index, 'tool': name, 'issue': 'recorded tool output differs from replay'})
            if name == 'physical_forward_model':
                counts['physical_calls_replayed'] += 1
            elif name == 'request_measurement':
                counts['measurements_replayed'] += 1
            elif name == 'submit_decision':
                counts['submission_tool_calls_replayed'] += 1
        if canonical(host.submission) != canonical(record['submission']) or canonical(host.score) != canonical(record['score']):
            failures.append({'case_id': identity, 'task': task, 'arm': arm,
                             'issue': 'saved decision or score differs from deterministic replay'})
        counts['attempts_reviewed'] += 1
        counts['accepted_decisions_replayed'] += int(host.submission is not None)
    import hashlib
    result = {'classification': 'deterministic_computational_replay_not_independent_scientific_review',
              'source_sha256': hashlib.sha256(source).hexdigest(), 'source_status': data['status'],
              'review_code_sha256': digest(Path(__file__)), 'passed': not failures,
              **counts, 'failures': failures,
              'limits': ['Agent prose and cited interpretations were not independently scientifically adjudicated.',
                         'Arbitrary numerical Python results were preserved but not reexecuted.',
                         'Replay checks reproducibility against synthetic evaluators, not real manufacturing validity.']}
    destination = 'computational-review.json' if not allow_running else 'computational-review-progress.json'
    dump(run / destination, result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', required=True, type=Path)
    parser.add_argument('--run', required=True, type=Path)
    parser.add_argument('--allow-running', action='store_true')
    args = parser.parse_args()
    print(json.dumps(review(args.dataset, args.run, allow_running=args.allow_running), indent=2))
