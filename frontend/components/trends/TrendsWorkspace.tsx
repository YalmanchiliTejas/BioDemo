'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import { Download, PackageCheck } from 'lucide-react';
import { WorkspacePageHeader } from '@/components/shell/WorkspacePageHeader';
import { Button, Callout, Modal, Pill, table } from '@/components/ui';
import { cn } from '@/lib/cn';
import { parameterLabel } from '@/lib/cmo-api';
import { processRequest } from '@/lib/process-api';
import { exportTrends, formatValue, getTrends, LAYOUTS, statistic, STATISTICS, type ExportLayout, type Statistic, type TrendCatalogue, type TrendData, type TrendSeries } from '@/lib/trends-api';
import { BatchComparisonChart, BatchProfileChart, outside, SERIES_COLORS, type Limits } from './TrendCharts';

type Spec = Limits & { spec_id: string; parameter: string; unit: string | null; version: number; equipment_id: string | null; product_id: string | null };
const REMEMBERED = 'trends.parameter';
const recall = () => { try { return localStorage.getItem(REMEMBERED) ?? ''; } catch { return ''; } };
const select = 'h-8 rounded-control border border-border-strong bg-surface px-2 text-[13px] text-text-primary';
const unitOf = (units: Array<string | null>) => units.filter(Boolean).join(' / ');

