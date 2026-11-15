'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { ArrowUpRight, Loader2, X } from 'lucide-react';
import { processRequest } from '@/lib/process-api';
import { SERIES_COLORS } from '@/components/trends/TrendCharts';
import { count, deliveryName, fig, hours, locationText, sameName, seconds, valueSource, withUnit,
  type Cohort, type CohortVerdict, type ComparisonSummary, type Dataset, type Measurement, type Picture as PictureData, type Selection, type Series } from '@/lib/workbench';
import { BatchChart, type ChartPoint } from './BatchChart';
import { Region } from './parts';

const CONTEXT = '#94a3b8';   // a ninth batch and beyond: drawn, named in the legend, without a colour of its own
const th = 'border-b border-border-hairline px-2.5 py-2 text-left text-[11px] font-medium text-text-tertiary', td = 'border-b border-border-hairline px-2.5 py-2 align-top';
const seriesKey = (s: { dataset_id?: string; batch: string }) => `${s.dataset_id ?? ''}|${s.batch}`;

/** A batch keeps its colour while it stays in view, so changing the selection never repaints the batches that remain. */
function useSlots(keys: string[]) {
  const slots = useRef(new Map<string, number>());
  for (const key of [...slots.current.keys()]) if (!keys.includes(key)) slots.current.delete(key);
  for (const key of keys) if (!slots.current.has(key)) {
    const free = SERIES_COLORS.findIndex((_, i) => ![...slots.current.values()].includes(i));
    slots.current.set(key, free);   // -1 once every colour is taken
  }
  return (key: string) => SERIES_COLORS[slots.current.get(key) ?? -1] ?? CONTEXT;
}

type Chosen = ChartPoint & { batch: string; label: string; dataset_id?: string; unit: string | null };
type SourceState = { status: 'loading' | 'ready' | 'error'; rows: Measurement[]; error?: string };

