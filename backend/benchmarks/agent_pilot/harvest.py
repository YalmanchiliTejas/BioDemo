"""Turn recorded user corrections into UNREVIEWED regression-case candidates.

Every mission correction (POST /missions/{id}/corrections) marks a reply a user
found wrong. This exports the question, the sources the assistant read and the
correction as an authored-case JSON with empty required_facts. A reviewer must
write the expected facts and set review_status before it can grade anything.

Output contains customer content: it is refused inside the repository unless
the path is git-ignored. It only reads, with migrations disabled; still point it
at a backup copy or read replica, never the live primary. Run as an operator.

  .venv/bin/python -m benchmarks.agent_pilot.harvest --db backup.sqlite|postgresql://... --tenant TENANT --output DIR
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess

from src.lifesci.store import RecordStore

ROOT = Path(__file__).resolve().parents[3]


def _key(text):
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')[:40] or 'source'


def candidates(store, tenant):
    tx = store.read()
    threads = {r.state['mission_id']: r.state for r in tx.list(tenant, 'engineering_conversation')}
    for mission in tx.list(tenant, 'mission'):
        thread = threads.get(mission.id)
        if not thread:
            continue
        turns = [tx.require(tenant, 'engineering_chat_turn', t).state for t in thread['turn_ids']]
        for corr in mission.state.get('corrections', []):
            before = [t for t in turns if t.get('created_at', '') <= corr['at'] and t.get('reply')]
            if not before:
                continue
            turn = before[-1]
            sources = {}
            for artifact in turn['artifacts']:
                if artifact['kind'] != 'assistant_workspace_result':
                    continue
                record = (tx.get(tenant, artifact['kind'], artifact['id']) or None)
                record = record and record.state.get('record')
                if record:
                    data = record.get('data', {})
                    sources[record['id']] = data.get('original') or json.dumps(data, ensure_ascii=False, default=str)
            keys = {sid: f'{_key(sid)}-{i}' for i, sid in enumerate(sources)}
            rejected = [h['hypothesis'] for h in mission.state.get('rejected_hypotheses', [])
                        if h['correction_id'] == corr['correction_id']]
            yield {
                'id': f"harvest-{corr['correction_id']}", 'family': 'expert', 'review_status': 'unreviewed', 'reviewer': '',
                'provenance': f"User correction {corr['correction_id']} at {corr['at']}; conversation {thread['id']} turn {turn['id']}",
                'prompt': turn['user_text'],
                'sources': [{'key': keys[sid], 'content': text} for sid, text in sources.items()],
                'truth': {'required_read': list(keys.values()), 'required_facts': [], 'forbidden_claims': rejected,
                          'banned_tokens': [], 'expected_proposals': False, 'answerable': True},
                'notes': {'reply_that_was_corrected': turn['reply'], 'user_correction': corr['text'],
                          'grounding_at_the_time': turn.get('grounding'),
                          'reviewer_todo': 'Write required_facts from the correction and sources; add forbidden_claims '
                                           'for the wrong statement; strip identifying details; then set review_status.'},
            }


def _safe_output(path: Path):
    path = path.resolve()
    if ROOT in path.parents or path == ROOT:
        ignored = subprocess.run(['git', '-C', str(ROOT), 'check-ignore', '-q', str(path)]).returncode == 0
        if not ignored:
            raise SystemExit(f'{path} is inside the repository and not git-ignored; harvested cases contain customer content')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--db', required=True, help='SQLite path or postgresql:// URL of a backup/replica')
    ap.add_argument('--tenant', required=True)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    if '://' not in args.db and not Path(args.db).is_file():
        ap.error('--db must be an existing SQLite file or a postgresql:// URL')
    _safe_output(args.output)
    args.output.mkdir(parents=True, exist_ok=True)
    written = skipped = 0
    for case in candidates(RecordStore(args.db, migrate=False), args.tenant):
        out = args.output / f"{case['id']}.json"
        if out.exists():  # never overwrite a reviewer's edits
            skipped += 1
            continue
        out.write_text(json.dumps(case, indent=2, ensure_ascii=False) + '\n')
        written += 1
    print(json.dumps({'written': written, 'kept_existing': skipped, 'output': str(args.output)}))


if __name__ == '__main__':
    main()
