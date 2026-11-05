'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { processRequest } from '@/lib/process-api';
import { cached } from '@/lib/cache';
import type { ArtifactRef } from './AnalysisArtifact';

type Row = { result_id: string; batch_id: string | null; value: number | null; lower: number | null; upper: number | null; unit: string; status: string; source: { file: string; row: number }; specification: { file: string; row: number | null; revision: string | null } };
type Data = { status: string; label: string; rows: Row[]; assay_count: number; flagged_count: number; review_count: number; issues: string[]; next_steps: string[]; timing_note?: string; source_turn_id: string; source_saved_at?: string; root_cause: string };
const labels: Record<string, string> = { below_limit: 'Below limit', above_limit: 'Above limit', within_limits: 'Within limits', needs_source_review: 'Needs source review' };
const outside = (r: Row) => ['below_limit', 'above_limit'].includes(r.status);

function AssayChart({ rows }: { rows: Row[] }) {
  const shown = rows.slice(0, 12);
  const values = shown.flatMap(r => [r.value, r.lower, r.upper]).filter((v): v is number => typeof v === 'number');
  const min = Math.min(0, ...values), max = Math.max(1, ...values);
  const x = (n: number) => 160 + (n - min) / Math.max(1, max - min) * 420;
  return <figure className="my-4"><figcaption className="mb-2 text-xs text-text-secondary">Assay values and inclusive specification bands · mg/L{rows.length > 12 ? ' · first 12 results' : ''}</figcaption>
    <svg viewBox={`0 0 640 ${shown.length * 30 + 35}`} className="w-full" role="img" aria-label="Assay values compared with source specification limits. Out-of-specification values are orange; values within limits are teal.">
      {shown.map((r, i) => <g key={`${r.result_id}:${i}`}>
        <text x={0} y={22 + i * 30} fontSize={11} fill="currentColor">{r.result_id.slice(0, 23)}</text>
        <line x1={160} x2={580} y1={18 + i * 30} y2={18 + i * 30} stroke="#dce3e8" />
        {r.lower !== null && r.upper !== null && r.lower <= r.upper && <rect x={x(r.lower)} y={10 + i * 30} width={Math.max(1, x(r.upper) - x(r.lower))} height={16} fill="#d7efeb"><title>Inclusive specification: {r.lower}–{r.upper} mg/L</title></rect>}
        {r.value !== null && <circle cx={x(r.value)} cy={18 + i * 30} r={5} fill={outside(r) ? '#c26a31' : r.status === 'within_limits' ? '#0e7490' : '#718096'}><title>{r.result_id}: {r.value} mg/L · {labels[r.status]}</title></circle>}
        <text x={600} y={22 + i * 30} fontSize={11} fill="currentColor">{r.value ?? '—'}</text>
      </g>)}
      <text x={160} y={shown.length * 30 + 25} fontSize={10} fill="currentColor">{min}</text><text x={580} y={shown.length * 30 + 25} textAnchor="end" fontSize={10} fill="currentColor">{max} mg/L</text>
    </svg>
  </figure>;
}

export function DemoDeviationsArtifact({ threadId, artifact }: { threadId: string; artifact: ArtifactRef }) {
  const [data, setData] = useState<Data | null>(() => cached<Data>(`/v1/process-model/conversations/${threadId}/artifacts/${artifact.kind}/${encodeURIComponent(artifact.id)}`) ?? null);
  const [error, setError] = useState('');
  useEffect(() => {
    let alive = true;
    setData(null); setError('');
    processRequest<Data>(`/v1/process-model/conversations/${threadId}/artifacts/${artifact.kind}/${encodeURIComponent(artifact.id)}`)
      .then(r => { if (alive) setData(r); }).catch(e => { if (alive) setError(String(e)); });
    return () => { alive = false; };
  }, [threadId, artifact.id, artifact.kind, artifact.status]);
  const stale = ['stale', 'quarantined'].includes(data?.status ?? artifact.status ?? '');
  return <section className="my-4 overflow-hidden rounded-card border border-border-hairline bg-surface" aria-label="Deviation review">
    <header className="flex flex-wrap justify-between gap-2 border-b border-border-hairline p-4"><h3 className="text-sm font-medium">Deviation review</h3><span className="text-xs text-text-tertiary">{data?.label} · Sample data</span></header>
    <div className="p-4">
      {error && <p role="alert" className="text-sm text-status-critical">{error}</p>}
      {stale ? <p className="text-sm text-status-warning">The source changed or access was withdrawn. Ask again to refresh this review.</p> : data ? <>
        <dl className="grid grid-cols-3 gap-3">{[['Assays', data.assay_count], ['Outside limits', data.flagged_count], ['Cannot compare', data.review_count]].map(([label, count]) => <div key={String(label)}><dt className="text-xs text-text-tertiary">{label}</dt><dd className="mt-1 text-2xl font-medium">{count}</dd></div>)}</dl>
        {!!data.rows.length && <AssayChart rows={data.rows} />}
        <div className="overflow-x-auto"><table className="w-full text-left text-xs"><caption className="sr-only">Source assay findings</caption><thead><tr>{['Assay / batch', 'Result', 'Inclusive limits', 'Finding', 'Source'].map(h => <th key={h} className="pb-2 pr-3 font-medium">{h}</th>)}</tr></thead><tbody>{data.rows.slice(0, 100).map((r, i) => <tr key={`${r.result_id}:${i}`} className="border-t border-border-hairline"><th className="py-3 pr-3 font-normal">{r.result_id}<span className="block text-text-tertiary">{r.batch_id}</span></th><td className="pr-3">{r.value ?? '—'} {r.unit}</td><td className="pr-3">{r.lower ?? '?'}–{r.upper ?? '?'} {r.unit}</td><td className={`pr-3 ${outside(r) ? 'text-status-warning' : ''}`}>{labels[r.status] ?? r.status}</td><td>{r.source.file}:{r.source.row}<span className="block text-text-tertiary">{r.specification.file}:{r.specification.row ?? '?'} · {r.specification.revision ?? 'Unresolved'}</span></td></tr>)}</tbody></table></div>
        {data.rows.length > 100 && <p className="mt-2 text-xs text-text-tertiary">Showing 100 of {data.rows.length} rows. Full results remain in the saved review.</p>}
        {!!data.issues.length && <ul className="mt-3 space-y-1 text-xs text-status-warning">{data.issues.map(issue => <li key={issue}>{issue}</li>)}</ul>}
        <h4 className="mt-5 text-sm font-medium">Next review steps</h4><ol className="mt-2 list-decimal space-y-2 pl-5 text-sm text-text-secondary">{data.next_steps.map(s => <li key={s}>{s}</li>)}</ol>
        <p className="mt-4 text-xs text-text-tertiary">Cause: {data.root_cause} No manufacturing action has been performed.</p>
        <details className="mt-3 text-xs text-text-secondary"><summary className="cursor-pointer">Source details</summary><p className="mt-2">{data.timing_note}</p><p className="mt-2">Review saved: {data.source_saved_at ?? 'Unknown'}</p><Link className="mt-2 inline-block underline underline-offset-2" href={`/workspaces/#${encodeURIComponent(data.source_turn_id)}`}>Open the original saved review</Link></details>
      </> : !error && <p className="text-xs" role="status">Loading findings…</p>}
    </div>
  </section>;
}