export function Picture({ picture, busy, error, onRetry, selection, datasets, emptyReason }: {
  picture: PictureData | null; busy: boolean; error: string; onRetry: () => void; selection: Selection | null; datasets: Dataset[];
  /** Why there is nothing to calculate yet, when that is the case. */
  emptyReason?: string;
}) {
  const reconcile = picture?.results.reconcile, compare = picture?.results.compare;
  const names = { ...Object.fromEntries(datasets.map(d => [d.id, deliveryName(d)])), ...(reconcile?.data.deliveries ?? {}) };
  const all = useMemo(() => (reconcile?.data.series ?? []).filter((s: Series) => !selection?.parameter || sameName(s.parameter, selection.parameter)), [reconcile, selection?.parameter]);
  const label = (s: { dataset_id?: string; batch: string }) => s.dataset_id ? `${s.batch} (${names[s.dataset_id] ?? 'delivery'})` : s.batch;
  const color = useSlots(all.map(seriesKey));
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [chosen, setChosen] = useState<Chosen | null>(null);
  const [source, setSource] = useState<SourceState | null>(null);
  const lookup = useRef(0);
  const shown = all.filter(s => !hidden.has(seriesKey(s)));
  const unit = all[0]?.unit ?? null, parameter = all[0]?.parameter ?? selection?.parameter ?? '';
  // A value that is no longer in view cannot keep its source panel.
  useEffect(() => {
    if (chosen && !all.some(s => seriesKey(s) === chosen.key && s.points.some(p => p[0] === chosen.time_h && p[1] === chosen.value))) { lookup.current++; setChosen(null); setSource(null); }
  }, [all, chosen]);

  const summary = (compare?.data.comparison_summary ?? []) as ComparisonSummary[];
  const visiblePair = (row: ComparisonSummary) => [{ dataset_id: row.left_dataset_id, batch: row.left_batch }, { dataset_id: row.right_dataset_id, batch: row.right_batch }].every(side => shown.some(s => seriesKey(s) === seriesKey(side)));
  const largest = summary.filter(visiblePair).sort((a, b) => Math.abs(b.largest_difference.difference) - Math.abs(a.largest_difference.difference))[0];
  const unmatched = Object.entries(compare?.data.unmatched_counts ?? {}).filter(([, n]) => n > 0);

  async function choose(point: ChartPoint) {
    const series = all.find(s => seriesKey(s) === point.key); if (!series || !selection) return;
    const request = ++lookup.current;
    setChosen({ ...point, batch: series.batch, label: label(series), dataset_id: series.dataset_id, unit: series.unit });
    const matches = (row: Measurement) => row.batch === series.batch && row.time_h === point.time_h && sameName(row.parameter, series.parameter) && (!series.dataset_id || !row.dataset_id || row.dataset_id === series.dataset_id);
    // The rows already on the page carry their source; only a value outside that page is looked up.
    const local = (reconcile?.data.measurements ?? []).filter(matches);
    if (local.length) { setSource({ status: 'ready', rows: local }); return; }
    setSource({ status: 'loading', rows: [] });
    try {
      const rows = (await valueSource(selection, series.batch, point.time_h)).filter(matches);
      if (lookup.current === request) setSource({ status: 'ready', rows });
    } catch (e) { if (lookup.current === request) setSource({ status: 'error', rows: [], error: (e as Error).message }); }
  }
  const close = () => { lookup.current++; setChosen(null); setSource(null); };
  const timing = picture?.timing;

  return <Region number={2} id="picture" title="What the data shows"
    aside={timing && !error ? <span className={timing.within_target ? 'text-text-tertiary' : 'font-medium text-status-warning'} data-testid="picture-timing">
      {busy && <Loader2 size={11} className="mr-1 inline animate-spin" aria-hidden />}{timing.within_target ? `Updated in ${seconds(timing.seconds)}` : `Took ${seconds(timing.seconds)} · over the ${fig(timing.target_seconds)} s target`}</span>
      : busy ? <span role="status" className="text-text-tertiary"><Loader2 size={11} className="mr-1 inline animate-spin" aria-hidden />Calculating…</span> : null}>
    {error && <div role="alert" className="rounded-control bg-status-warning-bg p-3 text-xs leading-5">The picture could not be calculated. {error}
      <button type="button" onClick={onRetry} className="ml-2 font-medium text-brand-teal underline">Try again</button></div>}
    {!error && !picture && <p role={emptyReason ? undefined : 'status'} className="py-6 text-center text-xs text-text-tertiary">{emptyReason ?? 'Calculating from the selected deliveries…'}</p>}
    {!error && picture && !all.length && <div className="rounded-control bg-surface-secondary p-4 text-xs leading-5 text-text-secondary" data-testid="picture-empty">
      <p className="font-medium text-text-primary">No usable values{parameter ? ` for ${parameter}` : ''} in this selection.</p>
      <ul className="mt-1 list-disc pl-4">{[...new Set((reconcile?.issues ?? []).map(issue => issue.code === 'unverified_dataset' ? 'A selected delivery is still in review and is not used. Tick “Include values still in review” above to use it.' : issue.message))].map(message => <li key={message}>{message}</li>)}</ul>
    </div>}
    {!error && picture && !!all.length && <div className={`space-y-5 transition-opacity ${busy ? 'opacity-60' : ''}`}>
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_236px]">
        <div className="min-w-0">
          <div className="flex flex-wrap gap-1.5" role="group" aria-label="Batches drawn">
            {all.map(s => { const key = seriesKey(s), on = !hidden.has(key); return <button key={key} type="button" aria-pressed={on} title={on ? 'Hide this batch in the chart' : 'Show this batch in the chart'}
              onClick={() => setHidden(prev => { const next = new Set(prev); if (!next.delete(key)) next.add(key); return next; })}
              className={`inline-flex items-center gap-1.5 rounded-pill border px-2 py-1 text-[11px] ${on ? 'border-border-strong bg-surface text-text-primary' : 'border-border-hairline bg-surface-secondary text-text-tertiary line-through'}`}>
              <span className="h-0.5 w-3.5 rounded" style={{ background: on ? color(key) : '#cbd5e1' }} /><span className="font-mono">{label(s)}</span><span className="text-text-tertiary no-underline">{s.n}</span></button>; })}
          </div>
          <div className="mt-2 overflow-x-auto">
            {shown.length ? <BatchChart series={shown.map(s => ({ key: seriesKey(s), label: label(s), color: color(seriesKey(s)), points: s.points }))} unit={unit} parameter={parameter}
              selected={chosen} onSelect={point => void choose(point)}
              mark={largest ? { time_h: largest.largest_difference.time_h, from: largest.largest_difference.left_value, to: largest.largest_difference.right_value, label: `Largest difference ${withUnit(Math.abs(largest.largest_difference.difference), largest.unit)}` } : null} />
              : <p className="py-10 text-center text-xs text-text-tertiary">Every batch is hidden. Click a batch above to draw it.</p>}
          </div>
          <p className="mt-1 text-[11px] leading-4 text-text-tertiary">Each point is a recorded sample; lines only join samples of one batch. {reconcile?.data.series_complete === false ? 'The selection is larger than one result holds, so some values are not drawn.' : `${count(all.reduce((n, s) => n + s.n, 0), 'value')} drawn.`}</p>
        </div>
        <SourcePanel chosen={chosen} source={source} datasets={datasets} names={names} onClose={close} />
      </div>

      <ValuesTable rows={(reconcile?.data.measurements ?? []).filter(row => !selection?.parameter || sameName(row.parameter, selection.parameter))} total={reconcile?.data.measurement_count} names={names}
        onSource={row => { const series = all.find(s => s.batch === row.batch && (!s.dataset_id || !row.dataset_id || s.dataset_id === row.dataset_id)); if (series && row.time_h != null) void choose({ key: seriesKey(series), time_h: row.time_h, value: row.value }); }} />

      <section aria-label="Differences between batches">
        <h3 className="text-[13px] font-medium text-text-primary">Differences between batches</h3>
        {summary.length ? <>
          <p className="mt-0.5 text-[11px] text-text-tertiary">Each difference is {summary[0].difference_definition}. {compare?.data.alignment?.tolerance_h ? `Samples up to ${fig(compare.data.alignment.tolerance_h)} h apart are paired; nothing is interpolated.` : 'Only samples at exactly the same time are paired; nothing is interpolated.'}</p>
          {/* On a phone each pair is a short list; from tablet width up, one table. */}
          <ul className="mt-2 space-y-2 sm:hidden" data-testid="comparison-cards">{summary.map((row, i) => { const big = row.largest_difference; return <li key={i} className="rounded-control border border-border-hairline p-3 text-xs tabular-nums">
            <p className="font-medium text-text-primary"><span className="font-mono">{label({ dataset_id: row.right_dataset_id, batch: row.right_batch })}</span> minus <span className="font-mono">{label({ dataset_id: row.left_dataset_id, batch: row.left_batch })}</span></p>
            <dl className="mt-1.5 grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 text-text-secondary">
              <dt className="text-text-tertiary">Matching times</dt><dd>{row.matched_times}, from {hours(row.first_time_h)} to {hours(row.last_time_h)} h</dd>
              <dt className="text-text-tertiary">Mean difference</dt><dd className="font-medium text-text-primary">{withUnit(row.mean_difference, row.unit)}</dd>
              <dt className="text-text-tertiary">Largest difference</dt><dd>{withUnit(big.difference, row.unit)} at {hours(big.time_h)} h ({row.right_batch} {withUnit(big.right_value, row.unit)}, {row.left_batch} {withUnit(big.left_value, row.unit)})</dd>
              <dt className="text-text-tertiary">Spread</dt><dd>{row.statistics?.standard_deviation == null ? '—' : `${withUnit(row.statistics.standard_deviation, row.unit)} standard deviation`}</dd>
              <dt className="text-text-tertiary">Samples matched</dt><dd>{row.share_of_samples_matched == null ? '—' : `${fig(row.share_of_samples_matched * 100, 3)}%`}</dd>
            </dl></li>; })}</ul>
          <div className="mt-2 hidden overflow-x-auto sm:block"><table className="w-full min-w-[600px] border-collapse text-xs tabular-nums" data-testid="comparison-table">
            <thead><tr>{['Batches', 'Matching times', 'Mean difference', 'Largest difference', 'Spread', 'Samples matched'].map(name => <th key={name} scope="col" className={th}>{name}</th>)}</tr></thead>
            <tbody>{summary.map((row, i) => { const big = row.largest_difference; return <tr key={i}>
              <th scope="row" className={`${td} whitespace-nowrap text-left font-medium`}><span className="font-mono">{label({ dataset_id: row.right_dataset_id, batch: row.right_batch })}</span> minus <span className="font-mono">{label({ dataset_id: row.left_dataset_id, batch: row.left_batch })}</span></th>
              <td className={td}>{row.matched_times}<span className="block text-text-tertiary">{hours(row.first_time_h)} to {hours(row.last_time_h)} h</span></td>
              <td className={td}>{withUnit(row.mean_difference, row.unit)}</td>
              <td className={td}>{withUnit(big.difference, row.unit)} at {hours(big.time_h)} h<span className="block text-text-tertiary">{row.right_batch} {withUnit(big.right_value, row.unit)} · {row.left_batch} {withUnit(big.left_value, row.unit)}</span></td>
              <td className={td}>{row.statistics?.standard_deviation == null ? '—' : withUnit(row.statistics.standard_deviation, row.unit)}<span className="block text-text-tertiary">standard deviation</span></td>
              <td className={td}>{row.share_of_samples_matched == null ? '—' : `${fig(row.share_of_samples_matched * 100, 3)}%`}</td>
            </tr>; })}</tbody></table></div>
          {!!unmatched.length && <p className="mt-2 text-[11px] text-text-tertiary">Samples with no partner at the same time: {unmatched.map(([name, n]) => `${name.replace(/ \(([^()]+)\)$/, (_, id: string) => ` (${names[id] ?? 'delivery'})`)} ${n}`).join(' · ')}</p>}
          {summary[0].statistics?.note && <p className="mt-1 text-[11px] text-text-tertiary">{summary[0].statistics.note}</p>}
        </> : <p className="mt-1 text-xs leading-5 text-text-secondary">{all.length < 2 ? 'One batch is in view. Add a second batch to compare them.' : 'These batches have no samples at the same times, so no difference is calculated. Widen the time window, or pair samples a few hours apart under “More options”.'}</p>}
      </section>

      {compare?.data.cohort && all.length > 1 && <FairComparison cohort={compare.data.cohort} />}
    </div>}
  </Region>;
}

