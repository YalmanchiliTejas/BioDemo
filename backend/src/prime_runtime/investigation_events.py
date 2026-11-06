"""Metadata-only investigation progress events (docs/architecture/multi-agent-investigations.md §12.1).

`clean()` is the single allow-list. The agent container uses it before printing and the
dispatcher uses it again on every log line, so a line can only be stored if both agree.
Message text, source text, answer previews, recaps and provider errors are never carried.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Callable

MAX_LINE_BYTES = 8 * 1024
PHASES = {'planning', 'investigating', 'finalizing', 'submitted'}

# kind -> {key: cap}; cap is a max string length, a max list length (tuple), or None for a number.
_INT = None
SCHEMA: dict[str, dict[str, Any]] = {
    'phase': {'phase': 16},
    'agent_started': {'depth': _INT, 'status': 32, 'question': 300},
    'agent_finished': {'depth': _INT, 'status': 32, 'question': 300},
    'agent_activity': {'status': 32, 'tool': 80, 'tool_use_count': _INT, 'token_count': _INT, 'model': 120},
    'allocation': {'task_ids': (16, 120), 'owner': 80, 'reason': 300, 'calls': _INT},
    'subreport_saved': {'subreport_id': 80, 'assessment': 500, 'fact_count': _INT, 'claim_count': _INT,
                        'open_question_count': _INT, 'evidence_ids': (50, 200)},
    'budget': {'tool_calls_used': _INT, 'tool_calls_limit': _INT, 'elapsed_seconds': _INT, 'tokens': _INT},
    'error': {'code': 80},
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def session_key(session_dir: str | None) -> str | None:
    """Stable, non-reversible key linking a child kernel's RLM_SESSION_DIR to the SDK child snapshot."""
    return hashlib.sha256(session_dir.encode()).hexdigest()[:16] if session_dir else None


def _value(raw: Any, cap: Any) -> Any:
    if cap is None:
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            return None
        return int(raw)
    if isinstance(cap, tuple):
        count, length = cap
        if not isinstance(raw, list):
            return None
        return [str(item)[:length] for item in raw if isinstance(item, (str, int))][:count]
    return str(raw)[:cap] if isinstance(raw, (str, int, float)) and not isinstance(raw, bool) else None


def clean(event: Any) -> dict | None:
    """Return the allow-listed event, or None when it is not a valid investigation event."""
    if not isinstance(event, dict) or event.get('type') != 'investigation_event':
        return None
    kind = event.get('kind')
    if kind not in SCHEMA or type(event.get('local_seq')) is not int or event['local_seq'] < 0:
        return None
    try:
        at = datetime.fromisoformat(str(event.get('at')).replace('Z', '+00:00'))
        if at.tzinfo is None:
            return None
    except ValueError:
        return None
    payload = event.get('payload') if isinstance(event.get('payload'), dict) else {}
    kept = {k: v for k, cap in SCHEMA[kind].items() if k in payload and (v := _value(payload[k], cap)) is not None}
    if kind == 'phase' and kept.get('phase') not in PHASES:
        return None
    ident = lambda v: str(v)[:80] if isinstance(v, str) and v else None
    return {'type': 'investigation_event', 'local_seq': event['local_seq'], 'at': at.isoformat(), 'kind': kind,
            'agent_id': ident(event.get('agent_id')), 'parent_id': ident(event.get('parent_id')), 'payload': kept}


def parse_line(line: str | bytes) -> dict | None:
    """Dispatcher entry point: one container log line -> cleaned event or None (dropped)."""
    if isinstance(line, bytes):
        if len(line) > MAX_LINE_BYTES:
            return None
        line = line.decode('utf-8', errors='replace')
    if len(line.encode()) > MAX_LINE_BYTES:
        return None
    try:
        return clean(json.loads(line))
    except (ValueError, TypeError):
        return None


class EventEmitter:
    """Turns SDK stdout events and bridge hooks into numbered, cleaned events.

    Child attribution: the SDK does not pass its child id into child kernels; each child
    kernel does receive its own RLM_SESSION_DIR, and the SDK child snapshot carries the same
    sessionDir. Bridge calls send session_key(RLM_SESSION_DIR); this emitter maps it to the
    child id learned from child_activity. Unmapped specialist calls get agent_id=None
    (shown as approximate attribution).
    """

    def __init__(self, write: Callable[[dict], None]):
        self.write, self.seq = write, 0
        self.children: dict[str, dict] = {}
        self.by_session: dict[str, str] = {}
        self.phase: str | None = None
        self.tokens = 0

    def emit(self, kind: str, payload: dict, agent_id: str | None = None, parent_id: str | None = None) -> dict | None:
        event = clean({'type': 'investigation_event', 'local_seq': self.seq, 'at': now(), 'kind': kind,
                       'agent_id': agent_id, 'parent_id': parent_id, 'payload': payload})
        if event is not None:
            self.seq += 1
            self.write(event)
        return event

    def set_phase(self, phase: str) -> None:
        if phase != self.phase:
            self.phase = phase
            self.emit('phase', {'phase': phase}, agent_id='lead')

    def agent_for(self, depth: int, key: str | None) -> str | None:
        return 'lead' if depth == 0 else self.by_session.get(key) if key else None

    def sdk(self, raw: dict) -> None:
        kind = raw.get('type')
        if kind == 'child_activity' and raw.get('child_id'):
            child_id, status = str(raw['child_id']), str(raw.get('status') or 'running')
            if raw.get('session_key'):
                self.by_session[str(raw['session_key'])] = child_id
            parent = raw.get('parent_id') if raw.get('parent_id') in self.children else 'lead'
            known = self.children.get(child_id)
            if known is None:
                self.children[child_id] = {'status': status}
                self.set_phase('investigating')
                self.emit('agent_started', {'depth': raw.get('depth', 1), 'status': status, 'question': raw.get('label')},
                          agent_id=child_id, parent_id=parent)
            self.emit('agent_activity', {'status': status, 'tool': raw.get('tool'), 'tool_use_count': raw.get('tool_use_count'),
                                         'token_count': raw.get('token_count'), 'model': raw.get('model')},
                      agent_id=child_id, parent_id=parent)
            if status in ('done', 'error', 'cancelled') and (known or {}).get('status') not in ('done', 'error', 'cancelled'):
                self.emit('agent_finished', {'depth': raw.get('depth', 1), 'status': status}, agent_id=child_id, parent_id=parent)
            self.children[child_id]['status'] = status
            if isinstance(raw.get('token_count'), int):
                self.children[child_id]['tokens'] = raw['token_count']
        elif kind == 'message_end':
            usage = (raw.get('message') or {}).get('usage') or {}
            self.tokens += int(usage.get('input', 0) or 0) + int(usage.get('output', 0) or 0)
        elif kind in ('specialist_wrap_up', 'finalization_reserve', 'investigation_deadline'):
            self.set_phase('finalizing')
        elif kind == 'investigation_report_persisted':
            self.set_phase('submitted')

    @property
    def total_tokens(self) -> int:
        """Root session tokens plus each child's latest snapshot. ponytail: child snapshots are context size,
        not billed usage; an approximate cap until the SDK reports additive child usage."""
        return self.tokens + sum(c.get('tokens', 0) for c in self.children.values())

    def bridge(self, kind: str, payload: dict, *, depth: int = 0, key: str | None = None) -> None:
        self.emit(kind, payload, agent_id=self.agent_for(depth, key), parent_id=None if depth == 0 else 'lead')
