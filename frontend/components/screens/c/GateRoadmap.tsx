'use client';

import { Check, X } from 'lucide-react';
import { cn } from '@/lib/cn';

export type GateState = 'done' | 'active' | 'blocked' | 'pending';
export const GATE_NAMES = ['G0 Feasibility', 'G1 Process & analytics', 'G2 Engineering & CPP dossier', 'G3 Engineering run', 'G4 PPQ readiness'];

const STATE_LABEL: Record<GateState, string> = { done: 'cleared', active: 'in progress', blocked: 'blocked', pending: 'not started' };

/** Gates 0–4 as a compact horizontal roadmap. */
export function GateRoadmap({ gates, className }: { gates: GateState[]; className?: string }) {
  return (
    <ol className={cn('flex items-center', className)} aria-label="Gate roadmap">
      {gates.map((g, i) => (
        <li key={i} className="flex items-center" title={`${GATE_NAMES[i]} · ${STATE_LABEL[g]}`}>
          <span className="sr-only">{GATE_NAMES[i]}: {STATE_LABEL[g]}</span>
          <span
            aria-hidden
            className={cn(
              'h-5 w-5 rounded-full border flex items-center justify-center text-[10px] font-semibold tabular-nums',
              g === 'done' && 'bg-brand-teal border-brand-teal text-white',
              g === 'active' && 'bg-brand-teal-light border-brand-teal text-brand-teal-dark',
              g === 'blocked' && 'bg-status-critical-bg border-status-critical text-status-critical',
              g === 'pending' && 'bg-surface border-border-strong text-text-muted',
            )}
          >
            {g === 'done' ? <Check className="h-3 w-3" /> : g === 'blocked' ? <X className="h-3 w-3" /> : i}
          </span>
          {i < gates.length - 1 && <span aria-hidden className={cn('h-px w-4', g === 'done' ? 'bg-brand-teal' : 'bg-border-strong')} />}
        </li>
      ))}
    </ol>
  );
}
