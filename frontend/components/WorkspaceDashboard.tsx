'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { ArrowRight, CheckCircle2, Circle, PackageCheck, Plus, RotateCw } from 'lucide-react';
import { connectorRequest, type Connector } from '@/lib/connectors-api';
import { decisionCount, getJson, type RunListing } from '@/lib/cmo-api';
import { isDemoCmo } from '@/lib/cmo-demo';
import { useWorkspace } from '@/lib/workspace-context';
import { useTutorial } from '@/lib/tutorial-context';
import { WorkspacePageHeader } from '@/components/shell/WorkspacePageHeader';

const deliveryHref = (run: RunListing) => `/cmo/?run=${encodeURIComponent(run.id)}`;
const deliveryStatus = (run: RunListing) => run.status !== 'complete'
  ? { tone: run.status === 'failed' ? 'failed' : '', label: run.status === 'queued' || run.status === 'running' ? 'Checking' : run.status }
  : run.summary?.verified_package ? { tone: 'verified', label: 'Verified' }
  : { tone: 'review', label: run.summary ? `${decisionCount(run.summary)} to review` : 'Review details' };

export function WorkspaceDashboard() {
  const { user } = useWorkspace();
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
    { label: 'Needs your review', value: review?.length, detail: 'Deliveries awaiting decisions', href: '/cmo/' },
    { label: 'Verified deliveries', value: verified?.length, detail: 'All source checks complete', href: '/cmo/' },
    { label: 'Checks in progress', value: checking?.length, detail: 'Queued or being processed', href: '/cmo/' },
    { label: 'Connected sources', value: enabled?.length, detail: 'Enabled in this workspace', href: '/sources/' },
  ];
  const steps = [
    { done: !!enabled?.length, label: 'Connect a source', detail: 'Start with a system you already use', href: '/sources/' },
    { done: !!runs?.length, label: 'Check a delivery', detail: 'Keep the original evidence beside each value', href: '/cmo/' },
  ];
  const setupComplete = !loading && steps.every(step => step.done);
  return <div className="workspace-page" data-testid="workspace-dashboard">
    <WorkspacePageHeader title={firstName ? `Welcome back, ${firstName}` : 'Overview'} description="What needs your attention across deliveries and connected sources."
      actions={<Link href="/cmo/" className="chrome-button primary"><Plus size={15} />New delivery</Link>} />
    {(errors.connections || errors.runs) && <div role="alert" className="workspace-alert compact"><div><strong>Some information is unavailable.</strong> {[errors.runs && `Deliveries: ${errors.runs}`, errors.connections && `Connections: ${errors.connections}`].filter(Boolean).join(' ')}</div><button type="button" className="chrome-button" onClick={() => setAttempt(i => i + 1)}><RotateCw size={13} />Retry</button></div>}
    <section className="dashboard-metrics" aria-label="Workspace status" aria-busy={loading}>{metrics.map(({ label, value, detail, href }) => <Link className="metric" href={href} key={label}><span>{label}</span><strong className={!loading && value === undefined ? 'metric-unknown' : ''}>{loading ? '…' : value ?? '—'}</strong><small>{!loading && value === undefined ? 'Unavailable right now' : detail}</small></Link>)}</section>
    <div className="dashboard-columns">
      <section className="workspace-panel"><div className="panel-heading"><div><h2>Recent deliveries</h2><p>Pick up where you left off.</p></div>{!!runs?.length && <Link href="/cmo/">View all <ArrowRight size={13} /></Link>}</div>
        {loading && <p role="status" className="panel-body panel-muted">Loading deliveries…</p>}
        {runs && !runs.length && <div className="dashboard-empty"><span className="empty-icon"><PackageCheck size={20} /></span><h3>No deliveries yet</h3><p>Add the files a CMO sent you. Each extracted value is shown beside its original source for review.</p><Link className="chrome-button" href="/cmo/">Check a delivery <ArrowRight size={14} /></Link></div>}
        {!runs && !loading && <div className="dashboard-empty"><h3>Deliveries could not be loaded</h3><p>Retry above. Nothing has been changed.</p></div>}
        {runs && runs.length > 0 && <table className="delivery-table"><thead><tr><th>Delivery</th><th>Status</th><th className="date-column">Received</th></tr></thead><tbody>{runs.slice(0, 6).map(run => { const status = deliveryStatus(run); return <tr key={run.id}><td><Link href={deliveryHref(run)}>{run.delivery_name || run.cmo}<small>{run.cmo}</small></Link></td><td><span className={`status-label ${status.tone}`}>{status.label}</span></td><td className="date-column">{run.started_at ? new Date(run.started_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : '—'}</td></tr>; })}</tbody></table>}
      </section>
      <div className="dashboard-stack">
        {!setupComplete && <section className="workspace-panel"><div className="panel-heading"><div><h2>Get started</h2><p>{steps.filter(step => step.done).length} of {steps.length} done</p></div></div><ol className="getting-started-list">{steps.map(step => <li key={step.label}>{step.done ? <CheckCircle2 size={16} className="done" /> : <Circle size={16} />}<Link href={step.href}>{step.label}<small>{step.detail}</small></Link></li>)}</ol><div className="panel-foot"><button type="button" className="text-action" onClick={() => guide.open()}>Open the workspace guide <ArrowRight size={13} /></button></div></section>}
        <section className="workspace-panel"><div className="panel-heading"><h2>Data connections</h2><Link href="/sources/">Manage</Link></div>{connections?.length ? <ul className="source-status-list">{connections.slice(0, 5).map(connection => <li key={connection.connector_id}><div><span>{connection.connector_id}</span><span className={`status-label ${connection.last_error ? 'failed' : connection.enabled ? 'verified' : ''}`}>{connection.last_error ? 'Needs attention' : connection.enabled ? 'Enabled' : 'Paused'}</span></div><small>{connection.family} · {connection.last_sync ? `Last attempt ${new Date(connection.last_sync).toLocaleDateString()}` : 'No sync attempt yet'}</small>{connection.last_error && <small className="source-error">{connection.last_error}</small>}</li>)}</ul> : <p className="panel-body panel-muted">{loading ? 'Loading connections…' : connections ? 'No sources connected yet. Connect an authorized system to start collecting data.' : 'Connection status is unavailable.'}</p>}</section>
      </div>
    </div>
  </div>;
}
