"""Per-user assistant memory: private to its owner, readable by a colleague (and that colleague's agents) only
under an active grant the owner approved. Grants are read-only, same organization only (records are tenant-scoped),
time-limited and revocable; every check happens on read, so a revocation applies immediately.

What counts as memory (scope):
- conversations: engineering conversations, their turns, the evidence stored from the person's own messages, the
  mission notes copied from them, results and artifacts produced inside those conversations, and investigation runs
  started from them.
- corrections: the person's mission corrections and rejected hypotheses.
- rules: the person's user-scope assistant rules.
Organization knowledge stays shared under normal permissions: site/org rules, cases, verified deliveries, signals.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from .identity import AccessContext
from .ids import iso, new_id, parse_iso, utc_now

GRANT = 'memory_grant'
SCOPES = ('conversations', 'corrections', 'rules')
DEFAULT_DAYS, MAX_DAYS = 30, 90
INSTRUCTION_SOURCE = 'engineering-user-instruction'


class MemoryAccessDenied(PermissionError):
    def __init__(self) -> None:
        super().__init__("This is part of another person's private assistant memory. Ask them to share it with you "
                         "under Settings › Memory & sharing.")


def principal(ctx: AccessContext) -> str:
    """The person whose authority this request carries (an agent acts for the person it is delegated from)."""
    return ctx.delegated_from or ctx.actor_id


def owner_of(store, tenant_id: str, kind: str, state: dict[str, Any]) -> tuple[str, str] | None:
    """(owner, scope) when a record is private memory; None for shared organization data."""
    if kind == 'engineering_conversation':
        return state.get('owner_id', ''), 'conversations'
    if kind == 'engineering_chat_turn':
        return _conversation_owner(store, tenant_id, state.get('conversation_id')), 'conversations'
    if kind == 'mission':
        return state.get('owner_id', ''), 'conversations'
    if kind in ('memory_note', 'memory_page', 'memory_vector', 'memory_state'):  # the assistant's own notes (agent_memory.py)
        return state.get('owner_id', ''), 'conversations'
    if kind == 'assistant_rule':
        return (state.get('owner_id') or '', 'rules') if state.get('scope') == 'user' else None
    if kind == 'evidence' and state.get('source_system') == INSTRUCTION_SOURCE:
        return _conversation_owner(store, tenant_id, (state.get('metadata') or {}).get('conversation_id')), 'conversations'
    if kind in ('investigation_run', 'investigation_proposal', 'investigation_report'):
        return state.get('owner_id', ''), 'conversations'
    if state.get('conversation_id') and kind in ('assistant_workspace_result', 'data_flow_run'):
        return _conversation_owner(store, tenant_id, state.get('conversation_id')), 'conversations'
    return None


def _conversation_owner(store, tenant_id: str, conversation_id: str | None) -> str:
    if not conversation_id:
        return ''  # unattributable private record: nobody but an explicit owner match may read it
    rec = store.read().get(tenant_id, 'engineering_conversation', conversation_id)
    return rec.state.get('owner_id', '') if rec else ''


class MemoryGrants:
    def __init__(self, store, identity) -> None:
        self.store, self.identity = store, identity

    # --- checks ------------------------------------------------------------------------
    def can_read(self, ctx: AccessContext, owner_id: str, scope: str) -> bool:
        me = principal(ctx)
        if owner_id and me == owner_id:
            return True
        if not owner_id:
            return False
        now = utc_now()
        for rec in self.store.read().list(ctx.tenant_id, GRANT):
            g = rec.state
            if (g['owner_id'] == owner_id and g['grantee_id'] == me and g['status'] == 'active'
                    and scope in g['scopes'] and parse_iso(g['expires_at']) > now):
                return True
        return False

    def require_read(self, ctx: AccessContext, owner_id: str, scope: str) -> None:
        if not self.can_read(ctx, owner_id, scope):
            raise MemoryAccessDenied()

    def require_record(self, ctx: AccessContext, kind: str, state: dict[str, Any]) -> None:
        """For generic read paths: raises when the record is someone else's memory without a grant."""
        owned = owner_of(self.store, ctx.tenant_id, kind, state)
        if owned is not None:
            self.require_read(ctx, *owned)

    def memory_owners(self, ctx: AccessContext, kind: str, state: dict[str, Any]) -> list[tuple[str, str]]:
        """(owner, scope) of the record and of its direct inputs: a result derived from someone's message is theirs too."""
        out = [owner_of(self.store, ctx.tenant_id, kind, state)]
        for ref in state.get('inputs') or []:
            rec = self.store.read().get(ctx.tenant_id, ref.get('kind', ''), ref.get('id', ''))
            if rec is not None:
                out.append(owner_of(self.store, ctx.tenant_id, ref['kind'], rec.state))
        return [o for o in out if o is not None]

    def readable(self, ctx: AccessContext, kind: str, state: dict[str, Any]) -> bool:
        return all(self.can_read(ctx, *owned) for owned in self.memory_owners(ctx, kind, state))

    @staticmethod
    def require_owner_write(ctx: AccessContext, owner_id: str) -> None:
        """Grants are read-only: only the owner (or an agent acting for them) writes into their memory."""
        if principal(ctx) != owner_id:
            raise MemoryAccessDenied()

    # --- grant lifecycle ---------------------------------------------------------------
    @staticmethod
    def _person(ctx: AccessContext, what: str) -> None:
        if ctx.actor_kind != 'person' or ctx.delegated_from:
            raise PermissionError(f'{what} needs a person; agents cannot request or approve memory access')

    def request(self, ctx: AccessContext, *, owner_id: str, scopes: list[str], reason: str, days: int = DEFAULT_DAYS) -> dict[str, Any]:
        self._person(ctx, 'requesting access to someone’s memory')
        scopes = sorted(set(scopes))
        if not scopes or any(s not in SCOPES for s in scopes):
            raise ValueError(f'scopes must be some of {SCOPES}')
        if not (reason or '').strip():
            raise ValueError('say why you need access')
        if owner_id == ctx.actor_id:
            raise ValueError('your own memory is already yours')
        if not self.identity.context_for(ctx.tenant_id, owner_id).roles:
            raise PermissionError('that person is not a member of this organization')
        if not 1 <= int(days) <= MAX_DAYS:
            raise ValueError(f'access lasts 1–{MAX_DAYS} days')
        gid = new_id('mgrant')
        state = {'grant_id': gid, 'owner_id': owner_id, 'grantee_id': ctx.actor_id, 'scopes': scopes,
                 'reason': reason.strip()[:1000], 'requested_days': int(days), 'status': 'requested',
                 'requested_at': iso(utc_now()), 'expires_at': None, 'history': []}
        with self.store.transaction(ctx.actor_id) as tx:
            tx.put(ctx.tenant_id, GRANT, gid, state, expected_revision=None, action='request_memory_access',
                   event_type='memory_grant.requested', event_payload={'grant_id': gid, 'owner_id': owner_id})
        return state

    def _decide(self, ctx: AccessContext, grant_id: str, *, by_owner: bool, status: str, from_states: set[str],
                reason: str = '', days: int | None = None) -> dict[str, Any]:
        self._person(ctx, 'changing memory access')
        with self.store.transaction(ctx.actor_id) as tx:
            rec = tx.require(ctx.tenant_id, GRANT, grant_id)
            g = rec.state
            allowed = {g['owner_id']} if by_owner else {g['owner_id'], g['grantee_id']}
            if ctx.actor_id not in allowed:
                raise PermissionError('only the person whose memory this is can decide')
            if g['status'] not in from_states:
                raise ValueError(f"this request is {g['status']}")
            now = utc_now()
            change = {'status': status, 'history': [*g['history'], {'event': status, 'by': ctx.actor_id, 'at': iso(now), 'reason': reason}]}
            if status == 'active':
                length = int(days or g['requested_days'])
                if not 1 <= length <= MAX_DAYS:
                    raise ValueError(f'access lasts 1–{MAX_DAYS} days')
                change['expires_at'] = iso(now + timedelta(days=length))
            out = tx.put(ctx.tenant_id, GRANT, grant_id, {**g, **change}, expected_revision=rec.revision,
                         action=f'memory_grant_{status}', reason=reason or None,
                         event_type=f'memory_grant.{status}', event_payload={'grant_id': grant_id})
        return {**out.state, 'revision': out.revision}

    def approve(self, ctx, grant_id, *, days=None, reason=''):
        return self._decide(ctx, grant_id, by_owner=True, status='active', from_states={'requested'}, days=days, reason=reason)

    def deny(self, ctx, grant_id, *, reason=''):
        return self._decide(ctx, grant_id, by_owner=True, status='denied', from_states={'requested'}, reason=reason)

    def revoke(self, ctx, grant_id, *, reason=''):
        """The owner revokes, or the grantee gives the access back."""
        return self._decide(ctx, grant_id, by_owner=False, status='revoked', from_states={'requested', 'active'}, reason=reason)

    def list_for(self, ctx: AccessContext) -> dict[str, list[dict[str, Any]]]:
        me, now = ctx.actor_id, utc_now()
        mine, theirs = [], []
        for rec in self.store.read().list(ctx.tenant_id, GRANT):
            g = {**rec.state, 'revision': rec.revision}
            if g['status'] == 'active' and parse_iso(g['expires_at']) <= now:
                g['status'] = 'expired'
            if g['owner_id'] == me:
                mine.append(g)
            elif g['grantee_id'] == me:
                theirs.append(g)
        key = lambda g: g['requested_at']
        return {'shared_by_me': sorted(mine, key=key, reverse=True), 'shared_with_me': sorted(theirs, key=key, reverse=True)}
