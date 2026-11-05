'use client';

import { useEffect, useMemo, useState } from 'react';
import { ArrowDownToLine, ArrowUpRight, Check, Circle, FileText, MessageSquare, RefreshCw, TriangleAlert } from 'lucide-react';
import { Button, Card, Pill } from '@/components/ui';
import { useCompanion } from '@/lib/companion-context';
import { useWorkspace } from '@/lib/workspace-context';
import { processRequest } from '@/lib/process-api';
import { cached, remember } from '@/lib/cache';
import { cn } from '@/lib/cn';
import { exportTable, projectThread, workView, WORK_KINDS, type SavedThread, type WorkKind, type WorkResult, type WorkView } from '@/lib/work-results';

export function WorkResults() {
  const { user, organization } = useWorkspace();
  if (!user || !organization) return <p role="status" className="p-6 text-sm">Loading your workspace access…</p>;
  // Remount on identity/scope changes: account results never survive an organization switch.
  return <Results key={`${user?.id}:${organization?.id}`} />;
}

function Results() {
  // Revisits render the last projection at once; the effect below still rereads every thread.
  const [results, setResults] = useState<WorkResult[]>(() => cached<WorkResult[]>('work-results') ?? []);
  const [loading, setLoading] = useState(() => !cached('work-results')), [error, setError] = useState(''), [attempt, setAttempt] = useState(0);
  const [kind, setKind] = useState<WorkKind>('holds'), [selected, setSelected] = useState(''), [query, setQuery] = useState('');
  const [source, setSource] = useState<{ name: string; line: number } | null>(null);
  const [exported, setExported] = useState(false);
  const companion = useCompanion();
  useEffect(() => {
    let alive = true;
    const hadCache = !!cached('work-results');
    if (!hadCache) { setLoading(true); setResults([]); }
    setError('');
    (async () => {
      try {
        const list = await processRequest<{ conversations: { id: string }[] }>('/v1/process-model/conversations');
        const all: WorkResult[] = [];let failed = 0;
        // Bounded reads of existing account records; no model or workflow requests.
        for (let i = 0; alive && i < list.conversations.length; i += 3) {
          const batch = await Promise.allSettled(list.conversations.slice(i, i + 3).map(c => processRequest<SavedThread>(`/v1/process-model/conversations/${encodeURIComponent(c.id)}`)));
          for (const entry of batch) { if (entry.status === 'fulfilled') all.push(...projectThread(entry.value)); else failed++; }
        }
        if (!alive) return;
        all.sort((a, b) => (b.turn.created_at ?? '').localeCompare(a.turn.created_at ?? ''));
        setResults(all); remember('work-results', all);
        const requested = decodeURIComponent(window.location.hash.slice(1));const picked = all.find(r => r.id === requested) ?? all.find(r => r.kind === 'holds') ?? all[0];
        if (picked && !hadCache) { setKind(picked.kind); setSelected(picked.id); }
        if (failed) setError('Some saved work could not be loaded. Refresh to try again.');
      } catch (e) { if (alive) setError(e instanceof Error ? e.message : 'Saved work could not be loaded.'); }
      finally { if (alive) setLoading(false); }
    })();
    return () => { alive = false; };
  }, [attempt]);
  const choices = useMemo(() => results.filter(r => r.kind === kind), [results, kind]);
  const result = choices.find(r => r.id === selected) ?? choices[0];
  const view = useMemo(() => result ? workView(result) : null, [result]);
  const rows = useMemo(() => view?.rows.filter(r => !query || r.cells.some(c => c.toLowerCase().includes(query.toLowerCase()))) ?? [], [view, query]);
  function pick(id: string) {
    setSelected(id); setSource(null); setQuery(''); setExported(false);
    window.history.replaceState(null, '', `${window.location.pathname}#${encodeURIComponent(id)}`);
  }
  function ask() {
    if (!result || !view) return;
    const scope = source ? view.rows.filter(r => r.source === source.name && r.line === source.line) : view.rows;
    companion.show({ kind: 'chart', label: `${view.title} · ${result.label}`, page_path: '/workspaces/', captured_at: new Date().toISOString(),
      content: JSON.stringify({ classification: result.synthetic ? 'user_supplied_synthetic_unverified' : 'user_supplied_unverified',
        saved_turn_id: result.id, headers: view.headers, displayed_rows: scope.slice(0, 20).map(r => ({ values: r.cells, source_file: r.source, source_line: r.line })),
        omitted_rows: Math.max(0, scope.length - 20), questions: result.turn.questions ?? [], issues: view.issues,
        action_status: 'No manufacturing action or reviewer approval recorded in this saved result' }) });
  }
  function download() {
    if (!view) return;
    const blob = new Blob([exportTable({ ...view, rows })], { type: 'text/csv;charset=utf-8' });const url = URL.createObjectURL(blob);
    const a = document.createElement('a');a.href = url;a.download = 'work-review.csv';a.click();window.setTimeout(() => URL.revokeObjectURL(url), 1000);setExported(true);
  }
  function inspect(name: string, line: number) {
    setSource({ name, line });
    if (window.matchMedia('(max-width: 1279px)').matches) window.requestAnimationFrame(() => document.getElementById('work-source-panel')?.scrollIntoView({ block: 'start', behavior: 'smooth' }));
  }
  return <div className="mx-auto max-w-[1440px] space-y-5" data-testid="work-results">
    <header className="flex flex-wrap items-start justify-between gap-4">
      <div><h1 className="text-3xl font-semibold tracking-tight">Workspaces</h1><p className="mt-2 text-sm text-text-secondary">Everything you've worked through, with the records behind it.</p></div>
      <div className="flex gap-2"><Button variant="subtle" onClick={() => setAttempt(a => a + 1)} disabled={loading} aria-label="Refresh saved work"><RefreshCw size={14} /></Button><Button variant="primary" onClick={() => companion.show()}><MessageSquare size={14} />Ask assistant</Button></div>
    </header>
    <nav aria-label="Work type" className="flex gap-1 overflow-x-auto">
      {WORK_KINDS.map(k => <button key={k.id} type="button" aria-current={kind === k.id ? 'page' : undefined}
        onClick={() => { setKind(k.id); const first = results.find(r => r.kind === k.id);if (first) pick(first.id); }}
        className={cn('flex shrink-0 items-center gap-2 rounded-pill px-4 py-2 text-sm transition-colors', kind === k.id ? 'bg-surface font-medium text-text-primary shadow-[0_1px_3px_rgba(16,24,40,0.08)]' : 'text-text-secondary hover:bg-surface-secondary')}>
        {k.label}{(n => n > 0 && <span className="rounded-pill bg-brand-teal-light px-2 py-0.5 text-[10px] font-medium tabular-nums text-brand-teal">{n}</span>)(results.filter(r => r.kind === k.id).length)}
      </button>)}
    </nav>
    {error && <div role="alert" className="rounded-control border border-amber-200 bg-amber-50 p-3 text-sm">{error}</div>}
    {loading && <p role="status" className="py-10 text-sm text-text-secondary">Loading your saved work…</p>}
    {!loading && (!result || !view) && <div className="py-12"><h2 className="text-base font-semibold">Nothing here yet</h2><p className="mt-2 max-w-lg text-sm leading-6 text-text-secondary">When you work through {WORK_KINDS.find(k => k.id === kind)?.label.toLowerCase() ?? 'a task'} with the assistant, the findings, tables and the source records behind them collect here.</p><Button className="mt-5" onClick={() => companion.show()}><MessageSquare size={14} />Start with the assistant</Button></div>}
    {!loading && result && view && <>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <label className="flex min-w-0 flex-wrap items-center gap-2 text-sm"><span className="text-text-tertiary">Saved review</span><select aria-label="Saved review" value={result.id} onChange={e => pick(e.target.value)} className="max-w-full rounded-control border border-border-strong bg-surface px-3 py-2 text-sm">
          {choices.map(c => <option key={c.id} value={c.id}>{c.label}{c.turn.status === 'blocked' ? ' · Blocked' : c.turn.status === 'needs_information' ? ' · Questions open' : ''}</option>)}
        </select></label>
        <div className="flex flex-wrap gap-2"><Pill tone={result.synthetic ? 'info' : 'neutral'}>{result.synthetic ? 'Synthetic example' : 'User-supplied records'}</Pill><Pill tone="warning">Source review required</Pill></div>
      </div>
      <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_300px]">
        <div className="min-w-0 space-y-4">
          <Card>
            <div className="border-b border-border-hairline px-5 py-4"><h2 className="text-lg font-semibold">{view.title}</h2><p className="mt-1 text-xs leading-5 text-text-secondary">{view.description}</p></div>
            <dl className="grid grid-cols-3 divide-x divide-border-hairline border-b border-border-hairline">{view.metrics.map(m => <div key={m.label} className="min-w-0 px-4 py-3"><dt className="text-[11px] text-text-tertiary">{m.label}</dt><dd className="mt-1 text-xl font-semibold tabular-nums sm:text-2xl">{m.value}</dd><p className="mt-1 text-[10px] text-text-tertiary">{m.note}</p></div>)}</dl>
            <div className="p-4"><ResultChart kind={kind} view={view} result={result} /></div>
          </Card>
          <Card>
            <div className="flex flex-wrap items-center gap-3 border-b border-border-hairline px-4 py-3"><h2 className="mr-auto text-sm font-semibold">{kind === 'scheduling' ? 'Jobs and constraint checks' : kind === 'ingestion' ? 'Reconciliation table' : 'Findings by source record'}</h2><input aria-label="Filter result rows" placeholder="Find a batch or record…" value={query} onChange={e => setQuery(e.target.value)} className="w-48 max-w-full rounded-control border border-border-strong px-2.5 py-1.5 text-xs" /><Button size="sm" onClick={download}><ArrowDownToLine size={13} />Export table</Button></div>
            <div className="overflow-x-auto"><table className="w-full text-left text-xs" data-testid="work-table"><thead className="bg-surface-secondary"><tr>{view.headers.map(h => <th scope="col" className="whitespace-nowrap px-3 py-3 font-medium text-text-tertiary" key={h}>{h}</th>)}<th scope="col" className="px-3 py-3 text-text-tertiary">Evidence</th></tr></thead><tbody>{rows.map((r, i) => <tr key={`${r.id}:${i}`} className={cn('border-t border-border-hairline', (r.flagged || r.computedAttention) && 'bg-amber-50/50', source?.name === r.source && source.line === r.line && 'bg-brand-teal-light')}>
              {r.cells.map((c, j) => <td key={j} className={cn('whitespace-nowrap px-3 py-3 tabular-nums', j === 0 && 'font-medium')}>{c || '—'}</td>)}
              <td className="px-3 py-3"><button type="button" aria-label={`Inspect source row ${r.line} for ${r.cells[0]}`} onClick={() => inspect(r.source, r.line)} className="inline-flex items-center gap-1 whitespace-nowrap font-medium text-brand-teal underline underline-offset-2">Row {r.line}<ArrowUpRight size={12} /></button></td>
            </tr>)}</tbody></table></div>
            {!rows.length && <p className="p-4 text-sm text-text-tertiary">No rows match this filter.</p>}
            <p role="status" className="border-t border-border-hairline px-4 py-2 text-[11px] text-text-tertiary">{exported ? 'Table exported. ' : ''}{rows.length} of {view.rows.length} source rows shown</p>
          </Card>
        </div>
        <aside className="min-w-0 space-y-4" aria-label="Work status and evidence">
          <Card className="p-4"><h2 className="text-sm font-semibold">What has been done</h2><ol className="mt-4 space-y-4">
            <WorkStep label="Source rows provided" status="Recorded" done />
            <WorkStep label="Agent response" status={result.turn.status === 'blocked' ? 'Blocked' : result.answer ? 'Returned' : result.turn.status.replaceAll('_', ' ')} done={!!result.answer} />
            <WorkStep label="Table and comparison checks" status={view.issues.length ? 'Issues found' : 'Calculated here'} done={!view.issues.length} />
            {(result.turn.steps ?? []).map(s => <WorkStep key={s.node_id} label={s.title} status={s.status} done={s.status === 'completed'} />)}
            <WorkStep label="Reviewer decision" status="Not recorded" />
            <WorkStep label="Manufacturing action" status="Not performed" />
          </ol></Card>
          <Card className="scroll-mt-20 p-4" id="work-source-panel"><div className="flex items-center gap-2"><FileText size={15} className="text-brand-teal" /><h2 className="text-sm font-semibold">Source record</h2></div>
            <SourceRecord result={result} selection={source} />
            <Button size="sm" variant="subtle" onClick={ask} className="mt-4 w-full"><MessageSquare size={13} />{source ? 'Ask about this row' : 'Ask about these results'}</Button>
          </Card>
          <Card className="p-4"><h2 className="text-sm font-semibold">Next review</h2><p className="mt-2 text-xs leading-5 text-text-secondary">{kind === 'scheduling' ? 'Confirm timing assumptions and review the proposal before dispatch.' : kind === 'ingestion' ? 'Resolve flagged values and conflicts against their original records.' : 'Check flagged records against the procedure and source evidence.'}</p>
            <div className="mt-3 flex items-center justify-between border-t border-border-hairline pt-3 text-xs"><span className="text-text-tertiary">Owner</span><span>Unassigned</span></div><Pill tone="warning" className="mt-3">Review not approved</Pill>
          </Card>
        </aside>
      </div>
      {(view.issues.length > 0 || (result.turn.questions?.length ?? 0) > 0 || result.turn.status === 'blocked') && <Card className="p-4"><h2 className="flex items-center gap-2 text-sm font-semibold"><TriangleAlert size={15} className="text-amber-600" />Open checks and questions</h2><ul className="mt-3 divide-y divide-border-hairline text-sm leading-6">{[...view.issues, ...(result.turn.questions ?? []), ...(result.turn.status === 'blocked' ? result.turn.issues ?? ['The agent could not return an accepted report.'] : [])].map((q, i) => <li key={i} className="py-2">{q}</li>)}</ul></Card>}
      <details className="rounded-card border border-border-hairline bg-surface p-4 text-xs"><summary className="cursor-pointer font-medium text-text-secondary">Original message, source tables and execution record</summary><div className="mt-4 space-y-5">
        <p className="max-w-4xl whitespace-pre-wrap leading-6">{result.turn.reply ?? 'No accepted assistant reply was saved.'}</p>
        <p className="text-text-secondary">Saved status: {result.turn.status.replaceAll('_', ' ')}{result.turn.elapsed_seconds !== undefined ? ` · ${result.turn.elapsed_seconds.toFixed(1)} s` : ''}{result.turn.gateway_runs?.[0]?.route?.model ? ` · ${result.turn.gateway_runs[0].route.model}` : ''}</p>
        {result.sources.map(s => <details key={s.name}><summary className="cursor-pointer font-medium">{s.name} · {s.rows.length} rows</summary><pre className="mt-2 max-h-72 overflow-auto rounded bg-surface-secondary p-3">{s.raw}</pre></details>)}
        <p className="break-all font-mono text-[10px] text-text-tertiary">Saved turn {result.id} · conversation {result.threadId}</p>
      </div></details>
    </>}
  </div>;
}

