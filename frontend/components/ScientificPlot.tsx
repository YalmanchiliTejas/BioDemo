'use client';

import { useEffect, useId, useMemo, useRef, useState } from 'react';
import type { Point } from '@/fixtures/timeseries';

export interface ScientificPlotProps {
  batches: Array<{
    id: string;
    color: string;
    dataPoints: Array<Point>;
  }>;
  variableName: string;
  unit: string;
  referenceEnvelope?: { min: number; max: number };
  missingDataInterval?: { startHour: number; endHour: number; annotation: string };
  kalmanStateActive?: boolean;
  selectedWindow?: [number, number];
  onWindowSelect?: (window: [number, number]) => void;
  /** Synchronized crosshair across stacked plots. */
  hoverHour?: number | null;
  onHoverHour?: (h: number | null) => void;
  height?: number;
  xDomain?: [number, number];
  /** Vertical event markers, e.g. the T+264.4h pressure spike. */
  markers?: Array<{ hour: number; label: string; tone?: 'critical' | 'warning' | 'neutral' }>;
  /** Optional secondary series drawn against a right-hand axis. */
  secondary?: { label: string; unit: string; color: string; dataPoints: Point[] };
  /** Show x-axis tick labels (hide on upper plots in a stack). */
  showXAxis?: boolean;
  xLabel?: string;
}

const M = { top: 10, right: 52, bottom: 24, left: 48 };

function niceTicks(min: number, max: number, count = 5) {
  const span = max - min || 1;
  const step0 = span / count;
  const mag = 10 ** Math.floor(Math.log10(step0));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= step0) ?? step0;
  const out: number[] = [];
  for (let v = Math.ceil(min / step) * step; v <= max + 1e-9; v += step) out.push(+v.toFixed(6));
  return out;
}

function fmt(v: number) {
  const a = Math.abs(v);
  return a >= 100 ? v.toFixed(0) : a >= 10 ? v.toFixed(1) : v.toFixed(2);
}

