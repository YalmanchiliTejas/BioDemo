'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { count, deliveryName, fig, sameName, type Dataset, type Profile, type Selection } from '@/lib/workbench';
import { chip, field, Region } from './parts';

export type Profiles = Record<string, Profile | { error: string } | undefined>;
const loaded = (profile: Profiles[string]): profile is Profile => !!profile && !('error' in profile);
const MAX_DELIVERIES = 10;   // one calculation reads at most ten deliveries

/** What the selected deliveries hold, from their prepared profiles (or the listing until a profile arrives). */
export function scopeOf(datasets: Dataset[], profiles: Profiles, selection: Selection | null) {
  const selected = (selection?.dataset_ids ?? []).map(id => datasets.find(d => d.id === id)).filter((d): d is Dataset => !!d);
  const waiting = selected.filter(d => d.verification === 'provisional' && !selection?.include_unverified);
  const used = selected.filter(d => !waiting.includes(d));
  const source = used.length ? used : selected;
  const parameters = new Map<string, { name: string; units: string[] }>();
  const batches = new Set<string>();
  let from = Infinity, to = -Infinity, known = selected.length > 0;
  for (const dataset of source) {
    const profile = profiles[dataset.id];
    if (!loaded(profile) && dataset.parameters == null) known = false;
    for (const item of loaded(profile) ? profile.parameters : (dataset.parameters ?? []).map(parameter => ({ parameter, units: [] as (string | null)[] }))) {
      const entry = parameters.get(item.parameter.toLowerCase()) ?? { name: item.parameter, units: [] };
      for (const unit of item.units) if (unit && !entry.units.includes(unit)) entry.units.push(unit);
      parameters.set(item.parameter.toLowerCase(), entry);
    }
    for (const batch of loaded(profile) ? profile.batches : dataset.batches ?? []) batches.add(batch);
    if (loaded(profile)) {
      const series = profile.series.filter(s => (!selection?.parameter || sameName(s.parameter, selection.parameter)) && (!selection?.batches.length || selection.batches.includes(s.batch)) && s.first_time_h != null && s.last_time_h != null);
      for (const s of series) { from = Math.min(from, s.first_time_h!); to = Math.max(to, s.last_time_h!); }
      if (!series.length && profile.time_range_h) { from = Math.min(from, profile.time_range_h[0]); to = Math.max(to, profile.time_range_h[1]); }
    }
  }
  /** Batches that hold the chosen parameter, when the profiles say. */
  const holding = new Set(source.flatMap(d => { const profile = profiles[d.id]; return loaded(profile) ? profile.series.filter(s => !selection?.parameter || sameName(s.parameter, selection.parameter)).map(s => s.batch) : []; }));
  return { selected, used, waiting, parameters: [...parameters.values()], batches: [...batches], known, holding: source.every(d => loaded(profiles[d.id])) ? holding : null,
    range: Number.isFinite(from) && Number.isFinite(to) ? [from, to] as [number, number] : null };
}

/** Hours typed by hand: empty means no limit. The text is kept as typed, so "12." does not jump while typing. */
function HoursInput({ label, value, onChange, invalid }: { label: string; value: number | null; onChange: (value: number | null) => void; invalid?: boolean }) {
  const [text, setText] = useState(value == null ? '' : String(value));
  useEffect(() => { setText(current => (current.trim() === '' ? null : Number(current)) === value ? current : value == null ? '' : String(value)); }, [value]);
  return <label className="block text-xs text-text-secondary">{label}
    <input type="number" inputMode="decimal" min={0} step="any" aria-label={`${label} (hours)`} aria-invalid={invalid || undefined} className={`${field} !w-24 tabular-nums ${invalid ? '!border-status-warning' : ''}`} value={text} placeholder="any"
      onChange={e => { setText(e.target.value); const parsed = e.target.value.trim() === '' ? null : Number(e.target.value); if (parsed == null || (Number.isFinite(parsed) && parsed >= 0)) onChange(parsed); }} /></label>;
}

