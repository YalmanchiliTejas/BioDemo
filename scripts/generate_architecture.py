from pathlib import Path
from xml.etree import ElementTree as E
from html import escape
import textwrap, json

import argparse
import tempfile

parser = argparse.ArgumentParser(description='Generate the editable Sievance architecture with checked orthogonal routes.')
parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1] / 'sievance-architecture.drawio')
parser.add_argument('--preview-dir', type=Path, default=Path(tempfile.gettempdir()) / 'sievance-diagram-review')
args = parser.parse_args()
OUT = args.output
PREVIEW = args.preview_dir; PREVIEW.mkdir(parents=True, exist_ok=True)
C={'service':('#EFF8F5','#80AF9E'),'agent':('#DDF1EC','#458E7C'),'store':('#EEF3FA','#8BA4C4'),'human':('#FFF6E7','#C7A66A'),'external':('#F4F6F7','#A4B1B7')}
mx=E.Element('mxfile',host='app.diagrams.net',type='device',version='24.7.17',compressed='false')
pages=[]
class Page:
 def __init__(self,title,subtitle,note):
  self.title=title;self.subtitle=subtitle;self.note=note;self.nodes={};self.edges=[];self.lanes=[]
  self.index=len(pages)+1;pages.append(self)
 def lane(self,row,title):
  title=title.split('  ·')[0].replace('PERSISTENCE & FINALIZATION','EVIDENCE & REPORTS').replace('CLOUD INVESTIGATION JOBS','CLOUD INVESTIGATION').replace('LIFE-SCIENCES PLATFORM','PLATFORM DEPLOYMENT')
  self.lanes.append((row,title))
 def n(self,id,col,row,title,body,src,kind='service',overview=False):
  w=300 if overview else 340;x=60+col*(340 if overview else 440);y=220+row*280
  tl=textwrap.wrap(title, width=31 if overview else 35)
  bl=[]
  for line in body.split('\n'):bl+=textwrap.wrap(line,width=36 if overview else 42)
  assert len(tl)<=2,(title,tl)
  assert len(bl)<=4,(title,bl)
  ty=18;by=ty+len(tl)*20+12
  assert by+len(bl)*19<=145,(title,by,bl)
  self.nodes[id]={'id':id,'x':x,'y':y,'w':w,'h':160,'title':tl,'body':bl,'source':src,'kind':kind,'body_y':by}
 def e(self,a,b,ports='RL',via=(),optional=False):
  def pt(n,s):
   q=self.nodes[n];x,y,w,h=q['x'],q['y'],q['w'],q['h']
   return {'R':(x+w,y+h/2),'L':(x,y+h/2),'T':(x+w/2,y),'B':(x+w/2,y+h),'t':(x+w*.75,y)}[s]
  coords=[pt(a,ports[0]),*via,pt(b,ports[1])]
  for u,v in zip(coords,coords[1:]):
   assert u[0]==v[0] or u[1]==v[1],(self.title,a,b,u,v)
   for id,n in self.nodes.items():
    if id in (a,b):continue
    x,y,w,h=n['x'],n['y'],n['w'],n['h']
    if u[0]==v[0]:bad=x+1<u[0]<x+w-1 and max(min(u[1],v[1]),y+1)<min(max(u[1],v[1]),y+h-1)
    else:bad=y+1<u[1]<y+h-1 and max(min(u[0],v[0]),x+1)<min(max(u[0],v[0]),x+w-1)
    assert not bad,(self.title,a,b,'route crosses',id)
  self.edges.append((a,b,ports,list(via),optional,coords))

