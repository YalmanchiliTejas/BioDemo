'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Check, Lock, PenLine, Send, ShieldCheck, Activity } from 'lucide-react';
import { templateOf, useAgent } from '@/lib/agent/agent-context';
import type { AgentTask } from '@/lib/agent/types';
import { ROLE_LABELS, ROLE_PEOPLE, useAppContext } from '@/lib/app-context';
import { Button, ClaimTag, EvidenceChip, Pill, SectionLabel, table } from '../ui';
import { cn } from '@/lib/cn';

const STAGES = ['Draft', 'Review required', 'Approved for handoff', 'Handoff (simulated)', 'Monitoring'] as const;

function stageIndex(t: AgentTask) {
  if (t.state === 'MONITORING_ACTIVE') return 4;
  if (t.state === 'SENT_TO_EXTERNAL_SYSTEM') return 3;
  if (t.state === 'APPROVED_FOR_HANDOFF') return 2;
  if (t.review.routedAt) return 1;
  return 0;
}

/** GxP review boundary for an agent proposal. Never writes to a system of record. */
export function ReviewRequiredGate({ task, variant = 'dock' }: { task: AgentTask; variant?: 'dock' | 'review' }) {
  const router = useRouter();
  const { dispatch } = useAgent();
  const { userRole, notify } = useAppContext();
  const r = templateOf(task).review!;
  const diff = r.diff(task.answers, task.selections);
  const stage = stageIndex(task);
  const [ack, setAck] = useState(false);
  const [meaning, setMeaning] = useState('Approved for handoff');
  const [revising, setRevising] = useState(false);
  const [note, setNote] = useState('');

  const isSigner = r.signOffRoles.includes(userRole);
  const isRequester = userRole === task.requesterRole;
  const needsSelection = task.templateId === 'schedule' && !task.selections['heuristic'];
  const complete = task.state !== 'RUNNING' && task.state !== 'QUEUED' && task.state !== 'NEEDS_USER_INPUT' && task.state !== 'WAITING_ON_PERMISSION';

  const route = () => {
    dispatch({ type: 'ROUTE', uid: task.uid });
    notify(`${r.proposalId} routed to REV-01. Required signer: ${r.signOffRoles.map((x) => ROLE_LABELS[x]).join(', ')}.`, 'info');
    router.push('/reviews/REV-01');
  };

  return (
    <div className="border-l-4 border-l-brand-teal bg-slate-50 rounded-r-card p-4 space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="flex items-center gap-1.5 text-[10.5px] font-semibold uppercase tracking-wider text-brand-teal-dark"><ShieldCheck className="h-3.5 w-3.5" aria-hidden /> Review required gate</p>
          <p className="mt-1 text-[13.5px] font-semibold text-text-primary">{r.title}</p>
          <p className="text-[11.5px] text-text-tertiary"><code className="font-mono">{r.proposalId}</code> · from {task.taskId} · risk {r.riskTier} · system of record {r.systemOfRecord}</p>
        </div>
        <ClaimTag kind={stage >= 2 ? 'approved' : 'recommendation'} />
      </div>

      <ol className="flex flex-wrap items-center gap-1 text-[10.5px]" aria-label="Proposal status">
        {STAGES.map((s, i) => (
          <li key={s} className="flex items-center gap-1">
            {i > 0 && <span className="h-px w-2 bg-border-strong" aria-hidden />}
            <span className={cn('inline-flex items-center gap-1 h-5 px-1.5 rounded-pill border', i < stage ? 'bg-status-success-bg border-emerald-200 text-emerald-700' : i === stage ? 'bg-white border-brand-teal text-brand-teal-dark font-semibold' : 'bg-white border-border-hairline text-text-muted')} aria-current={i === stage ? 'step' : undefined}>
              {i < stage && <Check className="h-2.5 w-2.5" aria-hidden />}{s}
            </span>
          </li>
        ))}
      </ol>

      <div className={table.wrap}>
        <table className={cn(table.root, 'bg-white border border-border-hairline rounded')}>
          <thead><tr><th className={table.th}>Parameter</th><th className={table.th}>Current</th><th className={table.th}>Proposed</th></tr></thead>
          <tbody>
            {diff.map((d) => (
              <tr key={d.parameter}>
                <td className={cn(table.td, 'text-[12px]')}>{d.parameter}{d.citation && <EvidenceChip id={d.citation} label="src" className="ml-1" />}</td>
                <td className={cn(table.td, 'text-[12px] text-text-secondary')}>{d.current}</td>
                <td className={cn(table.td, 'text-[12px] font-medium text-brand-teal-dark')}>{d.proposed}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {needsSelection && <p className="text-[11.5px] text-amber-700">Select an option in the schedule diff to fix the proposed change.</p>}

      <dl className="grid grid-cols-1 gap-1.5 text-[12px]">
        {[['Rationale', r.rationale], ['Expected result', r.expectedResult], ['Constraints', r.constraints], ['Owner', r.owner], ['Required sign-off', r.signOffRoles.map((x) => `${ROLE_LABELS[x]} (${ROLE_PEOPLE[x]})`).join(', ')]].map(([k, v]) => (
          <div key={k} className="flex gap-2"><dt className="w-28 shrink-0 text-text-tertiary">{k}</dt><dd className="text-text-primary">{v}</dd></div>
        ))}
        <div className="flex gap-2"><dt className="w-28 shrink-0 text-text-tertiary">Would change this</dt><dd className="text-text-primary"><ul className="list-disc pl-4">{r.changeMind.map((c) => <li key={c}>{c}</li>)}</ul></dd></div>
      </dl>

      {task.review.revisionNote && <p className="text-[11.5px] text-amber-800 bg-amber-50 border border-amber-200 rounded px-2 py-1">Revision requested: {task.review.revisionNote}</p>}

      {task.review.signedBy && (
        <p className="flex items-center gap-1.5 text-[12px] text-emerald-700"><PenLine className="h-3.5 w-3.5" aria-hidden /> {task.review.signedBy.meaning} by {task.review.signedBy.name} ({ROLE_LABELS[task.review.signedBy.role]}) · {new Date(task.review.signedBy.at).toISOString().slice(0, 16).replace('T', ' ')} UTC · simulated, not a Part 11 record</p>
      )}
      {task.review.monitoringSince && <p className="flex items-center gap-1.5 text-[12px] text-text-secondary"><Activity className="h-3.5 w-3.5 text-brand-teal" aria-hidden /> Monitoring: {r.monitor}</p>}

      {/* Actions */}
      <div className="flex flex-wrap items-center gap-2 pt-1">
        {!task.review.routedAt && complete && (
          <Button size="sm" variant="primary" onClick={route} disabled={needsSelection}><Send className="h-3 w-3" /> Submit for review · REV-01</Button>
        )}
        {task.review.routedAt && stage === 1 && variant === 'dock' && (
          <Button size="sm" variant="secondary" onClick={() => router.push('/reviews/REV-01')}><PenLine className="h-3 w-3" /> Open in REV-01</Button>
        )}
        {stage === 2 && (
          <Button size="sm" variant="secondary" onClick={() => dispatch({ type: 'DISPATCH', uid: task.uid })}><Send className="h-3 w-3" /> Hand off to {r.systemOfRecord} owner (simulated)</Button>
        )}
        {stage === 3 && (
          <Button size="sm" variant="secondary" onClick={() => dispatch({ type: 'MONITOR', uid: task.uid })}><Activity className="h-3 w-3" /> Track outcome</Button>
        )}
        {stage <= 1 && complete && !revising && <Button size="sm" variant="ghost" onClick={() => setRevising(true)}>Request revision</Button>}
      </div>
      {revising && (
        <div className="space-y-1.5">
          <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} placeholder="What should change, and why?" aria-label="Revision note" className="w-full rounded-control border border-border-strong bg-white px-2 py-1.5 text-[12.5px] focus:outline-none focus:ring-2 focus:ring-brand-teal" />
          <div className="flex gap-2">
            <Button size="sm" variant="primary" disabled={!note.trim()} onClick={() => { dispatch({ type: 'REVISE', uid: task.uid, artifactId: 'gate', note: note.trim() }); setRevising(false); setNote(''); }}>Record revision request</Button>
            <Button size="sm" variant="ghost" onClick={() => setRevising(false)}>Cancel</Button>
          </div>
        </div>
      )}

      {/* Signature block lives in REV-01 only. */}
      {variant === 'review' && stage === 1 && (
        <div className="rounded-card border border-border-hairline bg-white p-3 space-y-2">
          <SectionLabel>Signature</SectionLabel>
          {!isSigner ? (
            <p className="text-[12px] text-amber-700">{ROLE_LABELS[userRole]} is not a required signer. Required: {r.signOffRoles.map((x) => ROLE_LABELS[x]).join(', ')}. Switch role in the header to sign (demo).</p>
          ) : isRequester ? (
            <p className="text-[12px] text-amber-700">The requester cannot approve their own proposal.</p>
          ) : (
            <>
              <label className="flex items-start gap-2 text-[12.5px]"><input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} className="mt-0.5 accent-[#0e7490]" /> I reviewed the diff, the cited evidence and the open unknowns.</label>
              <label className="flex items-center gap-2 text-[12.5px]">Meaning
                <select value={meaning} onChange={(e) => setMeaning(e.target.value)} className="h-7 rounded-control border border-border-strong bg-white px-1.5 text-[12.5px]">
                  <option>Approved for handoff</option>
                  <option>Approved with conditions</option>
                </select>
              </label>
              <Button size="sm" variant="primary" disabled={!ack || needsSelection} onClick={() => { dispatch({ type: 'SIGN', uid: task.uid, role: userRole, meaning }); notify(`${r.proposalId} approved for handoff (simulated signature).`); }}>
                <PenLine className="h-3 w-3" /> Sign as {ROLE_PEOPLE[userRole]}
              </Button>
            </>
          )}
        </div>
      )}

      <p className="flex items-center gap-1.5 text-[11px] text-text-tertiary"><Lock className="h-3 w-3" aria-hidden /> Agent has no writeback to PLC/DCS, QMS, MES or ERP. Approval hands the proposal to the record owner; it does not execute it.</p>
      {variant === 'dock' && stage === 1 && <Pill tone="warning" dot>Waiting for {r.signOffRoles.map((x) => ROLE_LABELS[x]).join(', ')}</Pill>}
    </div>
  );
}
