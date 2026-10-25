'use client';

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';

export type UserRole = 'MSAT_LEAD' | 'QA_REVIEWER' | 'CLEANROOM_SUPERVISOR' | 'OPERATOR';

export type InspectorEntity = {
  type: 'EVIDENCE' | 'SAMPLE' | 'WORK_ORDER' | 'HYPOTHESIS' | 'AGENT_STEP' | 'RECORD' | 'PROJECT' | 'SCHEDULE_ITEM';
  id: string;
  title?: string;
  sha256?: string;
  sourceFile?: string;
  /** Citation ids (see fixtures CITATIONS) that support this entity. */
  citations?: string[];
  href?: string;
  hrefLabel?: string;
  metadata?: Record<string, string | number>;
};

export interface AppContextState {
  organization: string;
  siteId: string;
  productId: string;
  processId: string;
  campaignId: string;
  activeBatchId: string;
  userRole: UserRole;
  isInspectorOpen: boolean;
  /** The right-hand slot is shared by the agent dock and the evidence inspector. */
  sidePaneTab: SidePaneTab;
  activeInspectorEntity: InspectorEntity | null;
  agentRunningState: {
    isRunning: boolean;
    runId?: string;
    label?: string;
    resolvedSources?: number;
    totalSources?: number;
  };
}

export type SidePaneTab = 'AGENT' | 'EVIDENCE';

type Toast = { id: number; message: string; tone: 'success' | 'info' | 'warning' };

interface AppContextValue extends AppContextState {
  setSite: (siteId: string) => void;
  setRole: (role: UserRole) => void;
  openEvidence: (citationId: string) => void;
  openInspector: (entity: InspectorEntity) => void;
  closeInspector: () => void;
  openAgentPane: () => void;
  setSidePaneTab: (tab: SidePaneTab) => void;
  startRun: (label: string, totalSources?: number) => void;
  stopRun: () => void;
  notify: (message: string, tone?: Toast['tone']) => void;
  toasts: Toast[];
  dismissToast: (id: number) => void;
}

export const ROLE_LABELS: Record<UserRole, string> = {
  MSAT_LEAD: 'MSAT Lead',
  QA_REVIEWER: 'QA Reviewer',
  CLEANROOM_SUPERVISOR: 'Cleanroom Supervisor',
  OPERATOR: 'Operator',
};

export const ROLE_PEOPLE: Record<UserRole, string> = {
  MSAT_LEAD: 'Alex Rivera',
  QA_REVIEWER: 'Priya Natarajan',
  CLEANROOM_SUPERVISOR: 'Marcus Bell',
  OPERATOR: 'Taylor Reed',
};

export const SITES = ['Mesa Site (UP-01)', 'Durham Site', 'Basel'];

const STORAGE_KEY = 'mos.context.v1';
const Ctx = createContext<AppContextValue | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AppContextState>({
    organization: 'Aster Biologics',
    siteId: SITES[0],
    productId: 'AB-mAb-014',
    processId: 'UP-01',
    campaignId: 'CMP-26-10',
    activeBatchId: 'MES-26073',
    userRole: 'MSAT_LEAD',
    isInspectorOpen: false,
    sidePaneTab: 'EVIDENCE',
    activeInspectorEntity: null,
    agentRunningState: { isRunning: false },
  });
  const [toasts, setToasts] = useState<Toast[]>([]);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
      if (saved.userRole || saved.siteId) setState((s) => ({ ...s, ...pick(saved) }));
    } catch {
      /* ignore unreadable local state */
    }
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ userRole: state.userRole, siteId: state.siteId }));
    } catch {
      /* storage may be unavailable */
    }
  }, [state.userRole, state.siteId]);

  useEffect(() => () => { if (timer.current) clearInterval(timer.current); }, []);

  const notify = useCallback((message: string, tone: Toast['tone'] = 'success') => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, message, tone }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4200);
  }, []);

  const stopRun = useCallback(() => {
    if (timer.current) clearInterval(timer.current);
    timer.current = null;
    setState((s) => ({ ...s, agentRunningState: { isRunning: false } }));
  }, []);

  const startRun = useCallback((label: string, totalSources = 8) => {
    if (timer.current) clearInterval(timer.current);
    setState((s) => ({ ...s, agentRunningState: { isRunning: true, runId: 'RUN-2026-1043', label, resolvedSources: 0, totalSources } }));
    timer.current = setInterval(() => {
      setState((s) => {
        const r = s.agentRunningState;
        const next = (r.resolvedSources ?? 0) + 1;
        if (next > (r.totalSources ?? totalSources)) {
          if (timer.current) clearInterval(timer.current);
          timer.current = null;
          setTimeout(() => notify(`${label} finished. Results need human review before use.`, 'info'), 0);
          return { ...s, agentRunningState: { isRunning: false } };
        }
        return { ...s, agentRunningState: { ...r, resolvedSources: next } };
      });
    }, 900);
  }, [notify]);

  const value = useMemo<AppContextValue>(() => ({
    ...state,
    toasts,
    setSite: (siteId) => setState((s) => ({ ...s, siteId })),
    setRole: (userRole) => setState((s) => ({ ...s, userRole })),
    openEvidence: (id) => setState((s) => ({ ...s, isInspectorOpen: true, sidePaneTab: 'EVIDENCE', activeInspectorEntity: { type: 'EVIDENCE', id } })),
    openInspector: (entity) => setState((s) => ({ ...s, isInspectorOpen: true, sidePaneTab: 'EVIDENCE', activeInspectorEntity: entity })),
    closeInspector: () => setState((s) => ({ ...s, isInspectorOpen: false })),
    openAgentPane: () => setState((s) => ({ ...s, isInspectorOpen: true, sidePaneTab: 'AGENT' })),
    setSidePaneTab: (sidePaneTab) => setState((s) => ({ ...s, isInspectorOpen: true, sidePaneTab })),
    startRun,
    stopRun,
    notify,
    dismissToast: (id) => setToasts((t) => t.filter((x) => x.id !== id)),
  }), [state, toasts, startRun, stopRun, notify]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

function pick(saved: Partial<AppContextState>) {
  const out: Partial<AppContextState> = {};
  if (saved.userRole && saved.userRole in ROLE_LABELS) out.userRole = saved.userRole;
  if (saved.siteId && SITES.includes(saved.siteId)) out.siteId = saved.siteId;
  return out;
}

export function useAppContext() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useAppContext must be used inside <AppProvider>');
  return ctx;
}