p=Page('01  System overview','The main paths through the current agent, ingestion, and evaluation code.','Different execution paths reuse components; they do not all run in every deployment. Detailed pages preserve the boundaries between source stores, platform records, Prime sessions, and bounded scientific workflows.')
p.lane(0,'PRODUCT PATH  ·  Source data to reviewable work')
p.n('source',0,0,'Existing sources','Files and approved repositories\nMES, LIMS, QMS, ERP, historians','External systems and authorized input packages','external',True)
p.n('ingest',1,0,'Acquire & verify','Files / live CDMO records\nShared verification checks','src/ingestion/verification.py; src/lifesci/source_verification.py',overview=True)
p.n('evidence',2,0,'Evidence & state','Scoped source store\nVersioned platform evidence','src/manufacturing_data/store.py; src/lifesci/store.py; src/lifesci/evidence.py','store',True)
p.n('agent',3,0,'Agent execution','Prime investigations\nBounded scientific workflows','src/prime_runtime/; src/lifesci/process_engineering/conversation.py','agent',True)
p.n('review',4,0,'Reviewable results','Source-linked findings\nDrafts, uncertainty and next steps','src/workflows/; src/lifesci/quality.py','human',True)
for a,b in [('source','ingest'),('ingest','evidence'),('evidence','agent'),('agent','review')]:p.e(a,b)
p.lane(1,'SUPPORTING SERVICES  ·  Access, background work, models, and authorization')
p.n('identity',1,1,'Identity & permissions','Supabase / OIDC on the API\nStored tenant, site and role access','src/lifesci/identity.py; src/lifesci/supabase_auth.py',overview=True)
p.n('runtime',2,1,'Mission runtime','Obligations and resumable work\nPolling, timers and checkpoints','src/lifesci/missions.py; src/lifesci/runtime.py',overview=True)
p.n('models',3,1,'Models & task gateway','SDK provider configuration\nGateway routes and task budgets','src/prime_runtime/provider_config.mjs; src/lifesci/gateway/',overview=True)
p.n('actions',4,1,'Approved actions','Human decision → action intent\nAuthorization recheck → dispatch','src/lifesci/actions.py; src/lifesci/connectors.py','human',True)
p.e('identity','ingest','TB');p.e('runtime','models');p.e('models','agent','TB');p.e('review','actions','BT',optional=True)
p.lane(2,'EVALUATION PATH  ·  Independent of the product request path above')
p.n('protocol',0,2,'Frozen case protocol','Inputs, as-of cutoff and budgets\nHeld-out references stay private','benchmarks/common/case_protocol.py','external')
p.n('isolation',1,2,'Audit & isolate','Stage authorized source bytes\nVerify OS-level access denials','benchmarks/common/case_audit.py; isolated_runner.py')
p.n('reuse',2,2,'Run the shared agent','Full-agent adapter invokes\nthe same Prime execution harness','benchmarks/common/full_agent_adapter.py','agent')
p.n('scores',3,2,'Score & retain receipts','Independent scores and review\nOutput hashes, traces, artifacts','benchmarks/common/case_runner.py; objective_scores.py; quality.py','store')
for a,b in [('protocol','isolation'),('isolation','reuse'),('reuse','scores')]:p.e(a,b)

p=Page('02  Shared ingestion & verification','File delivery and live CDMO acquisition converge on the same deterministic verification rules.','File parsing is an extraction capability within delivery intake. Live structured records enter after extraction. Both call src/ingestion/verification.py. Review/storage adapters retain source-specific provenance. Open polls never claim batch completeness; accepted live measurement snapshots use the existing agent dataset contract.')
p.lane(0,'ACQUIRE & EXTRACT')
p.n('files',0,0,'Uploaded / delivered files','Files, ZIPs and shared folders\nOriginal source bytes retained','src/manufacturing_data/cmo/api.py; src/manufacturing_data/ingest.py','external')
p.n('parse',1,0,'Parse & extract','Inventory / classify documents\nNative readers or configured OCR\nMap extracted observations','src/manufacturing_data/ingest.py; src/manufacturing_data/cmo/pipeline.py')
p.n('systems',2,0,'Live CDMO systems','MES, LIMS, QMS, historian\nREST, file, webhook, MQTT, OPC UA','src/lifesci/connectors.py','external')
p.n('read',3,0,'Read structured records','Authorized incremental collection\nPreserve payloads and revisions\nApply the configured field map','src/lifesci/integrations.py; src/lifesci/connectors.py')
p.e('files','parse');p.e('systems','read')
p.lane(1,'SHARED VERIFICATION')
p.n('originals',0,1,'Originals & provenance','Source hashes / IDs / revisions\nTenant, site and source group\nCheckpoints remain transport-owned','src/manufacturing_data/store.py; src/lifesci/evidence.py','store')
p.n('observations',1,1,'Canonical observations','Batch / time / quantity / raw unit\nOriginal location / evidence refs\nNonmeasurement fields retained','src/ingestion/schema.py; src/lifesci/source_verification.py')
p.n('checks',2,1,'One verification engine','Normalize units and check ranges\nDetect conflicts / row issues\nApply collection completeness policy','src/ingestion/verification.py','agent')
p.n('review',3,1,'Review & acceptance','Pending records remain separate\nNamed review reason and revision\nCorrections reset stale decisions','src/manufacturing_data/cmo/pipeline.py; src/lifesci/source_verification.py','human')
p.e('parse','observations','BT')
p.e('read','observations','Bt',[(1550,420),(755,420)])
p.e('observations','originals','LR');p.e('observations','checks');p.e('checks','review')
p.lane(2,'PUBLISH & CONSUME')
p.n('policy',0,2,'Source-aware policy','Files: complete-delivery checks\nLive: open incremental collection\nCross-poll checks within site / CDMO','src/ingestion/verification.py; src/lifesci/source_verification.py')
p.n('publish',1,2,'Publish accepted snapshot','Block pending / stale / bad values\nPin source and review revisions\nRetain rejection receipts','src/lifesci/source_verification.py; src/manufacturing_data/cmo/api.py')
p.n('dataset',2,2,'Shared dataset contract','File and live measurement snapshots\nSame authorized dataset reader\nCheck basis before consumption','src/lifesci/cmo_datasets.py','store')
p.n('agent',3,2,'Agent / scientific consumers','Source-linked accepted values\nCoverage / limitations stay visible\nChanged basis blocks old snapshots','src/lifesci/process_engineering/conversation.py','agent')
p.e('review','publish','BT',[(1550,700),(670,700)])
p.e('publish','dataset');p.e('dataset','agent')

