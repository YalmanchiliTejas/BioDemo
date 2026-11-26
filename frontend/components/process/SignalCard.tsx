'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { ArrowUpRight, Radar } from 'lucide-react';
import { Pill } from '@/components/ui';
import { getSignal, KIND_LABEL, SEVERITY_TONE, type Signal } from '@/lib/signals-api';

/** Shown on an assistant turn the system started for a deviation signal: what fired, and where to act on it. */
export function SignalCard({ id }: { id: string }) {
  const [signal, setSignal] = useState<Signal | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let alive = true;
    getSignal(id).then(s => { if (alive) setSignal(s); }).catch(e => { if (alive) setError(String((e as Error).message ?? e)); });
    return () => { alive = false; };
  }, [id]);
  return <div className="mb-3 rounded-card border border-border-hairline bg-surface p-3 text-xs" aria-label={`Signal ${id}`}>
    <div className="flex flex-wrap items-center justify-between gap-2">
      <p className="flex items-center gap-1.5 font-medium text-text-secondary"><Radar size={14} className="text-brand-teal" />Started automatically for signal {id}</p>
      <Link href={`/signals/?id=${encodeURIComponent(id)}`} className="inline-flex items-center gap-1 text-brand-teal">Open signal<ArrowUpRight size={13} /></Link>
    </div>
    {error ? <p className="mt-1.5 text-text-tertiary">Signal details unavailable: {error}</p>
      : !signal ? <p className="mt-1.5 text-text-tertiary">Loading signal…</p>
      : <p className="mt-1.5 flex flex-wrap items-center gap-2 text-text-primary"><Pill tone={SEVERITY_TONE[signal.severity]} dot>{signal.severity}</Pill>
          <span>{signal.rule}</span><span className="text-text-tertiary">{KIND_LABEL[signal.kind] ?? signal.kind}{signal.subject ? ` · ${signal.subject.kind} ${signal.subject.id}` : ''} · {signal.status.replace('_', ' ')}</span></p>}
    <p className="mt-1.5 text-text-tertiary">The assistant gathers evidence and proposes next steps; opening a case or an investigation is your decision.</p>
  </div>;
}
