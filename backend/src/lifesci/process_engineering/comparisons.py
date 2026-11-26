"""Comparison check: does a stated comparison hold for the numbers stated with it?

"DO 24 % is below the 30 % limit" is checked as 24 < 30; "61 %, 44 %, 33 %, 24 % — the last three below 30 %" as
44, 33, 24 < 30 (false: flagged). Deterministic and conservative: only comparisons whose numbers are written in the
same sentence, with the same unit, and no negation nearby; anything ambiguous is left alone, because a check that
cries wolf teaches people to ignore it. It checks the answer against itself; number provenance is grounding.py.
"""
from __future__ import annotations

import re

UNITS = r'million cells/mL|×\s?10⁶\s?cells/mL|cells/mL|g/L|mg/L|mmol/L|°C|L/min|rpm|%'
VALUE = re.compile(r'(?<![\w.:/-])(-?\d+(?:\.\d+)?)(?![\d:])\s*(' + UNITS + r')?')
# "over" and "under" are left out: too often about time or groups ("over 01:00-04:00", "under the new lot").
LESS = r'below|beneath|less than|lower than|<|≤'
MORE = r'above|exceed(?:s|ed|ing)?|more than|greater than|higher than|>|≥'
THOUSANDS = re.compile(r'(?<=\d),(?=\d{3}(?!\d))')
APPROXIMATE = re.compile(r'(~|≈|about|around|roughly|approximately|[-–]\s*$|\bto\s*$)', re.I)
COMPARATOR = re.compile(rf'(?<![\w])({LESS}|{MORE})(?![\w])', re.I)
NEGATION = re.compile(r"\b(not|never|no longer|neither|nor|without)\b|n't", re.I)
WORDS = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10}
COUNT = r'(\d+|one|two|three|four|five|six|seven|eight|nine|ten)'
QUANTIFIER = re.compile(rf'\b(?:(all|both|each|every|none|neither)|(?:the\s+)?(last|first)\s+{COUNT}|{COUNT}\s+of\s+(?:the\s+)?{COUNT})\b'
                        r'(.{0,80}?)\s' + rf'({LESS}|{MORE})(?![\w])', re.I)
SUPERLATIVE = re.compile(r'\b(highest|lowest|largest|smallest|maximum|minimum)\b', re.I)
SENTENCE = re.compile(r'(?<=[.!?])\s+(?=[A-Z*(\[])|\n+')


def _unit(u: str | None) -> str:
    u = (u or '').replace(' ', '')
    return 'million cells/mL' if u in ('millioncells/mL', '×10⁶cells/mL') else u


def _values(text: str) -> list[tuple[float, str, int, int]]:
    return [(float(m.group(1)), _unit(m.group(2)), m.start(), m.end()) for m in VALUE.finditer(text)]


def _less(match: str) -> bool:
    return re.fullmatch(LESS, match, re.I) is not None


def _holds(value: float, less: bool, limit: float) -> bool:
    return value < limit if less else value > limit


def _trailing(values, before: int, unit: str) -> list[float]:
    """The unbroken run of same-unit values just before a quantifier ("61 %, 44 %, 33 %, 24 % … the last three")."""
    run = []
    for v, u, s, e in reversed([x for x in values if x[3] <= before]):
        if not u:
            continue  # a bare number ("seq 1-4") neither joins nor breaks the list
        if u != unit:
            break
        run.append(v)
    return list(reversed(run))