p=Page('03  Prime execution harness','The open-ended investigation loop: host orchestration, SDK reasoning, bounded evidence tools, and verified submission.','Only the lead submits the final report. Specialists save subreports. Sessions, checkpoints, source verification and review states remain separate. The external Prime SDK bundle and configured model provider must be available.')
p.lane(0,'SESSION START  ·  Python host launches the Node SDK session')
p.n('request',0,0,'Investigation request','Objective, incident ID and scope\nAs-of cutoff and evidence IDs','benchmarks/common/full_agent_adapter.py; src/cloud_backend/agent.py')
p.n('host',1,0,'Python harness','Incident lock and session paths\nDeadlines, tool limits and logs','src/prime_runtime/harness.py','agent')
p.n('sdk',2,0,'Prime SDK host','Load SDK and required skills\nCreate / resume agent session','src/prime_runtime/sdk_runner.mjs','agent')
p.n('provider',3,0,'Model provider','SDK model registry and auth\nProject provider configuration','src/prime_runtime/provider_config.mjs','external')
for a,b in [('request','host'),('host','sdk'),('sdk','provider')]:p.e(a,b)
p.lane(1,'REASONING & TOOLS  ·  Evidence access stays behind the scoped bridge')
p.n('tools',0,1,'Evidence & analysis tools','Inspect, query, search, verify\nSource regions and context\nMetrics and series alignment','src/manufacturing_data/tools.py')
p.n('bridge',1,1,'ManufacturingBridge','Scoped tool dispatch and budget\nWork queue and allocations\nProgress / report checkpoints','src/prime_runtime/bridge.py; coordination.py','agent')
p.n('lead',2,1,'Lead + IPython','Reason over scoped evidence\nCoordinate work and repairs\nCompaction / lifecycle controls','src/prime_runtime/sdk_runner.mjs; investigation_lifecycle.mjs','agent')
p.n('child',3,1,'Specialist sessions','Native SDK child agents\nBounded work allocations\nReturn specialist subreports','src/prime_runtime/coordination.py; sdk_runner.mjs','agent')
p.e('host','bridge','BT');p.e('sdk','lead','BT');p.e('lead','bridge','LR');p.e('bridge','tools','LR');p.e('lead','child')
p.lane(2,'PERSISTENCE & FINALIZATION  ·  Traceable evidence, explicit report state')
p.n('store',0,2,'Private source store','Originals and source metadata\nAuthorized partitions only\nScope and time-filtered reads','src/manufacturing_data/store.py; retrieval.py','store')
p.n('verify',1,2,'Verify & submit','Assemble and validate report\nCheck citations / claims / math\nPreserve unresolved limitations','src/prime_runtime/bridge.py; src/workflows/report_verification.py','human')
p.n('workflow',2,2,'Investigation workflow','Report, hypotheses and triage\nEvidence requests / follow-up\nIndependent human review','src/workflows/manufacturing.py','store')
p.n('state',3,2,'State & telemetry','Blackboards and SDK sessions\nCheckpoints and tool traces\nRoot / child usage scope noted','src/state/; src/prime_runtime/telemetry.py','store')
for a,b in [('tools','store'),('bridge','verify'),('child','state')]:p.e(a,b,'BT')
p.e('verify','workflow');p.e('workflow','state')

