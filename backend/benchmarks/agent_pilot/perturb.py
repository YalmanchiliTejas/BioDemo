"""Metamorphic variants of authored worlds: more cases without new labels.

Each transform changes the world in a known way, so the expected change in the
answer is known without a new expert oracle:

* rename_ids      - every identifier gets a new number; old IDs must vanish.
* remove_evidence - the required source becomes an empty export; the answer must
                    say the information is missing and must not state its specifics.
* add_distractor  - a renamed near-copy of the source is also seeded; its IDs must
                    never be used to answer.

Truth still never enters the application; banned tokens are grader-only.
"""
from __future__ import annotations

from copy import deepcopy
import re

from src.workflows.claim_verification import NUMBER

TOKEN = re.compile(r'\b[A-Z][A-Z0-9]{0,8}-\d{1,3}\b')
KINDS = ('rename_ids', 'remove_evidence', 'add_distractor')
EMPTY = 'SYNTHETIC evaluation source; no real manufacturing data.\nExport contained headers only; no rows were included.'


def _walk(value, fn):
    if isinstance(value, str):
        return fn(value)
    if isinstance(value, list):
        return [_walk(v, fn) for v in value]
    if isinstance(value, dict):
        return {k: _walk(v, fn) for k, v in value.items()}
    return value


def _tokens(case):
    found = set()
    _walk({k: v for k, v in case.items() if k != 'id'}, lambda s: found.update(TOKEN.findall(s)) or s)
    return found


def _mapping(tokens, offset):
    """Deterministic renumbering that never collides with an existing token."""
    taken, out = set(tokens), {}
    for token in sorted(tokens):
        prefix, num = token.rsplit('-', 1)
        n = (int(num) * 7 + offset) % 900 + 100
        while f'{prefix}-{n}' in taken:
            n += 1
        out[token] = f'{prefix}-{n}'
        taken.add(out[token])
    return out


def _rename(text, mapping):
    return TOKEN.sub(lambda m: mapping.get(m.group(0), m.group(0)), text)


def _reid(case, kind, original):
    cid = f"{original['id']}-p-{kind}"
    case.update(id=cid, perturbation={'kind': kind, 'of': original['id']})
    case['truth']['private_sentinels'] = [f'PRIVATE_SITE_{cid}', f'PRIVATE_TENANT_{cid}']
    return case


def _specifics(text):
    """IDs and numbers a reader could only learn from this text (years, tiny ints excluded)."""
    numbers = {n.rstrip('.') for n in NUMBER.findall(text)
               if not re.fullmatch(r'(19|20)\d\d\.?', n) and not (n.rstrip('.').isdigit() and int(n.rstrip('.')) < 10)}
    return set(TOKEN.findall(text)) | numbers


def rename_ids(case):
    mapping = _mapping(_tokens(case), 311)
    if not mapping:
        return None
    out = _walk({k: v for k, v in deepcopy(case).items() if k != 'id'}, lambda s: _rename(s, mapping))
    out['truth']['banned_tokens'] = sorted(mapping)
    return _reid(out, 'rename_ids', case)


def remove_evidence(case):
    truth = case['truth']
    if case['family'] in ('memory', 'background') or not truth['required_read_ids'] or truth['expected_proposals']:
        return None
    out = deepcopy(case)
    removed = [s for s in out['sources'] if s['id'] in truth['required_read_ids']]
    kept = ' '.join([out['prompt'], *out['followups'], *(s['content'] for s in out['sources'] if s not in removed),
                     *(r['description'] for r in out['cases'])])
    banned = set().union(*(_specifics(s['content']) for s in removed)) - _specifics(kept)
    for source in removed:
        source['content'] = EMPTY
    out['truth'].update(
        required_facts=['the inspected record contains no data that answers the question',
                        'the answer names the missing evidence instead of supplying values'],
        forbidden_claims=[*truth['forbidden_claims'], *truth['required_facts']],
        banned_tokens=sorted(banned))
    for key in ('normalized_values', 'feasible', 'applicable_revision', 'affected_ids', 'schedule_constraints'):
        out['truth'].pop(key, None)
    return _reid(out, 'remove_evidence', case)


def add_distractor(case):
    truth = case['truth']
    asked = set(TOKEN.findall(' '.join([case['prompt'], *case['followups']])))
    primary = next((s for s in case['sources'] if s['id'] in truth['required_read_ids']), None)
    if not primary or not asked & set(TOKEN.findall(primary['content'])):
        return None  # without a named target, a decoy makes the question legitimately ambiguous
    mapping = _mapping(_tokens(case), 577)
    out = deepcopy(case)
    rid = f"PILOT:{case['id']}-p-add_distractor-other-register"
    out['sources'].append({'id': rid, 'filename': 'SYNTHETIC-other-register.txt',
                           'content': _rename(primary['content'], mapping)})
    out['cases'].append({'id': f"SYNTHETIC-{case['id']}-p-other", 'description': f'SYNTHETIC register. Evidence: {rid}',
                         'timeline': [{'description': f'SYNTHETIC register. Evidence: {rid}',
                                       'time': '2026-10-21T10:00:00Z', 'evidence_ids': [rid]}]})
    # Naming the decoy to set it aside is correct behaviour, so its ids are not banned; using it as the answer is wrong.
    decoys = sorted(set(mapping.values()) & set(TOKEN.findall(out['sources'][-1]['content'])))
    out['truth']['forbidden_claims'] = [*truth.get('forbidden_claims', []),
                                        f"facts about {', '.join(decoys)} are presented as facts about {', '.join(sorted(asked))}"]
    return _reid(out, 'add_distractor', case)


def perturb_suite(cases, kinds=KINDS):
    """All applicable variants, in input order. Inapplicable transforms are skipped, not faked."""
    fns = {'rename_ids': rename_ids, 'remove_evidence': remove_evidence, 'add_distractor': add_distractor}
    return [v for case in cases for kind in kinds if (v := fns[kind](case)) is not None]
