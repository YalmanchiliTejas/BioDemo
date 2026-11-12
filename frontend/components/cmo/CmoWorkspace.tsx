'use client';

import Link from 'next/link';
import { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowLeft, ArrowRight, CheckCircle2, CircleAlert, Download, FileText, Loader2, MessageSquare, RotateCcw, ShieldCheck, Upload, X } from 'lucide-react';
import { WorkspacePageHeader } from '@/components/shell/WorkspacePageHeader';
import { Button, Callout, Pill, table, type Tone } from '@/components/ui';
import { cn } from '@/lib/cn';
import {
  decisionCount, download, getJson, getToken, kindLabel, postJson, setToken, setUploadConfig, uploadFile,
  type Catalog, type CatalogItem, type IntakeEntry, type Measurement, type Parameter, type Run, type RunListing,
} from '@/lib/cmo-api';
import { DEMO_STEPS, demoCmo, isDemoCmo, resetDemo } from '@/lib/cmo-demo';
import { useDemo } from '@/lib/demo-api';
import { setReviewer, useReviewer } from '@/lib/reviewer';
import { authMode } from '@/lib/auth';
import { useOptionalCompanion } from '@/lib/companion-context';
import { processRequest } from '@/lib/process-api';
import { cached } from '@/lib/cache';
import { DataView } from './DataView';
import { DeliveryFiles } from './DeliveryFiles';
import { Links } from './Links';
import { Mappings } from './Mappings';
import { SourceViewer } from './SourceViewer';
import { ToCheck, visibleToCheck } from './ToCheck';
import { plural } from './shared';
import { monthLabel, planDump, type PlannedGroup } from '@/lib/dump-plan';

