'use client';

import { KeyRound, MessageCircleQuestion } from 'lucide-react';
import type { Gate } from '@/lib/agent/types';
import { EvidenceChip } from '../ui';
import { cn } from '@/lib/cn';

/** Blocks the run until the user resolves something the agent cannot determine itself. */
export function ClarificationPrompt({ gate, answer, onAnswer }: { gate: Gate; answer?: string; onAnswer: (value: string) => void }) {
  const Icon = gate.kind === 'PERMISSION' ? KeyRound : MessageCircleQuestion;
  const held = gate.options.find((o) => o.value === answer && o.holds);
  return (
    <div className="bg-amber-50 border border-amber-200 rounded-md p-3" role="group" aria-label={gate.kind === 'PERMISSION' ? 'Access needed' : 'Decision needed'}>
      <p className="flex items-center gap-1.5 text-[10.5px] font-semibold uppercase tracking-wider text-amber-800">
        <Icon className="h-3.5 w-3.5" aria-hidden />
        {gate.kind === 'PERMISSION' ? 'Waiting on access' : 'Needs your input'} · run paused
      </p>
      <p className="mt-1.5 text-[13px] font-medium text-text-primary leading-snug">{gate.question}</p>
      {gate.context && <p className="mt-1 text-[12px] text-text-secondary leading-snug">{gate.context}</p>}
      {gate.citations && <div className="mt-2 flex flex-wrap gap-1">{gate.citations.map((c) => <EvidenceChip key={c} id={c} />)}</div>}
      <div className="mt-2.5 flex flex-col gap-1.5">
        {gate.options.map((o) => (
          <button
            key={o.value}
            type="button"
            onClick={() => onAnswer(o.value)}
            aria-pressed={answer === o.value}
            className={cn(
              'text-left rounded-control border px-2.5 py-2 text-[12.5px] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-teal',
              answer === o.value ? 'border-amber-400 bg-white' : 'border-amber-200 bg-white/70 hover:bg-white hover:border-amber-300',
            )}
          >
            <span className="font-medium text-text-primary">{o.label}</span>
            {o.recommended && <span className="ml-1.5 text-[10.5px] font-semibold uppercase tracking-wide text-brand-teal-dark">Recommended</span>}
            {o.note && <span className="block mt-0.5 text-[11.5px] text-text-tertiary">{o.note}</span>}
          </button>
        ))}
      </div>
      {held && <p className="mt-2 text-[11.5px] text-amber-800">Holding on “{held.label}”. Pick another option at any time to continue.</p>}
    </div>
  );
}
