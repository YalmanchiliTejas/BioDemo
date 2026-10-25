'use client';

/** Simplified, not-to-engineering-scale bioreactor schematic for side-by-side site comparison. */
export function BioreactorSchematic({ variant }: { variant: 'mesa' | 'durham' }) {
  const isMesa = variant === 'mesa';
  // Vessel proportions: Mesa H/D 1.5, Durham H/D 2.0; Durham drawn ~1.59× linear scale (4× volume).
  const D = isMesa ? 92 : 128;
  const H = isMesa ? D * 1.5 : D * 2.0;
  const W = 300;
  const Hsvg = 330;
  const cx = 130;
  const bottom = 290;
  const top = bottom - H;
  const left = cx - D / 2;
  const right = cx + D / 2;
  const liquid = top + H * 0.18;
  const steel = '#64748b';
  const bag = '#0e7490';
  const imp = (y: number, kind: 'pbt' | 'rushton') =>
    kind === 'pbt' ? (
      <g key={`${kind}-${y}`}>
        <line x1={cx - D * 0.17} y1={y - 5} x2={cx + D * 0.17} y2={y + 5} stroke="#0f172a" strokeWidth={3} />
        <line x1={cx - D * 0.17} y1={y + 5} x2={cx + D * 0.17} y2={y - 5} stroke="#0f172a" strokeWidth={3} opacity={0.35} />
      </g>
    ) : (
      <g key={`${kind}-${y}`}>
        <line x1={cx - D * 0.18} y1={y} x2={cx + D * 0.18} y2={y} stroke="#0f172a" strokeWidth={2} />
        {[-1, -0.5, 0.5, 1].map((k) => (
          <rect key={k} x={cx + k * D * 0.16 - 3} y={y - 6} width={6} height={12} fill="#0f172a" />
        ))}
      </g>
    );

  return (
    <svg viewBox={`0 0 ${W} ${Hsvg}`} className="w-full h-auto" role="img" aria-label={isMesa ? 'Mesa 500 L single-use bioreactor schematic' : 'Durham 2000 L stainless bioreactor schematic'}>
      {/* vessel */}
      {isMesa ? (
        <>
          <rect x={left - 6} y={top - 6} width={D + 12} height={H + 12} rx={6} fill="none" stroke={steel} strokeWidth={1.5} strokeDasharray="4 3" />
          <rect x={left} y={top} width={D} height={H} rx={10} fill="#ecfeff" stroke={bag} strokeWidth={1.5} />
        </>
      ) : (
        <path d={`M${left},${top + 14} Q${cx},${top - 14} ${right},${top + 14} L${right},${bottom - 16} Q${cx},${bottom + 14} ${left},${bottom - 16} Z`} fill="#f1f5f9" stroke={steel} strokeWidth={2} />
      )}
      {/* liquid */}
      <rect x={left + 3} y={liquid} width={D - 6} height={bottom - liquid - (isMesa ? 3 : 10)} fill={isMesa ? bag : '#0284c7'} opacity={0.08} />
      <line x1={left + 3} x2={right - 3} y1={liquid} y2={liquid} stroke={isMesa ? bag : '#0284c7'} strokeDasharray="3 2" strokeWidth={1} />
      {/* shaft and impellers */}
      <line x1={cx} y1={top - 18} x2={cx} y2={bottom - 26} stroke="#0f172a" strokeWidth={2} />
      <rect x={cx - 10} y={top - 30} width={20} height={12} rx={2} fill="#cbd5e1" stroke={steel} />
      {isMesa ? imp(bottom - 40, 'pbt') : [imp(bottom - 44, 'rushton'), imp(bottom - 44 - H * 0.42, 'pbt')]}
      {/* sparger */}
      {isMesa ? (
        <g>
          <line x1={cx - 14} y1={bottom - 14} x2={cx + 14} y2={bottom - 14} stroke="#475569" strokeWidth={2} />
          {[-10, -4, 2, 8].map((dx) => <circle key={dx} cx={cx + dx} cy={bottom - 19} r={1.5} fill="#475569" />)}
        </g>
      ) : (
        <ellipse cx={cx} cy={bottom - 20} rx={D * 0.22} ry={4} fill="none" stroke="#475569" strokeWidth={2} />
      )}
      {/* feed line */}
      <path d={`M${W - 18},${top + 30} L${right + 22},${top + 30} L${right + 22},${top - 10} L${cx + 18},${top - 10} L${cx + 18},${liquid - 6}`} fill="none" stroke="#d97706" strokeWidth={1.8} />
      <circle cx={right + 22} cy={top + 30} r={7} fill="#fff" stroke="#d97706" strokeWidth={1.5} />
      <text x={right + 22} y={top + 33} textAnchor="middle" fontSize={8} fill="#92400e" fontWeight={600}>P</text>
      {isMesa ? (
        <g>
          <rect x={W - 52} y={top + 40} width={34} height={22} rx={2} fill="#fff" stroke="#0e7490" />
          <text x={W - 35} y={top + 54} textAnchor="middle" fontSize={8} fill="#0e7490" fontWeight={600}>WT</text>
          <text x={W - 35} y={top + 74} textAnchor="middle" fontSize={8} fill="#475569">gravimetric</text>
          <text x={W - 35} y={top + 84} textAnchor="middle" fontSize={8} fill="#475569">cascade</text>
        </g>
      ) : (
        <g>
          <circle cx={W - 35} cy={top + 51} r={11} fill="#fff" stroke="#dc2626" strokeDasharray="3 2" />
          <text x={W - 35} y={top + 54} textAnchor="middle" fontSize={8} fill="#dc2626" fontWeight={600}>FIC</text>
          <text x={W - 35} y={top + 74} textAnchor="middle" fontSize={8} fill="#dc2626">flow-only</text>
          <text x={W - 35} y={top + 84} textAnchor="middle" fontSize={8} fill="#dc2626">PID unmapped</text>
        </g>
      )}
      {/* labels */}
      <text x={left - 10} y={top + H / 2} textAnchor="end" fontSize={9} fill="#475569">H/D {isMesa ? '1.5' : '2.0'}</text>
      <text x={cx} y={bottom + 24} textAnchor="middle" fontSize={10} fill="#0f172a" fontWeight={600}>{isMesa ? '500 L working · single-use' : '2000 L working · stainless'}</text>
      <text x={cx} y={bottom + 36} textAnchor="middle" fontSize={8.5} fill="#64748b">{isMesa ? 'PBT 45° · drilled-hole sparger' : 'Rushton + PBT · ring sparger'}</text>
    </svg>
  );
}
