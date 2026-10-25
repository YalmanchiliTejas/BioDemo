'use client';

import Link from 'next/link';
import { Loader2, Square } from 'lucide-react';
import { useAppContext } from '@/lib/app-context';
import { ProgressBar } from '../ui';

/** Appears only while a background agent run is computing. */
export function RunStrip() {
  const { agentRunningState: r, stopRun } = useAppContext();
  if (!r.isRunning) return null;
  const done = r.resolvedSources ?? 0;
  const total = r.totalSources ?? 1;
  return (
    <div className="h-10 shrink-0 flex items-center gap-4 px-4 border-t border-border-hairline bg-surface text-[12.5px]" role="status" aria-live="polite">
      <Loader2 className="h-4 w-4 animate-spin text-brand-teal" aria-hidden />
      <span className="font-medium text-text-primary truncate">{r.label}</span>
      <code className="hidden sm:inline text-[11px] font-mono text-text-tertiary">{r.runId}</code>
      <div className="hidden md:flex items-center gap-2 w-56">
        <ProgressBar value={done} max={total} label="Sources resolved" />
        <span className="text-text-tertiary tabular-nums whitespace-nowrap">{done}/{total} sources</span>
      </div>
      <span className="hidden lg:inline text-text-tertiary">Read-only · results will wait for your review</span>
      <div className="ml-auto flex items-center gap-2">
        <Link href="/runs/RUN-2026-1042" className="text-brand-teal hover:underline">View trace</Link>
        <button onClick={stopRun} className="inline-flex items-center gap-1 h-7 px-2 rounded-control border border-border-strong text-text-secondary hover:bg-surface-secondary">
          <Square className="h-3 w-3" aria-hidden /> Stop
        </button>
      </div>
    </div>
  );
}
