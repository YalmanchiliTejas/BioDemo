'use client';

import { useEffect, useMemo, useState } from 'react';
import { Download, Save, Trash2 } from 'lucide-react';
import { WorkspacePageHeader } from '@/components/shell/WorkspacePageHeader';
import { Button, Callout, Segmented, table } from '@/components/ui';
import { cn } from '@/lib/cn';
import { parameterLabel } from '@/lib/cmo-api';
import { KIND_LABEL, listSignals, type Signal } from '@/lib/signals-api';
import { EXPORT_HANDOFF, exportTrends, getTrends, LAYOUTS, previewExport, type ExportFormat, type ExportLayout, type ExportOptions, type ExportPreview, type TrendCatalogue } from '@/lib/trends-api';

/** Everything a batch-values export is made of. A saved preset is one of these under a name. */
type Choice = { scope: 'all' | 'chosen'; batches: string[]; parameters: string[] | null; layout: ExportLayout; columns: string[] | null;
  timeFrom: string; timeTo: string; celsius: boolean; verifiedOnly: boolean; format: ExportFormat };
const START: Choice = { scope: 'all', batches: [], parameters: null, layout: 'long', columns: null, timeFrom: '', timeTo: '', celsius: false, verifiedOnly: false, format: 'csv' };
const PRESETS = 'export.presets.v1';
const heading = 'mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-text-tertiary';
const field = 'h-8 rounded-control border border-border-strong bg-surface px-2 text-[13px] text-text-primary';
const columnLabel = (c: string) => c.replace(/_/g, ' ');
const hours = (v: string) => (v.trim() === '' || !Number.isFinite(Number(v)) ? null : Number(v));

function readPresets(): Record<string, Choice> { try { return JSON.parse(localStorage.getItem(PRESETS) ?? '{}'); } catch { return {}; } }
function writePresets(presets: Record<string, Choice>) { try { localStorage.setItem(PRESETS, JSON.stringify(presets)); } catch { /* storage unavailable: presets are a convenience */ } }

function toOptions(choice: Choice, catalogue: TrendCatalogue): ExportOptions {
  const known = new Set(catalogue.batches.map(b => b.key));
  return { layout: choice.layout,
    parameters: choice.parameters?.filter(p => catalogue.parameters.some(c => c.id === p)),
    batches: choice.scope === 'chosen' ? choice.batches.filter(b => known.has(b)) : undefined,
    // Parameters are the columns of the wide shape, so a column choice applies to the other two.
    columns: choice.layout === 'wide' ? undefined : choice.columns ?? undefined,
    timeFrom: hours(choice.timeFrom), timeTo: hours(choice.timeTo), celsius: choice.celsius, verifiedOnly: choice.verifiedOnly };
}

/** One place to take data to another tool: what, which, in what shape and units, as what file, with a look before downloading. */
export function ExportWorkspace() {
  const [what, setWhat] = useState<'values' | 'signals'>('values');
  return <div className="workspace-page" data-testid="export">
    <WorkspacePageHeader title="Export" description="Take your data to another tool in the shape it needs. The table at the bottom shows the first rows of exactly what the file will contain." />
    <div className="mb-4"><Segmented<'values' | 'signals'> size="md" value={what} onChange={setWhat} options={[{ value: 'values', label: 'Batch values' }, { value: 'signals', label: 'Signals' }]} /></div>
    {what === 'values' ? <ValuesExport /> : <SignalsExport />}
  </div>;
}

