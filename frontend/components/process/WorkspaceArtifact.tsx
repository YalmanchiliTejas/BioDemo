'use client';

import { useEffect, useState } from 'react';
import { processRequest } from '@/lib/process-api';
import type { ArtifactRef } from './AnalysisArtifact';

type Ref = { kind: string; id: string; revision: number; time?: string; time_basis?: string; label?: string; classification?: string };
type WorkspaceResult = { status: string; records?: Ref[]; matching_count?: number; truncated?: boolean; ordering?: string; warning?: string; record?: Ref & { data: Record<string, unknown> }; source_refs?: Ref[] };
const cell = 'border-t border-border-hairline py-2 pr-4 align-top';

export function WorkspaceArtifact({ threadId, artifact }: { threadId: string; artifact: ArtifactRef }) {
  const [data, setData] = useState<WorkspaceResult | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let alive = true;
    processRequest<WorkspaceResult>(`/v1/process-model/conversations/${threadId}/artifacts/${artifact.kind}/${encodeURIComponent(artifact.id)}`)
      .then(r => { if (alive) setData(r); }).catch(e => { if (alive) setError(String(e)); });
    return () => { alive = false; };
  }, [threadId, artifact.id, artifact.kind, artifact.status]);
  const stale = ['stale', 'quarantined'].includes(data?.status ?? artifact.status ?? '');
  const timeline = data?.record?.data.timeline;
  return <section className="my-4 rounded-card border border-border-hairline bg-surface p-4" aria-label={artifact.title}>
    <h3 className="text-sm font-medium">{artifact.title}</h3>
    {error && <p role="alert" className="mt-2 text-xs text-status-critical">{error}</p>}
    {stale ? <p className="mt-2 text-xs text-status-warning">Evidence changed or access was withdrawn. Run a fresh investigation.</p> : <>
      {!data && !error && <p role="status" className="mt-2 text-xs">Loading evidence…</p>}
      {data?.records && <div className="mt-3 overflow-x-auto"><table className="w-full text-left text-xs"><caption className="mb-3 text-left text-text-tertiary">{data.matching_count} permitted matches{data.truncated ? ' · partial list' : ''}</caption><thead><tr><th>Record</th><th>Type</th><th>Source time</th></tr></thead><tbody>{data.records.map(r => <tr key={`${r.kind}:${r.id}`}><td className={cell}>{r.label ?? r.id}<span className="mt-1 block text-text-tertiary">{r.id} · revision {r.revision}{r.classification ? ` · ${r.classification.replaceAll('_', ' ')}` : ''}</span></td><td className={cell}>{r.kind.replaceAll('_', ' ')}</td><td className={cell}>{r.time ?? 'Unknown'}<span className="block text-text-tertiary">{r.time_basis}</span></td></tr>)}</tbody></table>{!data.records.length && <p className="py-3 text-text-tertiary">No accessible matching records.</p>}</div>}
      {Array.isArray(timeline) && <div className="mt-3 overflow-x-auto"><table className="w-full text-left text-xs"><caption className="mb-3 text-left">Recorded case timeline</caption><thead><tr><th>Event time</th><th>Observation / recorded explanation</th></tr></thead><tbody>{timeline.map((event: { time?: string; description?: string }, i) => <tr key={i}><td className={cell}>{event.time ?? 'Unknown'}</td><td className={cell}>{event.description}</td></tr>)}</tbody></table>{!timeline.length && <p className="py-3 text-text-tertiary">No timeline evidence recorded.</p>}</div>}
      {data?.record && <dl className="mt-3 grid gap-2 text-xs sm:grid-cols-2">{Object.entries(data.record.data).filter(([key, value]) => key !== 'original' && (typeof value === 'string' || typeof value === 'number')).map(([key, value]) => <div key={key}><dt className="text-text-tertiary">{key.replaceAll('_', ' ')}</dt><dd className="mt-1 break-words">{String(value)}</dd></div>)}</dl>}
      {!!data?.source_refs?.length && <p className="mt-3 text-xs text-text-tertiary">Sources: {data.source_refs.map(r => `${r.id} @${r.revision}`).join(' · ')}</p>}
      {data?.ordering && <p className="mt-3 text-xs text-text-tertiary">{data.ordering}</p>}
      {data?.warning && <p className="mt-2 text-xs text-text-tertiary">{data.warning}</p>}
      {data && <details className="mt-3 text-xs"><summary className="cursor-pointer text-text-secondary">Inspect source content and provenance</summary><pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap break-words rounded bg-surface-secondary p-3">{JSON.stringify(data.record ?? data, null, 2)}</pre></details>}
    </>}
  </section>;
}
