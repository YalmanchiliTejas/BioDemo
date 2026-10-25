'use client';

import { useState } from 'react';
import { BATCH_COLORS } from '@/fixtures/biomanufacturingData';

type Node = { id: string; label: string; sub?: string; x: number; y: number; kind: 'file' | 'batch' | 'skid' | 'assay' };

const FILES = ['Historian_UP01_Oct.csv', 'Batch_events_UP01.parquet', 'LIMS_CMP-26-10_results.xlsx', 'eBR_MES-26071.pdf', 'eBR_MES-26072.pdf', 'eBR_MES-26073.pdf', 'Maximo_WO_export.csv', 'QMS_deviations.xlsx'];
const ASSAYS = [
  { id: 'HPLC-PROA-01', sub: 'Titer' },
  { id: 'VICELL-VCD-02', sub: 'Viable cell density' },
  { id: 'OSMO-03', sub: 'Osmolality' },
  { id: 'CEDEX-GLU-04', sub: 'Glucose / lactate' },
];

const W = 680;
const H = 300;

const nodes: Node[] = [
  ...FILES.map((f, i) => ({ id: f, label: f, x: 92, y: 24 + i * 36, kind: 'file' as const })),
  ...['MES-26071', 'MES-26072', 'MES-26073'].map((b, i) => ({ id: b, label: b, sub: ['Released', 'Released', 'QA hold'][i], x: 340, y: 46 + i * 64, kind: 'batch' as const })),
  { id: 'BR-UP-01', label: 'BR-UP-01', sub: '2,000 L fed-batch skid', x: 340, y: 254, kind: 'skid' },
  ...ASSAYS.map((a, i) => ({ id: a.id, label: a.id, sub: a.sub, x: 580, y: 54 + i * 62, kind: 'assay' as const })),
];

const byId = Object.fromEntries(nodes.map((n) => [n.id, n]));

// Which files contributed to which entities (as indexed at intake).
const EDGES: Array<[string, string]> = [
  ['Historian_UP01_Oct.csv', 'MES-26071'], ['Historian_UP01_Oct.csv', 'MES-26072'], ['Historian_UP01_Oct.csv', 'MES-26073'],
  ['Batch_events_UP01.parquet', 'MES-26071'], ['Batch_events_UP01.parquet', 'MES-26072'], ['Batch_events_UP01.parquet', 'MES-26073'],
  ['LIMS_CMP-26-10_results.xlsx', 'MES-26071'], ['LIMS_CMP-26-10_results.xlsx', 'MES-26072'], ['LIMS_CMP-26-10_results.xlsx', 'MES-26073'],
  ['eBR_MES-26071.pdf', 'MES-26071'], ['eBR_MES-26072.pdf', 'MES-26072'], ['eBR_MES-26073.pdf', 'MES-26073'],
  ['Maximo_WO_export.csv', 'BR-UP-01'], ['QMS_deviations.xlsx', 'MES-26073'],
  ['MES-26071', 'BR-UP-01'], ['MES-26072', 'BR-UP-01'], ['MES-26073', 'BR-UP-01'],
  ...ASSAYS.flatMap((a) => ['MES-26071', 'MES-26072', 'MES-26073'].map((b) => [b, a.id] as [string, string])),
];

export function EntityGraph() {
  const [hover, setHover] = useState<string | null>(null);
  const linked = (id: string) => !hover || hover === id || EDGES.some(([a, b]) => (a === hover && b === id) || (b === hover && a === id));

  return (
    <div className="w-full overflow-x-auto">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full min-w-[560px] h-auto" role="img" aria-label="Indexed entity graph: 8 files linked to 3 batches on skid BR-UP-01 and 4 analytical assays">
        <text x={92} y={10} textAnchor="middle" className="fill-slate-400" fontSize={9} fontWeight={600} letterSpacing={0.6}>8 FILES</text>
        <text x={340} y={10} textAnchor="middle" className="fill-slate-400" fontSize={9} fontWeight={600} letterSpacing={0.6}>3 BATCHES · 1 SKID</text>
        <text x={580} y={10} textAnchor="middle" className="fill-slate-400" fontSize={9} fontWeight={600} letterSpacing={0.6}>4 ASSAYS</text>
        {EDGES.map(([a, b]) => {
          const s = byId[a];
          const t = byId[b];
          const sx = s.kind === 'file' ? s.x + 82 : s.x + 56;
          const tx = t.kind === 'assay' ? t.x - 66 : t.x - 56;
          const vertical = t.kind === 'skid' && s.kind === 'batch';
          const on = hover && (hover === a || hover === b);
          const d = vertical ? `M${s.x},${s.y + 14} L${t.x},${t.y - 14}` : `M${sx},${s.y} C${(sx + tx) / 2},${s.y} ${(sx + tx) / 2},${t.y} ${tx},${t.y}`;
          return <path key={`${a}-${b}`} d={d} fill="none" stroke={on ? '#0e7490' : '#cbd5e1'} strokeWidth={on ? 1.4 : 0.8} opacity={hover && !on ? 0.25 : 1} />;
        })}
        {nodes.map((n) => {
          const op = linked(n.id) ? 1 : 0.35;
          const common = { onMouseEnter: () => setHover(n.id), onMouseLeave: () => setHover(null), onFocus: () => setHover(n.id), onBlur: () => setHover(null), tabIndex: 0, style: { cursor: 'default', outline: 'none' }, opacity: op };
          if (n.kind === 'file') {
            return (
              <g key={n.id} {...common} aria-label={`File ${n.label}`}>
                <rect x={n.x - 82} y={n.y - 11} width={164} height={22} rx={4} fill="#fff" stroke={hover === n.id ? '#0e7490' : '#e2e8f0'} />
                <text x={n.x - 74} y={n.y + 3.5} fontSize={9.5} style={{ fontFamily: "var(--font-mono), monospace" }} fill="#475569">{n.label.length > 26 ? n.label.slice(0, 25) + '…' : n.label}</text>
              </g>
            );
          }
          const color = n.kind === 'batch' ? BATCH_COLORS[n.id] : n.kind === 'skid' ? '#0e7490' : '#64748b';
          const w = n.kind === 'assay' ? 132 : 112;
          return (
            <g key={n.id} {...common} aria-label={`${n.kind} ${n.label}${n.sub ? `, ${n.sub}` : ''}`}>
              <rect x={n.x - w / 2} y={n.y - 16} width={w} height={32} rx={6} fill={n.kind === 'skid' ? '#ecfeff' : '#fff'} stroke={hover === n.id ? '#0e7490' : n.kind === 'skid' ? '#a5f3fc' : '#cbd5e1'} />
              <rect x={n.x - w / 2} y={n.y - 16} width={3} height={32} rx={1.5} fill={color} />
              <text x={n.x - w / 2 + 10} y={n.y - 2} fontSize={10.5} fontWeight={600} style={{ fontFamily: "var(--font-mono), monospace" }} fill="#0f172a">{n.label}</text>
              {n.sub && <text x={n.x - w / 2 + 10} y={n.y + 10} fontSize={9} fill={n.sub === 'QA hold' ? '#dc2626' : '#64748b'}>{n.sub}</text>}
            </g>
          );
        })}
      </svg>
    </div>
  );
}