p=Page('04  Platform runtime & actions','Persistent missions, bounded scientific planning, model/task execution, and the human authorization boundary.','Mission obligations call configured gateway tasks; they are not automatically Prime sessions. Temporal is an optional configured scheduler. Simulations and recommendations do not themselves authorize manufacturing changes.')
p.lane(0,'PERSISTENT WORK  ·  API commands and durable mission state')
p.n('api',0,0,'Authenticated API','Resolve tenant / actor / sites\nCheck stored roles and grants','src/lifesci/api.py; identity.py')
p.n('domains',1,0,'Domain services','Quality, lab and procedures\nExecution, transfers, partners\nEvidence and ownership','src/lifesci/container.py')
p.n('missions',2,0,'Manufacturing missions','Objective, owner and obligations\nPending events and checkpoints\nRemaining work persists','src/lifesci/missions.py','store')
p.n('scheduler',3,0,'Runtime / scheduler','Recoverable event pump\nTimers, leases and polling\nOptional Temporal worker','src/lifesci/runtime.py; orchestration/')
for a,b in [('api','domains'),('domains','missions'),('missions','scheduler')]:p.e(a,b)
p.lane(1,'BOUNDED SCIENTIFIC WORK  ·  Host-registered operations')
p.n('planner',0,1,'Scientific planner','Owner-scoped conversation\nPropose a bounded DAG','src/lifesci/process_engineering/conversation.py','agent')
p.n('flows',1,1,'Versioned flow runtime','Explicit dependencies / inputs\nResumable node results\nNo arbitrary uploaded code','src/lifesci/flows.py; data_worker.py')
p.n('gateway',2,1,'Task gateway','Route and authorize tasks\nBudgets, checks and retries\nPersist model/task run receipts','src/lifesci/gateway/','agent')
p.n('handlers',3,1,'Execution adapters','Registered scientific handlers\nConfigured model providers\nDrafts and simulation results','src/lifesci/gateway/providers.py; bioprocess/; lyophilization/')
for a,b in [('planner','flows'),('flows','gateway'),('gateway','handlers')]:p.e(a,b)
p.e('api','planner','BT');p.e('missions','gateway','BT')
p.lane(2,'CONSEQUENTIAL ACTIONS  ·  Each step is independently recorded')
p.n('proposal',0,2,'Proposed action','Rationale, owner and evidence\nExpected result and constraints','src/lifesci/actions.py','human')
p.n('approval',1,2,'Approval → intent','Human decision / signature\nExact approved action version\nApproval is not execution','src/lifesci/actions.py; records.py','human')
p.n('dispatch',2,2,'Recheck & dispatch','Current evidence / permissions\nAuthoritative system ownership\nReconcile delivery status','src/lifesci/actions.py; ownership.py; connectors.py')
p.n('target',3,2,'Owning system + outcome','Explicitly enabled operations\nConfirmed / failed / unknown\nObserve effectiveness separately','External systems of record','external')
for a,b in [('proposal','approval'),('approval','dispatch'),('dispatch','target')]:p.e(a,b,optional=(a=='dispatch'))

