'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { ArrowUpRight, CheckCircle2, Circle, Loader2, Square, Users, XCircle } from 'lucide-react';
import { ago, getRun, isActive, minutes, STATUS_LABEL, stopRun, type Agent, type Budget, type Run } from '@/lib/investigations-api';

export function AgentIcon({ status }: { status: Agent['status'] }) {
  if (status === 'done') return <CheckCircle2 size={14} className="shrink-0 text-status-success" aria-label="done" />;
  if (status === 'failed') return <XCircle size={14} className="shrink-0 text-status-critical" aria-label="failed" />;
  if (status === 'running') return <Loader2 size={14} className="shrink-0 text-brand-teal motion-safe:animate-spin" aria-label="running" />;
  return <Circle size={14} className="shrink-0 text-text-muted" aria-label="waiting" />;
}

export const agentName = (a: Agent) => a.role === 'lead' ? 'Lead' : 'Investigator';

/** Lead first, then each agent's children beneath it (depth-first). */
export function orderedAgents(agents: Agent[]): { agent: Agent; depth: number }[] {
  const ids = new Set(agents.map(a => a.agent_id));
  const children = (parent: string | null) => agents.filter(a => (a.parent_id && ids.has(a.parent_id) ? a.parent_id : null) === parent && a.agent_id !== parent);
  const out: { agent: Agent; depth: number }[] = [];
  const walk = (parent: string | null, depth: number) => {
    for (const a of children(parent).sort((x, y) => (x.role === 'lead' ? -1 : 0) - (y.role === 'lead' ? -1 : 0))) {
      if (out.some(o => o.agent.agent_id === a.agent_id)) continue;
      out.push({ agent: a, depth }); walk(a.agent_id, depth + 1);
    }
  };
  walk(null, 0);
  return out;
}

export function agentLine(a: Agent, active: boolean) {
  if (a.status === 'running' && a.current_tool) return `using ${a.current_tool.replaceAll('_', ' ')}`;
  if (a.status === 'running') return 'thinking';
  if (a.status === 'waiting') return active ? 'waiting' : 'did not start';
  if (a.status === 'failed') return 'stopped with an error';
  const findings = a.subreports.length;
  return findings ? `${findings} finding${findings === 1 ? '' : 's'} saved` : 'finished';
}

export function BudgetBar({ budget, compact = false }: { budget: Budget; compact?: boolean }) {
  const share = budget.tool_calls_limit ? Math.min(1, budget.tool_calls_used / budget.tool_calls_limit) : 0;
  return <div className={compact ? '' : 'space-y-1.5'}>
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-secondary" role="progressbar" aria-label="Tool calls used"
      aria-valuenow={budget.tool_calls_used} aria-valuemin={0} aria-valuemax={budget.tool_calls_limit}>
      <div className={`h-full rounded-full ${share > 0.9 ? 'bg-status-warning' : 'bg-brand-teal'}`} style={{ width: `${share * 100}%` }} />
    </div>
    <p className="mt-1.5 text-[11px] text-text-tertiary">
      {budget.tool_calls_used}/{budget.tool_calls_limit} tool calls · {minutes(budget.elapsed_seconds)}/{minutes(budget.deadline_seconds)} min
      {budget.tokens != null && ` · ${budget.tokens.toLocaleString()}${budget.token_limit ? `/${budget.token_limit.toLocaleString()}` : ''} tokens`}
      {' · cost: '}{budget.cost_status && budget.cost_status !== 'unknown' ? budget.cost_status.replaceAll('_', ' ') : 'unknown'}
    </p>
  </div>;
}

export function StopButton({ run, onStopped }: { run: Run; onStopped: (r: Run) => void }) {
  const [armed, setArmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => { if (!armed) return; const t = window.setTimeout(() => setArmed(false), 4000); return () => window.clearTimeout(t); }, [armed]);
  if (!isActive(run.status)) return null;
  return <span className="inline-flex items-center gap-2">
    {error && <span role="alert" className="text-[11px] text-status-critical">{error}</span>}
    <button type="button" disabled={busy} onClick={async () => {
      if (!armed) { setArmed(true); return; }
      setBusy(true); setError('');
      try { onStopped(await stopRun(run.run_id)); } catch (e) { setError((e as Error).message); } finally { setBusy(false); setArmed(false); }
    }} className={`inline-flex items-center gap-1.5 rounded-control px-2.5 py-1.5 text-xs font-medium ${armed ? 'bg-status-critical text-white' : 'border border-border-hairline text-text-secondary hover:border-status-critical hover:text-status-critical'} disabled:opacity-50`}>
      <Square size={11} />{busy ? 'Stopping…' : armed ? 'Stop now?' : 'Stop'}</button>
  </span>;
}

