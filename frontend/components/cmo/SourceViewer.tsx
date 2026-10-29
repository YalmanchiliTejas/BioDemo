'use client';

import { useEffect, useState } from 'react';
import { Check, FileSearch, Loader2, X, ZoomIn, ZoomOut } from 'lucide-react';
import { Button, Callout, Pill } from '@/components/ui';
import { cn } from '@/lib/cn';
import { ACCEPTED, cmoFetch, getJson, postJson, ruleTitle, sourceLabel, type Measurement, type Parameter, type Run } from '@/lib/cmo-api';
import { statusPill } from './shared';

type Cells = { headers: Array<string | null>; values: Array<string | null>; source_sha256: string };

/** Original page or spreadsheet row for one value, with single-value decisions. */
export function SourceViewer({ run, measurement, parameters, reviewer, onChanged, onClose }: {
  run: Run; measurement: Measurement; parameters: Parameter[]; reviewer: string; onChanged: () => void; onClose: () => void;
}) {
  const [cells, setCells] = useState<Cells | null>(null);
  const [page, setPage] = useState<{ url: string; width: number; height: number } | null>(null);
  const [zoom, setZoom] = useState(false);
  const [error, setError] = useState('');
  const [reason, setReason] = useState('');
  const [rejecting, setRejecting] = useState(false);
  const [busy, setBusy] = useState(false);
  const [correcting, setCorrecting] = useState(false);
  const [fix, setFix] = useState({ value: '', unit: '', parameter: '', batch: '', time: '' });
  const pdf = measurement.source.path.toLowerCase().endsWith('.pdf');

  useEffect(() => {
    let url = '';
    setCells(null); setPage(null); setError(''); setCorrecting(false);
    setFix({ value: measurement.value_raw, unit: measurement.unit_declared ?? measurement.unit_raw ?? measurement.unit, parameter: measurement.parameter, batch: measurement.batch, time: measurement.time });
    (async () => {
      try {
        if (pdf) {
          const response = await cmoFetch(`/runs/${run.id}/pages/${measurement.source_id}/${measurement.source.page ?? 1}`);
          url = URL.createObjectURL(await response.blob());
          setPage({ url, width: Number(response.headers.get('X-Page-Width') ?? 1), height: Number(response.headers.get('X-Page-Height') ?? 1) });
        } else {
          setCells(await getJson<Cells>(`/runs/${run.id}/cells/${measurement.id}`));
        }
      } catch (e) { setError((e as Error).message); }
    })();
    return () => { if (url) URL.revokeObjectURL(url); };
  }, [run.id, measurement.id, measurement.source_id, measurement.source.page, pdf, measurement]);

  async function decide(decision: 'accept' | 'reject' | 'correct') {
    setBusy(true); setError('');
    try {
      await postJson(`/runs/${run.id}/reviews`, {
        measurement_id: measurement.id, binding: measurement.review_binding, decision, actor: reviewer, reason,
        ...(decision === 'correct' ? { value: fix.value, unit: fix.unit, parameter: fix.parameter, batch: fix.batch, time: fix.time } : {}),
      });
      setReason(''); setRejecting(false); onChanged();
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  const region = measurement.source.region;
  const pending = measurement.status === 'needs_review';
  return (
    <aside className="flex h-full flex-col" aria-label="Source and verification">
      <div className="flex items-start justify-between gap-2 border-b border-border-hairline px-4 py-3">
        <div className="min-w-0">
          <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-text-tertiary"><FileSearch className="h-3.5 w-3.5" />Original source</p>
          <p className="mt-1 truncate text-[13px] font-medium" title={sourceLabel(measurement.source)}>{sourceLabel(measurement.source)}</p>
          <p className="mt-0.5 text-[11px] text-text-tertiary">Read by {measurement.parser}{measurement.source_verified ? ' · matches original bytes' : ' · not byte-verified'}</p>
        </div>
        <button onClick={onClose} className="rounded p-1 text-text-tertiary hover:bg-surface-secondary" aria-label="Close source"><X className="h-4 w-4" /></button>
      </div>
      <div className="flex-1 space-y-3 overflow-y-auto p-4">
        <div className="rounded-card border border-border-hairline p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-[13px]"><span className="font-semibold">{measurement.parameter}</span> · batch {measurement.batch || '—'} · {measurement.time || '—'} h</p>
            {statusPill(measurement.status)}
          </div>
          <p className="mt-2 text-xl font-semibold tabular-nums">{measurement.value ?? 'not a number'} <span className="text-xs font-normal text-text-tertiary">{measurement.unit}</span></p>
          <p className="text-[11px] text-text-tertiary">Printed as “{measurement.value_raw}”{measurement.unit_raw ? ` ${measurement.unit_raw}` : ' with no unit'}{measurement.unit_declared ? ` · unit declared in mapping: ${measurement.unit_declared}` : ''}</p>
          {measurement.rule_codes.length > 0 && <div className="mt-2 flex flex-wrap gap-1">{measurement.rule_codes.map(code => <Pill key={code} tone="warning">{ruleTitle(code)}</Pill>)}</div>}
        </div>
        {error && <Callout tone="critical">{error}</Callout>}
        {!error && !cells && !page && <p className="flex items-center gap-2 text-xs text-text-tertiary"><Loader2 className="h-3.5 w-3.5 animate-spin" />Loading the original…</p>}
        {cells && (
          <div className="overflow-hidden rounded-card border border-border-hairline">
            <p className="border-b border-border-hairline bg-surface-secondary/60 px-3 py-1.5 text-[11px] text-text-tertiary">Row {measurement.source.row} as stored in the delivered file</p>
            <table className="w-full text-[12px]"><tbody>
              {cells.headers.map((header, i) => (
                <tr key={`${header}-${i}`} className={cn('border-b border-border-hairline last:border-0', header === measurement.source.column && 'bg-amber-50 outline outline-2 -outline-offset-2 outline-amber-400')}>
                  <th className="w-1/2 px-3 py-1.5 text-left font-medium text-text-secondary">{header ?? `(column ${i + 1})`}</th>
                  <td className="px-3 py-1.5 font-mono">{cells.values[i] ?? ''}</td>
                </tr>
              ))}
            </tbody></table>
          </div>
        )}
        {page && (
          <div>
            <div className="mb-1 flex items-center justify-between text-[11px] text-text-tertiary"><span>Page {measurement.source.page ?? 1}{region ? ' · located text outlined' : ' · find the line on this page'}</span>
              <Button size="sm" variant="ghost" onClick={() => setZoom(z => !z)}>{zoom ? <ZoomOut className="h-3.5 w-3.5" /> : <ZoomIn className="h-3.5 w-3.5" />}{zoom ? 'Fit' : 'Zoom'}</Button></div>
            <div className="max-h-[520px] overflow-auto rounded-card border border-border-hairline bg-surface-secondary">
              <div className="relative" style={{ width: zoom ? page.width * 1.5 : '100%' }}>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img alt={`Page ${measurement.source.page ?? 1} of ${measurement.source.path}`} src={page.url} className="h-auto w-full" />
                {region && <div aria-label="Located text" className="pointer-events-none absolute border-2 border-amber-500 bg-amber-200/20" style={{
                  left: `${100 * Math.min(region[0], region[2]) / page.width}%`, top: `${100 * (region[1] > region[3] ? page.height - region[1] : region[1]) / page.height}%`,
                  width: `${100 * Math.abs(region[2] - region[0]) / page.width}%`, height: `${100 * Math.abs(region[3] - region[1]) / page.height}%` }} />}
              </div>
            </div>
            {!measurement.source.page && <Callout tone="warning" className="mt-2">The parser gave no page number. Find the record in the original before accepting.</Callout>}
          </div>
        )}
        {pending ? (
          <div className="space-y-2 rounded-card border border-border-hairline p-3">
            <div className="flex flex-wrap gap-2">
              <Button variant="primary" disabled={!reviewer || busy || measurement.value === null} onClick={() => decide('accept')}><Check className="h-3.5 w-3.5" />Matches source</Button>
              <Button disabled={!reviewer || busy} onClick={() => { setCorrecting(c => !c); setRejecting(false); }}>Correct</Button>
              <Button variant="danger" disabled={!reviewer || busy} onClick={() => { setRejecting(r => !r); setCorrecting(false); }}>Reject</Button>
            </div>
            {(correcting || rejecting) && (
              <input autoFocus aria-label="Reason" placeholder={rejecting ? 'Why reject this value?' : 'What does the source show?'} value={reason} onChange={e => setReason(e.target.value)}
                className="h-8 w-full rounded-control border border-border-strong px-2 text-[13px]" />
            )}
            {rejecting && <Button variant="danger" disabled={!reason.trim() || busy} onClick={() => decide('reject')}>Reject value</Button>}
            {correcting && (
              <div className="grid grid-cols-2 gap-2 pt-1">
                {(['value', 'unit', 'batch', 'time'] as const).map(field => (
                  <label key={field} className="grid gap-1 text-[11px] text-text-tertiary">{field === 'time' ? 'Process time (h or ISO time)' : field[0].toUpperCase() + field.slice(1)}
                    <input className="h-8 rounded-control border border-border-strong px-2 text-[13px] text-text-primary" value={fix[field]} onChange={e => setFix({ ...fix, [field]: e.target.value })} /></label>
                ))}
                <label className="col-span-2 grid gap-1 text-[11px] text-text-tertiary">Parameter
                  <select className="h-8 rounded-control border border-border-strong px-2 text-[13px] text-text-primary" value={fix.parameter} onChange={e => setFix({ ...fix, parameter: e.target.value })}>
                    {parameters.map(p => <option key={p.id} value={p.id}>{p.id} ({p.unit})</option>)}
                  </select></label>
                <Button className="col-span-2" variant="primary" disabled={!reason.trim() || busy} onClick={() => decide('correct')}>Save correction</Button>
              </div>
            )}
            {!reviewer && <p className="text-[11px] text-status-warning">Enter your name at the top right first.</p>}
          </div>
        ) : (
          <p className="text-[12px] text-text-secondary">{ACCEPTED.has(measurement.status) ? (measurement.status === 'auto_accepted'
            ? 'Accepted automatically: confirmed mapping, value matches the original file, and every check passed.' : 'Accepted by a reviewer. See Activity for the receipt.') : 'Rejected by a reviewer. It is excluded from exports.'}</p>
        )}
      </div>
    </aside>
  );
}
