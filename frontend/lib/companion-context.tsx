'use client';

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';

/** A user-selected screen snapshot, never a verified system-of-record reference. */
export type DisplayContext = {
  kind: 'text' | 'chart';
  label: string;
  page_path: string;
  captured_at: string;
  content: string;
};

/** A verified CMO delivery published as platform evidence; the assistant receives its values server-side. */
export type AttachedDataset = { id: string; label: string; measurements: number; batches: number };

type CompanionState = {
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
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [selection, setSelection] = useState<DisplayContext | null>(null);
  const [busy, setBusy] = useState(false);
  const [datasets, setDatasets] = useState<AttachedDataset[]>([]);
  const attachDataset = useCallback((dataset: AttachedDataset) => {
    setDatasets(current => [...current.filter(d => d.id !== dataset.id), dataset].slice(-5));
    setOpen(true);
  }, []);
  const removeDataset = useCallback((id?: string) => setDatasets(current => id ? current.filter(d => d.id !== id) : []), []);
  const show = useCallback((context?: DisplayContext) => {
    if (context) setSelection(context);
    setOpen(true);
  }, []);
  const close = useCallback(() => setOpen(false), []);
  const clearSelection = useCallback((expected?: DisplayContext) => setSelection(current => !expected || current === expected ? null : current), []);
  const value = useMemo(() => ({ open, expanded, selection, busy, show, close, setExpanded, clearSelection, setBusy, datasets, attachDataset, removeDataset }),
    [open, expanded, selection, busy, show, close, clearSelection, datasets, attachDataset, removeDataset]);
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export const useOptionalCompanion = () => useContext(Context);
export function useCompanion() {
  const context = useOptionalCompanion();
  if (!context) throw new Error('CompanionProvider is missing');
  return context;
}
