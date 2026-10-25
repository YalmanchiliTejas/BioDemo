'use client';

import { cn } from '@/lib/cn';

export type GanttBar = {
  id: string;
  row: string;
  start: number;
  end: number;
  label: string;
  kind: 'batch' | 'cip' | 'unavailable' | 'prep' | 'requirement' | 'moved';
  note?: string;
};

const ROW_H = 44;
const LABEL_W = 150;
const W = 1120;
const AXIS_H = 34;

const FILL: Record<GanttBar['kind'], { fill: string; stroke: string; text: string; dash?: string }> = {
  batch: { fill: '#dbeafe', stroke: '#2563eb', text: '#1e3a8a' },
  cip: { fill: 'url(#g-hatch-cip)', stroke: '#0e7490', text: '#155e75' },
  unavailable: { fill: 'url(#g-hatch-gray)', stroke: '#94a3b8', text: '#475569' },
  prep: { fill: '#fef3c7', stroke: '#d97706', text: '#92400e' },
  requirement: { fill: '#f8fafc', stroke: '#64748b', text: '#334155', dash: '4 3' },
  moved: { fill: '#ecfeff', stroke: '#0e7490', text: '#155e75', dash: '5 3' },
};

export function Gantt({
  rows, bars, hours, startLabelDay, conflicts = [], nowHour, onBarClick, preview,
}: {
  rows: Array<{ id: string; label: string; sub?: string }>;
  bars: GanttBar[];
  hours: number;
  startLabelDay: (dayIndex: number) => string;
  conflicts?: Array<{ row: string; start: number; end: number; label: string }>;
  nowHour?: number;
  onBarClick?: (b: GanttBar) => void;
  preview?: string;
}) {
  const H = AXIS_H + rows.length * ROW_H + 8;
  const iw = W - LABEL_W - 12;
  const x = (h: number) => LABEL_W + (h / hours) * iw;
  const rowY = (id: string) => AXIS_H + rows.findIndex((r) => r.id === id) * ROW_H;
  const days = Math.ceil(hours / 24);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto min-w-[880px]" role="img" aria-label="Equipment schedule Gantt chart">
      <defs>
        <pattern id="g-hatch-cip" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <rect width="6" height="6" fill="#ecfeff" />
          <line x1="0" y1="0" x2="0" y2="6" stroke="#67e8f9" strokeWidth="2" />
        </pattern>
        <pattern id="g-hatch-gray" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <rect width="6" height="6" fill="#f8fafc" />
          <line x1="0" y1="0" x2="0" y2="6" stroke="#cbd5e1" strokeWidth="2" />
        </pattern>
        <pattern id="g-hatch-red" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(-45)">
          <rect width="5" height="5" fill="#fee2e2" fillOpacity="0.85" />
          <line x1="0" y1="0" x2="0" y2="5" stroke="#dc2626" strokeWidth="1.6" />
        </pattern>
      </defs>

      {/* rows */}
      {rows.map((r, i) => (
        <g key={r.id}>
          <rect x={0} y={AXIS_H + i * ROW_H} width={W} height={ROW_H} fill={i % 2 ? '#f8fafc' : '#ffffff'} />
          <text x={10} y={AXIS_H + i * ROW_H + 19} fontSize={11.5} fontWeight={600} fill="#0f172a" fontFamily="ui-monospace, monospace">{r.id}</text>
          {r.sub && <text x={10} y={AXIS_H + i * ROW_H + 33} fontSize={9.5} fill="#64748b">{r.sub}</text>}
        </g>
      ))}

      {/* grid */}
      {Array.from({ length: hours / 6 + 1 }, (_, k) => k * 6).map((h) => (
        <line key={h} x1={x(h)} x2={x(h)} y1={AXIS_H - (h % 24 === 0 ? 30 : 6)} y2={H - 8} stroke={h % 24 === 0 ? '#cbd5e1' : '#eef2f7'} strokeWidth={1} />
      ))}
      {Array.from({ length: days }, (_, d) => (
        <g key={d}>
          <text x={x(d * 24) + 6} y={14} fontSize={11} fontWeight={600} fill="#334155">{startLabelDay(d)}</text>
          {[6, 12, 18].map((hh) => (
            <text key={hh} x={x(d * 24 + hh)} y={AXIS_H - 9} fontSize={9} fill="#94a3b8" textAnchor="middle">{String(hh).padStart(2, '0')}</text>
          ))}
        </g>
      ))}
      <line x1={LABEL_W} x2={W - 12} y1={AXIS_H} y2={AXIS_H} stroke="#cbd5e1" />

      {/* bars */}
      {bars.map((b) => {
        const f = FILL[b.kind];
        const y0 = rowY(b.row) + 8;
        const bw = Math.max(2, x(b.end) - x(b.start));
        return (
          <g key={b.id} className={cn(onBarClick && 'cursor-pointer')} onClick={() => onBarClick?.(b)}>
            <title>{`${b.label} · ${b.start.toFixed(1)}–${b.end.toFixed(1)} h${b.note ? ' · ' + b.note : ''}`}</title>
            <rect x={x(b.start)} y={y0} width={bw} height={ROW_H - 16} rx={3} fill={f.fill} stroke={f.stroke} strokeWidth={1.2} strokeDasharray={f.dash} />
            {bw > 50 && (
              <text x={x(b.start) + 6} y={y0 + (ROW_H - 16) / 2 + 3.5} fontSize={10} fill={f.text} fontWeight={500}>
                {b.label.length * 5.6 > bw - 10 ? b.label.slice(0, Math.max(3, Math.floor((bw - 14) / 5.6))) + '…' : b.label}
              </text>
            )}
          </g>
        );
      })}

      {/* conflicts */}
      {conflicts.map((c, i) => {
        const y0 = rowY(c.row) + 3;
        return (
          <g key={i}>
            <title>{c.label}</title>
            <rect x={x(c.start)} y={y0} width={x(c.end) - x(c.start)} height={ROW_H - 6} fill="url(#g-hatch-red)" stroke="#dc2626" strokeWidth={1.5} />
            <text x={(x(c.start) + x(c.end)) / 2} y={y0 - 1} fontSize={9.5} fontWeight={700} fill="#b91c1c" textAnchor="middle">{c.label}</text>
          </g>
        );
      })}

      {nowHour !== undefined && (
        <g>
          <line x1={x(nowHour)} x2={x(nowHour)} y1={AXIS_H - 4} y2={H - 8} stroke="#0f172a" strokeWidth={1.2} />
          <text x={x(nowHour) + 3} y={AXIS_H - 2} fontSize={9} fill="#0f172a" fontWeight={600}>now</text>
        </g>
      )}

      {preview && (
        <g>
          <rect x={W - 290} y={AXIS_H + 4} width={278} height={20} rx={3} fill="#fffbeb" stroke="#d97706" />
          <text x={W - 151} y={AXIS_H + 18} fontSize={10.5} fill="#92400e" textAnchor="middle" fontWeight={600}>{preview}</text>
        </g>
      )}
    </svg>
  );
}
