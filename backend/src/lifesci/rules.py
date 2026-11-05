"""Standing rules the assistant must follow, kept outside any one conversation or mission.

A rule is proposed by anyone (including the assistant), and becomes active only by a
person with authority for its scope: the user themselves for a user rule, an
``approve`` holder for a site or organisation rule. Active rules are always given to
the assistant in full, never retrieved by similarity, so a rule cannot be silently missed.
"""
from __future__ import annotations

from typing import Any

from .identity import AccessContext, AuthorizationError, Decision, IdentityService
from .ids import iso, new_id, utc_now
from .store import RecordStore

KIND = 'assistant_rule'
SCOPES = ('user', 'site', 'org')
# ponytail: every active rule is injected; past ~200 rules select by scope/topic instead of loading all.
MAX_ACTIVE = 200


class RuleService:
    def __init__(self, store: RecordStore, identity: IdentityService) -> None:
        self.store = store
        self.identity = identity

    def propose(self, ctx: AccessContext, *, scope: str, text: str, site_id: str | None = None,
                owner_id: str | None = None, reason: str = '') -> dict[str, Any]:
        text = (text or '').strip()
        if scope not in SCOPES:
            raise ValueError(f'scope must be one of {SCOPES}')
        if not text or len(text) > 2000:
            raise ValueError('rule text must be 1-2000 characters')
        if scope == 'site' and not site_id:
            raise ValueError('a site rule needs site_id')
        owner = owner_id or ctx.delegated_from or ctx.actor_id
        if scope == 'user' and owner != (ctx.delegated_from or ctx.actor_id):
            raise PermissionError('a user rule can only be proposed for yourself')
        self.identity.require(ctx, 'propose', 'mission', site_id=site_id)
        rule_id = new_id('rule')
        state = {'rule_id': rule_id, 'scope': scope, 'site_id': site_id if scope == 'site' else None,
                 'owner_id': owner if scope == 'user' else None, 'text': text, 'status': 'proposed',
                 'proposed_by': ctx.actor_id, 'proposed_by_kind': ctx.actor_kind, 'created_at': iso(utc_now()),
                 'history': [{'event': 'proposed', 'by': ctx.actor_id, 'at': iso(utc_now()), 'reason': reason}]}
        with self.store.transaction(ctx.actor_id) as tx:
            rec = tx.put(ctx.tenant_id, KIND, rule_id, state, expected_revision=None, action='propose_rule')
        return {**rec.state, 'revision': rec.revision}

    def _authority(self, ctx: AccessContext, rule: dict[str, Any]) -> None:
        if ctx.actor_kind != 'person' or ctx.delegated_from:
            raise AuthorizationError(Decision(False, 'activating or retiring a rule requires the person, not an agent'))
        if rule['scope'] == 'user':
            if rule['owner_id'] != ctx.actor_id:
                raise PermissionError('only the user a rule applies to can activate or retire it')
            return
        if rule['scope'] == 'org' and ctx.site_ids:
            raise PermissionError('an organisation rule needs tenant-wide approve authority')
        self.identity.require(ctx, 'approve', KIND, rule['rule_id'], site_id=rule.get('site_id'))

    def _decide(self, ctx: AccessContext, rule_id: str, status: str, reason: str, expected: set[str]) -> dict[str, Any]:
        if not (reason or '').strip():
            raise ValueError('a reason is required')
        with self.store.transaction(ctx.actor_id) as tx:
            rec = tx.require(ctx.tenant_id, KIND, rule_id)
            self._authority(ctx, rec.state)
            if rec.state['status'] not in expected:
                raise ValueError(f"rule is {rec.state['status']}")
            now = iso(utc_now())
            state = {**rec.state, 'status': status, f'{status}_by': ctx.actor_id, f'{status}_at': now,
                     'history': [*rec.state['history'], {'event': status, 'by': ctx.actor_id, 'at': now, 'reason': reason}]}
            out = tx.put(ctx.tenant_id, KIND, rule_id, state, expected_revision=rec.revision, action=f'{status}_rule', reason=reason)
        return {**out.state, 'revision': out.revision}

    def activate(self, ctx: AccessContext, rule_id: str, reason: str) -> dict[str, Any]:
        return self._decide(ctx, rule_id, 'active', reason, {'proposed'})

    def retire(self, ctx: AccessContext, rule_id: str, reason: str) -> dict[str, Any]:
        return self._decide(ctx, rule_id, 'retired', reason, {'proposed', 'active'})

    def visible(self, ctx: AccessContext, *, site_id: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        """Rules this person may see: their own user rules, their sites' rules and organisation rules."""
        me = ctx.delegated_from or ctx.actor_id
        out = []
        for rec in self.store.read().list(ctx.tenant_id, KIND):
            r = rec.state
            if r['scope'] == 'user' and r['owner_id'] != me:
                continue
            if r['scope'] == 'site' and ((site_id and r['site_id'] != site_id) or
                                         not self.identity.check(ctx, 'read', KIND, rec.id, site_id=r['site_id'])):
                continue
            if status and r['status'] != status:
                continue
            out.append({**r, 'revision': rec.revision})
        out.sort(key=lambda r: (SCOPES.index(r['scope']), r['created_at']))
        return out

    def applicable(self, ctx: AccessContext, *, site_id: str) -> list[dict[str, Any]]:
        """Active rules for this owner at this site, in full, for injection into the assistant's context."""
        rules = self.visible(ctx, site_id=site_id, status='active')
        return [{k: r[k] for k in ('rule_id', 'scope', 'text', 'revision')} for r in rules[:MAX_ACTIVE]]
