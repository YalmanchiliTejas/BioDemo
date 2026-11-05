"""Entity links across ingested sources, and human review of those links.

Links are derived at query time from the `relations` and `entities` tables written by
ingestion, so access scope, the as-of cutoff and per-source permission apply exactly as
they do to evidence. Nothing here invents a relationship: every link names its basis and,
where one exists, the exact source cell. Only human review decisions are stored.

Predicates describe how a link was observed, not what it means. "B1 and EQ7 are on one
source row" is a fact; "B1 was processed on EQ7" is an interpretation for the agent or a
reviewer to make from the cited row.
"""
from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from datetime import datetime, timezone

DDL = """
CREATE TABLE IF NOT EXISTS link_reviews (
 link_id TEXT NOT NULL, decision TEXT NOT NULL CHECK (decision IN ('confirmed','rejected')),
 actor TEXT NOT NULL, reason TEXT NOT NULL, reviewed_at TEXT NOT NULL
);
"""

BASIS = {
    'same_record': 'both identifiers appear in explicit ID columns of one source row',
    'same_identifier': 'identifiers are equal after ignoring case, spaces and - _ . / separators',
    'source_label': 'one identifier was inferred from a filename or sheet name',
    'co_observed': 'identifiers co-occur in a document extraction',
}
EXTRACTED = {'same_record', 'same_identifier'}  # deterministic; every other basis is a candidate


def canonical(identifier: str) -> str:
    """B-001, b_001 and 'B 001' share a key. Leading zeros are kept: B-01 and B-001 stay distinct."""
    return re.sub(r'[\s\-_./]+', '', str(identifier)).upper()


def link_id(scope: str, predicate: str, a: str, b: str) -> str:
    left, right = sorted((a, b))
    return hashlib.sha256(f'{scope}|{predicate}|{left}|{right}'.encode()).hexdigest()[:24]


