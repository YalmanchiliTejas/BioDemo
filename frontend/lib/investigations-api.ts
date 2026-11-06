/** Multi-agent investigation runs (docs/architecture/multi-agent-investigations.md §12.3). */
import { authHeaders, authMode, redirectToSignIn, SIGNED_OUT_MESSAGE } from './auth';
import { PROCESS_API } from './process-api';

export type RunStatus = 'queued' | 'submitted' | 'running' | 'finalizing' | 'awaiting_review' | 'blocked' | 'failed' | 'cancelled';
export type AgentStatus = 'running' | 'waiting' | 'done' | 'failed';
export type Subreport = { subreport_id: string; assessment?: string; fact_count?: number; claim_count?: number; open_question_count?: number; evidence_ids?: string[] };
export type Agent = { agent_id: string; parent_id: string | null; role: 'lead' | 'investigator'; question?: string | null; status: AgentStatus;
  current_tool?: string | null; tool_calls?: number; tokens?: number; started_at?: string | null; last_activity_at?: string | null;
  subreports: Subreport[]; attribution: 'exact' | 'approximate' };
export type Budget = { tool_calls_used: number; tool_calls_limit: number; elapsed_seconds: number; deadline_seconds: number;
  tokens?: number | null; token_limit?: number | null; cost_status?: string };
export type Run = { run_id: string; status: RunStatus; objective: string; site_id: string; case_id?: string | null; conversation_id?: string | null;
  owner_id?: string; created_at?: string; as_of?: string | null;
  evidence_snapshot?: { sha256?: string; taken_at?: string; items?: { kind?: string; id: string; label?: string }[] } | null;
  agents: Agent[]; budget: Budget; sync?: { updated_at?: string | null; reachable?: boolean; lag_seconds?: number | null };
  issues?: string[]; report_ref?: string | null; basis_status?: string };
export type RunEvent = { seq: number; at: string; kind: string; agent_id: string | null; parent_id: string | null; payload: Record<string, unknown> };
export type Report = { run_id: string; review_status: string; report: { summary?: string; assessment?: string; findings?: { text?: string; title?: string; kind?: string; status?: string; evidence_ids?: string[] }[];
  hypotheses?: { text?: string; title?: string; status?: string }[]; open_questions?: string[]; [key: string]: unknown } };

export class InvestigationError extends Error {
  constructor(message: string, public status: number) { super(message); }
}

async function call<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${PROCESS_API}${path}`, {
    method: body !== undefined ? 'POST' : 'GET',
    headers: { 'Content-Type': 'application/json', ...(await authHeaders()), ...(body !== undefined ? { 'Idempotency-Key': crypto.randomUUID() } : {}) },
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
  });
  if (response.status === 401 && authMode() === 'supabase') { redirectToSignIn(); throw new InvestigationError(SIGNED_OUT_MESSAGE, 401); }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new InvestigationError(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail ?? data), response.status);
  return data as T;
}

export const startRun = (body: { proposal_id?: string; objective: string; site_id: string; conversation_id?: string; case_id?: string | null }) =>
  call<Run>('/v1/investigation-runs', body);
export const getRun = (id: string) => call<Run>(`/v1/investigation-runs/${encodeURIComponent(id)}`);
export const listRuns = (q: { case_id?: string; conversation_id?: string }) =>
  call<{ runs: Run[] }>(`/v1/investigation-runs?${new URLSearchParams(Object.entries(q).filter(([, v]) => v) as [string, string][])}`);
export const runEvents = (id: string, after = 0) => call<{ events: RunEvent[]; next: number }>(`/v1/investigation-runs/${encodeURIComponent(id)}/events?after=${after}`);
export const stopRun = (id: string) => call<Run>(`/v1/investigation-runs/${encodeURIComponent(id)}/stop`, {});
export const sendForReview = (id: string) => call<{ run_id: string; package_id: string; claims: string[] }>(`/v1/investigation-runs/${encodeURIComponent(id)}/send-for-review`, {});
export const runReport = (id: string) => call<Report>(`/v1/investigation-runs/${encodeURIComponent(id)}/report`);

export const ACTIVE: RunStatus[] = ['queued', 'submitted', 'running', 'finalizing'];
export const isActive = (s: RunStatus) => ACTIVE.includes(s);
export const notEntitled = (e: unknown) => e instanceof InvestigationError && e.status === 409 && /paid plan/i.test(e.message);
export const notConfigured = (e: unknown) => e instanceof InvestigationError && e.status === 409 && /not configured/i.test(e.message);

export const STATUS_LABEL: Record<RunStatus, string> = {
  queued: 'queued', submitted: 'starting', running: 'running', finalizing: 'writing the report', awaiting_review: 'ready for review',
  blocked: 'stopped before a report', failed: 'failed', cancelled: 'stopped',
};

export function ago(iso?: string | null, now = Date.now()) {
  if (!iso) return null;
  const s = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  return s < 60 ? `${s}s` : `${Math.round(s / 60)} min`;
}
export const minutes = (seconds?: number) => seconds == null ? '–' : `${Math.max(0, Math.round(seconds / 60))}`;
