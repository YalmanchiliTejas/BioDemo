'use client';

import { useEffect, useMemo, useRef, useState, type MouseEvent } from 'react';
import { niceTicks } from '@/components/ScientificPlot';
import { formatValue, type TrendSeries } from '@/lib/trends-api';

/** Categorical slots in fixed order (validated for colour-vision separation on a light surface). A batch keeps its slot while highlighted. */
export const SERIES_COLORS = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948'];
const CONTEXT = '#94a3b8';   // batches drawn for context, not identity
const GRID = '#e9edf2';
const AXIS = '#cbd5e1';
const LIMIT = '#b45309';
const CRITICAL = '#b91c1c';
const MONO = 'JetBrains Mono, monospace';

export type Limits = { low: number | null; high: number | null; critical_low: number | null; critical_high: number | null };
const limitLines = (l?: Limits | null) => !l ? [] : ([
  ['high', l.high, LIMIT], ['low', l.low, LIMIT], ['critical high', l.critical_high, CRITICAL], ['critical low', l.critical_low, CRITICAL],
] as Array<[string, number | null, string]>).filter((x): x is [string, number, string] => x[1] != null);
export const outside = (v: number, l?: Limits | null) => !!l && ((l.high != null && v > l.high) || (l.low != null && v < l.low)
  || (l.critical_high != null && v > l.critical_high) || (l.critical_low != null && v < l.critical_low));

function useWidth() {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(720);
  useEffect(() => {
    const el = ref.current; if (!el) return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(300, e.contentRect.width)));
    ro.observe(el); return () => ro.disconnect();
  }, []);
  return [ref, width] as const;
}

function domain(values: number[], limits?: Limits | null) {
  const all = [...values, ...limitLines(limits).map(l => l[1])];
  const lo = Math.min(...all), hi = Math.max(...all);
  const pad = (hi - lo) * 0.08 || Math.abs(hi) * 0.05 || 1;
  return [lo - pad, hi + pad] as const;
}

function LimitMarks({ limits, y, left, right }: { limits?: Limits | null; y: (v: number) => number; left: number; right: number }) {
  return <>{limitLines(limits).map(([label, value, color]) => <g key={label}>
    <line x1={left} x2={right} y1={y(value)} y2={y(value)} stroke={color} strokeWidth="1" strokeDasharray="5 4" />
    <text x={right - 4} y={y(value) - 4} textAnchor="end" fontSize="10" className="fill-text-secondary">{label} {formatValue(value)}</text>
  </g>)}</>;
}

const M = { top: 14, right: 16, bottom: 44, left: 56 };

