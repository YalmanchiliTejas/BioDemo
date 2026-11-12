import { connectorRequest } from './connectors-api';
export type Organization = { id: string; name: string; roles: string[]; site_ids: string[]; onboarding_complete: boolean };
export type Account = { actor_id: string; organizations: Organization[]; can_create_organization: boolean };
export type Member = { email?: string | null; actor_id: string; role: string; site_id: string | null };
export const getAccount = () => connectorRequest<Account>('/account');
/** The default is the landing page (LANDING in auth.ts), written out so this module stays import-free for the auth check. */
export const organizationDestination = (org: Organization, next = '/trends/') => !org.onboarding_complete && org.roles.includes('admin') ? '/onboarding/start/' : next;