function ValuesExport() {
  const [catalogue, setCatalogue] = useState<TrendCatalogue | null>(null);
  const [choice, setChoice] = useState<Choice>(START);
  const [available, setAvailable] = useState<string[]>([]);
  const [preview, setPreview] = useState<ExportPreview | null>(null);
  const [error, setError] = useState('');
  const [previewError, setPreviewError] = useState('');
  const [busy, setBusy] = useState(false);
  const [presets, setPresets] = useState<Record<string, Choice>>({});
  const [presetName, setPresetName] = useState('');
  const [active, setActive] = useState('');
  const set = (changes: Partial<Choice>) => { setChoice(c => ({ ...c, ...changes })); setActive(''); };

  useEffect(() => {
    setPresets(readPresets());
    let alive = true;
    getTrends().then(c => {
      if (!alive) return;
      setCatalogue(c);
      // Arriving from Trends: start from the parameter and batches that were on screen there.
      // Read here, cleared only once applied: an effect that is torn down and run again must still find it.
      let handoff: { parameters?: string[]; batches?: string[] } = {};
      try { handoff = JSON.parse(sessionStorage.getItem(EXPORT_HANDOFF) ?? '{}'); sessionStorage.removeItem(EXPORT_HANDOFF); } catch { /* start from everything */ }
      const named = new URLSearchParams(window.location.search).get('parameter');
      const parameters = handoff.parameters ?? (named ? [named] : null);
      if (parameters || handoff.batches) setChoice(c => ({ ...c, parameters: parameters ?? null, ...(handoff.batches ? { scope: 'chosen' as const, batches: handoff.batches } : {}) }));
    }).catch(e => { if (alive) setError((e as Error).message); });
    return () => { alive = false; };
  }, []);

  const options = useMemo(() => catalogue ? toOptions(choice, catalogue) : null, [choice, catalogue]);
  const nothing = !!options && ((options.parameters && !options.parameters.length) || (options.batches && !options.batches.length) || (options.columns && !options.columns.length));
  const key = JSON.stringify(options);
  // The columns a shape offers, learned from the server so the list can never drift from the file.
  useEffect(() => {
    if (!catalogue?.parameters.length) return;
    let alive = true;
    previewExport({ layout: choice.layout }, 1).then(p => { if (alive) setAvailable(p.columns); }).catch(() => { if (alive) setAvailable([]); });
    return () => { alive = false; };
  }, [choice.layout, catalogue]);
  useEffect(() => {
    if (!options || nothing) { setPreview(null); return; }
    let alive = true;
    const timer = window.setTimeout(() => {
      previewExport(options).then(p => { if (alive) { setPreview(p); setPreviewError(''); } }).catch(e => { if (alive) { setPreview(null); setPreviewError((e as Error).message); } });
    }, 250);
    return () => { alive = false; window.clearTimeout(timer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, nothing]);

  if (error) return <Callout tone="critical" title="Export is unavailable">{error}</Callout>;
  if (!catalogue) return <p role="status" className="py-10 text-center text-sm text-text-secondary">Loading what can be exported…</p>;
  if (!catalogue.parameters.length) return <Callout tone="info" title="Nothing to export yet">Batch values appear here once a delivery has values accepted against their source.</Callout>;

  const parameters = choice.parameters ?? catalogue.parameters.map(p => p.id);
  const columns = choice.columns ?? available;
  const toggle = (list: string[], item: string) => list.includes(item) ? list.filter(x => x !== item) : [...list, item];
  const kelvin = catalogue.parameters.some(p => p.units.includes('K'));
  async function run() {
    if (!options) return;
    setBusy(true); setError('');
    try { await exportTrends({ ...options, format: choice.format }); } catch (e) { setPreviewError((e as Error).message); } finally { setBusy(false); }
  }
  function savePreset() {
    const name = presetName.trim(); if (!name) return;
    const next = { ...presets, [name]: choice };
    setPresets(next); writePresets(next); setActive(name); setPresetName('');
  }
  function removePreset(name: string) {
    const { [name]: _removed, ...rest } = presets;
    setPresets(rest); writePresets(rest); if (active === name) setActive('');
  }

  return <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_300px]">
    <div className="min-w-0 space-y-4">
      <section className="space-y-5 rounded-2xl border border-border-hairline bg-white px-6 py-5 text-[13px]">
        <div><p className={heading}>Batches</p>
          <div className="flex flex-wrap items-center gap-x-5 gap-y-1.5">
            <label className="inline-flex items-center gap-2"><input type="radio" name="scope" checked={choice.scope === 'all'} onChange={() => set({ scope: 'all' })} />All {catalogue.batches.length} batches</label>
            <label className="inline-flex items-center gap-2"><input type="radio" name="scope" checked={choice.scope === 'chosen'} onChange={() => set({ scope: 'chosen' })} />Choose batches</label>
            <label className="inline-flex items-center gap-2 text-text-secondary"><input type="checkbox" checked={choice.verifiedOnly} onChange={e => set({ verifiedOnly: e.target.checked })} />Fully verified deliveries only</label>
          </div>
          {choice.scope === 'chosen' && <div className="mt-2 grid max-h-44 gap-x-4 gap-y-1 overflow-y-auto rounded-control border border-border-hairline p-2 sm:grid-cols-2" data-testid="export-batches">
            {catalogue.batches.map(b => <label key={b.key} className="flex items-center gap-2 truncate"><input type="checkbox" checked={choice.batches.includes(b.key)} onChange={() => set({ batches: toggle(choice.batches, b.key) })} />
              <span className="font-mono">{b.batch || '(no batch)'}</span><span className="truncate text-xs text-text-tertiary">{b.delivery_name ?? b.cmo}</span></label>)}</div>}
        </div>
        <div><div className="flex items-baseline justify-between"><p className={heading}>Parameters</p>
            <button className="text-xs text-brand-teal hover:underline" onClick={() => set({ parameters: choice.parameters === null || parameters.length === catalogue.parameters.length ? [] : null })}>{parameters.length === catalogue.parameters.length ? 'Clear' : 'Select all'}</button></div>
          <div className="grid max-h-44 gap-x-4 gap-y-1 overflow-y-auto rounded-control border border-border-hairline p-2 sm:grid-cols-3" data-testid="export-parameters">
            {catalogue.parameters.map(p => <label key={p.id} className="flex items-center gap-2 truncate"><input type="checkbox" checked={parameters.includes(p.id)} onChange={() => set({ parameters: toggle(parameters, p.id) })} />{parameterLabel(p.id)}</label>)}
          </div>
        </div>
        <div><p className={heading}>Shape</p>
          <div className="grid gap-2 md:grid-cols-3">{LAYOUTS.map(l => <label key={l.value} className={cn('flex cursor-pointer items-start gap-2 rounded-card border p-3', choice.layout === l.value ? 'border-brand-teal bg-brand-teal-light/40' : 'border-border-hairline')}>
            <input type="radio" name="layout" className="mt-1" checked={choice.layout === l.value} onChange={() => set({ layout: l.value, columns: null })} />
            <span><span className="font-medium text-text-primary">{l.label}</span><span className="mt-0.5 block text-xs leading-5 text-text-tertiary">{l.detail}</span></span></label>)}</div>
        </div>
        {choice.layout !== 'wide' && available.length > 0 && <div><div className="flex items-baseline justify-between"><p className={heading}>Columns</p>
            <button className="text-xs text-brand-teal hover:underline" onClick={() => set({ columns: columns.length === available.length ? [] : null })}>{columns.length === available.length ? 'Clear' : 'Select all'}</button></div>
          <div className="grid gap-x-4 gap-y-1 rounded-control border border-border-hairline p-2 sm:grid-cols-3" data-testid="export-columns">
            {/* Kept in the file's own order whatever order they are ticked in. */}
            {available.map(c => <label key={c} className="flex items-center gap-2 truncate"><input type="checkbox" checked={columns.includes(c)} onChange={() => set({ columns: available.filter(x => x === c ? !columns.includes(c) : columns.includes(x)) })} />{columnLabel(c)}</label>)}
          </div>
        </div>}
        <div className="flex flex-wrap gap-x-8 gap-y-4">
          <div><p className={heading}>Process time (h)</p>
            <div className="flex items-center gap-2"><input aria-label="From hour" inputMode="decimal" placeholder="start" className={cn(field, 'w-24')} value={choice.timeFrom} onChange={e => set({ timeFrom: e.target.value })} />
              <span className="text-text-tertiary">to</span><input aria-label="To hour" inputMode="decimal" placeholder="end" className={cn(field, 'w-24')} value={choice.timeTo} onChange={e => set({ timeTo: e.target.value })} /></div>
            {(hours(choice.timeFrom) != null || hours(choice.timeTo) != null) && <p className="mt-1 text-xs text-text-tertiary">Readings with no usable time are left out of a time window.</p>}
          </div>
          {kelvin && <div><p className={heading}>Units</p>
            <label className="inline-flex h-8 items-center gap-2"><input type="checkbox" checked={choice.celsius} onChange={e => set({ celsius: e.target.checked })} />Temperature in °C <span className="text-xs text-text-tertiary">(stored in K)</span></label></div>}
          <div><p className={heading}>File</p>
            <div className="flex h-8 items-center gap-4">{(['csv', 'xlsx', 'json'] as const).map(f => <label key={f} className="inline-flex items-center gap-2"><input type="radio" name="format" checked={choice.format === f} onChange={() => set({ format: f })} />{f === 'xlsx' ? 'Excel' : f.toUpperCase()}</label>)}</div></div>
        </div>
      </section>

      <section className="rounded-2xl border border-border-hairline bg-white" data-testid="export-preview">
        <div className="flex flex-wrap items-center gap-3 border-b border-border-hairline px-6 py-3">
          <div><h2 className="text-[15px] font-medium text-ink">What the file will contain</h2>
            <p className="text-xs text-text-tertiary">{nothing ? 'Choose at least one batch, parameter and column.' : preview ? `${preview.total_rows.toLocaleString()} rows × ${preview.columns.length} columns. The first ${Math.min(preview.rows.length, preview.total_rows)} are shown.` : previewError ? '' : 'Working it out…'}</p></div>
          <Button variant="primary" className="ml-auto" disabled={busy || nothing || !preview?.total_rows} onClick={run}><Download size={15} />{busy ? 'Preparing…' : `Download ${choice.format === 'xlsx' ? 'Excel' : choice.format.toUpperCase()}`}</Button>
        </div>
        {previewError && <Callout tone="critical" title="This selection cannot be exported" className="m-4">{previewError}</Callout>}
        {preview && preview.total_rows === 0 && <p className="px-6 py-6 text-sm text-text-secondary">No accepted values match this selection.</p>}
        {preview && preview.total_rows > 0 && <div className={table.wrap}><table className={table.root}>
          <thead><tr>{preview.columns.map(c => <th key={c} className={table.th}>{columnLabel(c)}</th>)}</tr></thead>
          <tbody>{preview.rows.map((row, i) => <tr key={i} className={table.tr}>{preview.columns.map(c => <td key={c} className={cn(table.td, 'max-w-[220px] truncate whitespace-nowrap', typeof row[c] === 'number' && 'text-right tabular-nums')} title={String(row[c] ?? '')}>{row[c] === null || row[c] === undefined ? '' : String(row[c])}</td>)}</tr>)}</tbody>
        </table></div>}
        <p className="border-t border-border-hairline px-6 py-2.5 text-xs text-text-tertiary">Only accepted values are exported. On download, each source file is checked against its recorded hash; the export stops if a file has changed.</p>
      </section>
    </div>

    <aside className="h-fit space-y-3 rounded-2xl border border-border-hairline bg-white px-5 py-4 text-[13px]" aria-label="Saved presets" data-testid="export-presets">
      <div><p className={heading}>Saved presets</p>
        <p className="text-xs leading-5 text-text-tertiary">Keep a selection you export regularly. Presets are saved in this browser only.</p></div>
      {Object.keys(presets).length === 0 ? <p className="text-xs text-text-tertiary">None yet.</p> : <ul className="space-y-1">{Object.keys(presets).sort().map(name => <li key={name} className="flex items-center gap-1">
        <button className={cn('min-w-0 flex-1 truncate rounded-control border px-2.5 py-1.5 text-left', active === name ? 'border-brand-teal bg-brand-teal-light/40 font-medium' : 'border-border-hairline hover:bg-surface-secondary')}
          onClick={() => { setChoice({ ...START, ...presets[name] }); setActive(name); }} title="Use this preset">{name}</button>
        <button aria-label={`Delete preset ${name}`} className="rounded p-1.5 text-text-tertiary hover:bg-surface-secondary hover:text-status-critical" onClick={() => removePreset(name)}><Trash2 size={14} /></button></li>)}</ul>}
      <form className="flex gap-1.5" onSubmit={e => { e.preventDefault(); savePreset(); }}>
        <input aria-label="Preset name" placeholder="Name this selection" className={cn(field, 'min-w-0 flex-1')} value={presetName} onChange={e => setPresetName(e.target.value)} />
        <Button type="submit" disabled={!presetName.trim()}><Save size={14} />Save</Button>
      </form>
      {presetName.trim() in presets && <p className="text-xs text-amber-700">Saving will replace the preset with this name.</p>}
    </aside>
  </div>;
}

const SIGNAL_COLUMNS: Array<[string, (s: Signal) => string | number | null | undefined]> = [
  ['signal_id', s => s.signal_id], ['severity', s => s.severity], ['kind', s => KIND_LABEL[s.kind] ?? s.kind], ['status', s => s.status], ['rule', s => s.rule],
  ['parameter', s => s.parameter], ['value', s => s.value], ['unit', s => s.unit], ['limit_low', s => s.limit?.low], ['limit_high', s => s.limit?.high],
  ['limit_critical_low', s => s.limit?.critical_low], ['limit_critical_high', s => s.limit?.critical_high], ['subject_kind', s => s.subject?.kind], ['subject', s => s.subject?.id],
  ['site', s => s.site_id], ['occurrences', s => s.occurrences], ['first_at', s => s.first_at], ['last_at', s => s.last_at], ['deviation_case', s => s.case_id],
  ['specification', s => s.spec_ref ? `${s.spec_ref.spec_id} v${s.spec_ref.version}` : null], ['source_system', s => s.source?.system], ['source_record', s => s.source?.record_id],
  ['dismiss_reason', s => s.dismiss_reason],
];
/** Text a spreadsheet would run as a formula is written as text, the same rule the server applies to its own files. */
const safeCell = (v: unknown) => typeof v === 'string' && (/^[\t\r\n]/.test(v) || /^[=+\-@]/.test(v.trimStart())) ? `'${v}` : v;
const csvCell = (v: unknown) => { const text = v == null ? '' : String(safeCell(v)); return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text; };

function SignalsExport() {
  const [signals, setSignals] = useState<Signal[] | null>(null);
  const [status, setStatus] = useState('');
  const [severity, setSeverity] = useState('');
  const [format, setFormat] = useState<'csv' | 'json'>('csv');
  const [error, setError] = useState('');
  useEffect(() => {
    let alive = true; setSignals(null);
    listSignals({ status, min_severity: severity }).then(r => { if (alive) { setSignals(r.signals); setError(''); } }).catch(e => { if (alive) setError((e as Error).message); });
    return () => { alive = false; };
  }, [status, severity]);
  const rows = useMemo(() => (signals ?? []).map(s => Object.fromEntries(SIGNAL_COLUMNS.map(([name, read]) => [name, read(s) ?? null]))), [signals]);
  function run() {
    const body = format === 'json' ? JSON.stringify(rows, null, 1)
      : [SIGNAL_COLUMNS.map(c => c[0]).join(','), ...rows.map(r => SIGNAL_COLUMNS.map(c => csvCell(r[c[0]])).join(','))].join('\r\n');
    const url = URL.createObjectURL(new Blob([body], { type: format === 'json' ? 'application/json' : 'text/csv' }));
    const a = document.createElement('a'); a.href = url; a.download = `signals.${format}`; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return <div className="space-y-4">
    <section className="flex flex-wrap items-end gap-x-8 gap-y-4 rounded-2xl border border-border-hairline bg-white px-6 py-5 text-[13px]">
      <label className="flex flex-col gap-1.5"><span className={cn(heading, 'mb-0')}>Status</span>
        <select className={field} value={status} onChange={e => setStatus(e.target.value)}>{[['', 'All'], ['open', 'Open'], ['acknowledged', 'Acknowledged'], ['case_opened', 'Case opened'], ['dismissed', 'Dismissed']].map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>
      <label className="flex flex-col gap-1.5"><span className={cn(heading, 'mb-0')}>Severity</span>
        <select className={field} value={severity} onChange={e => setSeverity(e.target.value)}>{[['', 'Any'], ['action', 'Action and above'], ['critical', 'Critical only']].map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>
      <div><p className={heading}>File</p><div className="flex h-8 items-center gap-4">{(['csv', 'json'] as const).map(f => <label key={f} className="inline-flex items-center gap-2"><input type="radio" name="signal-format" checked={format === f} onChange={() => setFormat(f)} />{f.toUpperCase()}</label>)}</div></div>
    </section>
    {error && <Callout tone="critical" title="Signals could not be loaded">{error}</Callout>}
    <section className="rounded-2xl border border-border-hairline bg-white" data-testid="export-signals">
      <div className="flex flex-wrap items-center gap-3 border-b border-border-hairline px-6 py-3">
        <div><h2 className="text-[15px] font-medium text-ink">What the file will contain</h2>
          <p className="text-xs text-text-tertiary">{signals ? `${rows.length.toLocaleString()} signals × ${SIGNAL_COLUMNS.length} columns. The first ${Math.min(8, rows.length)} are shown.` : 'Loading…'}</p></div>
        <Button variant="primary" className="ml-auto" disabled={!rows.length} onClick={run}><Download size={15} />Download {format.toUpperCase()}</Button>
      </div>
      {signals && !rows.length && <p className="px-6 py-6 text-sm text-text-secondary">No signals match these filters.</p>}
      {rows.length > 0 && <div className={table.wrap}><table className={table.root}>
        <thead><tr>{SIGNAL_COLUMNS.map(([c]) => <th key={c} className={table.th}>{columnLabel(c)}</th>)}</tr></thead>
        <tbody>{rows.slice(0, 8).map((row, i) => <tr key={i} className={table.tr}>{SIGNAL_COLUMNS.map(([c]) => <td key={c} className={cn(table.td, 'max-w-[240px] truncate whitespace-nowrap')} title={String(row[c] ?? '')}>{row[c] == null ? '' : String(row[c])}</td>)}</tr>)}</tbody>
      </table></div>}
      <p className="border-t border-border-hairline px-6 py-2.5 text-xs text-text-tertiary">A signal is a detection, not a deviation. The value column holds the latest reading for a signal seen more than once.</p>
    </section>
  </div>;
}