export function DataInView({ datasets, error, onRetry, selection, onChange, profiles, notice }: {
  datasets: Dataset[] | null; error: string; onRetry: () => void; selection: Selection | null; onChange: (next: Selection) => void; profiles: Profiles; notice?: string;
}) {
  const scope = scopeOf(datasets ?? [], profiles, selection);
  if (error) return <Region number={1} id="data" title="Data in view"><div role="alert" className="rounded-control bg-status-warning-bg p-3 text-xs leading-5">The deliveries for this site could not be read. {error}
    <button type="button" onClick={onRetry} className="ml-2 font-medium text-brand-teal underline">Try again</button></div></Region>;
  if (!datasets || !selection) return <Region number={1} id="data" title="Data in view"><p role="status" className="py-4 text-xs text-text-tertiary">Reading the deliveries for this site…</p></Region>;
  if (!datasets.length && !selection.dataset_ids.length) return <Region number={1} id="data" title="Data in view"><div className="rounded-control bg-surface-secondary p-4 text-xs leading-5 text-text-secondary" data-testid="no-deliveries">
    <p className="text-sm font-medium text-text-primary">No deliveries to work with yet</p>
    <p className="mt-1 max-w-xl">The workbench reads the batch values in your CDMO deliveries. A delivery appears here once its file has been added under Deliveries and its values have been checked against the source, or while that review is still under way.</p>
    <Link href="/cmo/" className="chrome-button primary mt-3">Go to deliveries</Link></div></Region>;

  const set = (change: Partial<Selection>) => onChange({ ...selection, ...change });
  const missing = selection.dataset_ids.filter(id => !datasets.some(d => d.id === id));
  function toggleDelivery(id: string, on: boolean) {
    const dataset_ids = on ? [...selection!.dataset_ids, id] : selection!.dataset_ids.filter(value => value !== id);
    // A batch that none of the remaining deliveries lists cannot stay selected.
    const listed = new Set(dataset_ids.flatMap(value => datasets!.find(d => d.id === value)?.batches ?? []));
    const stillReview = dataset_ids.some(value => datasets!.find(d => d.id === value)?.verification === 'provisional');
    onChange({ ...selection!, dataset_ids, batches: listed.size ? selection!.batches.filter(batch => listed.has(batch)) : selection!.batches, include_unverified: selection!.include_unverified && stillReview });
  }
  const toggleBatch = (batch: string) => set({ batches: selection.batches.includes(batch) ? selection.batches.filter(value => value !== batch) : [...selection.batches, batch] });
  const [start, end] = scope.range ?? [null, null];
  const presets: { label: string; from: number | null; to: number | null }[] = [{ label: 'All', from: null, to: null }];
  if (start != null && end != null) {
    if (end - start > 24) presets.push({ label: 'First 24 h', from: start, to: start + 24 });
    if (end - start > 72) presets.push({ label: 'First 72 h', from: start, to: start + 72 });
    if (end - start > 48) presets.push({ label: 'Last 48 h', from: end - 48, to: end });
  }
  const backwards = selection.time_from_h != null && selection.time_to_h != null && selection.time_from_h > selection.time_to_h;
  const totals = scope.selected.map(d => profiles[d.id]);
  const ready = totals.filter(loaded);
  const strip = scope.selected.length && ready.length === scope.selected.length ? [
    count(ready.reduce((n, p) => n + p.values, 0), 'value'), count(new Set(ready.flatMap(p => p.batches)).size, 'batch', 'batches'),
    count(new Set(ready.flatMap(p => p.parameters.map(x => x.parameter.toLowerCase()))).size, 'parameter'),
    count(ready.reduce((n, p) => n + (p.review?.open_issues ?? 0), 0), 'open check'), count(ready.reduce((n, p) => n + p.conflicting_sample_times, 0), 'conflicting sample time'),
  ].join(' · ') : null;
  const parameterListed = !selection.parameter || scope.parameters.some(p => sameName(p.name, selection.parameter!));

  return <Region number={1} id="data" title="Data in view" hint="Choose what to bring together. The picture below follows every change.">
    {notice && <p role="status" className="mb-3 rounded-control bg-brand-teal-light/60 p-2 text-xs text-text-secondary">{notice}</p>}
    <div className="grid gap-x-6 gap-y-4 md:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
      <fieldset className="min-w-0"><legend className="text-xs font-medium text-text-secondary">Deliveries</legend>
        <ul className="mt-1.5 max-h-52 space-y-1.5 overflow-y-auto pr-1">{datasets.map(dataset => { const on = selection.dataset_ids.includes(dataset.id), review = dataset.verification === 'provisional'; return <li key={dataset.id}>
          <label className={`flex cursor-pointer items-start gap-2.5 rounded-control border px-3 py-2 text-xs ${on ? 'border-brand-teal bg-brand-teal-light/50' : 'border-border-hairline hover:bg-surface-secondary'}`}>
            <input type="checkbox" className="mt-0.5" checked={on} disabled={!on && selection.dataset_ids.length >= MAX_DELIVERIES} aria-label={`Use delivery ${deliveryName(dataset)}`} onChange={e => toggleDelivery(dataset.id, e.target.checked)} />
            <span className="min-w-0 flex-1"><span className="flex flex-wrap items-center gap-x-2 gap-y-0.5"><span className="break-words font-medium text-text-primary">{deliveryName(dataset)}</span>
              <span className={`rounded-pill px-1.5 py-0.5 text-[10px] font-medium ${review ? 'bg-status-warning-bg text-amber-800' : 'bg-status-success-bg text-emerald-700'}`}>{review ? 'In review' : 'Verified'}</span></span>
              <span className="mt-0.5 block text-[11px] text-text-tertiary">{[dataset.measurements != null && count(dataset.measurements, 'value'), dataset.batches?.length && count(dataset.batches.length, 'batch', 'batches'), dataset.parameters?.length && count(dataset.parameters.length, 'parameter'),
                review && `${count(dataset.review?.pending_values ?? 0, 'value')} still in review`, review && count(dataset.review?.open_issues ?? 0, 'open check')].filter(Boolean).join(' · ')}</span></span>
          </label></li>; })}
          {missing.map(id => <li key={id} className="flex items-center justify-between gap-2 rounded-control border border-dashed border-border-strong px-3 py-2 text-xs text-text-secondary">A delivery saved with this work is no longer available.
            <button type="button" className="text-brand-teal underline" onClick={() => toggleDelivery(id, false)}>Remove</button></li>)}</ul>
        {selection.dataset_ids.length >= MAX_DELIVERIES && <p className="mt-1 text-[11px] text-text-tertiary">Up to {MAX_DELIVERIES} deliveries can be read together.</p>}
        {!!scope.selected.filter(d => d.verification === 'provisional').length && <label className="mt-2 flex items-start gap-2 rounded-control bg-status-warning-bg p-2.5 text-xs">
          <input type="checkbox" className="mt-0.5" aria-label="Include values still in review" checked={selection.include_unverified} onChange={e => set({ include_unverified: e.target.checked })} />
          <span><span className="font-medium text-text-primary">Include values still in review</span>
            <span className="mt-0.5 block text-text-secondary">{selection.include_unverified ? 'Everything below is marked as resting on values nobody has accepted yet.'
              : `${scope.waiting.map(deliveryName).join(', ')} ${scope.waiting.length === 1 ? 'is' : 'are'} not used: ${scope.waiting.length === 1 ? 'its' : 'their'} values are still in review. Tick to use them; the results are then marked as resting on unreviewed values.`}</span></span></label>}
      </fieldset>

      <div className="min-w-0 space-y-4">
        <label className="block text-xs font-medium text-text-secondary">Parameter
          <select aria-label="Parameter" className={`${field} font-normal`} value={selection.parameter ?? ''} disabled={!scope.parameters.length && !selection.parameter} onChange={e => set({ parameter: e.target.value || null })}>
            {!selection.parameter && <option value="">{scope.selected.length ? 'Reading parameters…' : 'Select a delivery first'}</option>}
            {scope.parameters.map(p => <option key={p.name} value={p.name}>{p.name}{p.units.length ? ` (${p.units.join(' / ')})` : ''}</option>)}
            {selection.parameter && !parameterListed && <option value={selection.parameter}>{selection.parameter} (not in the selected deliveries)</option>}
          </select></label>
        <div><p className="text-xs font-medium text-text-secondary">Batches</p>
          <div className="mt-1.5 flex flex-wrap gap-1.5" role="group" aria-label="Batches">
            <button type="button" aria-pressed={!selection.batches.length} className={chip(!selection.batches.length)} onClick={() => set({ batches: [] })}>All batches</button>
            {[...new Set([...scope.batches, ...selection.batches])].map(batch => { const on = selection.batches.includes(batch), empty = !!scope.holding && !scope.holding.has(batch); return <button key={batch} type="button" aria-pressed={on}
              title={empty ? `No ${selection.parameter ?? 'values'} recorded for this batch in the selected deliveries` : undefined} className={`${chip(on)} font-mono ${empty ? 'opacity-55' : ''}`} onClick={() => toggleBatch(batch)}>{batch}</button>; })}
          </div>
          <p className="mt-1 text-[11px] text-text-tertiary">{selection.batches.length ? `${count(selection.batches.length, 'batch', 'batches')} selected.` : 'None selected means every batch.'}</p></div>
        <div><p className="text-xs font-medium text-text-secondary">Time window <span className="font-normal text-text-tertiary">(elapsed hours{start != null && end != null ? `; these deliveries cover ${fig(start, 6)} to ${fig(end, 6)} h` : ''})</span></p>
          <div className="mt-1 flex flex-wrap items-end gap-x-3 gap-y-2">
            <HoursInput label="From" value={selection.time_from_h} invalid={backwards} onChange={time_from_h => set({ time_from_h })} />
            <HoursInput label="To" value={selection.time_to_h} invalid={backwards} onChange={time_to_h => set({ time_to_h })} />
            <div className="flex flex-wrap gap-1.5 pb-0.5" role="group" aria-label="Time window presets">{presets.map(preset => { const on = selection.time_from_h === preset.from && selection.time_to_h === preset.to;
              return <button key={preset.label} type="button" aria-pressed={on} className={chip(on)} onClick={() => set({ time_from_h: preset.from, time_to_h: preset.to })}>{preset.label}</button>; })}</div>
          </div>
          {backwards && <p role="alert" className="mt-1 text-[11px] text-status-warning">“From” is later than “To”. The picture keeps the last valid window until this is corrected.</p>}</div>
        <details className="text-xs text-text-secondary" open={selection.align_tolerance_h > 0 || undefined}><summary className="cursor-pointer">More options</summary>
          <label className="mt-2 flex flex-wrap items-center gap-2">Pair samples up to
            <input type="number" min={0} max={24} step="any" aria-label="Pair samples up to this many hours apart" className={`${field} !mt-0 !w-20 tabular-nums`} value={selection.align_tolerance_h}
              onChange={e => { const value = Number(e.target.value); if (e.target.value !== '' && Number.isFinite(value)) set({ align_tolerance_h: Math.max(0, Math.min(24, value)) }); }} />h apart</label>
          <p className="mt-1 text-[11px] text-text-tertiary">0 compares samples taken at exactly the same elapsed time. A larger number pairs each sample with the other batch’s nearest one; values are never interpolated.</p></details>
      </div>
    </div>
    <p className="mt-4 border-t border-border-hairline pt-3 text-xs tabular-nums text-text-secondary" data-testid="consolidation">{!scope.selected.length ? 'No delivery is selected. Tick one to see what it holds.'
      : strip ?? (totals.some(p => p && 'error' in p) ? `${count(scope.selected.length, 'delivery', 'deliveries')} selected. What they hold could not be summarised; the picture below is still calculated from them.` : 'Reading what these deliveries hold…')}</p>
  </Region>;
}