p=Page('05  Full-agent evaluation harness','The evaluation harness controls inputs, isolation, scoring and reproducibility; the Prime harness controls the investigation.','Hidden references are supplied only to scorers. Failed source or permission audits withhold scores. Manual/incumbent arms require observed workflows. Current OS-level full-agent isolation uses macOS sandbox-exec.')
p.lane(0,'PREPARE & ISOLATE  ·  Freeze exactly what the agent may see')
p.n('protocol',0,0,'Frozen case protocol','Objective, inputs and as-of\nBudgets, conditions and policy','benchmarks/common/case_protocol.py','external')
p.n('audit',1,0,'Preflight audits','Check source / version manifests\nCheck provenance and leakage\nStop invalid trials','benchmarks/common/case_audit.py; case_runner.py')
p.n('stage',2,0,'Staged agent inputs','Only authorized source bytes\nOwned runtime workspace\nReferences stay outside','benchmarks/common/input_store.py; case_runner.py')
p.n('isolation',3,0,'Isolated worker','OS filesystem restrictions\nDenied-read probes / canaries\nInherited child restrictions','benchmarks/common/isolated_runner.py; agent_worker.py')
for a,b in [('protocol','audit'),('audit','stage'),('stage','isolation')]:p.e(a,b)
p.lane(1,'EXECUTE  ·  Common adapter with a full-agent comparison arm')
p.n('modes',0,1,'Common agent interface','Conventional / retrieval LLM\nFull RLM; rule baselines\nEach arm explicitly labeled','benchmarks/common/agent_adapter.py')
p.n('full',1,1,'Full-agent adapter','Ingest → store → workflow\nSet evaluation budgets\nRun existing Prime harness','benchmarks/common/full_agent_adapter.py','agent')
p.n('prime',2,1,'Shared Prime runtime','Same host, bridge and SDK\nIsolated settings / resources\nEvaluation claim-ledger checks','src/prime_runtime/','agent')
p.n('output',3,1,'Output + integrity audit','Freeze source-linked output\nRehash staged source bytes\nRetain execution trace','benchmarks/common/case_runner.py; trace.py','store')
for a,b in [('modes','full'),('full','prime'),('prime','output')]:p.e(a,b)
p.e('isolation','modes','BT',[(1550,420),(230,420)])
p.lane(2,'SCORE & REVIEW  ·  Evaluator-only knowledge stays on this side')
p.n('hidden',0,2,'Hidden references','Answer keys and held-out truth\nRubrics / task-specific targets\nNever valid agent evidence','Benchmark ground-truth and reference assets','human')
p.n('score',1,2,'Independent scoring','Objective and numerical checks\nCitation and quality measures\nScore only when audits pass','benchmarks/common/objective_scores.py; quality.py')
p.n('review',2,2,'Blinded human review','Standard report view\nDecisions bound to output hash\nRecheck integrity on review','benchmarks/common/case_runner.py','human')
p.n('receipts',3,2,'Reproducibility receipts','Run / source / code hashes\nOutput, trace and artifacts\nIncomplete / untested labels','backend/results/evaluation/','store')
for a,b in [('hidden','score'),('score','review'),('review','receipts')]:p.e(a,b)
p.e('output','score','BT',[(1550,700),(670,700)])

