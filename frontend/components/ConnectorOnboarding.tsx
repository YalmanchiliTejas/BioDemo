'use client';
import { SourceVerificationPanel } from '@/components/SourceVerificationPanel';
import { useCallback, useEffect, useState, type FormEvent } from 'react';
import Link from 'next/link';
import { ArrowLeft, ArrowRight, Check, Database, FlaskConical, ShieldCheck, Activity, BookOpen, Wrench, Boxes, Factory, RefreshCw, Plus, Loader2 } from 'lucide-react';
import { connectorRequest, configuration, type Catalog, type Connector, type Identity, type Mapping } from '@/lib/connectors-api';
import { useSession } from '@/lib/auth';
const families: Record<string, {
    title: string;
    description: string;
    icon: typeof Database;
}> = {
    MES: { title: 'Manufacturing', description: 'Batch records, orders & production events', icon: Factory },
    LIMS: { title: 'Laboratory', description: 'Samples, tests & laboratory results', icon: FlaskConical },
    QMS: { title: 'Quality', description: 'Deviations, CAPAs & quality records', icon: ShieldCheck },
    HISTORIAN: { title: 'Historian', description: 'Process measurements & equipment tags', icon: Activity },
    ERP: { title: 'Enterprise resources', description: 'Materials, lots & resource planning', icon: Boxes },
    ELN: { title: 'Lab notebooks', description: 'Experiments & research context', icon: BookOpen },
    CMMS: { title: 'Maintenance', description: 'Equipment & maintenance work orders', icon: Wrench },
    WMS: { title: 'Warehouse', description: 'Inventory, storage locations & stock', icon: Database },
};
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
export function ConnectorOnboarding() {
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
    const edit = (c: Connector) => { setDraft(configuration(c)); setEditingId(c.connector_id); setSaved(true); setPreview(null); setStage(1); setInterval(Number(c.options.poll_seconds) || 0); setError(''); setNotice('Saving changes returns this connection to manual mode for testing.'); };
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
            setNotice(`First sync finished. ${interval ? 'Recurring collection is enabled.' : 'Manual collection is selected.'} Sync result: ${JSON.stringify(result)}`);
        });
    };
    const manage = (c: Connector, action: 'sync' | 'toggle') => void run(`${action}:${c.connector_id}`, async () => {
        if (action === 'sync') {
            const result = await connectorRequest(`/connectors/${encodeURIComponent(c.connector_id)}/sync`, {});
            setNotice(`Sync finished for ${c.connector_id}: ${JSON.stringify(result)}`);
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
        window.location.assign('/cmo/');
    });
    const o = draft?.options || {};
    return <main className="setup-main">
    <aside className="setup-sidebar"><p className="setup-eyebrow">YOUR WORKSPACE, CONNECTED</p><h1>Start with what<br />you already know.</h1><p>Connect a source. Check the data.<br />Build from there.</p>
      <ol className="setup-steps">{['Choose a source', 'Configure access', 'Test & start collection', 'Ready to work'].map((label, i) => <li key={label} aria-current={stage === i ? 'step' : undefined} className={i <= stage ? 'active' : ''}><span>{stage > i ? <Check size={14}/> : i + 1}</span>{label}</li>)}</ol>
      <div className="setup-assurance"><ShieldCheck size={21}/><strong>Read access. Clear boundaries.</strong><p>Source records stay in your existing systems. Connections created here cannot write back.</p></div>
      {me && <p className="setup-identity">Workspace: {me.tenant_id}<br />{mode === 'development' ? 'Development identity' : me.actor_id}</p>}
    </aside>
    <section className="setup-content" aria-busy={!!busy || loading}>
      <div className="setup-content-top"><span>WORKSPACE SETUP</span><span>{stage + 1} / 4</span></div>
      {mode === 'development' && <div className="setup-message">Development mode: using the local API identity. Configure Supabase before onboarding real users.</div>}
      {error && <div className="setup-message error" role="alert">{error} {!catalog && <button className="setup-text-link" onClick={load}>Try again</button>}</div>}
      {notice && <div className="setup-message" role="status">{notice}</div>}
      {loading ? <p role="status" className="setup-loading"><Loader2 className="animate-spin" size={20}/> Loading your workspace and available connections…</p> : <>
      {stage === 0 && <><h2>Where does your data live?</h2><p className="setup-subtitle">Choose a system to connect. You can add more at any time.</p><div className="connector-grid">{catalog?.families.map(f => {
                    const details = families[f.system] || { title: f.system, description: f.record_type, icon: Database };
                    const Icon = details.icon;
                    return <button key={f.system} className="connector-choice" onClick={() => choose(f.system)}><span className="connector-icon"><Icon size={23} strokeWidth={1.5}/></span><span className="connector-kind">{f.system}</span><strong>{details.title}</strong><span>{details.description}</span><ArrowRight size={17} className="connector-arrow"/></button>;
                })}</div><p className="setup-fine">Connectors use configurable source mappings. Vendor qualification has not been performed.</p></>}
      {stage === 1 && draft && <><button className="setup-back" onClick={() => setStage(0)}><ArrowLeft size={15}/> All sources</button><h2>Connect your {draft.family}.</h2><p className="setup-subtitle">Use access approved by your system owner. Start with a manual test.</p>
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
      {stage === 2 && draft && <><h2>Make sure it connects.</h2><p className="setup-subtitle">{draft.connector_id} · {transports[draft.transport]} · {draft.site_id}</p>
        {draft.transport === 'webhook' ? <div className="setup-message"><strong>Your webhook receiver</strong><code>/v1/webhooks/{me?.tenant_id}/{draft.connector_id}</code><p>Send signed deliveries to this path on the API server. Webhooks receive data when your source sends it; recurring polling is not needed.</p><button className="setup-primary" onClick={() => setStage(3)}>Finish setup <Check size={16}/></button></div> : <>
        <div className="connection-test"><Database size={28}/><strong>{draft.connector_id}</strong><span>Saved · {saved ? 'ready to test' : 'manual mode'}</span>{draft.transport !== 'mqtt' ? <button className="setup-secondary" disabled={!!busy} onClick={test}>{busy === 'test' ? 'Testing…' : 'Test connection & mapping'}</button> : <p>MQTT begins durable collection with the first sync. Review your topics and mapping before starting.</p>}</div>
        {preview && <div className="setup-preview"><h3>{preview.ok ? 'Source reached · mapping passed' : 'Preview needs attention'}</h3>{!preview.ok && <p className="setup-message error">{preview.error ? String(preview.error) : 'Review the field mappings and source details below, then configure this connection again.'}</p>}<p className="setup-fine">{preview.records_sampled ?? 0} records sampled. Source records have not been ingested.</p>{preview.preview?.rows?.slice(0, 3).map(row => <div className="preview-record" key={row.source_record_id}><strong>Source record: {row.source_record_id}</strong><dl>{Object.entries(row.fields).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{typeof value === 'object' ? JSON.stringify(value) : String(value ?? 'Missing')}</dd></div>)}</dl></div>)}<details className="setup-details"><summary>Inspect source and mapping details</summary><pre>{JSON.stringify(preview, null, 2)}</pre></details></div>}
        <label className="setup-poll">Collection schedule<select value={interval} onChange={e => setInterval(Number(e.target.value))}><option value={0}>Manual only</option><option value={60}>Every minute</option><option value={300}>Every 5 minutes</option><option value={900}>Every 15 minutes</option><option value={3600}>Every hour</option></select></label>
        <p className="setup-fine">Starting collection reads source data into this workspace. Recurring sync runs on the server and can be paused below.</p><button className="setup-primary" disabled={!!busy || (draft.transport !== 'mqtt' && (!preview?.ok))} onClick={activate}>{busy === 'activate' ? 'Starting collection…' : 'Run first sync & finish'} <ArrowRight size={17}/></button></>}
        <button className="setup-text-link" disabled={!!busy} onClick={() => { setStage(0); setDraft(null); }}>Keep saved and return to connections</button></>}
      {stage === 3 && <div className="setup-complete"><span><Check size={28}/></span><h2>Your source is set up.</h2><p>Review collection status below, add another source, or start working with your data.</p><button className="setup-primary" onClick={() => { setStage(0); setDraft(null); setNotice(''); }}><Plus size={17}/> Add another source</button><button disabled={!!busy} className="setup-text-link" onClick={finishOnboarding}>Open workspace <ArrowRight size={16}/></button></div>}
      {items.length > 0 && <section className="saved-connections"><div><h3>Your connections <span>{items.length}</span></h3><button aria-label="Refresh connections" disabled={!!busy} onClick={() => void run('refresh', refresh)}><RefreshCw size={16}/></button></div>{items.map(c => <article key={c.connector_id}><Database size={20}/><div><strong>{c.connector_id}</strong><p>{c.family} · {c.site_id} · {!c.enabled ? 'Paused' : Number(c.options.poll_seconds) ? `Every ${c.options.poll_seconds}s` : c.transport === 'webhook' ? 'Receives webhooks' : 'Manual'}</p><p>{c.last_sync ? `Last attempt: ${new Date(c.last_sync).toLocaleString()}` : 'No sync attempt recorded'}{c.last_error && <span className="connection-error"> · {c.last_error}</span>}</p></div><div className="connection-actions"><button disabled={!!busy} onClick={() => setVerificationId(c.connector_id)}>Verify data</button><button disabled={!!busy} onClick={() => edit(c)}>Configure</button><button disabled={!!busy} onClick={() => manage(c, 'toggle')}>{c.enabled ? 'Pause' : 'Resume'}</button>{c.transport !== 'webhook' && <button disabled={!!busy || !c.enabled} onClick={() => manage(c, 'sync')}>{busy === `sync:${c.connector_id}` ? 'Syncing…' : 'Sync now'}</button>}</div></article>)}</section>}
      {verificationId && <><button className="setup-text-link" onClick={() => setVerificationId(null)}>Close source verification</button><SourceVerificationPanel key={verificationId} connectorId={verificationId}/></>}
      <div className="setup-bottom"><button disabled={!!busy || loading} onClick={finishOnboarding}>Continue without adding a source <ArrowRight size={15}/></button><span>You can return here anytime.</span></div>
      </>}
    </section>
  </main>;
}
