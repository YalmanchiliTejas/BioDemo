'use client';
import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { ArrowLeft, ArrowRight, Check, Loader2, Search } from 'lucide-react';
import { connectorRequest, configuration, type Connector, type Discovery, type Identity, type Mapping, type Product, type Resource, type SourceField } from '@/lib/connectors-api';
import { FAMILIES, fieldLabel } from '@/lib/connector-labels';

type Preview = {
    ok: boolean;
    error?: string;
    records_sampled?: number;
    preview?: {
        rows?: { source_record_id: string; fields: Record<string, unknown> }[];
        errors?: { source_record_id?: string; field?: string; error?: string }[];
    };
};
type SyncResult = { ingested?: number; duplicates?: number };
export type GuidedStep = 'signin' | 'choose' | 'fields' | 'collect' | 'done';

const SCHEDULES: [number, string][] = [[0, 'Only when I click Sync'], [900, 'Every 15 minutes'], [3600, 'Every hour'], [86400, 'Once a day']];
const slug = (text: string) => text.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 60) || 'connection';
const show = (value: unknown): string => value === null || value === undefined || value === '' ? '—' : Array.isArray(value) ? value.map(show).join(', ') : typeof value === 'object' ? JSON.stringify(value) : String(value);

function newDraft(product: Product, me: Identity, taken: string[]): Connector {
    const base = slug(product.name.replace(/\(.*\)/, ''));
    let id = base;
    for (let n = 2; taken.includes(id); n++) id = `${base}-${n}`;
    return { connector_id: id, family: product.family ?? '', transport: product.product, site_id: me.site_ids[0] || '', owner: me.actor_id, vendor: product.product, version: '1', options: { poll_seconds: 0, ...(product.product === 'rest_api' ? { auth_type: 'bearer' } : {}) }, enabled: true, write_operations: [] };
}

