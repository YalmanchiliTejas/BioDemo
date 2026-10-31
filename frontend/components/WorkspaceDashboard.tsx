'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { ArrowRight, ArrowUpRight, BookOpen, CheckCircle2, Circle, Database, FlaskConical, Layers, MessageSquare, PackageCheck, Plus, ShieldCheck } from 'lucide-react';
import { Button } from '@/components/ui';
import { connectorRequest, type Connector } from '@/lib/connectors-api';
import { decisionCount, getJson, type RunListing } from '@/lib/cmo-api';
import { isDemoCmo } from '@/lib/cmo-demo';
import { useWorkspace } from '@/lib/workspace-context';
import { useTutorial } from '@/lib/tutorial-context';

const tools = [
  { title: 'Check a delivery', body: 'Bring in files as received. Review values against their original sources.', href: '/cmo/', icon: PackageCheck },
  { title: 'Ask the assistant', body: 'Investigate a question using the context and evidence you choose.', href: '/home/', icon: MessageSquare },
  { title: 'Compare process scenarios', body: 'Explore predicted outcomes, assumptions and constraints.', href: '/process-simulation/', icon: FlaskConical },
];

export function WorkspaceDashboard() {
  const { organization, user } = useWorkspace();
  const guide = useTutorial();
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
  const checking = runs?.filter(r => r.status === 'queued' || r.status === 'running');
  const enabled = connections?.filter(c => c.enabled);
  const firstName = String(user?.user_metadata?.full_name || '').split(' ')[0];
  const metrics = [
    { label: 'Connected sources', value: enabled?.length, detail: 'Enabled in this workspace', icon: Database, href: '/sources/' },
    { label: 'Needs your review', value: review?.length, detail: 'Deliveries awaiting decisions', icon: PackageCheck, href: '/cmo/' },
    { label: 'Verified deliveries', value: verified?.length, detail: 'Source checks complete', icon: ShieldCheck, href: '/cmo/' },
    { label: 'Checks in progress', value: checking?.length, detail: 'Queued or being processed', icon: Layers, href: '/cmo/' },
  ];
  return <div className="workspace-page" data-testid="workspace-dashboard">
    <header className="page-heading"><div><div className="page-kicker">{organization?.name ?? 'Your workspace'} / Overview</div><h1>{firstName ? `Welcome back, ${firstName}.` : 'Your workspace at a glance.'}</h1><p>A clear view of your data, your work, and what needs attention.</p></div><div className="page-heading-actions"><button type="button" className="chrome-button" onClick={() => guide.open()}><BookOpen size={14} />Quick tour</button><Link href="/cmo/" className="chrome-button primary"><Plus size={15} />New delivery</Link></div></header>
    <section className="dashboard-metrics" aria-label="Workspace status">{metrics.map(({ label, value, detail, icon: Icon, href }) => <Link className="metric" href={href} key={label}><div><span>{label}</span><Icon size={15} /></div><strong className={!loading && value === undefined ? 'metric-unknown' : ''}>{loading ? '…' : value ?? 'Unavailable'}</strong><small>{detail}</small></Link>)}</section>
    {(errors.connections || errors.runs) && <div role="alert" className="workspace-alert"><strong>Some workspace information is unavailable.</strong>{errors.connections && <p>Connections: {errors.connections}</p>}{errors.runs && <p>Deliveries: {errors.runs}</p>}<Button onClick={() => setAttempt(i => i + 1)}>Try again</Button></div>}
    {loading && <p role="status" className="mb-4 text-xs text-text-secondary">Loading your workspace…</p>}
    <div className="dashboard-columns">
      <div className="dashboard-stack">
        <section className="workspace-panel"><div className="panel-heading"><div><h2>Recent deliveries</h2><p>Pick up where you left off.</p></div><Link href="/cmo/">View all <ArrowUpRight size={13} /></Link></div>
          <div className="quick-actions">{tools.map(({ title, href, icon: Icon }) => <Link key={href} href={href}><Icon size={14} />{title}</Link>)}</div>
          {runs && !runs.length && <div className="dashboard-empty"><span className="empty-icon"><PackageCheck size={21} /></span><h3>Your first delivery starts here.</h3><p>Add the files you received. Review extracted values beside their sources, all in one place.</p><Link className="chrome-button" href="/cmo/">Check a delivery <ArrowRight size={14} /></Link></div>}
          {!runs && !loading && <div className="dashboard-empty"><h3>Deliveries could not be loaded.</h3><p>Try again above, or continue with another tool.</p></div>}
          {runs && runs.length > 0 && <table className="delivery-table"><thead><tr><th>DELIVERY</th><th>STATUS</th><th className="date-column">RECEIVED</th></tr></thead><tbody>{runs.slice(0, 5).map(run => <tr key={run.id}><td><Link href={`/cmo/?run=${encodeURIComponent(run.id)}`}>{run.delivery_name || run.cmo}<small>{run.cmo}</small></Link></td><td><Link href={`/cmo/?run=${encodeURIComponent(run.id)}`} className={`status-label ${run.status !== 'complete' ? run.status : run.summary?.verified_package ? 'verified' : 'review'}`}>{run.status !== 'complete' ? run.status : run.summary?.verified_package ? 'Verified' : run.summary ? `${decisionCount(run.summary)} to review` : 'Review details'}</Link></td><td className="date-column">{run.started_at ? new Date(run.started_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : '—'}</td></tr>)}</tbody></table>}
        </section>
        <section className="workspace-panel dashboard-start"><MessageSquare size={22} strokeWidth={1.5} /><h2>Start with a question.</h2><p>Bring your manufacturing context together. Ask the assistant to work with your authorized sources and the verified deliveries you choose.</p><Link className="text-action" href="/home/">Open assistant <ArrowRight size={14} /></Link></section>
      </div>
      <div className="dashboard-stack">
        <section className="workspace-panel"><div className="panel-heading"><h2>Make this workspace yours</h2><button type="button" aria-label="Open getting started guide" className="text-action" onClick={() => guide.open()}><ArrowUpRight size={14} /></button></div><ol className="getting-started-list"><li>{enabled?.length ? <CheckCircle2 size={17} /> : <Circle size={17} />}<Link href="/sources/">Connect a source<small>{enabled?.length ? 'You have an enabled connection' : 'Start with the systems you use'}</small></Link></li><li>{runs?.length ? <CheckCircle2 size={17} /> : <Circle size={17} />}<Link href="/cmo/">Bring in a delivery<small>Keep the original evidence close</small></Link></li><li><Circle size={17} /><Link href="/settings/organization/">Review your team’s access<small>See roles and authorized sites</small></Link></li></ol><div className="panel-foot">At your pace. You can start working now.</div></section>
        <section className="workspace-panel"><div className="panel-heading"><h2>Data connections</h2><Link href="/sources/" aria-label="Manage data connections"><ArrowUpRight size={14} /></Link></div>{connections?.length ? <ul className="source-status-list">{connections.slice(0, 4).map(connection => <li key={connection.connector_id}><Link href="/sources/"><span>{connection.connector_id}</span><span className={`status-label ${connection.last_error ? 'failed' : ''}`}>{connection.last_error ? 'Needs attention' : connection.enabled ? 'Enabled' : 'Paused'}</span></Link><small>{connection.family} · {connection.last_sync ? `Last attempt ${new Date(connection.last_sync).toLocaleDateString()}` : 'No sync attempt yet'}</small>{connection.last_error && <small className="source-error">{connection.last_error}</small>}</li>)}</ul> : <div className="panel-body"><p className="text-xs leading-6 text-text-secondary">{loading ? 'Loading connections…' : connections ? 'Connect an authorized source to start collecting data.' : 'Connection status is unavailable.'}</p><Link href="/sources/" className="text-action mt-4"><Database size={13} />Manage connections</Link></div>}</section>
        <Link href="/process-simulation/" className="workspace-panel dashboard-start"><FlaskConical size={21} /><h2>Explore a process scenario</h2><p>Compare assumptions and predicted outcomes before deciding what to do next.</p><span className="text-action">Open simulation <ArrowRight size={14} /></span></Link>
      </div>
    </div>
    <p className="dashboard-note"><ShieldCheck size={13} />Status reflects records available to your account. Open a delivery to inspect its evidence and review history. Your source systems remain the systems of record.</p>
  </div>;
}
