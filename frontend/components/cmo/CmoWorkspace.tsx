'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowLeft, ArrowRight, CheckCircle2, CircleAlert, Download, FileText, Loader2, MessageSquare, RotateCcw, ShieldCheck, Upload, X } from 'lucide-react';
import { Button, Callout, Pill, table, type Tone } from '@/components/ui';
import { cn } from '@/lib/cn';
import {
  decisionCount, download, getJson, getToken, kindLabel, postJson, setToken, uploadFile,
  type Catalog, type CatalogItem, type Measurement, type Parameter, type Run, type RunListing,
} from '@/lib/cmo-api';
import { DEMO_STEPS, demoCmo, isDemoCmo, resetDemo } from '@/lib/cmo-demo';
import { setReviewer, useReviewer } from '@/lib/reviewer';
import { useOptionalCompanion } from '@/lib/companion-context';
import { processRequest } from '@/lib/process-api';
import { DataView } from './DataView';
import { Mappings } from './Mappings';
import { SourceViewer } from './SourceViewer';
import { ToCheck, visibleToCheck } from './ToCheck';
import { plural } from './shared';

const LAST_CMO = 'cmo.last';
const eyebrow = 'text-[12px] font-semibold uppercase tracking-[0.18em] text-brand-teal';

function state(run: Pick<Run, 'status' | 'summary'>): { tone: Tone; label: string } {
  if (run.status === 'queued' || run.status === 'running') return { tone: 'info', label: 'Checking' };
  if (run.status !== 'complete') return { tone: 'critical', label: 'Failed' };
  if (run.summary?.verified_package) return { tone: 'success', label: 'Verified' };
  return { tone: 'warning', label: `${plural(decisionCount(run.summary), 'thing')} to check` };
}

function go(id: string | null) {
  const url = new URL(window.location.href);
  url.searchParams.delete('demo');
  if (id) url.searchParams.set('run', id); else url.searchParams.delete('run');
  window.history.pushState(null, '', url);
  window.dispatchEvent(new PopStateEvent('popstate'));
}

async function startDemoStep(packageId: string) {
  if (!localStorage.getItem('cmo.reviewer')) setReviewer('Demo reviewer');
  go((await postJson<{ id: string }>('/runs', { package_id: packageId, cmo: demoCmo() })).id);
}

/* ---------------------------------------------------------------- Start */

