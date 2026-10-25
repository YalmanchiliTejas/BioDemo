'use client';

import { useEffect, useRef, useState } from 'react';
import { usePathname } from 'next/navigation';
import Link from 'next/link';
import { Bot, Check, ChevronDown, Circle, CornerDownLeft, Loader2, Lock, Minimize2, Pause, Pin, PinOff, Plus, RotateCcw, Square, Zap } from 'lucide-react';
import { STATE_META, formatElapsed, resolvedSources, templateOf, useAgent, type DockTab } from '@/lib/agent/agent-context';
import { SCOPE_KIND_LABEL, frameForPath, screenContext } from '@/lib/agent/screens';
import { BLOCKED_STATES, ACTIVE_STATES, type AgentMessage, type AgentTask } from '@/lib/agent/types';
import { resolveOutputs } from '@/lib/agent/templates';
import { useAppContext } from '@/lib/app-context';
import { Button, ClaimTag, EvidenceChip, Pill, ProgressBar } from '../ui';
import { ClarificationPrompt } from './ClarificationPrompt';
import { InlineArtifactCard } from './InlineArtifactCard';
import { cn } from '@/lib/cn';

const time = (at: number) => new Date(at).toISOString().slice(11, 19) + 'Z';

function Message({ m, onOpenArtifacts }: { m: AgentMessage; onOpenArtifacts: () => void }) {
  if (m.from === 'user') {
    return (
      <div className="flex justify-end">
        <p className="max-w-[85%] rounded-lg rounded-br-sm bg-slate-800 text-white px-3 py-2 text-[12.5px] leading-snug">{m.text}</p>
      </div>
    );
  }
  if (m.from === 'system') {
    return <p className="text-center text-[11px] text-text-tertiary px-4"><span className="font-mono text-text-muted mr-1">{time(m.at)}</span>{m.text}</p>;
  }
  return (
    <div className="flex gap-2">
      <span className="mt-0.5 h-6 w-6 shrink-0 rounded-full bg-brand-teal-light text-brand-teal-dark flex items-center justify-center"><Bot className="h-3.5 w-3.5" aria-hidden /></span>
      <div className="min-w-0 flex-1">
        <p className="text-[12.5px] text-text-primary font-medium leading-snug">{m.outputs ? <><Check className="inline h-3.5 w-3.5 text-status-success mr-1 -mt-0.5" aria-hidden />{m.text}</> : m.text}</p>
        {m.outputs && (
          <ul className="mt-1.5 space-y-1.5">
            {m.outputs.map((o) => (
              <li key={o.text} className="text-[12px] text-text-secondary leading-snug">
                <ClaimTag kind={o.kind} className="mr-1 !h-4 !px-1.5 !text-[9px]" />
                {o.text}
                {o.citations?.map((c) => <EvidenceChip key={c} id={c} className="ml-1" />)}
              </li>
            ))}
          </ul>
        )}
        {m.artifactId && <button type="button" onClick={onOpenArtifacts} className="mt-1 text-[12px] text-brand-teal hover:underline">View in working artifacts →</button>}
        <p className="mt-0.5 text-[10px] font-mono text-text-muted">{time(m.at)}</p>
      </div>
    </div>
  );
}

