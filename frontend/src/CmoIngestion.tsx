import { useEffect, useRef, useState } from 'react';

type Item = { id: string; dataset: string; condition: string; cmo: string; disclosure: string; files: {path:string}[] };
type Layout = { fingerprint:string; kind:string; path:string; confirmed:boolean; template_origin:string|null; mapping:unknown; decisions?:unknown[] };
type Measurement = { id:string; source_id:string; batch:string; time:string; parameter:string; value:number|null; unit:string; value_raw:string; unit_raw:string; parser:string; status:string; rule_codes:string[]; source: {path:string; sheet?:string; cell?:string; row?:number; column?:string; page?:number; region?:number[]}; review_binding:string; extraction_confidence?:Record<string,number|null>; extraction_spans?:Record<string,number[]>; extraction_review_reasons?:string[] };
type Issue = {id:string; rule_code:string; path:string; status:string; message?:string};
type Run = {id:string; package_id?:string; extraction_reviews?:unknown[]; status:string; stages:{stage:string; state:string; elapsed_seconds:number}[]; error?:string; unavailable_reasons?:string[]; runtime_seconds?:number; measurements?:Measurement[]; layouts?:Layout[]; issues?:Issue[]; disclosure?:string; human_minutes?:number|null; human_time_status?:string; summary?:Record<string,number|boolean|null>; model_usage?:{role:string; model:string; input_tokens:number|null; output_tokens:number|null; cost_usd:number|null; status:string}[]; documents?:{path:string; doc_type:string; route:{selected_backend?:string; fallback_used?:boolean}}[] };
type Score = {configuration:string; dataset:string; condition:string; status:string; reasons?:string[]; field_recall?:number|null; value_and_unit_accuracy?:number|null; source_provenance_accuracy?:number|null; classification_accuracy?:number|null; mapping_accuracy?:number|null; defect_detection_rate?:number|null; auto_acceptance_rate?:number|null; incorrect_auto_acceptance_rate?:number|null; human_minutes?:number|null; end_to_end_seconds?:number; model_calls?:number; inference_cost_usd?:number|null};
const stages=['Ingest','Classify','Parse','Map','Validate','Review','Store/Export'];
const percent=(n:number|null|undefined)=>n==null?'—':(100*n).toFixed(1)+'%';
const button='rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium hover:bg-slate-50 disabled:opacity-40';
const input='rounded-lg border border-slate-300 bg-white p-2 text-sm';

