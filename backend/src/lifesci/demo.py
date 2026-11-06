"""Public demo workspaces: one isolated, synthetic, 24-hour workspace per anonymous visitor (docs/product/demo-workspaces.md).

Wiring: ``platform.demo = DemoService(platform)``; ``demo_routes(app, platform, ctx_dep, visitor_dep)``;
``platform.demo.tick()`` on the runtime tick; ``platform.demo.consume_message(ctx)`` before a demo turn is queued.

Tenants ``demo_<hex>`` hold the visitor's workspace. Two reserved tenants hold platform state the visitor never reads:
``__demo_control__`` (workspace registry, message counters) and ``__demo_corpus__`` (feedback and transcript snapshots,
kept 90 days for improving the assistant). Physical deletion is ``python -m src.lifesci demo-purge`` (schema owner).
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .identity import AccessContext
from .ids import iso, new_id, parse_iso, utc_now
from .store import ConflictError
from . import demo_scenarios

PREFIX, CONTROL, CORPUS = 'demo_', '__demo_control__', '__demo_corpus__'
PERSONA_ROLES = {'process_engineer': 'engineering', 'msat': 'msat', 'qa': 'qa', 'executive': 'supervisor'}
TTL = timedelta(hours=24)
PER_WORKSPACE, GLOBAL_DAILY, CORPUS_DAYS = 20, 300, 90
NOTICE = ("This is a demo with synthetic data. We keep demo conversations and feedback to improve the product. "
          "Don't enter confidential information.")


class DemoExpired(Exception):
    """A request for a demo workspace whose 24 hours are over."""


class DemoLimit(ConflictError):
    """A demo usage cap was reached (per workspace or across all demos today); returned as HTTP 429."""


def is_demo(tenant: str | None) -> bool:
    return bool(tenant) and tenant.startswith(PREFIX)


class WorkspaceIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    persona: Literal['process_engineer', 'msat', 'qa', 'executive']
    accepted_notice: bool


class FeedbackIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['answer', 'scenario', 'overall']
    turn_id: str | None = Field(default=None, max_length=100)
    scenario_id: str | None = Field(default=None, max_length=60)
    rating: Literal['up', 'down', 1, 2, 3, 4, 5] | None = None
    realistic: int | None = Field(default=None, ge=1, le=5)
    useful: int | None = Field(default=None, ge=1, le=5)
    would_use: Literal['yes', 'maybe', 'no'] | None = None
    comment: str | None = Field(default=None, max_length=4000)
    email: str | None = Field(default=None, max_length=254)


class DemoService:
    def __init__(self, platform: Any) -> None:
        self.p = platform

    # --- registry -------------------------------------------------------------------
    def _entry(self, tenant: str) -> dict[str, Any] | None:
        rec = self.p.store.read().get(CONTROL, 'demo_workspace', tenant)
        return {**rec.state, 'revision': rec.revision} if rec else None

    def expired(self, tenant: str) -> bool:
        entry = self._entry(tenant)
        return entry is not None and (entry['status'] != 'active' or parse_iso(entry['expires_at']) <= utc_now())

    def _daily(self) -> tuple[str, int]:
        day = utc_now().date().isoformat()
        rec = self.p.store.read().get(CONTROL, 'demo_daily', day)
        return day, (rec.state['messages'] if rec else 0)

    # --- provisioning ---------------------------------------------------------------
    def provision(self, visitor: str, persona: str, accepted_notice: bool) -> dict[str, Any]:
        if not accepted_notice:
            raise ValueError('Accept the demo notice to continue')
        owner = self.p.store.read().get(CONTROL, 'demo_owner', visitor)
        if owner and not self.expired(owner.state['tenant_id']):
            return self.view(owner.state['tenant_id'])  # one active workspace per visitor
        if self._daily()[1] >= GLOBAL_DAILY:
            raise DemoLimit('The demo is at capacity today. Please try again tomorrow, or talk to us.')
        tenant = PREFIX + uuid.uuid4().hex[:20]
        now = utc_now()
        demo = {'tenant_id': tenant, 'owner': visitor, 'persona': persona, 'created_at': iso(now),
                'expires_at': iso(now + TTL), 'status': 'active', 'messages': 0, 'notice': NOTICE,
                'notice_accepted_at': iso(now), 'snapshotted_turns': []}
        with self.p.store.transaction('demo') as tx:
            tx.put(CONTROL, 'demo_workspace', tenant, demo, expected_revision=None, action='create_demo_workspace')
        with self.p.store.transaction('demo') as tx:
            current = tx.get(CONTROL, 'demo_owner', visitor)
            tx.put(CONTROL, 'demo_owner', visitor, {'tenant_id': tenant}, expected_revision=current.revision if current else None,
                   action='assign_demo_workspace')
        with self.p.store.transaction('demo') as tx:
            tx.put(tenant, 'organization', tenant, {'name': 'Demo workspace (synthetic)', 'created_by': 'demo', 'created_at': iso(now),
                   'onboarding_complete': True, 'demo': {k: demo[k] for k in ('persona', 'created_at', 'expires_at', 'owner')}},
                   expected_revision=None, action='create_demo_organization')
            # Seeding must never start a model call: auto-triage stays paused in demo workspaces.
            from .triage import DEFAULTS, SETTINGS
            from .demo_seed import SITE
            tx.put(tenant, SETTINGS, SITE, {**DEFAULTS, 'paused': True}, expected_revision=None, action='pause_demo_triage')
        self.p.identity.assign_role(tenant, visitor, PERSONA_ROLES[persona], by='demo', reason='demo visitor')
        from .organizations import OrganizationService
        OrganizationService(self.p.store, self.p.identity).remember(visitor, tenant)
        from .demo_seed import seed
        seeded = seed(self.p, tenant, visitor, persona)
        with self.p.store.transaction('demo') as tx:
            rec = tx.require(CONTROL, 'demo_workspace', tenant)
            tx.put(CONTROL, 'demo_workspace', tenant, {**rec.state, 'seed': seeded}, expected_revision=rec.revision,
                   action='record_demo_seed')
        self.p.runtime.track(tenant) if hasattr(self.p, 'runtime') else None
        return self.view(tenant)

    def view(self, tenant: str) -> dict[str, Any]:
        entry = self._entry(tenant)
        if entry is None:
            raise PermissionError('not a demo workspace')
        return {'tenant_id': tenant, 'persona': entry['persona'], 'created_at': entry['created_at'],
                'expires_at': entry['expires_at'], 'status': 'expired' if self.expired(tenant) else 'active',
                'messages_used': entry['messages'], 'messages_left': max(0, PER_WORKSPACE - entry['messages']),
                'message_limit': PER_WORKSPACE, 'notice': entry['notice'],
                'scenarios': demo_scenarios.for_persona(entry['persona']),
                'dataset_id': (entry.get('seed') or {}).get('dataset_id'), 'site_id': (entry.get('seed') or {}).get('site_id')}

    def workspace(self, ctx: AccessContext) -> dict[str, Any]:
        if not is_demo(ctx.tenant_id) or not ctx.roles:
            raise PermissionError('not a demo workspace')
        return self.view(ctx.tenant_id)

    # --- limits ---------------------------------------------------------------------
    def consume_message(self, ctx: AccessContext) -> None:
        """Called before a turn is queued. Over-counts if the queueing then fails (acceptable for a demo cap)."""
        if not is_demo(ctx.tenant_id):
            return
        if self.expired(ctx.tenant_id):
            raise DemoExpired()
        day, used_today = self._daily()
        if used_today >= GLOBAL_DAILY:
            raise DemoLimit('The demo has reached today\'s limit. Please come back tomorrow, or talk to us to keep going.')
        with self.p.store.transaction('demo') as tx:
            rec = tx.require(CONTROL, 'demo_workspace', ctx.tenant_id)
            if rec.state['messages'] >= PER_WORKSPACE:
                raise DemoLimit(f"You've used this demo's {PER_WORKSPACE} messages. Talk to us to keep going.")
            tx.put(CONTROL, 'demo_workspace', ctx.tenant_id, {**rec.state, 'messages': rec.state['messages'] + 1},
                   expected_revision=rec.revision, action='count_demo_message')
        with self.p.store.transaction('demo') as tx:
            rec = tx.get(CONTROL, 'demo_daily', day)
            tx.put(CONTROL, 'demo_daily', day, {'messages': (rec.state['messages'] if rec else 0) + 1},
                   expected_revision=rec.revision if rec else None, action='count_demo_daily')

    # --- feedback and corpus --------------------------------------------------------
    def feedback(self, ctx: AccessContext, body: FeedbackIn) -> dict[str, Any]:
        entry = self._entry(ctx.tenant_id) if is_demo(ctx.tenant_id) else None
        if entry is None or not ctx.roles:
            raise PermissionError('feedback here is for demo workspaces')
        if body.scenario_id and not demo_scenarios.get(body.scenario_id):
            raise ValueError('unknown scenario')
        snapshot = None
        if body.turn_id:
            snapshot = self._turn_snapshot(ctx, body.turn_id)
        state = {**body.model_dump(), 'tenant_id': ctx.tenant_id, 'persona': entry['persona'], 'visitor': ctx.actor_id,
                 'recorded_at': iso(utc_now()), 'turn': snapshot}
        fid = new_id('dfb')
        with self.p.store.transaction('demo') as tx:
            tx.put(CORPUS, 'demo_feedback', fid, state, expected_revision=None, action='record_demo_feedback')
        return {'feedback_id': fid, 'recorded': True}

    def _turn_snapshot(self, ctx: AccessContext, turn_id: str) -> dict[str, Any] | None:
        rec = self.p.store.read().get(ctx.tenant_id, 'engineering_chat_turn', turn_id)
        if rec is None:
            return None
        thread = self.p.engineering_conversations.get(ctx, rec.state['conversation_id'])
        return next((self._turn(t) for t in thread['turns'] if t['id'] == turn_id), None)

    @staticmethod
    def _turn(turn: dict[str, Any]) -> dict[str, Any]:
        keep = ('id', 'user_text', 'status', 'reply', 'questions', 'claims', 'grounding', 'steps', 'issues', 'held_back',
                'capabilities_used', 'context_used', 'elapsed_seconds', 'system_message', 'origin')
        out = {k: turn.get(k) for k in keep}
        out['artifacts'] = [{'kind': a.get('kind'), 'title': a.get('title')} for a in turn.get('artifacts', [])]
        out['gateway_runs'] = [{k: r.get(k) for k in ('run_id', 'status', 'route', 'attempts', 'issues', 'cost_usd')}
                               for r in turn.get('gateway_runs', [])]
        return out

    def snapshot_workspace(self, tenant: str) -> int:
        """Copy completed demo conversations into the corpus (idempotent per turn)."""
        entry = self._entry(tenant)
        if entry is None:
            return 0
        owner = self.p.identity.context_for(tenant, entry['owner'])
        if not owner.roles:
            return 0
        done, fresh = set(entry.get('snapshotted_turns', [])), []
        for rec in self.p.store.read().list(tenant, 'engineering_conversation'):
            thread = self.p.engineering_conversations.get(owner, rec.id)
            turns = [self._turn(t) for t in thread['turns'] if t.get('status') not in ('queued', 'running')]
            new = [t['id'] for t in turns if t['id'] not in done]
            if not new:
                continue
            with self.p.store.transaction('demo') as tx:
                key = f'{tenant}:{rec.id}'
                current = tx.get(CORPUS, 'demo_transcript', key)
                tx.put(CORPUS, 'demo_transcript', key, {'tenant_id': tenant, 'persona': entry['persona'], 'visitor': entry['owner'],
                       'conversation_id': rec.id, 'title': thread.get('title'), 'captured_at': iso(utc_now()), 'turns': turns},
                       expected_revision=current.revision if current else None, action='snapshot_demo_transcript')
            fresh.extend(new)
        if fresh:
            with self.p.store.transaction('demo') as tx:
                rec = tx.require(CONTROL, 'demo_workspace', tenant)
                tx.put(CONTROL, 'demo_workspace', tenant, {**rec.state, 'snapshotted_turns': [*rec.state.get('snapshotted_turns', []), *fresh]},
                       expected_revision=rec.revision, action='record_demo_snapshot')
        return len(fresh)

    # --- runtime --------------------------------------------------------------------
    def tick(self) -> None:
        for rec in self.p.store.read().list(CONTROL, 'demo_workspace', lambda s: s.get('status') == 'active'):
            tenant = rec.id
            self.snapshot_workspace(tenant)
            if parse_iso(rec.state['expires_at']) > utc_now():
                continue
            # Expired: last snapshot is taken above, then the visitor loses access. Rows are deleted by demo-purge.
            self.p.identity.revoke_role(tenant, rec.state['owner'], PERSONA_ROLES[rec.state['persona']], by='demo',
                                        reason='demo workspace expired')
            with self.p.store.transaction('demo') as tx:
                current = tx.require(CONTROL, 'demo_workspace', tenant)
                tx.put(CONTROL, 'demo_workspace', tenant, {**current.state, 'status': 'expired', 'expired_at': iso(utc_now())},
                       expected_revision=current.revision, action='expire_demo_workspace')


def demo_routes(app: Any, platform: Any, ctx_dep: Any, visitor_dep: Any) -> None:
    from fastapi import Depends

    @app.post('/v1/demo/workspaces', status_code=201)
    def create_workspace(body: WorkspaceIn, visitor: str = Depends(visitor_dep)):
        return platform.demo.provision(visitor, body.persona, body.accepted_notice)

    @app.get('/v1/demo/workspace')
    def current_workspace(ctx: AccessContext = Depends(ctx_dep)):
        return platform.demo.workspace(ctx)

    @app.get('/v1/demo/scenarios')
    def scenarios(persona: Literal['process_engineer', 'msat', 'qa', 'executive']):
        return {'persona': persona, 'scenarios': demo_scenarios.for_persona(persona), 'notice': NOTICE}

    @app.post('/v1/demo/feedback', status_code=201)
    def feedback(body: FeedbackIn, ctx: AccessContext = Depends(ctx_dep)):
        return platform.demo.feedback(ctx, body)


# --- physical deletion (schema owner) and export --------------------------------------------------------------
def _registry(rows) -> list[dict]:
    import json
    return [json.loads(r[0]) for r in rows]


def purge(database_url: str, *, now=None) -> dict[str, Any]:
    """Delete every row of expired demo workspaces, and corpus entries older than 90 days.

    Run as the schema owner (append-only triggers are disabled only inside this transaction, and only rows of
    the purged tenant ids are touched). PostgreSQL row-level security applies to the owner too, so each tenant
    is deleted with ``app.tenant_id`` set to it, exactly as the application reads it.
    """
    import json
    now = now or utc_now()
    cutoff = iso(now - timedelta(days=CORPUS_DAYS))
    pg = database_url.startswith(('postgres://', 'postgresql://'))
    if pg:
        import psycopg
        conn = psycopg.connect(database_url, autocommit=False)
        ph = '%s'
    else:
        import sqlite3
        conn = sqlite3.connect(database_url[len('sqlite:///'):] if database_url.startswith('sqlite:///') else database_url,
                               isolation_level=None)
        ph = '?'
    cur = conn.cursor()

    def scope(tenant):  # RLS on PostgreSQL; a no-op for SQLite
        if pg:
            cur.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant,))

    def current(tenant, kind):
        scope(tenant)
        cur.execute(f"SELECT r.state, a.id FROM aggregates a JOIN aggregate_revisions r ON r.tenant_id=a.tenant_id AND r.kind=a.kind "
                    f"AND r.id=a.id AND r.revision=a.revision WHERE a.tenant_id={ph} AND a.kind={ph}", (tenant, kind))
        return [(json.loads(state), rid) for state, rid in cur.fetchall()]

    if pg:
        cur.execute("SELECT table_name FROM information_schema.columns WHERE column_name='tenant_id' AND table_schema=current_schema()")
        tables = sorted({r[0] for r in cur.fetchall()})
    else:
        cur.execute("BEGIN IMMEDIATE")
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = sorted(t for (t,) in cur.fetchall() if any(c[1] == 'tenant_id' for c in conn.execute(f'PRAGMA table_info({t})')))
    # Children before parents (e.g. aggregates -> aggregate_revisions, CMO files -> deliveries).
    if pg:
        cur.execute("SELECT tc.table_name, ccu.table_name FROM information_schema.table_constraints tc "
                    "JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name = tc.constraint_name "
                    "AND ccu.table_schema = tc.table_schema WHERE tc.constraint_type = 'FOREIGN KEY' "
                    "AND tc.table_schema = current_schema()")
        refs = [(child, parent) for child, parent in cur.fetchall() if child != parent]
    else:
        refs = [('aggregates', 'aggregate_revisions')]
    ordered, remaining = [], list(tables)
    while remaining:
        leaves = [t for t in remaining if not any(parent == t and child in remaining for child, parent in refs)]
        leaves = leaves or remaining[:1]  # a cycle would be unusual; fall back to the given order
        ordered += leaves
        remaining = [t for t in remaining if t not in leaves]
    tables = ordered
    triggers = []
    try:
        if pg:
            for t in tables:
                cur.execute(f'ALTER TABLE {t} DISABLE TRIGGER USER')
        else:
            cur.execute(f"SELECT name, sql FROM sqlite_master WHERE type='trigger' AND tbl_name IN ({','.join('?' * len(tables))})", tables)
            triggers = cur.fetchall()
            for name, _ in triggers:
                cur.execute(f'DROP TRIGGER {name}')
        expired = [(s, rid) for s, rid in current(CONTROL, 'demo_workspace') if parse_iso(s['expires_at']) <= now]
        for state, tenant in expired:
            if not tenant.startswith('demo_'):
                continue  # defence in depth: a malformed control record must never delete a real organization
            scope(tenant)
            for t in tables:
                cur.execute(f'DELETE FROM {t} WHERE tenant_id={ph}', (tenant,))
            scope(CONTROL)
            for kind, ident in (('demo_workspace', tenant), ('demo_owner', state['owner'])):
                for t in ('aggregates', 'aggregate_revisions'):
                    cur.execute(f'DELETE FROM {t} WHERE tenant_id={ph} AND kind={ph} AND id={ph}', (CONTROL, kind, ident))
                cur.execute(f'DELETE FROM audit WHERE tenant_id={ph} AND aggregate_kind={ph} AND aggregate_id={ph}', (CONTROL, kind, ident))
        old = [(kind, rid) for kind, field in (('demo_feedback', 'recorded_at'), ('demo_transcript', 'captured_at'))
               for s, rid in current(CORPUS, kind) if (s.get(field) or '') < cutoff]
        scope(CORPUS)
        for kind, rid in old:
            for t in ('aggregates', 'aggregate_revisions'):
                cur.execute(f'DELETE FROM {t} WHERE tenant_id={ph} AND kind={ph} AND id={ph}', (CORPUS, kind, rid))
            cur.execute(f'DELETE FROM audit WHERE tenant_id={ph} AND aggregate_kind={ph} AND aggregate_id={ph}', (CORPUS, kind, rid))
        if pg:
            for t in tables:
                cur.execute(f'ALTER TABLE {t} ENABLE TRIGGER USER')
        else:
            for _, sql in triggers:
                cur.execute(sql)
        conn.commit() if pg else cur.execute('COMMIT')
    except BaseException:
        conn.rollback() if pg else cur.execute('ROLLBACK')
        raise
    finally:
        conn.close()
    return {'purged_workspaces': [t for _, t in expired], 'purged_corpus_items': len(old)}


def export_corpus(store: Any, since: str | None = None):
    """Yield corpus items (feedback and transcripts) for harness evaluation, oldest first."""
    items = []
    for kind, field in (('demo_feedback', 'recorded_at'), ('demo_transcript', 'captured_at')):
        for rec in store.read().list(CORPUS, kind):
            if since is None or (rec.state.get(field) or '') >= since:
                items.append({'kind': kind, 'id': rec.id, **rec.state})
    yield from sorted(items, key=lambda i: i.get('recorded_at') or i.get('captured_at') or '')
