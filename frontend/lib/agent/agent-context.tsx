'use client';

import { createContext, useCallback, useContext, useEffect, useMemo, useReducer, useRef, useState, type ReactNode } from 'react';
import { ROLE_PEOPLE, useAppContext, type UserRole } from '@/lib/app-context';
import { TEMPLATE_BY_ID, resolveOutputs } from './templates';
import { ACTIVE_STATES, type AgentMessage, type AgentTask, type ComposerMode, type ScopeChip, type TaskTemplate } from './types';

export type DockTab = 'CHAT' | 'PLAN' | 'OUTPUTS';
export type OverlayPreset = { templateId?: string; scope?: ScopeChip[]; prompt?: string; frame?: string };

type State = { tasks: AgentTask[]; activeUid: string | null; dismissed: string[] };

type Action =
  | { type: 'RESTORE'; state: State }
  | { type: 'LAUNCH'; task: AgentTask }
  | { type: 'TICK'; now: number }
  | { type: 'SET_ACTIVE'; uid: string }
  | { type: 'ANSWER'; uid: string; gateId: string; value: string; now: number }
  | { type: 'CANCEL'; uid: string; now: number }
  | { type: 'RETRY'; uid: string; now: number }
  | { type: 'USER_MSG'; uid: string; text: string; now: number }
  | { type: 'INSERT'; uid: string; artifactId: string; frame: string; now: number }
  | { type: 'REMOVE_INSERT'; uid: string; artifactId: string; frame: string }
  | { type: 'PIN'; uid: string; artifactId: string; now: number }
  | { type: 'REVISE'; uid: string; artifactId: string; note: string; now: number }
  | { type: 'SELECT'; uid: string; key: string; value: string }
  | { type: 'ROUTE'; uid: string; now: number }
  | { type: 'SIGN'; uid: string; role: UserRole; meaning: string; now: number }
  | { type: 'DISPATCH'; uid: string; now: number }
  | { type: 'MONITOR'; uid: string; now: number }
  | { type: 'DISMISS'; uid: string };

let seq = 0;
const mid = () => `m${Date.now().toString(36)}${(seq++).toString(36)}`;
const msg = (from: AgentMessage['from'], text: string, at: number, extra?: Partial<AgentMessage>): AgentMessage => ({ id: mid(), at, from, text, ...extra });

export const templateOf = (t: AgentTask): TaskTemplate => TEMPLATE_BY_ID[t.templateId];

function blockingGate(task: AgentTask) {
  const t = templateOf(task);
  return t.gates?.find((g) => g.beforeStep === task.stepIndex && (!task.answers[g.id] || g.options.find((o) => o.value === task.answers[g.id])?.holds));
}

function tickTask(task: AgentTask, now: number): AgentTask {
  if (task.state === 'QUEUED') {
    return { ...task, state: 'RUNNING', messages: [...task.messages, msg('system', 'Started. Reading connected sources with read-only credentials.', now)] };
  }
  if (task.state !== 'RUNNING') return task;
  const t = templateOf(task);
  const gate = blockingGate(task);
  if (gate) {
    return {
      ...task,
      state: gate.kind === 'PERMISSION' ? 'WAITING_ON_PERMISSION' : 'NEEDS_USER_INPUT',
      messages: [...task.messages, msg('agent', gate.kind === 'PERMISSION' ? `Waiting on access: ${gate.question}` : `I need a decision before continuing: ${gate.question}`, now)],
    };
  }
  const cp = t.checkpoints[task.stepIndex];
  const elapsed = task.stepElapsed + 1;
  if (elapsed < cp.durationSec) return { ...task, stepElapsed: elapsed };

  const done = task.stepIndex + 1;
  const messages = [...task.messages, msg('agent', cp.title, now, { outputs: resolveOutputs(t, task.stepIndex, task.answers) })];
  const artifacts = { ...task.artifacts };
  t.artifacts.filter((a) => a.availableAfter === done).forEach((a) => {
    artifacts[a.id] = { insertedInto: [], pinned: false };
    messages.push(msg('agent', a.id === 'gate' ? `${a.title} staged for review.` : `Draft ready: ${a.title}`, now, { artifactId: a.id }));
  });
  const finished = done >= t.checkpoints.length;
  if (finished) messages.push(msg('system', t.review ? 'All checkpoints complete. Proposal needs human review — nothing has been applied to any system.' : 'All checkpoints complete. Findings need your review before anyone relies on them.', now));
  return { ...task, stepIndex: done, stepElapsed: 0, artifacts, messages, state: finished ? 'PROPOSAL_NEEDS_REVIEW' : 'RUNNING', endedAt: finished ? now : undefined };
}