def _instant(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _visible_at(value: str | None, as_of: str | None) -> bool:
    if as_of is None or value is None:
        return True
    try:
        return _instant(value) <= _instant(as_of)
    except ValueError:
        return False  # an unparseable timestamp cannot be shown to precede the cutoff


def review(store, link: str, decision: str, *, actor: str, reason: str) -> dict:
    """Record a human decision on a link. Append-only; the latest decision applies."""
    if decision not in {'confirmed', 'rejected'}:
        raise ValueError('decision must be confirmed or rejected')
    if not actor.strip() or not reason.strip():
        raise ValueError('a named reviewer and a reason are required')
    if not re.fullmatch(r'[0-9a-f]{24}', link):
        raise ValueError('unknown link id')
    row = {'link_id': link, 'decision': decision, 'actor': actor.strip(), 'reason': reason.strip(),
           'reviewed_at': datetime.now(timezone.utc).isoformat()}
    with store.connect() as con:
        con.executescript(DDL)
        con.execute('INSERT INTO link_reviews VALUES (:link_id,:decision,:actor,:reason,:reviewed_at)', row)
    return row


def _reviews(store, as_of: str | None, extra: list[dict] = ()) -> dict[str, dict]:
    with store.connect() as con:
        con.executescript(DDL)
        rows = [dict(r) for r in con.execute('SELECT * FROM link_reviews')]
    # extra: durable reviews kept outside this store (e.g. the CMO audit log), so a decision
    # made on one delivery applies to every later delivery with the same link.
    rows = sorted([*rows, *extra], key=lambda r: r['reviewed_at'])
    # Replaying history must not apply a review made after the cutoff.
    return {r['link_id']: r for r in rows if _visible_at(r['reviewed_at'], as_of)}


def links(store, *, sources: list[dict], as_of: str | None,
          reviews: list[dict] = ()) -> tuple[list[dict], dict[str, str]]:
    """All links visible through the given (already permission- and time-filtered) sources."""
    scope_of = {s['id']: s['access_scope'] for s in sources}
    # ponytail: full scan of permitted relations per call; index by entity if stores reach millions of pairs.
    with store.connect() as con:
        relations = [dict(r) for r in con.execute('SELECT * FROM relations')
                     if r['source_id'] in scope_of and _visible_at(r['available_at'], as_of)]
        kinds = {r['id']: r['kind'] for r in con.execute('SELECT id,kind FROM entities')}
        seen_in = defaultdict(set)  # entity -> scopes where a permitted source mentions it
        for r in con.execute('SELECT id,source_id FROM entities'):
            if r['source_id'] in scope_of:
                seen_in[r['id']].add(scope_of[r['source_id']])
    reviews = _reviews(store, as_of, list(reviews))
    edges: dict[str, dict] = {}

    def add(scope, predicate, a, b, evidence):
        ident = link_id(scope, predicate, a, b)
        edge = edges.setdefault(ident, {
            'link_id': ident, 'a': a, 'b': b, 'a_kind': kinds.get(a), 'b_kind': kinds.get(b),
            'predicate': predicate, 'basis': BASIS.get(predicate, predicate), 'scope': scope,
            'status': 'extracted' if predicate in EXTRACTED else 'candidate', 'evidence': []})
        if evidence:
            edge['evidence'].append(evidence)

    for r in relations:
        scope = scope_of[r['source_id']]
        seen_in[r['left_id']].add(scope); seen_in[r['right_id']].add(scope)
        add(scope, r['relation'], r['left_id'], r['right_id'],
            {'source_id': r['source_id'], 'evidence_id': r.get('evidence_id'), 'available_at': r['available_at']})

    # Deterministic aliases: same kind, same scope, same canonical key. Only among identifiers a
    # permitted, already-available source mentions, so an alias cannot leak a future or foreign record.
    groups = defaultdict(list)
    for entity, scopes in seen_in.items():
        for scope in scopes:
            groups[(scope, kinds.get(entity), canonical(entity))].append(entity)
    aliases: dict[str, str] = {}
    for (scope, _kind, _key), members in groups.items():
        members = sorted(set(members))
        for other in members[1:]:
            add(scope, 'same_identifier', members[0], other, None)
            aliases[other] = members[0]

    for ident, edge in edges.items():
        if ident in reviews:
            edge['status'] = reviews[ident]['decision']
            edge['review'] = {k: reviews[ident][k] for k in ('actor', 'reason', 'reviewed_at')}
    return list(edges.values()), aliases


def neighborhood(store, entity_id: str, *, sources: list[dict], as_of: str | None,
                 hops: int = 1, include_candidates: bool = True, reviews: list[dict] = ()) -> dict:
    all_edges, _ = links(store, sources=sources, as_of=as_of, reviews=reviews)
    usable = [e for e in all_edges if e['status'] != 'rejected'
              and (include_candidates or e['status'] != 'candidate')]
    adjacent = defaultdict(list)
    for e in usable:
        adjacent[e['a']].append(e); adjacent[e['b']].append(e)
    chosen: dict[str, dict] = {}

    def with_aliases(nodes: set[str]) -> set[str]:
        # An alias (B001 = B-001) is the same entity, so following it never costs a hop.
        found, stack = set(nodes), list(nodes)
        while stack:
            node = stack.pop()
            for e in adjacent[node]:
                if e['predicate'] == 'same_identifier':
                    chosen[e['link_id']] = e
                    other = e['a'] if e['b'] == node else e['b']
                    if other not in found:
                        found.add(other); stack.append(other)
        return found

    start = with_aliases({entity_id})
    reached, frontier = set(start), set(start)
    for _ in range(hops):
        nxt = set()
        for node in frontier:
            for e in adjacent[node]:
                chosen[e['link_id']] = e
                nxt |= {e['a'], e['b']} - reached
        nxt = with_aliases(nxt) - reached
        reached |= nxt
        frontier = nxt
    rejected = sum(1 for e in all_edges if e['status'] == 'rejected' and {e['a'], e['b']} & reached)
    warnings = []
    if not chosen:
        warnings.append(f'No links for {entity_id!r} among {len(sources)} permitted, available sources; '
                        'this is not evidence that none exist elsewhere.')
    if rejected:
        warnings.append(f'{rejected} reviewer-rejected link(s) omitted.')
    return {'entity_id': entity_id, 'aliases': sorted(start - {entity_id}),
            'entities': sorted(reached), 'links': sorted(chosen.values(), key=lambda e: (e['status'] != 'confirmed',
                                                                                      e['status'] != 'extracted', e['link_id'])),
            'sources_searched': len(sources), 'warnings': warnings}
