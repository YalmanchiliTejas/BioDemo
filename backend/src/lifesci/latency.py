"""How long requests take, measured where the person waits.

The target is an answer within ten seconds. This module only measures and labels: nothing is cut off at the target,
because a slower correct answer is preferred to a faster wrong one. Work that runs past the target stays visibly
"working" and is counted as an overrun.
"""
from __future__ import annotations

import math
import os
import re
import time
from collections import defaultdict, deque
from threading import Lock
from typing import Any


def _target() -> float:
    try:
        value = float(os.environ.get('LIFESCI_ANSWER_TARGET_S', '10'))
        return value if math.isfinite(value) and value > 0 else 10.0
    except ValueError:
        return 10.0


ANSWER_TARGET_SECONDS = _target()


def percentile(ordered: list[float], p: float) -> float | None:
    """Nearest-rank percentile of an ascending list."""
    return ordered[max(math.ceil(p / 100 * len(ordered)) - 1, 0)] if ordered else None


def distribution(values: list[float], *, target: float = ANSWER_TARGET_SECONDS) -> dict[str, Any]:
    ordered = sorted(values)
    return {'n': len(ordered), 'mean': sum(ordered) / len(ordered) if ordered else None,
            'min': ordered[0] if ordered else None, 'max': ordered[-1] if ordered else None,
            'p50': percentile(ordered, 50), 'p95': percentile(ordered, 95),
            'target_seconds': target, 'within_target': sum(v <= target for v in ordered),
            'over_target': sum(v > target for v in ordered)}


def against_target(seconds: float, *, target: float = ANSWER_TARGET_SECONDS) -> dict[str, Any]:
    return {'seconds': round(seconds, 3), 'target_seconds': target, 'within_target': seconds <= target}


class Phases:
    """Wall time of the named steps of one request: where the time went, not only how much."""

    def __init__(self) -> None:
        self.started = time.perf_counter()
        self.seconds: dict[str, float] = defaultdict(float)

    def __call__(self, name: str) -> '_Phase':
        return _Phase(self, name)

    def report(self) -> dict[str, Any]:
        total = time.perf_counter() - self.started
        return {'phases': {k: round(v, 4) for k, v in self.seconds.items()}, **against_target(total)}


class _Phase:
    def __init__(self, owner: Phases, name: str) -> None:
        self.owner, self.name = owner, name

    def __enter__(self) -> None:
        self.t0 = time.perf_counter()

    def __exit__(self, *exc: Any) -> None:
        self.owner.seconds[self.name] += time.perf_counter() - self.t0


_ID = re.compile(r'/(?:[a-z]+_[0-9A-Za-z]{12,}|[0-9a-f]{16,}|[0-9a-f-]{32,})(?=/|$)')


class RequestLatency:
    """Recent request durations per route, kept in this process.

    ponytail: a bounded in-memory window per process; restarts clear it and several workers each keep their own.
    Durable figures live on the records themselves (chat turns and task results carry their timing)."""

    def __init__(self, window: int = 500) -> None:
        self._by_route: dict[str, deque[tuple[float, int]]] = defaultdict(lambda: deque(maxlen=window))
        self._lock = Lock()
        self.window = window

    @staticmethod
    def route_key(method: str, path: str) -> str:
        return f'{method} {_ID.sub("/{id}", path)}'

    def record(self, method: str, path: str, seconds: float, status: int) -> None:
        with self._lock:
            self._by_route[self.route_key(method, path)].append((seconds, status))

    def summary(self, prefix: str = '') -> dict[str, Any]:
        with self._lock:
            snapshot = {route: list(items) for route, items in self._by_route.items() if prefix in route}
        routes = [{'route': route, **distribution([s for s, _ in items]),
                   'server_errors': sum(status >= 500 for _, status in items)} for route, items in snapshot.items()]
        routes.sort(key=lambda r: -(r['p95'] or 0))
        return {'target_seconds': ANSWER_TARGET_SECONDS, 'window_per_route': self.window, 'routes': routes,
                'scope': 'Server handling time of recent requests in this process; network and browser time are not '
                         'included. A chat answer is produced after its request returns: read its timing on the turn.'}
