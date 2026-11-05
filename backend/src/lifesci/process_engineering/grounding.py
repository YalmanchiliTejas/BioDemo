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


def _numbers(text):
    return {float(m) for m in NUMBER.findall(str(text))}


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
    # ponytail: exact float match on parsed numbers; no unit-aware arithmetic check.
    reply_numbers = _numbers(reply)
    unsupported_numbers = sorted(reply_numbers - allowed - derived)
    verified = sum(r['verified'] for r in results)
    if not results and not unsupported_numbers:
        status = 'no_claims'
    elif verified == len(results) and not unsupported_numbers:
        status = 'grounded'
    elif verified:
        status = 'partially_grounded'
    else:
        status = 'ungrounded'
    return {'status': status, 'claims': results, 'unsupported_numbers': unsupported_numbers,
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
    print('ok')
