"""Common frame for the skill benchmarks: what a case is, how it can fail, and how failures are reported.

A pass rate says how often the product is right. It does not say where it is lacking. So every case here:

- belongs to one **skill** (one thing the product must be able to do),
- carries **tags** for what makes it hard (irregular sample times, a renamed parameter, a request with a condition...),
- ends in exactly one **outcome** from a fixed list, so "wrong" is never one bucket.

The report then answers: for each skill, how often is the product right, in what way is it wrong when it is, and
under which conditions. `not_supported` and `abstained_unnecessarily` are kept apart from wrong answers on purpose:
they are things the product cannot do yet, not things it does badly.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable

# How a case can end. Order is the order of the report columns.
OUTCOMES = {
    'correct': 'The expected result, with the expected sources.',
    'wrong_value': 'A figure, selection or classification that differs from the reference.',
    'wrong_record': 'The right kind of answer from the wrong record, version or site, or without citing its source.',
    'missed': 'Something that is there was not found or not flagged (a record, a gap, a conflict, a deviation).',
    'false_alarm': 'Something was flagged or claimed that the reference does not support.',
    'should_have_abstained': 'An answer was given where the right response was "unknown", "needs information" or a hand-off.',
    'abstained_unnecessarily': 'The product declined or handed off although a correct answer was possible from the data.',
    'not_supported': 'The product has no way to do this yet.',
    'error': 'The request failed.',
}
# Outcomes that are wrong answers a person could act on, as opposed to things the product does not do.
HARMFUL = ('wrong_value', 'wrong_record', 'false_alarm', 'should_have_abstained')
CAPABILITY_GAPS = ('not_supported', 'abstained_unnecessarily')


@dataclass(frozen=True)
class Skill:
    id: str
    title: str
    question: str            # what this skill answers about the product, in one sentence
    capability: str          # the product function or endpoint under test
    datasets: tuple[str, ...]


@dataclass
class Case:
    id: str
    skill: str
    dataset: str
    tags: tuple[str, ...]
    request: Any                         # what is sent to the product
    reference: Any                       # what a right answer contains; never sent to the product
    run: Callable[['Case', Any], Any]    # (case, world) -> the product's response
    score: Callable[['Case', Any], tuple[str, str]]  # (case, response) -> (outcome, one-line reason)
    arm: str = 'host'                    # host | decision_model | explanation | assistant


@dataclass
class Row:
    case_id: str
    skill: str
    dataset: str
    arm: str
    tags: tuple[str, ...]
    outcome: str
    reason: str
    seconds: float | None = None
    detail: dict[str, Any] = field(default_factory=dict)


def wilson(successes: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """95% interval for a proportion. With few cases it is wide, and the report shows it so nobody over-reads a rate."""
    if n == 0:
        return None
    p = successes / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (max(0.0, centre - half), min(1.0, centre + half))


def summarize(rows: list[Row], target_seconds: float = 10.0) -> list[dict[str, Any]]:
    """Per skill and arm: the rate, the kinds of failure, and the conditions under which they happen."""
    groups: dict[tuple[str, str], list[Row]] = defaultdict(list)
    for row in rows:
        groups[(row.skill, row.arm)].append(row)
    out = []
    for (skill, arm), items in sorted(groups.items()):
        n = len(items)
        outcomes = Counter(r.outcome for r in items)
        correct = outcomes.get('correct', 0)
        by_tag = {}
        for tag in sorted({t for r in items for t in r.tags}):
            tagged = [r for r in items if tag in r.tags]
            by_tag[tag] = {'cases': len(tagged), 'correct': sum(r.outcome == 'correct' for r in tagged),
                           'outcomes': dict(Counter(r.outcome for r in tagged if r.outcome != 'correct'))}
        times = sorted(r.seconds for r in items if r.seconds is not None)
        reasons = Counter((r.outcome, r.reason) for r in items if r.outcome != 'correct')
        out.append({
            'skill': skill, 'arm': arm, 'cases': n, 'correct': correct, 'correct_rate': correct / n if n else None,
            'interval_95': wilson(correct, n), 'outcomes': {k: outcomes.get(k, 0) for k in OUTCOMES if outcomes.get(k)},
            'harmful': sum(outcomes.get(k, 0) for k in HARMFUL),
            'capability_gaps': sum(outcomes.get(k, 0) for k in CAPABILITY_GAPS),
            'by_tag': by_tag,
            # Where to look first: conditions with the lowest rate, among those with enough cases to mean something.
            'weakest_conditions': sorted(({'tag': t, **v, 'rate': v['correct'] / v['cases']} for t, v in by_tag.items()
                                          if v['cases'] >= 5 and v['correct'] < v['cases']), key=lambda x: x['rate'])[:6],
            'most_common_failures': [{'outcome': o, 'reason': reason, 'cases': c} for (o, reason), c in reasons.most_common(6)],
            'seconds': {'n': len(times), 'mean': sum(times) / len(times) if times else None,
                        'p95': times[max(math.ceil(0.95 * len(times)) - 1, 0)] if times else None,
                        'max': times[-1] if times else None, 'over_target': sum(t > target_seconds for t in times)},
            'datasets': sorted({r.dataset for r in items}),
        })
    return out


def markdown(summary: list[dict[str, Any]], skills: dict[str, Skill]) -> str:
    lines = ['| Skill | Arm | Cases | Correct | 95% interval | Wrong answers | Cannot do yet | Slowest |',
             '|---|---|---:|---:|---|---:|---:|---:|']
    for s in summary:
        low, high = s['interval_95'] or (0, 0)
        slow = f"{s['seconds']['max']:.2f} s" if s['seconds']['max'] is not None else 'n/a'
        lines.append(f"| {skills[s['skill']].title} | {s['arm']} | {s['cases']} | {s['correct']} ({s['correct_rate']:.0%}) | "
                     f"{low:.0%}–{high:.0%} | {s['harmful']} | {s['capability_gaps']} | {slow} |")
    for s in summary:
        if s['correct'] == s['cases']:
            continue
        lines += ['', f"### {skills[s['skill']].title} · {s['arm']}", '', skills[s['skill']].question, '']
        lines.append('How it fails: ' + ', '.join(f"{OUTCOMES_SHORT[k]} {v}" for k, v in s['outcomes'].items() if k != 'correct') + '.')
        if s['weakest_conditions']:
            lines += ['', '| Condition | Cases | Correct | What goes wrong |', '|---|---:|---:|---|']
            for w in s['weakest_conditions']:
                lines.append(f"| {w['tag']} | {w['cases']} | {w['correct']} ({w['rate']:.0%}) | "
                             + ', '.join(f"{OUTCOMES_SHORT[k]} {v}" for k, v in w['outcomes'].items()) + ' |')
        if s['most_common_failures']:
            lines += ['', 'Most common reasons:']
            lines += [f"- {f['cases']} × {OUTCOMES_SHORT[f['outcome']]}: {f['reason']}" for f in s['most_common_failures']]
    return '\n'.join(lines) + '\n'


OUTCOMES_SHORT = {'correct': 'correct', 'wrong_value': 'wrong value', 'wrong_record': 'wrong record', 'missed': 'missed',
                  'false_alarm': 'false alarm', 'should_have_abstained': 'should have abstained',
                  'abstained_unnecessarily': 'declined although answerable', 'not_supported': 'not supported', 'error': 'error'}
