'use client';

import { Suspense, useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { ArrowLeft, FileText, Send, Users } from 'lucide-react';
import { EvidenceChip, Pill, type Tone } from '@/components/ui';
import { AgentIcon, agentLine, agentName, BudgetBar, orderedAgents, StopButton, SyncNote, useRun } from '@/components/process/InvestigationCard';
import { ago, isActive, listRuns, runEvents, runReport, sendForReview, STATUS_LABEL, type Report, type Run, type RunEvent, type RunStatus } from '@/lib/investigations-api';

const TONE: Record<RunStatus, Tone> = { queued: 'neutral', submitted: 'info', running: 'info', finalizing: 'info', awaiting_review: 'success', blocked: 'warning', failed: 'critical', cancelled: 'muted' };
const count = (n: number | undefined, word: string) => `${n ?? 0} ${word}${(n ?? 0) === 1 ? '' : 's'}`;
const HIDDEN = new Set(['agent_activity', 'budget']); // shown live in the "Now" strip and budget panel instead

function describe(e: RunEvent, name: (id: string | null) => string) {
  const p = e.payload as Record<string, string | number | string[] | undefined>;
  switch (e.kind) {
    case 'phase': return `Phase: ${String(p.phase ?? '').replaceAll('_', ' ')}`;
    case 'agent_started': return `${name(e.agent_id)} started${p.question ? `: ${p.question}` : ''}`;
    case 'agent_finished': return `${name(e.agent_id)} finished${p.status && p.status !== 'done' ? ` (${p.status})` : ''}`;
    case 'allocation': return `Lead assigned work${p.owner ? ` to ${p.owner}` : ''}${p.reason ? `: ${p.reason}` : ''}`;
    case 'subreport_saved': return `${name(e.agent_id)} saved findings${p.assessment ? `: ${p.assessment}` : ''}`;
    case 'error': return `Error: ${p.code ?? 'unknown'}`;
    default: return e.kind.replaceAll('_', ' ');
  }
}

function useEvents(runId: string, active: boolean) {
  const [events, setEvents] = useState<RunEvent[]>([]);
  const next = useRef(0);
  useEffect(() => { setEvents([]); next.current = 0; }, [runId]);
  useEffect(() => {
    let alive = true, timer = 0;
    const load = async () => {
      try {
        for (let page = 0; page < 10; page++) { // drain a backlog, then wait
          const r = await runEvents(runId, next.current);
          if (!alive) return;
          if (r.events.length) setEvents(old => [...old, ...r.events.filter(e => !old.some(o => o.seq === e.seq))]);
          const moved = r.next > next.current; next.current = Math.max(next.current, r.next);
          if (!moved || r.events.length < 500) break;
        }
      } catch { /* the run panel shows reachability */ }
      if (alive && active) timer = window.setTimeout(load, 2000);
    };
    void load();
    return () => { alive = false; window.clearTimeout(timer); };
  }, [runId, active]);
  return events;
}

function RunView({ runId }: { runId: string }) {
  const { run, setRun, error } = useRun(runId);
  const active = run ? isActive(run.status) : false;
  const events = useEvents(runId, active || !run);
  const [selected, setSelected] = useState<string | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [reportError, setReportError] = useState('');
  useEffect(() => {
    if (run?.status !== 'awaiting_review' || report) return;
    runReport(run.run_id).then(setReport).catch(e => setReportError((e as Error).message));
  }, [run?.status, run?.run_id, report]);
  const agents = useMemo(() => run ? orderedAgents(run.agents) : [], [run]);
  const name = (id: string | null) => { const a = run?.agents.find(x => x.agent_id === id); return a ? agentName(a) : 'Lead'; };
  if (!run) return <p role="status" className="p-8 text-sm text-text-tertiary">{error || 'Opening investigation…'}</p>;
  const visible = events.filter(e => !HIDDEN.has(e.kind) && (!selected || e.agent_id === selected)).slice().reverse();
  const subreports = run.agents.filter(a => !selected || a.agent_id === selected).flatMap(a => a.subreports.map(s => ({ agent: a, s })));
  const now = run.agents.filter(a => a.status === 'running');
  const finished = run.agents.filter(a => a.status === 'done').length;
  return <div className="mx-auto max-w-[1280px] px-4 py-6 sm:px-6">
    <Link href="/investigations/" className="inline-flex items-center gap-1 text-xs text-text-tertiary hover:text-text-secondary"><ArrowLeft size={13} />All investigations</Link>
    <header className="mt-2 flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0"><h1 className="text-xl font-medium text-text-primary">{run.objective}</h1>
        <p className="mt-1 flex flex-wrap items-center gap-2 text-xs text-text-tertiary"><Pill tone={TONE[run.status]}>{STATUS_LABEL[run.status]}</Pill>
          {run.case_id && <span>Case {run.case_id}</span>}<span>{finished}/{run.agents.length} investigators finished</span><SyncNote run={run} /></p></div>
      <StopButton run={run} onStopped={setRun} />
    </header>
    {run.basis_status === 'stale' && <p className="mt-3 rounded-control bg-status-warning-bg px-3 py-2 text-xs">The evidence changed after this investigation started. It continued on its pinned snapshot; check the report against current records.</p>}
    {(run.status === 'failed' || run.status === 'blocked' || run.status === 'cancelled') && <p className="mt-3 rounded-control bg-status-warning-bg px-3 py-2 text-xs text-text-secondary">
      {run.status === 'cancelled' ? 'You stopped this investigation.' : 'This investigation ended without a validated report.'} What finished is below: {finished} investigator{finished === 1 ? '' : 's'} completed and {run.agents.reduce((n, a) => n + a.subreports.length, 0)} findings were saved.{run.issues?.length ? ` ${run.issues.join(' ')}` : ''}</p>}

    <div className="mt-5 grid gap-5 lg:grid-cols-[240px_minmax(0,1fr)_280px]">
      <aside aria-label="Investigators" className="space-y-1">
        <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-text-tertiary">Investigators</p>
        <button type="button" onClick={() => setSelected(null)} className={`w-full rounded-control px-2 py-1.5 text-left text-xs ${!selected ? 'bg-brand-teal-light/60 font-medium' : 'text-text-secondary hover:bg-surface-secondary'}`}>Everyone</button>
        {agents.map(({ agent, depth }) => <button key={agent.agent_id} type="button" aria-pressed={selected === agent.agent_id} onClick={() => setSelected(agent.agent_id)}
          style={{ paddingLeft: 8 + depth * 12 }} className={`flex w-full items-start gap-2 rounded-control py-1.5 pr-2 text-left text-xs ${selected === agent.agent_id ? 'bg-brand-teal-light/60' : 'hover:bg-surface-secondary'}`}>
          <span className="mt-0.5"><AgentIcon status={agent.status} /></span>
          <span className="min-w-0"><span className="block font-medium text-text-primary">{agentName(agent)}{agent.attribution === 'approximate' && <span className="ml-1.5 font-normal text-text-tertiary" title="Matched by timing; the runtime did not report which investigator made each call.">· approximate</span>}</span>
            <span className="block truncate text-text-tertiary" title={agent.question ?? undefined}>{agent.question || agentLine(agent, active)}</span></span>
        </button>)}
        {!agents.length && <p className="px-2 text-xs text-text-tertiary">{active ? 'Waiting for the lead to start…' : 'No investigator activity was recorded.'}</p>}
      </aside>

      <main className="min-w-0 space-y-4">
        {active && <section aria-label="Now" className="rounded-card border border-border-hairline bg-surface p-3">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-text-tertiary">Now</p>
          {now.length ? <ul className="mt-1.5 flex flex-wrap gap-2">{now.map(a => <li key={a.agent_id} className="rounded-pill border border-border-hairline px-2.5 py-1 text-xs text-text-secondary">
            {agentName(a)} · {agentLine(a, true)}{a.last_activity_at ? ` · ${ago(a.last_activity_at)} ago` : ''}</li>)}</ul>
          : <p className="mt-1 text-xs text-text-tertiary">{run.status === 'finalizing' ? 'The lead is writing the report.' : 'Starting up…'}</p>}
        </section>}

        {run.status === 'awaiting_review' && <section aria-label="Report" className="rounded-card border border-border-hairline bg-surface p-4">
          <div className="flex flex-wrap items-center justify-between gap-2"><p className="flex items-center gap-2 text-sm font-medium"><FileText size={15} className="text-brand-teal" />Report · requires human review</p>
            <SendForReview run={run} /></div>
          {reportError ? <p role="alert" className="mt-2 text-xs text-status-critical">{reportError}</p> : !report ? <p className="mt-2 text-xs text-text-tertiary">Loading report…</p> : <>
            {(report.report.summary || report.report.assessment) && <p className="mt-3 text-sm leading-6">{report.report.summary ?? report.report.assessment}</p>}
            {!!report.report.findings?.length && <ul className="mt-3 space-y-2">{report.report.findings.map((f, i) => <li key={i} className="rounded-control bg-surface-secondary/60 px-3 py-2 text-xs">
              <Pill tone={f.status === 'supported' ? 'success' : f.status === 'unknown' ? 'muted' : 'warning'}>{f.status ?? f.kind ?? 'hypothesis'}</Pill> <span className="ml-1">{f.text ?? f.title}</span>
              {!!f.evidence_ids?.length && <span className="mt-1.5 flex flex-wrap gap-1">{f.evidence_ids.slice(0, 8).map(id => <EvidenceChip key={id} id={id} />)}</span>}</li>)}</ul>}
            {!!report.report.open_questions?.length && <><p className="mt-3 text-xs font-medium text-text-secondary">Still unknown</p><ul className="mt-1 list-disc pl-5 text-xs">{report.report.open_questions.map(q => <li key={q}>{q}</li>)}</ul></>}
            <p className="mt-3 text-[11px] text-text-tertiary">Findings are hypotheses until a qualified reviewer accepts them. Nothing was changed in your systems.</p></>}
        </section>}

        {!!subreports.length && <section aria-label="Findings saved by investigators" className="space-y-2">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-text-tertiary">Findings saved by investigators</p>
          {subreports.map(({ agent, s }) => <article key={`${agent.agent_id}:${s.subreport_id}`} className="rounded-card border border-border-hairline bg-surface p-3 text-xs">
            <p className="text-text-tertiary">{agentName(agent)}{agent.question ? ` · ${agent.question}` : ''}</p>
            {s.assessment && <p className="mt-1 text-sm leading-6 text-text-primary">{s.assessment}</p>}
            <p className="mt-1 text-text-tertiary">{count(s.fact_count, 'observation')} · {count(s.claim_count, 'claim')} · {count(s.open_question_count, 'open question')}</p>
            {!!s.evidence_ids?.length && <p className="mt-2 flex flex-wrap gap-1">{s.evidence_ids.slice(0, 12).map(id => <EvidenceChip key={id} id={id} />)}{s.evidence_ids.length > 12 && <span className="text-text-tertiary">+{s.evidence_ids.length - 12}</span>}</p>}
          </article>)}
        </section>}

        <section aria-label="Timeline">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-text-tertiary">Timeline</p>
          {visible.length ? <ol className="mt-2 space-y-2 border-l border-border-hairline pl-4">{visible.map(e => <li key={e.seq} className="relative text-xs">
            <span className="absolute -left-[21px] top-1.5 h-2 w-2 rounded-full bg-brand-teal" aria-hidden />
            <span className="text-text-tertiary">{new Date(e.at).toLocaleTimeString()}</span> <span className="text-text-primary">{describe(e, name)}</span></li>)}</ol>
          : <p className="mt-2 text-xs text-text-tertiary">No events yet.</p>}
        </section>
      </main>

      <aside aria-label="Budget and evidence" className="space-y-4">
        <section className="rounded-card border border-border-hairline bg-surface p-3"><p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-text-tertiary">Budget</p><BudgetBar budget={run.budget} /></section>
        <section className="rounded-card border border-border-hairline bg-surface p-3 text-xs"><p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-text-tertiary">Evidence it works from</p>
          {run.evidence_snapshot?.items?.length ? <ul className="space-y-1">{run.evidence_snapshot.items.slice(0, 20).map(i => <li key={i.id} className="truncate" title={i.id}>{i.label ?? i.id}{i.kind ? <span className="text-text-tertiary"> · {i.kind.replaceAll('_', ' ')}</span> : null}</li>)}</ul>
          : <p className="text-text-tertiary">Snapshot details not available.</p>}
          {run.evidence_snapshot?.taken_at && <p className="mt-2 text-text-tertiary">Pinned {new Date(run.evidence_snapshot.taken_at).toLocaleString()}; later changes are not mixed in.</p>}
          {run.evidence_snapshot?.sha256 && <p className="mt-1 truncate font-mono text-[10px] text-text-muted" title={run.evidence_snapshot.sha256}>sha256 {run.evidence_snapshot.sha256.slice(0, 16)}…</p>}
        </section>
      </aside>
    </div>
  </div>;
}

function RunIndex() {
  const [runs, setRuns] = useState<Run[] | null>(null);
  const [error, setError] = useState('');
  useEffect(() => { listRuns({}).then(r => setRuns(r.runs)).catch(e => setError((e as Error).message)); }, []);
  return <div className="mx-auto max-w-3xl px-4 py-8 sm:px-6">
    <h1 className="flex items-center gap-2 text-xl font-medium"><Users size={18} className="text-brand-teal" />Investigations</h1>
    <p className="mt-1 text-sm text-text-secondary">Multi-investigator runs you started from the assistant. Ask the assistant for a full investigation to start one.</p>
    {error && <p role="alert" className="mt-4 text-xs text-status-critical">{error}</p>}
    {runs && !runs.length && <p className="mt-6 text-sm text-text-tertiary">No investigations yet.</p>}
    {!!runs?.length && <ul className="mt-5 divide-y divide-border-hairline rounded-card border border-border-hairline bg-surface">{runs.map(r => <li key={r.run_id}>
      <Link href={`/investigations/?run=${encodeURIComponent(r.run_id)}`} className="flex items-center justify-between gap-3 px-4 py-3 text-sm hover:bg-surface-secondary/60">
        <span className="min-w-0 truncate">{r.objective}</span><Pill tone={TONE[r.status]}>{STATUS_LABEL[r.status]}</Pill></Link></li>)}</ul>}
  </div>;
}

function Investigations() {
  const run = useSearchParams().get('run');
  return run ? <RunView key={run} runId={run} /> : <RunIndex />;
}

export default function InvestigationsPage() {
  return <Suspense fallback={<p className="p-8 text-sm text-text-tertiary">Opening…</p>}><Investigations /></Suspense>;
}

/** Adds the report's hypotheses and open questions to the case as labelled claims and builds the QA package. */
function SendForReview({ run }: { run: Run }) {
  const [state, setState] = useState<'idle' | 'busy' | 'sent'>('idle');
  const [message, setMessage] = useState('');
  if (!run.case_id) return <span className="text-xs text-text-tertiary" title="Only investigations linked to a case can go to QA review">Not linked to a case</span>;
  if (state === 'sent') return <span role="status" className="text-xs text-status-success">{message}</span>;
  return <span className="flex items-center gap-2">
    {message && <span role="alert" className="text-xs text-status-critical">{message}</span>}
    <button type="button" disabled={state === 'busy'} onClick={async () => {
      setState('busy'); setMessage('');
      try { const r = await sendForReview(run.run_id); setMessage(`Sent: ${r.claims.length} hypotheses and open questions added to ${run.case_id} for QA review`); setState('sent'); }
      catch (e) { setMessage((e as Error).message); setState('idle'); }
    }} className="inline-flex items-center gap-1.5 rounded-control bg-brand-teal px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50"><Send size={13} />Send for QA review</button>
  </span>;
}
