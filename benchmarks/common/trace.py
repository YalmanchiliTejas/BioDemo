"""Evaluation traces: metadata and artifact references, never raw source content."""
from __future__ import annotations

import json
import math
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

STAGES = ('ingestion', 'mapping', 'analysis', 'verification', 'investigation', 'triage', 'coordination', 'setup', 'corrections', 'ongoing_configuration')
ACTORS = ('agent', 'human', 'pipeline', 'evaluator')
STATUSES = ('success', 'partial', 'unresolved', 'error')


def now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def instant(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('timestamps must include a timezone')
    return parsed.astimezone(timezone.utc)


def validate_event(event):
    for key in ('case_id', 'run_id', 'event_id', 'action'):
        if not isinstance(event.get(key), str) or not event[key]:
            raise ValueError(f'missing trace {key}')
    if event.get('actor') not in ACTORS or event.get('stage') not in STAGES or event.get('status') not in STATUSES:
        raise ValueError('invalid trace actor/stage/status')
    duration = (instant(event['ended_at']) - instant(event['started_at'])).total_seconds()
    active = event.get('active_human_seconds')
    if duration < 0 or type(active) not in (int, float) or not math.isfinite(active) or not 0 <= active <= duration + .001:
        raise ValueError('invalid active-work interval')
    if event['actor'] != 'human' and active != 0:
        raise ValueError('machine runtime is not human effort')
    if not isinstance(event.get('source_refs'), list):
        raise ValueError('source_refs must be a list')
    for key in ('input_tokens', 'output_tokens', 'estimated_cost_usd'):
        value = event.get(key)
        if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or value < 0):
            raise ValueError(f'invalid {key}')
    return event


class TraceSink:
    def __init__(self, path, case_id, run_id, *, environment=None, budgets=None):
        self.path, self.case_id, self.run_id = Path(path), case_id, run_id
        self.environment, self.budgets = environment or {}, budgets or {}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()

    def emit(self, *, actor, stage, action, started_at=None, ended_at=None, status='success', **fields):
        stamp = now()
        event = dict(case_id=self.case_id, run_id=self.run_id, event_id=uuid4().hex,
                     actor=actor, stage=stage, action=action, started_at=started_at or stamp,
                     ended_at=ended_at or stamp, active_human_seconds=0, source_refs=[], tool=None,
                     error_code=None, model_id=None, prompt_version=None, input_tokens=None,
                     output_tokens=None, estimated_cost_usd=None, output_refs=[], evidence_ids=[],
                     correction_of=None, environment=self.environment, budgets=self.budgets)
        event.update(fields, status=status)
        validate_event(event)
        with self.lock, self.path.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(event, sort_keys=True, default=str) + '\n')
        return event

    @contextmanager
    def interval(self, *, actor, stage, action, **fields):
        start, tick = now(), time.monotonic()
        detail = dict(fields)
        try:
            yield detail
        except BaseException as exc:
            detail.update(status='error', error_code=type(exc).__name__)
            raise
        finally:
            self.emit(actor=actor, stage=stage, action=action, started_at=start, ended_at=now(),
                      wall_clock_seconds=time.monotonic()-tick, **detail)
