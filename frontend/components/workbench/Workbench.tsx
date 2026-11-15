'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { ChevronDown, Pencil, Plus } from 'lucide-react';
import { WorkspacePageHeader } from '@/components/shell/WorkspacePageHeader';
import { useOptionalCompanion } from '@/lib/companion-context';
import { ProcessApiError } from '@/lib/process-api';
import { useWorkspace } from '@/lib/workspace-context';
import { addPlanStep, count, createPlan, deliveryProfile, getPlan, listDeliveries, listPlans, planTitle, previewPicture, sameName, savePicture, selectionFor, updatePlan, updatePlanStep,
  type Dataset, type NewStep, type Picture as PictureData, type Plan, type PlanStep, type PlanSummary, type SavedIds, type Selection } from '@/lib/workbench';
import { DataInView, scopeOf, type Profiles } from './DataInView';
import { Findings, type Work } from './Findings';
import { NextSteps } from './NextSteps';
import { Picture } from './Picture';

const remembered = (siteId: string) => `workbench.plan:${siteId}`;
const recall = (siteId: string) => { try { return localStorage.getItem(remembered(siteId)); } catch { return null; } };
const remember = (siteId: string, id?: string | null) => { try { if (id) localStorage.setItem(remembered(siteId), id); else localStorage.removeItem(remembered(siteId)); } catch { /* A convenience only. */ } };
const listOf = (text: string | null) => [...new Set((text ?? '').split(',').map(item => item.trim()).filter(Boolean))];

/** The first picture needs no input: the newest verified delivery, its first parameter, every batch.
 *  A link from another page (Trends, for one) may name the parameter, deliveries and batches instead. */
function firstSelection(siteId: string, datasets: Dataset[], query: URLSearchParams): { selection: Selection; notice: string } {
  const asked = listOf(query.get('datasets')), wanted = query.get('parameter')?.trim() ?? '';
  const found = [...new Set(asked.map(id => datasets.find(d => d.id === id || d.run_id === id)?.id).filter((id): id is string => !!id))].slice(0, 10);
  const notes: string[] = [];
  if (asked.length > found.length) notes.push(`${count(asked.length - found.length, 'delivery', 'deliveries')} named in the link ${asked.length - found.length === 1 ? 'is' : 'are'} not available here yet. A delivery is listed once its review has started under Deliveries.`);
  let ids = found;
  if (!ids.length) {
    const newest = [...datasets].sort((a, b) => (b.published_at ?? '').localeCompare(a.published_at ?? ''));
    const first = newest.find(d => d.verification !== 'provisional') ?? newest[0];
    ids = first ? [first.id] : [];
  }
  const chosen = ids.map(id => datasets.find(d => d.id === id)!);
  const used = chosen.some(d => d.verification !== 'provisional') ? chosen.filter(d => d.verification !== 'provisional') : chosen;
  const parameters = [...new Set(used.flatMap(d => d.parameters ?? []))], batches = new Set(chosen.flatMap(d => d.batches ?? []));
  const parameter = (wanted && parameters.find(name => sameName(name, wanted))) || parameters[0] || wanted || null;
  if (wanted && parameter && !sameName(parameter, wanted)) notes.push(`${wanted} is not recorded in ${chosen.length === 1 ? 'this delivery' : 'these deliveries'}; ${parameter} is shown.`);
  return { selection: selectionFor(siteId, { dataset_ids: ids, parameter, batches: listOf(query.get('batches')).filter(batch => !batches.size || batches.has(batch)).slice(0, 30) }), notice: notes.join(' ') };
}

export function Workbench() {
  const workspace = useWorkspace();
  const siteId = workspace.organization?.site_ids?.[0] ?? 'NF1';
  if (workspace.loadingAccount) return <div className="workspace-page"><p role="status" className="py-10 text-center text-sm text-text-secondary">Opening the workbench…</p></div>;
  return <Surface key={siteId} siteId={siteId} />;
}