/** Any accepted parameter across every delivery, chosen from a list: no question to type and no model call to wait for. */
export function TrendsWorkspace() {
  const [catalogue, setCatalogue] = useState<TrendCatalogue | null>(null);
  const [parameter, setParameter] = useState('');
  const [data, setData] = useState<TrendData | null>(null);
  const [error, setError] = useState('');
  const [stat, setStat] = useState<Statistic>('last');
  const [cdmo, setCdmo] = useState('');
  const [verifiedOnly, setVerifiedOnly] = useState(false);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [slots, setSlots] = useState<Record<string, number>>({});
  const [notice, setNotice] = useState('');
  const [specs, setSpecs] = useState<Spec[]>([]);
  const [specId, setSpecId] = useState('');
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    let alive = true;
    getTrends().then(c => {
      if (!alive) return;
      setCatalogue(c);
      // A link from elsewhere (a signal, for example) names the parameter to open on.
      const remembered = new URLSearchParams(window.location.search).get('parameter') || recall();
      // Start on the parameter last looked at, otherwise the one the most batches share.
      setParameter(c.parameters.some(p => p.id === remembered) ? remembered : [...c.parameters].sort((a, b) => b.batches - a.batches || b.values - a.values)[0]?.id ?? '');
    }).catch(e => { if (alive) setError((e as Error).message); });
    // Limits are an overlay: the charts stand without them if specifications cannot be read.
    processRequest<{ specifications: Spec[] }>('/v1/specifications').then(r => { if (alive) setSpecs(r.specifications); }).catch(() => undefined);
    return () => { alive = false; };
  }, []);

  useEffect(() => {
    if (!parameter) return;
    let alive = true;
    setError('');
    try { localStorage.setItem(REMEMBERED, parameter); } catch { /* preference only */ }
    getTrends<TrendData>(parameter).then(d => {
      if (!alive) return;
      setData(d);
      // Keep highlights that still apply; otherwise start with the most recent batch.
      setSlots(prev => {
        const kept = Object.fromEntries(Object.entries(prev).filter(([key]) => d.series.some(s => s.key === key)));
        const latest = d.series[d.series.length - 1];
        return Object.keys(kept).length || !latest ? kept : { [latest.key]: 0 };
      });
    }).catch(e => { if (alive) setError((e as Error).message); });
    return () => { alive = false; };
  }, [parameter]);

  const current = data?.parameter === parameter ? data : null;
  const info = catalogue?.parameters.find(p => p.id === parameter);
  const unit = info ? unitOf(info.units) : '';
  const cdmos = useMemo(() => [...new Set((catalogue?.batches ?? []).map(b => b.cmo).filter((c): c is string => !!c))].sort(), [catalogue]);
  const candidates = useMemo(() => (current?.series ?? []).filter(s => (!cdmo || s.cmo === cdmo) && (!verifiedOnly || s.delivery_verified)), [current, cdmo, verifiedOnly]);
  const shown = useMemo(() => candidates.filter(s => !hidden.has(s.key)), [candidates, hidden]);
  // Specifications are matched to parameters without regard to case, as the signal rules do.
  const matching = specs.filter(s => s.parameter.trim().toLowerCase() === parameter.trim().toLowerCase());
  const spec = matching.find(s => s.spec_id === specId) ?? matching[0];
  const comparable = !!spec && (!spec.unit || !unit || spec.unit === unit);
  const limits = comparable ? spec : null;
  const colors = useMemo(() => Object.fromEntries(Object.entries(slots).map(([key, slot]) => [key, SERIES_COLORS[slot]])), [slots]);
  const selected = useMemo(() => new Set(Object.keys(slots)), [slots]);
  const rows = useMemo(() => shown.map(series => ({ series, value: statistic(series.summary, stat), at: stat === 'mean' ? null : series.summary[stat].time_h })), [shown, stat]);

  function toggleHighlight(key: string) {
    setNotice('');
    setSlots(prev => {
      if (key in prev) { const { [key]: _removed, ...rest } = prev; return rest; }
      const free = SERIES_COLORS.findIndex((_, i) => !Object.values(prev).includes(i));
      if (free < 0) { setNotice(`Up to ${SERIES_COLORS.length} batches can be highlighted at once. Remove one to add another.`); return prev; }
      return { ...prev, [key]: free };
    });
  }
  const toggleShown = (key: string) => setHidden(prev => { const next = new Set(prev); if (!next.delete(key)) next.add(key); return next; });

  const sampled = shown.filter(s => s.sampled_every > 1).length;
  const untimed = shown.reduce((n, s) => n + s.points_without_time, 0);
  const converted = shown.filter(s => s.time_basis === 'hours_since_first_reading').length;
  const unverified = shown.filter(s => !s.delivery_verified).length;

  return <div className="workspace-page" data-testid="trends">
    <WorkspacePageHeader title="Trends" description="Any accepted value from your deliveries, across batches and over process time. Choose a parameter; nothing here waits on the assistant."
      actions={catalogue?.parameters.length ? <Button variant="primary" onClick={() => setExporting(true)}><Download size={15} />Export</Button> : undefined} />
    {error && <Callout tone="critical" title="Trends could not be loaded" className="mb-4">{error}</Callout>}
    {!catalogue && !error && <p role="status" className="py-10 text-center text-sm text-text-secondary">Loading accepted values…</p>}
    {catalogue && !catalogue.parameters.length && <section className="rounded-2xl border border-border-hairline bg-white px-6 py-12 text-center">
      <span className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-surface-secondary text-text-tertiary"><PackageCheck size={20} /></span>
      <h2 className="text-[17px] font-medium text-ink">No accepted values yet</h2>
      <p className="mx-auto mt-1 max-w-md text-[13px] text-text-secondary">Trends are drawn from values that have been checked against their source. Add a delivery, confirm what its columns mean, and its batches appear here.</p>
      <div className="mt-4 flex justify-center gap-2"><Link href="/cmo/" className="chrome-button primary">Go to deliveries</Link><Link href="/dashboard/" className="chrome-button">Workspace overview</Link></div>
    </section>}
    {catalogue && !!catalogue.parameters.length && <>
      <div className="mb-4 flex flex-wrap items-end gap-x-4 gap-y-2">
        <label className="flex flex-col gap-1 text-[11px] font-medium uppercase tracking-wide text-text-tertiary">Parameter
          <select className={cn(select, 'min-w-[260px]')} value={parameter} onChange={e => { setParameter(e.target.value); setSpecId(''); }} data-testid="trend-parameter">
            {catalogue.parameters.map(p => <option key={p.id} value={p.id}>{parameterLabel(p.id)}{unitOf(p.units) ? ` (${unitOf(p.units)})` : ''} · {p.batches} {p.batches === 1 ? 'batch' : 'batches'}</option>)}
          </select></label>
        {cdmos.length > 1 && <label className="flex flex-col gap-1 text-[11px] font-medium uppercase tracking-wide text-text-tertiary">CDMO
          <select className={select} value={cdmo} onChange={e => setCdmo(e.target.value)}><option value="">All</option>{cdmos.map(c => <option key={c} value={c}>{c}</option>)}</select></label>}
        {matching.length > 1 && <label className="flex flex-col gap-1 text-[11px] font-medium uppercase tracking-wide text-text-tertiary">Limits from
          <select className={select} value={spec?.spec_id ?? ''} onChange={e => setSpecId(e.target.value)}>
            {matching.map(s => <option key={s.spec_id} value={s.spec_id}>{[s.equipment_id, s.product_id].filter(Boolean).join(' · ') || 'General'} · v{s.version}</option>)}</select></label>}
        <label className="flex h-8 items-center gap-2 text-[13px] text-text-secondary"><input type="checkbox" checked={verifiedOnly} onChange={e => setVerifiedOnly(e.target.checked)} />Fully verified deliveries only</label>
        <p className="ml-auto text-xs text-text-tertiary">{shown.length} of {current?.series.length ?? '…'} batches · {catalogue.deliveries} {catalogue.deliveries === 1 ? 'delivery' : 'deliveries'}</p>
      </div>

      {info && info.units.length > 1 && <Callout tone="warning" title="This parameter is recorded in more than one unit" className="mb-4">Batches in {unitOf(info.units)} share these charts. Compare only batches with the same unit; the table below shows each batch&apos;s unit.</Callout>}
      {!current && !error && <p role="status" className="py-10 text-center text-sm text-text-secondary">Loading {parameterLabel(parameter)}…</p>}
      {current && !shown.length && <Callout tone="info" title="No batches match these filters">Clear a filter or tick a batch in the table to bring it back.</Callout>}

      {current && !!shown.length && <div className="space-y-4">
        <section className="rounded-2xl border border-border-hairline bg-white">
          <div className="flex flex-wrap items-center gap-3 border-b border-border-hairline px-5 py-3">
            <div className="min-w-0">
              <h2 className="text-[15px] font-medium text-ink">{parameterLabel(parameter)} across batches {unit && <span className="font-normal text-text-tertiary">({unit})</span>}</h2>
              <p className="text-xs text-text-tertiary">One point per batch. {limits ? `Limits from specification ${spec!.spec_id} v${spec!.version}.` : spec ? `Specification ${spec.spec_id} is in ${spec.unit}; its limits are not drawn against ${unit}.` : 'No specification is set for this parameter, so no limits are drawn.'}</p>
            </div>
            <label className="ml-auto flex items-center gap-2 text-xs text-text-secondary">Show
              <select className={select} value={stat} onChange={e => setStat(e.target.value as Statistic)} data-testid="trend-statistic">
                {STATISTICS.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}</select></label>
          </div>
          <div className="px-3 py-3"><BatchComparisonChart rows={rows} unit={unit} limits={limits} selected={selected} onSelect={toggleHighlight} /></div>
        </section>

        <section className="rounded-2xl border border-border-hairline bg-white">
          <div className="border-b border-border-hairline px-5 py-3">
            <h2 className="text-[15px] font-medium text-ink">{parameterLabel(parameter)} over process time {unit && <span className="font-normal text-text-tertiary">({unit})</span>}</h2>
            <p className="text-xs text-text-tertiary">Every shown batch in grey; click a line or a table row to highlight it.</p>
            <div className="mt-2 flex flex-wrap items-center gap-1.5" aria-label="Highlighted batches">
              {shown.filter(s => colors[s.key]).map(s => <button key={s.key} onClick={() => toggleHighlight(s.key)} title="Remove highlight"
                className="inline-flex items-center gap-1.5 rounded-pill border border-border-hairline px-2 py-0.5 text-[11px] text-text-secondary hover:bg-surface-secondary">
                <span className="h-0.5 w-3 rounded" style={{ background: colors[s.key] }} /><span className="font-mono">{s.batch || '(no batch)'}</span><span aria-hidden>×</span></button>)}
              {notice && <span role="status" className="text-[11px] text-amber-700">{notice}</span>}
            </div>
          </div>
          <div className="px-3 py-3"><BatchProfileChart series={shown} unit={unit} limits={limits} colors={colors} onSelect={toggleHighlight} /></div>
          {(sampled > 0 || untimed > 0 || converted > 0) && <ul className="space-y-0.5 border-t border-border-hairline px-5 py-2.5 text-xs text-text-tertiary">
            {converted > 0 && <li>{converted} {converted === 1 ? 'batch was' : 'batches were'} recorded with clock timestamps; {converted === 1 ? 'it is' : 'they are'} placed on hours since {converted === 1 ? 'its' : 'their'} first reading.</li>}
            {sampled > 0 && <li>{sampled} long {sampled === 1 ? 'profile is' : 'profiles are'} drawn from a regular sample of the readings. The table and exports use every reading.</li>}
            {untimed > 0 && <li>{untimed.toLocaleString()} {untimed === 1 ? 'reading has' : 'readings have'} no usable time and {untimed === 1 ? 'is' : 'are'} left out of this chart, but counted in the table.</li>}
          </ul>}
        </section>
      </div>}

      {current && !!candidates.length && <section className="mt-4 rounded-2xl border border-border-hairline bg-white">
        <div className="flex flex-wrap items-center gap-2 border-b border-border-hairline px-5 py-3">
          <h2 className="text-[15px] font-medium text-ink">Batches</h2>
          {unverified > 0 && <span className="text-xs text-amber-700">{unverified} from deliveries that still have items to check</span>}
          {hidden.size > 0 && <Button size="sm" variant="ghost" className="ml-auto" onClick={() => setHidden(new Set())}>Show all batches</Button>}
        </div>
        <div className={table.wrap}>
          <table className={table.root} data-testid="trend-batches">
            <thead><tr>{['Shown', 'Batch', 'Delivery', 'Readings', 'First', 'Final', 'Minimum', 'Maximum', 'Mean', 'Unit', 'Delivery status'].map(h => <th key={h} className={table.th}>{h}</th>)}</tr></thead>
            <tbody>{candidates.map(s => <BatchRow key={s.key} s={s} color={colors[s.key]} shown={!hidden.has(s.key)} limits={limits}
              onHighlight={() => toggleHighlight(s.key)} onShown={() => toggleShown(s.key)} />)}</tbody>
          </table>
        </div>
      </section>}
    </>}
    {exporting && catalogue && <ExportDialog catalogue={catalogue} parameter={parameter} shown={shown} total={current?.series.length ?? 0} onClose={() => setExporting(false)} />}
  </div>;
}

