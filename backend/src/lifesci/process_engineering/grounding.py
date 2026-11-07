"""Deterministic reply grounding: does each stated claim trace to inspected text?

This checks provenance, not meaning. A verbatim quote proves the words exist in
a source the assistant actually saw; it does not prove the claim follows from
them. Numbers are checked because they are the cheapest nonsense to catch.
"""
import json
import re

from ...workflows.claim_verification import NUMBER


# ponytail: conversion constants a correct unit explanation may state; extend when a real flag says so.
UNIT_FACTORS = {1.0, 10.0, 100.0, 1000.0, 1e6, 60.0, 24.0, 3600.0}


def _norm(text):
    return ' '.join(str(text).split()).casefold()


THOUSANDS = re.compile(r'(?<=\d),(?=\d{3}(?!\d))')
# Displayed values often change unit scale: cells/mL vs million cells/mL, mg vs g, a fraction vs a percent.
SCALES = (1.0, 1e-6, 1e-3, 1e3, 1e6, 100.0, 0.01)


def _numbers(text):
    return {float(m) for m in NUMBER.findall(THOUSANDS.sub('', str(text)))}


def _shown(text):
    """Reply numbers as written, with the precision they claim (5.41 claims two decimals)."""
    out = []
    for m in NUMBER.findall(THOUSANDS.sub('', str(text))):
        digits = m.lower().split('e')[0]
        decimals = len(digits.split('.')[1]) if '.' in digits else 0
        out.append((float(m), 0.5 * 10 ** -decimals + 1e-9 * abs(float(m))))
    return out


def _traced(value, tolerance, allowed_sorted):
    """A source value that rounds to the shown value, directly or at a common unit scale."""
    from bisect import bisect_left
    for scale in SCALES:
        target, tol = value / scale, tolerance / scale
        i = bisect_left(allowed_sorted, target - tol)
        if i < len(allowed_sorted) and allowed_sorted[i] <= target + tol:
            return True
    return False


def _arithmetic(value, tolerance, operands):
    """A difference, sum, ratio, product or percent change of two traced numbers in the same reply."""
    for a in operands:
        for b in operands:
            candidates = [a - b, a + b, a * b] + ([a / b, (a - b) / b * 100] if b else [])
            if any(abs(abs(c) - value) <= tolerance for c in candidates):
                return True
    return False


def source_text(record):
    """Searchable text of a workspace read or an attached source entry."""
    # The assistant sees metadata (event_time, revision) too, and may quote it.
    original = record.get('data', record).get('original') or ''
    return original + '\n' + json.dumps(record, ensure_ascii=False, default=str, sort_keys=True)


def check_reply(reply, claims, sources, *, support_texts=()):
    """sources: {source_id: text actually provided to the assistant}.
    support_texts: other legitimate number origins (user messages, host-computed artifacts).

    Returns status grounded | partially_grounded | ungrounded | no_claims.
    """
    normalized = {sid: _norm(text) for sid, text in sources.items()}
    results = []
    for claim in claims:
        # Models stitch non-adjacent sentences into one quote; each fragment must still be verbatim.
        parts = [_norm(x) for x in re.split(r'(?<=[.;!?])\s+|\s*\n\s*|\s*(?:\.\.\.|…)\s*', claim['quote']) if x.strip()]
        found = lambda t: bool(parts) and all(x in t for x in parts)
        text = normalized.get(claim['source_id'])
        if text is not None:
            problem = None if found(text) else 'quote_not_found'
        else:
            # Mislabelled id but the words are in something the assistant saw: provenance holds.
            # ponytail: 20-char floor so a generic word can't relabel a citation; tune if real quotes are shorter.
            match = next((sid for sid, t in normalized.items() if found(t)), None) if len(' '.join(parts)) >= 20 else None
            problem = None if match else 'source_not_inspected'
            if match:
                claim = {**claim, 'cited_source_id': claim['source_id'], 'source_id': match}
        results.append({**claim, 'verified': problem is None, 'problem': problem})
    allowed = set()
    for value in [*sources.values(), *support_texts, *(c['quote'] for c in claims)]:
        # ISO dates hide their parts from NUMBER; "October 2026" restates 2026-10-20.
        allowed |= _numbers(value) | _numbers(re.sub(r'(?<=\d)[-/:T](?=\d)', ' ', str(value)))
    allowed |= UNIT_FACTORS
    # Derived claims (unit conversions, differences) may state new numbers, but
    # only from a verified quote, and they stay listed: the arithmetic is unchecked.
    derived = set()
    for r in results:
        if r.get('kind') == 'derived' and r['verified']:
            derived |= _numbers(r['text']) - allowed
    # Numbers are traced as a reviewer would: a source value that rounds to the shown precision, possibly at a
    # common unit scale (live: correct forecast values like 5.41 g/L for 5.4113 were all flagged by exact matching).
    # A difference/ratio/percent change of traced numbers is shown as calculated, not as untraced.
    allowed_sorted = sorted(allowed)
    shown = _shown(reply)
    reply_numbers = {v for v, _ in shown}
    traced = {v for v, tol in shown if v in allowed or v in derived or _traced(v, tol, allowed_sorted)}
    operands = [v for v in traced if v not in UNIT_FACTORS]
    calculated = {v for v, tol in shown if v not in traced and _arithmetic(v, tol, operands)}
    derived |= calculated
    unsupported_numbers = sorted(reply_numbers - traced - calculated)
    verified = sum(r['verified'] for r in results)
    # Statements contradicted by their own numbers ("the last three below 30 %" over 44, 33, 24 %): the most serious
    # finding, so it takes precedence and is always shown.
    from .comparisons import check as contradictions_in
    contradictions = contradictions_in(reply)
    if contradictions:
        status = 'contradicted'
    elif not results and not unsupported_numbers:
        status = 'no_claims'
    elif verified == len(results) and not unsupported_numbers:
        status = 'grounded'
    elif verified:
        status = 'partially_grounded'
    else:
        status = 'ungrounded'
    return {'status': status, 'claims': results, 'unsupported_numbers': unsupported_numbers, 'contradictions': contradictions,
            'derived_numbers': sorted(derived & reply_numbers),
            'method': 'verbatim quote in inspected source + number provenance; not semantic support'}


