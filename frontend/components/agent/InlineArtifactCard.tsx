'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Bot, Columns2, FileText, Pin, PlusSquare, Send, X } from 'lucide-react';
import { templateOf, useAgent } from '@/lib/agent/agent-context';
import { FRAME_HREF } from '@/lib/agent/screens';
import type { AgentTask, ArtifactData } from '@/lib/agent/types';
import { useAppContext } from '@/lib/app-context';
import { Button, ClaimTag, EvidenceChip, Pill, table } from '../ui';
import { ReviewRequiredGate } from './ReviewRequiredGate';
import { cn } from '@/lib/cn';

function MiniChart({ d, showReference }: { d: Extract<ArtifactData, { type: 'CHART_DIFF' }>; showReference: boolean }) {
  const W = 380, H = 150, P = { l: 30, r: 8, t: 8, b: 22 };
  const all = [...d.observed, ...d.compensated, ...(showReference ? d.reference : [])].map((p) => p[1]);
  const lo = Math.floor(Math.min(...all) - 0.3), hi = Math.ceil(Math.max(...all) + 0.3);
  const x = (h: number) => P.l + ((h - d.window[0]) / (d.window[1] - d.window[0])) * (W - P.l - P.r);
  const y = (v: number) => P.t + (1 - (v - lo) / (hi - lo)) * (H - P.t - P.b);
  const path = (pts: Array<[number, number]>) => pts.map(([h, v], i) => `${i ? 'L' : 'M'}${x(h).toFixed(1)},${y(v).toFixed(1)}`).join('');
  const ticks = [d.window[0], (d.window[0] + d.window[1]) / 2, d.window[1]];
  return (
    <figure className="max-w-[640px]">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" role="img" aria-label={`Feed rate ${d.unit}: observed, modelled compensation${showReference ? ' and reference batch' : ''}`}>
        <rect x={x(260)} y={P.t} width={x(272) - x(260)} height={H - P.t - P.b} fill="#fef3c7" opacity={0.6} />
        {[lo, (lo + hi) / 2, hi].map((v) => (
          <g key={v}><line x1={P.l} x2={W - P.r} y1={y(v)} y2={y(v)} stroke="#e2e8f0" /><text x={P.l - 4} y={y(v) + 3} fontSize={8} textAnchor="end" fill="#64748b">{v.toFixed(1)}</text></g>
        ))}
        {ticks.map((h, i) => <text key={h} x={x(h)} y={H - 8} fontSize={8} textAnchor={i === 0 ? 'start' : i === ticks.length - 1 ? 'end' : 'middle'} fill="#64748b">T+{h}h</text>)}
        {showReference && <path d={path(d.reference)} fill="none" stroke="#94a3b8" strokeWidth={1.2} />}
        <path d={path(d.observed)} fill="none" stroke="#dc2626" strokeWidth={1.5} />
        <path d={path(d.compensated)} fill="none" stroke="#0e7490" strokeWidth={1.5} strokeDasharray="4 3" />
      </svg>
      <figcaption className="mt-1 flex flex-wrap gap-3 text-[10.5px] text-text-tertiary">
        <span className="flex items-center gap-1"><span className="h-0.5 w-3 bg-[#dc2626]" /> MES-26073 observed</span>
        <span className="flex items-center gap-1"><span className="h-0.5 w-3 border-t border-dashed border-[#0e7490]" /> Modelled compensation</span>
        {showReference && <span className="flex items-center gap-1"><span className="h-0.5 w-3 bg-[#94a3b8]" /> MES-26071 reference</span>}
        <span className="flex items-center gap-1"><span className="h-2 w-3 bg-amber-100" /> Selected span T+260–272h</span>
      </figcaption>
    </figure>
  );
}