export default function CmoIngestion({embeddedRunId,authToken=''}:{embeddedRunId?:string;authToken?:string}={}) {
  const [catalog,setCatalog]=useState<Item[]>([]),[dataset,setDataset]=useState('indpensim'),[packageId,setPackageId]=useState('');
  const [configuration,setConfiguration]=useState('clairic_decisions'),[availability,setAvailability]=useState<Record<string,string[]>>({});
  const [configNames,setConfigNames]=useState<Record<string,string>>({}),[run,setRun]=useState<Run|null>(null),[error,setError]=useState('');
  const [busy,setBusy]=useState(false),[actor,setActor]=useState(''),[reason,setReason]=useState(''),[token,setToken]=useState(authToken);
  const [selected,setSelected]=useState<Measurement|null>(null),[source,setSource]=useState<{headers:string[];values:unknown[]}|null>(null),[pdf,setPdf]=useState('');
  const [pdfSize,setPdfSize]=useState<[number,number]>([1,1]);
  const [pdfZoom,setPdfZoom]=useState(false);
  const [layout,setLayout]=useState<Layout|null>(null),[mapping,setMapping]=useState(''),[filter,setFilter]=useState(true),[page,setPage]=useState(0);
  const [corrected,setCorrected]=useState(''),[correctionParameter,setCorrectionParameter]=useState(''),[correctionUnit,setCorrectionUnit]=useState('');
  const [correctedBatch,setCorrectedBatch]=useState(''),[correctedTime,setCorrectedTime]=useState('');
  const [comparison,setComparison]=useState<{results:Score[];human_study?:string;calibration_protocol?:string;limitations?:string[]}>({results:[]});
  const lastInput=useRef(Date.now()),session=useRef(crypto.randomUUID());
  const item=catalog.find(i=>i.id===packageId),matches=catalog.filter(i=>i.dataset===dataset);

  async function request(path:string,options:RequestInit={}) {
    const response=await fetch('/api/cmo-ingestion'+path,{...options,headers:{'Content-Type':'application/json',...(token?{'X-CMO-Token':token}:{}),...options.headers}});
    if(!response.ok) {const text=await response.text(); throw new Error(text);}
    return response;
  }
  async function post(path:string,data:unknown) { return (await request(path,{method:'POST',body:JSON.stringify(data)})).json(); }
  async function refreshCatalog() {
    try {const data=await (await request('/catalog')).json(); setCatalog(data.packages);setAvailability(data.availability);setConfigNames(data.configurations);
      setComparison(await (await request('/comparison')).json());
    } catch(e) {setError('Cannot reach the ingestion API. Start the existing FastAPI application and configure the Vite proxy. '+String(e));}
  }
  useEffect(()=>{if(!embeddedRunId)void refreshCatalog();},[token,embeddedRunId]);
  useEffect(()=>{if(embeddedRunId)setToken(authToken);},[authToken,embeddedRunId]);
  useEffect(()=>{const id=embeddedRunId||new URLSearchParams(window.location.search).get('run');if(!id)return;request('/runs/'+encodeURIComponent(id)).then(r=>r.json()).then(data=>{setRun(data);if(data.package_id){setDataset(data.package_id.startsWith('sanofi-')?'sanofi':'indpensim');setPackageId(data.package_id);}}).catch(e=>setError(String(e)));},[token,embeddedRunId]);
  useEffect(()=>{setPackageId(current=>matches.some(i=>i.id===current)?current:matches.find(i=>i.condition==='unseen')?.id??matches[0]?.id??'');},[dataset,catalog]);
  useEffect(()=>{
    if(!run||!['queued','running'].includes(run.status))return;
    const timer=setInterval(()=>{request('/runs/'+run.id).then(r=>r.json()).then(setRun).catch(e=>{setError(String(e));setBusy(false);});},700);
    return ()=>clearInterval(timer);
  },[run?.id,run?.status,token]);
  useEffect(()=>{if(run&&!['queued','running'].includes(run.status))setBusy(false);},[run?.status]);

  // Only visible, focused screens with recent user activity generate heartbeat
  // intervals. Server measures elapsed time, never accepts a client duration.
  useEffect(()=>{
    if(!run||run.status!=='complete'||navigator.webdriver)return;
    const update=()=>{lastInput.current=Date.now();};
    window.addEventListener('pointerdown',update);window.addEventListener('keydown',update);window.addEventListener('scroll',update,true);
    let active=false;
    const timer=setInterval(()=>{
      const visible=document.visibilityState==='visible'&&document.hasFocus()&&Date.now()-lastInput.current<30000&&(selected!==null||layout!==null);
      const action=visible?(active?'heartbeat':'start'):'stop';
      if(visible||active)post('/runs/'+run.id+'/activity',{session_id:session.current,screen:layout?'templates':'review',action}).then(data=>setRun(r=>r?{...r,human_minutes:data.human_minutes,human_time_status:data.status}:r)).catch(()=>{});
      active=visible;
    },10000);
    return()=>{clearInterval(timer);window.removeEventListener('pointerdown',update);window.removeEventListener('keydown',update);window.removeEventListener('scroll',update,true);};
  },[run?.id,run?.status,selected?.id,layout?.fingerprint,token]);

  async function start() {
    setError('');setBusy(true);setSelected(null);setLayout(null);setPage(0);
    try {const r=await post('/runs',{package_id:packageId,configuration});setRun({...r,stages:[]});}
    catch(e){setError(String(e));setBusy(false);}
  }
  async function upload(file:File) {
    setError('');try {const r=await fetch('/api/cmo-ingestion/upload?dataset='+dataset,{method:'POST',headers:token?{'X-CMO-Token':token}:{},body:file});
      if(!r.ok)throw new Error(await r.text());const data=await r.json();setCatalog(c=>[...c,data]);setPackageId(data.id);
    }catch(e){setError(String(e));}
  }
  async function choose(m:Measurement,keepLayout=false) {
    setSelected(m);setSource(null);setPdf('');setCorrected(String(m.value??''));setCorrectionParameter(m.parameter);setCorrectionUnit(m.unit);if(!keepLayout)setLayout(null);
    setCorrectedBatch(m.batch);setCorrectedTime(m.time);
    setPdfZoom(false);
    try {if(m.source.path.toLowerCase().endsWith('.pdf')) {
      const response=await request('/runs/'+run!.id+'/pages/'+m.source_id+'/'+(m.source.page??1));
      setPdfSize([Number(response.headers.get('X-Page-Width')??1),Number(response.headers.get('X-Page-Height')??1)]);
      const blob=await response.blob();setPdf(URL.createObjectURL(blob));
    } else setSource(await (await request('/runs/'+run!.id+'/cells/'+m.id)).json());}
    catch(e){setError(String(e));}
  }
  useEffect(()=>()=>{if(pdf)URL.revokeObjectURL(pdf);},[pdf]);
  async function review(decision:string) {
    if(!run||!selected)return;setError('');
    try {await post('/runs/'+run.id+'/reviews',{measurement_id:selected.id,binding:selected.review_binding,decision,actor,reason,
      ...(decision==='correct'?{value:corrected,parameter:correctionParameter,unit:correctionUnit,batch:correctedBatch,time:correctedTime}:{})});
      const data=await (await request('/runs/'+run.id)).json();setRun(data);setSelected(null);setSource(null);setPdf('');
    }catch(e){setError(String(e));}
  }
  async function confirm() {
    if(!run||!layout)return;setError('');
    try {await post('/runs/'+run.id+'/templates',{fingerprint:layout.fingerprint,mapping:JSON.parse(mapping),actor,reason});
      setLayout(null);setError('Template version saved. Run a returning package to observe reuse. Existing measurements retain their original review status.');
    }catch(e){setError(String(e));}
  }
  async function download(format:string,wide=false) {
    if(!run)return;try {const blob=await (await request(`/runs/${run.id}/export?format=${format}&wide=${wide}`)).blob();const url=URL.createObjectURL(blob);
      const a=document.createElement('a');a.href=url;a.download=`verified-${run.id}.${format}`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    }catch(e){setError(String(e));}
  }
  const measurements=(run?.measurements??[]).filter(m=>!filter||m.status==='needs_review');
  const visible=measurements.slice(page*25,page*25+25);
  const summary=run?.summary;
  return <section className="space-y-6 text-slate-800">
    <div><p className="text-xs font-semibold uppercase tracking-widest text-emerald-700">CMO data ingestion</p>
      <h1 className="mt-2 text-3xl font-semibold">From raw package to verified data</h1>
      <p className="mt-2 max-w-3xl text-sm text-slate-600">Run the existing ingestion pipeline, inspect each value at its source, and confirm reusable mappings. Results below come from executed jobs.</p></div>
    {!embeddedRunId&&<div className="rounded-xl border bg-white p-5 space-y-4">
      <div className="flex flex-wrap gap-4 items-end">
        <label className="grid gap-1 text-xs font-medium">Dataset<select aria-label="Dataset" className={input} value={dataset} onChange={e=>setDataset(e.target.value)}><option value="indpensim">IndPenSim · simulated fermentation</option><option value="sanofi">Sanofi · synthetic reconstruction</option></select></label>
        <label className="grid gap-1 text-xs font-medium">Raw package<select aria-label="Raw package" className={input} value={packageId} onChange={e=>setPackageId(e.target.value)}>{matches.map(i=><option key={i.id} value={i.id}>{i.condition} · {i.files.length} files</option>)}</select></label>
        <label className="grid gap-1 text-xs font-medium">Extraction configuration<select aria-label="Extraction configuration" className={input} value={configuration} onChange={e=>setConfiguration(e.target.value)}>{Object.entries(configNames).filter(([c])=>!['A','B','C'].includes(c)).map(([c,name])=><option key={c} value={c}>{c==='preview'?'Diagnostic':c} · {name}</option>)}</select></label>
        <button className="rounded-lg bg-emerald-800 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-900 disabled:opacity-40" disabled={busy||!packageId} onClick={()=>void start()}>{busy?'Processing…':'Run ingestion'}</button>
        <label className={button+' cursor-pointer'}>Upload ZIP<input aria-label="Upload package" type="file" accept=".zip" className="hidden" onChange={e=>{const file=e.target.files?.[0];if(file)void upload(file);}}/></label>
      </div>
      <p className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">{item?.disclosure??'Generate benchmark packages to begin.'}</p>
      {availability[configuration]?.length>0&&<p className="text-sm text-amber-800">Unavailable: {availability[configuration].join('; ')}. Running this configuration records its unavailable status.</p>}
      <details className="text-xs"><summary>Package files and connection</summary><ul className="mt-2 list-disc pl-5">{item?.files.map(f=><li key={f.path}>{f.path}</li>)}</ul><label className="mt-3 grid gap-1 max-w-md">Local API token (if configured)<input type="password" autoComplete="off" className={input} value={token} onChange={e=>setToken(e.target.value)}/></label></details>
    </div>}
    {error&&<p role="alert" className="rounded-lg bg-amber-50 p-4 text-sm text-amber-900 whitespace-pre-wrap">{error}</p>}
    <div className="grid gap-3 md:grid-cols-4">
      {[
        ['Raw CMO package',embeddedRunId?`${run?.documents?.length??0} original files`:item?`${item.files.length} original files`:'Choose a package','Original bytes retained by SHA-256'],
        ['Automatic processing',run?.runtime_seconds!=null?`${run.runtime_seconds.toFixed(2)} seconds`:run?.status??'Awaiting run',`${summary?.model_calls??'—'} model calls`],
        ['Human interventions',summary?`${summary.needs_review} values · ${summary.open_issues} issues`:'Awaiting results',run?.human_minutes!=null?`${run.human_minutes.toFixed(2)} observed minutes · partial session`:'Human minutes: not measured'],
        ['Verified data',summary?`${summary.accepted} accepted values`:'Awaiting verification',summary?.verified_package?'Package verification complete':'Package verification required'],
      ].map(([title,value,note])=><div key={title} className="rounded-xl border bg-white p-5"><p className="text-xs font-medium text-slate-500">{title}</p><p className="mt-3 text-xl font-semibold">{value}</p><p className="mt-2 text-xs text-slate-500">{note}</p></div>)}
    </div>
    {run&&<>
      <div className="flex flex-wrap gap-2" aria-label="Pipeline progress">{stages.map(name=>{const event=run.stages.filter(s=>s.stage===name).slice(-1)[0];return <div key={name} className={'rounded-lg border px-3 py-2 text-xs '+(event?'bg-emerald-50 border-emerald-200':'bg-slate-50')}><b>{name}</b><div className="mt-1">{event?`${event.elapsed_seconds.toFixed(2)}s · ${event.state}`:'pending'}</div></div>;})}</div>
      {run.status==='unavailable'&&<p className="text-amber-800">Configuration unavailable: {run.unavailable_reasons?.join('; ')}. No extraction score was generated.</p>}
      {run.error&&<p role="alert" className="text-red-800">{run.error}</p>}
      {summary&&<>
        <div className="rounded-xl border bg-white p-4 text-sm"><b>Execution receipt</b><p className="mt-2">Auto accepted: {summary.auto_accepted} · Corrections: {summary.corrections} · Tokens in/out: {summary.input_tokens??'unknown'} / {summary.output_tokens??'unknown'} · Inference cost: {summary.inference_cost_usd==null?'unknown':`$${Number(summary.inference_cost_usd).toFixed(6)}`}</p>
          <details className="mt-2 text-xs"><summary>Actual parsers and model usage</summary>{run.documents?.map(d=><p key={d.path}>{d.path}: {d.doc_type} · {d.route.selected_backend??'error'}{d.route.fallback_used?' · fallback used':''}</p>)}<pre className="mt-2 overflow-auto">{JSON.stringify(run.model_usage,null,2)}</pre></details></div>
        {Boolean(run.extraction_reviews?.length)&&<details className="rounded-xl border bg-white p-4 text-xs"><summary>Clairic answers requiring review ({run.extraction_reviews?.length})</summary><p className="mt-2">These are unverified model responses. Null values are missing; guesses are not extracted measurements.</p><pre className="mt-2 max-h-96 overflow-auto">{JSON.stringify(run.extraction_reviews,null,2)}</pre></details>}
        <div className="flex flex-wrap gap-4 rounded-xl border bg-white p-4"><label className="grid gap-1 text-xs">Reviewer name<input aria-label="Reviewer name" className={input} value={actor} onChange={e=>setActor(e.target.value)}/></label><label className="grid flex-1 gap-1 text-xs">Review reason<input aria-label="Review reason" className={input} value={reason} onChange={e=>setReason(e.target.value)}/></label><p className="w-full text-xs text-slate-500">Local demonstration receipts record attribution. They do not provide regulated electronic signatures. Active screen time is partial observation, not evidence of completed verification time.</p></div>
        <div className="grid gap-5 lg:grid-cols-2">
          <div className="space-y-4">
            <div className="rounded-xl border bg-white p-4"><h2 className="font-semibold">Layout mappings</h2><p className="mt-1 text-xs text-slate-500">Confirm on calibration, then run returning with D. Unseen uses a different form. Changed forms remain subject to review.</p><div className="mt-3 flex flex-wrap gap-2">{run.layouts?.map(l=><button key={l.fingerprint} className={button} onClick={()=>{setLayout(l);setSelected(null);setMapping(JSON.stringify(l.mapping,null,2));}}>{l.kind} · {l.confirmed?'confirmed':'draft'}{l.template_origin==='study_protocol'?' (study fixture)':''}</button>)}</div></div>
            <div className="rounded-xl border bg-white p-4"><div className="flex items-center justify-between"><h2 className="font-semibold">Extracted values</h2><label className="text-xs"><input type="checkbox" checked={filter} onChange={e=>{setFilter(e.target.checked);setPage(0);}}/> Review only</label></div>
              <div className="mt-3 overflow-auto"><table className="w-full text-left text-xs"><thead><tr><th className="p-2">Batch / hour</th><th>Parameter</th><th>Value / unit</th><th>Status</th></tr></thead><tbody>{visible.map(m=><tr key={m.id} className={'border-t cursor-pointer hover:bg-emerald-50 '+(selected?.id===m.id?'bg-emerald-50':'')} onClick={()=>void choose(m)}><td className="p-2">{m.batch}<div className="text-slate-400">{m.time} h</div></td><td>{m.parameter}</td><td>{m.value??'invalid'} {m.unit}</td><td>{m.status}</td></tr>)}</tbody></table></div>
              <div className="mt-3 flex items-center justify-between text-xs"><button className={button} disabled={page===0} onClick={()=>setPage(p=>p-1)}>Previous</button><span>{measurements.length} values · page {page+1}</span><button className={button} disabled={(page+1)*25>=measurements.length} onClick={()=>setPage(p=>p+1)}>Next</button></div>
            </div>
          </div>
          <div className="rounded-xl border bg-white p-4 min-h-72">
            <h2 className="font-semibold">Source and verification</h2>
            {!selected&&!layout&&<p className="mt-4 text-sm text-slate-500">Choose an extracted value to inspect its original page or spreadsheet row, or open a layout mapping.</p>}
            {layout&&<div className="mt-4 space-y-3"><p className="text-sm">{layout.path} · {layout.kind} · {layout.confirmed?'confirmed':'draft'}</p><p className="text-xs">Review the source and edit column assignments before confirming.</p><button className={button} onClick={()=>{const m=run.measurements?.find(m=>m.source.path===layout.path);if(m)void choose(m,true);}}>Inspect example source</button>{Boolean(layout.decisions?.length)&&<details><summary className="text-xs">OpenAI Decisions confidence and review requirements</summary><pre className="max-h-60 overflow-auto text-xs">{JSON.stringify(layout.decisions,null,2)}</pre></details>}<textarea aria-label="Layout mapping" className={input+' h-72 w-full font-mono'} value={mapping} onChange={e=>setMapping(e.target.value)}/><button className={button} disabled={!actor.trim()||!reason.trim()} onClick={()=>void confirm()}>Confirm mapping version</button></div>}
            {selected&&<div className="mt-4 space-y-3"><p className="text-sm font-medium">{selected.parameter}: {selected.value_raw} {selected.unit_raw}</p><p className="text-xs break-all">{selected.source.path} · {selected.source.sheet?`${selected.source.sheet}!${selected.source.cell}`:selected.source.page?`page ${selected.source.page}`:`CSV row ${selected.source.row}, ${selected.source.column}`} · {selected.parser}</p><p className="text-xs text-amber-800">{selected.rule_codes.join(' · ')||'Confirmed template and source checks passed.'}</p>{selected.extraction_confidence&&<details className="text-xs"><summary>Clairic confidence, source spans and review reasons</summary><pre className="max-h-64 overflow-auto">{JSON.stringify({confidence:selected.extraction_confidence,source_spans:selected.extraction_spans,review_reasons:selected.extraction_review_reasons},null,2)}</pre></details>}
              {source&&<div className="max-h-64 overflow-auto"><table className="w-full text-xs"><tbody>{source.headers.map((h,i)=><tr key={h+i} className={h===selected.source.column?'bg-yellow-100 border-2 border-yellow-500':'border-b'}><th className="p-2 text-left">{h}</th><td className="p-2">{String(source.values[i]??'')}</td></tr>)}</tbody></table></div>}
              {pdf&&<><button className={button} onClick={()=>setPdfZoom(z=>!z)}>{pdfZoom?'Fit page':'Zoom source page'}</button><div className="max-h-[520px] overflow-auto rounded border bg-slate-100"><div className="relative" style={{width:pdfZoom?pdfSize[0]*1.5:'100%'}}><img alt="Original PDF source page" src={pdf} className="h-auto w-full"/>{selected.source.region&&<div aria-label="Source bounding box" className="pointer-events-none absolute border-2 border-amber-500 bg-amber-200/20" style={{left:`${100*Math.min(selected.source.region[0],selected.source.region[2])/pdfSize[0]}%`,top:`${100*(selected.source.region[1]>selected.source.region[3]?pdfSize[1]-selected.source.region[1]:selected.source.region[1])/pdfSize[1]}%`,width:`${100*Math.abs(selected.source.region[2]-selected.source.region[0])/pdfSize[0]}%`,height:`${100*Math.abs(selected.source.region[3]-selected.source.region[1])/pdfSize[1]}%`}}/>}</div></div></>}
              {!selected.source.page&&selected.source.path.endsWith('.pdf')&&<p className="text-xs text-amber-800">Parser supplied no precise page. Locate the record in the original before accepting.</p>}
              <div className="flex flex-wrap gap-2"><button className={button} disabled={!actor.trim()||!reason.trim()} onClick={()=>void review('accept')}>Accept source value</button><button className={button} disabled={!actor.trim()||!reason.trim()} onClick={()=>void review('reject')}>Reject</button></div>
              <details><summary className="text-sm cursor-pointer">Correct value, parameter, batch or time</summary><div className="mt-2 grid grid-cols-2 gap-2"><label className="grid gap-1 text-xs">Value<input aria-label="Corrected value" className={input} value={corrected} onChange={e=>setCorrected(e.target.value)}/></label><label className="grid gap-1 text-xs">Parameter<input aria-label="Corrected parameter" className={input} value={correctionParameter} onChange={e=>setCorrectionParameter(e.target.value)}/></label><label className="grid gap-1 text-xs">Unit<input aria-label="Corrected unit" className={input} value={correctionUnit} onChange={e=>setCorrectionUnit(e.target.value)}/></label><label className="grid gap-1 text-xs">Batch<input aria-label="Corrected batch" className={input} value={correctedBatch} onChange={e=>setCorrectedBatch(e.target.value)}/></label><label className="grid gap-1 text-xs">Process hour<input aria-label="Corrected process hour" className={input} value={correctedTime} onChange={e=>setCorrectedTime(e.target.value)}/></label></div><button className={button+' mt-2'} disabled={!actor.trim()||!reason.trim()} onClick={()=>void review('correct')}>Save correction with audit receipt</button></details>
            </div>}
          </div>
        </div>
        <div className="rounded-xl border bg-white p-4"><h2 className="font-semibold">Missing information and conflicts</h2><div className="mt-3 max-h-64 overflow-auto space-y-2">{run.issues?.length?run.issues.map(i=><div key={i.id} className="flex flex-wrap justify-between gap-2 border-b pb-2 text-xs"><p><b>{i.rule_code}</b> · {i.path} · {i.status}{i.message?' · '+i.message:''}</p>{i.status==='open'&&<button className={button} disabled={!actor.trim()||!reason.trim()} onClick={async()=>{try{await post('/runs/'+run.id+'/issues',{issue_id:i.id,actor,reason});setRun(await (await request('/runs/'+run.id)).json());}catch(e){setError(String(e));}}}>Record disposition</button>}</div>):<p className="text-xs text-slate-500">No package validation issues reported. Individual draft mappings and OCR still require review.</p>}</div></div>
        <div className="rounded-xl border bg-white p-4"><h2 className="font-semibold">Export accepted measurements</h2><p className="mt-1 text-xs text-slate-500">Exports include accepted values and source references. {summary.verified_package?'All review work is resolved.':'This is a partial export; the package still requires verification.'}</p><div className="mt-3 flex gap-2"><button className={button} onClick={()=>void download('csv')}>CSV · long</button><button className={button} onClick={()=>void download('csv',true)}>CSV · wide</button><button className={button} onClick={()=>void download('xlsx')}>Excel</button></div></div>
      </>}
    </>}
    {!embeddedRunId&&<div className="rounded-xl border bg-white p-5"><div className="flex items-center justify-between"><h2 className="text-lg font-semibold">Executed benchmark comparison</h2><button className={button} onClick={()=>void refreshCatalog()}>Refresh report</button></div><p className="mt-2 text-sm text-slate-500">{comparison.human_study??'Generate an evaluation report to compare configurations.'}</p><p className="mt-1 text-xs text-slate-500">{comparison.calibration_protocol}</p>
      <div className="mt-4 overflow-auto"><table className="w-full whitespace-nowrap text-left text-xs"><thead><tr>{['Config','Dataset','Condition','Status','Recall','Value + unit','Provenance','Classification','Mapping','Defects','Auto accepted','Wrong auto','Human min','Seconds','Calls','Cost'].map(h=><th key={h} className="p-2">{h}</th>)}</tr></thead><tbody>{comparison.results.map(r=><tr key={[r.configuration,r.dataset,r.condition].join('-')} className="border-t" title={r.reasons?.join('; ')}>{[r.configuration,r.dataset,r.condition,r.status,percent(r.field_recall),percent(r.value_and_unit_accuracy),percent(r.source_provenance_accuracy),percent(r.classification_accuracy),percent(r.mapping_accuracy),percent(r.defect_detection_rate),percent(r.auto_acceptance_rate),percent(r.incorrect_auto_acceptance_rate),r.human_minutes==null?'not measured':r.human_minutes.toFixed(2),r.end_to_end_seconds?.toFixed(2)??'—',r.model_calls??'—',r.inference_cost_usd==null?'unknown':`$${r.inference_cost_usd.toFixed(6)}`].map((v,i)=><td key={i} className="p-2">{v}</td>)}</tr>)}</tbody></table></div>
      <p className="mt-3 text-xs text-slate-500">Targets: ≥98% recall · ≥99% auto-accepted accuracy · ≥80% acceptance after confirmation · ≤15 human minutes. Targets are not measured results. Diagnostic is a separate local baseline; unavailable configurations have no extraction score.</p>
      {comparison.limitations&&<details className="mt-3 text-xs"><summary>Evaluation limitations</summary><ul className="mt-2 list-disc pl-5">{comparison.limitations.map(s=><li key={s}>{s}</li>)}</ul></details>}
    </div>}
  </section>;
}