function Plan({ task }: { task: AgentTask }) {
  const t = templateOf(task);
  const resolved = resolvedSources(task);
  const blocked = BLOCKED_STATES.includes(task.state);
  let lastSub: string | undefined;
  return (
    <div className="space-y-4">
      <div>
        <p className="text-[11px] font-semibold uppercase tracking-wider text-text-tertiary">Sources · {resolved}/{t.sources.length} resolved</p>
        <div className="mt-1.5 flex flex-wrap gap-1">
          {t.sources.map((s) => {
            const done = t.checkpoints.slice(0, task.stepIndex).some((c) => c.resolvesSource === s);
            const missing = t.unavailableSources?.includes(s);
            return <Pill key={s} tone={missing ? 'muted' : done ? 'success' : 'neutral'} dot>{s}{missing ? ' · not connected' : ''}</Pill>;
          })}
        </div>
      </div>
      <ol className="space-y-1">
        {t.checkpoints.map((c, i) => {
          const done = i < task.stepIndex;
          const current = i === task.stepIndex && ACTIVE_STATES.includes(task.state);
          const header = c.subtask && c.subtask !== lastSub ? c.subtask : null;
          lastSub = c.subtask ?? lastSub;
          return (
            <li key={c.id}>
              {header && <p className="mt-2 mb-1 text-[11px] font-semibold text-text-secondary">Subtask {header}</p>}
              <div className={cn('rounded-card border px-3 py-2', current ? (blocked ? 'border-amber-300 bg-amber-50/50' : 'border-cyan-300 bg-brand-teal-light/40') : 'border-border-hairline')}>
                <div className="flex items-start gap-2">
                  <span className="mt-0.5 shrink-0">
                    {done ? <Check className="h-4 w-4 text-status-success" aria-label="Completed" />
                      : current && blocked ? <Pause className="h-4 w-4 text-status-warning" aria-label="Blocked" />
                      : current ? <Loader2 className="h-4 w-4 animate-spin text-brand-teal" aria-label="Running" />
                      : <Circle className="h-4 w-4 text-text-muted" aria-label="Pending" />}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-[12.5px] font-medium text-text-primary">Checkpoint {i + 1} · {c.title}</p>
                    <p className="text-[10.5px] font-mono text-text-tertiary truncate" title={c.tool}>{c.tool}</p>
                    {current && !blocked && <ProgressBar value={task.stepElapsed} max={c.durationSec} className="mt-1.5" label={`Checkpoint ${i + 1} progress`} />}
                    {current && blocked && <p className="mt-1 text-[11.5px] text-amber-700">Paused — waiting for your answer above.</p>}
                    {done && (
                      <ul className="mt-1.5 space-y-1">
                        {resolveOutputs(t, i, task.answers).map((o) => (
                          <li key={o.text} className="text-[11.5px] text-text-secondary leading-snug"><ClaimTag kind={o.kind} className="mr-1 !h-4 !px-1.5 !text-[9px]" />{o.text}{o.citations?.map((cid) => <EvidenceChip key={cid} id={cid} className="ml-1" />)}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>
              </div>
            </li>
          );
        })}
      </ol>
      {t.runTraceHref && <Link href={t.runTraceHref} className="inline-block text-[12px] text-brand-teal hover:underline">Open full run trace and logs →</Link>}
      <p className="text-[11px] text-text-muted">Demo run: checkpoint timings are simulated in the browser.</p>
    </div>
  );
}

function EmptyDock() {
  const pathname = usePathname();
  const { openOverlay } = useAgent();
  const ctx = screenContext(frameForPath(pathname));
  return (
    <div className="p-4 space-y-3">
      <p className="text-[13px] font-semibold text-text-primary">No agent task yet</p>
      <p className="text-[12.5px] text-text-secondary">Start from what you are looking at. The agent reads connected systems with read-only access and returns drafts for your review.</p>
      <div className="flex flex-col items-start gap-1.5">
        {ctx.suggestions.map((s) => (
          <button key={s.label} type="button" onClick={() => openOverlay('DELEGATE', { frame: ctx.frame, templateId: s.templateId })} className="inline-flex items-center gap-1.5 h-7 px-2.5 rounded-pill border border-cyan-200 bg-brand-teal-light text-[12px] text-brand-teal-dark hover:bg-cyan-100">
            <Zap className="h-3 w-3" aria-hidden />{s.label}
          </button>
        ))}
      </div>
    </div>
  );
}

export function AgentDock() {
  const pathname = usePathname();
  const frame = frameForPath(pathname);
  const { closeInspector } = useAppContext();
  const { tasks, activeTask: task, now, dockTab, setDockTab, pinned, setPinned, dispatch, openOverlay, openDock } = useAgent();
  const [draft, setDraft] = useState('');
  const [switcher, setSwitcher] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (dockTab === 'CHAT' && scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [task?.messages.length, dockTab]);

  if (!task) return <EmptyDock />;

  const t = templateOf(task);
  const meta = STATE_META[task.state];
  const visibleArtifacts = t.artifacts.filter((a) => task.artifacts[a.id]);
  const gate = t.gates?.find((g) => g.beforeStep === task.stepIndex && BLOCKED_STATES.includes(task.state));
  const active = ACTIVE_STATES.includes(task.state);
  const tabs: Array<{ key: DockTab; label: string }> = [
    { key: 'CHAT', label: 'Conversation' },
    { key: 'PLAN', label: 'Structured plan' },
    { key: 'OUTPUTS', label: `Working artifacts (${visibleArtifacts.length})` },
  ];

  const send = () => {
    if (!draft.trim()) return;
    dispatch({ type: 'USER_MSG', uid: task.uid, text: draft.trim() });
    setDraft('');
  };

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Top bar */}
      <div className="px-4 pt-3 pb-2 border-b border-border-hairline space-y-2">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 relative">
            <button type="button" onClick={() => tasks.length > 1 && setSwitcher((o) => !o)} className={cn('text-left min-w-0', tasks.length > 1 && 'hover:opacity-80')} aria-expanded={tasks.length > 1 ? switcher : undefined}>
              <span className="text-[10.5px] font-semibold uppercase tracking-wider text-text-tertiary flex items-center gap-1">
                <Zap className="h-3 w-3 text-brand-teal" aria-hidden />{task.agent}{tasks.length > 1 && <> · {tasks.length} tasks <ChevronDown className="h-3 w-3" aria-hidden /></>}
              </span>
              <span className="block mt-0.5 text-[13.5px] font-semibold text-text-primary leading-snug"><code className="font-mono text-[12px] text-text-secondary">{task.taskId}</code>: {task.title}</span>
            </button>
            {switcher && (
              <div className="absolute left-0 top-full mt-1 z-10 w-[360px] bg-surface border border-border-hairline rounded-card shadow-lg py-1">
                {tasks.slice().reverse().map((x) => (
                  <button key={x.uid} type="button" onClick={() => { openDock(x.uid); setSwitcher(false); }} className={cn('w-full flex items-center justify-between gap-2 px-3 py-1.5 text-left text-[12.5px] hover:bg-surface-secondary', x.uid === task.uid && 'bg-brand-teal-light/60')}>
                    <span className="truncate"><code className="font-mono text-[11px] text-text-tertiary mr-1">{x.taskId}</code>{x.title}</span>
                    <Pill tone={STATE_META[x.state].tone}>{STATE_META[x.state].label}</Pill>
                  </button>
                ))}
              </div>
            )}
          </div>
          <div className="flex items-center gap-0.5 shrink-0">
            <button type="button" onClick={() => openOverlay('DELEGATE', { frame: frame ?? undefined })} className="p-1 rounded text-text-tertiary hover:bg-surface-secondary" aria-label="New task" title="New task"><Plus className="h-4 w-4" /></button>
            <button type="button" onClick={() => setPinned(!pinned)} className={cn('p-1 rounded hover:bg-surface-secondary', pinned ? 'text-brand-teal' : 'text-text-tertiary')} aria-pressed={pinned} aria-label={pinned ? 'Unpin dock' : 'Pin dock open across pages'} title={pinned ? 'Unpin' : 'Keep open across pages'}>{pinned ? <Pin className="h-4 w-4" /> : <PinOff className="h-4 w-4" />}</button>
            <button type="button" onClick={closeInspector} className="p-1 rounded text-text-tertiary hover:bg-surface-secondary" aria-label="Collapse to run strip" title="Collapse to run strip"><Minimize2 className="h-4 w-4" /></button>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-[11.5px]">
          <Pill tone={meta.tone} dot>{meta.label}</Pill>
          <span className="text-text-tertiary tabular-nums">Step {Math.min(task.stepIndex + (active ? 1 : 0), t.checkpoints.length)}/{t.checkpoints.length}</span>
          <span className="text-text-tertiary tabular-nums">{resolvedSources(task)}/{t.sources.length} sources</span>
          <span className="text-text-tertiary tabular-nums">Elapsed {formatElapsed(task, now)}</span>
          <span className="ml-auto flex items-center gap-1">
            {active && <Button size="sm" variant="ghost" onClick={() => dispatch({ type: 'CANCEL', uid: task.uid })}><Square className="h-3 w-3" /> Cancel</Button>}
            {(task.state === 'CANCELLED' || task.state === 'FAILED') && <Button size="sm" variant="secondary" onClick={() => dispatch({ type: 'RETRY', uid: task.uid })}><RotateCcw className="h-3 w-3" /> Resume</Button>}
          </span>
        </div>
        <details className="group">
          <summary className="cursor-pointer list-none text-[11px] text-text-tertiary hover:text-text-primary">Scope · {task.scope.length} items <ChevronDown className="inline h-3 w-3 group-open:rotate-180 transition-transform" aria-hidden /></summary>
          <ul className="mt-1.5 flex flex-wrap gap-1">
            {task.scope.map((s) => <li key={s.id}><span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded border border-border-hairline bg-surface-secondary text-[11px]"><span className="text-text-tertiary">{SCOPE_KIND_LABEL[s.kind]}:</span> <span className="font-mono text-text-primary">{s.value}</span></span></li>)}
          </ul>
        </details>
        <div role="tablist" className="flex gap-1 -mb-2">
          {tabs.map((x) => (
            <button key={x.key} role="tab" aria-selected={dockTab === x.key} onClick={() => setDockTab(x.key)} className={cn('h-8 px-2 -mb-px border-b-2 text-[12.5px] font-medium whitespace-nowrap', dockTab === x.key ? 'border-brand-teal text-text-primary' : 'border-transparent text-text-tertiary hover:text-text-primary')}>{x.label}</button>
          ))}
        </div>
      </div>

      {/* Body */}
      <div ref={scrollRef} className="flex-1 min-h-0 overflow-y-auto px-4 py-3 space-y-3">
        {gate && <ClarificationPrompt gate={gate} answer={task.answers[gate.id]} onAnswer={(value) => dispatch({ type: 'ANSWER', uid: task.uid, gateId: gate.id, value })} />}
        {dockTab === 'CHAT' && task.messages.map((m) => <Message key={m.id} m={m} onOpenArtifacts={() => setDockTab('OUTPUTS')} />)}
        {dockTab === 'CHAT' && task.state === 'RUNNING' && (
          <p className="flex items-center gap-1.5 text-[12px] text-text-tertiary"><Loader2 className="h-3.5 w-3.5 animate-spin text-brand-teal" aria-hidden /> {t.checkpoints[task.stepIndex]?.title}…</p>
        )}
        {dockTab === 'PLAN' && <Plan task={task} />}
        {dockTab === 'OUTPUTS' && (
          visibleArtifacts.length === 0
            ? <p className="text-[12.5px] text-text-tertiary">Drafts appear here as checkpoints complete. The first one is expected after checkpoint {Math.min(...t.artifacts.map((a) => a.availableAfter))}.</p>
            : visibleArtifacts.map((a) => <InlineArtifactCard key={a.id} task={task} artifactId={a.id} currentFrame={frame} />)
        )}
      </div>

      {/* Footer */}
      <div className="border-t border-border-hairline px-4 py-2.5 space-y-1.5">
        {dockTab === 'CHAT' && (
          <div className="flex items-end gap-2">
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } }}
              rows={1}
              placeholder={active ? 'Redirect the run or add context…' : 'Add a note to this task…'}
              aria-label="Message the agent"
              className="flex-1 resize-none rounded-control border border-border-strong px-2.5 py-1.5 text-[12.5px] focus:outline-none focus:ring-2 focus:ring-brand-teal"
            />
            <Button size="sm" variant="primary" onClick={send} disabled={!draft.trim()} aria-label="Send"><CornerDownLeft className="h-3.5 w-3.5" /></Button>
          </div>
        )}
        <p className="flex items-center gap-1 text-[10.5px] text-text-tertiary"><Lock className="h-3 w-3" aria-hidden /> Read-only: historian, eBR, LIMS, CMMS, QMS · Writes: none (sandbox staging only)</p>
      </div>
    </div>
  );
}