function WorkStep({ label, status, done = false }: { label: string; status: string; done?: boolean }) {
  return <li className="flex gap-2.5">{done ? <Check size={15} className="mt-0.5 shrink-0 text-brand-teal" /> : <Circle size={14} className="mt-0.5 shrink-0 text-text-muted" />}<div><p className="text-xs font-medium">{label}</p><p className="mt-0.5 text-[11px] text-text-tertiary">{status}</p></div></li>;
}

function SourceRecord({ result, selection }: { result: WorkResult; selection: { name: string; line: number } | null }) {
  const table = result.sources.find(s => s.name === selection?.name) ?? result.sources[0];
  const row = table?.rows.find(r => r.line === selection?.line) ?? table?.rows[0];
  if (!table || !row) return <p className="mt-3 text-xs text-text-tertiary">No source rows available.</p>;
  return <div className="mt-3" data-testid="work-source" aria-live="polite"><p className="break-all text-xs font-medium text-brand-teal">{table.name} · row {row.line}</p><dl className="mt-3 divide-y divide-border-hairline">{Object.entries(row.values).map(([key, value]) => <div key={key} className="py-2"><dt className="text-[10px] text-text-tertiary">{key}</dt><dd className="mt-0.5 break-words text-xs">{value || 'Missing'}</dd></div>)}</dl></div>;
}

