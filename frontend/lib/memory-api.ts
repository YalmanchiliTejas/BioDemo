import { processRequest } from './process-api';

export type MemoryScope = 'conversations' | 'corrections' | 'rules';
export type GrantStatus = 'requested' | 'active' | 'denied' | 'revoked' | 'expired';
export type Grant = {
  grant_id: string; owner_id: string; grantee_id: string; owner_email?: string | null; grantee_email?: string | null;
  scopes: MemoryScope[]; reason: string; status: GrantStatus; requested_at: string; expires_at?: string | null;
  requested_days: number; history?: { event: string; by: string; at: string; reason?: string }[];
};
export type Grants = { shared_by_me: Grant[]; shared_with_me: Grant[] };

export const SCOPE_LABEL: Record<MemoryScope, string> = {
  conversations: 'Conversations and messages', corrections: 'Corrections', rules: 'Personal rules',
};

export const listGrants = () => processRequest<Grants>('/v1/memory-grants');
export const requestAccess = (body: { owner_email: string; scopes: MemoryScope[]; reason: string; days: number }) =>
  processRequest<Grant>('/v1/memory-grants', body);
export const approveGrant = (id: string, days?: number) => processRequest<Grant>(`/v1/memory-grants/${encodeURIComponent(id)}/approve`, { days });
export const denyGrant = (id: string, reason = '') => processRequest<Grant>(`/v1/memory-grants/${encodeURIComponent(id)}/deny`, { reason });
export const revokeGrant = (id: string, reason = '') => processRequest<Grant>(`/v1/memory-grants/${encodeURIComponent(id)}/revoke`, { reason });

const owner = (id: string) => `/v1/memory/${encodeURIComponent(id)}`;
export const sharedConversations = (ownerId: string) =>
  processRequest<{ conversations: { id: string; title: string; updated_at?: string }[] }>(`${owner(ownerId)}/conversations`);
export const sharedConversation = (ownerId: string, id: string) =>
  processRequest<{ id: string; title: string; turns: { id: string; user_text: string; reply: string | null; status?: string; created_at?: string }[] }>(
    `${owner(ownerId)}/conversations/${encodeURIComponent(id)}`);
export const sharedCorrections = (ownerId: string) =>
  processRequest<{ corrections: { correction_id: string; text: string; at?: string }[] }>(`${owner(ownerId)}/corrections`);
export const sharedRules = (ownerId: string) =>
  processRequest<{ rules: { rule_id: string; text: string; status?: string }[] }>(`${owner(ownerId)}/rules`);

export const formatDate = (iso?: string | null) => {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
};
