'use client';
import { useEffect, useState } from 'react';
import { processRequest } from '@/lib/process-api';
import type { Original } from '@/lib/quality-workflow-api';

export function SourceInspector({ path, onClose }: { path: string; onClose: () => void }) {
  const [source, setSource] = useState<Original | null>(null), [error, setError] = useState('');
  useEffect(() => { const close = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose(); }; window.addEventListener('keydown', close); return () => window.removeEventListener('keydown', close); }, [onClose]);
  useEffect(() => { let active = true; processRequest<Original>(path).then(s => { if (active) setSource(s); }).catch(e => { if (active) setError(e.message); }); return () => { active = false; }; }, [path]);
  function download() {
    if (!source) return;
    const original = source.original_base64 ?? source.content_base64;
    if (!original) return;
    const bytes = Uint8Array.from(atob(original), c => c.charCodeAt(0));
    const url = URL.createObjectURL(new Blob([bytes], {type: source.state.media_type ?? 'application/octet-stream'}));
    const a = document.createElement('a'); a.href = url; a.download = `${source.ref.id.replaceAll('/', '_')}-r${source.ref.revision}`; a.click(); URL.revokeObjectURL(url);
  }
  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4" role="dialog" aria-modal="true" aria-label="Pinned source original">
    <section className="max-h-[90vh] w-full max-w-3xl overflow-auto rounded-card bg-surface p-5 shadow-lg">
      <div className="flex items-center justify-between"><h2 className="font-medium">Pinned source original</h2><button onClick={onClose} className="underline">Close source</button></div>
      {error && <p role="alert">Source unavailable: {error}</p>}
      {!source && !error && <p role="status">Retrieving authorized original…</p>}
      {source && <><p className="mt-3 text-sm">{source.ref.kind} · {source.ref.id} · revision {source.ref.revision}</p>
        <p className="mt-1 text-xs text-text-tertiary">{source.state.source_system} · {source.state.source_record_id} · {source.state.media_type} · source time {source.state.event_time ?? 'unknown'}</p>
        {source.snapshot_sha256 && <p className="mt-2 break-all text-xs">Snapshot sha256 {source.snapshot_sha256}</p>}
        {source.source_coordinate != null && <p className="text-xs">Source coordinate: {JSON.stringify(source.source_coordinate)}</p>}
        <div data-testid="source-original" className="mt-4"><pre className="max-h-[50vh] overflow-auto whitespace-pre-wrap break-words rounded border border-border-hairline p-3 text-xs">{source.content_text ?? (source.content_base64 ? 'Binary original available for download.' : JSON.stringify(source.state, null, 2))}</pre></div>
        {source.content_text && <p className="mt-2 text-xs text-text-tertiary">Escaped text preview; unsupported text encodings may display replacement characters.</p>}
        {(source.original_base64 || source.content_base64) && <button className="mt-3 underline" onClick={download}>Download original revision {source.ref.revision}</button>}
        <details className="mt-3 text-xs"><summary>Stored source metadata</summary><pre className="overflow-auto whitespace-pre-wrap">{JSON.stringify(source.state, null, 2)}</pre></details>
      </>}
    </section>
  </div>;
}

/** Real run citations never enter the fixture-only demo inspector. */
export function RunCitation({ runId, citationId }: { runId: string; citationId: string }) {
  const [open, setOpen] = useState(false);
  return <><button className="rounded border border-border-hairline px-2 py-1 text-xs underline" onClick={() => setOpen(true)}>Source {citationId}</button>{open && <SourceInspector path={`/v1/investigation-runs/${encodeURIComponent(runId)}/citations/${encodeURIComponent(citationId)}`} onClose={() => setOpen(false)} />}</>;
}
