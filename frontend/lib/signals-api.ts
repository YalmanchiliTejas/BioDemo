import type { Tone } from '@/components/ui';
import { processRequest } from '@/lib/process-api';

/** Deviation signals: detections from data, not deviations. A person decides whether a case is opened. */
export type Severity = 'warning' | 'action' | 'critical';
export type SignalStatus = 'open' | 'acknowledged' | 'case_opened' | 'dismissed';
export type Triage = { status: 'pending' | 'running' | 'ready' | 'skipped' | 'failed'; reason?: string | null; conversation_id?: string | null; turn_id?: string | null };
export type Signal = {
  signal_id: string; site_id: string;
  kind: 'step_exception' | 'lab_oos' | 'spec_excursion' | 'trend' | 'qms_deviation' | 'delivery_excursion' | string;
  severity: Severity; rule: string; parameter?: string | null; value?: number | string | null; unit?: string | null;
  limit?: { low?: number | null; high?: number | null; critical_low?: number | null; critical_high?: number | null } | null;
  spec_ref?: { spec_id: string; version: number | string } | null;
  subject?: { kind: string; id: string } | null;
  evidence_refs?: { kind: string; id: string; revision?: number }[];
  source?: { system: string; record_id: string } | null;
  occurrences?: number; first_at?: string; last_at?: string; status: SignalStatus;
  dismiss_reason?: string | null; case_id?: string | null;
  alerts?: { sent: number; last_at?: string | null } | null; triage?: Triage | null; revision?: number;
};

export const SEVERITY_TONE: Record<Severity, Tone> = { warning: 'warning', action: 'critical', critical: 'critical' };
export const SEVERITY_RANK: Record<Severity, number> = { warning: 1, action: 2, critical: 3 };
export const KIND_LABEL: Record<string, string> = {
  step_exception: 'Step out of limit', lab_oos: 'Lab result out of specification', spec_excursion: 'Outside specification',
  trend: 'Early-warning trend', qms_deviation: 'Deviation recorded in QMS', delivery_excursion: 'CMO value outside specification',
};

export function listSignals(q: { site_id?: string; status?: string; min_severity?: string } = {}) {
  const params = new URLSearchParams(Object.entries(q).filter(([, v]) => v) as [string, string][]);
  return processRequest<{ signals: Signal[] }>(`/v1/signals${params.toString() ? `?${params}` : ''}`);
}
export const getSignal = (id: string) => processRequest<Signal>(`/v1/signals/${encodeURIComponent(id)}`);
export const acknowledgeSignal = (id: string) => processRequest<Signal>(`/v1/signals/${encodeURIComponent(id)}/acknowledge`, {});
export const dismissSignal = (id: string, reason: string) => processRequest<Signal>(`/v1/signals/${encodeURIComponent(id)}/dismiss`, { reason });
export const openCaseFromSignal = (id: string, owner_id: string, qa_reviewer_id: string) =>
  processRequest<Signal>(`/v1/signals/${encodeURIComponent(id)}/open-case`, { owner_id, qa_reviewer_id });