export function GuidedConnection({ product, me, existing, taken, onStep, onChanged, onVerify, onExit }: {
    product: Product;
    me: Identity;
    existing?: Connector;
    taken: string[];
    onStep: (step: GuidedStep) => void;
    onChanged: () => Promise<void>;
    onVerify: (connectorId: string) => void;
    onExit: () => void;
}) {
    const [draft, setDraft] = useState<Connector>(() => existing ? configuration(existing) : newDraft(product, me, taken));
    const [creds, setCreds] = useState<Record<string, string>>({});
    const [savedCreds, setSavedCreds] = useState<string[]>(existing?.credential_fields ?? []);
    const [step, setStep] = useState<GuidedStep>('signin');
    const [resources, setResources] = useState<Resource[] | null>(null);
    const [search, setSearch] = useState('');
    const initial = existing ? (Array.isArray(existing.options.resources) ? existing.options.resources : existing.options.resource ? [String(existing.options.resource)] : []) : [];
    const [chosen, setChosen] = useState<string[]>(initial.map(String));
    const [labels, setLabels] = useState<Record<string, string>>({});
    const [columns, setColumns] = useState<SourceField[]>([]);
    const [idColumn, setIdColumn] = useState(String(existing?.options.id_column ?? ''));
    const [updatedColumn, setUpdatedColumn] = useState(String(existing?.options.updated_column ?? ''));
    const [fields, setFields] = useState<SourceField[]>([]);
    const [suggested, setSuggested] = useState<Mapping | null>(null);
    const [mapping, setMapping] = useState<Mapping | null>(existing?.mapping ?? null);
    const [dirty, setDirty] = useState(false);
    const [confirmed, setConfirmed] = useState(!!existing?.mapping_confirmed);
    const [preview, setPreview] = useState<Preview | null>(null);
    const [schedule, setSchedule] = useState(Number(existing?.options.poll_seconds) || 3600);
    const [result, setResult] = useState<SyncResult | null>(null);
    const [busy, setBusy] = useState('');
    const [error, setError] = useState('');
    useEffect(() => { onStep(step); }, [step, onStep]);
    const id = encodeURIComponent(draft.connector_id);
    const visible = product.fields.filter(f => !f.when || Object.entries(f.when).every(([key, values]) => values.includes(String(draft.options[key] ?? ''))));
    const run = async (name: string, task: () => Promise<void>) => {
        setBusy(name);
        setError('');
        try { await task(); }
        catch (err) { setError((err as Error).message); }
        finally { setBusy(''); }
    };
    const option = (key: string, value: string) => setDraft(d => {
        const options = { ...d.options };
        if (value === '') delete options[key];
        else options[key] = value;
        return { ...d, options };
    });
    const save = async (changes: Partial<Connector>, withCredentials = false) => {
        const next = { ...draft, ...changes };
        const credentials = Object.fromEntries(Object.entries(creds).filter(([, v]) => v.trim() !== ''));
        const saved = await connectorRequest<Connector>('/connectors', { ...configuration(next), ...(withCredentials ? { credentials } : {}) });
        setDraft(configuration(saved));
        if (withCredentials) {
            setSavedCreds(s => Array.from(new Set([...s, ...Object.keys(credentials)])));
            setCreds({});
        }
        await onChanged();
        return saved;
    };
    const discover = (body: { resource?: string; search?: string }) => connectorRequest<Discovery>(`/connectors/${id}/discover`, body);
    const test = async () => {
        const outcome = await connectorRequest<Preview>(`/connectors/${id}/preview`, {});
        setPreview(outcome);
        return outcome;
    };
    const applyFields = (found: Discovery, keepMapping: boolean) => {
        setFields(found.fields ?? []);
        setSuggested(found.suggested_mapping ?? null);
        const next = keepMapping && mapping ? mapping : found.suggested_mapping ?? null;
        setMapping(next);
        return next;
    };
    const loadColumns = async (resource: string, keepSelection: boolean) => {
        const found = await discover({ resource });
        const cols = found.fields ?? [];
        setColumns(cols);
        setFields(cols);
        setSuggested(found.suggested_mapping ?? null);
        if (keepSelection && idColumn && updatedColumn) return;
        setIdColumn(cols.find(c => /^(id|.*_id|.*id)$/i.test(c.name))?.name ?? cols[0]?.name ?? '');
        setUpdatedColumn(cols.find(c => /updated|modified|changed/i.test(c.name))?.name ?? cols.find(c => /timestamp|date|time/i.test(c.type))?.name ?? '');
    };

    const signIn = (event: FormEvent) => {
        event.preventDefault();
        void run('signin', async () => {
            if (!draft.family) throw new Error('Choose what kind of data this system holds.');
            if (!draft.site_id.trim()) throw new Error('Enter the site this data belongs to.');
            await save({ options: { ...draft.options, poll_seconds: 0 } }, true);
            if (product.resource) {
                setResources((await discover({})).resources ?? []);
                if (product.table && chosen.length) await loadColumns(chosen[0], true);
                setStep('choose');
            } else {
                const next = applyFields(await discover({}), !!existing);
                await save({ mapping: next ?? undefined, mapping_confirmed: false });
                await test();
                setStep('fields');
            }
        });
    };
    const searchResources = (event: FormEvent) => {
        event.preventDefault();
        void run('search', async () => setResources((await discover({ search })).resources ?? []));
    };
    const pick = (resource: Resource) => {
        setLabels(l => ({ ...l, [resource.id]: resource.label }));
        if (product.multiple) {
            setChosen(c => c.includes(resource.id) ? c.filter(x => x !== resource.id) : [...c, resource.id]);
            return;
        }
        setChosen([resource.id]);
        if (product.table) void run('columns', () => loadColumns(resource.id, false));
    };
    const confirmChoice = () => void run('choose', async () => {
        if (!chosen.length) throw new Error(`Choose ${product.multiple ? 'at least one of the' : 'a'} ${product.resource}.`);
        const previous = draft.options;
        const options: Connector['options'] = { ...previous, poll_seconds: 0 };
        if (product.multiple) {
            const before = Array.isArray(previous.resources) ? previous.resources : [];
            const beforeLabels = Array.isArray(previous.resource_labels) ? previous.resource_labels : [];
            options.resources = chosen;
            options.resource_labels = chosen.map(c => labels[c] ?? beforeLabels[before.indexOf(c)] ?? c);
        } else options.resource = chosen[0];
        if (product.table) {
            if (!idColumn || !updatedColumn) throw new Error('Choose the ID column and the last-updated column.');
            options.id_column = idColumn;
            options.updated_column = updatedColumn;
        }
        const sameChoice = JSON.stringify(initial) === JSON.stringify(chosen);
        const next = product.table && suggested
            ? (sameChoice && mapping ? mapping : suggested)
            : applyFields(await discover({ resource: chosen[0] }), sameChoice);
        if (product.table) setMapping(next);
        await save({ options, mapping: next ?? undefined, mapping_confirmed: false });
        setConfirmed(false);
        await test();
        setStep('fields');
    });
    const remap = (canonical: string, source: string) => {
        setMapping(m => m ? { ...m, fields: m.fields.map(f => f.canonical === canonical ? { ...f, source } : f) } : m);
        setDirty(true);
        setConfirmed(false);
    };
    const refreshPreview = () => void run('remap', async () => {
        await save({ mapping: mapping ?? undefined, mapping_confirmed: false });
        setDirty(false);
        await test();
    });
    const acceptFields = () => void run('fields', async () => {
        await save({ mapping: mapping ?? undefined, mapping_confirmed: confirmed });
        setStep('collect');
    });
    const start = () => void run('collect', async () => {
        const outcome = await connectorRequest<SyncResult>(`/connectors/${id}/sync`, {});
        setResult(outcome);
        await save({ options: { ...draft.options, poll_seconds: schedule } });
        setStep('done');
    });

    const sourceNames = useMemo(() => Array.from(new Set([...fields.map(f => f.name), ...(mapping?.fields.map(f => f.source).filter(Boolean) ?? [])])), [fields, mapping]);
    const filtered = (resources ?? []).filter(r => !search || `${r.label} ${r.detail}`.toLowerCase().includes(search.toLowerCase()));
    const back = (to: GuidedStep | null, label: string) => <button type="button" className="setup-back" disabled={!!busy} onClick={() => { setError(''); if (to) setStep(to); else onExit(); }}><ArrowLeft size={15} /> {label}</button>;
    const errorBox = error && <div className="setup-message error" role="alert">{error}</div>;

    if (step === 'signin') return <>
        {back(null, 'All systems')}
        <h2>Connect {product.name}</h2>
        <p className="setup-subtitle">{product.help}</p>
        {errorBox}
        <form className="connector-form" onSubmit={signIn}>
            {!product.family && <label>What kind of data is this?<select required value={draft.family} onChange={e => setDraft(d => ({ ...d, family: e.target.value }))}><option value="">Choose…</option>{Object.entries(FAMILIES).map(([key, f]) => <option key={key} value={key}>{f.title} — {f.description}</option>)}</select></label>}
            {visible.map(f => {
                const saved = f.credential && savedCreds.includes(f.key);
                const value = f.credential ? creds[f.key] ?? '' : String(draft.options[f.key] ?? '');
                const set = (v: string) => f.credential ? setCreds(c => ({ ...c, [f.key]: v })) : option(f.key, v);
                return <label key={f.key}>{f.label}{!f.required && <span className="setup-optional"> optional</span>}
                    {f.choices ? <select value={value} onChange={e => set(e.target.value)}>{f.choices.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
                        : <input type={f.secret ? 'password' : 'text'} autoComplete={f.secret ? 'new-password' : 'off'} spellCheck={false} required={f.required && !saved} placeholder={saved ? 'Saved. Leave blank to keep it.' : f.placeholder} value={value} onChange={e => set(e.target.value)} />}
                    {f.help && <small>{f.help}</small>}
                </label>;
            })}
            <div className="setup-two-columns">
                <label>Site{me.site_ids.length ? <select value={draft.site_id} onChange={e => setDraft(d => ({ ...d, site_id: e.target.value }))} disabled={!!existing}>{me.site_ids.map(s => <option key={s}>{s}</option>)}</select>
                    : <input required placeholder="e.g. NF1" value={draft.site_id} disabled={!!existing} onChange={e => setDraft(d => ({ ...d, site_id: e.target.value }))} />}
                    <small>The site this data belongs to.</small></label>
                <label>Connection name<input required pattern="[A-Za-z0-9_.\-]{1,80}" value={draft.connector_id} disabled={!!existing} onChange={e => setDraft(d => ({ ...d, connector_id: e.target.value }))} /><small>Letters, numbers and dashes.</small></label>
            </div>
            <p className="setup-fine">Credentials are encrypted and only used to read data. They are never shown again.</p>
            <button className="setup-primary" disabled={!!busy} type="submit">{busy ? <><Loader2 size={16} className="animate-spin" /> Connecting…</> : <>Connect <ArrowRight size={17} /></>}</button>
        </form>
    </>;

    if (step === 'choose') return <>
        {back('signin', 'Sign-in details')}
        <h2>Choose what to collect</h2>
        <p className="setup-subtitle">Signed in to {product.name}. {product.multiple ? `Select the ${product.resource} to read.` : `Select a ${product.resource}.`}</p>
        {errorBox}
        <form className="source-catalog-search" onSubmit={searchResources}><Search size={15} /><input aria-label={`Search ${product.resource}`} type="search" placeholder={`Search ${product.resource}…`} value={search} onChange={e => setSearch(e.target.value)} />{product.multiple && <button className="setup-text-link" disabled={!!busy}>Search</button>}</form>
        <div className="resource-list" role={product.multiple ? 'group' : 'radiogroup'} aria-label={product.resource ?? 'Choices'}>
            {filtered.length ? filtered.map(r => <label key={r.id} className={`resource-option ${chosen.includes(r.id) ? 'selected' : ''}`}>
                <input type={product.multiple ? 'checkbox' : 'radio'} name="resource" checked={chosen.includes(r.id)} onChange={() => pick(r)} />
                <span><strong>{r.label}</strong>{r.detail && r.detail !== r.label && <small>{r.detail}</small>}</span>
            </label>) : <p className="setup-fine">{busy === 'search' ? 'Searching…' : resources?.length ? 'Nothing matches your search.' : `No ${product.resource} are visible to this account.`}</p>}
        </div>
        {product.multiple && <p className="setup-fine">{chosen.length} selected</p>}
        {product.table && chosen.length > 0 && <div className="setup-two-columns resource-columns">
            <label>Record ID column<select value={idColumn} onChange={e => setIdColumn(e.target.value)} disabled={busy === 'columns'}><option value="">Choose…</option>{columns.map(c => <option key={c.name} value={c.name}>{c.name}</option>)}</select><small>Uniquely identifies each row.</small></label>
            <label>Last updated column<select value={updatedColumn} onChange={e => setUpdatedColumn(e.target.value)} disabled={busy === 'columns'}><option value="">Choose…</option>{columns.map(c => <option key={c.name} value={c.name}>{c.name} {c.type ? `(${c.type.toLowerCase()})` : ''}</option>)}</select><small>Lets later syncs read only new or changed rows.</small></label>
        </div>}
        <button className="setup-primary" disabled={!!busy || !chosen.length} onClick={confirmChoice}>{busy === 'choose' ? <><Loader2 size={16} className="animate-spin" /> Reading a sample…</> : <>Continue <ArrowRight size={17} /></>}</button>
    </>;

    if (step === 'fields') {
        const rows = preview?.preview?.rows ?? [];
        const problems = preview?.preview?.errors ?? [];
        return <>
            {back(product.resource ? 'choose' : 'signin', product.resource ? `Choose ${product.resource}` : 'Connection details')}
            <h2>Check the fields</h2>
            <p className="setup-subtitle">We matched {product.name}&rsquo;s fields to ours. Change any that look wrong.</p>
            {errorBox}
            {preview && !preview.ok && <div className="setup-message error" role="alert">{preview.error ?? (problems.length ? `${problems.length} value${problems.length === 1 ? '' : 's'} could not be read. ${problems.slice(0, 2).map(p => `${p.field}: ${p.error}`).join('; ')}` : 'The sample could not be read.')}</div>}
            {mapping && <table className="mapping-table"><thead><tr><th>Our field</th><th>Field in {product.name}</th><th>Sample</th></tr></thead><tbody>
                {mapping.fields.map(f => <tr key={f.canonical}><td>{fieldLabel(f.canonical)}</td>
                    <td><select aria-label={`Source for ${fieldLabel(f.canonical)}`} value={sourceNames.includes(f.source) ? f.source : ''} onChange={e => remap(f.canonical, e.target.value)}><option value="">Not in this source</option>{sourceNames.map(n => <option key={n} value={n}>{n}</option>)}</select></td>
                    <td className="mapping-sample">{dirty ? '…' : show(rows[0]?.fields[f.canonical])}</td></tr>)}
            </tbody></table>}
            <p className="setup-fine">{preview?.records_sampled ?? 0} sample record{preview?.records_sampled === 1 ? '' : 's'} read. Nothing has been saved yet.</p>
            {dirty && <button className="setup-secondary" disabled={!!busy} onClick={refreshPreview}>{busy === 'remap' ? 'Updating…' : 'Update sample'}</button>}
            <label className="source-confirm-mapping"><input type="checkbox" checked={confirmed} disabled={dirty || !preview?.ok} onChange={e => setConfirmed(e.target.checked)} /><span>These fields look right. Accept values that pass every check automatically; anything else waits for review.</span></label>
            <button className="setup-primary" disabled={!!busy || dirty || !preview?.ok} onClick={acceptFields}>Continue <ArrowRight size={17} /></button>
        </>;
    }

    if (step === 'collect') return <>
        {back('fields', 'Check the fields')}
        <h2>Start collecting</h2>
        <p className="setup-subtitle">The first sync reads the data now. After that, Sievance checks for new records on the schedule you choose. Nothing is written back to {product.name}.</p>
        {errorBox}
        <label className="setup-poll">How often should we check for new data?<select value={schedule} onChange={e => setSchedule(Number(e.target.value))}>{SCHEDULES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>
        <button className="setup-primary" disabled={!!busy} onClick={start}>{busy === 'collect' ? <><Loader2 size={16} className="animate-spin" /> Collecting…</> : <>Run first sync <ArrowRight size={17} /></>}</button>
    </>;

    return <div className="setup-complete">
        <span><Check size={28} /></span>
        <h2>{product.name} is connected</h2>
        <p>{result?.ingested ?? 0} new record{result?.ingested === 1 ? '' : 's'} collected{result?.duplicates ? `, ${result.duplicates} already present` : ''}. {schedule ? `Next check: ${SCHEDULES.find(([v]) => v === schedule)?.[1].toLowerCase()}.` : 'Sync manually from the list below.'}</p>
        <button className="setup-primary" onClick={() => onVerify(draft.connector_id)}>Review collected data <ArrowRight size={17} /></button>
        <button className="setup-text-link" onClick={onExit}>Connect another system</button>
    </div>;
}