function Body({ task, data, compare }: { task: AgentTask; data: ArtifactData; compare: boolean }) {
  const { dispatch } = useAgent();
  switch (data.type) {
    case 'CHART_DIFF':
      return (
        <div className="space-y-2">
          <MiniChart d={data} showReference={compare} />
          <p className="text-[11.5px] text-text-tertiary">{data.note}</p>
          <div className="flex flex-wrap gap-1">{data.citations.map((c) => <EvidenceChip key={c} id={c} />)}</div>
        </div>
      );
    case 'HYPOTHESIS_MATRIX':
      return (
        <div className="space-y-2">
          <ul className="divide-y divide-border-hairline border border-border-hairline rounded">
            {data.rows.map((r) => (
              <li key={r.hypothesis} className="p-2.5 text-[12px]">
                <div className="flex items-start justify-between gap-2">
                  <p className="font-medium text-text-primary">{r.hypothesis}</p>
                  <ClaimTag kind={r.kind} />
                </div>
                <p className="mt-0.5 text-[11.5px] font-mono text-text-secondary">{r.statistic}</p>
                <dl className="mt-1 grid grid-cols-[56px_1fr] gap-x-2 gap-y-0.5 text-[11.5px]">
                  <dt className="text-text-tertiary">For</dt><dd className="text-text-secondary">{r.for}</dd>
                  <dt className="text-text-tertiary">Against</dt><dd className="text-text-secondary">{r.against}</dd>
                </dl>
                <div className="mt-1.5 flex flex-wrap gap-1">{r.citations.map((c) => <EvidenceChip key={c} id={c} />)}</div>
              </li>
            ))}
          </ul>
          <p className="text-[11.5px] text-text-tertiary">{data.note}</p>
        </div>
      );
    case 'TABLE_DIFF':
      return (
        <div className="space-y-2">
          <div className={table.wrap}>
            <table className={table.root}>
              <thead><tr><th className={table.th}>{data.columns[0]}</th>{compare && <th className={table.th}>{data.columns[1]}</th>}<th className={table.th}>{compare ? data.columns[2] : 'Change'}</th></tr></thead>
              <tbody>
                {data.rows.map((r) => (
                  <tr key={r.parameter}>
                    <td className={cn(table.td, 'text-[12px] align-top')}>{r.parameter}<span className="ml-1 inline-flex"><ClaimTag kind={r.kind} className="!h-4 !px-1 !text-[9px]" /></span>{r.citation && <EvidenceChip id={r.citation} label="src" className="ml-1" />}</td>
                    {compare ? (
                      <><td className={cn(table.td, 'text-[12px] text-text-secondary align-top')}>{r.current}</td><td className={cn(table.td, 'text-[12px] font-medium text-brand-teal-dark align-top')}>{r.proposed}</td></>
                    ) : (
                      <td className={cn(table.td, 'text-[12px] align-top')}><span className="text-text-tertiary line-through decoration-slate-300">{r.current}</span> → <span className="font-medium text-brand-teal-dark">{r.proposed}</span></td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-[11.5px] text-text-tertiary">{data.note}</p>
        </div>
      );
    case 'DOC_DRAFT':
      return (
        <div className="space-y-2.5">
          <p className="text-[11px] text-text-tertiary"><FileText className="inline h-3 w-3 mr-1" aria-hidden />{data.docId} · {data.version} · redline draft, not a controlled document</p>
          {data.sections.map((s) => (
            <div key={s.heading} className="rounded border border-border-hairline bg-white p-2.5">
              <div className="flex items-center justify-between gap-2"><p className="text-[12.5px] font-semibold">{s.heading}</p><ClaimTag kind={s.kind} /></div>
              <p className="mt-1 text-[12.5px] text-text-secondary leading-relaxed bg-emerald-50/60 border-l-2 border-emerald-300 pl-2">{s.body}</p>
              <div className="mt-1.5 flex flex-wrap gap-1">{s.citations.map((c) => <EvidenceChip key={c} id={c} />)}</div>
            </div>
          ))}
        </div>
      );
    case 'SCHEDULE_DIFF':
      return (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2" role="radiogroup" aria-label="Schedule option">
          {data.options.map((o) => {
            const sel = task.selections['heuristic'] === o.key;
            return (
              <div key={o.key} className={cn('rounded-card border p-2.5 bg-white transition-colors', sel ? 'border-brand-teal ring-1 ring-brand-teal' : 'border-border-hairline')}>
                <button type="button" role="radio" aria-checked={sel} onClick={() => dispatch({ type: 'SELECT', uid: task.uid, key: 'heuristic', value: o.key })} className="w-full text-left rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-teal">
                  <span className="flex items-center gap-1.5 text-[12.5px] font-semibold"><span className={cn('h-3 w-3 rounded-full border', sel ? 'border-brand-teal bg-brand-teal' : 'border-border-strong')} aria-hidden />Option {o.key}{o.recommended && <Pill tone="brand" className="!h-4 !text-[9.5px]">Agent pick</Pill>}</span>
                  <span className="mt-0.5 block text-[12px] text-text-primary">{o.title}</span>
                </button>
                <dl className="mt-1.5 space-y-0.5 text-[11.5px]">{o.rows.map(([k, v]) => <div key={k} className="flex justify-between gap-2"><dt className="text-text-tertiary">{k}</dt><dd className={cn('text-right', v.startsWith('Unknown') && 'text-text-muted italic')}>{v}</dd></div>)}</dl>
                <ul className="mt-1.5 list-disc pl-4 text-[11px] text-amber-700">{o.risks.map((r) => <li key={r}>{r}</li>)}</ul>
                <div className="mt-1.5 flex flex-wrap gap-1">{o.citations.map((c) => <EvidenceChip key={c} id={c} />)}</div>
              </div>
            );
          })}
        </div>
      );
    case 'REVIEW_GATE':
      return <ReviewRequiredGate task={task} />;
  }
}

export function InlineArtifactCard({ task, artifactId, variant = 'dock', currentFrame }: { task: AgentTask; artifactId: string; variant?: 'dock' | 'canvas'; currentFrame?: string | null }) {
  const router = useRouter();
  const { dispatch, openDock, setDockTab } = useAgent();
  const { notify } = useAppContext();
  const t = templateOf(task);
  const def = t.artifacts.find((a) => a.id === artifactId);
  const st = task.artifacts[artifactId];
  const [compare, setCompare] = useState(false);
  const [revising, setRevising] = useState(false);
  const [note, setNote] = useState('');
  if (!def || !st) return null;
  const data = def.build(task.answers, task.selections);

  if (data.type === 'REVIEW_GATE') return <ReviewRequiredGate task={task} variant={variant === 'canvas' ? 'review' : 'dock'} />;

  const canCompare = data.type === 'CHART_DIFF' || data.type === 'TABLE_DIFF';
  const target = def.insertTarget;
  const inserted = !!target && st.insertedInto.includes(target);
  const insert = () => {
    if (!target) return;
    dispatch({ type: 'INSERT', uid: task.uid, artifactId, frame: target });
    if (currentFrame !== target && FRAME_HREF[target]) router.push(FRAME_HREF[target]);
    notify(`${def.title} inserted into ${target} as an unreviewed agent draft.`, 'info');
  };
  const reviewReady = !!t.review && task.state === 'PROPOSAL_NEEDS_REVIEW' && !task.review.routedAt;

  return (
    <article className={cn('border border-slate-200 rounded-lg bg-white', variant === 'canvas' ? 'p-4 border-dashed border-cyan-300' : 'p-3')}>
      {variant === 'canvas' && (
        <p className="mb-2 flex flex-wrap items-center gap-1.5 text-[11px] text-brand-teal-dark">
          <Bot className="h-3.5 w-3.5" aria-hidden /> Inserted from <code className="font-mono">{task.taskId}</code> · {task.agent} · agent draft, not reviewed
          <span className="ml-auto flex items-center gap-1">
            <button type="button" onClick={() => { openDock(task.uid); setDockTab('OUTPUTS'); }} className="text-brand-teal hover:underline">Open in dock</button>
            {currentFrame && st.insertedInto.includes(currentFrame) && <button type="button" onClick={() => dispatch({ type: 'REMOVE_INSERT', uid: task.uid, artifactId, frame: currentFrame })} className="p-0.5 rounded hover:bg-surface-secondary text-text-tertiary" aria-label="Remove from canvas"><X className="h-3.5 w-3.5" /></button>}
          </span>
        </p>
      )}
      <header className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="text-[13px] font-semibold text-text-primary leading-5">{def.title}</h3>
          <p className="text-[11.5px] text-text-tertiary">{def.summary}</p>
        </div>
        <ClaimTag kind={def.kind} />
      </header>
      <div className="mt-2.5"><Body task={task} data={data} compare={compare} /></div>
      {st.revisionNote && <p className="mt-2 text-[11.5px] text-amber-800 bg-amber-50 border border-amber-200 rounded px-2 py-1">Revision requested: {st.revisionNote}</p>}
      <footer className="mt-3 flex flex-wrap items-center gap-1.5">
        {variant === 'dock' && target && (
          <Button size="sm" variant={inserted ? 'ghost' : 'primary'} onClick={insert} disabled={inserted}>
            <PlusSquare className="h-3 w-3" /> {inserted ? `Inserted in ${target}` : currentFrame === target ? 'Insert into canvas' : `Insert into ${target}`}
          </Button>
        )}
        {canCompare && <Button size="sm" variant={compare ? 'subtle' : 'secondary'} onClick={() => setCompare((c) => !c)} aria-pressed={compare}><Columns2 className="h-3 w-3" /> Compare</Button>}
        {!st.pinned ? (
          <Button size="sm" variant="secondary" onClick={() => { dispatch({ type: 'PIN', uid: task.uid, artifactId }); notify(`${def.title} pinned to WORK-01.`); }}><Pin className="h-3 w-3" /> Pin to WORK-01</Button>
        ) : (
          <Pill tone="success">Pinned to WORK-01</Pill>
        )}
        {!revising && <Button size="sm" variant="ghost" onClick={() => setRevising(true)}>Request revision</Button>}
        {reviewReady && <Button size="sm" variant="ghost" onClick={() => { dispatch({ type: 'ROUTE', uid: task.uid }); router.push('/reviews/REV-01'); }}><Send className="h-3 w-3" /> Route to REV-01</Button>}
      </footer>
      {revising && (
        <div className="mt-2 space-y-1.5">
          <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} placeholder="What should change, and why?" aria-label="Revision note" className="w-full rounded-control border border-border-strong px-2 py-1.5 text-[12.5px] focus:outline-none focus:ring-2 focus:ring-brand-teal" />
          <div className="flex gap-2">
            <Button size="sm" variant="primary" disabled={!note.trim()} onClick={() => { dispatch({ type: 'REVISE', uid: task.uid, artifactId, note: note.trim() }); setRevising(false); setNote(''); }}>Record request</Button>
            <Button size="sm" variant="ghost" onClick={() => setRevising(false)}>Cancel</Button>
          </div>
        </div>
      )}
    </article>
  );
}