function Surface({ siteId }: { siteId: string }) {
  const companion = useOptionalCompanion();
  const [datasets, setDatasets] = useState<Dataset[] | null>(null), [loadError, setLoadError] = useState(''), [attempt, setAttempt] = useState(0);
  const [selection, setSelection] = useState<Selection | null>(null), [profiles, setProfiles] = useState<Profiles>({});
  const [plan, setPlan] = useState<Plan | null>(null), [plans, setPlans] = useState<PlanSummary[] | null>(null);
  const [picture, setPicture] = useState<PictureData | null>(null), [pictureError, setPictureError] = useState(''), [busy, setBusy] = useState(false), [retry, setRetry] = useState(0);
  const [notice, setNotice] = useState(''), [dataNotice, setDataNotice] = useState('');
  const selectionKey = selection ? JSON.stringify(selection) : '';
  const now = useRef({ selection, key: selectionKey }); now.current = { selection, key: selectionKey };
  const planNow = useRef<Plan | null>(null), synced = useRef(''), saved = useRef<{ key: string; ids: Promise<SavedIds> } | null>(null);
  const queue = useRef<Promise<unknown>>(Promise.resolve()), profiled = useRef(new Set<string>()), previews = useRef(0), drawn = useRef(false);

  /** `adopt` puts the plan's saved selection back in view: on opening it, and when it changed somewhere else. */
  function applyPlan(next: Plan | null, adopt = false) {
    planNow.current = next; setPlan(next); remember(siteId, next?.id);
    if (next && adopt) { const restored = selectionFor(siteId, next.selection); synced.current = JSON.stringify(restored); setSelection(restored); }
  }
  const refreshPlans = () => { listPlans(siteId).then(found => setPlans(found.plans)).catch(() => setPlans(current => current ?? [])); };

  useEffect(() => {
    let alive = true; setLoadError('');
    const query = new URLSearchParams(window.location.search);
    refreshPlans();
    (async () => {
      try {
        const listed = (await listDeliveries(siteId)).datasets.filter(d => !d.status || d.status === 'current');
        // Return to the work last open here, unless a link names what to look at.
        const wanted = query.get('plan') ?? (['parameter', 'datasets', 'batches'].some(name => query.get(name)) ? null : recall(siteId));
        let opened: Plan | null = null;
        if (wanted) try { opened = await getPlan(wanted); } catch { remember(siteId, null); }
        if (!alive) return;
        setDatasets(listed);
        if (opened) applyPlan(opened, true);
        else { const first = firstSelection(siteId, listed, query); setSelection(first.selection); setDataNotice(first.notice); }
      } catch (e) { if (alive) setLoadError((e as Error).message); }
    })();
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteId, attempt]);

  // What each selected delivery holds: prepared once per delivery revision on the server, read once here.
  const selectedIds = selection?.dataset_ids.join('\n') ?? '';
  useEffect(() => {
    for (const id of selection?.dataset_ids ?? []) {
      if (profiled.current.has(id) || !datasets?.some(d => d.id === id)) continue;
      profiled.current.add(id);
      deliveryProfile(id, siteId).then(profile => setProfiles(current => ({ ...current, [id]: profile }))).catch(e => setProfiles(current => ({ ...current, [id]: { error: (e as Error).message } })));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedIds, datasets, siteId]);

  const scope = useMemo(() => scopeOf(datasets ?? [], profiles, selection), [datasets, profiles, selection]);
  // A delivery whose listing names no parameters gets its first one from the profile.
  useEffect(() => { if (selection && !selection.parameter && scope.known && scope.parameters.length) setSelection({ ...selection, parameter: scope.parameters[0].name }); }, [selection, scope]);

  // The picture follows the selection. Nothing is saved by looking.
  const ready = !!selection && selection.dataset_ids.length > 0 && !!selection.parameter;
  const backwards = !!selection && selection.time_from_h != null && selection.time_to_h != null && selection.time_from_h > selection.time_to_h;
  useEffect(() => {
    if (!ready) { previews.current++; drawn.current = false; setPicture(null); setPictureError(''); setBusy(false); return; }
    if (backwards) return;
    const mine = ++previews.current, wanted = now.current.selection!;
    setBusy(true);
    const timer = setTimeout(() => {
      previewPicture(wanted).then(data => { if (previews.current !== mine) return; drawn.current = true; setPicture(data); setPictureError(''); setBusy(false); })
        .catch(e => { if (previews.current !== mine) return; setPictureError((e as Error).message); setBusy(false); });
    }, drawn.current ? 300 : 0);
    return () => clearTimeout(timer);
  }, [selectionKey, ready, backwards, retry]);

  /** Plan writes run one at a time, each against the revision the last one returned. The plan is created by the first of them. */
  function writePlan(write: (plan: Plan) => Promise<Plan>, title?: string): Promise<Plan> {
    const run = queue.current.then(async () => {
      let current = planNow.current;
      if (!current) {
        const view = now.current.selection ?? selectionFor(siteId);
        current = await createPlan(siteId, title ?? planTitle(view), view);
        synced.current = JSON.stringify(view); applyPlan(current); refreshPlans();
      }
      try { const next = await write(current); applyPlan(next); return next; }
      catch (e) {
        if (!(e instanceof ProcessApiError) || e.status !== 409) throw e;
        try { applyPlan(await getPlan(current.id), true); } catch { /* What is shown stays until the next reload. */ }
        setNotice('This work was changed somewhere else, so it has been reloaded with the latest steps and selection. Your last change was not saved; make it again if it still applies.');
        throw new Error('This work changed somewhere else and was reloaded. Make the change again if it still applies.');
      }
    });
    queue.current = run.catch(() => undefined);
    return run;
  }
  // A saved plan keeps the selection it is about.
  useEffect(() => {
    if (!plan || !selection || selectionKey === synced.current) return;
    const timer = setTimeout(() => { const key = selectionKey; writePlan(current => updatePlan(current, { selection })).then(() => { synced.current = key; }).catch(() => undefined); }, 800);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectionKey, plan?.id]);

  const work: Work = {
    siteId, selection, selectionKey, datasets: datasets ?? [],
    ensureSaved() {
      const { key, selection: view } = now.current;
      if (!view) return Promise.reject(new Error('Nothing is in view to save.'));
      if (saved.current?.key === key) return saved.current.ids;
      const ids = savePicture(view).then(run => Object.fromEntries(Object.entries(run.results).map(([name, result]) => [name, result?.id])) as SavedIds);
      saved.current = { key, ids };
      ids.catch(() => { if (saved.current?.ids === ids) saved.current = null; });
      return ids;
    },
    addStep: (step: NewStep) => writePlan(current => addPlanStep(current, step)).then(() => undefined),
    askAssistant: companion ? text => companion.show({ kind: 'text', label: `Workbench · ${plan?.title ?? planTitle(selection)}`, page_path: '/workbench/', captured_at: new Date().toISOString(), content: text }) : undefined,
  };
  const onStep = (stepId: string, change: { status?: PlanStep['status']; text?: string; outcome?: string }) => writePlan(current => updatePlanStep(current, stepId, change)).then(() => undefined);
  async function openPlan(id: string) {
    setNotice('');
    try { applyPlan(await getPlan(id), true); setDataNotice(''); } catch (e) { setNotice(`That work could not be opened. ${(e as Error).message}`); }
  }
  const title = plan?.title ?? planTitle(selection), progress = plan?.progress;
  const status = !plan ? 'Not saved yet. It becomes your saved work the first time you add a step, ask for evidence or propose an action.'
    : [(progress!.to_do ?? progress!.open) ? `${count(progress!.to_do ?? progress!.open, 'step')} to do` : 'No steps to do', progress!.waiting_for_approval && `${progress!.waiting_for_approval} waiting for approval`,
      progress!.waiting_for_reply && `${progress!.waiting_for_reply} waiting for a reply`, progress!.done && `${progress!.done} done`].filter(Boolean).join(' · ');
  const waiting = loadError ? 'Available once the deliveries above can be read.' : !datasets || !selection ? 'Waiting for the deliveries…' : !datasets.length ? 'Appears here once a delivery is in view.'
    : !selection.dataset_ids.length ? 'Select a delivery above to see its values.' : !selection.parameter ? (scope.known && !scope.parameters.length ? 'The selected deliveries list no parameters.' : 'Reading what the selected deliveries hold…') : undefined;

  return <div className="workspace-page" data-testid="workbench">
    <WorkspacePageHeader title={<PlanTitle title={title} onRename={next => writePlan(current => current.title === next ? Promise.resolve(current) : updatePlan(current, { title: next }), next).then(refreshPlans)} />}
      description={<span data-testid="plan-status">{status}</span>}
      actions={<MyWork plans={plans} currentId={plan?.id} onShow={refreshPlans} onOpen={id => void openPlan(id)} onNew={() => { applyPlan(null); setNotice(''); }} />} />
    {notice && <div role="alert" className="mb-4 flex items-start justify-between gap-3 rounded-control border border-amber-200 bg-status-warning-bg p-3 text-xs leading-5 text-text-primary" data-testid="workbench-notice"><span>{notice}</span>
      <button type="button" className="shrink-0 text-brand-teal underline" onClick={() => setNotice('')}>Dismiss</button></div>}
    <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_340px]">
      <div className="min-w-0 space-y-5">
        <DataInView datasets={datasets} error={loadError} onRetry={() => setAttempt(n => n + 1)} selection={selection} onChange={setSelection} profiles={profiles} notice={dataNotice} />
        <Picture picture={picture} busy={busy} error={pictureError} onRetry={() => setRetry(n => n + 1)} selection={selection} datasets={datasets ?? []} emptyReason={waiting} />
        <Findings picture={pictureError ? null : picture} unavailable={pictureError ? 'Findings appear once the picture can be calculated.' : waiting} work={work} />
      </div>
      <div className="min-w-0 xl:sticky xl:top-0 xl:max-h-[calc(100vh-7.5rem)] xl:overflow-y-auto">
        <NextSteps plan={plan} work={work} onStep={onStep} batches={scope.batches} canCite={ready && !!picture && !pictureError} />
      </div>
    </div>
  </div>;
}