function update(state: State, uid: string, fn: (t: AgentTask) => AgentTask): State {
  return { ...state, tasks: state.tasks.map((t) => (t.uid === uid ? fn(t) : t)) };
}

function reducer(state: State, a: Action): State {
  switch (a.type) {
    case 'RESTORE':
      return a.state;
    case 'LAUNCH':
      return { tasks: [...state.tasks, a.task], activeUid: a.task.uid, dismissed: state.dismissed };
    case 'TICK':
      return { ...state, tasks: state.tasks.map((t) => tickTask(t, a.now)) };
    case 'SET_ACTIVE':
      return { ...state, activeUid: a.uid };
    case 'DISMISS':
      return { ...state, dismissed: [...state.dismissed, a.uid] };
    case 'ANSWER':
      return update(state, a.uid, (t) => {
        const gate = templateOf(t).gates?.find((g) => g.id === a.gateId);
        const opt = gate?.options.find((o) => o.value === a.value);
        if (!gate || !opt) return t;
        const messages = [...t.messages, msg('user', opt.label, a.now)];
        if (opt.holds) {
          messages.push(msg('agent', opt.note ?? 'Holding here until this is resolved.', a.now));
          return { ...t, answers: { ...t.answers, [gate.id]: a.value }, messages };
        }
        messages.push(msg('agent', 'Recorded in the run log. Continuing.', a.now));
        return { ...t, answers: { ...t.answers, [gate.id]: a.value }, state: 'RUNNING', messages };
      });
    case 'CANCEL':
      return update(state, a.uid, (t) => ({ ...t, state: 'CANCELLED', endedAt: a.now, messages: [...t.messages, msg('system', `Cancelled by user after ${t.stepIndex} of ${templateOf(t).checkpoints.length} checkpoints. Partial results are kept and can be resumed.`, a.now)] }));
    case 'RETRY':
      return update(state, a.uid, (t) => ({ ...t, state: 'QUEUED', endedAt: undefined, stepElapsed: 0, messages: [...t.messages, msg('system', `Resuming from checkpoint ${t.stepIndex + 1}. Completed checkpoints are reused, not recomputed.`, a.now)] }));
    case 'USER_MSG':
      return update(state, a.uid, (t) => {
        const live = ACTIVE_STATES.includes(t.state);
        const reply = live
          ? 'Noted in the run log. It applies from the next checkpoint; completed checkpoints are unchanged. Use the plan tab to see where that is.'
          : 'Noted. This task has finished, so the note is attached to its record. Start a new task from the composer to act on it.';
        return { ...t, messages: [...t.messages, msg('user', a.text, a.now), msg('agent', reply, a.now)] };
      });
    case 'INSERT':
      return update(state, a.uid, (t) => {
        const cur = t.artifacts[a.artifactId] ?? { insertedInto: [], pinned: false };
        if (cur.insertedInto.includes(a.frame)) return t;
        const title = templateOf(t).artifacts.find((x) => x.id === a.artifactId)?.title;
        return { ...t, artifacts: { ...t.artifacts, [a.artifactId]: { ...cur, insertedInto: [...cur.insertedInto, a.frame] } }, messages: [...t.messages, msg('system', `${title} inserted into ${a.frame} as an unreviewed draft.`, a.now)] };
      });
    case 'REMOVE_INSERT':
      return update(state, a.uid, (t) => {
        const cur = t.artifacts[a.artifactId];
        if (!cur) return t;
        return { ...t, artifacts: { ...t.artifacts, [a.artifactId]: { ...cur, insertedInto: cur.insertedInto.filter((f) => f !== a.frame) } } };
      });
    case 'PIN':
      return update(state, a.uid, (t) => {
        const cur = t.artifacts[a.artifactId] ?? { insertedInto: [], pinned: false };
        const title = templateOf(t).artifacts.find((x) => x.id === a.artifactId)?.title;
        return { ...t, artifacts: { ...t.artifacts, [a.artifactId]: { ...cur, pinned: true } }, messages: [...t.messages, msg('system', `${title} pinned to workspace UP-01 Yield Consistency (WORK-01).`, a.now)] };
      });
    case 'REVISE':
      return update(state, a.uid, (t) => {
        const cur = t.artifacts[a.artifactId] ?? { insertedInto: [], pinned: false };
        return {
          ...t,
          artifacts: { ...t.artifacts, [a.artifactId]: { ...cur, revisionNote: a.note } },
          review: a.artifactId === 'gate' ? { ...t.review, revisionNote: a.note } : t.review,
          messages: [...t.messages, msg('user', `Revision requested: ${a.note}`, a.now), msg('agent', 'Revision request recorded against this draft. In this demo the draft is not regenerated; the note travels with it to review.', a.now)],
        };
      });
    case 'SELECT':
      return update(state, a.uid, (t) => ({ ...t, selections: { ...t.selections, [a.key]: a.value } }));
    case 'ROUTE':
      return update(state, a.uid, (t) => ({ ...t, review: { ...t.review, routedAt: a.now }, messages: [...t.messages, msg('system', `${templateOf(t).review?.proposalId} routed to REV-01 for sign-off. Status: Review required.`, a.now)] }));
    case 'SIGN':
      return update(state, a.uid, (t) => ({
        ...t,
        state: 'APPROVED_FOR_HANDOFF',
        review: { ...t.review, signedBy: { name: ROLE_PEOPLE[a.role], role: a.role, at: a.now, meaning: a.meaning } },
        messages: [...t.messages, msg('system', `Approved for handoff by ${ROLE_PEOPLE[a.role]} (${a.meaning}). Simulated signature stored in this browser only.`, a.now)],
      }));
    case 'DISPATCH':
      return update(state, a.uid, (t) => ({ ...t, state: 'SENT_TO_EXTERNAL_SYSTEM', review: { ...t.review, dispatchedAt: a.now }, messages: [...t.messages, msg('system', `Handoff to ${templateOf(t).review?.systemOfRecord} queue simulated. Nothing was sent; the record owner applies the change in the system of record.`, a.now)] }));
    case 'MONITOR':
      return update(state, a.uid, (t) => ({ ...t, state: 'MONITORING_ACTIVE', review: { ...t.review, monitoringSince: a.now }, messages: [...t.messages, msg('system', `Outcome monitor set: ${templateOf(t).review?.monitor}`, a.now)] }));
  }
}

