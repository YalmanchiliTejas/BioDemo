'use client';

import { Suspense, useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { AlertTriangle, ArrowLeft, ArrowUpRight, Check, FolderOpen, MessageSquare, X } from 'lucide-react';
import { Button, Callout, EvidenceChip, Pill, table } from '@/components/ui';
import { useOptionalCompanion } from '@/lib/companion-context';
import { SignalEvidence } from '@/components/trends/SignalEvidence';
import { acknowledgeSignal, dismissSignal, getSignal, KIND_LABEL, listSignals, openCaseFromSignal, SEVERITY_RANK, SEVERITY_TONE, type Signal, type SignalStatus } from '@/lib/signals-api';

const STATUS_LABEL: Record<SignalStatus, string> = { open: 'open', acknowledged: 'acknowledged', case_opened: 'case opened', dismissed: 'dismissed' };
const TRIAGE_LABEL: Record<string, string> = { pending: 'triage queued', running: 'assistant is triaging', ready: 'triage ready', skipped: 'triage skipped', failed: 'triage failed' };
const when = (iso?: string) => iso ? new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) : '—';

function limitText(s: Signal) {
  const l = s.limit; if (!l) return null;
  const parts = [l.low != null && `low ${l.low}`, l.high != null && `high ${l.high}`,
    l.critical_low != null && `critical low ${l.critical_low}`, l.critical_high != null && `critical high ${l.critical_high}`].filter(Boolean);
  return parts.length ? parts.join(' · ') + (s.unit ? ` ${s.unit}` : '') : null;
}

function SignalList() {
  const [signals, setSignals] = useState<Signal[] | null>(null);
  const [status, setStatus] = useState('open');
  const [minSeverity, setMinSeverity] = useState('');
  const [error, setError] = useState('');
  useEffect(() => {
    let alive = true;
    listSignals({ status: status === 'all' ? '' : status, min_severity: minSeverity })
      .then(r => { if (alive) { setSignals(r.signals); setError(''); } }).catch(e => { if (alive) setError(String((e as Error).message ?? e)); });
    return () => { alive = false; };
  }, [status, minSeverity]);
  const sorted = [...(signals ?? [])].sort((a, b) => SEVERITY_RANK[b.severity] - SEVERITY_RANK[a.severity] || (b.last_at ?? '').localeCompare(a.last_at ?? ''));
  return <div className="mx-auto max-w-[1100px] px-4 py-6 sm:px-6">
    <h1 className="text-2xl font-medium text-ink">Signals</h1>
    <p className="mt-1 max-w-2xl text-sm text-text-secondary">Possible deviations detected from your data. A signal is not a deviation: you decide whether to open a case. The assistant triages serious signals automatically and proposes next steps.</p>
    <div className="mt-5 flex flex-wrap items-center gap-3 text-sm">
      <label className="flex items-center gap-2">Status
        <select value={status} onChange={e => setStatus(e.target.value)} className="h-9 rounded border border-border-hairline bg-surface px-2">
          {['open', 'acknowledged', 'case_opened', 'dismissed', 'all'].map(s => <option key={s} value={s}>{s === 'all' ? 'all' : STATUS_LABEL[s as SignalStatus]}</option>)}</select></label>
      <label className="flex items-center gap-2">Severity
        <select value={minSeverity} onChange={e => setMinSeverity(e.target.value)} className="h-9 rounded border border-border-hairline bg-surface px-2">
          <option value="">any</option><option value="action">action or critical</option><option value="critical">critical only</option></select></label>
    </div>
    {error && <Callout tone="warning" className="mt-4" title="Signals unavailable">{error}</Callout>}
    {!signals && !error && <p role="status" className="mt-6 text-sm text-text-tertiary">Loading signals…</p>}
    {signals && !sorted.length && <p className="mt-6 text-sm text-text-tertiary">No {status === 'all' ? '' : STATUS_LABEL[status as SignalStatus] + ' '}signals.</p>}
    {!!sorted.length && <div className={`mt-4 ${table.wrap}`}><table className={table.root}>
      <thead><tr>{['Severity', 'What fired', 'Subject', 'Last seen', 'Status', 'Assistant'].map(h => <th key={h} className={table.th}>{h}</th>)}</tr></thead>
      <tbody>{sorted.map(s => <tr key={s.signal_id} className={table.tr}>
        <td className={table.td}><Pill tone={SEVERITY_TONE[s.severity]} dot>{s.severity}</Pill></td>
        <td className={table.td}><Link href={`/signals/?id=${encodeURIComponent(s.signal_id)}`} className="font-medium text-ink hover:text-brand-teal">{s.rule}</Link>
          <span className="block text-[12px] text-text-tertiary">{KIND_LABEL[s.kind] ?? s.kind}{(s.occurrences ?? 1) > 1 ? ` · ${s.occurrences} times` : ''}</span></td>
        <td className={table.td}>{s.subject ? `${s.subject.kind} ${s.subject.id}` : '—'}<span className="block text-[12px] text-text-tertiary">{s.site_id}</span></td>
        <td className={table.td}>{when(s.last_at ?? s.first_at)}</td>
        <td className={table.td}>{STATUS_LABEL[s.status]}</td>
        <td className={table.td}>{s.triage ? TRIAGE_LABEL[s.triage.status] ?? s.triage.status : '—'}</td>
      </tr>)}</tbody></table></div>}
  </div>;
}

