'use client';

import { Loader2, Pause, ShieldCheck, X, Zap } from 'lucide-react';
import { STATE_META, formatElapsed, resolvedSources, templateOf, useAgent } from '@/lib/agent/agent-context';
import { ACTIVE_STATES, BLOCKED_STATES } from '@/lib/agent/types';
import { useAppContext } from '@/lib/app-context';

/** Persists across route changes whenever the dock is collapsed and a task needs attention. */
export function AgentBottomRunStrip() {
  const { isInspectorOpen, sidePaneTab } = useAppContext();
  const { tasks, activeTask, now, openDock, dispatch, isDismissed } = useAgent();
  if (isInspectorOpen && sidePaneTab === 'AGENT') return null;

  const visible = tasks.filter((t) => !isDismissed(t.uid) && t.state !== 'CANCELLED');
  if (visible.length === 0) return null;
  // Prefer the task that most needs attention: blocked, then running, then the active one.
  const task = visible.find((t) => BLOCKED_STATES.includes(t.state)) ?? visible.find((t) => ACTIVE_STATES.includes(t.state)) ?? (activeTask && visible.includes(activeTask) ? activeTask : visible[visible.length - 1]);
  const t = templateOf(task);
  const active = ACTIVE_STATES.includes(task.state);
  const blocked = BLOCKED_STATES.includes(task.state);
  const step = Math.min(task.stepIndex + (active ? 1 : 0), t.checkpoints.length);
  const others = visible.filter((x) => x.uid !== task.uid && ACTIVE_STATES.includes(x.state)).length;

  return (
    <div className="h-10 shrink-0 w-full bg-slate-900 text-white z-40 px-4 md:px-6 flex items-center gap-3 text-[12.5px]" role="status" aria-live="polite">
      {blocked ? <Pause className="h-4 w-4 text-amber-300 shrink-0" aria-hidden /> : active ? <Loader2 className="h-4 w-4 animate-spin text-cyan-300 shrink-0" aria-hidden /> : <ShieldCheck className="h-4 w-4 text-emerald-300 shrink-0" aria-hidden />}
      <span className="flex items-center gap-1 font-medium truncate"><Zap className="h-3.5 w-3.5 text-cyan-300 shrink-0" aria-hidden />{task.agent}</span>
      <code className="hidden sm:inline text-[11px] font-mono text-slate-400">{task.taskId}</code>
      <span className="truncate text-slate-200">
        {blocked ? `${STATE_META[task.state].label} · Step ${step}/${t.checkpoints.length}` : active ? `Step ${step}/${t.checkpoints.length}: ${t.checkpoints[task.stepIndex]?.short ?? ''}` : STATE_META[task.state].label}
      </span>
      <span className="hidden md:inline text-slate-400 tabular-nums whitespace-nowrap">{resolvedSources(task)}/{t.sources.length} sources resolved</span>
      <span className="hidden lg:inline text-slate-400 tabular-nums whitespace-nowrap">{formatElapsed(task, now)}</span>
      {others > 0 && <span className="hidden lg:inline text-slate-400">+{others} more running</span>}
      <div className="ml-auto flex items-center gap-2 shrink-0">
        <button type="button" onClick={() => openDock(task.uid)} className="h-7 px-2.5 rounded-control bg-white/10 hover:bg-white/20 font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-300">
          {blocked ? 'Answer in dock' : 'Inspect dock'}
        </button>
        {active ? (
          <button type="button" onClick={() => dispatch({ type: 'CANCEL', uid: task.uid })} className="h-7 px-2 rounded-control text-slate-300 hover:text-white hover:bg-white/10">Cancel</button>
        ) : (
          <button type="button" onClick={() => dispatch({ type: 'DISMISS', uid: task.uid })} className="p-1 rounded text-slate-400 hover:text-white hover:bg-white/10" aria-label="Hide from run strip"><X className="h-3.5 w-3.5" /></button>
        )}
      </div>
    </div>
  );
}
