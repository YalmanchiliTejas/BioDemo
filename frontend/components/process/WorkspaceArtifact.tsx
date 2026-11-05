'use client';

import { useEffect, useState } from 'react';
import { ChevronRight, FileText, Search } from 'lucide-react';
import { processRequest } from '@/lib/process-api';
import { cached } from '@/lib/cache';
import type { ArtifactRef } from './AnalysisArtifact';

type Ref = { kind: string; id: string; revision: number; time?: string; time_basis?: string; label?: string; classification?: string };
type WorkspaceResult = { status: string; records?: Ref[]; matching_count?: number; truncated?: boolean; ordering?: string; warning?: string; record?: Ref & { data: Record<string, unknown> }; source_refs?: Ref[] };
const cell = 'border-t border-border-hairline py-2 pr-4 align-top';

const shortDate = (iso: string) => { const d = new Date(iso); return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }); };

function searchSummary(data: WorkspaceResult) {
  const counts: Record<string, number> = {};
  for (const r of data.records ?? []) counts[r.kind] = (counts[r.kind] ?? 0) + 1;
  const parts = Object.entries(counts).map(([k, n]) => `${n} ${k === 'engineering_chat_turn' ? 'saved conversation' : k.replaceAll('_', ' ')}`);
  return `Searched · ${data.matching_count ?? 0} found${parts.length ? ` (${parts.join(', ')})` : ''}${data.truncated ? ', partial list' : ''}`;
}

export function WorkspaceArtifact({ threadId, artifact }: { threadId: string; artifact: ArtifactRef }) {
  const [data, setData] = useState<WorkspaceResult | null>(() => cached<WorkspaceResult>(`/v1/process-model/conversations/${threadId}/artifacts/${artifact.kind}/${encodeURIComponent(artifact.id)}`) ?? null);
  const [error, setError] = useState('');
  useEffect(() => {
    let alive = true;
    processRequest<WorkspaceResult>(`/v1/process-model/conversations/${threadId}/artifacts/${artifact.kind}/${encodeURIComponent(artifact.id)}`)
      .then(r => { if (alive) setData(r); }).catch(e => { if (alive) setError(String(e)); });
    return () => { alive = false; };
  }, [threadId, artifact.id, artifact.kind, artifact.status]);
  const stale = ['stale', 'quarantined'].includes(data?.status ?? artifact.status ?? '');
  const timeline = data?.record?.data.timeline;
  // Reads and searches are the assistant's working steps: one quiet line each, full record on demand.
  const rec = data?.record;
  const source = rec ? [rec.data.source_system, rec.data.source_record_id ?? rec.data.case_id ?? rec.id].filter(Boolean).join(' · ') : '';
  const when = rec?.data.event_time ?? rec?.data.opened_at;
  const asked = rec?.kind === 'engineering_chat_turn' ? String(rec.data.user_text ?? '') : '';
  const line = data?.records ? searchSummary(data) : asked ? `Read an earlier conversation: “${asked.length > 60 ? `${asked.slice(0, 60)}…` : asked}”` : rec ? `Read ${source}${when ? ` · ${shortDate(String(when))}` : ''}` : artifact.title;
  return <section className="my-1.5 text-xs" aria-label={artifact.title}>
    {error && <p role="alert" className="text-status-critical">{error}</p>}
    {stale ? <p className="text-status-warning">{artifact.title}: evidence changed or access was withdrawn. Run a fresh investigation.</p>
    : !data && !error ? <p role="status" className="text-text-tertiary">Opening {artifact.title}…</p>
    : data && <details className="group">
      <summary className="flex cursor-pointer list-none items-center gap-2 text-text-tertiary hover:text-text-secondary">{data.records ? <Search size={13} /> : <FileText size={13} />}<span className="truncate">{line}</span><ChevronRight size={12} className="shrink-0 transition-transform group-open:rotate-90" /></summary>
      <div className="mt-2 rounded-card bg-surface p-4 shadow-[0_1px_3px_rgba(16,24,40,0.06)]">
        {data.records && <><div className="overflow-x-auto"><table className="w-full text-left text-xs"><thead><tr><th>Record</th><th>Type</th><th>Source time</th></tr></thead><tbody>{data.records.map(r => <tr key={`${r.kind}:${r.id}`}><td className={cell}>{r.label ?? r.id}<span className="mt-1 block text-text-tertiary">{r.id} · revision {r.revision}{r.classification ? ` · ${r.classification.replaceAll('_', ' ')}` : ''}</span></td><td className={cell}>{r.kind.replaceAll('_', ' ')}</td><td className={cell}>{r.time ?? 'Unknown'}<span className="block text-text-tertiary">{r.time_basis}</span></td></tr>)}</tbody></table>{!data.records.length && <p className="py-3 text-text-tertiary">No accessible matching records.</p>}</div>{data.ordering && <p className="mt-3 text-text-tertiary">{data.ordering}</p>}</>}
        {Array.isArray(timeline) && <div className="overflow-x-auto"><table className="w-full text-left text-xs"><caption className="mb-3 text-left">Recorded case timeline</caption><thead><tr><th>Event time</th><th>Observation / recorded explanation</th></tr></thead><tbody>{timeline.map((event: { time?: string; description?: string }, i) => <tr key={i}><td className={cell}>{event.time ?? 'Unknown'}</td><td className={cell}>{event.description}</td></tr>)}</tbody></table>{!timeline.length && <p className="py-3 text-text-tertiary">No timeline evidence recorded.</p>}</div>}
        {rec && typeof rec.data.original === 'string' && <pre className="max-h-56 overflow-auto whitespace-pre-wrap break-words font-sans text-text-primary">{rec.data.original}</pre>}
        {rec && <dl className="mt-3 grid gap-2 sm:grid-cols-2">{Object.entries(rec.data).filter(([key, value]) => key !== 'original' && (typeof value === 'string' || typeof value === 'number')).map(([key, value]) => <div key={key}><dt className="text-text-tertiary">{key.replaceAll('_', ' ')}</dt><dd className="mt-1 break-words">{String(value)}</dd></div>)}</dl>}
        {!!data.source_refs?.length && <p className="mt-3 text-text-tertiary">Sources: {data.source_refs.map(r => `${r.id} @${r.revision}`).join(' · ')}</p>}
        {data.warning && <p className="mt-2 text-text-tertiary">{data.warning}</p>}
        {!data.records && <details className="mt-3"><summary className="cursor-pointer text-text-secondary">Raw record and provenance</summary><pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap break-words rounded bg-surface-secondary p-3">{JSON.stringify(data.record ?? data, null, 2)}</pre></details>}
      </div>
    </details>}
  </section>;
}