function PlanTitle({ title, onRename }: { title: string; onRename: (title: string) => Promise<unknown> }) {
  const [editing, setEditing] = useState(false), [text, setText] = useState(''), [error, setError] = useState('');
  async function save() {
    if (!editing) return;   // Enter and the blur that follows it are one save
    const next = text.trim(); setEditing(false);
    if (!next || next === title) return;
    try { setError(''); await onRename(next); } catch (e) { setError((e as Error).message); }
  }
  if (editing) return <form className="min-w-0 flex-1" onSubmit={e => { e.preventDefault(); void save(); }}>
    <input aria-label="Name of this work" autoFocus maxLength={160} value={text} onChange={e => setText(e.target.value)} onBlur={() => void save()} onKeyDown={e => { if (e.key === 'Escape') setEditing(false); }}
      className="w-full max-w-xl rounded-control border border-border-strong bg-surface px-2 py-1 text-[20px] font-semibold text-text-primary" /></form>;
  return <><button type="button" title="Rename" aria-label={`${title}. Rename`} onClick={() => { setText(title); setEditing(true); }} className="group inline-flex min-w-0 items-center gap-2 break-words text-left hover:text-brand-teal-dark">
    <span className="min-w-0">{title}</span><Pencil size={14} aria-hidden className="shrink-0 text-text-tertiary opacity-60 group-hover:opacity-100" /></button>
    {error && <span role="alert" className="text-xs font-normal text-status-warning">Not renamed. {error}</span>}</>;
}

