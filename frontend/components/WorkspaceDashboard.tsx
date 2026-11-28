'use client';

import { Component, useEffect, useMemo, useState, type ReactNode } from 'react';
import { RotateCw } from 'lucide-react';
import { connectorRequest, type Connector } from '@/lib/connectors-api';
import { getJson, type RunListing } from '@/lib/cmo-api';
import { isDemoCmo } from '@/lib/cmo-demo';
import { listSignals } from '@/lib/signals-api';
import { listQuality } from '@/lib/quality-workflow-api';
import { listPlans } from '@/lib/workbench';
import { processRequest } from '@/lib/process-api';
import { useDemo } from '@/lib/demo-api';
import { useWorkspace } from '@/lib/workspace-context';
import { cached, remember } from '@/lib/cache';
import { ICP_LABEL, attentionOrder, overviewComponents, sourcesFor, type Icp, type Source } from '@/lib/overview-views';
import { useView } from '@/lib/use-view';
import { summarize, type Conversation, type Loaded, type State } from '@/lib/overview-summaries';
import { WorkspacePageHeader } from '@/components/shell/WorkspacePageHeader';
import { NativeOverview } from '@/components/overview/SummaryViews';
import { OverviewGuideButton, OverviewOnboarding } from '@/components/overview/OverviewOnboarding';
import { Worklist } from '@/components/worklist/Worklist';

const LOADERS: Record<Source, (siteId: string) => Promise<unknown>> = {
  deliveries: () => getJson<{ runs: RunListing[] }>('/runs').then(r => r.runs),
  signals: () => listSignals({ status: 'open' }).then(r => r.signals),
  quality: () => listQuality().then(r => r.items),
  workbench: siteId => listPlans(siteId).then(r => r.plans),
  connections: () => connectorRequest<{ items: Connector[] }>('/connectors').then(r => r.items),
  assistant: () => processRequest<{ conversations: Conversation[] }>('/v1/process-model/conversations').then(r => r.conversations),
};
// Coming back to the overview within a minute reuses what was just read instead of asking the server again.
const FRESH_MS = 60_000;
type Kept = { loaded: Loaded; at: Partial<Record<Source, number>> };

// A renderer failure must leave every summary and link on the landing page.
class SurfaceBoundary extends Component<{ children: ReactNode; fallback: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() { return this.state.failed ? this.props.fallback : this.props.children; }
}

