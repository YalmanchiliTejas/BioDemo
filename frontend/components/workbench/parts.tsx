import type { ReactNode } from 'react';
import { workButton } from '@/components/process/AssistantTaskWork';

/** Shared with the assistant's task forms, so both surfaces read as one product. */
export const field = 'mt-1 block w-full rounded-control border border-border-strong bg-surface px-2.5 py-2 text-sm text-text-primary';
export const primaryButton = `${workButton} !border-brand-teal !bg-brand-teal !text-white hover:!bg-brand-teal-dark`;
export const card = 'rounded-control border border-border-hairline bg-surface p-3 text-xs leading-5 text-text-secondary';
export const chip = (on: boolean) => `inline-flex items-center gap-1.5 rounded-pill border px-2.5 py-1 text-xs focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-teal ${on
  ? 'border-brand-teal bg-brand-teal-light font-medium text-brand-teal-dark' : 'border-border-strong bg-surface text-text-secondary hover:bg-surface-secondary'}`;

/** One of the four parts of the working sequence. They share a page and do not force an order. */
export function Region({ number, id, title, hint, aside, children }: { number: number; id: string; title: string; hint?: ReactNode; aside?: ReactNode; children: ReactNode }) {
  return <section id={id} aria-labelledby={`${id}-title`} data-testid={`region-${id}`} className="min-w-0 scroll-mt-4 rounded-card border border-border-hairline bg-surface p-4 sm:p-5">
    <header className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-1">
      <h2 id={`${id}-title`} className="flex items-center gap-2 text-[15px] font-medium text-text-primary">
        <span aria-hidden className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-brand-teal-light text-[11px] font-semibold text-brand-teal-dark">{number}</span>{title}</h2>
      {hint && <p className="text-xs text-text-tertiary">{hint}</p>}
      {aside && <div className="ml-auto text-[11px]">{aside}</div>}
    </header>
    {children}
  </section>;
}
