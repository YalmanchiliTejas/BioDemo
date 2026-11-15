"""Replay deterministic workspace tasks against frozen local sources, without inference.

Run from the repository root with PYTHONPATH=backend. Source acquisition, licensing,
deidentification and reference-answer review happen before this runner is invoked.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform as host_platform
import time
from typing import Any


@dataclass(frozen=True)
class FrozenFixture:
    spec: dict[str, Any]
    sha256: str
    sources: tuple[tuple[dict[str, Any], bytes], ...]


def _required_text(obj: dict, key: str, where: str) -> str:
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{where}.{key} must be nonempty text')
    return value


def _reject_constant(value: str) -> None:
    raise ValueError(f'Nonfinite JSON number is not allowed: {value}')


def load_fixture(path: Path) -> FrozenFixture:
    """Verify and freeze every payload before executing any task; never fetch URLs."""
    path = Path(path).resolve()
    raw = path.read_bytes()
    spec = json.loads(raw, parse_constant=_reject_constant)
    if not isinstance(spec, dict) or spec.get('schema_version') != 'workspace-tasks-replay-v1':
        raise ValueError('Expected schema_version workspace-tasks-replay-v1')
    _required_text(spec, 'suite_id', 'fixture')
    provenance = spec.get('provenance', {})
    for key in ('kind', 'description'):
        _required_text(provenance, key, 'provenance')
    context = spec.get('context', {})
    for key in ('tenant_id', 'actor_id', 'site_id'):
        _required_text(context, key, 'context')
    tasks = spec.get('tasks')
    if not isinstance(tasks, list) or not tasks:
        raise ValueError('tasks must be a nonempty list')
    ids = set()
    for task in tasks:
        task_id = _required_text(task, 'id', 'task')
        if task_id in ids:
            raise ValueError('Task ids must be unique')
        ids.add(task_id)
        for key in ('request', 'expected'):
            if not isinstance(task.get(key), dict) or not task[key]:
                raise ValueError(f'task.{key} must be a nonempty object')
    if not isinstance(spec.get('sources'), list):
        raise ValueError('sources must be a list (possibly empty)')
    sources = []
    source_ids = set()
    for source in spec['sources']:
        for key in ('path', 'sha256', 'source_system', 'source_record_id', 'media_type', 'event_time'):
            _required_text(source, key, 'source')
        for key in ('kind', 'citation', 'license'):
            _required_text(source.get('provenance', {}), key, 'source.provenance')
        identity = (source['source_system'], source['source_record_id'])
        if identity in source_ids:
            raise ValueError('Initial source identities must be unique')
        source_ids.add(identity)
        payload_path = (path.parent / source['path']).resolve()
        if not payload_path.is_relative_to(path.parent):
            raise ValueError('Source paths must remain inside the fixture directory')
        content = payload_path.read_bytes()
        if hashlib.sha256(content).hexdigest() != source['sha256']:
            raise ValueError(f'SHA-256 mismatch for source {source["path"]}')
        sources.append((source, content))
    return FrozenFixture(spec, hashlib.sha256(raw).hexdigest(), tuple(sources))


def check_expected(actual: Any, expected: Any, path: str = '$') -> list[dict]:
    """Recursive object subset; arrays retain exact length/order; no fuzzy grading."""
    if isinstance(expected, dict) and isinstance(actual, dict):
        differences = []
        for key, value in expected.items():
            if key not in actual:
                differences.append({'path': f'{path}.{key}', 'expected': value, 'missing': True})
            else:
                differences.extend(check_expected(actual[key], value, f'{path}.{key}'))
        return differences
    if isinstance(expected, list) and isinstance(actual, list) and len(actual) == len(expected):
        return [difference for i, value in enumerate(expected)
                for difference in check_expected(actual[i], value, f'{path}[{i}]')]
    # JSON numbers compare by value, but true must not pass an expectation of 1.
    same_kind = type(actual) is type(expected) or (
        type(actual) in (int, float) and type(expected) in (int, float))
    if same_kind and actual == expected:
        return []
    return [{'path': path, 'expected': expected, 'actual': actual}]


class InferenceGuard:
    """Fail closed at gateway and embedding entry points, and count caught attempts."""
    model = 'inference-disabled'

    def __init__(self, platform):
        self.blocked_attempts = 0
        platform.gateway.providers.clear()
        platform.gateway.run = self.block
        platform.gateway.converse = self.block
        platform.agent_memory.embedder = self

    def block(self, *args, **kwargs):
        self.blocked_attempts += 1
        raise RuntimeError('Model and embedding inference is disabled in workspace task replay')

    embed = block


def _latencies(values: list[float]) -> dict:
    ordered = sorted(values)
    return {'n': len(ordered),
            'min': min(ordered, default=None), 'max': max(ordered, default=None),
            'mean': sum(ordered) / len(ordered) if ordered else None,
            **{f'p{p}': ordered[math.ceil(p / 100 * len(ordered)) - 1] if ordered else None
               for p in (50, 90, 95, 99)}}


def run_replay(fixture_path: Path, repeats: int = 1) -> dict:
    """Each task/repeat receives a fresh in-memory store and the same frozen sources."""
    if type(repeats) is not int or repeats < 1:
        raise ValueError('repeats must be a positive integer')
    frozen = load_fixture(fixture_path)
    spec = frozen.spec
    # Explicit construction avoids configured production databases and providers.
    from src.lifesci.container import Platform
    from src.lifesci.store import RecordStore

    started_at = datetime.now(timezone.utc).isoformat()
    started = time.perf_counter()
    attempts = []
    for repeat in range(1, repeats + 1):
        for task in spec['tasks']:
            wall_started = time.perf_counter()
            service_started = None
            p = guard = None
            row = {'task_id': task['id'], 'repeat': repeat, 'outcome': 'error',
                   'task_status': None, 'record_status': None, 'provider_calls': 0,
                   'reported_model_calls': None, 'blocked_inference_attempts': 0,
                   'service_wall_seconds': None}
            try:
                p = Platform(RecordStore(), providers={})
                guard = InferenceGuard(p)
                context = spec['context']
                p.identity.assign_role(context['tenant_id'], context['actor_id'], 'msat', site_id=context['site_id'])
                ctx = p.identity.context_for(context['tenant_id'], context['actor_id'])
                for source, content in frozen.sources:
                    p.evidence.ingest(ctx, content=content, site_id=context['site_id'],
                        **{key: deepcopy(source[key]) for key in (
                            'source_system', 'source_record_id', 'media_type', 'event_time',
                            'source_revision', 'mapping_version', 'metadata') if key in source})
                service_started = time.perf_counter()
                result = p.workspace_tasks.execute(ctx, deepcopy(task['request']))
                row['service_wall_seconds'] = time.perf_counter() - service_started
                row.update(result=result, task_status=result.get('task_status'),
                           record_status=result.get('status'), reported_model_calls=result.get('model_calls'))
                differences = check_expected(result, task['expected'])
                differences.extend(check_expected(result, {'model_calls': 0}))
                if result.get('task_status') not in ('completed', 'needs_information'):
                    differences.append({'path': '$.task_status', 'error': 'Unrecognized task status'})
                row.update(outcome='mismatch' if differences else 'passed', differences=differences)
            except Exception as exc:
                row['error'] = {'type': type(exc).__name__, 'message': str(exc)[:1500]}
            finally:
                if service_started is not None and row['service_wall_seconds'] is None:
                    row['service_wall_seconds'] = time.perf_counter() - service_started
                if guard is not None:
                    row['blocked_inference_attempts'] = guard.blocked_attempts
                    if guard.blocked_attempts:
                        row['outcome'] = 'inference_blocked'
                if p is not None:
                    p.store.release_connections()
                row['wall_seconds'] = time.perf_counter() - wall_started
                attempts.append(row)
    passed = sum(row['outcome'] == 'passed' for row in attempts)
    return {
        'schema_version': 'workspace-tasks-replay-report-v1', 'started_at': started_at,
        'fixture': {'suite_id': spec['suite_id'], 'schema_version': spec['schema_version'],
                    'sha256': frozen.sha256, 'provenance': spec['provenance'],
                    'sources': [{**source, 'bytes': len(content)} for source, content in frozen.sources]},
        'protocol': {
            'python': host_platform.python_version(), 'platform': host_platform.platform(),
            'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'repeats': repeats, 'distinct_tasks': len(spec['tasks']), 'concurrency': 1,
            'scope': 'Local deterministic service replay; no provider, API, browser or scientific-quality evaluation.',
            'timing': 'wall_seconds includes setup, ingestion, service, checks and cleanup for every attempt. '
                      'service_wall_seconds includes every service invocation, including exceptions. '
                      'Fixture loading and report serialization are excluded from both.',
            'cache': 'Fresh in-memory store per attempt; shared interpreter and uncontrolled OS caches.',
            'grading': 'Only supplied expected object keys; arrays exact in length/order; scalar values exact. '
                       'Zero model calls and a recognized task status are additional required checks.',
            'limits': ['No deadline enforcement; observed durations only.',
                       'Repeat counts do not increase independent incident/site coverage.',
                       'Small-sample empirical percentiles do not establish a production SLO.',
                       'Provenance and license declarations require human review; this runner does not certify rights.'],
        },
        'attempts': attempts,
        'summary': {
            'attempts': len(attempts), 'passed': passed, 'failed': len(attempts) - passed,
            'outcomes': dict(Counter(row['outcome'] for row in attempts)),
            'task_statuses': dict(Counter(row['task_status'] or 'no_result' for row in attempts)),
            'all_run_wall_seconds': _latencies([row['wall_seconds'] for row in attempts]),
            'service_wall_seconds': _latencies([row['service_wall_seconds'] for row in attempts
                                               if row['service_wall_seconds'] is not None]),
            'campaign_wall_seconds': time.perf_counter() - started,
            'provider_calls': 0, 'blocked_inference_attempts': sum(row['blocked_inference_attempts'] for row in attempts),
            'provider_inference_cost_usd': 0, 'total_compute_cost_usd': None,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path, help='New JSON report path; existing files are never overwritten.')
    parser.add_argument('--repeats', type=int, default=1)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error('Output already exists; choose a new report path')
    report = run_replay(args.fixture, repeats=args.repeats)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'report': str(args.output), 'summary': report['summary']}, indent=2))
    return 0 if report['summary']['failed'] == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
