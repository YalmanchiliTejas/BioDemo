'use client';

import { useMemo, useState } from 'react';
import { Button, EmptyNote, Segmented, table } from '@/components/ui';
import { cn } from '@/lib/cn';
import { ACCEPTED, sourceLabel, type Measurement, type Run } from '@/lib/cmo-api';
import { statusPill } from './shared';

type Scope = 'verified' | 'pending' | 'all';
const PAGE = 100;

function timeOrder(value: string) {
  const n = Number(value.replace(',', '.'));
  return Number.isFinite(n) ? n : Date.parse(value) / 3.6e6 || 0;
}

/** Aggregated values across every file in the delivery, by batch and parameter. */
export function DataView({ run, onInspect }: { run: Run; onInspect: (m: Measurement) => void }) {
  const all = useMemo(() => (run.measurements ?? []).filter(m => m.status !== 'rejected'), [run.measurements]);
  const batches = useMemo(() => [...new Set(all.map(m => m.batch))].sort(), [all]);
  const parameters = useMemo(() => [...new Set(all.map(m => m.parameter))].sort(), [all]);
  const [scope, setScope] = useState<Scope>('verified');
  const [batch, setBatch] = useState('');
  const [parameter, setParameter] = useState('');
  const [page, setPage] = useState(0);

  const matrix = useMemo(() => {
    const cells = new Map<string, { verified: number; pending: number }>();
    for (const m of all) {
      const key = `${m.batch}|${m.parameter}`; const cell = cells.get(key) ?? { verified: 0, pending: 0 };
      if (ACCEPTED.has(m.status)) cell.verified++; else cell.pending++;
      cells.set(key, cell);
    }
    return cells;
  }, [all]);

  const rows = useMemo(() => all
    .filter(m => scope === 'all' || (scope === 'verified' ? ACCEPTED.has(m.status) : m.status === 'needs_review'))
    .filter(m => (!batch || m.batch === batch) && (!parameter || m.parameter === parameter))
    .sort((a, b) => a.batch.localeCompare(b.batch) || a.parameter.localeCompare(b.parameter) || timeOrder(a.time) - timeOrder(b.time)), [all, scope, batch, parameter]);
  const visible = rows.slice(page * PAGE, page * PAGE + PAGE);

  if (!all.length) return <EmptyNote>No values were extracted from this delivery. See Decisions and Files for what was found.</EmptyNote>;
  return (
    <div className="space-y-4">
      <section className="rounded-2xl border border-border-hairline bg-white">
        <div className="border-b border-border-hairline px-6 py-5">
          <h2 className="font-display text-[20px] font-light text-ink">All values, by batch and parameter</h2>
          <p className="mt-1 text-[13px] text-text-secondary">Counts of verified values. Amber cells still have values waiting; a dash means the delivery has none. Click a cell to filter the table.</p>
        </div>
        <div className="overflow-x-auto px-3 py-2">
          <table className="text-[12px] tabular-nums">
            <thead><tr><th className="sticky left-0 bg-surface px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-wide text-text-tertiary">Batch</th>
              {parameters.map(p => <th key={p} className="px-2 py-2 text-[10.5px] font-medium text-text-tertiary"><span className="block max-w-[84px] truncate" title={p}>{p.replace(/_/g, ' ')}</span></th>)}</tr></thead>
            <tbody>
              {batches.map(b => (
                <tr key={b} className="border-t border-border-hairline">
                  <th className="sticky left-0 bg-surface px-3 py-1.5 text-left font-medium">{b || '(no batch)'}</th>
                  {parameters.map(p => {
                    const cell = matrix.get(`${b}|${p}`);
                    return (
                      <td key={p} className="p-0.5 text-center">
                        <button onClick={() => { setBatch(b); setParameter(p); setScope('all'); setPage(0); }}
                          title={cell ? `${cell.verified} verified, ${cell.pending} awaiting review` : 'No value in this delivery'}
                          className={cn('h-7 w-full min-w-[44px] rounded', !cell ? 'text-text-muted' : cell.pending ? 'bg-amber-100 text-amber-800' : 'bg-emerald-50 text-emerald-800')}>
                          {cell ? (cell.pending ? `${cell.verified}+${cell.pending}` : cell.verified) : '—'}
                        </button>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section className="rounded-2xl border border-border-hairline bg-white">
        <div className="flex flex-wrap items-center gap-2 border-b border-border-hairline px-6 py-4">
          <Segmented<Scope> value={scope} onChange={v => { setScope(v); setPage(0); }} options={[{ value: 'verified', label: 'Verified' }, { value: 'pending', label: 'Awaiting review' }, { value: 'all', label: 'All' }]} />
          <select aria-label="Filter by batch" className="h-7 rounded-control border border-border-strong px-2 text-xs" value={batch} onChange={e => { setBatch(e.target.value); setPage(0); }}>
            <option value="">All batches</option>{batches.map(b => <option key={b} value={b}>{b}</option>)}</select>
          <select aria-label="Filter by parameter" className="h-7 rounded-control border border-border-strong px-2 text-xs" value={parameter} onChange={e => { setParameter(e.target.value); setPage(0); }}>
            <option value="">All parameters</option>{parameters.map(p => <option key={p} value={p}>{p.replace(/_/g, ' ')}</option>)}</select>
          {(batch || parameter) && <Button size="sm" variant="ghost" onClick={() => { setBatch(''); setParameter(''); }}>Clear filters</Button>}
          <span className="ml-auto text-xs text-text-tertiary">{rows.length.toLocaleString()} values</span>
        </div>
        <div className={table.wrap}>
          <table className={table.root} data-testid="values">
            <thead><tr>{['Batch', 'Time (h)', 'Parameter', 'Value', 'As printed', 'Status', 'Source'].map(h => <th key={h} className={table.th}>{h}</th>)}</tr></thead>
            <tbody>
              {visible.map(m => (
                <tr key={m.id} className={cn(table.tr, 'cursor-pointer')} onClick={() => onInspect(m)}>
                  <td className={cn(table.td, 'whitespace-nowrap')}>{m.batch}</td><td className={table.td}>{m.time}</td><td className={cn(table.td, 'whitespace-nowrap')}>{m.parameter.replace(/_/g, ' ')}</td>
                  <td className={cn(table.td, 'whitespace-nowrap text-right')}>{m.value === null ? '—' : Number(m.value.toPrecision(8))} <span className="text-text-tertiary">{m.unit}</span></td>
                  <td className={cn(table.td, 'font-mono text-xs text-text-secondary')}>{m.value_raw}{m.unit_raw ? ` ${m.unit_raw}` : ''}</td>
                  <td className={table.td}>{statusPill(m.status)}</td>
                  <td className={cn(table.td, 'max-w-[260px] truncate text-xs text-brand-teal')} title={sourceLabel(m.source)}>{sourceLabel(m.source)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {rows.length > PAGE && (
          <div className="flex items-center justify-between px-4 py-2 text-xs text-text-tertiary">
            <Button size="sm" disabled={page === 0} onClick={() => setPage(p => p - 1)}>Previous</Button>
            <span>Page {page + 1} of {Math.ceil(rows.length / PAGE)}</span>
            <Button size="sm" disabled={(page + 1) * PAGE >= rows.length} onClick={() => setPage(p => p + 1)}>Next</Button>
          </div>
        )}
      </section>
    </div>
  );
}
