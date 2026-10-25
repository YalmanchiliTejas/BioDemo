'use client';

import { Zap } from 'lucide-react';
import { useAgent } from '@/lib/agent/agent-context';
import type { ComposerMode, ScopeChip } from '@/lib/agent/types';
import { cn } from '@/lib/cn';

/**
 * Contextual entry to the agent composer. Kept free of `components/ui` imports because
 * PageHeader renders it.
 */
export function AskDelegateButton({ frame, label = 'Ask / Delegate', templateId, scope, prompt, mode = 'DELEGATE', size = 'md', variant = 'outline', className }: {
  frame: string;
  label?: string;
  templateId?: string;
  scope?: ScopeChip[];
  prompt?: string;
  mode?: ComposerMode;
  size?: 'sm' | 'md';
  variant?: 'outline' | 'solid';
  className?: string;
}) {
  const { openOverlay } = useAgent();
  return (
    <button
      type="button"
      onClick={() => openOverlay(mode, { frame, templateId, scope, prompt })}
      className={cn(
        'inline-flex items-center justify-center gap-1.5 font-medium rounded-control whitespace-nowrap transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-teal focus-visible:ring-offset-1',
        size === 'sm' ? 'h-7 px-2.5 text-xs' : 'h-8 px-3 text-[13px]',
        variant === 'solid' ? 'bg-slate-900 text-white hover:bg-slate-800' : 'bg-surface text-brand-teal-dark border border-cyan-300 hover:bg-brand-teal-light',
        className,
      )}
    >
      <Zap className="h-3.5 w-3.5" aria-hidden />
      {label}
    </button>
  );
}
