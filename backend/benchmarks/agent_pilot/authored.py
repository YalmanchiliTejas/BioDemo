"""Load human-authored cases (domain expert, public-source, harvested corrections).

One JSON file per case. Only `review_status: "reviewed"` cases with a named
reviewer run against the agent; harvested candidates start "unreviewed".
Format: see benchmarks/agent_pilot/cases/README.md.
"""
from __future__ import annotations

import json
from pathlib import Path

from .scenarios import FAMILIES, _base, _record, _source

_TOP = {'id', 'family', 'review_status', 'reviewer', 'provenance', 'prompt', 'followups', 'sources', 'cases', 'truth', 'notes'}
_TRUTH = {'required_read', 'required_facts', 'forbidden_claims', 'banned_tokens', 'expected_proposals', 'answerable'}


def _fail(path, msg):
    raise ValueError(f'{path.name}: {msg}')


def load_case(path: Path, split: str, *, allow_unreviewed=False) -> dict:
    raw = json.loads(path.read_text())
    if not isinstance(raw, dict) or set(raw) - _TOP:
        _fail(path, f'unknown keys {sorted(set(raw) - _TOP)}')
    if raw.get('family') not in (*FAMILIES, 'expert'):
        _fail(path, 'family must be one of the pilot families or "expert"')
    if not (isinstance(raw.get('prompt'), str) and raw['prompt'].strip()):
        _fail(path, 'prompt required')
    reviewed = raw.get('review_status') == 'reviewed' and str(raw.get('reviewer', '')).strip()
    if not reviewed and not allow_unreviewed:
        _fail(path, 'not reviewed; a named reviewer must confirm truth before it can grade the agent')
    truth = raw.get('truth', {})
    if set(truth) - _TRUTH or not truth.get('required_facts'):
        _fail(path, 'truth needs required_facts and only known keys')
    case = _base(raw['family'], split, 0)
    case.update(id=f"{split}-{raw['id']}", condition=raw.get('provenance', ''), prompt=raw['prompt'],
                followups=raw.get('followups', []), authored={'reviewer': raw.get('reviewer'), 'provenance': raw.get('provenance'),
                                                             'file': path.name, 'review_status': raw.get('review_status')})
    case['truth']['private_sentinels'] = [f"PRIVATE_SITE_{case['id']}", f"PRIVATE_TENANT_{case['id']}"]
    ids = {}
    for source in raw.get('sources', []):
        ids[source['key']] = _source(case, source['key'], source['content'])
    for record in raw.get('cases', []):
        refs = [ids[k] for k in record.get('source_keys', [])]
        _record(case, record['key'], record['description'] + (f" Evidence: {', '.join(refs)}" if refs else ''), refs)
    missing = [k for k in truth.get('required_read', []) if k not in ids]
    if missing:
        _fail(path, f'required_read names unknown source keys {missing}')
    case['truth'].update(required_read_ids=[ids[k] for k in truth.get('required_read', [])],
                         required_facts=truth['required_facts'], forbidden_claims=truth.get('forbidden_claims', []),
                         banned_tokens=truth.get('banned_tokens', []), expected_proposals=bool(truth.get('expected_proposals')),
                         answerable=truth.get('answerable', True))
    return case


def load_dir(directory: Path, split: str = 'authored', *, allow_unreviewed=False) -> list[dict]:
    files = sorted(Path(directory).glob('*.json'))
    if not files:
        raise ValueError(f'no case files in {directory}')
    cases = [load_case(f, split, allow_unreviewed=allow_unreviewed) for f in files]
    dupes = {c['id'] for c in cases if [x['id'] for x in cases].count(c['id']) > 1}
    if dupes:
        raise ValueError(f'duplicate case ids {sorted(dupes)}')
    return cases