interface AgentContextValue {
  tasks: AgentTask[];
  activeTask: AgentTask | null;
  now: number;
  dockTab: DockTab;
  setDockTab: (t: DockTab) => void;
  pinned: boolean;
  setPinned: (p: boolean) => void;
  overlay: { open: boolean; mode: ComposerMode; preset?: OverlayPreset };
  openOverlay: (mode: ComposerMode, preset?: OverlayPreset) => void;
  closeOverlay: () => void;
  setOverlayMode: (mode: ComposerMode) => void;
  launch: (templateId: string, opts: { mode: ComposerMode; prompt: string; scope: ScopeChip[]; frame: string; href: string }) => void;
  openDock: (uid?: string) => void;
  dispatch: (a: DistributiveOmit<Action, 'now'>) => void;
  isDismissed: (uid: string) => boolean;
}

type DistributiveOmit<T, K extends PropertyKey> = T extends unknown ? Omit<T, K> : never;

const Ctx = createContext<AgentContextValue | null>(null);
const STORAGE_KEY = 'mos.agent.v1';

export function AgentProvider({ children }: { children: ReactNode }) {
  const { openAgentPane, userRole } = useAppContext();
  const [state, rawDispatch] = useReducer(reducer, { tasks: [], activeUid: null, dismissed: [] });
  const [now, setNow] = useState(() => Date.now());
  const [dockTab, setDockTab] = useState<DockTab>('PLAN');
  const [pinned, setPinned] = useState(false);
  const [overlay, setOverlay] = useState<AgentContextValue['overlay']>({ open: false, mode: 'FIND' });
  const restored = useRef(false);

  useEffect(() => {
    try {
      const saved = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || 'null') as State | null;
      if (saved?.tasks?.length) rawDispatch({ type: 'RESTORE', state: { ...saved, tasks: saved.tasks.filter((t) => TEMPLATE_BY_ID[t.templateId]) } });
    } catch {
      /* ignore unreadable session state */
    }
    restored.current = true;
  }, []);

  useEffect(() => {
    if (!restored.current) return;
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch {
      /* storage may be unavailable */
    }
  }, [state]);

  const live = state.tasks.some((t) => t.state === 'QUEUED' || t.state === 'RUNNING');
  const anyOpen = state.tasks.some((t) => ACTIVE_STATES.includes(t.state));
  useEffect(() => {
    if (!anyOpen) return;
    const id = setInterval(() => {
      const n = Date.now();
      setNow(n);
      if (live) rawDispatch({ type: 'TICK', now: n });
    }, 1000);
    return () => clearInterval(id);
  }, [live, anyOpen]);

  const dispatch = useCallback((a: DistributiveOmit<Action, 'now'>) => {
    const n = Date.now();
    setNow(n);
    rawDispatch({ ...a, now: n } as Action);
  }, []);

  const openDock = useCallback((uid?: string) => {
    if (uid) rawDispatch({ type: 'SET_ACTIVE', uid });
    openAgentPane();
  }, [openAgentPane]);

  const launch = useCallback<AgentContextValue['launch']>((templateId, o) => {
    const t = TEMPLATE_BY_ID[templateId];
    const n = Date.now();
    const prior = state.tasks.filter((x) => x.templateId === templateId).length;
    const task: AgentTask = {
      uid: `${templateId}-${n.toString(36)}`,
      templateId,
      taskId: prior ? `${t.taskId}.${prior + 1}` : t.taskId,
      title: t.title,
      agent: t.agent,
      mode: o.mode,
      prompt: o.prompt,
      scope: o.scope,
      originFrame: o.frame,
      originHref: o.href,
      requesterRole: userRole,
      state: 'QUEUED',
      stepIndex: 0,
      stepElapsed: 0,
      startedAt: n,
      answers: {},
      selections: {},
      messages: [msg('user', o.prompt, n), msg('system', `Queued as ${prior ? `${t.taskId}.${prior + 1}` : t.taskId} · ${t.agent} · read-only access.`, n)],
      artifacts: {},
      review: {},
    };
    setNow(n);
    rawDispatch({ type: 'LAUNCH', task });
    setDockTab(o.mode === 'ASK' ? 'CHAT' : 'PLAN');
    setOverlay((s) => ({ ...s, open: false }));
    openAgentPane();
  }, [state.tasks, userRole, openAgentPane]);

  const value = useMemo<AgentContextValue>(() => ({
    tasks: state.tasks,
    activeTask: state.tasks.find((t) => t.uid === state.activeUid) ?? state.tasks[state.tasks.length - 1] ?? null,
    now,
    dockTab,
    setDockTab,
    pinned,
    setPinned,
    overlay,
    openOverlay: (mode, preset) => setOverlay({ open: true, mode, preset }),
    closeOverlay: () => setOverlay((s) => ({ ...s, open: false })),
    setOverlayMode: (mode) => setOverlay((s) => ({ ...s, mode })),
    launch,
    openDock,
    dispatch,
    isDismissed: (uid) => state.dismissed.includes(uid),
  }), [state, now, dockTab, pinned, overlay, launch, openDock, dispatch]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAgent() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useAgent must be used inside <AgentProvider>');
  return ctx;
}