function SourcePanel({ chosen, source, datasets, names, onClose }: { chosen: Chosen | null; source: SourceState | null; datasets: Dataset[]; names: Record<string, string>; onClose: () => void }) {
  return <aside aria-label="Source" data-testid="source-panel" className="min-w-0 rounded-control border border-border-hairline bg-surface-secondary/60 p-3 text-xs leading-5">
    <div className="flex items-start justify-between gap-2"><h3 className="text-[11px] font-medium uppercase tracking-wide text-text-tertiary">Source</h3>
      {chosen && <button type="button" onClick={onClose} aria-label="Close source" className="text-text-tertiary hover:text-text-primary"><X size={14} /></button>}</div>
    {!chosen && <p className="mt-1 text-text-tertiary">Click a point to see the file and the place its value was read from.</p>}
    {chosen && <>
      <p className="mt-1 font-mono text-text-secondary">{chosen.label} · {hours(chosen.time_h)} h</p>
      <p className="text-[15px] font-semibold tabular-nums text-text-primary">{withUnit(chosen.value, chosen.unit)}</p>
      {source?.status === 'loading' && <p role="status" className="mt-2 text-text-tertiary"><Loader2 size={12} className="mr-1 inline animate-spin" aria-hidden />Finding where this value was read from…</p>}
      {source?.status === 'error' && <p role="alert" className="mt-2 text-status-warning">The source could not be read. {source.error}</p>}
      {source?.status === 'ready' && !source.rows.some(row => row.sources?.length) && <p className="mt-2 text-status-warning">No source location came back for this value. Open the delivery to find it.</p>}
      {source?.status === 'ready' && source.rows.flatMap(row => (row.sources ?? []).map((origin, i) => <dl key={`${origin.measurement_id ?? i}:${origin.evidence_id}`} className="mt-2 space-y-1 border-t border-border-hairline pt-2">
        <div><dt className="text-text-tertiary">File</dt><dd className="break-words font-medium text-text-primary">{origin.source?.path ?? 'File name not recorded'}</dd></div>
        <div><dt className="text-text-tertiary">Place in the file</dt><dd className="font-medium text-text-primary">{locationText(origin.source)}</dd></div>
        {row.original_value != null && (row.original_value !== row.value || (row.original_unit ?? null) !== (row.unit ?? null)) && <div><dt className="text-text-tertiary">As recorded</dt><dd>{typeof row.original_value === 'number' ? withUnit(row.original_value, row.original_unit) : `${row.original_value} ${row.original_unit ?? ''}`}</dd></div>}
        <div><dt className="text-text-tertiary">Delivery</dt><dd>{names[origin.evidence_id] ?? 'Selected delivery'} · revision {origin.revision}</dd></div>
        <DeliveryLink evidenceId={origin.evidence_id} datasets={datasets} />
      </dl>))}
    </>}
  </aside>;
}