export function ScientificPlot({
  batches, variableName, unit, referenceEnvelope, missingDataInterval, kalmanStateActive = true, selectedWindow, onWindowSelect,
  hoverHour, onHoverHour, height = 200, xDomain = [0, 280], markers = [], secondary, showXAxis = true, xLabel = 'Elapsed batch time (h)',
}: ScientificPlotProps) {
  const uid = useId().replace(/:/g, '');
  const wrapRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(720);
  const [drag, setDrag] = useState<[number, number] | null>(null);
  const [localHover, setLocalHover] = useState<number | null>(null);
  const hover = hoverHour !== undefined ? hoverHour : localHover;
  const setHover = onHoverHour ?? setLocalHover;

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(320, e.contentRect.width)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const iw = width - M.left - M.right;
  const ih = height - M.top - M.bottom;

  const [y0, y1] = useMemo(() => {
    const vals = batches.flatMap((b) => b.dataPoints.filter((p) => p.elapsedHours >= xDomain[0] && p.elapsedHours <= xDomain[1]).map((p) => p.value));
    if (referenceEnvelope) vals.push(referenceEnvelope.min, referenceEnvelope.max);
    const lo = Math.min(...vals);
    const hi = Math.max(...vals);
    const pad = (hi - lo) * 0.08 || 1;
    return [lo - pad, hi + pad];
  }, [batches, referenceEnvelope, xDomain]);

  const [s0, s1] = useMemo(() => {
    if (!secondary) return [0, 1];
    const v = secondary.dataPoints.map((p) => p.value);
    const lo = Math.min(...v), hi = Math.max(...v), pad = (hi - lo) * 0.1 || 1;
    return [lo - pad, hi + pad];
  }, [secondary]);

  const x = (h: number) => M.left + ((h - xDomain[0]) / (xDomain[1] - xDomain[0])) * iw;
  const y = (v: number) => M.top + ih - ((v - y0) / (y1 - y0)) * ih;
  const ys = (v: number) => M.top + ih - ((v - s0) / (s1 - s0)) * ih;
  const inv = (px: number) => xDomain[0] + ((px - M.left) / iw) * (xDomain[1] - xDomain[0]);

  const paths = (pts: Point[], yy: (v: number) => number) => {
    const inDom = pts.filter((p) => p.elapsedHours >= xDomain[0] && p.elapsedHours <= xDomain[1]);
    let solid = '';
    let dashed = '';
    let prev: Point | null = null;
    for (const p of inDom) {
      const cmd = `${x(p.elapsedHours).toFixed(1)},${yy(p.value).toFixed(1)}`;
      if (p.imputed) {
        if (kalmanStateActive) dashed += (prev && !prev.imputed ? `M${x(prev.elapsedHours).toFixed(1)},${yy(prev.value).toFixed(1)}L` : prev?.imputed ? 'L' : 'M') + cmd;
        prev = p;
        continue;
      }
      if (prev?.imputed && kalmanStateActive) dashed += 'L' + cmd;
      solid += (!prev || prev.imputed ? 'M' : 'L') + cmd;
      prev = p;
    }
    return { solid, dashed };
  };

  const xTicks = niceTicks(xDomain[0], xDomain[1], Math.max(4, Math.floor(iw / 90)));
  const yTicks = niceTicks(y0, y1, 4);

  const valueAt = (pts: Point[], h: number) => {
    let best: Point | null = null;
    for (const p of pts) if (!best || Math.abs(p.elapsedHours - h) < Math.abs(best.elapsedHours - h)) best = p;
    // No reading near the cursor (e.g. before feeding starts): show nothing rather than a distant value.
    return best && Math.abs(best.elapsedHours - h) <= 6 ? best : null;
  };

  const toHour = (e: React.MouseEvent<SVGSVGElement>) => {
    const rect = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
    const px = e.clientX - rect.left;
    return Math.max(xDomain[0], Math.min(xDomain[1], inv(px)));
  };

  const win = drag ?? selectedWindow;

  return (
    <div ref={wrapRef} className="relative w-full select-none">
      <div className="flex items-center justify-between px-1 pb-1">
        <p className="text-[12px] font-semibold text-text-primary">
          {variableName} <span className="font-normal text-text-tertiary">({unit})</span>
          {secondary && <span className="ml-2 font-normal" style={{ color: secondary.color }}>— {secondary.label} ({secondary.unit}, right axis)</span>}
        </p>
        {hover !== null && hover !== undefined && (
          <p className="text-[11px] font-mono text-text-tertiary tabular-nums">T+{hover.toFixed(1)}h</p>
        )}
      </div>
      <svg
        width={width}
        height={height}
        role="img"
        aria-label={`${variableName} by elapsed hour for ${batches.map((b) => b.id).join(', ')}`}
        className="block cursor-crosshair"
        onMouseMove={(e) => {
          const h = toHour(e);
          setHover(h);
          if (drag) setDrag([drag[0], h]);
        }}
        onMouseLeave={() => { setHover(null); setDrag(null); }}
        onMouseDown={(e) => onWindowSelect && setDrag([toHour(e), toHour(e)])}
        onMouseUp={() => {
          if (drag && onWindowSelect && Math.abs(drag[1] - drag[0]) > 2) onWindowSelect([Math.min(...drag), Math.max(...drag)] as [number, number]);
          setDrag(null);
        }}
      >
        <defs>
          <pattern id={`hatch-${uid}`} width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <rect width="6" height="6" fill="#fef3c7" />
            <line x1="0" y1="0" x2="0" y2="6" stroke="#d97706" strokeWidth="1.5" opacity="0.55" />
          </pattern>
          <clipPath id={`clip-${uid}`}><rect x={M.left} y={M.top} width={iw} height={ih} /></clipPath>
        </defs>

        {/* grid */}
        {yTicks.map((t) => (
          <g key={`y${t}`}>
            <line x1={M.left} x2={M.left + iw} y1={y(t)} y2={y(t)} stroke="#e2e8f0" strokeWidth="1" />
            <text x={M.left - 6} y={y(t) + 3.5} textAnchor="end" className="fill-text-tertiary" fontSize="10" fontFamily="JetBrains Mono, monospace">{fmt(t)}</text>
          </g>
        ))}
        {xTicks.map((t) => (
          <g key={`x${t}`}>
            <line x1={x(t)} x2={x(t)} y1={M.top} y2={M.top + ih} stroke="#f1f5f9" strokeWidth="1" />
            {showXAxis && <text x={x(t)} y={M.top + ih + 15} textAnchor="middle" className="fill-text-tertiary" fontSize="10" fontFamily="JetBrains Mono, monospace">{t}</text>}
          </g>
        ))}
        <line x1={M.left} x2={M.left + iw} y1={M.top + ih} y2={M.top + ih} stroke="#cbd5e1" />

        <g clipPath={`url(#clip-${uid})`}>
          {referenceEnvelope && (
            <rect x={M.left} width={iw} y={y(referenceEnvelope.max)} height={Math.max(0, y(referenceEnvelope.min) - y(referenceEnvelope.max))} fill="#059669" opacity="0.06" />
          )}
          {referenceEnvelope && (
            <>
              <line x1={M.left} x2={M.left + iw} y1={y(referenceEnvelope.max)} y2={y(referenceEnvelope.max)} stroke="#059669" strokeDasharray="3 3" opacity="0.5" />
              <line x1={M.left} x2={M.left + iw} y1={y(referenceEnvelope.min)} y2={y(referenceEnvelope.min)} stroke="#059669" strokeDasharray="3 3" opacity="0.5" />
            </>
          )}

          {missingDataInterval && (
            <rect
              x={x(missingDataInterval.startHour) - 3}
              width={Math.max(6, x(missingDataInterval.endHour) - x(missingDataInterval.startHour) + 6)}
              y={M.top}
              height={ih}
              fill={`url(#hatch-${uid})`}
            >
              <title>{missingDataInterval.annotation}</title>
            </rect>
          )}

          {win && (
            <rect x={x(Math.min(...win))} width={Math.abs(x(win[1]) - x(win[0]))} y={M.top} height={ih} fill="#0e7490" opacity="0.08" stroke="#0e7490" strokeOpacity="0.4" />
          )}

          {markers.map((m) => (
            <g key={m.label}>
              <line x1={x(m.hour)} x2={x(m.hour)} y1={M.top} y2={M.top + ih} stroke={m.tone === 'warning' ? '#d97706' : m.tone === 'neutral' ? '#64748b' : '#dc2626'} strokeWidth="1.25" strokeDasharray="4 3" />
            </g>
          ))}

          {secondary && (() => {
            const p = paths(secondary.dataPoints, ys);
            return <path d={p.solid} fill="none" stroke={secondary.color} strokeWidth="1.25" opacity="0.8" strokeDasharray="2 2" />;
          })()}

          {batches.map((b) => {
            const p = paths(b.dataPoints, y);
            return (
              <g key={b.id}>
                <path d={p.solid} fill="none" stroke={b.color} strokeWidth={b.id === 'MES-26073' ? 1.9 : 1.4} strokeLinejoin="round" />
                {p.dashed && <path d={p.dashed} fill="none" stroke={b.color} strokeWidth="1.6" strokeDasharray="3 3" opacity="0.8" />}
              </g>
            );
          })}
        </g>

        {markers.map((m) => (
          <text key={m.label + 't'} x={Math.min(x(m.hour) + 4, M.left + iw - 4)} y={M.top + 10} textAnchor={x(m.hour) > M.left + iw - 120 ? 'end' : 'start'} fontSize="10" fontWeight="600" fill={m.tone === 'warning' ? '#b45309' : m.tone === 'neutral' ? '#475569' : '#b91c1c'}>
            {m.label}
          </text>
        ))}

        {secondary && niceTicks(s0, s1, 4).map((t) => (
          <text key={`s${t}`} x={M.left + iw + 6} y={ys(t) + 3.5} fontSize="10" fill={secondary.color} fontFamily="JetBrains Mono, monospace">{fmt(t)}</text>
        ))}

        {hover !== null && hover !== undefined && (
          <g pointerEvents="none">
            <line x1={x(hover)} x2={x(hover)} y1={M.top} y2={M.top + ih} stroke="#0f172a" strokeOpacity="0.35" />
            {batches.map((b) => {
              const p = valueAt(b.dataPoints, hover);
              if (!p) return null;
              return <circle key={b.id} cx={x(p.elapsedHours)} cy={y(p.value)} r="3" fill="#fff" stroke={b.color} strokeWidth="1.5" />;
            })}
          </g>
        )}
        {showXAxis && <text x={M.left + iw / 2} y={height - 1} textAnchor="middle" fontSize="10" className="fill-text-muted">{xLabel}</text>}
      </svg>

      {hover !== null && hover !== undefined && (
        <div
          className="pointer-events-none absolute z-10 rounded-control border border-border-hairline bg-surface/95 shadow-md px-2 py-1.5 text-[11px] tabular-nums"
          style={{ left: Math.min(x(hover) + 10, width - 170), top: 28 }}
        >
          {batches.map((b) => {
            const p = valueAt(b.dataPoints, hover);
            return (
              <div key={b.id} className="flex items-center gap-1.5 whitespace-nowrap">
                <span className="h-2 w-2 rounded-full" style={{ background: b.color }} />
                <span className="font-mono text-text-secondary">{b.id}</span>
                <span className="ml-auto pl-2 font-medium text-text-primary">{p ? fmt(p.value) : '—'}</span>
                {p?.imputed && <span className="text-amber-700">imputed</span>}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export function PlotLegend({ batches, showGap = true, kalman = true }: { batches: Array<{ id: string; color: string }>; showGap?: boolean; kalman?: boolean }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-text-secondary">
      {batches.map((b) => (
        <span key={b.id} className="flex items-center gap-1.5"><span className="h-0.5 w-4 rounded" style={{ background: b.color }} /><span className="font-mono">{b.id}</span></span>
      ))}
      <span className="flex items-center gap-1.5"><span className="h-2.5 w-4 rounded-sm bg-emerald-600/10 border border-dashed border-emerald-600/50" />Reference envelope</span>
      {showGap && (
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-4 rounded-sm" style={{ background: 'repeating-linear-gradient(45deg,#fef3c7 0 3px,#f59e0b 3px 4px)' }} />
          Missing telemetry{kalman ? ' (dashed = imputed, excluded from stats)' : ''}
        </span>
      )}
    </div>
  );
}
