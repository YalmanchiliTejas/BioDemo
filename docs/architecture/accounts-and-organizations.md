# Accounts, organizations and access

The job is to let a new person register, establish or join an organization, complete data setup, and return to authorized work without granting access to another organization's records.

The implementation extends Supabase Auth and the existing versioned store and role policy. It preserves existing `DEPLOYMENT_TENANT` assignments. An invitation-only, single-tenant deployment remains available with `LIFESCI_MULTI_TENANT=0`; self-service organization creation uses `1`. Separate databases per organization would offer stronger infrastructure isolation but add provisioning and migration effort. This implementation uses the existing PostgreSQL tenant RLS, explicit tenant predicates and server-checked role assignments.

## Account flow

1. `/sign-in/` links to `/sign-up/`. Supabase manages passwords and email confirmation.
2. After authentication, `/account/` discovers organizations from a private directory and live role assignments.
3. A person can create one organization and join multiple organizations. Creation grants organization administration, which does not include quality approval or production execution.
4. New organization administrators go to `/onboarding/start/`. They can configure a source or explicitly continue without a source; completion is stored.
5. Returning members select an organization. Requests carry `X-Organization-Id`, which is only a selection hint: the server verifies a live membership before resolving tenant context. A full navigation on switching drops mounted workspace state.
6. Organization administrators manage existing registered users at `/settings/organization/`. Granting access does not send an invitation email. The person registers first, then an administrator grants a specific role and optional site scope. Removing the final administrator is refused.

Tokens establish identity, not roles. User-editable profile metadata and development identity headers cannot grant organization access. Revoked assignments are checked on subsequent requests. The private membership directory is a discovery projection, not an authorization source. Provisioning can be retried after an interrupted directory write; deterministic organization identifiers prevent duplicate organizations.

## Four pillars and trade-offs

- **Start:** registration, organization creation and resumable source setup require no infrastructure migration. Confirming email adds a necessary identity check.
- **Trust:** tenant membership, site-aware role checks and versioned administrative changes are enforced by the API. Authentication failures and missing configuration remain visible.
- **Act:** administrators can grant/revoke access; new organizations can proceed to source setup. Regulated approvals remain distinct from administrative access.
- **Adopt:** existing tenants, Supabase identity, RLS and systems of record remain in place. A shared database requires careful application and RLS testing; this is not a claim of compliance or completed production validation.

The current delivery-verification records have no site attribute. Site-restricted accounts are therefore refused access to that organization-wide delivery workspace. Other resource-aware services retain site-scoped permissions. Deliveries require `read`/`propose`, exports require `export`, and source review/issue decisions require `approve`; audit actors come from the authenticated identity. Administrative membership alone does not authorize those review decisions.

Observable checks: no demo identity headers in an unconfigured production build; no workspace API calls before authenticated membership is established; deterministic retry of organization creation; onboarding completion survives login; cross-organization selection and site-role mixing are denied; revocation changes the next request's permissions. Automated checks cover these backend boundaries; real email delivery and production infrastructure readiness must be checked separately.

## Lambda connection lifecycle

Production continues to use the Supabase session pooler because existing reads bind tenant context in session state. Changing only to transaction-mode port 6543 would invalidate that assumption. PostgreSQL sessions open lazily, close after every Lambda invocation (including errors), and reconnect on the next invocation. Boot failures also release any opened session. The SAM template caps concurrency at 5, leaving space within the observed 15-session pool for delivery transactions and administration. This limits throughput; tune only with measured headroom across all clients of that pool. Existing frozen containers may retain their old sessions until replaced.

Tenant binding and reads on the shared store connection are serialized. Reused read handles rebind their tenant on every operation. Write transactions cannot switch tenants through a read handle. The directory supports scheduled discovery so cold runtime workers see organizations created by other instances.