/** One value per batch, in the order deliveries arrived: where a batch sits against the others and against the limits. */
export function BatchComparisonChart({ rows, unit, limits, selected, onSelect, height = 280 }: {
  rows: Array<{ series: TrendSeries; value: number; at: number | null }>;
  unit: string; limits?: Limits | null; selected: Set<string>; onSelect: (key: string) => void; height?: number;
}) {
  const [ref, width] = useWidth();
  const [hover, setHover] = useState<number | null>(null);
  const iw = width - M.left - M.right, ih = height - M.top - M.bottom;
  const [y0, y1] = useMemo(() => domain(rows.map(r => r.value), limits), [rows, limits]);
  const x = (i: number) => M.left + (rows.length === 1 ? iw / 2 : (i + 0.5) * (iw / rows.length));
  const y = (v: number) => M.top + ih - ((v - y0) / (y1 - y0)) * ih;
  const mean = rows.reduce((a, r) => a + r.value, 0) / rows.length;
  const every = Math.max(1, Math.ceil(rows.length / Math.max(1, Math.floor(iw / 76))));
  const nearest = (e: MouseEvent<SVGSVGElement>) => {
    const px = e.clientX - e.currentTarget.getBoundingClientRect().left;
    return Math.max(0, Math.min(rows.length - 1, Math.floor(((px - M.left) / iw) * rows.length)));
  };
  const focus = hover == null ? null : rows[hover];
  return (
    <div ref={ref} className="relative w-full">
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" className="block cursor-pointer"
        aria-label={`One value per batch in ${unit || 'recorded units'}, ${rows.length} batches in delivery order`}
        onMouseMove={e => setHover(nearest(e))} onMouseLeave={() => setHover(null)} onClick={e => onSelect(rows[nearest(e)].series.key)}>
        {niceTicks(y0, y1, 5).map(t => <g key={t}>
          <line x1={M.left} x2={M.left + iw} y1={y(t)} y2={y(t)} stroke={GRID} />
          <text x={M.left - 8} y={y(t) + 3.5} textAnchor="end" fontSize="10" fontFamily={MONO} className="fill-text-tertiary">{formatValue(t)}</text>
        </g>)}
        <line x1={M.left} x2={M.left + iw} y1={M.top + ih} y2={M.top + ih} stroke={AXIS} />
        <LimitMarks limits={limits} y={y} left={M.left} right={M.left + iw} />
        {rows.length > 1 && <g>
          <line x1={M.left} x2={M.left + iw} y1={y(mean)} y2={y(mean)} stroke="#64748b" strokeWidth="1" strokeDasharray="2 3" />
          <text x={M.left + 4} y={y(mean) - 4} fontSize="10" className="fill-text-secondary">mean of shown batches {formatValue(mean)}</text>
        </g>}
        {hover != null && <rect x={x(hover) - iw / rows.length / 2} width={iw / rows.length} y={M.top} height={ih} fill="#0f172a" opacity="0.04" />}
        <path d={rows.map((r, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(r.value).toFixed(1)}`).join('')} fill="none" stroke={SERIES_COLORS[0]} strokeWidth="1.25" opacity="0.45" />
        {rows.map((r, i) => {
          const out = outside(r.value, limits), on = selected.has(r.series.key);
          return <g key={r.series.key}>
            {on && <circle cx={x(i)} cy={y(r.value)} r="8" fill="none" stroke="#0f172a" strokeWidth="1.25" />}
            {/* Outside a limit is a different shape as well as a different colour. */}
            {out ? <rect x={x(i) - 4.5} y={y(r.value) - 4.5} width="9" height="9" transform={`rotate(45 ${x(i)} ${y(r.value)})`} fill={CRITICAL} stroke="#fff" strokeWidth="2" />
              : <circle cx={x(i)} cy={y(r.value)} r={hover === i ? 5.5 : 4.5} fill={SERIES_COLORS[0]} stroke="#fff" strokeWidth="2" />}
            {i % every === 0 && <text x={x(i)} y={M.top + ih + 15} textAnchor="middle" fontSize="10" fontFamily={MONO} className="fill-text-tertiary">
              {r.series.batch.length > 12 ? `${r.series.batch.slice(0, 11)}…` : r.series.batch || '(no batch)'}</text>}
          </g>;
        })}
        <text x={M.left + iw / 2} y={height - 6} textAnchor="middle" fontSize="10" className="fill-text-muted">Batches, oldest delivery first</text>
      </svg>
      {focus && hover != null && <div className="pointer-events-none absolute z-10 w-max max-w-[260px] rounded-control border border-border-hairline bg-surface/95 px-2.5 py-2 text-[11px] shadow-md"
        style={{ left: Math.max(0, Math.min(x(hover) + 12, width - 240)), top: 8 }}>
        <p className="text-[13px] font-semibold tabular-nums text-text-primary">{formatValue(focus.value)} <span className="font-normal text-text-tertiary">{unit}</span></p>
        <p className="font-mono text-text-secondary">{focus.series.batch || '(no batch)'}</p>
        <p className="text-text-tertiary">{focus.series.delivery_name ?? 'Delivery'} · {focus.series.summary.n.toLocaleString()} readings{focus.at != null ? ` · at ${formatValue(focus.at)} h` : ''}</p>
        {outside(focus.value, limits) && <p className="font-medium text-status-critical">Outside the specification limit</p>}
        {!focus.series.delivery_verified && <p className="text-amber-700">Delivery not fully verified yet</p>}
        <p className="mt-1 text-text-muted">Click to {selected.has(focus.series.key) ? 'remove the highlight' : 'highlight this batch'}</p>
      </div>}
    </div>
  );
}

/** Index of the point nearest in time (points are in time order). */
function nearestIndex(points: TrendSeries['points'], t: number) {
  let lo = 0, hi = points.length - 1;
  while (lo < hi) { const mid = (lo + hi) >> 1; if (points[mid][0] < t) lo = mid + 1; else hi = mid; }
  return lo > 0 && Math.abs(points[lo - 1][0] - t) <= Math.abs(points[lo][0] - t) ? lo - 1 : lo;
}

const P = { top: 14, right: 84, bottom: 36, left: 56 };

/** Every batch against process time. All batches give context in grey; highlighted ones carry colour and a label. */
export function BatchProfileChart({ series, unit, limits, colors, onSelect, height = 320 }: {
  series: TrendSeries[]; unit: string; limits?: Limits | null; colors: Record<string, string>; onSelect: (key: string) => void; height?: number;
}) {
  const [ref, width] = useWidth();
  const [hover, setHover] = useState<{ t: number; near: string | null } | null>(null);
  const drawn = useMemo(() => series.filter(s => s.points.length), [series]);
  const iw = width - P.left - P.right, ih = height - P.top - P.bottom;
  const [x0, x1, y0, y1] = useMemo(() => {
    const times = drawn.flatMap(s => [s.points[0][0], s.points[s.points.length - 1][0]]);
    const [lo, hi] = domain(drawn.flatMap(s => [s.summary.min.value, s.summary.max.value]), limits);
    const t0 = Math.min(...times), t1 = Math.max(...times);
    return [t0, t1 === t0 ? t0 + 1 : t1, lo, hi];
  }, [drawn, limits]);
  const x = (t: number) => P.left + ((t - x0) / (x1 - x0)) * iw;
  const y = (v: number) => P.top + ih - ((v - y0) / (y1 - y0)) * ih;
  const path = (s: TrendSeries) => s.points.map((p, i) => `${i ? 'L' : 'M'}${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`).join('');
  const highlighted = drawn.filter(s => colors[s.key]);
  const at = (e: MouseEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const t = x0 + (Math.max(0, Math.min(iw, e.clientX - rect.left - P.left)) / iw) * (x1 - x0), py = e.clientY - rect.top;
    let near: string | null = null, best = 24;   // only a line within 24px of the pointer counts as pointed at
    for (const s of drawn) {
      const p = s.points[nearestIndex(s.points, t)];
      const d = Math.hypot(x(p[0]) - x(t), y(p[1]) - py);
      if (d < best) { best = d; near = s.key; }
    }
    return { t, near };
  };
  if (!drawn.length) return <p className="px-1 py-8 text-center text-[13px] text-text-secondary">These batches have no time recorded for this parameter, so there is no profile to draw. The comparison across batches still applies.</p>;
  // Tooltip rows: every highlighted batch, plus the line under the pointer.
  const tolerance = (x1 - x0) * 0.05;
  const readout = hover ? drawn.filter(s => colors[s.key] || s.key === hover.near).map(s => {
    const p = s.points[nearestIndex(s.points, hover.t)];
    return { s, p: Math.abs(p[0] - hover.t) <= tolerance ? p : null };
  }) : [];
  // End labels for up to four highlighted batches, nudged apart so they never overlap.
  const labels = highlighted.slice(0, 4).map(s => ({ s, at: y(s.points[s.points.length - 1][1]) })).sort((a, b) => a.at - b.at);
  for (let i = 1; i < labels.length; i++) if (labels[i].at - labels[i - 1].at < 12) labels[i].at = labels[i - 1].at + 12;
  return (
    <div ref={ref} className="relative w-full">
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" className="block cursor-crosshair"
        aria-label={`${drawn.length} batch profiles against process time in hours, values in ${unit || 'recorded units'}`}
        onMouseMove={e => setHover(at(e))} onMouseLeave={() => setHover(null)} onClick={e => { const hit = at(e).near; if (hit) onSelect(hit); }}>
        {niceTicks(y0, y1, 5).map(t => <g key={t}>
          <line x1={P.left} x2={P.left + iw} y1={y(t)} y2={y(t)} stroke={GRID} />
          <text x={P.left - 8} y={y(t) + 3.5} textAnchor="end" fontSize="10" fontFamily={MONO} className="fill-text-tertiary">{formatValue(t)}</text>
        </g>)}
        {niceTicks(x0, x1, Math.max(4, Math.floor(iw / 90))).map(t => <text key={t} x={x(t)} y={P.top + ih + 15} textAnchor="middle" fontSize="10" fontFamily={MONO} className="fill-text-tertiary">{formatValue(t)}</text>)}
        <line x1={P.left} x2={P.left + iw} y1={P.top + ih} y2={P.top + ih} stroke={AXIS} />
        <LimitMarks limits={limits} y={y} left={P.left} right={P.left + iw} />
        {drawn.filter(s => !colors[s.key]).map(s => <path key={s.key} d={path(s)} fill="none" stroke={CONTEXT} strokeLinejoin="round"
          strokeWidth={hover?.near === s.key ? 2 : 1} opacity={hover?.near === s.key ? 1 : 0.5} />)}
        {highlighted.map(s => <path key={s.key} d={path(s)} fill="none" stroke={colors[s.key]} strokeWidth="2" strokeLinejoin="round" />)}
        {/* A batch with a single reading has no line to show; mark the reading itself. */}
        {drawn.filter(s => s.points.length === 1).map(s => <circle key={s.key} cx={x(s.points[0][0])} cy={y(s.points[0][1])} r="4" fill={colors[s.key] ?? CONTEXT} stroke="#fff" strokeWidth="2" />)}
        {labels.map(({ s, at: ly }) => <g key={s.key}>
          <circle cx={x(s.points[s.points.length - 1][0])} cy={y(s.points[s.points.length - 1][1])} r="3" fill={colors[s.key]} />
          <text x={P.left + iw + 8} y={ly + 3.5} fontSize="10" fontFamily={MONO} className="fill-text-secondary">{s.batch.length > 11 ? `${s.batch.slice(0, 10)}…` : s.batch}</text>
        </g>)}
        {hover && <g pointerEvents="none">
          <line x1={x(hover.t)} x2={x(hover.t)} y1={P.top} y2={P.top + ih} stroke="#0f172a" strokeOpacity="0.3" />
          {readout.map(({ s, p }) => p && <circle key={s.key} cx={x(p[0])} cy={y(p[1])} r="4" fill="#fff" stroke={colors[s.key] ?? '#475569'} strokeWidth="2" />)}
        </g>}
        <text x={P.left + iw / 2} y={height - 4} textAnchor="middle" fontSize="10" className="fill-text-muted">Process time (h)</text>
      </svg>
      {hover && <div className="pointer-events-none absolute z-10 w-max max-w-[280px] rounded-control border border-border-hairline bg-surface/95 px-2.5 py-2 text-[11px] tabular-nums shadow-md"
        style={{ left: Math.max(0, Math.min(x(hover.t) + 12, width - 250)), top: 8 }}>
        <p className="font-mono text-text-tertiary">{formatValue(hover.t)} h</p>
        {readout.map(({ s, p }) => <div key={s.key} className="flex items-center gap-1.5 whitespace-nowrap">
          <span className="h-0.5 w-3 rounded" style={{ background: colors[s.key] ?? CONTEXT }} />
          <span className="font-medium text-text-primary">{p ? formatValue(p[1]) : '—'}</span>
          <span className="font-mono text-text-secondary">{s.batch || '(no batch)'}</span>
          {!colors[s.key] && <span className="text-text-muted">click to highlight</span>}
        </div>)}
        {!readout.length && <p className="text-text-muted">Point at a line to read it</p>}
      </div>}
    </div>
  );
}