function BatchRow({ s, color, shown, limits, onHighlight, onShown }: { s: TrendSeries; color?: string; shown: boolean; limits: Limits | null; onHighlight: () => void; onShown: () => void }) {
  const cell = (v: number) => <td className={cn(table.td, 'whitespace-nowrap text-right tabular-nums', outside(v, limits) && 'font-semibold !text-status-critical')} title={outside(v, limits) ? 'Outside the specification limit' : undefined}>{formatValue(v)}</td>;
  return <tr className={cn(table.tr, 'cursor-pointer', !shown && 'opacity-50')} onClick={onHighlight} aria-selected={!!color}>
    <td className={table.td} onClick={e => e.stopPropagation()}><input type="checkbox" checked={shown} onChange={onShown} aria-label={`Show batch ${s.batch}`} /></td>
    <td className={cn(table.td, 'whitespace-nowrap font-mono')}><span className="mr-2 inline-block h-0.5 w-3 rounded align-middle" style={{ background: color ?? 'transparent' }} />{s.batch || '(no batch)'}</td>
    <td className={cn(table.td, 'max-w-[220px] truncate')} onClick={e => e.stopPropagation()}><Link className="text-brand-teal hover:underline" href={`/cmo/?run=${encodeURIComponent(s.run_id)}`} title="Open this delivery and its source files">{s.delivery_name ?? s.cmo ?? 'Delivery'}</Link></td>
    <td className={cn(table.td, 'text-right tabular-nums')}>{s.summary.n.toLocaleString()}</td>
    {cell(s.summary.first.value)}{cell(s.summary.last.value)}{cell(s.summary.min.value)}{cell(s.summary.max.value)}
    <td className={cn(table.td, 'whitespace-nowrap text-right tabular-nums')}>{formatValue(s.summary.mean)}</td>
    <td className={cn(table.td, 'text-text-tertiary')}>{s.unit ?? '—'}</td>
    <td className={table.td}>{s.delivery_verified ? <Pill tone="success" dot>Verified</Pill> : <Pill tone="warning" dot>Items to check</Pill>}</td>
  </tr>;
}

