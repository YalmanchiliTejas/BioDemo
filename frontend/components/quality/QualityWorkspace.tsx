'use client';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useWorkspace } from '@/lib/workspace-context';
import { processRequest, ProcessApiError } from '@/lib/process-api';
import { getSignal, openCaseFromSignal, type Signal } from '@/lib/signals-api';
import { createQuality, getQuality, getAdoptionContext, listQuality, qualityAssignees, qualityPath, updateQuality, type AdoptionContext, type Assignee, type Fields, type QualityWorkspace, type Ref } from '@/lib/quality-workflow-api';
import { SourceInspector } from './SourceInspector';
import { SignalEvidence } from '@/components/trends/SignalEvidence';

const input = 'mt-1 block w-full rounded border border-border-hairline bg-surface px-3 py-2 text-sm';
const panel = 'rounded-card border border-border-hairline bg-surface p-4';
const btn = 'rounded border border-border-hairline bg-surface px-3 py-2 text-sm disabled:opacity-40';
const lines = (value: string) => value.split('\n').map(s => s.trim()).filter(Boolean);
const text = (value: unknown) => value == null ? 'Unknown' : typeof value === 'object' ? JSON.stringify(value) : String(value);
const refKey = (r: Ref) => `${r.kind}:${r.id}@${r.revision}`;
const identifiers = (value: Fields = {}) => Object.entries(value).map(([key,value])=>`${key.replaceAll('_',' ')}: ${Array.isArray(value)?value.join(', '):text(value)}`).join(' · ');
const assessmentLabels = {event_description:'Event description',scope:'Investigation scope',technical_summary:'Technical summary',initial_risk:'Initial risk',limitations:'Limitations',impact:'Impact assessment'} as const;
function missingCheck(w: QualityWorkspace, check: string) {
  if (check === 'owner_authority') return `Owner ${w.case.owner_id} needs current technical-review authority before local approval`;
  const separator = check.indexOf(':');
  const kind = check.slice(0, separator), id = check.slice(separator + 1);
  if (kind === 'evidence_request') {
    const request = w.requests.find(item => item.id === id);
    if (request) return `Evidence needed: ${request.description} · owner ${request.owner_id}`;
  }
  if (kind === 'immediate_action') {
    const action = w.actions.find(item => item.id === id);
    if (action) return `Immediate action: ${action.description} · owner ${action.owner_id}`;
  }
  return check.replaceAll('_', ' ');
}
const transitions: Record<string, string> = { assign: 'Assign investigation', request_evidence: 'Wait for more evidence', no_formal_deviation: 'No formal deviation', reference_external: 'Reference external quality record', submit_technical: 'Submit technical review', submit_qa: 'Submit QA review', return: 'Return for more evidence', approve_local: 'Approve local preparation' };
function useLiveRoute() {
  const live = useRef(true);
  useEffect(() => {
    live.current=true;
    // Next navigation may wait for server components. Stop old completions at
    // the user's navigation intent, before the previous route unmounts.
    const navigating = (event: MouseEvent) => {
      if(event.button!==0||event.metaKey||event.ctrlKey||event.shiftKey||event.altKey)return;
      const link=(event.target as Element).closest?.('a[href]') as HTMLAnchorElement|null;
      if(!link||link.hasAttribute('download')||link.target==='_blank')return;
      const next=new URL(link.href,window.location.href);
      if(next.origin===window.location.origin&&(next.pathname!==window.location.pathname||next.search!==window.location.search))live.current=false;
    };
    const back = () => {live.current=false;};
    document.addEventListener('click',navigating,true);window.addEventListener('popstate',back);
    return () => {live.current=false;document.removeEventListener('click',navigating,true);window.removeEventListener('popstate',back);};
  }, []);
  return live;
}

