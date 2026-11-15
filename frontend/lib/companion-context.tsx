'use client';

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';
import type { TaskContext } from './assistant-workflows';

/** A user-selected screen snapshot, never a verified system-of-record reference. */
export type DisplayContext = {
  kind: 'text' | 'chart';
  label: string;
  page_path: string;
  captured_at: string;
  content: string;
};

/** A verified CDMO delivery published as platform evidence; the assistant receives its values server-side. */
export type AttachedDataset = { id: string; label: string; measurements: number; batches: number };

type CompanionState = {
  view: 'chat' | 'work' | 'routines';
  setView: (view: 'chat' | 'work' | 'routines') => void;
  taskContext: TaskContext | null;
  showWork: (context: TaskContext) => void;
  datasets: AttachedDataset[];
  attachDataset: (dataset: AttachedDataset) => void;
  removeDataset: (id?: string) => void;
  open: boolean;
  expanded: boolean;
  selection: DisplayContext | null;
  busy: boolean;
  show: (selection?: DisplayContext) => void;
  close: () => void;
  setExpanded: (expanded: boolean) => void;
  clearSelection: (expected?: DisplayContext) => void;
  setBusy: (busy: boolean) => void;
};

const Context = createContext<CompanionState | null>(null);

export function CompanionProvider({ children }: { children: ReactNode }) {
  const [view, setView] = useState<'chat' | 'work' | 'routines'>('chat');
  const [taskContext, setTaskContext] = useState<TaskContext | null>(null);
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [selection, setSelection] = useState<DisplayContext | null>(null);
  const [busy, setBusy] = useState(false);
  const [datasets, setDatasets] = useState<AttachedDataset[]>([]);
  const attachDataset = useCallback((dataset: AttachedDataset) => {
    setDatasets(current => [...current.filter(d => d.id !== dataset.id), dataset].slice(-5));
    setOpen(true);
    setView('chat');
  }, []);
  const removeDataset = useCallback((id?: string) => setDatasets(current => id ? current.filter(d => d.id !== id) : []), []);
  const show = useCallback((context?: DisplayContext) => {
    if (context) { setSelection(context); setView('chat'); }
    setOpen(true);
  }, []);
  const showWork = useCallback((context: TaskContext) => { setTaskContext(context); setView('work'); setOpen(true); }, []);
  const close = useCallback(() => setOpen(false), []);
  const clearSelection = useCallback((expected?: DisplayContext) => setSelection(current => !expected || current === expected ? null : current), []);
  const value = useMemo(() => ({ open, expanded, selection, busy, show, close, setExpanded, clearSelection, setBusy, datasets, attachDataset, removeDataset, view, setView, taskContext, showWork }),
    [open, expanded, selection, busy, show, close, clearSelection, datasets, attachDataset, removeDataset, view, taskContext, showWork]);
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export const useOptionalCompanion = () => useContext(Context);
export function useCompanion() {
  const context = useOptionalCompanion();
  if (!context) throw new Error('CompanionProvider is missing');
  return context;
}
