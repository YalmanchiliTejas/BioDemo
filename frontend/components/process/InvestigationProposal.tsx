'use client';

import { useEffect, useState } from 'react';
import { Play, Users } from 'lucide-react';
import { processRequest } from '@/lib/process-api';
import { cached } from '@/lib/cache';
import { listRuns, notConfigured, notEntitled, startRun, type Run } from '@/lib/investigations-api';
import { InvestigationCard } from './InvestigationCard';
import type { ArtifactRef } from './AnalysisArtifact';

type Proposal = { proposal_id?: string; id?: string; objective?: string; rationale?: string; case_id?: string | null; site_id?: string;
  run_id?: string | null; evidence?: { label?: string; id?: string; kind?: string }[] | Record<string, unknown>; evidence_summary?: string;
  budget?: { max_tool_calls?: number; tool_calls_limit?: number; deadline_seconds?: number; max_minutes?: number } };

function evidenceLine(p: Proposal) {
  if (p.evidence_summary) return p.evidence_summary;
  if (Array.isArray(p.evidence) && p.evidence.length) return p.evidence.map(e => e.label ?? e.id).filter(Boolean).join(', ');
  return 'Records you can access in this workspace, re-checked when it starts';
}

/** The assistant may only propose; a person presses Start (a run spends model budget). */
export function InvestigationProposal({ threadId, siteId, artifact }: { threadId: string; siteId: string; artifact: ArtifactRef }) {
  const path = `/v1/process-model/conversations/${threadId}/artifacts/${artifact.kind}/${encodeURIComponent(artifact.id)}`;
  const [proposal, setProposal] = useState<Proposal | null>(() => cached<Proposal>(path) ?? null);
  const [run, setRun] = useState<Run | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [state, setState] = useState<'idle' | 'starting' | 'unconfigured' | 'paid'>('idle');
  const [error, setError] = useState('');
  useEffect(() => {
    let alive = true;
    processRequest<Proposal>(path).then(p => { if (!alive) return; setProposal(p); if (p.run_id) setRunId(p.run_id); }).catch(e => alive && setError(String(e)));
    // A run started from this proposal earlier (e.g. before a reload).
    listRuns({ conversation_id: threadId }).then(r => {
      const mine = r.runs.find(x => (x as Run & { proposal_id?: string }).proposal_id === artifact.id);
      if (alive && mine) { setRun(mine); setRunId(mine.run_id); }
    }).catch(() => undefined);
    return () => { alive = false; };
  }, [path, threadId, artifact.id]);

  if (runId) return <InvestigationCard runId={runId} initial={run} />;
  const objective = proposal?.objective ?? artifact.title;
  const calls = proposal?.budget?.max_tool_calls ?? proposal?.budget?.tool_calls_limit ?? 30;
  const mins = proposal?.budget?.max_minutes ?? (proposal?.budget?.deadline_seconds ? Math.round(proposal.budget.deadline_seconds / 60) : 10);
  async function start() {
    setState('starting'); setError('');
    try {
      const created = await startRun({ proposal_id: artifact.id, objective, site_id: proposal?.site_id ?? siteId, conversation_id: threadId, case_id: proposal?.case_id ?? null });
      setRun(created); setRunId(created.run_id);
    } catch (e) {
      if (notEntitled(e)) setState('paid');
      else if (notConfigured(e)) setState('unconfigured');
      else { setError((e as Error).message); setState('idle'); }
    }
  }
  return <section aria-label="Proposed investigation" className="my-3 rounded-card border border-brand-teal/30 bg-brand-teal-light/30 p-4 text-sm">
    <p className="flex items-center gap-2 font-medium text-text-primary"><Users size={15} className="text-brand-teal" />Proposed: a full investigation</p>
    <p className="mt-2 leading-6 text-text-primary">{objective}</p>
    {proposal?.rationale && <p className="mt-1 text-xs leading-5 text-text-secondary">{proposal.rationale}</p>}
    <dl className="mt-3 grid gap-2 text-xs sm:grid-cols-3">
      <div><dt className="text-text-tertiary">Evidence</dt><dd className="mt-0.5 text-text-secondary">{evidenceLine(proposal ?? {})}</dd></div>
      <div><dt className="text-text-tertiary">Limits</dt><dd className="mt-0.5 text-text-secondary">up to {calls} tool calls · {mins} min</dd></div>
      <div><dt className="text-text-tertiary">What you get</dt><dd className="mt-0.5 text-text-secondary">A cited report for review; nothing is changed in your systems</dd></div>
    </dl>
    {(state === 'paid' || (proposal as { entitled?: boolean } | null)?.entitled === false) ? <p role="status" className="mt-3 rounded-control bg-surface px-3 py-2 text-xs leading-5 text-text-secondary">
      Multi-agent investigations, where several investigators work your evidence in parallel, are part of the paid plan. The assistant can still work through this step by step here.
      {process.env.NEXT_PUBLIC_UPGRADE_URL && <> <a href={process.env.NEXT_PUBLIC_UPGRADE_URL} className="font-medium text-brand-teal underline">Talk to us about upgrading</a></>}</p>
    : state === 'unconfigured' ? <p role="status" className="mt-3 rounded-control bg-surface px-3 py-2 text-xs text-text-secondary">
      Investigation execution isn’t set up for this workspace yet. An administrator needs to connect the investigation service; until then the assistant can still answer step by step here.</p>
    : <div className="mt-3 flex items-center justify-between gap-3">
      <p className="text-[11px] text-text-tertiary">Investigators work in parallel. You can watch them and stop at any time.</p>
      <button type="button" onClick={() => void start()} disabled={state === 'starting'} className="inline-flex shrink-0 items-center gap-1.5 rounded-control bg-brand-teal px-3 py-2 text-xs font-medium text-white hover:bg-brand-teal-dark disabled:opacity-50">
        <Play size={13} />{state === 'starting' ? 'Starting…' : 'Start investigation'}</button>
    </div>}
    {error && <p role="alert" className="mt-2 text-xs text-status-critical">{error}</p>}
  </section>;
}