/** One place to take values to another tool: which batches, which parameters, what shape, what file. */
function ExportDialog({ catalogue, parameter, shown, total, onClose }: { catalogue: TrendCatalogue; parameter: string; shown: TrendSeries[]; total: number; onClose: () => void }) {
  const [scope, setScope] = useState<'shown' | 'all'>(shown.length && shown.length < total ? 'shown' : 'all');
  const [chosen, setChosen] = useState<Set<string>>(new Set([parameter]));
  const [layout, setLayout] = useState<ExportLayout>('long');
  const [format, setFormat] = useState<'csv' | 'xlsx'>('csv');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const everything = chosen.size === catalogue.parameters.length;
  async function run() {
    setBusy(true); setError('');
    try {
      await exportTrends({ format, layout, parameters: everything ? undefined : [...chosen], batches: scope === 'shown' ? shown.map(s => s.key) : undefined });
      onClose();
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  const heading = 'mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-text-tertiary';
  return <Modal open onClose={onClose} title="Export batch values" width="max-w-xl"
    footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" disabled={busy || !chosen.size} onClick={run}><Download size={14} />{busy ? 'Preparing…' : `Download ${format.toUpperCase()}`}</Button></>}>
    <div className="space-y-4 text-[13px]">
      <div><p className={heading}>Batches</p>
        <label className="mr-4 inline-flex items-center gap-2"><input type="radio" name="scope" checked={scope === 'all'} onChange={() => setScope('all')} />All {catalogue.batches.length} batches</label>
        <label className={cn('inline-flex items-center gap-2', !shown.length && 'opacity-50')}><input type="radio" name="scope" disabled={!shown.length} checked={scope === 'shown'} onChange={() => setScope('shown')} />The {shown.length} shown on the page</label>
      </div>
      <div><div className="flex items-baseline justify-between"><p className={heading}>Parameters</p>
          <button className="text-xs text-brand-teal hover:underline" onClick={() => setChosen(everything ? new Set([parameter]) : new Set(catalogue.parameters.map(p => p.id)))}>{everything ? 'Only the one on the page' : 'Select all'}</button></div>
        <div className="grid max-h-40 grid-cols-2 gap-x-4 gap-y-1 overflow-y-auto rounded-control border border-border-hairline p-2">
          {catalogue.parameters.map(p => <label key={p.id} className="flex items-center gap-2 truncate"><input type="checkbox" checked={chosen.has(p.id)}
            onChange={() => setChosen(prev => { const next = new Set(prev); if (!next.delete(p.id)) next.add(p.id); return next; })} />{parameterLabel(p.id)}</label>)}
        </div>
      </div>
      <div><p className={heading}>Shape</p>
        <div className="space-y-1.5">{LAYOUTS.map(l => <label key={l.value} className="flex items-start gap-2"><input type="radio" name="layout" className="mt-1" checked={layout === l.value} onChange={() => setLayout(l.value)} />
          <span><span className="font-medium text-text-primary">{l.label}</span><span className="block text-xs text-text-tertiary">{l.detail}</span></span></label>)}</div>
      </div>
      <div><p className={heading}>File</p>
        <label className="mr-4 inline-flex items-center gap-2"><input type="radio" name="format" checked={format === 'csv'} onChange={() => setFormat('csv')} />CSV</label>
        <label className="inline-flex items-center gap-2"><input type="radio" name="format" checked={format === 'xlsx'} onChange={() => setFormat('xlsx')} />Excel (.xlsx)</label>
      </div>
      <p className="text-xs text-text-tertiary">Only accepted values are exported. Each source file is checked against its recorded hash first; the export stops if a file has changed.</p>
      {error && <Callout tone="critical" title="Export stopped">{error}</Callout>}
    </div>
  </Modal>;
}
