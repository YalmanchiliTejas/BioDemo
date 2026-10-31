'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { ArrowRight, Database, FlaskConical, MessageSquare, PackageCheck } from 'lucide-react';
import { Button, LinkButton } from '@/components/ui';
import { connectorRequest, type Connector } from '@/lib/connectors-api';
import { decisionCount, getJson, type RunListing } from '@/lib/cmo-api';
import { isDemoCmo } from '@/lib/cmo-demo';

const tools = [
  { title: 'Check a delivery', body: 'Bring in files as received. Review values against their original sources.', href: '/cmo/', icon: PackageCheck },
  { title: 'Ask the assistant', body: 'Investigate a question using the context and evidence you choose.', href: '/home/', icon: MessageSquare },
  { title: 'Compare process scenarios', body: 'Explore predicted outcomes, assumptions and constraints.', href: '/process-simulation/', icon: FlaskConical },
];

export function WorkspaceDashboard() {
  const [connections, setConnections] = useState<Connector[] | null>(null);
  const [runs, setRuns] = useState<RunListing[] | null>(null);
  const [errors, setErrors] = useState<{ connections?: string; runs?: string }>({});
  const [loading, setLoading] = useState(true);
  const [attempt, setAttempt] = useState(0);
  const load = useCallback((active: () => boolean) => {
    setLoading(true); setErrors({});
    void Promise.allSettled([
      connectorRequest<{ items: Connector[] }>('/connectors'),
      getJson<{ runs: RunListing[] }>('/runs'),
    ]).then(([sources, deliveries]) => {
      if (!active()) return;
      setConnections(sources.status === 'fulfilled' ? sources.value.items : null);
      setRuns(deliveries.status === 'fulfilled' ? deliveries.value.runs.filter(r => !r.superseded_by && !isDemoCmo(r.cmo) && !r.cmo.includes('· demo ')) : null);
      setErrors({ ...(sources.status === 'rejected' ? { connections: sources.reason.message } : {}), ...(deliveries.status === 'rejected' ? { runs: deliveries.reason.message } : {}) });
      setLoading(false);
    });
  }, []);
  useEffect(() => { let active = true; load(() => active); return () => { active = false; }; }, [load, attempt]);
  const review = runs?.filter(r => r.status === 'complete' && !r.summary?.verified_package);
  const verified = runs?.filter(r => r.summary?.verified_package);
  return <div className="mx-auto max-w-6xl space-y-10" data-testid="workspace-dashboard">
    <header className="flex flex-wrap items-start justify-between gap-4"><div><p className="text-sm font-medium text-brand-teal">Your workspace</p><h1 className="mt-3 font-display text-4xl font-light tracking-tight text-ink">Dashboard</h1><p className="mt-3 text-sm leading-6 text-text-secondary">Pick up your work, check what needs attention, or start with a question.</p></div><LinkButton href="/onboarding/start/"><Database size={15} />Manage connections</LinkButton></header>
    <section aria-label="Workspace status" className="grid gap-6 rounded-xl border border-border-hairline bg-white p-6 sm:grid-cols-3">
      {[{ label: 'Enabled connections', value: connections?.filter(c => c.enabled).length, href: '/onboarding/start/' }, { label: 'Deliveries to review', value: review?.length, href: '/cmo/' }, { label: 'Verified deliveries', value: verified?.length, href: '/cmo/' }].map(item => <Link key={item.label} href={item.href} className="group"><p className="text-sm text-text-secondary">{item.label}</p><p className="mt-2 text-3xl font-light tabular-nums group-hover:text-brand-teal">{loading ? '…' : item.value ?? 'Unavailable'}</p></Link>)}
    </section>
    {(errors.connections || errors.runs) && <div role="alert" className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm"><p className="font-medium">Some workspace information could not be loaded.</p>{errors.connections && <p className="mt-2">Connections: {errors.connections}</p>}{errors.runs && <p className="mt-2">Deliveries: {errors.runs}</p>}<Button className="mt-3" onClick={() => setAttempt(i => i + 1)}>Try again</Button></div>}
    {loading && <p role="status" className="text-sm text-text-secondary">Loading workspace status…</p>}
    {connections?.some(c => c.last_error) && <section className="rounded-lg border border-amber-300 bg-amber-50 p-4"><h2 className="font-medium">Connections need attention</h2><ul className="mt-2 space-y-2">{connections.filter(c => c.last_error).map(c => <li key={c.connector_id}><Link href="/onboarding/start/" className="underline">{c.connector_id}</Link>: {c.last_error}</li>)}</ul></section>}
    <section><h2 className="text-xl font-medium">What would you like to do?</h2><div className="mt-4 divide-y divide-border-hairline">{tools.map(({ title, body, href, icon: Icon }) => <Link key={href} href={href} className="group flex items-center gap-4 py-5"><Icon className="h-5 w-5 shrink-0 text-brand-teal" /><div className="flex-1"><h3 className="text-base font-medium group-hover:text-brand-teal">{title}</h3><p className="mt-1 text-sm text-text-secondary">{body}</p></div><ArrowRight className="h-4 w-4 shrink-0" /></Link>)}</div></section>
    <section><div className="flex items-center justify-between gap-3"><h2 className="text-xl font-medium">Recent deliveries</h2><Link href="/cmo/" className="text-sm text-brand-teal underline">View deliveries</Link></div>
      {runs && !runs.length && <p className="mt-4 rounded-xl border border-dashed border-border-strong p-6 text-sm leading-6 text-text-secondary">No deliveries yet. Check your first delivery, or use the assistant to work with connected sources. Available samples are listed in Deliveries.</p>}
      {runs && runs.length > 0 && <ul className="mt-4 divide-y divide-border-hairline">{runs.slice(0, 6).map(run => <li key={run.id}><Link href={`/cmo/?run=${encodeURIComponent(run.id)}`} className="flex flex-wrap items-center justify-between gap-3 py-4 hover:text-brand-teal"><div><p className="font-medium">{run.delivery_name || run.cmo}</p><p className="mt-1 text-xs text-text-secondary">{run.cmo}{run.started_at ? ` · ${new Date(run.started_at).toLocaleString()}` : ''}</p></div><span className="text-sm">{run.status !== 'complete' ? run.status : run.summary?.verified_package ? 'Verified' : run.summary ? `${decisionCount(run.summary)} decisions to review` : 'Review details'} →</span></Link></li>)}</ul>}
    </section>
    <p className="text-xs leading-5 text-text-secondary">Status reflects records available to your account. Open a delivery to inspect its evidence and review history. Existing source systems remain the systems of record.</p>
  </div>;
}
