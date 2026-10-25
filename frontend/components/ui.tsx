'use client';

import Link from 'next/link';
import { useEffect, useId, useState, type ComponentProps, type ReactNode } from 'react';
import { AlertTriangle, ChevronRight, FileSearch, Info, X } from 'lucide-react';
import { cn } from '@/lib/cn';
import { useAppContext } from '@/lib/app-context';
import { CITATIONS } from '@/fixtures/biomanufacturingData';
import { AskDelegateButton } from './agent/AskDelegateButton';
import { hasAgentContext } from '@/lib/agent/screens';
import type { ScopeChip } from '@/lib/agent/types';

/* ------------------------------------------------------------------ Buttons */

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'subtle';
type ButtonSize = 'sm' | 'md' | 'lg' | 'touch';

const buttonBase =
  'inline-flex items-center justify-center gap-1.5 font-medium rounded-control transition-colors whitespace-nowrap focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-teal focus-visible:ring-offset-1 disabled:opacity-50 disabled:cursor-not-allowed';
const buttonVariants: Record<ButtonVariant, string> = {
  primary: 'bg-brand-teal text-white hover:bg-brand-teal-dark shadow-sm',
  secondary: 'bg-surface text-text-primary border border-border-strong hover:bg-surface-secondary',
  ghost: 'text-text-secondary hover:bg-surface-secondary hover:text-text-primary',
  danger: 'bg-surface text-status-critical border border-red-200 hover:bg-status-critical-bg',
  subtle: 'bg-brand-teal-light text-brand-teal-dark hover:bg-cyan-100',
};
const buttonSizes: Record<ButtonSize, string> = {
  sm: 'h-7 px-2.5 text-xs',
  md: 'h-8 px-3 text-[13px]',
  lg: 'h-10 px-4 text-sm',
  touch: 'min-h-[56px] px-5 text-base',
};

export function buttonClass(variant: ButtonVariant = 'secondary', size: ButtonSize = 'md', extra?: string) {
  return cn(buttonBase, buttonVariants[variant], buttonSizes[size], extra);
}

export function Button({ variant = 'secondary', size = 'md', className, ...props }: ComponentProps<'button'> & { variant?: ButtonVariant; size?: ButtonSize }) {
  return <button type="button" className={buttonClass(variant, size, className)} {...props} />;
}

export function LinkButton({ variant = 'secondary', size = 'md', className, ...props }: ComponentProps<typeof Link> & { variant?: ButtonVariant; size?: ButtonSize }) {
  return <Link className={buttonClass(variant, size, className)} {...props} />;
}

/* ------------------------------------------------------------------ Surfaces */

export function Card({ className, children, ...rest }: ComponentProps<'section'>) {
  return (
    <section className={cn('bg-surface border border-border-hairline rounded-card', className)} {...rest}>
      {children}
    </section>
  );
}

export function CardHeader({ title, subtitle, actions, icon, className }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode; icon?: ReactNode; className?: string }) {
  return (
    <header className={cn('flex items-start justify-between gap-3 px-4 py-3 border-b border-border-hairline', className)}>
      <div className="min-w-0 flex items-start gap-2">
        {icon && <span className="mt-0.5 text-text-tertiary">{icon}</span>}
        <div className="min-w-0">
          <h2 className="text-[13px] font-semibold text-text-primary leading-5">{title}</h2>
          {subtitle && <p className="text-xs text-text-tertiary mt-0.5">{subtitle}</p>}
        </div>
      </div>
      {actions && <div className="flex items-center gap-1.5 shrink-0">{actions}</div>}
    </header>
  );
}

