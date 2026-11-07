"""Recall evaluation: lexical-only vs hybrid (lexical + Modal embeddings) on paraphrased re-asks.

    cd backend && MODAL_EMBEDDINGS_URL=... MODAL_PROXY_TOKEN=... python -m benchmarks.memory_recall.evaluate

Builds an in-memory workspace with the cases' earlier answers and notes, then asks each query and scores whether a gold
item is ranked first (recall@1) or in the top three (recall@3). No database or production data is touched.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from src.lifesci import embeddings
from src.lifesci.container import Platform
from src.lifesci.ids import iso, utc_now
from src.lifesci.store import RecordStore

CASES = Path(__file__).with_name('cases.json')
TENANT, OWNER, SITE = 'recall-eval', 'eval-user', 'NF1'


def build(cases):
    p = Platform(RecordStore(), providers={})
    p.identity.assign_role(TENANT, OWNER, 'engineering', site_id=SITE)
    ctx = p.identity.context_for(TENANT, OWNER)
    thread = p.engineering_conversations.create(ctx, {'site_id': SITE})
    now = iso(utc_now())
    with p.store.transaction('eval') as tx:
        for t in cases['turns']:
            tx.put(TENANT, 'engineering_chat_turn', t['id'], {'id': t['id'], 'conversation_id': thread['id'], 'site_id': SITE,
                   'user_text': t['q'], 'reply': t['a'], 'status': 'completed', 'artifacts': [], 'created_at': now},
                   expected_revision=None, action='eval')
        for n in cases['notes']:
            tx.put(TENANT, 'memory_note', n['id'], {'note_id': n['id'], 'owner_id': OWNER, 'site_id': SITE, 'text': n['text'],
                   'kind': n['kind'], 'basis': 'user_stated', 'sources': [], 'entities': [], 'status': 'active', 'origin': 'assistant',
                   'conversation_id': thread['id'], 'turn_id': None, 'created_at': now, 'updated_at': now, 'uses': 0, 'history': []},
                   expected_revision=None, action='eval')
    return p, ctx, p.engineering_conversations._thread(ctx, thread['id']).state


def score(p, ctx, thread, queries):
    hits1 = hits3 = 0
    misses = []
    for case in queries:
        got = [r['id'] for r in p.agent_memory.recall(ctx, thread, case['q'], limit=3)['results']]
        hits1 += bool(got[:1] and got[0] in case['gold'])
        hit3 = bool(set(got) & set(case['gold']))
        hits3 += hit3
        if not hit3:
            misses.append({'q': case['q'], 'gold': case['gold'], 'got': got})
    n = len(queries)
    return {'recall@1': round(hits1 / n, 2), 'recall@3': round(hits3 / n, 2), 'misses': misses}


def main():
    cases = json.loads(CASES.read_text())
    embedder = embeddings.from_env()
    if embedder is None:
        sys.exit('set MODAL_EMBEDDINGS_URL and MODAL_PROXY_TOKEN to evaluate semantic recall')
    p, ctx, thread = build(cases)
    p.agent_memory.embedder = None
    lexical = score(p, ctx, thread, cases['queries'])
    p.agent_memory.embedder = embedder
    p.agent_memory.catch_up(TENANT)
    hybrid = score(p, ctx, thread, cases['queries'])
    print(json.dumps({'queries': len(cases['queries']), 'model': embedder.model, 'lexical_only': lexical, 'hybrid': hybrid}, indent=2))


if __name__ == '__main__':
    main()
