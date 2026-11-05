'use client';

import { useCallback, useEffect, useState } from 'react';
import { Button, Callout, Pill, table, type Tone } from '@/components/ui';
import { getJson, postJson, type Run } from '@/lib/cmo-api';

type Evidence = { source_id: string; evidence_id: string | null; available_at: string | null; delivery?: string };
type Link = { link_id: string; a: string; b: string; a_kind: string | null; b_kind: string | null; predicate: string;
  basis: string; status: 'candidate' | 'extracted' | 'confirmed' | 'rejected'; evidence: Evidence[];
  review?: { actor: string; reason: string; reviewed_at: string } };
type Listing = { links: Link[]; counts: Record<string, number>; sources_searched: number; deliveries?: string[]; deliveries_unavailable?: string[] };

const TONE: Record<Link['status'], Tone> = { candidate: 'warning', extracted: 'info', confirmed: 'success', rejected: 'muted' };

/** Identifiers recorded together across this delivery's files. Guessed links are listed first for review. */
export function Links({ run, reviewer }: { run: Run; reviewer: string }) {
  const [data, setData] = useState<Listing | null>(null);
  const [error, setError] = useState('');
  const [rejecting, setRejecting] = useState<string | null>(null);
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    try { setData(await getJson<Listing>(`/runs/${run.id}/links`)); setError(''); }
    catch (e) { setError((e as Error).message); }
  }, [run.id]);
  useEffect(() => { void load(); }, [load]);

  async function decide(link: Link, decision: 'confirmed' | 'rejected', why = '') {
    setBusy(link.link_id);
    try {
      await postJson(`/runs/${run.id}/links/reviews`, { link_id: link.link_id, decision, actor: reviewer, reason: why });
      setRejecting(null); setReason(''); await load();
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(null); }
  }

  if (error && !data) return <Callout tone="warning" title="Cross-file links unavailable">{error}</Callout>;
  if (!data || data.links.length === 0) return null;
  const toReview = data.counts.candidate ?? 0;
  return (
    <details className="rounded-card border border-border-hairline bg-white" open={toReview > 0}>
      <summary className="cursor-pointer px-4 py-3 text-[14px] font-medium text-ink">
        Cross-file links · {data.links.length} across {data.sources_searched} files{(data.deliveries?.length ?? 0) > 1 ? ` in ${data.deliveries!.length} deliveries` : ''}
        {toReview > 0 && <span className="ml-2"><Pill tone="warning">{toReview} guessed, to check</Pill></span>}
      </summary>
      <p className="px-4 pb-2 text-[12.5px] text-text-secondary">
        A link means two identifiers were recorded together, not why. Guessed links come from file or sheet names;
        rejected links are no longer used by the assistant. Links include this CMO's recent earlier deliveries.
      </p>
      {!!data.deliveries_unavailable?.length && <p className="px-4 pb-2 text-[12px] text-status-warning">Not included (originals unavailable): {data.deliveries_unavailable.join(', ')}</p>}
      {error && <Callout tone="critical" className="mx-4 mb-2">{error}</Callout>}
      <div className={table.wrap}><table className={table.root}>
        <thead><tr>{['Identifiers', 'Basis', 'Status', 'Evidence', ''].map(h => <th key={h} className={table.th}>{h}</th>)}</tr></thead>
        <tbody>{data.links.map(link => (
          <tr key={link.link_id} className={table.tr}>
            <td className={table.td}>{link.a}<span className="text-text-tertiary"> ({link.a_kind ?? '?'})</span> ↔ {link.b}<span className="text-text-tertiary"> ({link.b_kind ?? '?'})</span></td>
            <td className={table.td}>{link.basis}</td>
            <td className={table.td}><Pill tone={TONE[link.status]} title={link.review ? `${link.review.actor}: ${link.review.reason}` : undefined}>{link.status}</Pill></td>
            <td className={table.td}>{link.evidence.length ? <>{link.evidence.length} source{link.evidence.length > 1 ? 's' : ''}{(data.deliveries?.length ?? 0) > 1 && <span className="block text-[11px] text-text-tertiary">{[...new Set(link.evidence.map(e => e.delivery).filter(Boolean))].join(', ')}</span>}</> : '—'}</td>
            <td className={table.td}>
              {rejecting === link.link_id ? (
                <span className="flex items-center gap-2">
                  <input aria-label="Reason for rejecting" className="h-8 w-48 rounded border border-border-hairline px-2 text-[13px]"
                    value={reason} onChange={e => setReason(e.target.value)} placeholder="Why is this wrong?" />
                  <Button size="sm" disabled={!reason.trim() || busy === link.link_id} onClick={() => decide(link, 'rejected', reason)}>Reject</Button>
                  <Button size="sm" variant="ghost" onClick={() => setRejecting(null)}>Cancel</Button>
                </span>
              ) : link.status !== 'confirmed' && link.status !== 'rejected' ? (
                <span className="flex gap-2">
                  <Button size="sm" disabled={busy === link.link_id} onClick={() => decide(link, 'confirmed')}>Confirm</Button>
                  <Button size="sm" variant="ghost" onClick={() => { setRejecting(link.link_id); setReason(''); }}>Reject</Button>
                </span>
              ) : null}
            </td>
          </tr>))}
        </tbody>
      </table></div>
    </details>
  );
}
