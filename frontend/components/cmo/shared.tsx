'use client';

import { useState } from 'react';
import { Pill } from '@/components/ui';
import { type Measurement } from '@/lib/cmo-api';

export function statusPill(status: Measurement['status']) {
  const map = { needs_review: ['warning', 'To check'], auto_accepted: ['success', 'Verified'], accepted: ['success', 'Accepted'],
    corrected: ['info', 'Corrected'], rejected: ['muted', 'Rejected'] } as const;
  const [tone, label] = map[status];
  return <Pill tone={tone} dot>{label}</Pill>;
}

export const plural = (n: number, word: string, many = word + 's') => `${n.toLocaleString()} ${n === 1 ? word : many}`;

/** A button that asks for a short reason inline before acting. Used only where a reason matters. */
export function ReasonButton({ label, placeholder, onConfirm, danger }: { label: string; placeholder: string; onConfirm: (reason: string) => Promise<void> | void; danger?: boolean }) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState('');
  const base = 'h-7 rounded-control border px-2.5 text-xs font-medium';
  if (!open) return <button className={`${base} ${danger ? 'border-red-200 text-status-critical hover:bg-status-critical-bg' : 'border-border-strong text-text-secondary hover:bg-surface-secondary'}`} onClick={() => setOpen(true)}>{label}</button>;
  return (
    <form className="flex items-center gap-1" onSubmit={async e => { e.preventDefault(); if (!reason.trim()) return; await onConfirm(reason.trim()); setOpen(false); setReason(''); }}>
      <input autoFocus value={reason} onChange={e => setReason(e.target.value)} placeholder={placeholder} aria-label={placeholder} className="h-7 w-56 rounded-control border border-border-strong px-2 text-xs" />
      <button type="submit" disabled={!reason.trim()} className={`${base} border-border-strong disabled:opacity-40`}>{label}</button>
      <button type="button" className="px-1 text-xs text-text-tertiary" onClick={() => setOpen(false)}>Cancel</button>
    </form>
  );
}
