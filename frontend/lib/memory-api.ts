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

// The assistant's own memory (backend/src/lifesci/agent_memory.py): notes with sources, entity pages, consolidation.
export type NoteKind = 'lesson' | 'decision' | 'preference' | 'open_thread' | 'warning';
export type NoteBasis = 'observed' | 'calculated' | 'user_stated' | 'inferred';
export type MemoryNote = {
  id: string; text: string; kind: NoteKind; basis: NoteBasis; origin: 'assistant' | 'dreaming';
  status: 'active' | 'stale' | 'superseded' | 'forgotten' | 'wrong'; stale_because: string[];
  sources: { kind: string; id: string; revision?: number }[]; entities: string[]; site_id: string;
  conversation_id: string; created_at: string; updated_at: string;
};
export type MemoryPage = { page_id: string; entity: string; note_ids: string[]; summary: string; updated_at: string };
export type AssistantMemory = {
  notes: MemoryNote[]; pages: MemoryPage[]; index: { id: string }[]; last_consolidated_at: string | null;
  last_report: Record<string, number | string> | null; rule_suggestions: { note_id: string; text: string }[]; semantic_search: boolean;
};
export const NOTE_KIND_LABEL: Record<NoteKind, string> = {
  lesson: 'Lesson', decision: 'Decision', preference: 'Preference', open_thread: 'Open thread', warning: 'Warning' };
export const BASIS_LABEL: Record<NoteBasis, string> = {
  observed: 'seen in records', calculated: 'calculated', user_stated: 'you said', inferred: 'the assistant’s interpretation' };
export const assistantMemory = () => processRequest<AssistantMemory>('/v1/assistant-memory');
export const setNoteStatus = (id: string, status: 'forgotten' | 'wrong' | 'active', reason = '') =>
  processRequest<MemoryNote>(`/v1/assistant-memory/notes/${encodeURIComponent(id)}/status`, { status, reason });
export const consolidateMemory = () => processRequest<Record<string, number>>('/v1/assistant-memory/consolidate', {});
export const proposeSiteRule = (text: string, siteId: string) =>
  processRequest<unknown>('/v1/assistant-rules', { scope: 'site', text, site_id: siteId, reason: 'Suggested from assistant memory' });
