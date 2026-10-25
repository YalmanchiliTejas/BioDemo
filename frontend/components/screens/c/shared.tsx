'use client';

import { Check } from 'lucide-react';
import { cn } from '@/lib/cn';

/** Horizontal stage tracker. Stages before `current` are done; `current` is active. */
export function StageTracker({ stages, current, className, label }: { stages: string[]; current: number; className?: string; label?: string }) {
  return (
    <ol className={cn('flex flex-wrap items-center gap-y-2', className)} aria-label={label ?? 'Stage progress'}>
      {stages.map((s, i) => {
        const done = i < current;
        const active = i === current;
        return (
          <li key={s} className="flex items-center" aria-current={active ? 'step' : undefined}>
            <span className="flex items-center gap-1.5">
              <span
                className={cn(
                  'h-5 w-5 rounded-full flex items-center justify-center text-[10px] font-semibold tabular-nums border',
                  done && 'bg-brand-teal border-brand-teal text-white',
                  active && 'bg-brand-teal-light border-brand-teal text-brand-teal-dark',
                  !done && !active && 'bg-surface border-border-strong text-text-tertiary',
                )}
              >
                {done ? <Check className="h-3 w-3" aria-hidden /> : i + 1}
              </span>
              <span className={cn('text-[12px] whitespace-nowrap', active ? 'font-semibold text-text-primary' : done ? 'text-text-secondary' : 'text-text-tertiary')}>{s}</span>
            </span>
            {i < stages.length - 1 && <span className={cn('mx-2 h-px w-6 sm:w-8', done ? 'bg-brand-teal' : 'bg-border-strong')} aria-hidden />}
          </li>
        );
      })}
    </ol>
  );
}

/** Client-side text download (demo export; nothing leaves the browser). */
export function downloadText(filename: string, content: string, mime = 'text/markdown') {
  const blob = new Blob([content], { type: `${mime};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** Action lifecycle: keeps proposal, approval, implementation and effectiveness distinct. */
export const ACTION_LIFECYCLE = ['Proposed', 'Under review', 'Approved', 'Implemented in source system', 'Effectiveness verified'];