/* ------------------------------------------------------------------ Selectors */

export function resolvedSources(task: AgentTask) {
  const t = templateOf(task);
  return t.checkpoints.slice(0, task.stepIndex).filter((c) => c.resolvesSource).length;
}

export function formatElapsed(task: AgentTask, now: number) {
  const s = Math.max(0, Math.floor(((task.endedAt ?? now) - task.startedAt) / 1000));
  return `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, '0')}s`;
}

export const STATE_META: Record<AgentTask['state'], { label: string; tone: 'neutral' | 'success' | 'warning' | 'critical' | 'info' | 'brand' | 'muted' }> = {
  READY: { label: 'Ready', tone: 'neutral' },
  SCOPING_PLAN_PREVIEW: { label: 'Plan preview', tone: 'neutral' },
  QUEUED: { label: 'Queued', tone: 'neutral' },
  RUNNING: { label: 'Running', tone: 'info' },
  NEEDS_USER_INPUT: { label: 'Needs your input', tone: 'warning' },
  WAITING_ON_PERMISSION: { label: 'Waiting on access', tone: 'warning' },
  PROPOSAL_NEEDS_REVIEW: { label: 'Review required', tone: 'brand' },
  APPROVED_FOR_HANDOFF: { label: 'Approved for handoff', tone: 'success' },
  SENT_TO_EXTERNAL_SYSTEM: { label: 'Handoff simulated', tone: 'success' },
  MONITORING_ACTIVE: { label: 'Monitoring outcome', tone: 'success' },
  FAILED: { label: 'Failed', tone: 'critical' },
  CANCELLED: { label: 'Cancelled', tone: 'muted' },
};