p=Page('06  Restricted scientific experiments','Matched A/B tool-access studies reuse the SDK/provider, with a deliberately smaller tool surface than a full investigation.','These experiments do not exercise the whole autonomous workflow. Numerical analysis has a separately probed sandbox. One frozen submission is scored against hidden outcomes. Scientific tools return predictions, not source observations or manufacturing approvals.')
p.lane(0,'EXPERIMENT SETUP  ·  Frozen packet and matched settings')
p.n('packet',0,0,'Frozen public packet','Visible observations and cutoff\nAllowed actions / forecast targets\nHidden outcomes kept separate','benchmarks/physics_value/; external_simulators/','external')
p.n('runner',1,0,'Matched experiment runner','Per-case A/B arms and budgets\nSame model / common evidence\nIsolated scratch and receipts','*/run_agents.py')
p.n('sdk',2,0,'Restricted SDK session','Enumerated JSON-line host tools\nNo native kernel / child agents\nNo shell, browser or memories','*/sdk_experiment.mjs','agent')
p.n('model',3,0,'Configured provider','Shared SDK provider setup\nMatched model output ceiling\nExplicit usage scope','src/prime_runtime/provider_config.mjs','external')
for a,b in [('packet','runner'),('runner','sdk'),('sdk','model')]:p.e(a,b)
p.lane(1,'TREATMENTS & TOOLS  ·  The protocol defines exactly what differs')
p.n('a',0,1,'Arm A: common evidence','Public source observations\nAllowed numerical analysis\nNo supplied model tool','Experiment-specific treatment definitions','agent')
p.n('host',1,1,'Common host tools','Inspect allowed packet\nRequest permitted observations\nBounded numerical analysis','Host / HostTools in */run_agents.py')
p.n('b',2,1,'Arm B: added model access','Same task and common evidence\nAdditional declared process model\nModel assumptions stay visible','public_models.py; treatments.py','agent')
p.n('models',3,1,'Process model tools','Physics pilot / external simulators\nCHO held-out forecasting\nExact models vary by protocol','physics_value/; external_simulators/')
p.e('sdk','host','BT',[(1110,420),(670,420)]);p.e('host','a','LR');p.e('host','b');p.e('b','models')
p.lane(2,'SUBMIT & SCORE  ·  Immutable answers and independent evaluation')
p.n('numeric',0,2,'Numerical sandbox','Probe filesystem / network denial\nExclude credentials / hidden data\nNot a whole-host security proof','benchmarks/physics_value/research_sandbox.py')
p.n('submit',1,2,'Immutable submission','Prediction / action / rationale\nFreeze submit_decision once\nNo revision after scoring feedback','*/sdk_experiment.mjs; run_agents.py')
p.n('score',2,2,'Hidden-side scoring','Prediction / outcome objective\nHeld-out outcome separation\nNo real equipment operations','physics_value/evaluate.py; external_simulators/experiment.py')
p.n('results',3,2,'Results & receipts','Frozen answers / tool history\nHashes and isolation probes\nPer-arm traces and reports','backend/results/; benchmarks/assets/','store')
p.e('host','numeric','BT',[(670,700),(230,700)]);p.e('host','submit','BT');p.e('submit','score');p.e('score','results')

p=Page('07  Deployment & trust boundaries','Implemented deployment options, shown as separate lanes rather than one claimed live infrastructure topology.','Code/configuration snapshot: shared source-verification implementation, 30 Oct 2026. Deployment readiness was not verified. Source-file references are attached as component tooltips / metadata. No credentials or customer data are included.')
p.lane(0,'LIFE-SCIENCES PLATFORM  ·  Persistent API host or Lambda deployment')
p.n('web',0,0,'Static Next.js frontend','Supabase session in browser\nBearer API requests\nPublic build configuration only','frontend/next.config.mjs; lib/auth.ts','external')
p.n('api',1,0,'Authenticated API host','Supabase / OIDC verification\nTenant / role / site boundaries\nOptional services by deployment','src/lifesci/api.py; deploy/lifesci/; deploy/aws/')
p.n('data',2,0,'Platform data + originals','PostgreSQL domain / CMO records\nPrivate evidence object storage\nSQLite / local storage for dev','src/lifesci/store.py; cmo/persistence.py; cmo/evidence.py','store')
p.n('runtime',3,0,'Background runtime','Host loop or scheduled Lambda tick\nOptional Temporal / data worker\nPersistent host for MQTT / OPC UA','src/lifesci/runtime.py; tasks.py; orchestration/')
p.e('web','api');p.e('api','data');p.e('api','runtime','BB',[(670,420),(1550,420)])
p.lane(1,'CLOUD INVESTIGATION JOBS  ·  Separate trusted control plane')
p.n('cloudapi',0,1,'Investigation control plane','OIDC / tenant / project access\nDurable job admission\nControl-plane database','src/cloud_backend/api.py; store.py')
p.n('dispatch',1,1,'Trusted Docker dispatcher','Lease / fencing and pinned image\nOwns Docker socket\nPer-job proxy and limits','src/cloud_backend/dispatcher.py')
p.n('agent',2,1,'One agent container per job','Prime bundle baked into image\nNo database or broad cloud keys\nEphemeral private work directory','src/cloud_backend/agent.py','agent')
p.n('objects',3,1,'Encrypted object artifacts','Version-pinned input ZIP\nObject-specific signed URLs\nHashed input / encrypted output','src/cloud_backend/crypto.py; dispatcher.py','store')
for a,b in [('cloudapi','dispatch'),('dispatch','agent'),('agent','objects')]:p.e(a,b)
p.lane(2,'SHARED EXECUTION  ·  Reused code does not merge the control planes')
p.n('workspace',0,2,'Private agent workspace','ManufacturingStore / blackboards\nScoped, time-filtered evidence\nEvaluation adds OS isolation','src/manufacturing_data/; src/state/','store')
p.n('prime',1,2,'Prime implementation','Python host → SDK reasoning\nScoped bridge → verified report\nCloud / evaluation reuse this','src/prime_runtime/','agent')
p.n('provider',2,2,'Model / compute boundary','Server-side provider credentials\nConfigured SDK / gateway routes\nUnavailable routes stay explicit','src/prime_runtime/provider_config.mjs; src/lifesci/gateway/','external')
p.n('human',3,2,'Human authorization','Findings remain reviewable\nApproval separate from execution\nNo implied GxP validation','src/workflows/; src/lifesci/actions.py','human')
p.e('workspace','prime');p.e('prime','provider');p.e('provider','human',optional=True)

