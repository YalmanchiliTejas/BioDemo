"""Account endpoints authenticate before organization membership exists."""
from typing import Literal
from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from .organizations import OrganizationService
from .supabase_auth import lookup_user_id_by_email


class OrganizationIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=2, max_length=120)


class MemberIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    email: str | None = Field(default=None, max_length=254)
    actor_id: str | None = Field(default=None, max_length=128)
    role: str
    site_id: str | None = None
    operation: Literal['grant', 'revoke'] = 'grant'


class DevSessionIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=200)


def install_organization_api(app, platform, resolver, ctx_dep, multi_tenant, development=False):
    import os
    service = OrganizationService(platform.store, platform.identity, os.environ.get('DEPLOYMENT_TENANT', ''))
    verifier = getattr(resolver, 'verifier', None)
    if verifier is None and not development:
        return  # no account provisioning through an unrelated IdP
    lookup = None  # Supabase lookup, resolved per request
    if development:
        account_actor, lookup = _install_local_accounts(app, platform, service)
    else:
        def account_actor(request: Request):
            claims = verifier.verify(request.headers.get('authorization'))
            if not claims.get('email') or claims.get('is_anonymous') is True:
                raise HTTPException(403, 'A verified account is required')
            request.state.account_email = claims['email']
            return claims['sub']

    @app.get('/v1/account')
    def account(actor=Depends(account_actor)):
        return {'actor_id': actor, 'organizations': service.organizations(actor), 'can_create_organization': multi_tenant}

    @app.post('/v1/account/organizations', status_code=201)
    def create(body: OrganizationIn, request: Request, actor=Depends(account_actor)):
        if not multi_tenant:
            raise HTTPException(403, 'Self-service organizations are not enabled for this deployment')
        return service.create(actor, body.name, request.state.account_email)

    @app.get('/v1/organization/members')
    def members(ctx=Depends(ctx_dep)):
        return {'items': service.members(ctx)}

    @app.post('/v1/organization/members')
    def change_member(body: MemberIn, ctx=Depends(ctx_dep)):
        service.require_admin(ctx)
        if body.operation == 'grant':
            if not body.email or body.actor_id:
                raise HTTPException(400, 'Grant access using the existing account email')
            try:
                actor = (lookup or lookup_user_id_by_email)(body.email)
            except LookupError:
                raise HTTPException(400, 'This person must create an account before access can be granted')
        else:
            if not body.actor_id or body.email:
                raise HTTPException(400, 'Revoke access using the member identifier')
            actor = body.actor_id
        service.change_role(ctx, actor, body.role, body.site_id, body.operation == 'revoke', email=body.email)
        return {'status': 'updated'}

    @app.post('/v1/organization/onboarding/complete')
    def complete(ctx=Depends(ctx_dep)):
        service.complete_onboarding(ctx)
        return {'status': 'complete'}


def _install_local_accounts(app, platform, service):
    """Development-header mode: sign in with a local test account instead of Supabase."""
    from . import devaccounts

    @app.get('/v1/dev/accounts')
    def local_accounts():
        return {'accounts': devaccounts.listing(), 'password_env': 'LIFESCI_DEV_PASSWORD',
                'default_password': devaccounts.password() == devaccounts.DEFAULT_PASSWORD}

    @app.post('/v1/dev/session')
    def local_session(body: DevSessionIn):
        account = devaccounts.authenticate(body.email, body.password)
        if account is None:
            raise HTTPException(401, 'Email or password is incorrect.')
        devaccounts.ensure_seeded(platform, service)
        return devaccounts.session(account)

    def account_actor(request: Request):
        actor = request.headers.get('x-actor-id')
        if not actor or not request.headers.get('x-tenant-id'):
            raise HTTPException(401, 'Sign in with a local test account')
        return actor

    def lookup(email: str) -> str:
        account = devaccounts.by_email(email)
        if account is None:
            raise LookupError(email)
        return account.actor_id

    return account_actor, lookup
