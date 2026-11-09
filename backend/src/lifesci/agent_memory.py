"""The assistant's own memory (docs/architecture/assistant-memory.md), after Anthropic's "components of agent memory":

- transcripts: conversation turns, already saved with provenance (engineering_chat_turn)
- notes: what the assistant judged worth keeping (memory_note): lessons, decisions, preferences, open threads,
  warnings, each with its source records and how it is known
- representations: one page per entity (batch, lot, equipment, case) collecting the notes about it (memory_page)
- injected layer: a short index of the owner's most useful notes, loaded into every turn

Records stay the ground truth: a note points at records and is re-checked against their current revision whenever it
is read. Everything here is private to its owner (scope 'conversations' in memory.py); colleagues read it only under
a grant, and permissions are applied before ranking, so similarity search never surfaces another person's notes.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

from .embeddings import cosine
from .ids import iso, new_id, utc_now
from .memory import MemoryGrants, owner_of, principal

NOTE, PAGE, VECTOR, STATE = 'memory_note', 'memory_page', 'memory_vector', 'memory_state'
KINDS = ('lesson', 'decision', 'preference', 'open_thread', 'warning')
BASES = ('observed', 'calculated', 'user_stated', 'inferred')
INDEX_NOTES, INDEX_CHARS = 12, 3000
DUPLICATE = 0.93  # cosine above which two notes say the same thing
WORDS = re.compile(r'[a-z0-9]{2,}')
# A manufacturing identifier: letters then digits, optionally a run suffix (B-117, BR-07, L-8812, DEV-31, CHO-003-R01).
# Deliberately strict: "B-117/BR-07" is two entities and "BR-07-AF-DOSING-B-117" is not one (live: junk pages).
ID = re.compile(r'(?<![A-Za-z0-9])[A-Za-z]{1,6}-?\d{1,6}(?:-[A-Za-z]\d{1,3})?(?![A-Za-z0-9])')


def entities(text: str) -> list[str]:
    """Identifiers named in text, canonical: case and separators ignored (B-117 = b117)."""
    return sorted({m.replace('-', '').upper() for m in ID.findall((text or '').replace('/', ' '))})


def _lexical(query: str, text: str) -> float:
    q, t = set(WORDS.findall(query.casefold())), set(WORDS.findall((text or '').casefold()))
    words = len(q & t) / len(q) if q else 0.0
    ids = set(entities(query))
    return words + (len(ids & set(entities(text))) * 0.5)  # a shared identifier is strong evidence of relevance


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


class AgentMemory:
    def __init__(self, platform, embedder=None) -> None:
        self.p, self.embedder = platform, embedder
        self.grants: MemoryGrants = platform.memory

    # --- writing ---------------------------------------------------------------------------
    def inspected_refs(self, ctx, thread) -> dict[tuple[str, str], dict[str, Any]]:
        """Records this conversation actually read: the only basis a note may cite."""
        seen = {}
        for tid in thread['turn_ids']:
            for a in self.p.store.read().require(ctx.tenant_id, 'engineering_chat_turn', tid).state['artifacts']:
                # Only the host's explicit read path writes this versioned receipt.
                # Producing or merely listing an artifact does not count as inspection.
                inspected = a.get('inspected_ref')
                if inspected and inspected.get('kind') == a['kind'] and inspected.get('id') == a['id']:
                    seen[(inspected['kind'], inspected['id'])] = inspected
                rec = self.p.store.read().get(ctx.tenant_id, a['kind'], a['id'])
                for ref in (rec.state.get('inputs') or []) if rec else []:
                    if ref.get('kind') not in ('engineering_chat_turn',):
                        seen[(ref['kind'], ref['id'])] = ref
        return seen

    def remember(self, ctx, thread, turn_id, *, text: str, kind: str, basis: str,
                 sources: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        text = ' '.join(str(text or '').split())
        if not 10 <= len(text) <= 600:
            raise ValueError('a note is one or two sentences (10-600 characters)')
        if kind not in KINDS or basis not in BASES:
            raise ValueError(f'kind must be one of {KINDS}; basis one of {BASES}')
        owner = thread['owner_id']
        MemoryGrants.require_owner_write(ctx, owner)  # grants are read-only: a colleague's agent never writes here
        inspected = self.inspected_refs(ctx, thread)
        refs = []
        for s in sources or []:
            ref = inspected.get((str(s.get('kind', '')), str(s.get('id', ''))))
            if ref is None:
                raise ValueError(f"source {s.get('kind')}:{s.get('id')} was not read in this conversation; read it first")
            refs.append(ref)
        if basis != 'user_stated' and not refs:
            raise ValueError('cite the records this rests on (sources), or use basis user_stated for what the person told you')
        if refs:
            self.p.identity.validate_refs(ctx, refs)  # still readable and current, now
        user_text = self.p.store.read().require(ctx.tenant_id, 'engineering_chat_turn', turn_id).state.get('user_text', '')
        now = iso(utc_now())
        state = {'note_id': new_id('mnote'), 'owner_id': owner, 'site_id': thread['site_id'], 'text': text, 'kind': kind,
                 'basis': basis, 'sources': refs, 'entities': entities(' '.join([text, *[r['id'] for r in refs if r['kind'] in ('case', 'batch')]])),
                 'status': 'active', 'origin': 'assistant', 'conversation_id': thread['id'], 'turn_id': turn_id,
                 'user_quote': user_text[:500] if basis == 'user_stated' else None,
                 'created_at': now, 'updated_at': now, 'uses': 0, 'last_used_at': None, 'history': []}
        duplicate = self._duplicate(ctx.tenant_id, owner, text)
        with self.p.store.transaction(ctx.actor_id) as tx:
            if duplicate:  # the same lesson again: refresh it and widen its sources instead of a second copy
                rec = tx.require(ctx.tenant_id, NOTE, duplicate)
                merged = {**rec.state, 'updated_at': now, 'sources': list({(r['kind'], r['id']): r for r in
                          [*rec.state['sources'], *refs]}.values()), 'history': [*rec.state['history'], {'event': 'reaffirmed', 'at': now, 'turn_id': turn_id}]}
                out = tx.put(ctx.tenant_id, NOTE, duplicate, merged, expected_revision=rec.revision, action='reaffirm_memory_note')
            else:
                out = tx.put(ctx.tenant_id, NOTE, state['note_id'], state, expected_revision=None, action='remember',
                             event_type='memory.noted', event_payload={'note_id': state['note_id'], 'owner_id': owner})
        self._index(ctx.tenant_id, owner, NOTE, out.state['note_id'], out.state['text'], thread['site_id'])
        self.mark_active(ctx.tenant_id, owner)
        return self._view(ctx, out.state, out.revision)

    def set_status(self, ctx, note_id: str, status: str, reason: str = '') -> dict[str, Any]:
        """The owner forgets a note or marks it wrong. Kept (not deleted) so the audit trail stays whole."""
        if status not in ('forgotten', 'wrong', 'active'):
            raise ValueError('status is forgotten, wrong or active')
        with self.p.store.transaction(ctx.actor_id) as tx:
            rec = tx.require(ctx.tenant_id, NOTE, note_id)
            if principal(ctx) != rec.state['owner_id'] or ctx.delegated_from:
                raise PermissionError('only the person whose memory this is can change it')
            now = iso(utc_now())
            out = tx.put(ctx.tenant_id, NOTE, note_id, {**rec.state, 'status': status, 'updated_at': now,
                         'history': [*rec.state['history'], {'event': status, 'at': now, 'by': ctx.actor_id, 'reason': reason[:500]}]},
                         expected_revision=rec.revision, action=f'memory_note_{status}')
        return self._view(ctx, out.state, out.revision)

    # --- embeddings ----------------------------------------------------------------------
    def _index(self, tenant, owner, kind, rid, text, site_id) -> bool:
        """Best effort: recall still works lexically if the embedding service is down; the tick catches up."""
        if self.embedder is None:
            return False
        key = f'{kind}:{rid}'
        current = self.p.store.read().get(tenant, VECTOR, key)
        if current and current.state['text_hash'] == _hash(text) and current.state['model'] == self.embedder.model:
            return True
        try:
            vector = self.embedder.embed([text[:8000]])[0]
        except Exception:
            return False
        with self.p.store.transaction('memory-indexer') as tx:
            rec = tx.get(tenant, VECTOR, key)
            tx.put(tenant, VECTOR, key, {'owner_id': owner, 'ref_kind': kind, 'ref_id': rid, 'site_id': site_id,
                   'model': self.embedder.model, 'text_hash': _hash(text), 'vector': [round(x, 6) for x in vector]},
                   expected_revision=rec.revision if rec else None, action='embed_memory')
        return True

    def _duplicate(self, tenant, owner, text) -> str | None:
        norm = ' '.join(text.casefold().split())
        notes = [r for r in self.p.store.read().list(tenant, NOTE) if r.state['owner_id'] == owner and r.state['status'] == 'active']
        for r in notes:
            if ' '.join(r.state['text'].casefold().split()) == norm:
                return r.id
        if self.embedder is None or not notes:
            return None
        try:
            v = self.embedder.embed([text])[0]
        except Exception:
            return None
        vectors = {r.state['ref_id']: r.state['vector'] for r in self.p.store.read().list(tenant, VECTOR)
                   if r.state['ref_kind'] == NOTE and r.state['owner_id'] == owner}
        best = max(((cosine(v, vectors[r.id]), r.id) for r in notes if r.id in vectors), default=(0., None))
        return best[1] if best[0] >= DUPLICATE else None

    def catch_up(self, tenant) -> int:
        """Embed turns and notes that are missing a current vector (service down at write time, or a new model)."""
        if self.embedder is None:
            return 0
        done = 0
        for kind, rid, owner, text, site in self._documents(tenant):
            current = self.p.store.read().get(tenant, VECTOR, f'{kind}:{rid}')
            if current and current.state['text_hash'] == _hash(text) and current.state['model'] == self.embedder.model:
                continue
            if not self._index(tenant, owner, kind, rid, text, site):
                break
            done += 1
        return done

    def _documents(self, tenant):
        owners = {r.id: r.state.get('owner_id', '') for r in self.p.store.read().list(tenant, 'engineering_conversation')}
        for r in self.p.store.read().list(tenant, 'engineering_chat_turn'):
            if r.state.get('status') in ('completed', 'needs_information') and r.state.get('reply'):
                yield ('engineering_chat_turn', r.id, owners.get(r.state.get('conversation_id'), ''),
                       f"Q: {r.state.get('user_text', '')}\nA: {r.state.get('reply', '')}", r.state.get('site_id'))
        for r in self.p.store.read().list(tenant, NOTE):
            if r.state['status'] == 'active':
                yield NOTE, r.id, r.state['owner_id'], r.state['text'], r.state['site_id']

    # --- reading ----------------------------------------------------------------------------
    def _check(self, ctx, state) -> dict[str, Any]:
        """Re-check a note's sources now: a changed or unreadable record makes the note stale for this read."""
        problems = []
        for ref in state.get('sources') or []:
            rec = self.p.store.read().get(ctx.tenant_id, ref['kind'], ref['id'])
            if rec is None:
                problems.append(f"{ref['kind']} {ref['id']} no longer exists")
            elif rec.revision != ref.get('revision'):
                problems.append(f"{ref['kind']} {ref['id']} changed since this was noted")
        return {'current': not problems, 'problems': problems}

    def _view(self, ctx, state, revision=None) -> dict[str, Any]:
        check = self._check(ctx, state)
        status = 'stale' if state['status'] == 'active' and not check['current'] else state['status']
        return {'id': state['note_id'], 'text': state['text'], 'kind': state['kind'], 'basis': state['basis'],
                'status': status, 'stale_because': check['problems'], 'origin': state['origin'],
                'sources': [{k: r.get(k) for k in ('kind', 'id', 'revision')} for r in state['sources']],
                'entities': state['entities'], 'site_id': state['site_id'], 'conversation_id': state['conversation_id'], 'created_at': state['created_at'],
                'updated_at': state['updated_at'], 'owner_id': state['owner_id'], 'history': state.get('history', [])[-5:]}

    def _readable(self, ctx, kind, state) -> bool:
        owned = owner_of(self.p.store, ctx.tenant_id, kind, state)
        return owned is None or self.grants.can_read(ctx, *owned)

    def notes(self, ctx, owner_id: str | None = None, *, active_only=False) -> list[dict[str, Any]]:
        owner = owner_id or principal(ctx)
        self.grants.require_read(ctx, owner, 'conversations')
        out = [self._view(ctx, r.state, r.revision) for r in self.p.store.read().list(ctx.tenant_id, NOTE)
               if r.state['owner_id'] == owner]
        if active_only:
            out = [n for n in out if n['status'] in ('active', 'stale')]
        return sorted(out, key=lambda n: n['updated_at'], reverse=True)

    def pages(self, ctx, owner_id: str | None = None) -> list[dict[str, Any]]:
        owner = owner_id or principal(ctx)
        self.grants.require_read(ctx, owner, 'conversations')
        return sorted((r.state for r in self.p.store.read().list(ctx.tenant_id, PAGE) if r.state['owner_id'] == owner),
                      key=lambda pg: pg['entity'])

    def open(self, ctx, memory_id: str) -> dict[str, Any]:
        for kind in (NOTE, PAGE):
            rec = self.p.store.read().get(ctx.tenant_id, kind, memory_id)
            if rec is not None:
                if not self._readable(ctx, kind, rec.state):
                    raise PermissionError('this is part of another person’s private memory')
                if kind == NOTE:
                    self._used(ctx.tenant_id, [memory_id])
                    return self._view(ctx, rec.state, rec.revision)
                notes = [self.p.store.read().get(ctx.tenant_id, NOTE, n) for n in rec.state['note_ids']]
                return {**rec.state, 'notes': [self._view(ctx, n.state) for n in notes if n is not None]}
        raise KeyError(f'no memory {memory_id}')

    def _used(self, tenant, note_ids) -> None:
        now = iso(utc_now())
        with self.p.store.transaction('memory-usage') as tx:
            for nid in note_ids:
                rec = tx.get(tenant, NOTE, nid)
                if rec is not None:
                    tx.put(tenant, NOTE, nid, {**rec.state, 'uses': rec.state.get('uses', 0) + 1, 'last_used_at': now},
                           expected_revision=rec.revision, action='use_memory_note')

    def index(self, ctx, owner_id: str) -> list[dict[str, Any]]:
        """The injected layer: a few of the owner's most useful active notes, small enough for every turn."""
        state = self.p.store.read().get(ctx.tenant_id, STATE, owner_id)
        promoted = (state.state.get('promoted') if state else None) or []
        notes = {n['id']: n for n in self.notes(ctx, owner_id, active_only=True)}
        order = [notes[i] for i in promoted if i in notes] + sorted(
            (n for i, n in notes.items() if i not in promoted), key=lambda n: n['updated_at'], reverse=True)
        out, size = [], 0
        for n in order[:INDEX_NOTES]:
            line = {'id': n['id'], 'text': n['text'][:220], 'kind': n['kind'], 'basis': n['basis'],
                    **({'stale': n['stale_because']} if n['status'] == 'stale' else {})}
            size += len(str(line))
            if size > INDEX_CHARS:
                break
            out.append(line)
        return out

    def recall(self, ctx, thread, query: str, *, exclude_turn_id: str | None = None, limit: int = 8) -> dict[str, Any]:
        """Hybrid recall over earlier turns, notes and entity pages: lexical (words and identifiers) and semantic
        (embeddings) rankings merged by reciprocal rank. Candidates are filtered by permission first."""
        query = ' '.join(str(query or '').split())[:500]
        if not query:
            raise ValueError('say what to look for')
        owners = {r.id: r.state.get('owner_id', '') for r in self.p.store.read().list(ctx.tenant_id, 'engineering_conversation')}
        candidates = []
        for r in self.p.store.read().list(ctx.tenant_id, 'engineering_chat_turn'):
            s = r.state
            if r.id == exclude_turn_id or not s.get('reply') or s.get('site_id', thread['site_id']) != thread['site_id']:
                continue
            if not self._readable(ctx, 'engineering_chat_turn', s):
                continue
            owner = owners.get(s.get('conversation_id'), '')
            candidates.append({'type': 'earlier_answer', 'kind': 'engineering_chat_turn', 'id': r.id, 'revision': r.revision,
                               'owner': owner, 'text': f"Q: {s.get('user_text', '')}\nA: {s.get('reply', '')}",
                               'when': s.get('created_at'), 'conversation_id': s.get('conversation_id')})
        for r in self.p.store.read().list(ctx.tenant_id, NOTE):
            if r.state['status'] == 'active' and r.state['site_id'] == thread['site_id'] and self._readable(ctx, NOTE, r.state):
                candidates.append({'type': 'note', 'kind': NOTE, 'id': r.id, 'owner': r.state['owner_id'],
                                   'text': r.state['text'], 'when': r.state['updated_at']})
        for r in self.p.store.read().list(ctx.tenant_id, PAGE):
            if r.state.get('site_id') == thread['site_id'] and self._readable(ctx, PAGE, r.state):
                candidates.append({'type': 'entity_page', 'kind': PAGE, 'id': r.id, 'owner': r.state['owner_id'],
                                   'text': r.state['summary'], 'when': r.state['updated_at']})
        # Measured on benchmarks/memory_recall (20 paraphrased re-asks): semantic alone 0.70/0.95 (recall@1/@3), a
        # reciprocal-rank merge with word overlap 0.50/0.75 (weak overlaps drowned good matches). So: rank by meaning,
        # and let words count only where they are decisive: shared identifiers (B-117, L-8812) and exact phrases.
        ids = set(entities(query))
        boost = lambda c: 0.15 * len(ids & set(entities(c['text']))) + (0.05 if query.casefold() in c['text'].casefold() else 0.)
        semantic, fused = 'unavailable', None
        if self.embedder is not None and candidates:
            vectors = {r.state['ref_id']: r.state['vector'] for r in self.p.store.read().list(ctx.tenant_id, VECTOR)
                       if r.state['model'] == self.embedder.model}
            try:
                q = self.embedder.embed([query], query=True)[0]
                score = lambda c: (cosine(q, vectors[c['id']]) if c['id'] in vectors else _lexical(query, c['text']) * 0.5) + boost(c)
                fused = sorted(candidates, key=score, reverse=True)
                missing = sum(c['id'] not in vectors for c in candidates)
                semantic = 'used' if not missing else f'used; {missing} items not yet embedded were matched by words only'
            except Exception:
                semantic = 'unavailable (embedding service did not answer); matched by words only'
        if fused is None:
            fused = sorted((c for c in candidates if _lexical(query, c['text']) > 0), key=lambda c: -_lexical(query, c['text']))
        me = principal(ctx)
        out = [{'type': c['type'], 'kind': c['kind'], 'id': c['id'], **({'revision': c['revision']} if 'revision' in c else {}),
                'snippet': c['text'][:400], 'when': c['when'],
                **({'shared_from': c['owner']} if c['owner'] and c['owner'] != me else {})} for c in fused[:limit]]
        self._used(ctx.tenant_id, [c['id'] for c in out if c['kind'] == NOTE])
        return {'results': out, 'semantic_search': semantic, 'searched': len(candidates),
                'note': 'Earlier answers and notes are interpretations: re-check the underlying records before relying on them.'}

    # --- dreaming: offline consolidation -------------------------------------------------------------
    def mark_active(self, tenant, owner) -> None:
        """Note new activity (a finished answer, a new note) so consolidation finds the owner without scanning."""
        if not owner:
            return
        now = iso(utc_now())
        with self.p.store.transaction('memory-activity') as tx:
            cur = tx.get(tenant, STATE, owner)
            tx.put(tenant, STATE, owner, {**(cur.state if cur else {'owner_id': owner}), 'active_at': now},
                   expected_revision=cur.revision if cur else None, action='memory_activity')

    def due(self, tenant) -> list[str]:
        """Owners with activity since their last consolidation, not consolidated in the last few minutes. Reads only the
        small per-owner state records (live: scanning every turn and note each minute was most of our database egress)."""
        from datetime import timedelta
        from .ids import parse_iso
        out = []
        for r in self.p.store.read().list(tenant, STATE):
            active, last = r.state.get('active_at'), r.state.get('last_dream_at')
            if active and (last is None or (active > last and utc_now() - parse_iso(last) >= timedelta(minutes=DREAM_EVERY_MINUTES))):
                out.append(r.id)
        return out

    def dream(self, tenant, owner, *, use_model=True) -> dict[str, Any]:
        started = iso(utc_now())  # activity during this pass stays newer than last_dream_at, so it is not lost
        ctx = self.p.identity.context_for(tenant, owner)
        st = self.p.store.read().get(tenant, STATE, owner)
        since = (st.state.get('last_dream_at') if st else None) or ''
        report = {'embedded': self.catch_up(tenant), 'marked_stale': 0, 'merged': 0, 'new_notes': 0, 'corrections': 0}
        mine = [r for r in self.p.store.read().list(tenant, NOTE) if r.state['owner_id'] == owner]
        now = iso(utc_now())

        def change(rec, status, event, **extra):
            with self.p.store.transaction('memory-dreaming') as tx:
                cur = tx.require(tenant, NOTE, rec.id)
                tx.put(tenant, NOTE, rec.id, {**cur.state, 'status': status, 'updated_at': now, **extra,
                       'history': [*cur.state['history'], {'event': event, 'at': now, 'by': 'dreaming', **extra}]},
                       expected_revision=cur.revision, action=f'dream_{event}')
        # 1. Records are the ground truth: a note whose sources changed is stale until reaffirmed.
        for r in mine:
            if r.state['status'] == 'active' and not self._check(ctx, r.state)['current']:
                change(r, 'stale', 'sources_changed')
                report['marked_stale'] += 1
        # 2. The same lesson noted twice: keep the newer, link the older to it.
        active = [r for r in self.p.store.read().list(tenant, NOTE) if r.state['owner_id'] == owner and r.state['status'] == 'active']
        vectors = {r.state['ref_id']: r.state['vector'] for r in self.p.store.read().list(tenant, VECTOR) if r.state['ref_kind'] == NOTE}
        active.sort(key=lambda r: r.state['updated_at'], reverse=True)
        kept: list = []
        for r in active:
            twin = next((k for k in kept if r.id in vectors and k.id in vectors and cosine(vectors[r.id], vectors[k.id]) >= DUPLICATE), None)
            if twin is not None:
                change(r, 'superseded', 'merged', superseded_by=twin.id)
                report['merged'] += 1
            else:
                kept.append(r)
        # 3. Consolidate recent conversations: the model proposes notes; the host checks every source.
        if use_model:
            report.update(self._consolidate(ctx, owner, since))
        # 4. Entity pages, and 5. the injected index.
        self._rebuild_pages(tenant, owner)
        active = [r.state for r in self.p.store.read().list(tenant, NOTE) if r.state['owner_id'] == owner and r.state['status'] == 'active']
        rank = lambda n: (n.get('uses', 0), n['kind'] in ('warning', 'decision'), n['updated_at'])
        promoted = [n['note_id'] for n in sorted(active, key=rank, reverse=True)[:INDEX_NOTES]]
        suggestions = [{'note_id': n['note_id'], 'text': n['text']} for n in active
                       if n['kind'] in ('preference', 'lesson') and n.get('uses', 0) >= RULE_AFTER_USES][:5]
        with self.p.store.transaction('memory-dreaming') as tx:
            cur = tx.get(tenant, STATE, owner)
            tx.put(tenant, STATE, owner, {**(cur.state if cur else {}), 'owner_id': owner, 'last_dream_at': started,
                   'promoted': promoted, 'rule_suggestions': suggestions, 'last_report': report},
                   expected_revision=cur.revision if cur else None, action='dream')
        return report

    def _consolidate(self, ctx, owner, since) -> dict[str, int]:
        from .gateway import TaskRequest
        import json as _json
        threads = {r.id: r.state for r in self.p.store.read().list(ctx.tenant_id, 'engineering_conversation') if r.state.get('owner_id') == owner}
        turns = sorted((r for r in self.p.store.read().list(ctx.tenant_id, 'engineering_chat_turn')
                        if r.state.get('conversation_id') in threads and r.state.get('status') == 'completed'
                        and r.updated_at > since and r.state.get('reply')), key=lambda r: r.updated_at)[-DREAM_TURNS:]
        if not turns:
            return {'new_notes': 0, 'corrections': 0}
        notes = [{'id': r.id, 'text': r.state['text'], 'kind': r.state['kind'], 'basis': r.state['basis']}
                 for r in self.p.store.read().list(ctx.tenant_id, NOTE) if r.state['owner_id'] == owner and r.state['status'] == 'active'][:60]
        packet = {'existing_notes': notes, 'recent_conversations': [{
            'turn_id': t.id, 'asked': t.state.get('user_text', '')[:1500], 'answered': t.state['reply'][:3000],
            'records_read': [f"{k}:{i}" for (k, i) in self.inspected_refs(ctx, threads[t.state['conversation_id']])][:40]} for t in turns]}
        result = self.p.gateway.run(TaskRequest('investigation_planning', ctx, system=DREAM_SYSTEM, prompt=_json.dumps(packet),
                                                use_cache=False, timeout_s=150., prompt_version='memory-dream-v1', max_provider_calls=2))
        if result.status != 'completed' or not isinstance(result.output, dict):
            return {'new_notes': 0, 'corrections': 0, 'model': result.status}
        by_turn = {t.id: t for t in turns}
        new = fixed = 0
        for item in (result.output.get('new_notes') or [])[:10]:
            turn = by_turn.get(item.get('turn_id'))
            if turn is None:
                continue
            try:
                note = self.remember(ctx, threads[turn.state['conversation_id']], turn.id, text=item.get('text', ''),
                                     kind=item.get('kind', ''), basis=item.get('basis', ''),
                                     sources=[dict(zip(('kind', 'id'), s.split(':', 1))) if isinstance(s, str) else s for s in item.get('sources') or []])
                with self.p.store.transaction('memory-dreaming') as tx:
                    rec = tx.require(ctx.tenant_id, NOTE, note['id'])
                    if rec.state['origin'] != 'dreaming' and rec.state['created_at'] == rec.state['updated_at']:
                        tx.put(ctx.tenant_id, NOTE, note['id'], {**rec.state, 'origin': 'dreaming'}, expected_revision=rec.revision, action='dream_note')
                new += 1
            except (ValueError, PermissionError, KeyError):
                continue  # an unsupported note is dropped, never stored without its basis
        mine = {n['id'] for n in notes}
        for item in (result.output.get('corrections') or [])[:10]:
            rec = self.p.store.read().get(ctx.tenant_id, NOTE, str(item.get('note_id', '')))
            if rec is None or rec.id not in mine or item.get('action') not in ('stale', 'superseded'):
                continue  # dreaming may retire a note; only its owner can call one wrong
            now = iso(utc_now())
            with self.p.store.transaction('memory-dreaming') as tx:
                cur = tx.require(ctx.tenant_id, NOTE, rec.id)
                tx.put(ctx.tenant_id, NOTE, rec.id, {**cur.state, 'status': item['action'], 'updated_at': now,
                       'history': [*cur.state['history'], {'event': item['action'], 'at': now, 'by': 'dreaming',
                                                            'reason': str(item.get('reason', ''))[:500]}]},
                       expected_revision=cur.revision, action='dream_correction')
            fixed += 1
        return {'new_notes': new, 'corrections': fixed}

    def _rebuild_pages(self, tenant, owner) -> None:
        """One page per entity: the owner's notes about it, quoted verbatim with their basis and sources."""
        active = [r.state for r in self.p.store.read().list(tenant, NOTE) if r.state['owner_id'] == owner and r.state['status'] in ('active', 'stale')]
        by_entity: dict[str, list] = {}
        for n in active:
            for e in n['entities']:
                by_entity.setdefault(e, []).append(n)
        now = iso(utc_now())
        with self.p.store.transaction('memory-dreaming') as tx:
            for entity, notes in by_entity.items():
                notes.sort(key=lambda n: n['updated_at'], reverse=True)
                summary = f'{entity}: ' + ' | '.join(f"[{n['kind']}, {n['basis']}{', stale' if n['status'] == 'stale' else ''}] {n['text']}" for n in notes)[:2000]
                pid = f'{owner}:{entity}'
                cur = tx.get(tenant, PAGE, pid)
                state = {'page_id': pid, 'owner_id': owner, 'site_id': notes[0]['site_id'], 'entity': entity,
                         'note_ids': [n['note_id'] for n in notes], 'summary': summary, 'updated_at': now,
                         'sources': list({(r['kind'], r['id']): r for n in notes for r in n['sources']}.values())[:30]}
                if not cur or cur.state['summary'] != summary:
                    tx.put(tenant, PAGE, pid, state, expected_revision=cur.revision if cur else None, action='memory_page')
        for entity, text in [(r.state['entity'], r.state['summary']) for r in self.p.store.read().list(tenant, PAGE) if r.state['owner_id'] == owner]:
            self._index(tenant, owner, PAGE, f'{owner}:{entity}', text, None)

    def tick(self, tenants) -> int:
        done = 0
        for tenant in tenants:
            for owner in self.due(tenant):
                self.dream(tenant, owner)
                done += 1
        return done


DREAM_EVERY_MINUTES, DREAM_TURNS, RULE_AFTER_USES = 10, 10, 3
DREAM_SYSTEM = """You consolidate a manufacturing assistant's memory for one person. You get their recent conversations (question, answer, and the records each conversation read) and their existing notes.

Memory is for what the records will not tell next time: validated lessons and how they were established, decisions the person made, their stated preferences, open threads to pick up, and traps or dead ends to avoid. Do not copy record values (the records keep those). Prefer few, durable notes over many.

Return JSON only: {"new_notes": [{"turn_id": "...", "text": "one or two sentences", "kind": "lesson|decision|preference|open_thread|warning", "basis": "observed|calculated|user_stated|inferred", "sources": ["kind:id", ...]}], "corrections": [{"note_id": "...", "action": "stale|superseded", "reason": "..."}]}

Rules: every note except basis user_stated must cite sources from that conversation's records_read. Use basis inferred for interpretations, and say what would confirm them. Retire an existing note (stale or superseded) only when a later conversation shows it no longer holds, and give the reason. Return empty lists when nothing is worth keeping."""