function MyWork({ plans, currentId, onOpen, onNew, onShow }: { plans: PlanSummary[] | null; currentId?: string; onOpen: (id: string) => void; onNew: () => void; onShow: () => void }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', away); document.addEventListener('keydown', key);
    return () => { document.removeEventListener('mousedown', away); document.removeEventListener('keydown', key); };
  }, [open]);
  const updated = (iso: string) => { const date = new Date(iso); return Number.isNaN(date.getTime()) ? '' : date.toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }); };
  const row = 'block w-full rounded-control px-2.5 py-2 text-left text-xs hover:bg-surface-secondary focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-teal';
  return <div ref={box} className="relative flex-1 sm:flex-none">
    <button type="button" className="chrome-button w-full" aria-haspopup="menu" aria-expanded={open} onClick={() => { if (!open) onShow(); setOpen(!open); }}>My work<ChevronDown size={14} /></button>
    {open && <div role="menu" aria-label="My work" className="absolute left-0 z-30 mt-1 max-h-[60vh] w-[min(20rem,calc(100vw-2rem))] overflow-y-auto rounded-card border border-border-hairline bg-surface p-1.5 shadow-lg sm:left-auto sm:right-0">
      <button type="button" role="menuitem" className={`${row} flex items-center gap-1.5 font-medium text-brand-teal`} onClick={() => { setOpen(false); onNew(); }}><Plus size={13} />New</button>
      {plans === null && <p role="status" className="px-2.5 py-2 text-xs text-text-tertiary">Reading your saved work…</p>}
      {plans?.length === 0 && <p className="px-2.5 py-2 text-xs leading-5 text-text-tertiary">Nothing saved yet. Work is saved the first time you add a step.</p>}
      {plans?.map(item => <button key={item.id} type="button" role="menuitem" aria-current={item.id === currentId || undefined} className={`${row} ${item.id === currentId ? 'bg-brand-teal-light/60' : ''}`} onClick={() => { setOpen(false); if (item.id !== currentId) onOpen(item.id); }}>
        <span className="block break-words font-medium text-text-primary">{item.title}{item.status === 'closed' ? ' · closed' : ''}</span>
        <span className="block text-[11px] text-text-tertiary">{item.open_steps ? `${count(item.open_steps, 'step')} to do` : item.steps ? 'All steps closed' : 'No steps yet'}{updated(item.updated_at) ? ` · updated ${updated(item.updated_at)}` : ''}</span></button>)}
    </div>}
  </div>;
}