if __name__ == '__main__':
    src = {'E1': 'Assay result 2500 mg/L; specification minimum 2.8 g/L.'}
    ok = check_reply('The assay is 2500 mg/L, below 2.8 g/L.',
                     [{'text': 'assay 2500 mg/L', 'source_id': 'E1', 'quote': 'Assay result 2500  mg/L'}], src)
    assert ok['status'] == 'grounded', ok
    bad = check_reply('The assay is 2600 mg/L.', [{'text': 'x', 'source_id': 'E2', 'quote': 'Assay'}], src)
    assert bad['status'] == 'ungrounded' and bad['unsupported_numbers'] == [2600.0], bad
    assert bad['claims'][0]['problem'] == 'source_not_inspected'
    assert check_reply('No numbers here.', [], src)['status'] == 'no_claims'
    stitched = check_reply('ok', [{'text': 'x', 'source_id': 'E9', 'quote': 'Assay result 2500 mg/L; ... minimum 2.8 g/L.'}], src)
    assert stitched['status'] == 'grounded' and stitched['claims'][0]['cited_source_id'] == 'E9', stitched
    assert check_reply('ok', [{'text': 'x', 'source_id': 'E1', 'quote': 'Assay result 9 mg/L.'}], src)['status'] == 'ungrounded'
    assert check_reply('1000 mg = 1 g, so 2500 mg/L; event of October 2026.', [], src | {'E4': 'at 2026-10-20'})['status'] == 'no_claims'
    rows = check_reply('ok', [{'text': 'x', 'source_id': 'T', 'quote': 'A-1,2.9\nA-3,3.1'}], {'T': 'A-1,2.9\nA-2,2.3\nA-3,3.1'})
    assert rows['status'] == 'grounded', rows
    meta = {'id': 'E3', 'event_time': '2026-10-20T10:00:00Z', 'data': {'original': 'Assay pending.'}}
    assert check_reply('Pending since 2026-10-20.', [{'text': 'x', 'source_id': 'E3', 'quote': '"event_time": "2026-10-20T10:00:00Z"'}],
                       {'E3': source_text(meta)})['status'] == 'grounded'
    conv = check_reply('2500 mg/L is 2.5 g/L.', [{'text': '2500 mg/L equals 2.5 g/L', 'kind': 'derived',
                       'source_id': 'E1', 'quote': 'Assay result 2500 mg/L'}], src)
    assert conv['status'] == 'grounded' and conv['derived_numbers'] == [2.5], conv
    fc = {'F': '{"predicted": 5.411283, "measured": 3133333.33, "viability": [89.25, 6.17], "ks": 0.0027853}'}
    live = check_reply('Glucose 5.41 g/L; cells 3.13 million cells/mL; Ks 0.0028; viability fell from 89.25 % to 6.17 %, '
                       'a drop of 83.08 points.', [], fc)
    assert live['status'] == 'no_claims' and live['derived_numbers'] == [83.08], live
    assert check_reply('Glucose 5.45 g/L.', [], fc)['unsupported_numbers'] == [5.45]  # rounding is not a licence
    # A calculated number counts only when its inputs are in the answer; otherwise almost any number would pass.
    assert check_reply('Viability fell 83.08 points.', [], fc)['unsupported_numbers'] == [83.08]
    assert check_reply('Viable density 9,626,667 cells/mL.', [], {'S': 'vcd 9626667'})['status'] == 'no_claims'
    wrong = check_reply('DO read 61 %, 44 %, 33 %, 24 % (the last three below a 30 % limit).', [], {'H': '61 44 33 24 30'})
    assert wrong['status'] == 'contradicted' and wrong['contradictions'][0]['but'] == '44 %, 33 %, 24 %', wrong
    print('ok')