function NewWorkspace({ signal, context, onCreated }: { signal?: Signal | null; context?: AdoptionContext | null; onCreated: (w: QualityWorkspace) => void }) {
  const { organization, account } = useWorkspace();
  const live=useLiveRoute(), known=context?.case, associations=known?.associations ?? signal?.associations ?? {};
  const [people, setPeople] = useState<Assignee[]>([]), [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const [pendingCreate,setPendingCreate]=useState<{payload:Fields;key:string;formSignature:string}|null>(null);
  const [form, setForm] = useState({site: known?.site_id ?? signal?.site_id ?? organization?.site_ids[0] ?? '', title: known?.title ?? signal?.rule ?? '', owner: known?.owner_id ?? '', qa: known?.qa_reviewer_id ?? '', batch: String(associations.batch_id ?? (signal?.subject?.kind === 'batch' ? signal.subject.id : '')), equipment: String(associations.equipment_id ?? ''), risk: known?.initial_risk ?? '', deadline: known?.deadline?.slice(0,10) ?? '', category: known?.category ?? (signal?.kind === 'lab_oos' ? 'oos' : 'process_excursion'), priority:known?.priority ?? 'normal'});
  useEffect(() => { if (!form.site && organization?.site_ids[0]) setForm(f => ({...f,site:organization.site_ids[0]})); }, [organization, form.site]);
  useEffect(() => { let active=true;setPeople([]); if (form.site) qualityAssignees(form.site).then(r => {if(active)setPeople(r.items);}).catch(e => {if(active)setError(e.message);});return()=>{active=false;}; }, [form.site]);
  async function submit(e: React.FormEvent) {
    e.preventDefault();if(!live.current)return; setBusy(true); setError('');
    const retrying=Boolean(pendingCreate);
    try {
      let submission=pendingCreate;
      if(!submission){
      let source = signal ? await getSignal(signal.signal_id) : null;
      if(!live.current)return;
      if (source && !source.case_id) { await openCaseFromSignal(source.signal_id, form.owner, form.qa);if(!live.current)return; source = await getSignal(source.signal_id); }
      if(!live.current)return;
      const basis = context ?? (source?.case_id ? await getAdoptionContext(source.case_id) : null);
      if(!live.current)return;
      const payload={case_id: basis?.case.case_id ?? undefined, expected_case_revision:basis?.case.revision, site_id:form.site, title:form.title,
        owner_id:form.owner,qa_reviewer_id:form.qa, category:form.category,priority:form.priority,initial_risk:form.risk,
        deadline:form.deadline === basis?.case.deadline?.slice(0,10) ? basis?.case.deadline : form.deadline ? new Date(`${form.deadline}T12:00:00`).toISOString() : null,
        associations:{...(basis?.case.associations ?? source?.associations ?? {}),...(form.batch ? {batch_id:form.batch} : {}),...(form.equipment ? {equipment_id:form.equipment} : {})},
        discovery_refs:basis?.discovery_refs ?? (source ? [{kind:'deviation_signal',id:source.signal_id,revision:source.revision,site_id:source.site_id}] : [])};
      submission={payload:JSON.parse(JSON.stringify(payload)),key:crypto.randomUUID(),formSignature:JSON.stringify(form)};
      setPendingCreate(submission);
      }
      // An ambiguous response must retry this exact request, bypassing preflight
      // reads which may now correctly report an already-managed case.
      const w = await createQuality(submission.payload,submission.key);
      if(!w?.case?.case_id||!Number.isInteger(w.revision)||(submission.payload.case_id&&w.case.case_id!==submission.payload.case_id))throw new Error('Workspace response was incomplete. Retry the original submission to confirm its result.');
      if(live.current){setPendingCreate(null);onCreated(w);}
    } catch (err) {
      if(live.current){
        // A first explicit domain rejection did not commit this new request.
        // After response loss, even a later denial must not replace the intent.
        if(!retrying&&err instanceof ProcessApiError&&err.status>=400&&err.status<500)setPendingCreate(null);
        setError((err as Error).message);
      }
    } finally { if(live.current)setBusy(false); }
  }
  return <form className={`${panel} mt-5 grid gap-3 sm:grid-cols-2`} onSubmit={submit} aria-label="New Quality workspace">
    {context?.assignment_issues?.map(issue=><p key={issue} role="alert" className="sm:col-span-2 text-sm text-status-warning">{issue}</p>)}
    <h2 className="font-medium sm:col-span-2">{known || signal?.case_id ? 'Continue the existing case' : 'Start Quality preparation'}</h2>
    <p className="text-sm text-text-secondary sm:col-span-2">Local preparation for human review. Your quality system remains the approval system of record.</p>
    {Object.keys(associations).length>0&&<p data-testid="initiation-context" className="text-xs text-text-secondary sm:col-span-2">Known source context · {identifiers(associations)}. These associations stay with the case.</p>}
    <label>Site<input aria-label="Site" className={input} required readOnly={Boolean(known||signal)} value={form.site} onChange={e => setForm({...form,site:e.target.value,owner:'',qa:''})} /></label>
    <label>Event title<input aria-label="Event title" className={input} required value={form.title} onChange={e => setForm({...form,title:e.target.value})} /></label>
    <label>Investigation owner<select aria-label="Investigation owner" className={input} required value={form.owner} onChange={e => setForm({...form,owner:e.target.value})}><option value="">Choose eligible owner</option>{people.filter(p => p.eligible_owner).map(p => <option key={p.actor_id} value={p.actor_id}>{p.label}{p.actor_id === account?.actor_id ? ' (you)' : ''}</option>)}</select></label>
    <label>QA reviewer<select aria-label="QA reviewer" className={input} required value={form.qa} onChange={e => setForm({...form,qa:e.target.value})}><option value="">Choose eligible QA reviewer</option>{people.filter(p => p.eligible_qa_reviewer).map(p => <option key={p.actor_id} value={p.actor_id}>{p.label}</option>)}</select></label>
    <label>Batch identifier<input aria-label="Batch identifier" className={input} value={form.batch} onChange={e => setForm({...form,batch:e.target.value})} /></label>
    <label>Equipment identifier<input aria-label="Equipment identifier" className={input} value={form.equipment} onChange={e => setForm({...form,equipment:e.target.value})} /></label>
    <label>Category<select aria-label="Category" className={input} value={form.category} onChange={e => setForm({...form,category:e.target.value})}><option value="process_excursion">Process excursion</option><option value="oos">Out of specification</option><option value="quality_event">Quality event</option></select></label>
    <label>Priority<select aria-label="Priority" className={input} value={form.priority} onChange={e => setForm({...form,priority:e.target.value})}>{['normal','high','critical'].map(v => <option key={v}>{v}</option>)}</select></label>
    <label>Initial risk<input aria-label="Initial risk" className={input} value={form.risk} onChange={e => setForm({...form,risk:e.target.value})} /></label>
    <label>Investigation deadline<input aria-label="Investigation deadline" type="date" className={input} value={form.deadline} onChange={e => setForm({...form,deadline:e.target.value})} /></label>
    {error && <p role="alert" className="text-status-critical sm:col-span-2">{error}</p>}
    {pendingCreate&&!busy&&<div role="status" data-testid="create-pending-notice" className="rounded border border-border-hairline p-3 text-sm sm:col-span-2"><p>Confirm the original submission: “{pendingCreate.payload.title}”. Retry uses its original people, context and sources.</p>{pendingCreate.formSignature!==JSON.stringify(form)&&<p className="mt-2">Later form edits are unsaved and will not be included in this retry.</p>}</div>}
    <button className={btn} disabled={busy} formNoValidate={Boolean(pendingCreate)} type="submit">{busy ? 'Creating…' : pendingCreate ? 'Retry original submission' : 'Create workspace'}</button>
  </form>;
}

function Assessment({ w, run }: { w: QualityWorkspace; run: Run }) {
  const a = w.assessment;
  const [labRefs,setLabRefs] = useState<Ref[]>(a.initial_lab_assessment?.evidence_refs ?? []);
  const [form,setForm] = useState({event_description:a.event_description ?? '',scope:a.scope ?? '',technical_summary:a.technical_summary ?? '',root_cause_status:a.root_cause_status ?? 'unresolved',limitations:(a.limitations ?? []).join('\n'),impact:w.impact.summary ?? '',initial_risk:a.initial_risk ?? w.case.initial_risk ?? '',lab_conclusion:a.initial_lab_assessment?.conclusion ?? 'inconclusive',lab_rationale:a.initial_lab_assessment?.rationale ?? ''});
  const editable = w.allowed_actions.includes('assessment');
  return <form className="grid gap-3 sm:grid-cols-2" onSubmit={e => {e.preventDefault();void run('assessment',{assessment:{event_description:form.event_description,scope:form.scope,technical_summary:form.technical_summary,root_cause_status:form.root_cause_status,limitations:lines(form.limitations),initial_risk:form.initial_risk,impact:{...w.impact,status:'assessed',summary:form.impact},...(w.case.category==='oos' ? {initial_lab_assessment:{conclusion:form.lab_conclusion,rationale:form.lab_rationale,evidence_refs:labRefs}} : {})}});}}>
    {(['event_description','scope','technical_summary','initial_risk','limitations','impact'] as const).map(key => <label key={key}>{assessmentLabels[key]}<textarea aria-label={assessmentLabels[key]} className={input} disabled={!editable} required={['event_description','scope','technical_summary','impact'].includes(key)} value={form[key]} onChange={e=>setForm({...form,[key]:e.target.value})} /></label>)}
    <label>Root cause status<select aria-label="Root cause status" className={input} disabled={!editable} value={form.root_cause_status} onChange={e=>setForm({...form,root_cause_status:e.target.value})}><option value="unresolved">Unresolved</option><option value="supported_hypothesis">Supported hypothesis</option></select></label>
    {w.case.category==='oos' && <><label>Initial laboratory conclusion<select aria-label="Initial laboratory conclusion" disabled={!editable} className={input} value={form.lab_conclusion} onChange={e=>setForm({...form,lab_conclusion:e.target.value})}>{['inconclusive','expanded_investigation','laboratory_error_supported'].map(v=><option key={v}>{v}</option>)}</select></label><label>Laboratory rationale<textarea aria-label="Laboratory rationale" disabled={!editable} required className={input} value={form.lab_rationale} onChange={e=>setForm({...form,lab_rationale:e.target.value})}/></label><p className="text-xs">The original OOS remains preserved. Assessment links the case sources below.</p></>}
    {w.case.category==='oos'&&<RefChoices w={w} selected={labRefs} setSelected={setLabRefs}/>}
    {editable && <button className={btn}>Save assessment</button>}
    <div className="sm:col-span-2"><h3 className="font-medium">Extent of condition candidates</h3><p className="text-xs text-text-secondary">Shared identifiers indicate candidates, not established impact.</p>{(w.impact.candidates ?? []).map((c:Fields,i:number)=><p key={i} className="mt-2 text-sm">{identifiers(c.identifiers)} · distribution {c.distribution_status ?? 'unknown'} · {c.status}</p>)}</div>
  </form>;
}

type Run = (operation:string, fields?:Fields) => Promise<boolean>;
function RefChoices({w,selected,setSelected}:{w:QualityWorkspace;selected:Ref[];setSelected:(refs:Ref[])=>void}) {
 return <fieldset className="mt-2"><legend className="text-xs">Attach pinned source revisions</legend>{w.sources.map(s=><label key={refKey(s.ref)} className="mt-1 block text-xs"><input aria-label={refKey(s.ref)} type="checkbox" checked={selected.some(r=>refKey(r)===refKey(s.ref))} onChange={e=>setSelected(e.target.checked?[...selected,s.ref]:selected.filter(r=>refKey(r)!==refKey(s.ref)))} /> {refKey(s.ref)}</label>)}</fieldset>;
}
function Science({w,run}:{w:QualityWorkspace;run:Run}) {
 const [catalog,setCatalog]=useState<Fields|null>(null),[error,setError]=useState(''),[hypothesis,setHypothesis]=useState(''),[prior,setPrior]=useState(''),[rationale,setRationale]=useState(''),[status,setStatus]=useState('hypothesis'),[counter,setCounter]=useState('not_searched'),[support,setSupport]=useState<Ref[]>([]),[counterRefs,setCounterRefs]=useState<Ref[]>([]);
 const sourceBasis=JSON.stringify(w.sources.map(s=>[s.ref.kind,s.ref.id,s.ref.revision]).sort());
 useEffect(()=>{
   let active=true;setCatalog(null);setError('');
   processRequest<Fields>(`${qualityPath(w.case.case_id)}/science/catalog`).then(result=>{if(active){setCatalog(result);setError('');}}).catch(e=>{if(active)setError(e.message);});
   return()=>{active=false;};
 },[w.case.case_id,sourceBasis]);
 return <div className="space-y-4"><p className="text-sm">Source-backed conditional engineering work · unqualified/advisory · {w.science.status ?? 'not started'}. Calculations do not confirm a cause.</p>
   {error && <p role="alert">{error}</p>}
   <p className="text-xs">Supplied configurations: {(catalog?.configurations??[]).map((c:Fields)=>c.id).join(', ')||'None found. A source configuration and complete inputs are required.'}</p>
   {w.allowed_actions.includes('scientific_analysis')&&<button className={btn} onClick={()=>void run('science/analyze')}>Run supplied scientific configurations</button>}
   {(w.science.model_runs??[]).map((m:Fields,i:number)=><article key={i} className={`${panel} text-sm`} data-testid="science-run"><h3 className="font-medium">{m.configuration_id} · {m.status}</h3><p>{m.model?.id} · {m.model?.qualification ?? 'unqualified / advisory'}</p>
     {!!m.missing_inputs?.length&&<p>Missing inputs: {m.missing_inputs.map(text).join(', ')}</p>}{!!m.issues?.length&&<p>Issues: {m.issues.map(text).join('; ')}</p>}
     {!!m.comparison?.length&&<table className="mt-3 w-full text-left text-xs"><caption className="text-left font-medium">Observed versus predicted</caption><thead><tr>{['Observable','Coordinate','Unit','Observed','Predicted','Residual'].map(h=><th key={h}>{h}</th>)}</tr></thead><tbody>{m.comparison.map((c:Fields,j:number)=><tr key={j}>{['observable','coordinate','unit','observed','predicted','residual'].map(k=><td className="py-2" key={k}>{text(c[k])}</td>)}</tr>)}</tbody></table>}
     {m.output&&<details className="mt-2"><summary>Calculated outputs and basis</summary><pre className="max-h-72 overflow-auto whitespace-pre-wrap text-xs">{JSON.stringify(m.output,null,2)}</pre></details>}
     {m.model&&<details className="mt-2"><summary>Registered model, units and limitations</summary><pre className="max-h-72 overflow-auto whitespace-pre-wrap text-xs">{JSON.stringify(m.model,null,2)}</pre></details>}
     <p className="mt-2 text-xs">Assumptions: {(m.assumptions??[]).map(text).join('; ')||'None supplied'}<br/>Uncertainty: {(m.uncertainty??[]).map(text).join('; ')||'Not characterized'}</p><p className="text-xs">Sources: {(m.source_refs??[]).map(refKey).join(', ')}</p>
   </article>)}
   {(w.science.unknowns??[]).map((u:unknown,i:number)=><p className="text-sm" key={i}>Unknown: {text(u)}</p>)}
   <h3 className="font-medium">Hypotheses and challenges</h3>{[...w.hypotheses,...(w.science.hypotheses??[])].map((h:Fields,i:number)=><article key={h.id??i} className="border-l-2 border-border-hairline pl-3 text-sm"><p>{h.text} · {h.status??'hypothesis'}</p><p className="text-xs">{h.id} · Counterevidence: {h.counterevidence_status??'not searched'}</p><p className="text-xs">Supports: {(h.support_refs??[]).map(text).join(', ')||'None'}<br/>Against: {(h.counterevidence_refs??[]).map(text).join(', ')||'None'}</p>{h.prior_hypothesis_id&&<p className="text-xs">Follows {h.prior_hypothesis_id}: {h.rationale}</p>}</article>)}
   {w.allowed_actions.includes('hypotheses')&&<form className="grid gap-2" onSubmit={e=>{e.preventDefault();void run('hypotheses',{hypothesis:{text:hypothesis,status,counterevidence_status:counter,support_refs:support,counterevidence_refs:counterRefs,...(prior?{prior_hypothesis_id:prior,rationale}: {})}}).then(saved=>{if(saved)setHypothesis('');});}}>
     <label>Hypothesis or follow-up<textarea aria-label="Hypothesis or follow-up" required className={input} value={hypothesis} onChange={e=>setHypothesis(e.target.value)}/></label><label>Hypothesis status<select aria-label="Hypothesis status" className={input} value={status} onChange={e=>setStatus(e.target.value)}>{['hypothesis','unresolved','rejected'].map(v=><option key={v}>{v}</option>)}</select></label>
     <label>Prior hypothesis reference (for challenge)<input aria-label="Prior hypothesis reference (for challenge)" className={input} value={prior} onChange={e=>setPrior(e.target.value)}/></label>{prior&&<label>Challenge rationale<textarea aria-label="Challenge rationale" required className={input} value={rationale} onChange={e=>setRationale(e.target.value)}/></label>}
     <RefChoices w={w} selected={support} setSelected={setSupport}/><label>Counterevidence search<select aria-label="Counterevidence search" className={input} value={counter} onChange={e=>setCounter(e.target.value)}>{['not_searched','searched_none','searched_found'].map(v=><option key={v}>{v}</option>)}</select></label><RefChoices w={w} selected={counterRefs} setSelected={setCounterRefs}/><button className={btn}>Record hypothesis</button>
   </form>}
 </div>;
}

function FollowUp({w,run,inspect}:{w:QualityWorkspace;run:Run;inspect:(path:string)=>void}) {
 const [needed,setNeeded]=useState(''),[description,setDescription]=useState(''),[owner,setOwner]=useState(w.case.owner_id),[due,setDue]=useState(''),[kind,setKind]=useState('corrective_action'),[refs,setRefs]=useState<Ref[]>([]),[people,setPeople]=useState<Assignee[]>([]);
 const [peopleLoading,setPeopleLoading]=useState(true),[peopleError,setPeopleError]=useState(''),[peopleRetry,setPeopleRetry]=useState(0);
 useEffect(()=>{
   let active=true;setPeople([]);setPeopleLoading(true);setPeopleError('');
   qualityAssignees(w.case.site_id).then(r=>{if(active)setPeople(r.items);}).catch(e=>{if(active)setPeopleError(e.message);}).finally(()=>{if(active)setPeopleLoading(false);});
   return()=>{active=false;};
 },[w.case.site_id,peopleRetry]);
 const editable=w.allowed_actions.includes('actions');
 return <div className="space-y-4"><p className="text-xs">Local tracking only. Adding or completing an action does not execute it in manufacturing or write to your quality system.</p>
   {peopleLoading&&<p role="status" className="text-xs">Loading follow-up owners…</p>}
   {peopleError&&<div role="alert" className="text-sm"><p>Could not load follow-up owners: {peopleError}</p><button type="button" className={btn} onClick={()=>setPeopleRetry(n=>n+1)}>Retry follow-up owners</button></div>}
   {editable&&<label>Follow-up owner<select aria-label="Follow-up owner" className={input} disabled={peopleLoading||Boolean(peopleError)} value={owner} onChange={e=>setOwner(e.target.value)}><option value="">Choose eligible owner</option>{people.map(p=><option key={p.actor_id} value={p.actor_id}>{p.label}</option>)}</select></label>}
   {w.requests.map(r=><article key={r.id} className={panel}><p>{r.description}</p><p className="text-xs">{r.id} · {r.status} · owner {r.owner_id} · {r.required?'required':'optional'}</p>{editable&&r.status!=='resolved'&&<button className={`${btn} mt-2`} disabled={!refs.length} onClick={()=>void run('evidence-requests',{request:{id:r.id,status:'resolved',evidence_refs:refs}})}>Resolve request with selected evidence</button>}</article>)}
   {w.allowed_actions.includes('evidence_requests')&&<form onSubmit={e=>{e.preventDefault();void run('evidence-requests',{request:{description:needed,owner_id:owner,required:true}}).then(saved=>{if(saved)setNeeded('');});}}><label>Evidence needed<input aria-label="Evidence needed" required className={input} value={needed} onChange={e=>setNeeded(e.target.value)}/></label><button className={`${btn} mt-2`} disabled={peopleLoading||Boolean(peopleError)||!people.some(p=>p.actor_id===owner)}>Request evidence</button></form>}
   {w.actions.map(a=><article key={a.id} className={panel}><p>{a.description}</p><p className="text-xs">{a.kind} · {a.status} · owner {a.owner_id} · due {a.due_at} · effectiveness {a.effectiveness_status}</p>{(w.workflow.effectiveness_concerns??[]).filter((c:Fields)=>c.action_id===a.id).map((c:Fields)=><div key={c.id} data-testid="effectiveness-concern" className="mt-3 rounded border border-status-warning p-3 text-sm"><p className="font-medium">Human assessment required · action {a.id}</p><p>{c.description}</p><p className="mt-1 text-xs">{c.timing_status==='uncertain'?'Timing uncertain: source event time or action completion time is missing.':'Source event occurred after action completion.'} Action completed: {c.action_completed_at??'unknown'}.</p><p className="mt-1 text-xs">Review the linked evidence and record your assessment in Assessment and impact. Effectiveness remains subject to human review.</p><div className="mt-2 flex flex-wrap gap-2">{(c.evidence_refs??[]).map((ref:Ref)=><button key={refKey(ref)} className="underline text-xs" onClick={()=>inspect(`${qualityPath(w.case.case_id)}/evidence/${encodeURIComponent(ref.kind)}/${encodeURIComponent(ref.id)}?revision=${ref.revision}`)}>Inspect {refKey(ref)}</button>)}</div></div>)}{editable&&a.status!=='completed'&&<button disabled={!refs.length} className={`${btn} mt-2`} onClick={()=>void run('actions',{action:{id:a.id,status:'completed',completion_refs:refs}})}>Record completion with selected evidence</button>}</article>)}
   {editable&&<><RefChoices w={w} selected={refs} setSelected={setRefs}/><form className="grid gap-2" onSubmit={e=>{e.preventDefault();void run('actions',{action:{description,owner_id:owner,kind,due_at:new Date(`${due}T12:00:00`).toISOString()}}).then(saved=>{if(saved)setDescription('');});}}><label>Action description<input aria-label="Action description" required className={input} value={description} onChange={e=>setDescription(e.target.value)}/></label><label>Action kind<select aria-label="Action kind" className={input} value={kind} onChange={e=>setKind(e.target.value)}>{['immediate_correction','corrective_action','capa'].map(v=><option key={v}>{v}</option>)}</select></label><label>Action deadline<input aria-label="Action deadline" required type="date" className={input} value={due} onChange={e=>setDue(e.target.value)}/></label><button className={btn} disabled={peopleLoading||Boolean(peopleError)||!people.some(p=>p.actor_id===owner)}>Add action</button></form></>}
 </div>;
}

function QualityWorkspaceRoute() {
 const query=useSearchParams(),router=useRouter(),{account,organization}=useWorkspace();
 const caseId=query.get('case'),signalId=query.get('signal');
 const live=useLiveRoute(),readSequence=useRef(0);
 const [w,setW]=useState<QualityWorkspace|null>(null),[items,setItems]=useState<QualityWorkspace[]>([]),[signal,setSignal]=useState<Signal|null>(null),[adoption,setAdoption]=useState<AdoptionContext|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[loading,setLoading]=useState(true),[source,setSource]=useState(''),[reason,setReason]=useState(''),[external,setExternal]=useState(''),[focus,setFocus]=useState('Overview'),[exported,setExported]=useState<Fields|null>(null);
 const load=useCallback(async()=>{
   const sequence=++readSequence.current,current=()=>live.current&&sequence===readSequence.current;
   setLoading(true);setError('');setSignal(null);setAdoption(null);
   try{
     if(caseId){
       try{const next=await getQuality(caseId);if(current())setW(next);}
       catch(e){if(e instanceof ProcessApiError&&e.status===400){const context=await getAdoptionContext(caseId);if(current())setAdoption(context);}else throw e;}
     }else if(signalId){
       const next=await getSignal(signalId);if(!current())return;setSignal(next);
       if(next.case_id){
         try{const workspace=await getQuality(next.case_id);if(current()){setW(workspace);router.replace(`/quality/?case=${encodeURIComponent(next.case_id)}`);}}
         catch(e){if(e instanceof ProcessApiError&&e.status===400){const context=await getAdoptionContext(next.case_id);if(current())setAdoption(context);}else throw e;}
       }
     }else if(!query.has('new')){const result=await listQuality();if(current())setItems(result.items);}
   }catch(e){if(current())setError((e as Error).message);}finally{if(current())setLoading(false);}
 },[caseId,signalId,router,query,live]);
 useEffect(()=>{void load();},[load]);
 // Only poll while a real queued operation is pending. No inference while waiting for evidence.
 useEffect(()=>{if(!w||!(w.workflow.preparation?.status==='queued'||w.science.status==='queued'))return;let active=true;const t=setInterval(()=>{getQuality(w.case.case_id).then(next=>{if(active&&live.current)setW(next);}).catch(e=>{if(active&&live.current)setError(e.message);});},2000);return()=>{active=false;clearInterval(t);};},[w,live]);
 const run:Run=async(operation,fields={})=>{if(!live.current||!w||busy||loading)return false;setBusy(true);setError('');++readSequence.current;try{const next=await updateQuality(w,operation,fields);if(!live.current)return false;setW(next);setReason('');return true;}catch(e){if(live.current)setError(`${(e as Error).message}. Unsaved text is kept.${e instanceof ProcessApiError&&e.status===409?' Refresh workspace, review the current draft, then retry.':''}`);return false;}finally{if(live.current)setBusy(false);}};
 const created=(next:QualityWorkspace)=>{if(live.current){setW(next);router.replace(`/quality/?case=${encodeURIComponent(next.case.case_id)}`);}};
 async function exportPackage(){if(!w)return;try{const p=await processRequest<Fields>(`${qualityPath(w.case.case_id)}/export`);if(!live.current)return;setExported(p);const url=URL.createObjectURL(new Blob([JSON.stringify(p,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=`${w.case.case_id}-local-pending.json`;a.click();URL.revokeObjectURL(url);}catch(e){if(live.current)setError((e as Error).message);}}
 return <div className="mx-auto max-w-5xl space-y-4 px-4 py-6 sm:px-6"><div className="flex flex-wrap justify-between gap-3"><div><h1 className="text-2xl font-medium">Quality</h1><p className="mt-1 text-sm text-text-secondary">Event preparation, evidence and local review.</p></div><div className="flex flex-wrap gap-3 text-sm"><Link href="/signals/" className="underline">Signals</Link><Link href="/investigations/" className="underline">Investigation runs</Link><Link href="/quality/?demo=1" className="underline">Campaign demo</Link><Link href="/quality/?new=1" className="underline">New event</Link></div></div>
   <p className="text-xs text-text-tertiary">Signed in as {account?.actor_id ?? '…'} · {organization?.roles.join(', ') ?? 'loading membership'} · {w?.external_status === 'not_requested' ? 'local assessment; no external handoff requested' : 'local preparation only, pending external approval'}</p>
   {error&&<p role="alert" className="rounded border border-status-critical p-3 text-sm text-status-critical">{error}</p>}
   {loading&&<p role="status">Loading authorized Quality records…</p>}
   {!loading&&!w&&!error&&(adoption||signalId||query.has('new'))&&<NewWorkspace signal={signalId&&signal?.signal_id===signalId ? signal : null} context={adoption} onCreated={created}/>}
   {!loading&&!w&&!caseId&&!signalId&&!query.has('new')&&<section className={panel}><h2 className="font-medium">Event queue</h2>{items.length?items.map(item=><Link className="mt-3 block rounded border border-border-hairline p-3 text-sm" key={item.case.case_id} href={`/quality/?case=${encodeURIComponent(item.case.case_id)}`}><strong>{item.case.title}</strong> · {item.workflow.state}<span className="mt-1 block text-xs">{item.case.case_id} · owner {item.case.owner_id} · priority {item.case.priority} · deadline {item.case.deadline??'not assigned'} · {item.completeness.missing.length} missing checks</span></Link>):<p className="mt-2 text-sm">No authorized local workspaces yet. Start from a signal or create a new event.</p>}</section>}
   {w&&<div data-testid="quality-workspace" className="space-y-4" aria-busy={busy}><section className={panel}><div className="flex flex-wrap justify-between gap-2"><h2 className="text-xl font-medium">{w.case.title}</h2><span data-testid="workflow-state" className="text-sm">{w.workflow.state}</span></div><p className="mt-1 text-xs">{w.case.case_id} · revision {w.revision} · site {w.case.site_id} · owner {w.case.owner_id} · QA {w.case.qa_reviewer_id} · deadline {w.case.deadline??'not assigned'}</p><p className="mt-2 text-sm">{identifiers(w.case.associations)}</p>
     <div className="mt-3 flex flex-wrap gap-2">{w.allowed_actions.includes('prepare')&&<button className={btn} disabled={busy} onClick={()=>void run('prepare')}>Prepare evidence</button>}{w.allowed_actions.includes('export')&&<button className={btn} disabled={busy} onClick={()=>void exportPackage()}>Export local package</button>}<button className={btn} disabled={busy} onClick={()=>void load()}>Refresh workspace</button></div>
     <div className="mt-4 text-sm" data-testid="quality-gaps"><h3 className="font-medium">Next review checks</h3>{w.completeness.complete?<p>Material checks complete for local review.</p>:<ul className="mt-1 list-disc pl-5">{w.completeness.missing.map(v=><li key={v} title={v}>{missingCheck(w,v)}</li>)}</ul>}{w.completeness.gaps.map((g,i)=><p key={i}>{g.code?.replaceAll('_',' ')}</p>)}{!!w.completeness.source_drift.length&&<p>Source revisions changed. Refresh and review the changed evidence.</p>}{w.completeness.submission_drift&&<p>The submission differs from the current draft; a fresh review is required.</p>}</div>
   </section>
   {exported&&<p className={panel} data-testid="export-label">{exported.label} · {exported.external_status} · No external approval receipt.</p>}
   <details className={panel}><summary>Optional role focus</summary><p className="mt-2 text-xs">Changes emphasis only. Authority comes from your signed-in membership and the server.</p><select aria-label="Workspace focus" className={input} value={focus} onChange={e=>setFocus(e.target.value)}>{['Overview','Engineer','MSAT','QA'].map(v=><option key={v}>{v}</option>)}</select></details>
   <fieldset disabled={busy||loading} className="space-y-4">
   <details className={panel} open={focus==='Engineer'||undefined}><summary className="cursor-pointer font-medium">Sources and timeline</summary><div className="mt-3 space-y-3">{!w.sources.length&&<p className="text-sm">No sources prepared yet.</p>}{w.sources.map(s=><article data-testid="source-row" key={refKey(s.ref)} className="border-b border-border-hairline pb-2 text-sm"><button className="underline" onClick={()=>setSource(s.url)}>Inspect {s.ref.kind} · {s.ref.id}</button><p className="text-xs">Pinned revision {s.ref.revision} · current {s.current_revision} · {s.state.source_system??s.ref.kind} · {s.state.event_time??'source time unknown'}</p>{s.ref.kind==='deviation_signal'&&s.state.observations?.length>0&&<SignalEvidence signal={{...s.state,case_id:w.case.case_id} as Signal}/>}</article>)}<h3 className="font-medium">Source chronology</h3>{w.timeline.map((t,i)=><p key={i} className="text-xs">{t.event_time??'Event time unknown'} · {t.description} · {t.time_basis}</p>)}</div></details>
   <details className={panel}><summary className="cursor-pointer font-medium">Assessment and impact</summary><div className="mt-3"><Assessment key={`${w.case.case_id}:${w.revision}`} w={w} run={run}/></div></details>
   <details className={panel} open={focus==='MSAT'||undefined}><summary className="cursor-pointer font-medium">Scientific work and hypotheses</summary><div className="mt-3"><Science w={w} run={run}/></div></details>
   <details className={panel}><summary className="cursor-pointer font-medium">Actions and evidence requests</summary><div className="mt-3"><FollowUp w={w} run={run} inspect={setSource}/></div></details>
   <section className={panel}><h3 className="font-medium">Human review and triage</h3><p className="mt-1 text-xs">Submitting preserves a review snapshot. Local approval prepares handoff; it does not approve an official deviation or release a batch.</p><label className="mt-3 block text-sm">Decision reason<textarea aria-label="Decision reason" className={input} value={reason} onChange={e=>setReason(e.target.value)}/></label>{w.allowed_actions.includes('reference_external')&&<label className="mt-3 block text-sm">External quality reference<input aria-label="External quality reference" className={input} value={external} onChange={e=>setExternal(e.target.value)}/></label>}<div className="mt-3 flex flex-wrap gap-2">{Object.entries(transitions).filter(([op])=>w.allowed_actions.includes(op)).map(([op,label])=><button className={btn} key={op} disabled={!reason.trim()||(op==='approve_local'&&!w.completeness.complete)||(op==='reference_external'&&!external.trim())} onClick={()=>void run('transition',{transition:op,reason,...(op==='reference_external'?{external_reference:external}:{})})}>{label}</button>)}</div></section>
   <details className={panel} open={focus==='QA'||undefined}><summary className="cursor-pointer font-medium">Reviews and activity</summary><div className="mt-3 space-y-3 text-xs">{w.reviews.map((r,i)=><article key={i} className="border-b border-border-hairline pb-2"><p>{r.kind??r.decision??'submission'} · {r.reason} · {r.decision==='submitted'?r.submitted_by:r.actor_id} · {r.decision==='submitted'?r.submitted_at:r.at}</p><details><summary>Preserved review record {r.id}</summary><pre className="max-h-80 overflow-auto whitespace-pre-wrap">{JSON.stringify(r,null,2)}</pre></details></article>)}{w.activity.map((a,i)=><p key={i}>{a.at} · {a.actor_id} · {a.operation} · {a.reason}</p>)}</div></details>
   </fieldset>
   </div>}
   {source&&<SourceInspector path={source} onClose={()=>setSource('')}/>}
 </div>;
}

export function QualityWorkspacePage() {
  const query=useSearchParams(),{account,organization,user}=useWorkspace();
  return <QualityWorkspaceRoute key={`${account?.actor_id ?? user?.id ?? ''}:${organization?.id ?? ''}:${query.toString()}`} />;
}
