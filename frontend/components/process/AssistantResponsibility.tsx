'use client';

import { useState } from 'react';
import { processRequest } from '@/lib/process-api';

export type Responsibility = { enabled: boolean; objective: string; kinds: string[]; max_runs: number; runs_admitted: number; every_minutes?: number | null; billing: string };
export function AssistantResponsibility<T extends { id: string; revision: number; responsibility?: Responsibility | null; mission_status?: string }>({ thread, onChange }: { thread: T; onChange: (data: T) => void }) {
  const [objective, setObjective] = useState(thread.responsibility?.objective ?? '');
  const [kinds, setKinds] = useState(thread.responsibility?.kinds ?? ['case']);
  const [maxRuns, setMaxRuns] = useState(thread.responsibility?.max_runs ?? 3);
  const [scheduled, setScheduled] = useState(!!thread.responsibility?.every_minutes);
  const [ack, setAck] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const watch = thread.responsibility;
  async function save(enabled: boolean) {
    setBusy(true); setError('');
    try {
      const data = await processRequest<T>(`/v1/process-model/conversations/${thread.id}/responsibility`, {
        enabled, expected_revision: thread.revision, objective, kinds, max_runs: maxRuns,
        every_minutes: scheduled ? 60 : null, acknowledge_inference: ack,
      });
      onChange(data);
    } catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  }
  return <details className="my-2 text-xs text-text-secondary [&[open]]:rounded-card [&[open]]:bg-surface [&[open]]:p-4 [&[open]]:shadow-[0_1px_3px_rgba(16,24,40,0.06)]">
    <summary className="cursor-pointer list-none text-text-tertiary hover:text-brand-teal">{thread.mission_status === 'paused_budget' ? 'Follow-up paused: run limit reached' : watch?.enabled ? '● Keeping an eye on this for you' : 'Keep an eye on this for me…'}</summary>
    <div className="mt-3 space-y-3">
      <label className="block">What should I keep working on?<textarea value={objective} maxLength={2000} onChange={e => setObjective(e.target.value)} className="mt-2 block w-full rounded border border-border-strong bg-surface p-2" placeholder="Review new deviations, inspect supporting records and prepare evidence requests for review." /></label>
      <fieldset><legend className="mb-2">Sources to follow in this site</legend><div className="flex flex-wrap gap-4">{[['case', 'Deviation cases'], ['evidence', 'New or corrected evidence'], ['batch', 'Batches'], ['sample', 'Samples']].map(([kind, label]) => <label key={kind} className="flex items-center gap-2"><input type="checkbox" checked={kinds.includes(kind)} onChange={e => setKinds(previous => e.target.checked ? [...previous, kind] : previous.filter(k => k !== kind))} />{label}</label>)}</div></fieldset>
      <label className="flex items-center gap-2"><input type="checkbox" checked={scheduled} onChange={e => setScheduled(e.target.checked)} />Also follow up hourly</label>
      <label className="flex items-center gap-2">Background run allowance <input type="number" min={1} max={10} value={maxRuns} onChange={e => setMaxRuns(Number(e.target.value))} className="w-16 rounded border border-border-strong bg-surface p-1" /></label>
      <p className="text-text-tertiary">{watch?.runs_admitted ?? 0} runs used. Up to 6 planning model requests per run; scientific tools may add usage. Provider billing is unknown; this allowance is not a dollar cap. Results appear in this conversation. Production changes require approval.</p>
      <label className="flex items-start gap-2"><input type="checkbox" checked={ack} onChange={e => setAck(e.target.checked)} />I authorize background reads, analysis and drafts within this scope and acknowledge inference usage.</label>
      <div className="flex gap-3"><button type="button" disabled={busy || !ack || !objective.trim() || !kinds.length} onClick={() => void save(true)} className="rounded bg-brand-teal px-3 py-2 text-white disabled:opacity-40">{watch?.enabled ? 'Update responsibility' : 'Start follow-up'}</button>{watch?.enabled && <button type="button" disabled={busy} onClick={() => void save(false)} className="rounded border border-border-strong px-3 py-2">Pause follow-up</button>}</div>
      {error && <p role="alert" className="text-status-critical">{error}</p>}
    </div>
  </details>;
}