function ResultChart({ kind, view, result }: { kind: WorkKind; view: WorkView; result: WorkResult }) {
  const width = 720, left = 110, right = 660, top = 32, step = 42;
  if (kind === 'ingestion') {
    const proposed = Array.isArray(result.answer?.measurements) ? result.answer.measurements.length : 0;
    const review = Array.isArray(result.answer?.review_record_ids) ? result.answer.review_record_ids.length : 0;
    const max = Math.max(proposed + review, 1);
    return <div className="space-y-4 py-4" aria-label="Record routing chart"><div className="flex min-h-10 overflow-hidden rounded-md" role="img" aria-label={`${proposed} normalization proposals; ${review} record IDs need review`}>
      {proposed > 0 && <div style={{ width: `${proposed / max * 100}%` }} className="flex items-center justify-center bg-brand-teal px-2 text-xs font-medium text-white">{proposed} proposed</div>}
      {review > 0 && <div style={{ width: `${review / max * 100}%` }} className="flex items-center justify-center bg-amber-200 px-2 text-xs font-medium text-amber-900">{review} review</div>}
      {!result.answer && <div className="w-full bg-surface-secondary p-3 text-xs">No normalization answer returned</div>}
    </div><div className="flex flex-wrap gap-4 text-[11px] text-text-secondary"><span>Teal: proposed normalized values</span><span>Amber: agent-routed review records</span></div></div>;
  }
  const scheduling = kind === 'scheduling';
  const values = view.rows.flatMap(r => scheduling ? [r.start, r.end, r.ready, r.due] : [r.value]).filter((v): v is number => v !== undefined);
  const minimum = Math.min(0, ...values, view.lower ?? 0), maximum = Math.max(1, ...values, view.upper ?? 0, view.maintenance?.[1] ?? 0) * 1.08;
  const x = (n: number) => left + (n - minimum) / (maximum - minimum) * (right - left);
  const height = top + step * view.rows.length + 38;
  return <div><div className="overflow-x-auto"><svg viewBox={`0 0 ${width} ${height}`} className="block w-full min-w-[720px] lg:min-w-0" role="img" aria-label={`${view.chartLabel}. ${view.rows.map(r => `${r.cells[0]}: ${scheduling ? r.start === undefined ? 'no proposal' : `${r.start} to ${r.end} hours` : r.cells[kind === 'holds' ? 1 : 2]}`).join('; ')}`}>
    <title>{view.title}</title>
    {scheduling && view.maintenance && <><rect x={x(view.maintenance[0])} y={top - 8} width={x(view.maintenance[1]) - x(view.maintenance[0])} height={step * view.rows.length} fill="#e5e7eb" /><text x={x(view.maintenance[0]) + 3} y={16} fontSize="10" fill="#667085">Maintenance</text></>}
    {!scheduling && view.lower !== undefined && view.upper !== undefined && <rect x={x(view.lower)} y={top - 8} width={x(view.upper) - x(view.lower)} height={step * view.rows.length} fill="#e8f4ef" />}
    {[0, 1, 2, 3, 4].map(i => { const value = minimum + (maximum - minimum) * i / 4;return <g key={i}><line x1={x(value)} x2={x(value)} y1={top - 8} y2={top + step * view.rows.length - 8} stroke="#edf0f3" /><text x={x(value)} y={height - 20} textAnchor="middle" fontSize="10" fill="#667085">{Number(value.toFixed(1))}</text></g>; })}
    {!scheduling && view.upper !== undefined && <><line x1={x(view.upper)} x2={x(view.upper)} y1={top - 8} y2={top + step * view.rows.length - 8} stroke="#b7791f" strokeDasharray="4 3" /><text x={x(view.upper)} y={16} textAnchor="middle" fontSize="10" fill="#99621a">{kind === 'holds' ? 'Maximum' : 'Upper limit'} {view.upper}</text></>}
    {view.rows.map((r, i) => <g key={`${r.id}:${i}`}><text x={left - 12} y={top + step * i + 14} textAnchor="end" fontSize="11" fill="#344054">{r.cells[0]}</text>
      {scheduling ? <>{r.start !== undefined && r.end !== undefined && <rect x={x(r.start)} y={top + step * i} width={Math.max(1, x(r.end) - x(r.start))} height={22} rx={3} fill={r.flagged ? '#c67f21' : '#0e7490'}><title>{r.cells[0]} · proposed {r.start}–{r.end} h</title></rect>}{r.ready !== undefined && <line x1={x(r.ready)} x2={x(r.ready)} y1={top + step * i - 3} y2={top + step * i + 26} stroke="#64748b" strokeDasharray="2 2"><title>Ready at {r.ready} h</title></line>}</> : r.value !== undefined && <><rect x={x(Math.min(0, r.value))} y={top + step * i} width={Math.max(2, Math.abs(x(r.value) - x(0)))} height={22} rx={3} fill={r.computedAttention ? '#d49a36' : '#0e7490'}><title>{r.cells[0]} · {r.value} · {r.computedAttention ? 'outside source limit' : 'within source limit'} · {r.flagged ? 'agent flagged' : 'not agent flagged'}</title></rect><text x={x(r.value) + 6} y={top + step * i + 15} fontSize="11" fill="#344054">{r.value}</text></>}
    </g>)}
    <text x={(left + right) / 2} y={height - 2} textAnchor="middle" fontSize="10" fill="#667085">{view.chartLabel}</text>
  </svg></div><p className="mt-2 text-[11px] text-text-tertiary lg:hidden">Swipe across the chart to inspect its full scale.</p></div>;
}
