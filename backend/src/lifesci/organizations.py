"""Organization provisioning and membership discovery; role assignments remain authoritative.

The private directory is a projection for discovering a person's organizations.
Every access rechecks live roles in the destination tenant. It never grants access.
"""
from __future__ import annotations
import uuid
from typing import Any
from .identity import AccessContext, IdentityService
from .ids import iso, utc_now
from .store import RecordStore

DIRECTORY = '__identity_directory__'
HUMAN_ROLES = frozenset({'admin', 'operator', 'supervisor', 'qa', 'qa_reviewer', 'msat',
                         'engineering', 'maintenance', 'supply_chain', 'manufacturing_systems', 'quality_systems'})


class OrganizationService:
    def __init__(self, store: RecordStore, identity: IdentityService, legacy_tenant: str = ''):
        self.store, self.identity, self.legacy_tenant = store, identity, legacy_tenant

    def remember(self, actor: str, tenant: str) -> None:
        with self.store.transaction(actor) as tx:
            rec = tx.get(DIRECTORY, 'account_organizations', actor)
            ids = list(rec.state['tenant_ids']) if rec else []
            if tenant in ids:
                return
            tx.put(DIRECTORY, 'account_organizations', actor, {'tenant_ids': [*ids, tenant]},
                   expected_revision=rec.revision if rec else None, action='index_membership')

    def organizations(self, actor: str) -> list[dict[str, Any]]:
        rec = self.store.read().get(DIRECTORY, 'account_organizations', actor)
        ids = list(rec.state['tenant_ids']) if rec else []
        if self.legacy_tenant and self.legacy_tenant not in ids:
            ids.append(self.legacy_tenant)
        out = []
        for tenant in ids:
            ctx = self.identity.context_for(tenant, actor)
            if not ctx.roles:
                continue
            org = self.store.read().get(tenant, 'organization', tenant)
            out.append({'id': tenant, 'name': org.state['name'] if org else tenant,
                        'roles': sorted(ctx.roles), 'site_ids': sorted(ctx.site_ids),
                        'onboarding_complete': org.state.get('onboarding_complete', False) if org else True})
        return out

    def create(self, actor: str, name: str, email: str | None = None) -> dict[str, Any]:
        name = name.strip()
        if not 2 <= len(name) <= 120:
            raise ValueError('Organization name must contain 2–120 characters')
        # One self-created organization per person: retryable even after a directory failure.
        tenant = 'org_' + uuid.uuid5(uuid.NAMESPACE_URL, 'sievance:organization:' + actor).hex
        with self.store.transaction(actor) as tx:
            current = tx.get(tenant, 'organization', tenant)
            if current is None:
                tx.put(tenant, 'organization', tenant,
                       {'name': name, 'created_by': actor, 'created_at': iso(utc_now()), 'onboarding_complete': False},
                       expected_revision=None, action='create_organization')
                self.identity.assign_role(tenant, actor, 'admin', by=actor, reason='Created organization')
                if email:
                    tx.put(tenant, 'organization_member', actor, {'email': email.strip().lower()},
                           expected_revision=None, action='record_member')
            elif current.state['created_by'] != actor:
                raise PermissionError('Organization already exists')
            elif 'admin' not in self.identity.context_for(tenant, actor).roles:
                # Re-provisioning must never restore a revoked administrator.
                raise PermissionError('Organization access has been revoked')
        self.remember(actor, tenant)
        with self.store.transaction(actor) as tx:
            if tx.get(DIRECTORY, 'organization_index', tenant) is None:
                tx.put(DIRECTORY, 'organization_index', tenant, {'tenant_id': tenant},
                       expected_revision=None, action='index_organization')
        return next(o for o in self.organizations(actor) if o['id'] == tenant)

    @staticmethod
    def require_admin(ctx: AccessContext) -> None:
        if ctx.actor_kind != 'person' or 'admin' not in ctx.roles or ctx.site_ids:
            raise PermissionError('An organization-wide administrator is required')

    def members(self, ctx: AccessContext) -> list[dict[str, Any]]:
        self.require_admin(ctx)
        profiles = {r.id: r.state for r in self.store.read().list(ctx.tenant_id, 'organization_member')}
        return [{**r.state, 'email': profiles.get(r.state['actor_id'], {}).get('email')}
                for r in self.store.read().list(ctx.tenant_id, 'role_assignment') if not r.state.get('revoked_at')]

    def change_role(self, ctx: AccessContext, actor: str, role: str, site: str | None, revoke: bool, email: str | None = None) -> None:
        self.require_admin(ctx)
        if role not in HUMAN_ROLES:
            raise ValueError('Select a human organization role')
        if site is not None and (not site.strip() or len(site) > 80):
            raise ValueError('Invalid site identifier')
        if role == 'admin' and site is not None:
            raise ValueError('Organization administrators must have organization-wide scope')
        with self.store.transaction(ctx.actor_id) as tx:
            if self.store.backend == 'postgresql':
                tx._db.execute("SELECT pg_advisory_xact_lock(hashtext(?), hashtext(?))",
                               (ctx.tenant_id, 'organization_roles'))
            # Recheck authorization within the same transaction as the change.
            self.require_admin(self.identity.context_for(ctx.tenant_id, ctx.actor_id))
            if revoke and role == 'admin':
                admins = [r for r in tx.list(ctx.tenant_id, 'role_assignment')
                          if r.state['role'] == 'admin' and not r.state.get('revoked_at')
                          and r.state.get('site_id') is None and r.state['actor_id'] != actor]
                if not admins:
                    raise ValueError('Keep at least one organization administrator')
            if revoke:
                self.identity.revoke_role(ctx.tenant_id, actor, role, site_id=site, by=ctx.actor_id,
                                          reason='Organization administrator removed access')
            else:
                self.identity.assign_role(ctx.tenant_id, actor, role, site_id=site, by=ctx.actor_id,
                                          reason='Organization administrator granted access')
                if email:
                    profile = tx.get(ctx.tenant_id, 'organization_member', actor)
                    tx.put(ctx.tenant_id, 'organization_member', actor, {'email': email.strip().lower()},
                           expected_revision=profile.revision if profile else None, action='record_member')
        if not revoke:
            self.remember(actor, ctx.tenant_id)

    def complete_onboarding(self, ctx: AccessContext) -> None:
        self.require_admin(ctx)
        with self.store.transaction(ctx.actor_id) as tx:
            rec = tx.get(ctx.tenant_id, 'organization', ctx.tenant_id)
            if rec and not rec.state.get('onboarding_complete'):
                tx.put(ctx.tenant_id, 'organization', rec.id, {**rec.state, 'onboarding_complete': True},
                       expected_revision=rec.revision, action='complete_onboarding')