export function CardBody({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={cn('p-4', className)}>{children}</div>;
}

export function SectionLabel({ children, className }: { children: ReactNode; className?: string }) {
  return <h3 className={cn('text-[11px] font-semibold uppercase tracking-wider text-text-tertiary', className)}>{children}</h3>;
}

/* ------------------------------------------------------------------ Pills & status */

export type Tone = 'neutral' | 'success' | 'warning' | 'critical' | 'info' | 'brand' | 'muted';
const toneClasses: Record<Tone, string> = {
  neutral: 'bg-surface-secondary text-text-secondary border-border-hairline',
  success: 'bg-status-success-bg text-emerald-700 border-emerald-200',
  warning: 'bg-status-warning-bg text-amber-700 border-amber-200',
  critical: 'bg-status-critical-bg text-red-700 border-red-200',
  info: 'bg-sky-50 text-sky-700 border-sky-200',
  brand: 'bg-brand-teal-light text-brand-teal-dark border-cyan-200',
  muted: 'bg-transparent text-text-tertiary border-border-hairline',
};
const dotClasses: Record<Tone, string> = {
  neutral: 'bg-status-neutral', success: 'bg-status-success', warning: 'bg-status-warning', critical: 'bg-status-critical',
  info: 'bg-data-blue', brand: 'bg-brand-teal', muted: 'bg-text-muted',
};

export function Pill({ tone = 'neutral', children, dot, className, title }: { tone?: Tone; children: ReactNode; dot?: boolean; className?: string; title?: string }) {
  return (
    <span title={title} className={cn('inline-flex items-center gap-1 h-5 px-2 rounded-pill border text-[11px] font-medium whitespace-nowrap', toneClasses[tone], className)}>
      {dot && <span className={cn('h-1.5 w-1.5 rounded-full', dotClasses[tone])} />}
      {children}
    </span>
  );
}

export function StatusDot({ tone = 'neutral', pulse }: { tone?: Tone; pulse?: boolean }) {
  return (
    <span className="relative inline-flex h-2 w-2">
      {pulse && <span className={cn('absolute inline-flex h-full w-full rounded-full opacity-60 animate-ping', dotClasses[tone])} />}
      <span className={cn('relative inline-flex h-2 w-2 rounded-full', dotClasses[tone])} />
    </span>
  );
}

/**
 * Epistemic label. Every finding shown to a user should say what kind of claim it is
 * (observation, calculation, hypothesis, recommendation, unknown, approved decision).
 */
export type ClaimKind = 'observation' | 'calculated' | 'hypothesis' | 'recommendation' | 'unknown' | 'approved' | 'imputed' | 'contradicted';
const claimMeta: Record<ClaimKind, { label: string; tone: Tone; hint: string }> = {
  observation: { label: 'Observation', tone: 'info', hint: 'Directly read from a source record.' },
  calculated: { label: 'Calculated', tone: 'neutral', hint: 'Derived by a reproducible calculation from source records.' },
  hypothesis: { label: 'Hypothesis', tone: 'warning', hint: 'A candidate explanation. Not established.' },
  recommendation: { label: 'Proposal', tone: 'brand', hint: 'A suggested action. Not approved and not executed.' },
  unknown: { label: 'Unknown', tone: 'muted', hint: 'Evidence is missing or insufficient.' },
  approved: { label: 'Approved', tone: 'success', hint: 'Signed by an authorized person.' },
  imputed: { label: 'Imputed', tone: 'muted', hint: 'Estimated to fill a data gap. Excluded from statistics.' },
  contradicted: { label: 'Contradicted', tone: 'critical', hint: 'Evidence contradicts this explanation.' },
};
export function ClaimTag({ kind, className }: { kind: ClaimKind; className?: string }) {
  const m = claimMeta[kind];
  return <Pill tone={m.tone} title={m.hint} className={cn('uppercase tracking-wide text-[10px]', className)}>{m.label}</Pill>;
}

/** Clickable citation that opens the source excerpt and hash in the right inspector. */
export function EvidenceChip({ id, label, className }: { id: string; label?: string; className?: string }) {
  const { openEvidence } = useAppContext();
  const c = CITATIONS[id];
  const text = label ?? (c ? `${c.documentName}${c.sectionOrClause ? ' ' + c.sectionOrClause.split('·')[0].trim() : ''}` : id);
  return (
    <button
      type="button"
      onClick={() => openEvidence(id)}
      title={c ? `${c.sourceSystem} · open source excerpt` : 'Open source'}
      className={cn('inline-flex items-center gap-1 max-w-full align-baseline px-1.5 py-px rounded border border-cyan-200 bg-brand-teal-light text-brand-teal-dark text-[11px] font-mono hover:bg-cyan-100 hover:border-cyan-300 transition-colors', className)}
    >
      <FileSearch className="h-3 w-3 shrink-0" aria-hidden />
      <span className="truncate">[{text}]</span>
    </button>
  );
}

export function Hash({ value, className, full }: { value: string; className?: string; full?: boolean }) {
  const short = full || value.length < 20 ? value : `${value.slice(0, 10)}…${value.slice(-6)}`;
  return <code title={value} className={cn('font-mono text-[11px] text-text-tertiary', className)}>sha256:{short}</code>;
}

/* ------------------------------------------------------------------ Data display */

export function Stat({ label, value, unit, delta, deltaTone = 'neutral', hint, className, kind }: { label: string; value: ReactNode; unit?: string; delta?: string; deltaTone?: Tone; hint?: ReactNode; className?: string; kind?: ClaimKind }) {
  const deltaColor: Record<Tone, string> = { neutral: 'text-text-tertiary', success: 'text-status-success', warning: 'text-status-warning', critical: 'text-status-critical', info: 'text-data-blue', brand: 'text-brand-teal', muted: 'text-text-muted' };
  return (
    <div className={cn('min-w-0', className)}>
      <div className="flex items-center gap-1.5">
        <p className="text-[11px] font-medium uppercase tracking-wide text-text-tertiary truncate">{label}</p>
        {kind && <ClaimTag kind={kind} className="!h-4 !px-1.5 !text-[9px]" />}
      </div>
      <p className="mt-1 flex items-baseline gap-1 tabular-nums">
        <span className="text-xl font-semibold text-text-primary">{value}</span>
        {unit && <span className="text-xs text-text-tertiary">{unit}</span>}
        {delta && <span className={cn('ml-1 text-xs font-medium', deltaColor[deltaTone])}>{delta}</span>}
      </p>
      {hint && <p className="mt-0.5 text-[11px] text-text-tertiary">{hint}</p>}
    </div>
  );
}

export function ProgressBar({ value, max = 100, tone = 'brand', className, label }: { value: number; max?: number; tone?: Tone; className?: string; label?: string }) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div className={cn('h-1.5 w-full rounded-pill bg-surface-secondary overflow-hidden', className)} role="progressbar" aria-valuenow={value} aria-valuemax={max} aria-label={label}>
      <div className={cn('h-full rounded-pill', dotClasses[tone])} style={{ width: `${pct}%` }} />
    </div>
  );
}