/** The delivery's own page shows the original file beside each value. The run it opens is on the delivery listing, or on the evidence record. */
export function DeliveryLink({ evidenceId, datasets, children = 'Open this delivery' }: { evidenceId: string; datasets: Dataset[]; children?: React.ReactNode }) {
  const listed = datasets.find(d => d.id === evidenceId)?.run_id;
  const [run, setRun] = useState<string | null>(listed ?? null);
  useEffect(() => {
    if (listed) { setRun(listed); return; }
    let alive = true;
    processRequest<{ state?: { source_record_id?: unknown } }>(`/v1/records/evidence/${encodeURIComponent(evidenceId)}`)
      .then(record => { if (alive && typeof record.state?.source_record_id === 'string') setRun(record.state.source_record_id); }).catch(() => undefined);
    return () => { alive = false; };
  }, [evidenceId, listed]);
  return <Link href={run ? `/cmo/?run=${encodeURIComponent(run)}` : '/cmo/'} className="inline-flex items-center gap-1 text-brand-teal underline">{children}<ArrowUpRight size={12} /></Link>;
}

/** The same values the chart draws, as rows: readable without a pointer, and each row opens its source. */
function ValuesTable({ rows, total, names, onSource }: { rows: Measurement[]; total?: number; names: Record<string, string>; onSource: (row: Measurement) => void }) {
  if (!rows.length) return null;
  return <details className="text-xs"><summary className="cursor-pointer text-text-secondary">Values as a table · {total != null && total > rows.length ? `first ${rows.length} of ${total}` : rows.length}</summary>
    <div className="mt-2 max-h-64 overflow-auto"><table className="w-full border-collapse tabular-nums"><thead><tr>{['Batch', 'Elapsed time', 'Value', ''].map((name, i) => <th key={i} scope="col" className={th}>{name || <span className="sr-only">Source</span>}</th>)}</tr></thead>
      <tbody>{rows.map((row, i) => <tr key={i}><td className={`${td} font-mono`}>{row.batch}{row.dataset_id ? ` (${names[row.dataset_id] ?? 'delivery'})` : ''}</td><td className={td}>{hours(row.time_h)} h</td><td className={td}>{withUnit(row.value, row.unit)}</td>
        <td className={td}><button type="button" className="text-brand-teal underline" onClick={() => onSource(row)}>Source</button></td></tr>)}</tbody></table></div></details>;
}