type Dropped = { file: File; path: string };
// ponytail: browser folder APIs (webkitGetAsEntry / webkitdirectory) are non-standard but supported by Chrome, Edge, Safari and Firefox.
const picked = (list: FileList | null): Dropped[] => Array.from(list ?? []).map(file => ({ file, path: file.webkitRelativePath || file.name }));
async function dropped(transfer: DataTransfer): Promise<Dropped[]> {
  const entries = Array.from(transfer.items ?? []).map(item => item.webkitGetAsEntry?.()).filter((e): e is FileSystemEntry => !!e);
  if (!entries.length) return picked(transfer.files);
  const out: Dropped[] = [];
  async function walk(entry: FileSystemEntry): Promise<void> {
    if (entry.isFile) { out.push({ file: await new Promise<File>((ok, fail) => (entry as FileSystemFileEntry).file(ok, fail)), path: entry.fullPath.replace(/^\//, '') }); return; }
    const reader = (entry as FileSystemDirectoryEntry).createReader();
    for (;;) { // readEntries returns folders in batches
      const batch = await new Promise<FileSystemEntry[]>((ok, fail) => reader.readEntries(ok, fail));
      if (!batch.length) return;
      for (const child of batch) await walk(child);
    }
  }
  for (const entry of entries) await walk(entry);
  return out;
}

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
  const available = new Set((catalog?.packages ?? []).map(p => p.id));
  const load = useCallback(async () => {
    const name = demoCmo();
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
          <p className={eyebrow}>Sample deliveries</p>
          <h2 className="mt-3 font-display text-[24px] font-light tracking-tight text-ink">Three months of deliveries from one CDMO</h2>
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
      <p className="mt-4 text-[12px] leading-relaxed text-text-tertiary">Data: 24 CHO bioreactor runs, Zenodo 20829178 (CC BY 4.0). The CDMO is fictional.</p>
    </section>
  );
}

/** The proposed split, editable: rename a group's CDMO, merge groups, or keep everything together. */
function SplitReview({ plan, onCancel, onConfirm }: { plan: { groups: PlannedGroup[]; files: Dropped[] }; onCancel: () => void; onConfirm: (groups: PlannedGroup[]) => void }) {
  const [groups, setGroups] = useState(plan.groups);
  const relabel = (g: PlannedGroup) => ({ ...g, label: `${g.cmo} · ${monthLabel(g.month)}` });
  const merge = (from: string, into: string) => setGroups(all => all.filter(g => g.key !== from).map(g => g.key === into ? { ...g, paths: [...g.paths, ...all.find(f => f.key === from)!.paths] } : g));
  return <section className="space-y-6">
    <WorkspacePageHeader title="Deliveries" description="" />
    <div className="max-w-3xl">
      <h2 className="font-display text-[26px] font-light tracking-tight text-ink">This looks like {groups.length} separate deliveries</h2>
      <p className="mt-2 text-[13.5px] leading-6 text-text-secondary">Grouped by CDMO and month from the folder and file names. Check the names, merge anything that belongs together, then upload. Nothing has been uploaded yet.</p>
    </div>
    <ul className="space-y-3">{groups.map(g => <li key={g.key} className="flex flex-wrap items-start gap-4 rounded-card bg-surface p-5 shadow-[0_1px_3px_rgba(16,24,40,0.06)]">
      <div className="min-w-0 flex-1">
        <label className="block text-[12px] text-text-tertiary">CDMO
          <input value={g.cmo} aria-label={`CDMO for ${g.label}`} onChange={e => setGroups(all => all.map(o => o.key === g.key ? relabel({ ...o, cmo: e.target.value }) : o))}
            className="mt-1 block h-9 w-full max-w-xs rounded-control border border-border-strong px-3 text-[14px] text-ink" /></label>
        <p className="mt-3 text-[14px] font-medium text-ink">{g.label} <span className="font-normal text-text-tertiary">· {g.paths.length} {g.paths.length === 1 ? 'file' : 'files'}</span></p>
        <p className="mt-1 truncate font-mono text-[12px] text-text-tertiary" title={g.paths.join('\n')}>{g.paths.slice(0, 3).join(' · ')}{g.paths.length > 3 ? ' …' : ''}</p>
      </div>
      {groups.length > 1 && <label className="text-[12px] text-text-tertiary">Merge into
        <select value="" onChange={e => e.target.value && merge(g.key, e.target.value)} className="mt-1 block h-9 rounded-control border border-border-strong bg-white px-2 text-[13px] text-ink">
          <option value="">Keep separate</option>{groups.filter(o => o.key !== g.key).map(o => <option key={o.key} value={o.key}>{o.label}</option>)}
        </select></label>}
    </li>)}</ul>
    <div className="flex flex-wrap gap-3">
      <button type="button" disabled={groups.some(g => !g.cmo.trim())} onClick={() => onConfirm(groups.map(g => ({ ...g, cmo: g.cmo.trim() })))} className="rounded-control bg-brand-teal px-4 py-2.5 text-[13.5px] font-medium text-white disabled:opacity-50">Upload as {groups.length} {groups.length === 1 ? 'delivery' : 'deliveries'}</button>
      <button type="button" onClick={() => onConfirm([{ ...groups[0], label: `${groups[0].cmo} · ${new Date().toLocaleDateString()}`, paths: groups.flatMap(g => g.paths) }])} className="rounded-control px-4 py-2.5 text-[13.5px] text-text-secondary shadow-[0_1px_2px_rgba(16,24,40,0.08)] hover:text-ink">Upload as one delivery</button>
      <button type="button" onClick={onCancel} className="px-2 text-[13.5px] text-text-tertiary hover:text-ink">Cancel</button>
    </div>
  </section>;
}

function Start({ catalog, runs, onError, onCreated }: { catalog: Catalog | null; runs: RunListing[]; onError: (e: string) => void; onCreated: () => void }) {
  const demoWorkspace = !!useDemo().demo;
  const [cmo, setCmo] = useState('');
  const [plan, setPlan] = useState<{ groups: PlannedGroup[]; files: Dropped[] } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const folderInput = useRef<HTMLInputElement>(null);
  useEffect(() => { setCmo(localStorage.getItem(LAST_CMO) ?? ''); }, []);

  async function check(files: Dropped[]) {
    if (!files.length) return;
    if (!cmo.trim()) { onError('Enter the CDMO name first, then add the files.'); return; }
    onError(''); localStorage.setItem(LAST_CMO, cmo.trim());
    const known = (catalog?.cmos ?? []).filter(c => !c.includes('· demo'));
    const groups = planDump(files.map(f => f.path), [...new Set([...known, cmo.trim()])], cmo.trim());
    // More than one CDMO or month: show the proposed split first; nothing is uploaded until confirmed.
    if (groups.length > 1) { setPlan({ groups, files }); return; }
    await upload([{ cmo: cmo.trim(), label: `${cmo.trim()} · ${new Date().toLocaleDateString()}`, files }], true);
  }

  async function upload(deliveries: { cmo: string; label: string; files: Dropped[] }[], open: boolean) {
    setPlan(null);
    const total = deliveries.reduce((n, d) => n + d.files.length, 0);
    let done = 0, last = '';
    const nothing: string[] = [];
    try {
      for (const d of deliveries) {
        const delivery = await postJson<CatalogItem>('/deliveries', { cmo: d.cmo, name: d.label });
        // The server sorts duplicates, clutter and unsupported files within each delivery.
        let next = 0, readable = 0;
        const failed: string[] = [];
        // 4 parallel uploads; the server serialises appends to one delivery (database lock + retry).
        // A failed file is reported by name and the rest carry on, instead of the whole batch stalling.
        await Promise.all(Array.from({ length: Math.min(4, d.files.length) }, async () => {
          while (next < d.files.length) {
            const { file, path } = d.files[next++];
            try { readable = Math.max(readable, (await uploadFile(delivery.id, file, path)).files?.length ?? 0); }
            catch (e) { failed.push(`${path}: ${(e as Error).message}`); }
            setBusy(`Uploaded ${++done} of ${total}${failed.length ? ` · ${failed.length} failed` : ''}`);
          }
        }));
        if (failed.length) onError(`${failed.length} file${failed.length > 1 ? 's' : ''} in ${d.label} did not upload; the others were checked. To include ${failed.length > 1 ? 'them' : 'it'}, drop the folder again (it is checked as a new delivery). ${failed.join(' · ')}`);
        if (readable) last = (await postJson<{ id: string }>('/runs', { package_id: delivery.id })).id; else nothing.push(d.label);
      }
      if (nothing.length) onError(`Nothing to check in ${nothing.join(', ')}: it held only files that are not data. They were kept, not checked.`);
      if (open && last) { go(last); return; }
    } catch (e) { onError((e as Error).message); }
    setBusy(null); onCreated();
  }

  if (plan) return <SplitReview plan={plan} onCancel={() => setPlan(null)}
    onConfirm={(groups) => void upload(groups.map(g => ({ cmo: g.cmo, label: g.label, files: plan.files.filter(f => g.paths.includes(f.path)) })), groups.length === 1)} />;

  // Demo workspaces (this visitor's or anyone else's) stay out of the shared list.
  const mine = runs.filter(r => !r.superseded_by && !isDemoCmo(r.cmo) && !r.cmo.includes('· demo '));
  return (
    <div className="space-y-10">
      <WorkspacePageHeader title="Deliveries" description="Check the files a CDMO sends you. Every extracted value links back to its source." />
      {demoWorkspace && <Callout tone="info" title="Try your own delivery">Upload non-confidential files you are authorized to share, or use a sample below. Demo processing uses local preview extraction without hosted model calls; unsupported formats and ambiguous mappings may need review. Your workspace expires after 24 hours. Conversations and feedback may be retained for product improvement.</Callout>}
      <div className="grid gap-8 lg:grid-cols-[1fr_1fr]">
        <section className="space-y-4">
          <label className="block">
            <span className="text-[12px] font-medium uppercase tracking-wide text-text-tertiary">CDMO</span>
            <input list="cmo-names" value={cmo} onChange={e => setCmo(e.target.value)} placeholder="e.g. Acme Biologics" aria-label="CDMO name"
              className="mt-2 h-11 w-full rounded-[3px] border border-border-strong bg-white px-3 text-[15px] focus:border-brand-teal focus:outline-none" />
            <datalist id="cmo-names">{catalog?.cmos.filter(c => !c.includes('· demo')).map(c => <option key={c} value={c} />)}</datalist>
          </label>
          <button onClick={() => input.current?.click()} disabled={!!busy}
            onDragOver={e => { e.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={e => { e.preventDefault(); setDragging(false); void dropped(e.dataTransfer).then(check); }}
            className={cn('flex h-[260px] w-full flex-col items-center justify-center gap-3 rounded-2xl border border-dashed text-center transition-colors',
              dragging ? 'border-brand-teal bg-brand-teal-light/50' : 'border-border-strong bg-white hover:border-brand-teal')}>
            {busy ? <><Loader2 className="h-6 w-6 animate-spin text-brand-teal" /><span className="text-[14px]">{busy}</span></>
              : <><Upload className="h-6 w-6 text-brand-teal" strokeWidth={1.5} /><span className="font-display text-[20px] font-light text-ink">Drop everything the CDMO sent</span>
                <span className="max-w-sm text-[13px] text-text-tertiary">Files, folders, ZIPs or emails, exactly as received. Attachments are pulled out, and duplicates and nested ZIPs are sorted for you. You’ll see anything that was set aside.</span></>}
          </button>
          <input ref={input} type="file" multiple className="hidden" aria-label="Delivery files" onChange={e => void check(picked(e.target.files))} />
          <input ref={folderInput} type="file" multiple className="hidden" aria-label="Delivery folder" {...{ webkitdirectory: '' }} onChange={e => void check(picked(e.target.files))} />
          <p className="text-center text-[12.5px] text-text-tertiary">or <button type="button" disabled={!!busy} onClick={() => folderInput.current?.click()} className="text-brand-teal hover:underline">choose a whole folder</button></p>
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

const OUTCOME: Record<IntakeEntry['outcome'], string> = {
  added: 'read', renamed: 'read under a new name', duplicate: 'duplicate, not read twice', set_aside: 'set aside, not a data file',
  unreadable: 'could not be opened', system: 'system clutter, skipped', blocked: 'blocked: executables are not stored',
};
/** One line about the upload; the full per-file list is a click away. Nothing intake skipped is hidden. */
function IntakeSummary({ entries }: { entries: IntakeEntry[] }) {
  const read = entries.filter(e => e.outcome === 'added' || e.outcome === 'renamed').length;
  const counts = (['duplicate', 'set_aside', 'unreadable', 'blocked', 'system'] as const).map(o => [o, entries.filter(e => e.outcome === o).length] as const).filter(([, n]) => n);
  const [all, setAll] = useState(false);
  const attention = entries.filter(e => ['renamed', 'unreadable', 'blocked'].includes(e.outcome));
  // Problems first, then what was not read, then what was read.
  const rank: Record<IntakeEntry['outcome'], number> = { renamed: 0, unreadable: 0, blocked: 0, set_aside: 1, duplicate: 2, system: 3, added: 4 };
  const ordered = [...entries].sort((a, b) => rank[a.outcome] - rank[b.outcome]);
  const shown = all ? ordered : ordered.slice(0, 30);
  return <details className="rounded-card bg-surface px-5 py-4 text-[13px] shadow-[0_1px_3px_rgba(16,24,40,0.06)]" open={attention.length > 0}>
    <summary className="cursor-pointer list-none text-text-secondary"><span className="font-medium text-ink">{read} {read === 1 ? 'file' : 'files'} read</span>{counts.map(([o, n]) => ` · ${n} ${({ duplicate: n === 1 ? 'duplicate' : 'duplicates', set_aside: 'set aside', unreadable: 'unreadable', blocked: 'blocked', system: n === 1 ? 'system file' : 'system files' } as const)[o]}`).join('')}{attention.length ? <span className="text-status-warning"> · {attention.length} to look at</span> : null}</summary>
    <ul className="mt-3 space-y-1.5">{shown.map((e, i) => <li key={i} className="flex flex-wrap gap-x-3 text-[12.5px]"><span className="font-mono text-ink">{e.path}</span><span className={e.outcome === 'added' && !e.reason ? 'text-text-tertiary' : 'text-text-secondary'}>{OUTCOME[e.outcome]}{e.reason && !e.reason.includes('is not a data format') ? ` · ${e.reason}` : ''}</span></li>)}</ul>
    {ordered.length > shown.length && <button type="button" onClick={() => setAll(true)} className="mt-3 text-[12.5px] text-brand-teal hover:underline">Show all {ordered.length} files</button>}
  </details>;
}

const NARRATIVE = /\.(txt|log|pdf|docx)$/i;
/** Emails, notes and reports reach the assistant only when a reviewer shares them, labelled as unverified. */
function ShareDocuments({ runId, packageId, entries }: { runId: string; packageId: string; entries: IntakeEntry[] }) {
  const documents = entries.filter(e => (e.outcome === 'added' || e.outcome === 'renamed') && NARRATIVE.test(e.path));
  const [shared, setShared] = useState<string[] | null>(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  useEffect(() => {
    processRequest<{ documents: { path: string }[] }>(`/v1/cmo-documents?package_id=${encodeURIComponent(packageId)}`)
      .then(r => setShared(r.documents.map(d => d.path))).catch(() => setShared([]));
  }, [packageId]);
  if (!documents.length || shared === null) return null;
  const pending = documents.filter(d => !shared.includes(d.path)).length;
  async function share() {
    setBusy(true); setError('');
    try { setShared((await processRequest<{ shared: { path: string }[] }>('/v1/cmo-documents', { run_id: runId })).shared.map(d => d.path)); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  return <div className="flex flex-wrap items-center justify-between gap-3 rounded-card bg-brand-teal-light/50 px-5 py-4 text-[13px]">
    <p className="max-w-2xl text-text-secondary">{pending
      ? <>This delivery has <strong className="text-ink">{documents.length} {documents.length === 1 ? 'document' : 'documents'}</strong> (emails, notes or reports). Share them so the assistant can use them for deviations and investigations. They’ll be marked as unverified CDMO correspondence.</>
      : <><strong className="text-ink">{shared.length} {shared.length === 1 ? 'document' : 'documents'} shared with the assistant</strong>, marked as unverified CDMO correspondence.</>}</p>
    {pending ? <button type="button" disabled={busy} onClick={() => void share()} className="inline-flex items-center gap-2 rounded-control bg-brand-teal px-4 py-2 font-medium text-white disabled:opacity-60">{busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />}Share with assistant</button>
      : <Link href="/home/" className="font-medium text-brand-teal hover:underline">Ask the assistant →</Link>}
    {error && <p role="alert" className="w-full text-status-critical">{error}</p>}
  </div>;
}

function Delivery({ runId }: { runId: string }) {
  const [run, setRun] = useState<Run | null>(() => cached<Run>(`cmo:/runs/${runId}`) ?? null);
  const [error, setError] = useState('');
  const [inspect, setInspect] = useState<Measurement | null>(null);
  const [parameters, setParameters] = useState<Parameter[]>([]);
  const reviewer = useReviewer();

  const load = useCallback(async () => {
    try { const data = await getJson<Run>(`/runs/${runId}`); setRun(data); setError(''); return data; }
    catch (e) { setError((e as Error).message); return null; }
  }, [runId]);
  useEffect(() => { setRun(cached<Run>(`cmo:/runs/${runId}`) ?? null); setInspect(null); void load(); getJson<{ parameters: Parameter[] }>('/vocabulary').then(v => setParameters(v.parameters)).catch(() => {}); }, [load]);
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
      {!!run?.intake?.length && <IntakeSummary entries={run.intake} />}
      {run?.package_id && !checking && <ShareDocuments runId={runId} packageId={run.package_id} entries={run.intake ?? []} />}
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
          <DeliveryFiles run={run} />
          {pendingLayouts.length > 0 && <Mappings run={run} layouts={pendingLayouts} parameters={parameters} reviewer={reviewer} onApplied={go} />}
          <ToCheck run={run} reviewer={reviewer} mappingPending={pendingLayouts.length > 0} onChanged={refresh} onInspect={setInspect} />
          <DataView run={run} onInspect={setInspect} />
          <Links run={run} reviewer={reviewer} />
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
  const [catalog, setCatalog] = useState<Catalog | null>(() => cached<Catalog>('cmo:/catalog') ?? null);
  const [runs, setRuns] = useState<RunListing[]>(() => cached<{ runs: RunListing[] }>('cmo:/runs')?.runs ?? []);
  const [error, setError] = useState('');
  const [needsToken, setNeedsToken] = useState(false);
  const [token, setTokenDraft] = useState('');

  const loadHome = useCallback(async () => {
    try {
      const [c, r] = await Promise.all([getJson<Catalog>('/catalog'), getJson<{ runs: RunListing[] }>('/runs')]);
      setCatalog(c); setUploadConfig(c.upload); setRuns(r.runs); setError(''); setNeedsToken(false);
    } catch (e) { if ((e as { status?: number }).status === 401 && authMode() !== 'supabase') setNeedsToken(true); else setError((e as Error).message); }
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
    <div className="workspace-page pb-16">
      {error && !runId && <Callout tone="critical" className="mb-6" action={<button onClick={() => setError('')}><X className="h-4 w-4" /></button>}>{error}</Callout>}
      {runId ? <Delivery runId={runId} /> : <Start catalog={catalog} runs={runs} onError={setError} onCreated={() => void loadHome()} />}
    </div>
  );
}