export function KeyValue({ items, className, cols = 2 }: { items: Array<[ReactNode, ReactNode]>; className?: string; cols?: 1 | 2 | 3 | 4 }) {
  const grid = { 1: 'grid-cols-1', 2: 'grid-cols-2', 3: 'grid-cols-3', 4: 'grid-cols-2 md:grid-cols-4' }[cols];
  return (
    <dl className={cn('grid gap-x-4 gap-y-2.5', grid, className)}>
      {items.map(([k, v], i) => (
        <div key={i} className="min-w-0">
          <dt className="text-[11px] text-text-tertiary">{k}</dt>
          <dd className="text-[13px] text-text-primary font-medium tabular-nums truncate">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

/** Table styles. Use: <table className={table.root}> ... */
export const table = {
  wrap: 'w-full overflow-x-auto',
  root: 'w-full text-[13px] tabular-nums border-collapse',
  th: 'text-left text-[11px] font-semibold uppercase tracking-wide text-text-tertiary px-3 py-2 border-b border-border-hairline bg-surface-secondary/60 whitespace-nowrap',
  td: 'px-3 py-2 border-b border-border-hairline text-text-primary align-middle',
  tr: 'hover:bg-surface-secondary/60',
};

/* ------------------------------------------------------------------ Page scaffolding */

export type Crumb = { label: string; href?: string };

export function Breadcrumbs({ items }: { items: Crumb[] }) {
  return (
    <nav aria-label="Breadcrumb" className="flex items-center gap-1 text-xs text-text-tertiary min-w-0">
      {items.map((c, i) => (
        <span key={i} className="flex items-center gap-1 min-w-0">
          {i > 0 && <ChevronRight className="h-3 w-3 shrink-0 text-text-muted" aria-hidden />}
          {c.href ? <Link href={c.href} className="hover:text-text-primary truncate">{c.label}</Link> : <span className="text-text-secondary truncate">{c.label}</span>}
        </span>
      ))}
    </nav>
  );
}

export function PageHeader({ frameId, crumbs, title, objectId, status, description, actions, meta, agent }: {
  frameId?: string;
  crumbs?: Crumb[];
  title: ReactNode;
  objectId?: string;
  status?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  meta?: ReactNode;
  /** Contextual agent entry next to the primary actions. Defaults on for app-shell frames; `false` hides it. */
  agent?: false | { label?: string; templateId?: string; scope?: ScopeChip[] };
}) {
  const showAgent = agent !== false && hasAgentContext(frameId);
  const agentButton = showAgent && frameId ? <AskDelegateButton frame={frameId} {...(agent || {})} /> : null;
  return (
    <header className="mb-4">
      {crumbs && <Breadcrumbs items={crumbs} />}
      <div className="mt-1.5 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-lg font-semibold text-text-primary tracking-tight">{title}</h1>
            {objectId && <code className="text-xs font-mono text-text-secondary bg-surface-secondary border border-border-hairline px-1.5 py-0.5 rounded">{objectId}</code>}
            {status}
          </div>
          {description && <p className="mt-1 text-[13px] text-text-secondary max-w-3xl">{description}</p>}
          {meta && <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-text-tertiary">{meta}</div>}
        </div>
        {(actions || agentButton) && <div className="flex flex-wrap items-center gap-2">{agentButton}{actions}</div>}
      </div>
      {frameId && <span className="sr-only">Frame {frameId}</span>}
    </header>
  );
}

export function Tabs({ tabs, active, onChange, className }: { tabs: Array<{ key: string; label: string; count?: number }>; active: string; onChange: (k: string) => void; className?: string }) {
  return (
    <div role="tablist" className={cn('flex items-center gap-1 border-b border-border-hairline overflow-x-auto', className)}>
      {tabs.map((t) => (
        <button
          key={t.key}
          role="tab"
          aria-selected={active === t.key}
          onClick={() => onChange(t.key)}
          className={cn('h-9 px-3 -mb-px border-b-2 text-[13px] font-medium whitespace-nowrap transition-colors', active === t.key ? 'border-brand-teal text-text-primary' : 'border-transparent text-text-tertiary hover:text-text-primary')}
        >
          {t.label}
          {t.count !== undefined && <span className="ml-1.5 text-[11px] text-text-muted tabular-nums">{t.count}</span>}
        </button>
      ))}
    </div>
  );
}

export function Segmented<T extends string>({ options, value, onChange, size = 'sm' }: { options: Array<{ value: T; label: string }>; value: T; onChange: (v: T) => void; size?: 'sm' | 'md' }) {
  return (
    <div className="inline-flex rounded-control border border-border-hairline bg-surface-secondary p-0.5" role="radiogroup">
      {options.map((o) => (
        <button
          key={o.value}
          role="radio"
          aria-checked={value === o.value}
          onClick={() => onChange(o.value)}
          className={cn('rounded-[4px] font-medium transition-colors', size === 'sm' ? 'h-6 px-2 text-xs' : 'h-7 px-3 text-[13px]', value === o.value ? 'bg-surface text-text-primary shadow-sm' : 'text-text-tertiary hover:text-text-primary')}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Callout({ tone = 'info', title, children, icon, action, className }: { tone?: Tone; title?: ReactNode; children?: ReactNode; icon?: ReactNode; action?: ReactNode; className?: string }) {
  const Icon = tone === 'warning' || tone === 'critical' ? AlertTriangle : Info;
  return (
    <div className={cn('flex items-start gap-2.5 rounded-card border px-3 py-2.5', toneClasses[tone], className)} role={tone === 'critical' ? 'alert' : undefined}>
      <span className="mt-0.5 shrink-0">{icon ?? <Icon className="h-4 w-4" aria-hidden />}</span>
      <div className="min-w-0 flex-1 text-[13px]">
        {title && <p className="font-semibold">{title}</p>}
        {children && <div className={cn('text-[12.5px] opacity-90', !!title && 'mt-0.5')}>{children}</div>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}

/** Persistent reminder that the environment is synthetic and read-only. */
export function DemoBoundary({ className, compact }: { className?: string; compact?: boolean }) {
  return (
    <Pill tone="muted" className={className} title="All records are synthetic. Nothing is written to MES, DCS/PLC, LIMS, QMS or ERP systems.">
      <span className="h-1.5 w-1.5 rounded-full bg-status-warning" />
      {compact ? 'Demo · read-only' : 'Synthetic demo data · read-only, no writeback'}
    </Pill>
  );
}

/* ------------------------------------------------------------------ Modal */

export function Modal({ open, onClose, title, children, footer, width = 'max-w-lg' }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; footer?: ReactNode; width?: string }) {
  const id = useId();
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-slate-900/40" onClick={onClose} aria-hidden />
      <div role="dialog" aria-modal="true" aria-labelledby={id} className={cn('relative w-full bg-surface rounded-card border border-border-hairline shadow-xl', width)}>
        <div className="flex items-center justify-between px-4 py-3 border-b border-border-hairline">
          <h2 id={id} className="text-sm font-semibold text-text-primary">{title}</h2>
          <button onClick={onClose} className="p-1 rounded text-text-tertiary hover:bg-surface-secondary" aria-label="Close dialog"><X className="h-4 w-4" /></button>
        </div>
        <div className="px-4 py-4 max-h-[70vh] overflow-y-auto">{children}</div>
        {footer && <div className="flex justify-end gap-2 px-4 py-3 border-t border-border-hairline bg-surface-secondary/50 rounded-b-card">{footer}</div>}
      </div>
    </div>
  );
}

export function useDisclosure(initial = false) {
  const [open, setOpen] = useState(initial);
  return { open, onOpen: () => setOpen(true), onClose: () => setOpen(false), toggle: () => setOpen((o) => !o) };
}

export function EmptyNote({ children }: { children: ReactNode }) {
  return <p className="text-xs text-text-tertiary italic">{children}</p>;
}