const VERDICT: Record<CohortVerdict, { label: string; style: string }> = {
  same: { label: 'Same', style: 'border-emerald-200 bg-status-success-bg text-emerald-700' },
  differs: { label: 'Differs', style: 'border-amber-300 bg-status-warning-bg text-amber-800' },
  not_recorded: { label: 'Not recorded', style: 'border-dashed border-border-strong bg-surface text-text-tertiary' },
};
const OVERALL: Record<Cohort['verdict'], string> = { same_context: 'The recorded context is the same for these batches.', differs: 'The recorded context differs', not_established: 'Part of the context is not recorded, so a like-for-like comparison is not established' };

function FairComparison({ cohort }: { cohort: Cohort }) {
  const batches = [...new Set(cohort.attributes.flatMap(attribute => Object.keys(attribute.values)))];
  const detail = cohort.verdict === 'differs' ? `: ${cohort.differs.join(', ')}.` : cohort.verdict === 'not_established' ? `: ${cohort.not_recorded.join(', ')}.` : '';
  return <section aria-label="Is this a fair comparison?" data-testid="fair-comparison">
    <h3 className="text-[13px] font-medium text-text-primary">Is this a fair comparison?</h3>
    <p className={`mt-0.5 text-xs ${cohort.verdict === 'same_context' ? 'text-text-secondary' : 'font-medium text-amber-800'}`}>{OVERALL[cohort.verdict]}{detail}</p>
    <ul className="mt-2 divide-y divide-border-hairline rounded-control border border-border-hairline">{cohort.attributes.map(attribute => { const verdict = VERDICT[attribute.verdict] ?? VERDICT.not_recorded; return <li key={attribute.attribute} className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-x-3 gap-y-1 px-3 py-2 text-xs sm:grid-cols-[150px_110px_minmax(0,1fr)]" data-verdict={attribute.verdict}>
      <span className="font-medium text-text-primary">{attribute.label}</span>
      <span><span className={`inline-flex h-5 items-center rounded-pill border px-2 text-[11px] font-medium ${verdict.style}`}>{verdict.label}</span></span>
      <span className="col-span-2 flex flex-wrap gap-x-4 gap-y-0.5 text-text-secondary sm:col-span-1">{batches.map(batch => { const value = attribute.values[batch]; return <span key={batch}><span className="font-mono text-text-tertiary">{batch}</span> {value == null || value === '' ? <span className="italic text-text-tertiary">not recorded</span> : String(value)}</span>; })}</span>
    </li>; })}</ul>
    <p className="mt-2 text-[11px] leading-4 text-text-tertiary">{cohort.meaning}</p>
  </section>;
}
