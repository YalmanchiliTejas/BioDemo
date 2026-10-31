'use client';

import { useCallback, useEffect, useState } from 'react';
import { connectorRequest } from '@/lib/connectors-api';

type SourceRecord = {
  id: string; revision: number; source_record_id: string; source_system: string;
  status: string; review_state: string; rule_codes: string[]; can_accept: boolean;
  fields: Record<string, unknown>; unmapped: Record<string, unknown>;
  measurements: { parameter: string; batch: string; time: string; value: number | null; unit: string | null; source: { path: string; evidence_id: string; evidence_revision: number } }[];
};
type Verification = {
  summary: { source_group: string; records: number; accepted: number; needs_review: number; stale: number };
  items: SourceRecord[];
};

export function SourceVerificationPanel({ connectorId }: { connectorId: string }) {
  const [data, setData] = useState<Verification | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const path = `/connectors/${encodeURIComponent(connectorId)}/verification`;
  const load = useCallback(async () => {
    setBusy(true); setError('');
    try { setData(await connectorRequest<Verification>(path)); }
    catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }, [path]);
  useEffect(() => { void load(); }, [load]);
  const review = async (record: SourceRecord, decision: 'accept' | 'reject') => {
    setBusy(true); setError(''); setNotice('');
    try {
      await connectorRequest(`${path}/review`, { record_id: record.id, expected_revision: record.revision, decision, reason });
      setData(await connectorRequest<Verification>(path)); setReason('');
      setNotice(`Source record ${record.source_record_id} ${decision === 'accept' ? 'accepted' : 'rejected'}.`);
    } catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  };
  const publish = async () => {
    setBusy(true); setError(''); setNotice('');
    try {
      const result = await connectorRequest<{ id: string }>(`${path}/publish`, {});
      setNotice(`Accepted snapshot published: ${result.id}. It is available to authorized consumers; the source collection remains open.`);
    } catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  };
  return <section className="source-verification" aria-label="Source verification" aria-busy={busy}>
    <div className="source-verification-header"><h3>Verify collected data</h3><button className="setup-text-link" disabled={busy} onClick={load}>Refresh</button></div>
    <p className="setup-fine">Files and connected measurements use the same checks. Records with unresolved checks stay out of published snapshots. This live collection does not establish batch completeness.</p>
    {error && <div className="setup-message error" role="alert">{error}</div>}
    {notice && <div className="setup-message" role="status">{notice}</div>}
    {!data && busy && <p role="status">Loading verification…</p>}
    {data && <>
      <p className="setup-fine">{data.summary.source_group} · {data.summary.records} records · {data.summary.accepted} accepted · {data.summary.needs_review} need review · {data.summary.stale} stale</p>
      {data.items.length > 0 && <label className="source-review-reason">Review reason<input value={reason} onChange={e => setReason(e.target.value)} placeholder="What did you check against the source?" /></label>}
      {data.items.map(record => <article className="preview-record" key={record.id}>
        <strong>{record.source_system} / {record.source_record_id}</strong>
        <p className="setup-fine">{record.status === 'current' ? record.review_state.replaceAll('_', ' ') : record.status}{record.rule_codes.length > 0 ? ` · ${record.rule_codes.join(', ')}` : ''}</p>
        {record.measurements.map((m, i) => <div className="source-measurement" key={`${m.parameter}-${i}`}><span>{m.batch || 'Batch missing'} · {m.time} · {m.parameter}</span><strong>{m.value ?? 'Unresolved'} {m.unit}</strong><small>Source evidence: {m.source.evidence_id} · revision {m.source.evidence_revision}</small></div>)}
        <details className="setup-details"><summary>Inspect mapped and retained source fields</summary><pre>{JSON.stringify({ fields: record.fields, unmapped: record.unmapped }, null, 2)}</pre></details>
        <div className="source-review-actions"><button className="setup-secondary" disabled={busy || !reason.trim() || !record.can_accept} onClick={() => review(record, 'accept')}>Accept record</button><button className="setup-secondary" disabled={busy || !reason.trim() || record.status !== 'current'} onClick={() => review(record, 'reject')}>Reject record</button></div>
      </article>)}
      {data.items.length === 0 && <p className="setup-fine">No collected records yet. Run a sync to inspect the data.</p>}
      <button className="setup-primary" disabled={busy || data.summary.accepted === 0 || data.summary.needs_review > 0 || data.summary.stale > 0} onClick={publish}>Publish accepted snapshot</button>
    </>}
  </section>;
}