function SignalDetail({ id }: { id: string }) {
  const [signal, setSignal] = useState<Signal | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [dismissing, setDismissing] = useState(false);
  const [reason, setReason] = useState('');
  const [caseForm, setCaseForm] = useState<{ owner: string; qa: string } | null>(null);
  const companion = useOptionalCompanion();
  const load = useCallback(() => getSignal(id).then(s => { setSignal(s); setError(''); }).catch(e => setError(String((e as Error).message ?? e))), [id]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    if (signal?.triage?.status !== 'running' && signal?.triage?.status !== 'pending') return;
    const timer = window.setInterval(() => void load(), 5000);
    return () => window.clearInterval(timer);
  }, [signal?.triage?.status, load]);
  async function act(fn: () => Promise<Signal>) {
    setBusy(true); setError('');
    try { setSignal(await fn()); setDismissing(false); setCaseForm(null); } catch (e) { setError(String((e as Error).message ?? e)); } finally { setBusy(false); }
  }
  if (!signal) return <p role="status" className="p-8 text-sm text-text-tertiary">{error || 'Opening signal…'}</p>;
  const limit = limitText(signal);
  const closed = signal.status === 'case_opened' || signal.status === 'dismissed';
  return <div className="mx-auto max-w-[1100px] px-4 py-6 sm:px-6">
    <Link href="/signals/" className="inline-flex items-center gap-1.5 text-xs text-text-tertiary hover:text-ink"><ArrowLeft size={13} />All signals</Link>
    <div className="mt-3 flex flex-wrap items-start justify-between gap-4">
      <div><div className="flex flex-wrap items-center gap-2"><Pill tone={SEVERITY_TONE[signal.severity]} dot>{signal.severity}</Pill><span className="text-xs text-text-tertiary">{KIND_LABEL[signal.kind] ?? signal.kind} · {signal.signal_id} · {STATUS_LABEL[signal.status]}</span></div>
        <h1 className="mt-2 text-xl font-medium text-ink">{signal.rule}</h1>
        <p className="mt-1 text-sm text-text-secondary">{signal.subject ? `${signal.subject.kind} ${signal.subject.id} · ` : ''}site {signal.site_id} · first {when(signal.first_at)}{(signal.occurrences ?? 1) > 1 ? ` · seen ${signal.occurrences} times, last ${when(signal.last_at)}` : ''}</p></div>
      {!closed && <div className="flex flex-wrap gap-2">
        {signal.status === 'open' && <Button size="sm" disabled={busy} onClick={() => act(() => acknowledgeSignal(id))}><Check size={14} />Acknowledge</Button>}
        <Button size="sm" variant="primary" disabled={busy} onClick={() => setCaseForm({ owner: '', qa: '' })}><FolderOpen size={14} />Open deviation case</Button>
        <Button size="sm" variant="ghost" disabled={busy} onClick={() => setDismissing(true)}><X size={14} />Dismiss</Button>
      </div>}
    </div>
    {error && <Callout tone="critical" className="mt-4">{error}</Callout>}
    {signal.status === 'dismissed' && <Callout tone="neutral" className="mt-4" title="Dismissed">{signal.dismiss_reason}</Callout>}
    {signal.status === 'case_opened' && signal.case_id && <Callout tone="success" className="mt-4" title={`Deviation case ${signal.case_id} opened`}>The case now holds this signal's evidence.</Callout>}
    {dismissing && <form className="mt-4 flex flex-wrap items-end gap-2 rounded-card border border-border-hairline bg-surface p-3" onSubmit={e => { e.preventDefault(); if (reason.trim()) void act(() => dismissSignal(id, reason.trim())); }}>
      <label className="flex-1 text-sm">Why is this not a deviation?<input autoFocus required value={reason} onChange={e => setReason(e.target.value)} className="mt-1 block h-9 w-full rounded border border-border-hairline px-2" placeholder="e.g. sensor calibration, value confirmed in range by retest" /></label>
      <Button size="sm" type="submit" disabled={!reason.trim() || busy}>Dismiss signal</Button><Button size="sm" variant="ghost" onClick={() => setDismissing(false)}>Cancel</Button></form>}
    {caseForm && <form className="mt-4 grid gap-3 rounded-card border border-border-hairline bg-surface p-3 sm:grid-cols-[1fr_1fr_auto]" onSubmit={e => { e.preventDefault(); void act(() => openCaseFromSignal(id, caseForm.owner.trim(), caseForm.qa.trim())); }}>
      <label className="text-sm">Investigation owner<input required value={caseForm.owner} onChange={e => setCaseForm({ ...caseForm, owner: e.target.value })} className="mt-1 block h-9 w-full rounded border border-border-hairline px-2" placeholder="person ID" /></label>
      <label className="text-sm">QA reviewer<input required value={caseForm.qa} onChange={e => setCaseForm({ ...caseForm, qa: e.target.value })} className="mt-1 block h-9 w-full rounded border border-border-hairline px-2" placeholder="person ID" /></label>
      <div className="flex items-end gap-2"><Button size="sm" variant="primary" type="submit" disabled={busy || !caseForm.owner.trim() || !caseForm.qa.trim()}>Open case</Button><Button size="sm" variant="ghost" onClick={() => setCaseForm(null)}>Cancel</Button></div>
      <p className="text-[12px] text-text-tertiary sm:col-span-3">Opens a formal deviation case pre-filled with this signal's evidence. This is your decision; the assistant can only propose it.</p></form>}

    <div className="mt-6 grid gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
      <section className="min-w-0 space-y-4">
        <div className="rounded-card border border-border-hairline bg-surface p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-text-tertiary">What fired</p>
          <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2">
            {signal.parameter && <div><dt className="text-text-tertiary">Parameter</dt><dd>{signal.parameter}</dd></div>}
            {signal.value != null && <div><dt className="text-text-tertiary">Value</dt><dd className="font-medium">{String(signal.value)}{signal.unit ? ` ${signal.unit}` : ''}</dd></div>}
            {limit && <div><dt className="text-text-tertiary">Limit</dt><dd>{limit}</dd></div>}
            {signal.spec_ref && <div><dt className="text-text-tertiary">Specification</dt><dd>{signal.spec_ref.spec_id} v{signal.spec_ref.version}</dd></div>}
            {signal.source && <div><dt className="text-text-tertiary">Source record</dt><dd>{signal.source.system} · {signal.source.record_id}</dd></div>}
          </dl>
        </div>
        <div className="rounded-card border border-border-hairline bg-surface p-4">
          <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-text-tertiary">The values behind it</p>
          <SignalEvidence signal={signal} />
        </div>
        <div className="rounded-card border border-border-hairline bg-surface p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-text-tertiary">Evidence records</p>
          {signal.evidence_refs?.length ? <div className="mt-3 flex flex-wrap gap-1.5">{signal.evidence_refs.map(r => <EvidenceChip key={`${r.kind}:${r.id}`} id={r.id} label={`${r.kind} · ${r.id}`} />)}</div>
            : <p className="mt-2 text-sm text-text-tertiary">No linked evidence records.</p>}
        </div>
      </section>
      <aside className="space-y-4">
        <div className="rounded-card border border-border-hairline bg-surface p-4">
          <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-text-tertiary"><MessageSquare size={13} />Assistant triage</p>
          {!signal.triage ? <p className="mt-2 text-sm text-text-tertiary">Not triaged.</p> : <>
            <p className="mt-2 text-sm">{TRIAGE_LABEL[signal.triage.status] ?? signal.triage.status}</p>
            {signal.triage.reason && <p className="mt-1 text-[12px] text-text-tertiary">{signal.triage.reason}</p>}
            {signal.triage.conversation_id && <Link href={`/home/?conversation=${encodeURIComponent(signal.triage.conversation_id)}`} className="mt-3 inline-flex items-center gap-1 text-sm font-medium text-brand-teal">Open the triage<ArrowUpRight size={14} /></Link>}
          </>}
          {companion && <Button size="sm" className="mt-3 w-full" onClick={() => companion.show({ kind: 'text', label: `Signal ${signal.signal_id}`, page_path: '/signals', captured_at: new Date().toISOString(),
            content: `deviation_signal ${signal.signal_id}: ${signal.rule}${signal.subject ? ` · ${signal.subject.kind} ${signal.subject.id}` : ''} · site ${signal.site_id}` })}>Ask the assistant about this</Button>}
        </div>
        <div className="rounded-card border border-border-hairline bg-surface p-4 text-sm">
          <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-text-tertiary"><AlertTriangle size={13} />Alerts</p>
          <p className="mt-2">{signal.alerts ? `${signal.alerts.sent} sent${signal.alerts.last_at ? `, last ${when(signal.alerts.last_at)}` : ''}` : 'None sent'}</p>
        </div>
      </aside>
    </div>
  </div>;
}

function Signals() {
  const id = useSearchParams().get('id');
  // Keyed by signal: a different id starts from an empty view, so its actions can never sit under another signal's details.
  return id ? <SignalDetail key={id} id={id} /> : <SignalList />;
}

export default function SignalsPage() {
  return <Suspense fallback={<p className="p-8 text-sm text-text-tertiary">Opening…</p>}><Signals /></Suspense>;
}
