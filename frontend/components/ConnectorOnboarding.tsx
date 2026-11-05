'use client';
import { SourceVerificationPanel } from '@/components/SourceVerificationPanel';
import { useCallback, useEffect, useState, type FormEvent } from 'react';
import Link from 'next/link';
import { ArrowLeft, ArrowRight, Check, Database, ShieldCheck, RefreshCw, Plus, Loader2, Upload } from 'lucide-react';
import { connectorRequest, configuration, type Catalog, type Connector, type Identity, type Mapping, type Product } from '@/lib/connectors-api';
import { FAMILIES as families, PRODUCT_ICONS } from '@/lib/connector-labels';
import { GuidedConnection, type GuidedStep } from '@/components/GuidedConnection';
import { useSession } from '@/lib/auth';
const every = (seconds: number) => seconds % 86400 === 0 ? (seconds === 86400 ? 'daily' : `every ${seconds / 86400} days`) : seconds % 3600 === 0 ? (seconds === 3600 ? 'hourly' : `every ${seconds / 3600} hours`) : seconds % 60 === 0 ? `every ${seconds / 60} min` : `every ${seconds}s`;
const syncSummary = (result: unknown) => { const r = (result ?? {}) as { ingested?: number; duplicates?: number }; return `${r.ingested ?? 0} new record${r.ingested === 1 ? '' : 's'}${r.duplicates ? `, ${r.duplicates} already collected` : ''}.`; };
const GUIDED_STEPS: [GuidedStep, string][] = [['signin', 'Sign in'], ['choose', 'Choose data'], ['fields', 'Check fields'], ['collect', 'Start collecting']];
const transports: Record<string, string> = { rest: 'REST API', file: 'Server folder', webhook: 'Signed webhook', mqtt: 'MQTT', opcua: 'OPC UA' };
const empty = (family: string, me: Identity): Connector => ({ connector_id: '', family, transport: 'rest', site_id: me.site_ids[0] || '', owner: me.actor_id, vendor: 'generic', version: '1', options: { poll_seconds: 0, events_path: '/events' }, enabled: true, write_operations: [] });
type Preview = {
    ok: boolean;
    records_sampled?: number;
    preview?: {
        rows?: {
            source_record_id: string;
            fields: Record<string, unknown>;
        }[];
        errors?: unknown[];
        template_problems?: unknown[];
    };
    [key: string]: unknown;
};
export function ConnectorOnboarding({ embedded = false }: { embedded?: boolean }) {
    const { mode } = useSession();
    const [me, setMe] = useState<Identity | null>(null);
    const [catalog, setCatalog] = useState<Catalog | null>(null);
    const [items, setItems] = useState<Connector[]>([]);
    const [draft, setDraft] = useState<Connector | null>(null);
    const [stage, setStage] = useState(0);
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState('');
    const [error, setError] = useState('');
    const [notice, setNotice] = useState('');
    const [preview, setPreview] = useState<Preview | null>(null);
    const [saved, setSaved] = useState(false);
    const [editingId, setEditingId] = useState('');
    const [interval, setInterval] = useState(300);
    const [verificationId, setVerificationId] = useState<string | null>(null);
    const [sourceQuery, setSourceQuery] = useState('');
    const [guided, setGuided] = useState<{ product: Product; existing?: Connector } | null>(null);
    const [guidedStep, setGuidedStep] = useState<GuidedStep>('signin');
    const [advanced, setAdvanced] = useState(false);
    const onGuidedStep = useCallback((step: GuidedStep) => setGuidedStep(step), []);
    const refresh = useCallback(async () => {
        const connections = await connectorRequest<{
            items: Connector[];
        }>('/connectors');
        setItems(connections.items);
    }, []);
    const load = useCallback(async () => {
        setLoading(true);
        setError('');
        try {
            const [identity, available, connections] = await Promise.all([connectorRequest<Identity>('/me'), connectorRequest<Catalog>('/connectors/catalog'), connectorRequest<{
                    items: Connector[];
                }>('/connectors')]);
            setMe(identity);
            setCatalog(available);
            setItems(connections.items);
        }
        catch (err) {
            setError((err as Error).message);
        }
        finally {
            setLoading(false);
        }
    }, []);
    useEffect(() => { void load(); }, [load]);
    const change = (key: keyof Connector, value: unknown) => { setDraft(d => d ? { ...d, [key]: value, ...(key === 'mapping' ? { mapping_confirmed: false } : {}) } : null); setSaved(false); setPreview(null); };
    const option = (key: string, value: string | string[]) => {
        setDraft(d => {
            if (!d)
                return null;
            const options = { ...d.options };
            if (value === '')
                delete options[key];
            else
                options[key] = value;
            return { ...d, options };
        });
        setSaved(false);
        setPreview(null);
    };
    const run = async (name: string, task: () => Promise<void>) => {
        setBusy(name);
        setError('');
        setNotice('');
        try {
            await task();
        }
        catch (err) {
            setError((err as Error).message);
        }
        finally {
            setBusy('');
        }
    };
    const productOf = (c: Connector) => catalog?.products.find(p => p.product === c.transport);
    const openGuided = (product: Product, existing?: Connector) => { setGuided({ product, existing }); setGuidedStep('signin'); setVerificationId(null); setError(''); setNotice(''); window.scrollTo({ top: 0, behavior: 'smooth' }); };
    const closeGuided = () => { setGuided(null); setStage(0); void refresh().catch(() => undefined); };
    const edit = (c: Connector) => { const product = productOf(c); if (product) return openGuided(product, c); setAdvanced(true); setDraft(configuration(c)); setEditingId(c.connector_id); setSaved(true); setPreview(null); setStage(1); setInterval(Number(c.options.poll_seconds) || 0); setError(''); setNotice('Saving changes returns this connection to manual mode for testing.'); };
    const choose = (family: string) => {
        if (!me)
            return;
        setDraft(empty(family, me));
        setEditingId('');
        setStage(1);
        setSaved(false);
        setPreview(null);
        setError('');
        setNotice('');
    };
    const save = (event: FormEvent) => {
        event.preventDefault();
        if (!draft)
            return;
        void run('save', async () => {
            if (items.some(c => c.connector_id === draft.connector_id && c.connector_id !== editingId))
                throw new Error('This connection ID already exists. Choose a new ID or manage the saved connection below.');
            const result = await connectorRequest<Connector>('/connectors', configuration({ ...draft, options: { ...draft.options, poll_seconds: 0 } }));
            setDraft(result);
            setEditingId(result.connector_id);
            setSaved(true);
            setStage(2);
            await refresh();
            setNotice('Connection saved in manual mode. Test the source before starting collection.');
        });
    };
    const test = () => {
        if (!draft)
            return;
        void run('test', async () => {
            const result = await connectorRequest<Preview>(`/connectors/${encodeURIComponent(draft.connector_id)}/preview`, {});
            setPreview(result);
            setNotice(result.ok ? 'Source preview passed. Review the mapping results below. No records were ingested.' : 'The source preview found a problem. Review the results before starting collection.');
        });
    };
    const activate = () => {
        if (!draft)
            return;
        void run('activate', async () => {
            // Run the first real sync before enabling the recurring schedule.
            const result = await connectorRequest<Record<string, unknown>>(`/connectors/${encodeURIComponent(draft.connector_id)}/sync`, {});
            await refresh();
            setNotice('First sync completed. Saving the collection schedule…');
            const next = await connectorRequest<Connector>('/connectors', configuration({ ...draft, options: { ...draft.options, poll_seconds: interval } }));
            setDraft(next);
            await refresh();
            setStage(3);
            setNotice(`First sync finished. ${interval ? 'Recurring collection is enabled.' : 'Manual collection is selected.'} ${syncSummary(result)}`);
        });
    };
    const manage = (c: Connector, action: 'sync' | 'toggle') => void run(`${action}:${c.connector_id}`, async () => {
        if (action === 'sync') {
            const result = await connectorRequest(`/connectors/${encodeURIComponent(c.connector_id)}/sync`, {});
            setNotice(`Sync finished for ${c.connector_id}: ${syncSummary(result)}`);
        }
        else {
            await connectorRequest('/connectors', configuration({ ...c, enabled: !c.enabled }));
            setNotice(`${c.connector_id} ${c.enabled ? 'paused' : 'resumed'}.`);
        }
        await refresh();
    });
    const finishOnboarding = () => void run('finish', async () => {
        if (mode === 'supabase' && me?.roles.includes('admin'))
            await connectorRequest('/organization/onboarding/complete', {});
        window.location.assign('/dashboard/');
    });
    const o = draft?.options || {};
    const steps = guided || !advanced ? ['Choose a system', ...GUIDED_STEPS.map(([, label]) => label)] : ['Choose a source', 'Configure access', 'Test & start collection', 'Ready to work'];
    const current = guided ? (guidedStep === 'done' ? steps.length : GUIDED_STEPS.findIndex(([s]) => s === guidedStep) + 1) : advanced ? stage : 0;
    const query = sourceQuery.trim().toLowerCase();
    const shownProducts = (catalog?.products ?? []).filter(p => `${p.name} ${p.category} ${p.description}`.toLowerCase().includes(query));
    return <div className={`setup-main ${embedded ? 'setup-embedded' : ''}`}>
    <aside className="setup-sidebar"><p className="setup-eyebrow">LET’S GET YOU STARTED</p><h1>Make room for<br />your data.</h1><p>Connect the tools you use.<br />Keep working the way you work.</p>
      <ol className="setup-steps">{steps.map((label, i) => <li key={label} aria-current={current === i ? 'step' : undefined} className={i <= current ? 'active' : ''}><span>{current > i ? <Check size={14}/> : i + 1}</span>{label}</li>)}</ol>
      <div className="setup-assurance"><ShieldCheck size={21}/><strong>Read access. Clear boundaries.</strong><p>Source records stay in your existing systems. Connections created here cannot write back.</p></div>
      {me && <p className="setup-identity">Workspace: {me.tenant_id}<br />{mode === 'development' ? `Local test account · ${me.actor_id}` : me.actor_id}</p>}
    </aside>
    <section className="setup-content" aria-busy={!!busy || loading}>
      <div className="setup-content-top"><span>{embedded ? 'DATA CONNECTIONS' : 'WELCOME TO YOUR WORKSPACE'}</span><span>Step {Math.min(current + 1, steps.length)} of {steps.length}</span></div>
      {error && <div className="setup-message error" role="alert">{error} {!catalog && <button className="setup-text-link" onClick={load}>Try again</button>}</div>}
      {notice && <div className="setup-message" role="status">{notice}</div>}
      {loading ? <p role="status" className="setup-loading"><Loader2 className="animate-spin" size={20}/> Loading your workspace and available connections…</p> : <>
      {guided && me && <GuidedConnection key={`${guided.product.product}:${guided.existing?.connector_id ?? 'new'}`} product={guided.product} me={me} existing={guided.existing} taken={items.map(c => c.connector_id)} onStep={onGuidedStep} onChanged={refresh} onExit={closeGuided} onVerify={cid => { closeGuided(); setVerificationId(cid); window.setTimeout(() => document.getElementById('source-verification')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 300); }} />}
      {!guided && stage === 0 && !advanced && <><h2>Connect a system</h2><p className="setup-subtitle">Pick where your data lives. You&rsquo;ll sign in, choose what to collect and check a sample before any data is collected.</p>
        <label className="source-catalog-search"><Database size={15}/><input aria-label="Search systems" type="search" placeholder="Find a system…" value={sourceQuery} onChange={e => setSourceQuery(e.target.value)}/></label>
        <div className="connector-grid">{shownProducts.map(p => { const Icon = PRODUCT_ICONS[p.product] ?? Database; return <button key={p.product} className="connector-choice" onClick={() => openGuided(p)}><span className="connector-icon"><Icon size={23} strokeWidth={1.5}/></span><span className="connector-kind">{p.category.toUpperCase()}</span><strong>{p.name}</strong><span>{p.description}</span><ArrowRight size={17} className="connector-arrow"/></button>; })}
          <Link href="/cmo/" className="connector-choice"><span className="connector-icon"><Upload size={23} strokeWidth={1.5}/></span><span className="connector-kind">ANY SYSTEM</span><strong>Upload files instead</strong><span>For systems without a connection: upload exports (PDF, Excel, CSV). Every value is checked against its source.</span><ArrowRight size={17} className="connector-arrow"/></Link></div>
        {catalog && !shownProducts.length && <p className="setup-fine" role="status">No systems match your search. You can still upload files or use a REST API connection.</p>}
        <p className="setup-fine">Is your system only reachable inside your plant network? Upload its exports for now. Need MQTT, OPC UA, webhooks or a server folder? <button className="setup-text-link" onClick={() => { setAdvanced(true); setError(''); setNotice(''); }}>Use an advanced connection</button> (for IT administrators).</p></>}
      {!guided && stage === 0 && advanced && <><button className="setup-back" onClick={() => setAdvanced(false)}><ArrowLeft size={15}/> All systems</button><h2>Advanced connection</h2><p className="setup-subtitle">Protocol-level connections configured with server-side credentials. Your administrator must install secrets and approve hosts on the API server first.</p><div className="connector-grid">{catalog?.families.map(f => {
                    const details = families[f.system] || { title: f.system, description: f.record_type, icon: Database };
                    const Icon = details.icon;
                    return <button key={f.system} className="connector-choice" onClick={() => choose(f.system)}><span className="connector-icon"><Icon size={23} strokeWidth={1.5}/></span><span className="connector-kind">{f.system}</span><strong>{details.title}</strong><span>{details.description}</span><ArrowRight size={17} className="connector-arrow"/></button>;
                })}</div></>}
      {!guided && stage === 1 && draft && <><button className="setup-back" onClick={() => setStage(0)}><ArrowLeft size={15}/> All sources</button><h2>Connect your {draft.family}.</h2><p className="setup-subtitle">Use access approved by your system owner. Start with a manual test.</p>
        <form className="connector-form" onSubmit={save}><div className="setup-two-columns"><label>Connection ID<input readOnly={!!editingId} required pattern="[A-Za-z0-9_.-]{1,80}" maxLength={80} placeholder="e.g. mesa-lims" value={draft.connector_id} onChange={e => change('connector_id', e.target.value)}/></label>
        <label>Site{me?.site_ids.length ? <select value={draft.site_id} onChange={e => change('site_id', e.target.value)}>{me.site_ids.map(s => <option key={s}>{s}</option>)}</select> : <input required placeholder="Your authorized site ID" value={draft.site_id} onChange={e => change('site_id', e.target.value)}/>}</label></div>
        <label>CDMO / source group <span className="setup-optional">optional</span><input maxLength={120} placeholder="e.g. northfield-cdmo" value={draft.source_group || ''} onChange={e => change('source_group', e.target.value || undefined)}/><small>Use the same group for this CDMO’s lab and process connections. Checks compare records within this site and group.</small></label>
        <label>Connection method<select value={draft.transport} onChange={e => { change('transport', e.target.value); change('options', { poll_seconds: 0 }); }}>{catalog?.transports.map(t => <option key={t.transport} value={t.transport} disabled={!t.available}>{transports[t.transport]}{!t.available ? ' — unavailable on this server' : ''}</option>)}</select></label>
        {['rest', 'mqtt', 'opcua'].includes(draft.transport) && <label>Source endpoint<input required placeholder={draft.transport === 'rest' ? 'https://your-system.example.com/api' : draft.transport === 'mqtt' ? 'mqtts://broker.example.com:8883' : 'opc.tcp://server.example.com:4840'} value={String(o.base_url || '')} onChange={e => option('base_url', e.target.value)}/><small>Your administrator must allow this host on the API server.</small></label>}
        {draft.transport === 'rest' && <><label>Records path<input required placeholder="/events" value={String(o.events_path || '')} onChange={e => option('events_path', e.target.value)}/></label><label>Read credential reference <span className="setup-optional">optional</span><input pattern="[A-Za-z_][A-Za-z0-9_]*" placeholder="e.g. MESA_LIMS_READ_TOKEN" value={String(o.auth_env || '')} onChange={e => option('auth_env', e.target.value)}/><small>Name of a secret installed on the API server. Do not paste a token here.</small></label></>}
        {draft.transport === 'file' && <label>Server folder<input required placeholder="/data/connectors/lims" value={String(o.directory || '')} onChange={e => option('directory', e.target.value)}/><small>A folder on the server, inside the administrator’s allowed connector root.</small></label>}
        {draft.transport === 'webhook' && <label>Signing secret reference<input required pattern="[A-Za-z_][A-Za-z0-9_]*" placeholder="MESA_WEBHOOK_SECRET" value={String(o.secret_env || '')} onChange={e => option('secret_env', e.target.value)}/><small>Use the name of a secret installed on the API server.</small></label>}
        {['mqtt', 'opcua'].includes(draft.transport) && <><label>{draft.transport === 'mqtt' ? 'Topics' : 'Node IDs'}<textarea required placeholder="One per line" value={Array.isArray(o.addresses) ? o.addresses.join('\n') : ''} onChange={e => option('addresses', e.target.value.split('\n'))}/></label>{draft.transport === 'opcua' ? <label>Security configuration reference<input required pattern="[A-Za-z_][A-Za-z0-9_]*" value={String(o.security_string_env || '')} onChange={e => option('security_string_env', e.target.value)}/></label> : <div className="setup-two-columns">{['username_env', 'password_env'].map(key => <label key={key}>{key === 'username_env' ? 'Username secret reference' : 'Password secret reference'}<input pattern="[A-Za-z_][A-Za-z0-9_]*" value={String(o[key] || '')} onChange={e => option(key, e.target.value)}/></label>)}</div>}</>}
        <details className="setup-details"><summary>Field mapping & response format</summary><p>Map source fields to the platform fields. Source identifiers and timestamps remain attached to ingested evidence.</p>{draft.transport === 'rest' && <div className="setup-two-columns">{[['records_field', 'Records field', 'records'], ['next_checkpoint_field', 'Next checkpoint field', 'next_checkpoint'], ['id_field', 'Record ID field', 'id'], ['timestamp_field', 'Timestamp field', 'timestamp']].map(([key, label, placeholder]) => <label key={key}>{label}<input placeholder={placeholder} value={String(o[key] || '')} onChange={e => option(key, e.target.value)}/></label>)}</div>}
        {(draft.mapping || catalog?.families.find(f => f.system === draft.family)?.template)?.fields.map((field, i) => <label key={field.canonical}>{field.canonical}<input required value={field.source} onChange={e => {
                        const mapping = draft.mapping || catalog?.families.find(f => f.system === draft.family)?.template;
                        if (mapping)
                            change('mapping', { ...mapping, fields: mapping.fields.map((f, n) => n === i ? { ...f, source: e.target.value } : f) } as Mapping);
                    }}/></label>)}<label className="source-confirm-mapping"><input type="checkbox" checked={draft.mapping_confirmed || false} onChange={e => change('mapping_confirmed', e.target.checked)}/><span>I checked this mapping against the source. Values that pass all checks may be accepted automatically.</span></label></details>
        <button className="setup-primary" disabled={!!busy} type="submit">{busy ? 'Saving…' : 'Save & continue'} <ArrowRight size={17}/></button></form></>}
      {!guided && stage === 2 && draft && <><h2>Make sure it connects.</h2><p className="setup-subtitle">{draft.connector_id} · {transports[draft.transport]} · {draft.site_id}</p>
        {draft.transport === 'webhook' ? <div className="setup-message"><strong>Your webhook receiver</strong><code>/v1/webhooks/{me?.tenant_id}/{draft.connector_id}</code><p>Send signed deliveries to this path on the API server. Webhooks receive data when your source sends it; recurring polling is not needed.</p><button className="setup-primary" onClick={() => setStage(3)}>Finish setup <Check size={16}/></button></div> : <>
        <div className="connection-test"><Database size={28}/><strong>{draft.connector_id}</strong><span>Saved · {saved ? 'ready to test' : 'manual mode'}</span>{draft.transport !== 'mqtt' ? <button className="setup-secondary" disabled={!!busy} onClick={test}>{busy === 'test' ? 'Testing…' : 'Test connection & mapping'}</button> : <p>MQTT begins durable collection with the first sync. Review your topics and mapping before starting.</p>}</div>
        {preview && <div className="setup-preview"><h3>{preview.ok ? 'Source reached · mapping passed' : 'Preview needs attention'}</h3>{!preview.ok && <p className="setup-message error">{preview.error ? String(preview.error) : 'Review the field mappings and source details below, then configure this connection again.'}</p>}<p className="setup-fine">{preview.records_sampled ?? 0} records sampled. Source records have not been ingested.</p>{preview.preview?.rows?.slice(0, 3).map(row => <div className="preview-record" key={row.source_record_id}><strong>Source record: {row.source_record_id}</strong><dl>{Object.entries(row.fields).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{typeof value === 'object' ? JSON.stringify(value) : String(value ?? 'Missing')}</dd></div>)}</dl></div>)}<details className="setup-details"><summary>Inspect source and mapping details</summary><pre>{JSON.stringify(preview, null, 2)}</pre></details></div>}
        <label className="setup-poll">Collection schedule<select value={interval} onChange={e => setInterval(Number(e.target.value))}><option value={0}>Manual only</option><option value={60}>Every minute</option><option value={300}>Every 5 minutes</option><option value={900}>Every 15 minutes</option><option value={3600}>Every hour</option></select></label>
        <p className="setup-fine">Starting collection reads source data into this workspace. Recurring sync runs on the server and can be paused below.</p><button className="setup-primary" disabled={!!busy || (draft.transport !== 'mqtt' && (!preview?.ok))} onClick={activate}>{busy === 'activate' ? 'Starting collection…' : 'Run first sync & finish'} <ArrowRight size={17}/></button></>}
        <button className="setup-text-link" disabled={!!busy} onClick={() => { setStage(0); setDraft(null); }}>Keep saved and return to connections</button></>}
      {!guided && stage === 3 && <div className="setup-complete"><span><Check size={28}/></span><h2>Your source is set up.</h2><p>Review collection status below, add another source, or start working with your data.</p><button className="setup-primary" onClick={() => { setStage(0); setDraft(null); setNotice(''); setAdvanced(false); }}><Plus size={17}/> Add another source</button><button disabled={!!busy} className="setup-text-link" onClick={finishOnboarding}>Open workspace <ArrowRight size={16}/></button></div>}
      {!guided && items.length > 0 && <section className="saved-connections"><div><h3>Your connections <span>{items.length}</span></h3><button aria-label="Refresh connections" disabled={!!busy} onClick={() => void run('refresh', refresh)}><RefreshCw size={16}/></button></div>{items.map(c => { const product = productOf(c); const Icon = product ? PRODUCT_ICONS[product.product] ?? Database : families[c.family]?.icon ?? Database; return <article key={c.connector_id}><Icon size={20}/><div><strong>{c.connector_id}</strong><p>{product?.name ?? transports[c.transport] ?? c.transport} · {families[c.family]?.title ?? c.family} · {c.site_id} · {!c.enabled ? 'Paused' : Number(c.options.poll_seconds) ? `Checks ${every(Number(c.options.poll_seconds))}` : c.transport === 'webhook' ? 'Receives webhooks' : 'Manual sync'}</p><p>{c.last_sync ? `Last attempt: ${new Date(c.last_sync).toLocaleString()}` : 'No sync attempt recorded'}{c.last_error && <span className="connection-error"> · {c.last_error}</span>}</p></div><div className="connection-actions"><button disabled={!!busy} onClick={() => setVerificationId(c.connector_id)}>Verify data</button><button disabled={!!busy} onClick={() => edit(c)}>Configure</button><button disabled={!!busy} onClick={() => manage(c, 'toggle')}>{c.enabled ? 'Pause' : 'Resume'}</button>{c.transport !== 'webhook' && <button disabled={!!busy || !c.enabled} onClick={() => manage(c, 'sync')}>{busy === `sync:${c.connector_id}` ? 'Syncing…' : 'Sync now'}</button>}</div></article>; })}</section>}
      {verificationId && <><button id="source-verification" className="setup-text-link" onClick={() => setVerificationId(null)}>Close source verification</button><SourceVerificationPanel key={verificationId} connectorId={verificationId}/></>}
      {!guided && <div className="setup-bottom"><button disabled={!!busy || loading} onClick={finishOnboarding}>Continue without adding a source <ArrowRight size={15}/></button><span>You can return here anytime.</span></div>}
      </>}
    </section>
  </div>;
}