# Native draw.io geometry and matching SVG previews use exactly the same node and route data.
svg_ns='http://www.w3.org/2000/svg'
render_manifest=[]
def svgtext(x,y,lines,size=13,weight='normal',fill='#24433F',line=19):
 return f'<text x="{x}" y="{y}" font-family="Arial, Helvetica, sans-serif" font-size="{size}" font-weight="{weight}" fill="{fill}">'+''.join(f'<tspan x="{x}" dy="{0 if i==0 else line}">{escape(s)}</tspan>' for i,s in enumerate(lines))+'</text>'
for p in pages:
 d=E.SubElement(mx,'diagram',id=f'page-{p.index}',name=p.title)
 m=E.SubElement(d,'mxGraphModel',dx='1800',dy='1140',grid='1',gridSize='10',guides='1',tooltips='1',connect='1',arrows='1',fold='1',page='1',pageScale='1',pageWidth='1800',pageHeight='1140',math='0',shadow='0')
 r=E.SubElement(m,'root');E.SubElement(r,'mxCell',id='0');E.SubElement(r,'mxCell',id='1',parent='0')
 svg=[f'<svg xmlns="{svg_ns}" width="1800" height="1140" viewBox="0 0 1800 1140">','<rect width="1800" height="1140" fill="white"/>','<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="8" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 Z" fill="#6A837B"/></marker></defs>']
 def txt(id,lines,x,y,w,h,size=13,bold=False,parent='1',color='#24433F',spacing=0):
  c=E.SubElement(r,'mxCell',id=id,value='\n'.join(lines),style=f'text;html=0;strokeColor=none;fillColor=none;align=left;verticalAlign=top;whiteSpace=wrap;overflow=visible;spacing={spacing};fontFamily=Helvetica;fontSize={size};fontStyle={int(bold)};fontColor={color};',vertex='1',parent=parent,connectable='0')
  E.SubElement(c,'mxGeometry',x=str(x),y=str(y),width=str(w),height=str(h),**{'as':'geometry'})
 txt('title',[p.title],60,32,1680,45,28,True);svg.append(svgtext(60,61,[p.title],28,'bold',line=34))
 txt('subtitle',[p.subtitle],60,90,1680,32,14,color='#60756F');svg.append(svgtext(60,107,[p.subtitle],14,fill='#60756F'))
 legend='Teal: services / agents     Blue: stored data     Amber: human review     Gray: external systems     Dashed: conditional / optional'
 txt('legend',[legend],60,130,1680,25,12,color='#71847E');svg.append(svgtext(60,146,[legend],12,fill='#71847E'))
 for row,label in p.lanes:
  y=180+row*280;txt(f'lane-{row}',[label],60,y,1680,24,12,True,color='#446A5C');svg.append(svgtext(60,y+15,[label],12,'bold','#446A5C'))
  svg.append(f'<line x1="60" y1="{y+26}" x2="1720" y2="{y+26}" stroke="#E1E9E4"/>')
 # Explicit routing: every edge is a straight orthogonal segment or a specified polyline.
 for i,(a,b,ports,via,optional,coords) in enumerate(p.edges):
  anchors={'R':('1','0.5'),'L':('0','0.5'),'T':('0.5','0'),'B':('0.5','1'),'t':('0.75','0')};ex,ey=anchors[ports[0]];ix,iy=anchors[ports[1]]
  sty=f'noEdgeStyle=1;edgeStyle=none;rounded=0;html=0;endArrow=block;endSize=7;endFill=1;strokeColor=#6A837B;strokeWidth=1.6;exitX={ex};exitY={ey};exitPerimeter=0;entryX={ix};entryY={iy};entryPerimeter=0;'+('dashed=1;dashPattern=6 4;' if optional else '')
  c=E.SubElement(r,'mxCell',id=f'edge-{i}',value='',style=sty,edge='1',parent='1',source=a,target=b)
  g=E.SubElement(c,'mxGeometry',relative='1',**{'as':'geometry'})
  if via:
   arr=E.SubElement(g,'Array',**{'as':'points'})
   for x,y in via:E.SubElement(arr,'mxPoint',x=str(x),y=str(y))
  path='M'+' L'.join(f'{x},{y}' for x,y in coords)
  svg.append(f'<path d="{path}" fill="none" stroke="#6A837B" stroke-width="1.6" marker-end="url(#arrow)"'+(' stroke-dasharray="6 4"' if optional else '')+'/>')
 for id,n in p.nodes.items():
  x,y,w,h=n['x'],n['y'],n['w'],n['h'];fill,stroke=C[n['kind']]
  obj=E.SubElement(r,'object',id=id,label='',tooltip=n['source'],sourceFiles=n['source'])
  c=E.SubElement(obj,'mxCell',style=f'rounded=1;whiteSpace=wrap;html=0;arcSize=8;fillColor={fill};strokeColor={stroke};strokeWidth=1.25;container=0;collapsible=0;',vertex='1',parent='1')
  E.SubElement(c,'mxGeometry',x=str(x),y=str(y),width=str(w),height=str(h),**{'as':'geometry'})
  txt(id+'-title',n['title'],18,18,w-36,len(n['title'])*21,16,True,parent=id)
  txt(id+'-body',n['body'],18,n['body_y'],w-36,len(n['body'])*20,13,parent=id,color='#526B62')
  svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="9" fill="{fill}" stroke="{stroke}" stroke-width="1.25"/>')
  svg.append(svgtext(x+18,y+34,n['title'],16,'bold',line=20));svg.append(svgtext(x+18,y+n['body_y']+14,n['body'],13,fill='#526B62',line=19))
 note_lines=textwrap.wrap(p.note,width=190)
 txt('note',note_lines,60,1000,1660,75,12,color='#71847E');svg.append(svgtext(60,1015,note_lines,12,fill='#71847E',line=18));svg.append('</svg>')
 path=PREVIEW/f'{p.index:02}.svg';path.write_text('\n'.join(svg));render_manifest.append((p.title,path.name))
 # Structural checks: all labels fit in their parent, and component boxes do not overlap.
 ns=list(p.nodes.values())
 for i,a in enumerate(ns):
  assert a['body_y']+len(a['body'])*20<a['h']-5,(p.title,a['id'])
  for b in ns[i+1:]:assert not(a['x']<b['x']+b['w'] and a['x']+a['w']>b['x'] and a['y']<b['y']+b['h'] and a['y']+a['h']>b['y'])
