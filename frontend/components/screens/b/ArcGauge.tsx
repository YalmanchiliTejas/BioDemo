'use client';

import { cn } from '@/lib/cn';

type GaugeStatus = 'ok' | 'warning' | 'critical';

const STATUS_COLOR: Record<GaugeStatus, string> = { ok: '#059669', warning: '#d97706', critical: '#dc2626' };
const STATUS_TEXT: Record<GaugeStatus, string> = { ok: 'Within range', warning: 'Near limit', critical: 'Out of range' };

/**
 * 180° arc gauge with an acceptable band (green), optional hard ceiling marker and a needle.
 * Status is derived from the band unless given explicitly.
 */
export function ArcGauge({
  label, value, unit, min, max, bandLo, bandHi, ceiling, precision = 1, status, caption, className,
}: {
  label: string;
  value: number;
  unit: string;
  min: number;
  max: number;
  bandLo?: number;
  bandHi?: number;
  ceiling?: number;
  precision?: number;
  status?: GaugeStatus;
  caption?: string;
  className?: string;
}) {
  const W = 160, H = 96, cx = 80, cy = 84, r = 64;
  const clamp = (v: number) => Math.max(min, Math.min(max, v));
  const ang = (v: number) => Math.PI * (1 - (clamp(v) - min) / (max - min));
  const pt = (v: number, rr = r) => [cx + rr * Math.cos(ang(v)), cy - rr * Math.sin(ang(v))] as const;
  const arc = (a: number, b: number) => {
    const [x0, y0] = pt(a);
    const [x1, y1] = pt(b);
    return `M${x0.toFixed(2)},${y0.toFixed(2)} A${r},${r} 0 0 1 ${x1.toFixed(2)},${y1.toFixed(2)}`;
  };
  const derived: GaugeStatus =
    status ??
    ((ceiling !== undefined && value > ceiling) || (bandLo !== undefined && value < bandLo) || (bandHi !== undefined && value > bandHi) ? 'critical' : 'ok');
  const [nx, ny] = pt(value, r - 10);
  const [cx0, cy0] = ceiling !== undefined ? pt(ceiling, r + 7) : [0, 0];
  const [cx1, cy1] = ceiling !== undefined ? pt(ceiling, r - 7) : [0, 0];

  return (
    <figure className={cn('flex flex-col items-center min-w-0', className)}>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full max-w-[180px]" role="img" aria-label={`${label}: ${value.toFixed(precision)} ${unit}. ${STATUS_TEXT[derived]}.`}>
        <path d={arc(min, max)} fill="none" stroke="#e2e8f0" strokeWidth="10" strokeLinecap="butt" />
        {bandLo !== undefined && bandHi !== undefined && <path d={arc(bandLo, bandHi)} fill="none" stroke="#059669" strokeOpacity="0.28" strokeWidth="10" />}
        <path d={arc(min, value)} fill="none" stroke={STATUS_COLOR[derived]} strokeWidth="3" />
        {ceiling !== undefined && <line x1={cx0} y1={cy0} x2={cx1} y2={cy1} stroke="#dc2626" strokeWidth="2" />}
        <line x1={cx} y1={cy} x2={nx} y2={ny} stroke="#0f172a" strokeWidth="2" strokeLinecap="round" />
        <circle cx={cx} cy={cy} r="3.5" fill="#0f172a" />
        <text x={cx - r} y={H - 1} fontSize="9" textAnchor="middle" fill="#94a3b8" fontFamily="JetBrains Mono, monospace">{min}</text>
        <text x={cx + r} y={H - 1} fontSize="9" textAnchor="middle" fill="#94a3b8" fontFamily="JetBrains Mono, monospace">{max}</text>
      </svg>
      <figcaption className="-mt-1 text-center">
        <p className="text-[11px] font-medium uppercase tracking-wide text-text-tertiary">{label}</p>
        <p className="tabular-nums">
          <span className={cn('text-lg font-semibold', derived === 'critical' ? 'text-status-critical' : derived === 'warning' ? 'text-status-warning' : 'text-text-primary')}>{value.toFixed(precision)}</span>
          <span className="ml-1 text-xs text-text-tertiary">{unit}</span>
        </p>
        {caption && <p className="text-[11px] text-text-tertiary">{caption}</p>}
      </figcaption>
    </figure>
  );
}