function DemoCard({ catalog, onError }: { catalog: Catalog | null; onError: (e: string) => void }) {
  const [runs, setRuns] = useState<RunListing[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [cmo, setCmo] = useState('');
  const available = new Set((catalog?.packages ?? []).map(p => p.id));
  const load = useCallback(async () => {
    const name = demoCmo(); setCmo(name);
    try { setRuns((await getJson<{ runs: RunListing[] }>(`/runs?cmo=${encodeURIComponent(name)}`)).runs); } catch { setRuns([]); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  if (!DEMO_STEPS.every(s => available.has(s.packageId))) return null;

  const latest = (packageId: string) => runs.find(r => r.package_id === packageId && !r.superseded_by);
  const nextIndex = DEMO_STEPS.findIndex(s => !latest(s.packageId)?.summary?.verified_package);
  return (
    <section className="rounded-2xl border border-border-hairline bg-white p-7" data-testid="demo">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className={eyebrow}>Live demo · real CHO data</p>
          <h2 className="mt-3 font-display text-[24px] font-light tracking-tight text-ink">Three months of deliveries from one CMO</h2>
        </div>
        {runs.length > 0 && <button onClick={() => { resetDemo(); void load(); }} className="flex items-center gap-1 text-[12px] text-text-tertiary hover:text-ink" title="Start again with a fresh workspace"><RotateCcw className="h-3.5 w-3.5" />Restart</button>}
      </div>
      <ol className="mt-6 divide-y divide-border-hairline border-y border-border-hairline">
        {DEMO_STEPS.map((step, i) => {
          const run = latest(step.packageId); const done = run?.summary?.verified_package;
          const next = i === nextIndex;
          return (
            <li key={step.packageId} className="flex items-center justify-between gap-4 py-4">
              <div className="flex min-w-0 gap-4">
                <span className={cn('font-display text-[18px] font-light tabular-nums', done ? 'text-emerald-600' : 'text-brand-teal')}>{done ? <CheckCircle2 className="mt-1 h-5 w-5" /> : `0${i + 1}`}</span>
                <div className="min-w-0"><p className="text-[14.5px] font-medium text-ink">{step.month} · {step.title}</p><p className="text-[13px] text-text-secondary">{step.body}</p></div>
              </div>
              {run ? <button onClick={() => go(run.id)} className="shrink-0 text-[13px] font-medium text-brand-teal hover:underline">{done ? 'View' : 'Continue'}</button>
                : <button disabled={!!busy} onClick={async () => { setBusy(step.packageId); try { await startDemoStep(step.packageId); } catch (e) { onError((e as Error).message); setBusy(null); } }}
                  className={cn('inline-flex h-9 shrink-0 items-center gap-1.5 rounded-[3px] px-3.5 text-[13px] font-medium', next ? 'bg-brand-teal text-white hover:bg-brand-teal-dark' : 'border border-border-strong text-ink hover:bg-canvas')}>
                  {busy === step.packageId ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}Start<ArrowRight className="h-3.5 w-3.5" /></button>}
            </li>
          );
        })}
      </ol>
      <p className="mt-4 text-[12px] leading-relaxed text-text-tertiary">24 real bioreactor runs from Zenodo record 20829178 (CC BY 4.0), repackaged as deliveries from a fictional CMO. Your demo workspace: {cmo}.</p>
    </section>
  );
}

function Start({ catalog, runs, onError }: { catalog: Catalog | null; runs: RunListing[]; onError: (e: string) => void }) {
  const [cmo, setCmo] = useState('');
  const [busy, setBusy] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => { setCmo(localStorage.getItem(LAST_CMO) ?? ''); }, []);

  async function check(list: FileList | null) {
    const files = Array.from(list ?? []).filter(f => !f.name.startsWith('.'));
    if (!files.length) return;
    if (!cmo.trim()) { onError('Enter the CMO name first, then add the files.'); return; }
    onError(''); localStorage.setItem(LAST_CMO, cmo.trim());
    try {
      const delivery = await postJson<CatalogItem>('/deliveries', { cmo: cmo.trim(), name: `${cmo.trim()} · ${new Date().toLocaleDateString()}` });
      for (const [i, file] of files.entries()) { setBusy(`Uploading ${i + 1} of ${files.length}: ${file.name}`); await uploadFile(delivery.id, file); }
      go((await postJson<{ id: string }>('/runs', { package_id: delivery.id })).id);
    } catch (e) { onError((e as Error).message); setBusy(null); }
  }

  // Demo workspaces (this visitor's or anyone else's) stay out of the shared list.
  const mine = runs.filter(r => !r.superseded_by && !isDemoCmo(r.cmo) && !r.cmo.includes('· demo '));
  return (
    <div className="space-y-16">
      <header>
        <p className={eyebrow}>Deliveries</p>
        <h1 className="mt-4 max-w-3xl font-display text-[38px] font-light leading-[1.1] tracking-[-0.025em] text-ink sm:text-[46px]">
          Check a CMO delivery. <span className="text-text-tertiary">Every value links back to its source.</span>
        </h1>
      </header>
      <div className="grid gap-8 lg:grid-cols-[1fr_1fr]">
        <section className="space-y-4">
          <label className="block">
            <span className="text-[12px] font-medium uppercase tracking-wide text-text-tertiary">CMO</span>
            <input list="cmo-names" value={cmo} onChange={e => setCmo(e.target.value)} placeholder="e.g. Acme Biologics" aria-label="CMO name"
              className="mt-2 h-11 w-full rounded-[3px] border border-border-strong bg-white px-3 text-[15px] focus:border-brand-teal focus:outline-none" />
            <datalist id="cmo-names">{catalog?.cmos.filter(c => !c.includes('· demo')).map(c => <option key={c} value={c} />)}</datalist>
          </label>
          <button onClick={() => input.current?.click()} disabled={!!busy}
            onDragOver={e => { e.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={e => { e.preventDefault(); setDragging(false); void check(e.dataTransfer.files); }}
            className={cn('flex h-[260px] w-full flex-col items-center justify-center gap-3 rounded-2xl border border-dashed text-center transition-colors',
              dragging ? 'border-brand-teal bg-brand-teal-light/50' : 'border-border-strong bg-white hover:border-brand-teal')}>
            {busy ? <><Loader2 className="h-6 w-6 animate-spin text-brand-teal" /><span className="text-[14px]">{busy}</span></>
              : <><Upload className="h-6 w-6 text-brand-teal" strokeWidth={1.5} /><span className="font-display text-[20px] font-light text-ink">Drop your CMO files</span>
                <span className="text-[13px] text-text-tertiary">PDF, Excel, CSV or ZIP, as received. Checking starts right away.</span></>}
          </button>
          <input ref={input} type="file" multiple className="hidden" aria-label="Delivery files" accept=".pdf,.csv,.tsv,.xlsx,.xlsm,.zip,.docx,.txt,.json,.png,.jpg,.jpeg,.tif,.tiff" onChange={e => void check(e.target.files)} />
        </section>
        <DemoCard catalog={catalog} onError={onError} />
      </div>
      {mine.length > 0 && (
        <section>
          <h2 className="font-display text-[22px] font-light tracking-tight text-ink">Recent deliveries</h2>
          <ul className="mt-4 divide-y divide-border-hairline border-y border-border-hairline">
            {mine.slice(0, 12).map(r => {
              const s = state(r);
              return (
                <li key={r.id}><button onClick={() => go(r.id)} className="flex w-full items-center justify-between gap-3 py-4 text-left hover:bg-white">
                  <span className="min-w-0"><span className="block truncate text-[14.5px] font-medium text-ink">{r.delivery_name ?? `${r.cmo} · ${r.package_id}`}</span>
                    <span className="text-[12.5px] text-text-tertiary">{r.started_at ? new Date(r.started_at).toLocaleString() : ''} · {plural(r.documents, 'file')}</span></span>
                  <Pill tone={s.tone} dot>{s.label}</Pill>
                </button></li>
              );
            })}
          </ul>
        </section>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------- Delivery */

function Details({ run }: { run: Run }) {
  const g = run.guarantee;
  return (
    <details className="rounded-2xl border border-border-hairline bg-white px-6 py-4 text-[13px]">
      <summary className="cursor-pointer font-display text-[16px] text-ink">Details: files, checks and history</summary>
      <div className="mt-5 space-y-6">
        {g && <div>
          <h3 className="mb-2 font-semibold">Checks on this delivery</h3>
          <ul className="space-y-1.5">{g.checks.map(c => (
            <li key={c.id} className="flex gap-2">{c.passed ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" /> : <CircleAlert className="mt-0.5 h-4 w-4 shrink-0 text-status-critical" />}
              <span>{c.label}<span className="block text-[12px] text-text-tertiary">{c.detail}</span></span></li>))}</ul>
          <p className="mt-2 text-[12px] text-text-tertiary">{g.scope}</p>
        </div>}
        <div className={table.wrap}><table className={table.root}>
          <thead><tr>{['File', 'Read as', 'Values', 'Ignored', 'Listed for you'].map(h => <th key={h} className={table.th}>{h}</th>)}</tr></thead>
          <tbody>{(run.documents ?? []).map(d => { const c = run.coverage?.by_document[d.path]; return (
            <tr key={d.source_id}><td className={table.td} title={`SHA-256 ${d.sha256}`}><FileText className="mr-1 inline h-3.5 w-3.5 text-text-tertiary" />{d.path}</td>
              <td className={table.td}>{kindLabel(d.doc_type)}</td><td className={table.td}>{c?.measurement ?? 0}</td><td className={table.td}>{c?.ignored ?? 0}</td><td className={table.td}>{c?.flagged ?? 0}</td></tr>); })}</tbody>
        </table></div>
        <div>
          <h3 className="mb-2 font-semibold">Decisions</h3>
          {(run.reviews ?? []).length === 0 ? <p className="text-text-tertiary">No individual value decisions on this run.</p> :
            <ul className="max-h-60 space-y-0.5 overflow-y-auto">{[...(run.reviews ?? [])].reverse().slice(0, 200).map((r, i) => (
              <li key={i} className="text-[12px] text-text-secondary">{new Date(r.at).toLocaleString()} · <b>{r.actor}</b> {r.decision}ed {r.before.parameter} {r.before.value_raw} (batch {r.before.batch}) · {r.reason}</li>))}</ul>}
        </div>
        <p className="text-[12px] text-text-tertiary">Processed in {run.runtime_seconds?.toFixed(1)} s · {run.hosted_inference?.basis}{run.carried_over ? ` · ${plural(run.carried_over.reviews, 'earlier decision')} carried forward` : ''}. {run.disclosure} Decisions record your name and time; they are not regulated electronic signatures.</p>
      </div>
    </details>
  );
}

/** Publishes the verified values as platform evidence and opens them in the assistant. */
function AskAssistant({ run, onError }: { run: Run; onError: (message: string) => void }) {
  const companion = useOptionalCompanion();
  const [busy, setBusy] = useState(false);
  if (!companion || !run.summary?.verified_package) return null;
  async function ask() {
    setBusy(true);
    try {
      const d = await processRequest<{ id: string; cmo: string; delivery_name: string | null; measurements: number; batches: string[] }>('/v1/cmo-datasets', { run_id: run.id });
      companion!.attachDataset({ id: d.id, label: d.delivery_name ?? d.cmo, measurements: d.measurements, batches: d.batches.length });
    } catch (e) { onError(`The assistant could not receive this delivery: ${(e as Error).message}`); }
    finally { setBusy(false); }
  }
  return (
    <button onClick={() => void ask()} disabled={busy} title="Send the verified values, with their sources, to the assistant"
      className="inline-flex h-11 items-center gap-2 rounded-[3px] border border-ink px-5 text-[15px] font-medium text-ink hover:bg-ink hover:text-white disabled:opacity-60">
      {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <MessageSquare className="h-4 w-4" />}Ask the assistant</button>
  );
}

function NextDemoStep({ run }: { run: Run }) {
  const [busy, setBusy] = useState(false);
  if (!isDemoCmo(run.cmo) || !run.summary?.verified_package) return null;
  const index = DEMO_STEPS.findIndex(s => s.packageId === run.package_id);
  const next = DEMO_STEPS[index + 1];
  return (
    <section className="flex flex-wrap items-center justify-between gap-4 rounded-2xl bg-ink px-7 py-6 text-white">
      <div>
        <p className="text-[12px] font-semibold uppercase tracking-[0.18em] text-cyan-300">Demo · step {index + 1} of 3 done</p>
        <p className="mt-2 font-display text-[22px] font-light">{next ? `Next: the ${next.month} delivery. ${next.body}` : 'That is the full story. Try it with your own files next.'}</p>
      </div>
      {next ? <button disabled={busy} onClick={async () => { setBusy(true); await startDemoStep(next.packageId).catch(() => setBusy(false)); }}
          className="inline-flex h-11 items-center gap-2 rounded-[3px] bg-white px-5 text-[15px] font-medium text-ink hover:bg-cyan-50">{busy && <Loader2 className="h-4 w-4 animate-spin" />}Open {next.month}<ArrowRight className="h-4 w-4" /></button>
        : <button onClick={() => go(null)} className="inline-flex h-11 items-center gap-2 rounded-[3px] bg-white px-5 text-[15px] font-medium text-ink">Upload files<ArrowRight className="h-4 w-4" /></button>}
    </section>
  );
}

function Delivery({ runId }: { runId: string }) {
  const [run, setRun] = useState<Run | null>(null);
  const [error, setError] = useState('');
  const [inspect, setInspect] = useState<Measurement | null>(null);
  const [parameters, setParameters] = useState<Parameter[]>([]);
  const reviewer = useReviewer();

  const load = useCallback(async () => {
    try { const data = await getJson<Run>(`/runs/${runId}`); setRun(data); setError(''); return data; }
    catch (e) { setError((e as Error).message); return null; }
  }, [runId]);
  useEffect(() => { setRun(null); setInspect(null); void load(); getJson<{ parameters: Parameter[] }>('/vocabulary').then(v => setParameters(v.parameters)).catch(() => {}); }, [load]);
  useEffect(() => {
    if (!run || !['queued', 'running'].includes(run.status)) return;
    const timer = setInterval(() => { void load(); }, 700);
    return () => clearInterval(timer);
  }, [run, load]);
  useEffect(() => { if (run?.superseded_by) go(run.superseded_by); }, [run?.superseded_by]);

  async function refresh() {
    const data = await load();
    if (data && inspect) setInspect(data.measurements?.find(m => m.id === inspect.id) ?? null);
  }
  async function exportFile(format: 'csv' | 'xlsx') {
    try { await download(`/runs/${runId}/export?format=${format}`, `${run?.cmo ?? 'cmo'}-verified-${runId.slice(0, 8)}.${format}`); } catch (e) { setError((e as Error).message); }
  }

  const checking = !run || ['queued', 'running'].includes(run.status);
  const s = run?.summary;
  const pendingLayouts = (run?.layouts ?? []).filter(l => !l.confirmed);
  const verified = !!s?.verified_package;
  const visible = run ? visibleToCheck(run, pendingLayouts.length > 0) : { issues: [], groups: [] };
  const remaining = visible.issues.length + visible.groups.length;

  return (
    <div className="space-y-8">
      <button onClick={() => go(null)} className="flex items-center gap-1 text-[12.5px] text-text-tertiary hover:text-ink"><ArrowLeft className="h-3.5 w-3.5" />Deliveries</button>
      {error && <Callout tone="critical">{error}</Callout>}
      {checking && <div className="flex items-center gap-3 rounded-2xl border border-border-hairline bg-white px-7 py-10"><Loader2 className="h-5 w-5 animate-spin text-brand-teal" />
        <span className="font-display text-[20px] font-light">Checking the delivery… {run?.stages?.length ? <span className="text-text-tertiary">{run.stages[run.stages.length - 1].stage.toLowerCase()}</span> : null}</span></div>}
      {run && ['failed', 'unavailable', 'interrupted'].includes(run.status) &&
        <Callout tone="critical" title="This delivery could not be processed">{run.error ?? run.unavailable_reasons?.join('; ')} Nothing from it was accepted.</Callout>}
      {run?.status === 'complete' && s && (
        <>
          <header className="flex flex-wrap items-end justify-between gap-6">
            <div className="max-w-3xl">
              <p className={eyebrow}>{run.delivery_name ?? run.cmo}</p>
              <h1 className="mt-4 flex items-center gap-3 font-display text-[36px] font-light leading-[1.1] tracking-[-0.025em] text-ink sm:text-[42px]">
                {verified ? <><ShieldCheck className="h-8 w-8 shrink-0 text-emerald-600" strokeWidth={1.5} /><span>Verified. <span className="text-text-tertiary">{plural(s.accepted, 'value')} ready.</span></span></>
                  : pendingLayouts.length ? <span>Confirm how we read {plural(pendingLayouts.length, 'file')}.{remaining ? <span className="text-text-tertiary"> Then {remaining} to check.</span> : null}</span>
                  : <span>{plural(remaining, 'thing')} to check.</span>}
              </h1>
              <p className="mt-3 text-[14.5px] text-text-secondary">
                {plural(s.accepted, 'value')} verified{s.auto_accepted ? ` (${s.auto_accepted.toLocaleString()} automatically)` : ''}{s.needs_review ? ` · ${s.needs_review.toLocaleString()} waiting` : ''}
                {run.coverage ? ` · all ${run.coverage.elements.toLocaleString()} cells and lines accounted for` : ''}
                {run.guarantee && !run.guarantee.holds && <span className="text-status-critical"> · a check failed, see Details</span>}
              </p>
            </div>
            <div className="flex items-center gap-3">
              <button onClick={() => exportFile('xlsx')} className="text-[13px] text-text-tertiary hover:text-ink">Excel</button>
              <AskAssistant run={run} onError={setError} />
              <button onClick={() => exportFile('csv')} title={verified ? undefined : 'Exports verified values only'}
                className={cn('inline-flex h-11 items-center gap-2 rounded-[3px] px-5 text-[15px] font-medium', verified ? 'bg-brand-teal text-white hover:bg-brand-teal-dark' : 'border border-ink text-ink hover:bg-ink hover:text-white')}>
                <Download className="h-4 w-4" />{verified ? 'Export CSV' : 'Export verified so far'}</button>
            </div>
          </header>
          <NextDemoStep run={run} />
          {pendingLayouts.length > 0 && <Mappings run={run} layouts={pendingLayouts} parameters={parameters} reviewer={reviewer} onApplied={go} />}
          <ToCheck run={run} reviewer={reviewer} mappingPending={pendingLayouts.length > 0} onChanged={refresh} onInspect={setInspect} />
          <DataView run={run} onInspect={setInspect} />
          <Details run={run} />
        </>
      )}
      {run && inspect && (
        <div className="fixed inset-y-0 right-0 z-[70] w-full max-w-md border-l border-border-hairline bg-white shadow-2xl">
          <SourceViewer run={run} measurement={inspect} parameters={parameters} reviewer={reviewer} onChanged={refresh} onClose={() => setInspect(null)} />
        </div>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------- Page */

export function CmoWorkspace() {
  const [runId, setRunId] = useState<string | null>(null);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [runs, setRuns] = useState<RunListing[]>([]);
  const [error, setError] = useState('');
  const [needsToken, setNeedsToken] = useState(false);
  const [token, setTokenDraft] = useState('');

  const loadHome = useCallback(async () => {
    try {
      const [c, r] = await Promise.all([getJson<Catalog>('/catalog'), getJson<{ runs: RunListing[] }>('/runs')]);
      setCatalog(c); setRuns(r.runs); setError(''); setNeedsToken(false);
    } catch (e) { if ((e as { status?: number }).status === 401) setNeedsToken(true); else setError((e as Error).message); }
  }, []);

  useEffect(() => {
    setTokenDraft(getToken());
    const sync = () => setRunId(new URLSearchParams(window.location.search).get('run'));
    sync(); window.addEventListener('popstate', sync);
    return () => window.removeEventListener('popstate', sync);
  }, []);
  useEffect(() => { if (!runId) void loadHome(); document.getElementById('main')?.scrollTo({ top: 0 }); }, [runId, loadHome]);

  if (needsToken) {
    return (
      <form className="mx-auto mt-20 max-w-sm space-y-4" onSubmit={e => { e.preventDefault(); setToken(token); void loadHome(); }}>
        <h1 className="font-display text-[30px] font-light tracking-tight">Access code</h1>
        <p className="text-[14px] text-text-secondary">Enter the access code you were given.</p>
        <input type="password" autoFocus value={token} onChange={e => setTokenDraft(e.target.value)} aria-label="Access code" className="h-11 w-full rounded-[3px] border border-border-strong px-3 text-[15px]" />
        <Button type="submit" variant="primary" size="lg">Continue</Button>
      </form>
    );
  }
  return (
    <div className="mx-auto max-w-6xl pb-16">
      {error && !runId && <Callout tone="critical" className="mb-6" action={<button onClick={() => setError('')}><X className="h-4 w-4" /></button>}>{error}</Callout>}
      {runId ? <Delivery runId={runId} /> : <Start catalog={catalog} runs={runs} onError={setError} />}
    </div>
  );
}