def check(reply: str) -> list[dict]:
    """Statements contradicted by their own numbers: [{'statement', 'says', 'but'}]."""
    found: list[dict] = []
    for sentence in SENTENCE.split(THOUSANDS.sub('', reply or '')):
        values = _values(sentence)
        if len(values) < 2:
            continue
        used: set[int] = set()
        # 1. A list then a quantified comparison: "61 %, 44 %, 33 %, 24 % ... the last three below 30 %".
        for q in QUANTIFIER.finditer(sentence):
            if NEGATION.search(sentence[max(0, q.start() - 25):q.end()]):
                continue
            if re.match(r'\s*other\b', sentence[q.end(1) if q.group(1) else q.end():], re.I) or 'other' in q.group(0).lower().split():
                continue  # "every other run" means runs not listed here
            limit = next(((v, u, s, e) for v, u, s, e in values if s >= q.end() and s - q.end() <= 40 and u), None)
            if limit is None or APPROXIMATE.search(sentence[max(0, limit[2] - 12):limit[2]]) or \
                    re.match(r'\s*[-–]\s*\d', sentence[limit[3]:]):
                continue  # an approximate or range limit ("~72-88 %") is not a threshold to check
            # The values compared are listed between the quantifier and the comparison ("both runs, 8.1 and 9.9,
            # stayed above 9"), or else just before the quantifier ("61, 44, 33 … the last three below 30").
            inside = [v for v, u, s, e in values if q.start() <= s and e <= q.start(7) and u == limit[1]]
            listed = inside if len(inside) >= 2 else _trailing(values, q.start(), limit[1])
            every, edge, n, k, m = q.group(1), q.group(2), q.group(3), q.group(4), q.group(5)
            less = _less(q.group(7))
            if every:
                every = every.lower()
                if len(listed) < 2 or (every in ('both', 'neither') and len(listed) != 2):
                    continue
                ok = [_holds(v, less, limit[0]) for v in listed]
                good = not any(ok) if every in ('none', 'neither') else all(ok)
                claim = f"{every} {'below' if less else 'above'} {limit[0]:g} {limit[1]}"
                chosen = listed
            elif edge:
                count = WORDS.get(n.lower(), None) if not n.isdigit() else int(n)
                if not count or count > len(listed) or len(listed) < 2:
                    continue
                chosen = listed[-count:] if edge.lower() == 'last' else listed[:count]
                good = all(_holds(v, less, limit[0]) for v in chosen)
                claim = f"the {edge.lower()} {count} {'below' if less else 'above'} {limit[0]:g} {limit[1]}"
            else:
                said = WORDS.get(k.lower(), None) if not k.isdigit() else int(k)
                total = WORDS.get(m.lower(), None) if not m.isdigit() else int(m)
                if not said or total != len(listed):
                    continue
                chosen = listed
                good = sum(_holds(v, less, limit[0]) for v in listed) == said
                claim = f"{said} of {total} {'below' if less else 'above'} {limit[0]:g} {limit[1]}"
            used.add(limit[2])
            if not good:
                found.append({'statement': sentence.strip()[:400], 'says': claim,
                              'but': ', '.join(f'{v:g} {limit[1]}' for v in chosen)})
        # 2. A value, a comparator, a limit: "24 % is below the 30 % low limit", "33 % > 30 %".
        for c in COMPARATOR.finditer(sentence):
            if NEGATION.search(sentence[max(0, c.start() - 25):c.start()]):
                continue
            before = [(v, u, s, e) for v, u, s, e in values if e <= c.start() and c.start() - e <= 30 and s not in used]
            after = [(v, u, s, e) for v, u, s, e in values if s >= c.end() and s - c.end() <= 30 and s not in used]
            if not before or not after:
                continue
            (value, vu, vs, _), (limit, lu, ls, _) = before[-1], after[0]
            if COMPARATOR.search(sentence[c.end():ls]) or APPROXIMATE.search(sentence[max(0, ls - 12):ls]):
                continue  # the limit belongs to a later comparison, or is approximate
            if not vu or vu != lu or re.search(r'[a-z]', sentence[c.end():ls].replace('the', '').replace('a ', ''), re.I) and \
                    len(sentence[c.end():ls].split()) > 4:
                continue
            between = sentence[vs:c.start()]
            if re.search(r'\b(and|or|to|from|while|whereas|but)\b', between, re.I):
                continue  # "from 89 % to 6 % below …" — the nearest number may belong to another clause
            less = _less(c.group(1))
            if not _holds(value, less, limit):
                found.append({'statement': sentence.strip()[:400], 'says': f"{value:g} {vu} {'below' if less else 'above'} {limit:g} {lu}",
                              'but': f"{value:g} {vu} is {'not below' if less else 'not above'} {limit:g} {lu}"})
        # 3. A superlative naming a value, among comparable values listed in the same sentence.
        for s_match in SUPERLATIVE.finditer(sentence):
            near = [(v, u, s, e) for v, u, s, e in values if abs(s - s_match.end()) <= 20 or abs(e - s_match.start()) <= 20]
            if len(near) != 1 or not near[0][1]:
                continue
            value, unit = near[0][0], near[0][1]
            others = [v for v, u, s, e in values if u == unit and s != near[0][2]]
            if len(others) < 2 or NEGATION.search(sentence[max(0, s_match.start() - 25):s_match.start()]):
                continue
            high = s_match.group(1).lower() in ('highest', 'largest', 'maximum')
            if (high and value < max(others)) or (not high and value > min(others)):
                found.append({'statement': sentence.strip()[:400], 'says': f'{value:g} {unit} is the {s_match.group(1).lower()}',
                              'but': f"{max(others) if high else min(others):g} {unit} is also stated"})
    return found


if __name__ == '__main__':
    bad = check('DO fell 61 % at 01:00, 44 % at 02:00, 33 % at 03:00, 24 % at 04:00 (historian points, seq 1–4; the last three '
                'below a 30 % action level).')  # verbatim from a live answer, 2026-11-07
    assert len(bad) == 1 and bad[0]['but'] == '44 %, 33 %, 24 %', bad
    assert not check('DO fell 61 % at 01:00, 44 % at 02:00, 33 % at 03:00, 24 % at 04:00 (the last one below a 30 % action level).')
    assert len(check('DO read 33 %, below the 30 % low limit.')) == 1
    assert not check('DO read 24 %, below the 30 % low limit.')
    assert not check('DO read 33 %, not below the 30 % low limit.')
    assert not check('Glucose fell from 6.4 g/L to 2.0 g/L, below 2.5 g/L.')  # nearest number crosses a clause: skipped
    assert len(check('Both runs, 8.1 g/L and 9.9 g/L, stayed above 9 g/L.')) == 1
    assert not check('Runs ended at 9.9 g/L, 8.1 g/L and 0.3 g/L; the highest, 9.9 g/L, was CHO-003-R01.')
    # False alarms seen on real answers (2026-11-07), now left alone:
    assert not check('It fell to 46,000 cells/mL after peaking at 14,000,000 cells/mL (the highest), above 8,126,667 cells/mL.')
    assert not check('DO fell 61 % → 44 % → 33 % → 24 % over 01:00–04:00, below the 30 % low limit.')
    assert not check('It fell from 89.25 % at 114.5 h to 6.17 % at 142 h, while every other run was still ≥ ~72–88 %.')
    print('ok')
