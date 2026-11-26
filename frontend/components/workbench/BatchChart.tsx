'use client';

import { useEffect, useMemo, useRef, useState, type MouseEvent } from 'react';
import { niceTicks } from '@/components/ScientificPlot';
import { fig, hours, withUnit } from '@/lib/workbench';

const GRID = '#e9edf2', AXIS = '#cbd5e1', INK = '#0f172a', MONO = 'JetBrains Mono, monospace';
const M = { top: 18, right: 18, bottom: 40, left: 54 };
/** Above this many values the per-point markers are dropped; the lines, the pointer readout and the table remain. */
const MARKER_LIMIT = 400;

export type ChartSeries = { key: string; label: string; color: string; points: [number, number][] };
export type ChartPoint = { key: string; time_h: number; value: number };
export type ChartMark = { time_h: number; from: number; to: number; label: string };

function useWidth() {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(640);
  useEffect(() => {
    const el = ref.current; if (!el) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(300, Math.floor(entry.contentRect.width))));
    observer.observe(el); return () => observer.disconnect();
  }, []);
  return [ref, width] as const;
}

/** One line per batch against elapsed hours. Every plotted value is a recorded sample: nothing is drawn between deliveries' rows
 *  except the straight segment that joins two samples of the same batch. */
export function BatchChart({ series, unit, parameter, mark, selected, onSelect, height = 300 }: {
  series: ChartSeries[]; unit: string | null; parameter: string; mark?: ChartMark | null; selected?: ChartPoint | null;
  onSelect: (point: ChartPoint) => void; height?: number;
}) {
  const [ref, width] = useWidth();
  const [hover, setHover] = useState<ChartPoint | null>(null), [focused, setFocused] = useState(false);
  const drawn = useMemo(() => series.filter(s => s.points.length), [series]);
  const total = drawn.reduce((sum, s) => sum + s.points.length, 0);
  const iw = width - M.left - M.right, ih = height - M.top - M.bottom;
  const [x0, x1, y0, y1] = useMemo(() => {
    const times = drawn.flatMap(s => s.points.map(p => p[0])), values = drawn.flatMap(s => s.points.map(p => p[1]));
    const t0 = Math.min(...times), t1 = Math.max(...times), lo = Math.min(...values), hi = Math.max(...values);
    const pad = (hi - lo) * 0.1 || Math.abs(hi) * 0.05 || 1;
    return [t0, t1 === t0 ? t0 + 1 : t1, lo - pad, hi + pad];
  }, [drawn]);
  if (!drawn.length) return <div ref={ref} className="w-full" />;
  const x = (t: number) => M.left + ((t - x0) / (x1 - x0)) * iw;
  const y = (v: number) => M.top + ih - ((v - y0) / (y1 - y0)) * ih;
  const path = (s: ChartSeries) => s.points.map((p, i) => `${i ? 'L' : 'M'}${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`).join('');
  const nearest = (e: MouseEvent<SVGSVGElement>): ChartPoint | null => {
    const rect = e.currentTarget.getBoundingClientRect(), px = e.clientX - rect.left, py = e.clientY - rect.top;
    let best = 28, found: ChartPoint | null = null;   // the pointer only has to be closest, within 28px
    for (const s of drawn) for (const p of s.points) {
      const d = Math.hypot(x(p[0]) - px, y(p[1]) - py);
      if (d < best) { best = d; found = { key: s.key, time_h: p[0], value: p[1] }; }
    }
    return found;
  };
  const same = (a: ChartPoint | null | undefined, key: string, p: [number, number]) => !!a && a.key === key && a.time_h === p[0] && a.value === p[1];
  const readout = hover ? drawn.flatMap(s => s.points.filter(p => p[0] === hover.time_h).map(p => ({ s, p }))) : [];
  const markSide = mark && x(mark.time_h) > M.left + iw * 0.6 ? 'end' : 'start';
  return (
    <div ref={ref} className="relative w-full">
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="group" className="block cursor-pointer select-none"
        aria-label={`${parameter}${unit ? ` in ${unit}` : ''} against elapsed hours, ${drawn.length} ${drawn.length === 1 ? 'batch' : 'batches'}`}
        onMouseDown={e => e.preventDefault() /* the pointer picks the nearest value; focus stays with the keyboard */} onMouseMove={e => setHover(nearest(e))} onMouseLeave={() => setHover(null)} onClick={e => { const hit = nearest(e); if (hit) onSelect(hit); }}>
        {niceTicks(y0, y1, 5).map(t => <g key={t}>
          <line x1={M.left} x2={M.left + iw} y1={y(t)} y2={y(t)} stroke={GRID} />
          <text x={M.left - 8} y={y(t) + 3.5} textAnchor="end" fontSize="10" fontFamily={MONO} className="fill-text-tertiary">{fig(t)}</text>
        </g>)}
        {niceTicks(x0, x1, Math.max(3, Math.floor(iw / 80))).map(t => <text key={t} x={x(t)} y={M.top + ih + 15} textAnchor="middle" fontSize="10" fontFamily={MONO} className="fill-text-tertiary">{hours(t)}</text>)}
        <line x1={M.left} x2={M.left + iw} y1={M.top + ih} y2={M.top + ih} stroke={AXIS} />
        <text x={M.left} y={10} fontSize="10" className="fill-text-tertiary">{parameter}{unit ? ` (${unit})` : ''}</text>
        <text x={M.left + iw / 2} y={height - 5} textAnchor="middle" fontSize="10" className="fill-text-tertiary">Elapsed time (h)</text>
        {drawn.map(s => <path key={s.key} d={path(s)} fill="none" stroke={s.color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />)}
        {mark && <g pointerEvents="none" data-testid="largest-difference">
          <line x1={x(mark.time_h)} x2={x(mark.time_h)} y1={y(mark.from)} y2={y(mark.to)} stroke={INK} strokeWidth="1.5" strokeDasharray="3 2" />
          {[mark.from, mark.to].map((v, i) => <line key={i} x1={x(mark.time_h) - 4} x2={x(mark.time_h) + 4} y1={y(v)} y2={y(v)} stroke={INK} strokeWidth="1.5" />)}
          <text x={x(mark.time_h) + (markSide === 'end' ? -8 : 8)} y={Math.max(M.top + 10, Math.min(y(mark.from), y(mark.to)) - 8)} textAnchor={markSide} fontSize="10.5" fontWeight="600"
            stroke="#fff" strokeWidth="3" paintOrder="stroke" className="fill-text-primary">{mark.label}</text>
        </g>}
        {drawn.map(s => s.points.map((p, i) => {
          const active = same(hover, s.key, p), chosen = same(selected, s.key, p);
          if (total > MARKER_LIMIT && !active && !chosen && s.points.length > 1) return null;
          return <g key={`${s.key}:${i}`}>
            {(chosen || (active && focused)) && <circle cx={x(p[0])} cy={y(p[1])} r="8" fill="none" stroke={chosen ? INK : '#0e7490'} strokeWidth={chosen ? 1.5 : 2} />}
            <circle cx={x(p[0])} cy={y(p[1])} r={active || chosen ? 5 : 4} fill={s.color} stroke="#fff" strokeWidth="2" />
            {/* The hit area is larger than the mark, and reachable from the keyboard. */}
            <circle cx={x(p[0])} cy={y(p[1])} r="12" fill="transparent" role="button" tabIndex={0} style={{ outline: 'none' }} data-point={`${s.label}@${p[0]}`}
              aria-label={`${s.label}, ${hours(p[0])} h, ${withUnit(p[1], unit)}. Show source.`} aria-pressed={chosen}
              onFocus={() => { setFocused(true); setHover({ key: s.key, time_h: p[0], value: p[1] }); }} onBlur={() => { setFocused(false); setHover(null); }}
              onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect({ key: s.key, time_h: p[0], value: p[1] }); } }} />
          </g>;
        }))}
        {hover && <line pointerEvents="none" x1={x(hover.time_h)} x2={x(hover.time_h)} y1={M.top} y2={M.top + ih} stroke={INK} strokeOpacity="0.25" />}
      </svg>
      {hover && <div role="tooltip" className="pointer-events-none absolute z-10 w-max max-w-[240px] rounded-control border border-border-hairline bg-surface/95 px-2.5 py-2 text-[11px] tabular-nums shadow-md"
        style={{ left: Math.max(0, Math.min(x(hover.time_h) + 12, width - 200)), top: 6 }}>
        <p className="font-mono text-text-tertiary">{hours(hover.time_h)} h</p>
        {readout.map(({ s, p }) => <div key={s.key} className={`flex items-center gap-1.5 whitespace-nowrap ${s.key === hover.key ? '' : 'opacity-70'}`}>
          <span className="h-0.5 w-3 rounded" style={{ background: s.color }} />
          <span className="font-semibold text-text-primary">{withUnit(p[1], unit)}</span><span className="font-mono text-text-secondary">{s.label}</span>
        </div>)}
        <p className="mt-1 text-text-tertiary">Click for the source</p>
      </div>}
    </div>
  );
}
