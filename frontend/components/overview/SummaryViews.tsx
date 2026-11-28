'use client';

import Link from 'next/link';
import type { ReactNode } from 'react';
import { ArrowRight, ChartLine, ClipboardList, Database, Download, FlaskConical, FolderKanban, FolderOpen, MessageSquare, PackageCheck, Radar, type LucideIcon } from 'lucide-react';
import { DESTINATIONS, type ICONS, type OverviewComponent, type OverviewModel, type Tone } from '@/lib/overview-views';

/** The registered pieces an overview is built from. The A2UI surface and the plain fallback both render these. */
const ICON: Record<(typeof ICONS)[number], LucideIcon> = {
  deliveries: PackageCheck, signals: Radar, quality: FolderKanban, trends: ChartLine, workbench: ClipboardList,
  assistant: MessageSquare, simulation: FlaskConical, saved: FolderOpen, export: Download, connections: Database,
};
const TONES: Tone[] = ['loading', 'attention', 'problem', 'good', 'quiet', 'unavailable'];

export type CardProps = { icon: string; title: string; about: string; href: string; value?: string; status?: string; tone?: string };

export function SummaryCardView({ icon, title, about, href, value, status, tone }: CardProps) {
  const Icon = ICON[icon as keyof typeof ICON] ?? ClipboardList;
  const state = TONES.includes(tone as Tone) ? tone : 'quiet';
  // A view may only lead to a registered destination, whatever it declares.
  const target = (DESTINATIONS as readonly string[]).includes(href) ? href : '/dashboard/';
  return <Link href={target} className="summary-card" data-guide="overview-summary" data-tone={state} aria-busy={state === 'loading' || undefined}>
    <span className="summary-card-head"><span className="summary-card-icon" aria-hidden><Icon size={16} strokeWidth={1.75} /></span><strong>{title}</strong><ArrowRight size={15} className="summary-card-arrow" aria-hidden /></span>
    {(value || status) && <span className="summary-card-figure">{value && <b>{value}</b>}{status && <span>{status}</span>}</span>}
    <span className="summary-card-about">{about}</span>
  </Link>;
}

export function SummaryGroupView({ title, children }: { title: string; children: ReactNode }) {
  return <section className="summary-group" aria-label={title}><h2>{title}</h2><div className="summary-grid">{children}</div></section>;
}

export function OverviewPageView({ children }: { children: ReactNode }) {
  return <div className="overview-groups">{children}</div>;
}

const bound = (value: unknown, model: OverviewModel): string | undefined => {
  if (typeof value === 'string') return value;
  const path = (value as { '@path'?: string } | undefined)?.['@path'];
  if (!path) return undefined;
  const found = path.split('/').filter(Boolean).reduce<unknown>((at, key) => (at as Record<string, unknown> | undefined)?.[key], model);
  return typeof found === 'string' ? found : undefined;
};

/** The same view without the A2UI renderer: shown while it loads, and if it ever fails, so the landing page is never blank. */
export function NativeOverview({ components, model }: { components: OverviewComponent[]; model: OverviewModel }) {
  const byId = new Map(components.map(component => [component.id, component]));
  const render = (id: string): ReactNode => {
    const c = byId.get(id);
    if (!c) return null;
    const children = ((c.children as string[] | undefined) ?? []).map(render);
    if (c.component === 'OverviewPage') return <OverviewPageView key={id}>{children}</OverviewPageView>;
    if (c.component === 'SummaryGroup') return <SummaryGroupView key={id} title={String(c.title)}>{children}</SummaryGroupView>;
    return <SummaryCardView key={id} icon={String(c.icon)} title={String(c.title)} about={String(c.about)} href={String(c.href)}
      value={bound(c.value, model)} status={bound(c.status, model)} tone={bound(c.tone, model)} />;
  };
  return <>{render('root')}</>;
}
