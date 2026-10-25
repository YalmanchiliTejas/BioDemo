'use client';

import { EvidenceDrawer } from '@/components/EvidenceDrawer';
import { CITATIONS } from '@/fixtures/biomanufacturingData';
import { useAppContext } from '@/lib/app-context';

/**
 * Pages outside the app shell (onboarding, marketing) have no inspector column.
 * This renders the same evidence drawer as an overlay so EvidenceChips still resolve to their source.
 */
export function StandaloneEvidence() {
  const { isInspectorOpen, activeInspectorEntity, closeInspector } = useAppContext();
  const citation = activeInspectorEntity?.type === 'EVIDENCE' ? CITATIONS[activeInspectorEntity.id] : undefined;
  if (!isInspectorOpen || !citation) return null;
  return <EvidenceDrawer isOpen onClose={closeInspector} citation={citation} />;
}

export function Sparkline({ values, width = 120, height = 36, color = '#dc2626', label }: { values: number[]; width?: number; height?: number; color?: string; label: string }) {
  const min = Math.min(...values);
  const max = Math.max(...values);
  const pad = 4;
  const x = (i: number) => pad + (i * (width - pad * 2)) / Math.max(1, values.length - 1);
  const y = (v: number) => pad + (1 - (v - min) / (max - min || 1)) * (height - pad * 2);
  const d = values.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={label}>
      <path d={d} fill="none" stroke={color} strokeWidth={1.75} strokeLinejoin="round" />
      {values.map((v, i) => <circle key={i} cx={x(i)} cy={y(v)} r={2.5} fill="#fff" stroke={color} strokeWidth={1.5} />)}
    </svg>
  );
}
