'use client';

import { useMemo, useRef, useState } from 'react';
import { chromatogram } from '@/fixtures/timeseries';

export type PeakLabel = { t: number; label: string; primary?: boolean };

const M = { top: 16, right: 16, bottom: 30, left: 48 };

/** Hand-rolled SVG chromatogram with hover readout. Domain in minutes. */
export function Chromatogram({ domain, peaks, height = 260 }: { domain: [number, number]; peaks: PeakLabel[]; height?: number }) {
  const ref = useRef<SVGSVGElement>(null);
  const [hover, setHover] = useState<{ t: number; mAU: number } | null>(null);
  const width = 760;
  const iw = width - M.left - M.right;
  const ih = height - M.top - M.bottom;

  const pts = useMemo(() => chromatogram.filter((p) => p.t >= domain[0] && p.t <= domain[1]), [domain]);
  const yMax = Math.max(...pts.map((p) => p.mAU)) * 1.12;
  const yMin = Math.min(0, ...pts.map((p) => p.mAU));
  const x = (t: number) => M.left + ((t - domain[0]) / (domain[1] - domain[0])) * iw;
  const y = (v: number) => M.top + ih - ((v - yMin) / (yMax - yMin)) * ih;

  const path = pts.map((p, i) => `${i ? 'L' : 'M'}${x(p.t).toFixed(1)},${y(p.mAU).toFixed(1)}`).join('');
  const area = `${path}L${x(pts[pts.length - 1].t).toFixed(1)},${y(yMin)}L${x(pts[0].t).toFixed(1)},${y(yMin)}Z`;

  const xTicks: number[] = [];
  const xStep = domain[1] - domain[0] > 4 ? 1 : 0.25;
  for (let t = Math.ceil(domain[0] / xStep) * xStep; t <= domain[1] + 1e-9; t += xStep) xTicks.push(+t.toFixed(2));
  const yStep = yMax > 200 ? 50 : yMax > 40 ? 10 : 5;
  const yTicks: number[] = [];
  for (let v = 0; v <= yMax; v += yStep) yTicks.push(v);

  const onMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const svg = ref.current;
    if (!svg) return;
    const r = svg.getBoundingClientRect();
    const px = ((e.clientX - r.left) / r.width) * width;
    const t = domain[0] + ((px - M.left) / iw) * (domain[1] - domain[0]);
    if (t < domain[0] || t > domain[1]) return setHover(null);
    let best = pts[0];
    for (const p of pts) if (Math.abs(p.t - t) < Math.abs(best.t - t)) best = p;
    setHover(best);
  };

  return (
    <div className="relative">
      <svg
        ref={ref}
        viewBox={`0 0 ${width} ${height}`}
        className="w-full h-auto select-none"
        role="img"
        aria-label={`HPLC chromatogram, absorbance at 280 nm from ${domain[0]} to ${domain[1]} minutes`}
        onMouseMove={onMove}
        onMouseLeave={() => setHover(null)}
      >
        {yTicks.map((v) => (
          <g key={v}>
            <line x1={M.left} x2={width - M.right} y1={y(v)} y2={y(v)} stroke="#e2e8f0" strokeWidth={1} />
            <text x={M.left - 6} y={y(v) + 3} textAnchor="end" fontSize={10} fill="#64748b" className="tabular-nums">{v}</text>
          </g>
        ))}
        {xTicks.map((t) => (
          <g key={t}>
            <line x1={x(t)} x2={x(t)} y1={M.top + ih} y2={M.top + ih + 4} stroke="#94a3b8" />
            <text x={x(t)} y={M.top + ih + 15} textAnchor="middle" fontSize={10} fill="#64748b">{t}</text>
          </g>
        ))}
        <line x1={M.left} x2={width - M.right} y1={M.top + ih} y2={M.top + ih} stroke="#94a3b8" />
        <text x={M.left + iw / 2} y={height - 2} textAnchor="middle" fontSize={10} fill="#64748b">Retention time (min)</text>
        <text x={12} y={M.top + ih / 2} textAnchor="middle" fontSize={10} fill="#64748b" transform={`rotate(-90 12 ${M.top + ih / 2})`}>mAU (280 nm)</text>

        <path d={area} fill="#0e7490" fillOpacity={0.06} />
        <path d={path} fill="none" stroke="#0e7490" strokeWidth={1.4} />

        {peaks.filter((p) => p.t >= domain[0] && p.t <= domain[1]).map((p) => {
          const pk = pts.reduce((a, b) => (Math.abs(b.t - p.t) < Math.abs(a.t - p.t) ? b : a), pts[0]);
          const ly = Math.max(M.top + 10, y(pk.mAU) - 10);
          return (
            <g key={p.t}>
              <line x1={x(p.t)} x2={x(p.t)} y1={ly + 3} y2={y(pk.mAU) - 2} stroke={p.primary ? '#0f172a' : '#94a3b8'} strokeWidth={1} />
              <text x={x(p.t)} y={ly} textAnchor="middle" fontSize={p.primary ? 11 : 10} fontWeight={p.primary ? 600 : 400} fill={p.primary ? '#0f172a' : '#475569'}>
                {p.label} · {p.t.toFixed(2)}
              </text>
            </g>
          );
        })}

        {hover && (
          <g pointerEvents="none">
            <line x1={x(hover.t)} x2={x(hover.t)} y1={M.top} y2={M.top + ih} stroke="#0f172a" strokeDasharray="3 3" strokeWidth={1} />
            <circle cx={x(hover.t)} cy={y(hover.mAU)} r={3} fill="#0e7490" stroke="#fff" strokeWidth={1.5} />
          </g>
        )}
      </svg>
      <div className="absolute top-1 right-2 rounded-control border border-border-hairline bg-surface/95 px-2 py-1 text-[11px] font-mono tabular-nums text-text-secondary" aria-live="polite">
        {hover ? <>RT {hover.t.toFixed(3)} min · {hover.mAU.toFixed(1)} mAU</> : 'Hover trace for readout'}
      </div>
    </div>
  );
}

/** Trapezoidal peak area above a flat baseline within ±halfWidth of the apex (mAU·min). */
export function peakArea(center: number, halfWidth = 0.3, baseline = 2) {
  const pts = chromatogram.filter((p) => p.t >= center - halfWidth && p.t <= center + halfWidth);
  let a = 0;
  for (let i = 1; i < pts.length; i++) {
    const h0 = Math.max(0, pts[i - 1].mAU - baseline);
    const h1 = Math.max(0, pts[i].mAU - baseline);
    a += ((h0 + h1) / 2) * (pts[i].t - pts[i - 1].t);
  }
  return a;
}
