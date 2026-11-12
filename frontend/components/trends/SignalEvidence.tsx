'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import { ArrowUpRight } from 'lucide-react';
import { parameterLabel } from '@/lib/cmo-api';
import type { Signal } from '@/lib/signals-api';
import { getTrends, statistic, type TrendData } from '@/lib/trends-api';
import { BatchComparisonChart, BatchProfileChart, SERIES_COLORS, type Limits } from './TrendCharts';

type State = { status: 'loading' } | { status: 'none'; why: string } | { status: 'ready'; data: TrendData };

/** The flagged value drawn against its limits, its own batch profile and every other batch: enough to make the call without opening a file. */
export function SignalEvidence({ signal }: { signal: Signal }) {
  const [state, setState] = useState<State>({ status: 'loading' });
  const [extra, setExtra] = useState<Record<string, number>>({});
  const wanted = (signal.parameter ?? '').trim().toLowerCase();
  useEffect(() => {
    if (!wanted) { setState({ status: 'none', why: 'This signal is not about a measured parameter, so there is nothing to plot.' }); return; }
    let alive = true;
    getTrends().then(async catalogue => {
      const match = catalogue.parameters.find(p => p.id.toLowerCase() === wanted);
      if (!match) return { status: 'none', why: `No accepted delivery values for ${signal.parameter} to plot. The value above came from ${signal.source?.system ?? 'another source'}.` } as State;
      return { status: 'ready', data: await getTrends<TrendData>(match.id) } as State;
    }).then(next => { if (alive) setState(next); })
      .catch(() => { if (alive) setState({ status: 'none', why: 'The values behind this signal could not be loaded for a chart. The figures above are unaffected.' }); });
    return () => { alive = false; };
  }, [wanted, signal.parameter, signal.source?.system]);

  const data = state.status === 'ready' ? state.data : null;
  const subject = signal.subject?.kind === 'batch' ? signal.subject.id : null;
  const own = useMemo(() => (data?.series ?? []).filter(s => subject != null && s.batch === subject), [data, subject]);
  const colors = useMemo(() => {
    const slots: Record<string, number> = { ...extra };
    own.forEach(s => { slots[s.key] = 0; });
    return Object.fromEntries(Object.entries(slots).map(([key, slot]) => [key, SERIES_COLORS[slot]]));
  }, [own, extra]);
  const value = typeof signal.value === 'number' ? signal.value : Number(signal.value);
  const l = signal.limit;
  // Compare batches on the figure the rule is about: the peak for an upper limit, the trough for a lower one.
  const stat: 'max' | 'min' | 'last' = !l || !Number.isFinite(value) ? 'last'
    : (l.high != null && value > l.high) || (l.critical_high != null && value > l.critical_high) ? 'max'
    : (l.low != null && value < l.low) || (l.critical_low != null && value < l.critical_low) ? 'min' : 'last';

  if (state.status === 'loading') return <p role="status" className="text-sm text-text-tertiary">Loading the values behind this signal…</p>;
  if (!data) return <p className="text-sm text-text-tertiary">{state.status === 'none' ? state.why : ''}</p>;
  const unit = data.series[0]?.unit ?? '';
  const sameUnit = !signal.unit || !unit || signal.unit === unit;
  const limits: Limits | null = l && sameUnit ? { low: l.low ?? null, high: l.high ?? null, critical_low: l.critical_low ?? null, critical_high: l.critical_high ?? null } : null;
  const toggle = (key: string) => setExtra(prev => {
    if (own.some(s => s.key === key)) return prev;   // the flagged batch stays highlighted
    if (key in prev) { const { [key]: _removed, ...rest } = prev; return rest; }
    const free = SERIES_COLORS.findIndex((_, i) => i > 0 && !Object.values(prev).includes(i));
    return free < 0 ? prev : { ...prev, [key]: free };
  });
  const rows = data.series.map(series => ({ series, value: statistic(series.summary, stat), at: series.summary[stat].time_h }));
  const label = { max: 'Highest', min: 'Lowest', last: 'Final' }[stat];
  return <div className="space-y-4" data-testid="signal-evidence">
    <p className="text-[13px] text-text-secondary">
      {own.length ? <>Batch <span className="font-mono">{subject}</span> is highlighted among {data.series.length} batches with accepted {parameterLabel(data.parameter)} values.</>
        : subject ? <>Batch <span className="font-mono">{subject}</span> has no accepted delivery values for {parameterLabel(data.parameter)}; the {data.series.length} batches that do are shown for context.</>
        : <>The {data.series.length} batches with accepted {parameterLabel(data.parameter)} values, for context.</>}
      {' '}{limits ? 'Dashed lines are the limits in force when the signal fired.' : l ? `Limits are in ${signal.unit}; they are not drawn against values in ${unit}.` : ''}
    </p>
    <div><p className="mb-1 text-xs font-medium text-text-primary">Over process time {unit && <span className="font-normal text-text-tertiary">({unit})</span>}</p>
      <BatchProfileChart series={data.series} unit={unit} limits={limits} colors={colors} onSelect={toggle} height={260} /></div>
    <div><p className="mb-1 text-xs font-medium text-text-primary">{label} value of each batch {unit && <span className="font-normal text-text-tertiary">({unit})</span>}</p>
      <BatchComparisonChart rows={rows} unit={unit} limits={limits} selected={new Set(Object.keys(colors))} onSelect={toggle} height={220} /></div>
    <Link href={`/trends/?parameter=${encodeURIComponent(data.parameter)}`} className="inline-flex items-center gap-1 text-sm font-medium text-brand-teal">Open in Trends to filter, compare and export<ArrowUpRight size={14} /></Link>
  </div>;
}
