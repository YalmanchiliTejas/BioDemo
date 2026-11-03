"""Deterministic checks are authoritative; advisory judges cannot erase failures."""
from dataclasses import dataclass, asdict

@dataclass
class Check:
    name: str
    status: str
    evidence: object = None
    hard: bool = False

    def to_dict(self):
        return asdict(self)


def check(name, passed, evidence=None, *, hard=False):
    return Check(name, 'PASS' if passed else 'FAIL', evidence, hard).to_dict()


def unavailable(name, reason, status='NOT_TESTABLE'):
    return Check(name, status, reason).to_dict()


def overall(checks):
    statuses={c['status'] for c in checks}
    if 'FAIL' in statuses:return 'FAIL'
    if 'NOT_IMPLEMENTED' in statuses:return 'NOT_IMPLEMENTED'
    if 'NOT_TESTABLE' in statuses:return 'NOT_TESTABLE'
    if not checks or statuses=={'SKIPPED'}:return 'SKIPPED'
    return 'PASS'