export function WorkspaceDashboard() {
  const { user, organization } = useWorkspace();
  const { demo } = useDemo();
  const isDemo = !!demo;
  const orgId = organization?.id ?? '';
  const siteId = organization?.site_ids?.[0] ?? 'NF1';
  const { icp, choose } = useView(demo?.persona);

  const cacheKey = `overview:${orgId}`;
  const [loaded, setLoaded] = useState<Loaded>(() => cached<Kept>(cacheKey)?.loaded ?? {});
  const [state, setState] = useState<State>({});
  const [attempt, setAttempt] = useState(0);
  // The worklist leads the page. The summaries can still load if the worklist cannot be read.
  const [worklist, setWorklist] = useState<'loading' | 'ready' | 'failed'>('loading');
  const sources = useMemo(() => sourcesFor(icp, isDemo), [icp, isDemo]);
  useEffect(() => {
    if (!orgId) return;
    let active = true;
    const kept = cached<Kept>(cacheKey) ?? { loaded: {}, at: {} };
    setLoaded(kept.loaded);
    const now = Date.now();
    const stale = sources.filter(source => attempt || !kept.at[source] || now - kept.at[source]! > FRESH_MS);
    setState(Object.fromEntries(sources.map(source => [source, stale.includes(source) ? 'loading' : 'ready'])) as State);
    for (const source of stale) {
      LOADERS[source](siteId).then(value => {
        const current = cached<Kept>(cacheKey) ?? { loaded: {}, at: {} };
        const next = { loaded: { ...current.loaded, [source]: value }, at: { ...current.at, [source]: Date.now() } };
        remember(cacheKey, next);
        if (active) { setLoaded(next.loaded); setState(s => ({ ...s, [source]: 'ready' })); }
      }).catch((error: Error) => { if (active) setState(s => ({ ...s, [source]: { error: error.message } })); });
    }
    return () => { active = false; };
  }, [orgId, siteId, cacheKey, sources, attempt]);

  const model = useMemo(() => {
    // Sample deliveries a person opened while exploring are not their own work; a demo workspace has only samples.
    const runs = loaded.deliveries?.filter(r => !r.superseded_by && (isDemo || (!isDemoCmo(r.cmo) && !r.cmo.includes('· demo '))));
    return summarize({ ...loaded, deliveries: runs }, state, demo?.scenarios?.length ?? 0, attentionOrder(icp, isDemo));
  }, [loaded, state, icp, isDemo, demo?.scenarios?.length]);
  const failures = sources.filter(source => typeof state[source] === 'object');
  const busy = !organization || sources.some(source => state[source] === 'loading');
  const firstName = String(user?.user_metadata?.full_name || '').split(' ')[0];
  const fallback = <NativeOverview components={overviewComponents(icp, isDemo)} model={model} />;

  return <div className="workspace-page" data-testid="workspace-dashboard">
    <WorkspacePageHeader title={firstName ? `Welcome back, ${firstName}` : 'Overview'} description=""
      actions={<><OverviewGuideButton /><label className="overview-view">View<select id="overview-view" data-guide="overview-view" value={icp} onChange={e => choose(e.target.value as Icp)}>
        {(Object.keys(ICP_LABEL) as Icp[]).map(key => <option key={key} value={key}>{ICP_LABEL[key]}</option>)}
      </select></label></>} />
    <OverviewOnboarding worklist={worklist} />
    {!!failures.length && <div role="alert" className="workspace-alert compact"><div><strong>Some information is unavailable.</strong> The affected summaries say why. Nothing has been changed.</div><button type="button" className="chrome-button" onClick={() => setAttempt(i => i + 1)}><RotateCw size={13} />Try again</button></div>}
    {organization && <Worklist key={`${orgId}:${siteId}:${attempt}`} siteId={siteId} onState={setWorklist} retryElsewhere={!!failures.length} />}
    {(!organization || worklist === 'failed') && <section className="attention-summary" aria-label="Workspace status" aria-busy={busy}>
      <p className="lead" role="status" tabIndex={-1} data-guide="overview-status">{organization ? 'The latest worklist couldn’t be read.' : 'Checking what needs your attention…'}</p>
      {organization && <p className="mt-1 text-sm text-text-secondary">Use the summaries below to see which areas are available.</p>}
    </section>}
    {/* Wait for the organization so a person never sees someone else's view flash by before their own. */}
    {organization && <SurfaceBoundary key={`${icp}:${isDemo}`} fallback={fallback}>
      {/* The plain view paints first; the A2UI surface replaces it once its code has loaded. */}
      <SurfaceOrFallback icp={icp} demo={isDemo} model={model} fallback={fallback} />
    </SurfaceBoundary>}
  </div>;
}

function SurfaceOrFallback({ icp, demo, model, fallback }: { icp: Icp; demo: boolean; model: ReturnType<typeof summarize>; fallback: ReactNode }) {
  const [Surface, setSurface] = useState<typeof import('@/components/overview/OverviewSurface').default | null>(null);
  useEffect(() => {
    let active = true;
    void import('@/components/overview/OverviewSurface').then(module => { if (active) setSurface(() => module.default); }).catch(error => { console.warn('A2UI overview: showing the plain view', error); });
    return () => { active = false; };
  }, []);
  return Surface ? <Surface icp={icp} demo={demo} model={model} /> : <>{fallback}</>;
}