E.indent(mx,space='  ')
# Checks above complete before writing the requested output; previews support visual QA.
candidate=PREVIEW/'sievance-architecture.drawio';E.ElementTree(mx).write(candidate,encoding='utf-8',xml_declaration=True)
OUT.write_bytes(candidate.read_bytes())
html='''<!doctype html><meta charset="utf-8"><title>Sievance architecture review</title><style>body{margin:0;background:#e8ede9;font:14px Arial}nav{position:sticky;top:0;background:#173a31;padding:14px;display:flex;gap:12px}nav a{color:white;text-decoration:none}section{padding:20px}h2{color:#264c3e}img{display:block;width:100%;background:white;border:1px solid #ccd9d1} </style><nav>'''+''.join(f'<a href="#page-{i}">{i}</a>' for i in range(1,8))+'</nav>'+''.join(f'<section id="page-{i}"><h2>{escape(title)}</h2><img src="{name}"></section>' for i,(title,name) in enumerate(render_manifest,1))
(PREVIEW/'index.html').write_text(html)
print(json.dumps({'output':str(OUT),'pages':len(pages),'components':sum(len(p.nodes) for p in pages),'connections':sum(len(p.edges) for p in pages),'review':str(PREVIEW/'index.html'),'checks':'explicit orthogonal routes, no routes through unrelated boxes, no component overlap, labels fit inside their parent'},indent=2))
