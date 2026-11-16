'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import { ArrowUpRight } from 'lucide-react';
import { parameterLabel } from '@/lib/cmo-api';
import type { Signal } from '@/lib/signals-api';
import { getTrends, statistic, type TrendData } from '@/lib/trends-api';
import { BatchComparisonChart, BatchProfileChart, SERIES_COLORS, type Limits } from './TrendCharts';

type State = { status: 'loading' } | { status: 'none'; why: string } | { status: 'ready'; data: TrendData };

function HistorianObservations({ signal }: { signal: Signal }) {
  const [selected, setSelected] = useState<string>('');
  const groups = new Map<string, {unit:string;batch:string;points:NonNullable<Signal['observations']>}>();
  for (const raw of signal.observations ?? []) {
    const point = {...raw,value:raw.original_value ?? raw.value,unit:raw.original_unit ?? raw.unit};
    if (typeof point.value !== 'number' || !Number.isFinite(point.value)) continue;
    const unit = point.unit ?? 'unit unknown';
    const batch=point.batch_id ?? signal.subject?.id ?? 'subject unknown';
    const key=JSON.stringify([signal.parameter,unit,batch]);
    groups.set(key,{unit,batch,points:[...(groups.get(key)?.points ?? []),point]});
  }
  return <div className="space-y-3" data-testid="signal-observations"><p className="text-sm">Actual source observations · {signal.subject?.id}. Select a point to retain this signal and batch in Quality.</p>
    {[...groups].map(([key,{unit,batch,points}]) => {
      const provenance=(p:typeof points[number])=>p.evidence_ref ? `${p.evidence_ref.id} revision ${p.evidence_ref.revision}` : 'source revision not supplied';
      const versions=new Map<string,Set<number>>();
      for(const p of points)if(p.evidence_ref){const id=`${p.evidence_ref.kind}:${p.evidence_ref.id}`;versions.set(id,new Set([...(versions.get(id)??[]),p.evidence_ref.revision]));}
      const conflicts=[...versions].filter(([,revisions])=>revisions.size>1).map(([id])=>id);
      const timed = points.filter(p => p.event_time && Number.isFinite(Date.parse(p.event_time))).sort((a,b)=>Date.parse(a.event_time!)-Date.parse(b.event_time!));
      const times=timed.map(p=>Date.parse(p.event_time!)),values=timed.map(p=>p.value!);
      const limits=signal.unit===unit ? Object.entries(signal.limit??{}).filter(([k,v])=>['low','high','critical_low','critical_high'].includes(k)&&typeof v==='number'&&Number.isFinite(v)) as [string,number][] : [];
      const lo=Math.min(...values,...limits.map(l=>l[1])), hi=Math.max(...values,...limits.map(l=>l[1])),t0=Math.min(...times),t1=Math.max(...times);
      const x=(p:typeof timed[number])=>45+((Date.parse(p.event_time!)-t0)/(t1-t0||1))*570;
      const y=(p:typeof timed[number])=>165-((p.value!-lo)/(hi-lo||1))*125;
      return <div key={key}><h3 className="text-xs font-medium">{batch} · {signal.parameter} ({unit}) · source timestamps</h3><p className="text-xs text-text-tertiary">{new Set(points.map(provenance)).size} source revisions · select a point for its exact source</p>
        {conflicts.length>0&&<p className="text-xs" role="status">Multiple revisions of {conflicts.join(', ')} are preserved. Points are shown without a connecting trend; review the source correction.</p>}
        {timed.length>0&&<svg viewBox="0 0 650 210" className="w-full" aria-label={`Source observations in ${unit}`}>
          <line x1="45" x2="620" y1="180" y2="180" stroke="#94a3b8"/>{conflicts.length===0&&<polyline fill="none" stroke="#2a78d6" points={timed.map(p=>`${x(p)},${y(p)}`).join(' ')}/>}
          {limits.map(([name,value])=><g key={name}><line x1="45" x2="620" y1={y({value})} y2={y({value})} stroke="#b45309" strokeDasharray="5 4"/><text x="615" y={y({value})-4} textAnchor="end" fontSize="10">{name.replaceAll('_',' ')} {value} {unit}</text></g>)}
          {timed.map((p,i)=><g key={i}><circle data-testid="signal-observation-point" tabIndex={0} role="button" aria-label={`${batch} ${p.event_time}: ${p.value} ${unit} ${provenance(p)}`} cx={x(p)} cy={y(p)} r="7" fill="#2a78d6" className="cursor-pointer" onClick={()=>setSelected(`${batch} ${p.event_time}: ${p.value} ${unit} ${provenance(p)}`)} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();setSelected(`${batch} ${p.event_time}: ${p.value} ${unit} ${provenance(p)}`);}}}/><text x={x(p)} y={y(p)-12} textAnchor="middle" fontSize="11">{p.value}</text></g>)}
          <text x="45" y="202" fontSize="10">{timed[0].event_time}</text><text x="620" y="202" textAnchor="end" fontSize="10">{timed[timed.length-1].event_time}</text>
        </svg>}
        {points.length>timed.length&&<p className="text-xs">{points.length-timed.length} observations have no usable source timestamp; excluded from the time axis.</p>}
        {signal.limit&&signal.unit!==unit&&<p className="text-xs">Specification units differ; limits are not applied to this series.</p>}
      </div>;
    })}
    {selected&&<p className="text-sm">Selected {selected} · {signal.subject?.id}</p>}
    <Link className="text-sm underline" href={`/quality/?${signal.case_id ? `case=${encodeURIComponent(signal.case_id)}` : `signal=${encodeURIComponent(signal.signal_id)}`}`}>Prepare Quality workspace</Link>
  </div>;
}

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

  if (signal.observations?.some(p => typeof p.value === 'number' && Number.isFinite(p.value))) return <HistorianObservations signal={signal} />;
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