/** Re-renders every second for "updated Ns ago" and polls the run every 2 s while it is active. */
export function useRun(runId: string, initial?: Run | null) {
  const [run, setRun] = useState<Run | null>(initial ?? null);
  const [error, setError] = useState('');
  const [, tick] = useState(0);
  const live = useRef(true);
  useEffect(() => {
    live.current = true;
    let timer = 0;
    const load = async () => {
      try { const r = await getRun(runId); if (!live.current) return; setRun(r); setError(''); if (isActive(r.status)) timer = window.setTimeout(load, 2000); }
      catch (e) { if (!live.current) return; setError((e as Error).message); timer = window.setTimeout(load, 5000); }
    };
    void load();
    const clock = window.setInterval(() => tick(n => n + 1), 1000);
    return () => { live.current = false; window.clearTimeout(timer); window.clearInterval(clock); };
  }, [runId]);
  return { run, setRun, error };
}

export function SyncNote({ run }: { run: Run }) {
  if (run.sync?.reachable === false) return <span className="text-status-warning">execution service unreachable{run.sync.updated_at ? ` since ${ago(run.sync.updated_at)} ago` : ''}</span>;
  const updated = ago(run.sync?.updated_at);
  return updated ? <span>updated {updated} ago</span> : null;
}

export function InvestigationCard({ runId, initial }: { runId: string; initial?: Run | null }) {
  const { run, setRun, error } = useRun(runId, initial);
  if (!run) return <p role="status" className="my-3 text-xs text-text-tertiary">{error || 'Opening investigation…'}</p>;
  const active = isActive(run.status);
  const agents = orderedAgents(run.agents);
  const elapsed = minutes(run.budget.elapsed_seconds);
  return <section aria-label={`Investigation: ${run.objective}`} className="my-3 rounded-card border border-border-hairline bg-surface p-4 shadow-[0_1px_3px_rgba(16,24,40,0.06)]">
    <div className="flex flex-wrap items-start justify-between gap-2">
      <div className="min-w-0">
        <p className="flex items-center gap-2 text-sm font-medium text-text-primary"><Users size={15} className="text-brand-teal" /><span className="truncate">Investigation · {run.objective}</span></p>
        <p className="mt-0.5 text-[11px] text-text-tertiary">{STATUS_LABEL[run.status]}{active || run.budget.elapsed_seconds ? ` · ${elapsed} min` : ''} · <SyncNote run={run} /></p>
      </div>
      <StopButton run={run} onStopped={setRun} />
    </div>
    {agents.length ? <ul className="mt-3 space-y-1.5">{agents.map(({ agent, depth }) => <li key={agent.agent_id} className="flex items-center gap-2 text-xs" style={{ paddingLeft: depth * 14 }}>
      <AgentIcon status={agent.status} />
      <span className="w-24 shrink-0 font-medium text-text-primary">{agentName(agent)}</span>
      <span className="min-w-0 flex-1 truncate text-text-secondary" title={agent.question ?? undefined}>{agent.question || agentLine(agent, active)}</span>
      <span className="hidden shrink-0 text-text-tertiary sm:inline">{agentLine(agent, active)}{agent.tool_calls ? ` · ${agent.tool_calls} calls` : ''}</span>
      {agent.attribution === 'approximate' && <span className="shrink-0 rounded-pill border border-border-hairline px-1.5 text-[10px] text-text-tertiary" title="Tool calls are matched to this investigator by timing; the runtime did not report which investigator made them.">approximate</span>}
    </li>)}</ul> : <p className="mt-3 text-xs text-text-tertiary">{active ? 'Waiting for the first investigator to start…' : 'No investigator activity was recorded.'}</p>}
    <div className="mt-3"><BudgetBar budget={run.budget} compact /></div>
    {(run.status === 'failed' || run.status === 'blocked' || run.status === 'cancelled') && <p className="mt-2 rounded-control bg-status-warning-bg px-3 py-2 text-xs text-text-secondary">
      {run.status === 'cancelled' ? 'Stopped.' : 'This investigation ended without a validated report.'} {run.agents.reduce((n, a) => n + a.subreports.length, 0)} saved finding{run.agents.reduce((n, a) => n + a.subreports.length, 0) === 1 ? '' : 's'} remain inspectable.</p>}
    {run.status === 'awaiting_review' && <p className="mt-2 text-xs text-text-secondary">The report is ready for review. Its findings are hypotheses until a qualified reviewer accepts them.</p>}
    <div className="mt-3 flex justify-end"><Link href={`/investigations/?run=${encodeURIComponent(run.run_id)}`} className="inline-flex items-center gap-1.5 rounded-control bg-brand-teal px-3 py-2 text-xs font-medium text-white hover:bg-brand-teal-dark">
      {run.status === 'awaiting_review' ? 'Review the report' : 'Open investigation'}<ArrowUpRight size={14} /></Link></div>
  </section>;
}
