"""Durable project/case workflow around the existing ingestion and analysis.

Only approved deterministic functions execute in this module. Imported prose is
data, and raw/unreviewed values are never silently treated as analysis inputs.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import shutil
import signal
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
import zipfile
from collections import defaultdict
from pathlib import Path

from .pipeline import IngestionService, digest, utc


ACCEPTED={'accepted','auto_accepted','corrected'}
ACTIVE={'queued','running','cancelling'}


class CaseService:
    def __init__(self,root):
        self.ingestion=IngestionService(root)
        self.root=self.ingestion.root
        self.db=self.ingestion.db
        self._stop=threading.Event(); self._thread=None; self._process=None
        with self.connect() as con:
            con.executescript('''
                CREATE TABLE IF NOT EXISTS pharma_projects(id TEXT PRIMARY KEY,tenant TEXT NOT NULL,name TEXT NOT NULL,created TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS pharma_cases(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,title TEXT NOT NULL,problem TEXT NOT NULL,created TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS pharma_packages(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,name TEXT NOT NULL,hash TEXT NOT NULL,version INTEGER NOT NULL,path TEXT NOT NULL,created TEXT NOT NULL,UNIQUE(project_id,name,hash));
                CREATE TABLE IF NOT EXISTS pharma_imports(case_id TEXT NOT NULL,package_id TEXT NOT NULL,job_id TEXT NOT NULL,UNIQUE(case_id,package_id));
                CREATE TABLE IF NOT EXISTS pharma_jobs(id TEXT PRIMARY KEY,case_id TEXT NOT NULL,kind TEXT NOT NULL,status TEXT NOT NULL,request TEXT NOT NULL,result TEXT,stage TEXT,attempt INTEGER NOT NULL DEFAULT 0,lease TEXT,updated TEXT NOT NULL,error TEXT);
                CREATE TABLE IF NOT EXISTS pharma_reviews(id TEXT PRIMARY KEY,job_id TEXT NOT NULL,finding_id TEXT NOT NULL,decision TEXT NOT NULL,actor TEXT NOT NULL,reason TEXT NOT NULL,version TEXT NOT NULL,created TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS pharma_actions(id TEXT PRIMARY KEY,case_id TEXT NOT NULL,title TEXT NOT NULL,owner TEXT NOT NULL,status TEXT NOT NULL,rationale TEXT NOT NULL,evidence TEXT NOT NULL,outcome TEXT,created TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS pharma_action_events(id TEXT PRIMARY KEY,action_id TEXT NOT NULL,status TEXT NOT NULL,actor TEXT NOT NULL,reason TEXT NOT NULL,created TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS pharma_watches(id TEXT PRIMARY KEY,case_id TEXT NOT NULL,path TEXT NOT NULL,settle_seconds INTEGER NOT NULL,seen TEXT NOT NULL,status TEXT NOT NULL,error TEXT);
                CREATE TRIGGER IF NOT EXISTS pharma_reviews_immutable_update BEFORE UPDATE ON pharma_reviews BEGIN SELECT RAISE(ABORT,'append only'); END;
                CREATE TRIGGER IF NOT EXISTS pharma_reviews_immutable_delete BEFORE DELETE ON pharma_reviews BEGIN SELECT RAISE(ABORT,'append only'); END;
                CREATE TRIGGER IF NOT EXISTS pharma_action_events_immutable_update BEFORE UPDATE ON pharma_action_events BEGIN SELECT RAISE(ABORT,'append only'); END;
                CREATE TRIGGER IF NOT EXISTS pharma_action_events_immutable_delete BEFORE DELETE ON pharma_action_events BEGIN SELECT RAISE(ABORT,'append only'); END;
            ''')

    def connect(self):
        con=sqlite3.connect(self.db,timeout=30); con.row_factory=sqlite3.Row
        return con

    def project(self,ident,tenant):
        with self.connect() as con: row=con.execute('SELECT * FROM pharma_projects WHERE id=? AND tenant=?',(ident,tenant)).fetchone()
        if not row: raise KeyError('Project unavailable in this customer context')
        return dict(row)

    def create_project(self,tenant,name):
        if not name.strip(): raise ValueError('Project name is required')
        row={'id':uuid.uuid4().hex,'tenant':tenant,'name':name.strip(),'created':utc()}
        with self.connect() as con: con.execute('INSERT INTO pharma_projects VALUES (:id,:tenant,:name,:created)',row)
        return row

    def projects(self,tenant):
        with self.connect() as con: return [dict(r) for r in con.execute('SELECT * FROM pharma_projects WHERE tenant=? ORDER BY created',(tenant,))]

    def create_case(self,project_id,tenant,title,problem):
        self.project(project_id,tenant)
        if not title.strip() or not problem.strip(): raise ValueError('Case title and investigation question are required')
        row={'id':uuid.uuid4().hex,'project_id':project_id,'title':title.strip(),'problem':problem.strip(),'created':utc()}
        with self.connect() as con: con.execute('INSERT INTO pharma_cases VALUES (:id,:project_id,:title,:problem,:created)',row)
        return row

    def case(self,ident,tenant):
        with self.connect() as con: row=con.execute('SELECT * FROM pharma_cases WHERE id=?',(ident,)).fetchone()
        if not row: raise KeyError('Case unavailable')
        row=dict(row); self.project(row['project_id'],tenant)
        return row

    def cases(self,project_id,tenant):
        self.project(project_id,tenant)
        with self.connect() as con: return [dict(r) for r in con.execute('SELECT * FROM pharma_cases WHERE project_id=? ORDER BY created',(project_id,))]

    @staticmethod
    def unpack(data,name):
        if len(data)>64*1024*1024: raise ValueError('Upload exceeds 64 MiB')
        suffix=Path(name).suffix.lower()
        allowed={'.csv','.xlsx','.pdf'}
        if suffix in allowed: return [(Path(name).name,data)]
        if suffix!='.zip': raise ValueError('Supported imports: CSV, XLSX, PDF, or bounded ZIP')
        result=[]
        with zipfile.ZipFile(io.BytesIO(data)) as book:
            members=book.infolist()
            if len(members)>500 or sum(m.file_size for m in members)>128*1024*1024: raise ValueError('ZIP expansion limit exceeded')
            seen=set()
            for member in members:
                path=Path(member.filename)
                if path.is_absolute() or '..' in path.parts or '\\' in member.filename or member.flag_bits&1 or (member.external_attr>>16)&0o170000==0o120000:
                    raise ValueError('Unsafe or encrypted ZIP member')
                if member.is_dir(): continue
                if path.suffix.lower() not in allowed: raise ValueError('Nested archives and unsupported ZIP members are forbidden')
                if member.filename in seen: raise ValueError('Duplicate ZIP member path')
                seen.add(member.filename); result.append((member.filename,book.read(member)))
        if not result: raise ValueError('Package contains no supported files')
        return sorted(result)

    def import_bytes(self,case_id,tenant,name,data):
        case=self.case(case_id,tenant); name=Path(name).name
        entries=self.unpack(data,name)
        # Delivery names and ZIP metadata are not a new source version. Keep
        # content identity project-local while retaining the first original names.
        content=digest(sorted(hashlib.sha256(b).hexdigest() for p,b in entries))
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            package=con.execute('SELECT * FROM pharma_packages WHERE project_id=? AND hash=?',(case['project_id'],content)).fetchone()
            if not package:
                ident=uuid.uuid4().hex; folder=self.root/'case-packages'/case['project_id']/ident
                folder.mkdir(parents=True,mode=0o700)
                for path,raw in entries:
                    target=folder/path; target.parent.mkdir(parents=True,exist_ok=True)
                    target.write_bytes(raw); target.chmod(0o444)
                version=con.execute('SELECT coalesce(max(version),0)+1 FROM pharma_packages WHERE project_id=? AND name=?',(case['project_id'],name)).fetchone()[0]
                con.execute('INSERT INTO pharma_packages VALUES (?,?,?,?,?,?,?)',(ident,case['project_id'],name,content,version,str(folder),utc()))
                package=con.execute('SELECT * FROM pharma_packages WHERE id=?',(ident,)).fetchone()
            imported=con.execute('SELECT job_id FROM pharma_imports WHERE case_id=? AND package_id=?',(case_id,package['id'])).fetchone()
            if imported: return {'job_id':imported[0],'package_id':package['id'],'version':package['version'],'duplicate':True}
            job=self._enqueue(con,case_id,'ingest',{'package_id':package['id'],'tenant':tenant})
            con.execute('INSERT INTO pharma_imports VALUES (?,?,?)',(case_id,package['id'],job))
        return {'job_id':job,'package_id':package['id'],'version':package['version'],'duplicate':False}

    def _enqueue(self,con,case_id,kind,request):
        ident=uuid.uuid4().hex
        request={**request,'queued_at':utc()}
        con.execute('INSERT INTO pharma_jobs(id,case_id,kind,status,request,updated) VALUES (?,?,?,?,?,?)',(ident,case_id,kind,'queued',json.dumps(request),utc()))
        return ident

    def imports(self,case_id,tenant):
        self.case(case_id,tenant)
        with self.connect() as con:
            rows=[dict(r) for r in con.execute('SELECT p.id,p.name,p.hash,p.version,j.id AS job_id,j.status,j.stage,j.error,p.created FROM pharma_imports i JOIN pharma_packages p ON p.id=i.package_id JOIN pharma_jobs j ON j.id=i.job_id WHERE i.case_id=? ORDER BY p.created',(case_id,))]
        for r in rows:
            try:
                ingested=self.ingestion.get(r['job_id'])
                r['summary']=ingested.get('summary'); r['ingestion_status']=ingested['status']
                r['processing_seconds']=ingested.get('runtime_seconds')
            except KeyError: pass
        return rows

    def snapshot(self,case_id,tenant):
        imports=self.imports(case_id,tenant)
        latest={}
        for entry in imports: latest[entry['name']]=entry
        rows=[]; gaps=[]; versions=[]; active=[]
        for entry in latest.values():
            if entry['status']!='complete':
                active.append({'id':entry['job_id'],'status':entry['status']})
                gaps.append(f"{entry['name']}: ingestion {entry['status']}"); continue
            run=self.ingestion.get(entry['job_id'])
            active.append(run)
            versions.append({'job_id':entry['job_id'],'package_id':entry['id'],'hash':entry['hash'],'version':entry['version']})
            for m in run['measurements']:
                if m['status'] in ACCEPTED:
                    self.ingestion.original(run['id'],m['source_id'])
                    rows.append({**m,'ingestion_id':run['id']})
            pending=sum(m['status']=='needs_review' for m in run['measurements'])
            if pending: gaps.append(f"{entry['name']}: {pending} unverified measurements excluded")
            for issue in run['issues']:
                if issue['status']=='open': gaps.append(f"{entry['name']}: {issue['rule_code']} {issue.get('message','')}")
        identities=defaultdict(list)
        for measurement in rows:
            identities[(measurement['batch'],float(measurement['time'].replace(',','.')),measurement['parameter'],measurement['unit'])].append(measurement)
        ambiguous=set()
        for identity,group in identities.items():
            if len(group)>1:
                kind='Conflicting values' if len({m['value'] for m in group})>1 else 'Repeated records'
                gaps.append(f'{kind} for batch {identity[0]}, hour {identity[1]}, {identity[2]}: excluded from calculations; resolve these records in Data review. Sources: '+', '.join(m['source']['path'] for m in group))
                ambiguous.update(m['id'] for m in group)
        rows=[m for m in rows if m['id'] not in ambiguous]
        # The full active evidence state binds acceptance, rejection, and corrections,
        # including pending observations. Changing any review invalidates a result.
        revision=digest([{'versions':versions,'active':[{k:r.get(k) for k in ['id','status','measurements','issues','reviews']} for r in active]}])
        return {'revision':revision,'measurements':rows,'source_versions':versions,'gaps':gaps,'case_id':case_id,'captured_at':utc()}

    def analyze(self,case_id,tenant,starter='batch_comparison',parameters=None):
        case=self.case(case_id,tenant)
        if starter not in {'batch_comparison','yield_change','deviation_review'}: raise ValueError('Unknown task starter')
        snapshot=self.snapshot(case_id,tenant)
        if not snapshot['measurements']: raise ValueError('No unambiguous reviewed measurements available. Review pending values and resolve repeated/conflicting records in Data review.')
        if parameters:
            if not set(parameters)<={m['parameter'] for m in snapshot['measurements']}: raise ValueError('Selected parameter has no verified data')
            snapshot['measurements']=[m for m in snapshot['measurements'] if m['parameter'] in parameters]
        with self.connect() as con: job=self._enqueue(con,case_id,'analyze',{'tenant':tenant,'starter':starter,'problem':case['problem'],'snapshot':snapshot})
        return {'job_id':job}

    def job(self,ident,tenant):
        with self.connect() as con: row=con.execute('SELECT * FROM pharma_jobs WHERE id=?',(ident,)).fetchone()
        if not row: raise KeyError('Run unavailable')
        row=dict(row); self.case(row['case_id'],tenant)
        row['request']=json.loads(row['request']); row['result']=json.loads(row['result']) if row['result'] else None
        row.pop('lease',None)
        if row['kind']=='analyze' and row['result']:
            row['stale']=row['request']['snapshot']['revision']!=self.snapshot(row['case_id'],tenant)['revision']
            with self.connect() as con: row['reviews']=[dict(r) for r in con.execute('SELECT * FROM pharma_reviews WHERE job_id=? ORDER BY created',(ident,))]
        return row

    def jobs(self,case_id,tenant):
        self.case(case_id,tenant)
        with self.connect() as con: ids=[r[0] for r in con.execute('SELECT id FROM pharma_jobs WHERE case_id=? ORDER BY updated',(case_id,))]
        return [self.job(i,tenant) for i in ids]

    def review_finding(self,job_id,tenant,finding_id,decision,actor,reason,version):
        job=self.job(job_id,tenant)
        if decision not in {'accept','reject','annotate'} or not actor.strip() or not reason.strip(): raise ValueError('Review decision, actor and reason are required')
        if not job['result'] or job.get('stale'): raise ValueError('Run is stale or incomplete; rerun analysis before review')
        if version!=job['result']['version']: raise ValueError('Reviewed version differs from saved result')
        if finding_id not in {f['id'] for f in job['result']['findings']}: raise KeyError('Finding absent from this run')
        with self.connect() as con: con.execute('INSERT INTO pharma_reviews VALUES (?,?,?,?,?,?,?,?)',(uuid.uuid4().hex,job_id,finding_id,decision,actor,reason,version,utc()))
        return self.job(job_id,tenant)

    def action(self,case_id,tenant,title,owner,rationale,evidence,actor='local-user'):
        self.case(case_id,tenant)
        if not all(str(v).strip() for v in [title,owner,rationale]): raise ValueError('Action, responsible role/owner and rationale are required')
        visible={m['id'] for item in self.imports(case_id,tenant) if item['status']=='complete'
                 for m in self.ingestion.get(item['job_id'])['measurements']}
        if not set(evidence)<=visible: raise ValueError('Action cites evidence outside the current verified case')
        ident=uuid.uuid4().hex
        with self.connect() as con:
            con.execute('INSERT INTO pharma_actions VALUES (?,?,?,?,?,?,?,?,?)',(ident,case_id,title,owner,'proposed',rationale,json.dumps(evidence),None,utc()))
            con.execute('INSERT INTO pharma_action_events VALUES (?,?,?,?,?,?)',(uuid.uuid4().hex,ident,'proposed',actor,rationale,utc()))
        return ident

    def actions(self,case_id,tenant):
        self.case(case_id,tenant)
        with self.connect() as con:
            actions=[dict(r) for r in con.execute('SELECT * FROM pharma_actions WHERE case_id=? ORDER BY created',(case_id,))]
            for action in actions: action['events']=[dict(r) for r in con.execute('SELECT * FROM pharma_action_events WHERE action_id=? ORDER BY created',(action['id'],))]
        return actions

    def action_status(self,ident,tenant,status,actor,reason):
        with self.connect() as con: row=con.execute('SELECT * FROM pharma_actions WHERE id=?',(ident,)).fetchone()
        if not row: raise KeyError('Action unavailable')
        self.case(row['case_id'],tenant)
        next_status={'proposed':'reviewed','reviewed':'in_progress','in_progress':'outcome_recorded'}
        if next_status.get(row['status'])!=status or not actor.strip() or not reason.strip(): raise ValueError('Invalid action transition or missing reviewer/reason')
        with self.connect() as con:
            con.execute('UPDATE pharma_actions SET status=?,outcome=? WHERE id=?',(status,reason if status=='outcome_recorded' else None,ident))
            con.execute('INSERT INTO pharma_action_events VALUES (?,?,?,?,?,?)',(uuid.uuid4().hex,ident,status,actor,reason,utc()))
        return {'id':ident,'status':status}

    def export(self,case_id,tenant):
        case=self.case(case_id,tenant); snapshot=self.snapshot(case_id,tenant)
        jobs=[j for j in self.jobs(case_id,tenant) if j['kind']=='analyze' and j['result']]
        lines=[f"# {case['title']}",'',case['problem'],'',f"Case: {case_id}",f"Current evidence revision: {snapshot['revision']}",'','## Data and unresolved information','']
        lines += [f'- {g}' for g in snapshot['gaps']] or ['No unresolved ingestion issues recorded.']
        lines+=['','## Imported source versions','']
        for item in self.imports(case_id,tenant):
            lines.append(f"- {item['name']}, version {item['version']}, {item['status']}; package hash {item['hash']}")
            if item['status']=='complete':
                for doc in self.ingestion.get(item['job_id'])['documents']:
                    self.ingestion.original(item['job_id'],doc['source_id'])
                    lines.append(f"  - [{doc['path']}](/api/cmo-ingestion/runs/{item['job_id']}/sources/{doc['source_id']}); SHA-256 {doc['sha256']}")
        for job in jobs:
            result=job['result']
            lines+=['',f"## Analysis {job['id']}",f"Status: {'STALE; do not act on this result' if job.get('stale') else job['status']}",f"Input revision: {job['request']['snapshot']['revision']}",'']
            for finding in result['findings']:
                lines += [f"### {finding['statement']}",f"Type: {finding['type']}",f"Calculation: {json.dumps(finding['calculation'])}",'Sources:']
                for source in finding['sources']:
                    url=f"/api/cmo-ingestion/runs/{source['ingestion_id']}/sources/{source['source_id']}"
                    if source['source'].get('page'): url+=f"#page={source['source']['page']}"
                    lines.append(f"- [{source['source']['path']}]({url}) {json.dumps(source['source'])}; SHA-256 {source['source_sha256']}")
                lines+=['Limitations: '+'; '.join(finding['limitations']),'Contradictions: '+finding['contradictions'],'']
            lines+=['### Missing information / next steps',*['- '+s for s in result['requests']],'','### Reviewer dispositions',*['- '+json.dumps(r) for r in job.get('reviews',[])]]
        lines+=['','## Proposed actions (not execution authorizations)','']
        for action in self.actions(case_id,tenant):
            lines.append(f"- {action['title']} — {action['owner']} — {action['status']}; rationale: {action['rationale']}; outcome: {action['outcome'] or 'not recorded'}; evidence IDs: {action['evidence']}")
            for event in action['events']: lines.append(f"  - {event['created']}: {event['actor']} recorded {event['status']}: {event['reason']}")
        lines+=['','Human work and savings have not been measured. Review acceptance is not scientific ground truth, batch release authorization, or a regulated electronic signature.']
        return '\n'.join(lines)+'\n'

    def execute(self,ident,lease):
        """Worker entry. Input and completed snapshots are persisted in SQLite."""
        with self.connect() as con: job=dict(con.execute('SELECT * FROM pharma_jobs WHERE id=? AND lease=? AND status=?',(ident,lease,'running')).fetchone())
        started=time.monotonic()
        request=json.loads(job['request']); tenant=request['tenant']; case=self.case(job['case_id'],tenant)
        def stage(name):
            with self.connect() as con:
                changed=con.execute('UPDATE pharma_jobs SET stage=?,updated=? WHERE id=? AND lease=? AND status=?',(name,utc(),ident,lease,'running')).rowcount
                if not changed: raise InterruptedError('Run was cancelled or superseded')
        try:
            if job['kind']=='ingest':
                with self.connect() as con: package=dict(con.execute('SELECT * FROM pharma_packages WHERE id=?',(request['package_id'],)).fetchone())
                scope='project-'+case['project_id']
                result=self.ingestion.run(package['path'],scope,'preview',run_id=ident,on_stage=lambda event:stage(event['stage']),
                    project_context={'project_tenant':tenant,'project_id':case['project_id'],'case_id':case['id']})
                result.update(project_tenant=tenant,project_id=case['project_id'],case_id=case['id'])
                self.ingestion.save(result)
                if result['status']!='complete': raise RuntimeError(result.get('error') or str(result.get('unavailable_reasons')))
                saved={'ingestion_id':ident,'summary':result['summary']}
            else:
                stage('Snapshot verified evidence')
                saved=self._analyze_snapshot(ident,request,stage)
            stage('Save result')
            saved['processing_seconds']=time.monotonic()-started
            with self.connect() as con:
                con.execute('UPDATE pharma_jobs SET status=?,result=?,updated=? WHERE id=? AND lease=? AND status=?',('complete',json.dumps(saved,allow_nan=False),utc(),ident,lease,'running'))
        except Exception as exc:
            with self.connect() as con: con.execute('UPDATE pharma_jobs SET status=?,error=?,updated=? WHERE id=? AND lease=? AND status=?',('failed',str(exc),utc(),ident,lease,'running'))

    def _analyze_snapshot(self,ident,request,stage):
        from ..store import ManufacturingStore
        from ..models import Observation,SourceRef
        from ..analysis import DeterministicAnalysis
        snapshot=request['snapshot']; rows=snapshot['measurements']; scope='case-snapshot-'+ident
        store=ManufacturingStore(self.root/'case-analysis'/ident)
        for source_id in {m['source_id'] for m in rows}:
            measurement=next(m for m in rows if m['source_id']==source_id)
            original,doc=self.ingestion.original(measurement['ingestion_id'],source_id)
            source_store=ManufacturingStore(self.ingestion.get(measurement['ingestion_id'])['store'])
            with source_store.connect() as con: source=dict(con.execute('SELECT * FROM sources WHERE id=?',(source_id,)).fetchone())
            target=store.originals/doc['sha256'][:2]/original.name; target.parent.mkdir(exist_ok=True)
            shutil.copyfile(original,target); target.chmod(0o444)
            source['original_path']=str(target); source['access_scope']=scope
            with store.connect() as con:
                columns=','.join(source); placeholders=','.join('?' for _ in source)
                con.execute(f'INSERT OR REPLACE INTO sources ({columns}) VALUES ({placeholders})',list(source.values()))
        store.add_observations([Observation(observation_id=m['id'],source=SourceRef(**{'source_id':m['source_id'],**m['source']}),
            name=m['parameter'],value_text=m['value_raw'],value_number=m['value'],unit=m['unit'],entity_id=m['batch'],entity_kind='batch',
            validation_status='normalized',access_scope=scope,extraction_method='reviewed-cmo-snapshot') for m in rows])
        groups=defaultdict(list)
        for m in rows: groups[(m['batch'],m['parameter'],m['unit'])].append(m)
        if len(groups)>200: raise ValueError('Analysis exceeds 200 series; select fewer parameters or a smaller case')
        analysis=DeterministicAnalysis(store,scopes=(scope,)); findings=[]; requests=list(snapshot['gaps'])
        for (batch,parameter,unit),series in sorted(groups.items()):
            stage(f'Calculate {batch}: {parameter}')
            ids=[m['id'] for m in series]
            mean=analysis.calculate({'operation':'mean','evidence_ids':ids})
            minimum=analysis.calculate({'operation':'minimum','evidence_ids':ids})
            maximum=analysis.calculate({'operation':'maximum','evidence_ids':ids})
            times=[float(m['time'].replace(',','.')) for m in series]
            limitation=['Descriptive observed timepoints, not independent biological replicates.',
                        'Batch comparability, specification limits and causation are not established.',
                        'Only accepted measurements are included; missing/unverified evidence can change this result.']
            trend=None
            if len(set(times))==len(times) and len(times)>1:
                ordered=sorted(series,key=lambda m:float(m['time'].replace(',','.')))
                trend=analysis.calculate({'operation':'difference','numerator_ids':[ordered[-1]['id']],'denominator_ids':[ordered[0]['id']]})
            else: limitation.append('A unique time-aligned trend cannot be established from this series.')
            citations=[{k:m[k] for k in ['id','ingestion_id','source_id','source','source_sha256','batch','time','parameter','value','unit']} for m in series]
            findings.append({'id':digest([snapshot['revision'],batch,parameter,unit]),'type':'observed_fact',
                'statement':f'{batch}: {parameter} mean {mean["value"]:.6g} {unit} across {len(series)} reviewed measurements.',
                'relevance_reason':'Describes a reviewed process or quality variable selected for this case; causal relevance remains unresolved.',
                'calculation':{'n':len(series),'mean':mean,'minimum':minimum,'maximum':maximum,'last_minus_first':trend},
                'sources':citations,'contradictions':'No causal explanation is asserted. Review the case gaps and conflicting-source issues before interpretation.',
                'limitations':limitation,'points':[{'time':m['time'],'value':m['value'],'measurement_id':m['id']} for m in sorted(series,key=lambda m:float(m['time'].replace(',','.')))]})
        if request['starter']=='yield_change': requests.append('Supply comparable batch endpoints, paired substrate/feed and volume records, and the intended yield definition before attributing a yield change.')
        requests.append('Confirm operating conditions, comparable sampling schedules and candidate competing explanations before causal interpretation.')
        return {'version':digest([snapshot['revision'],findings]),'engine':'existing DeterministicAnalysis; approved descriptive operations',
                'findings':findings,'requests':requests,'snapshot_revision':snapshot['revision'],
                'model_calls':0,'tool_calls':sum(4 if f['calculation']['last_minus_first'] else 3 for f in findings),'completed_at':utc()}

    def cancel(self,ident,tenant):
        job=self.job(ident,tenant)
        if job['status'] not in ACTIVE: raise ValueError('Run is already finished')
        with self.connect() as con: con.execute('UPDATE pharma_jobs SET status=?,updated=? WHERE id=?',('cancelled',utc(),ident))
        return self.job(ident,tenant)

    def resume(self,ident,tenant):
        job=self.job(ident,tenant)
        if job['status'] not in {'failed','cancelled','interrupted'}: raise ValueError('Only failed, cancelled or interrupted runs can be retried')
        if job['attempt']>=3: raise ValueError('Retry budget exhausted; inspect the error before creating a new run')
        with self.connect() as con: con.execute('UPDATE pharma_jobs SET status=?,lease=NULL,error=NULL,updated=? WHERE id=?',('queued',utc(),ident))
        return self.job(ident,tenant)

    def start(self):
        if self._thread and self._thread.is_alive(): return
        # Single-process local deployment. A clean stop cancels the owned child;
        # after a crash, old leases are fenced and explicit retry is required.
        with self.connect() as con: con.execute("UPDATE pharma_jobs SET status='interrupted',lease=NULL,error='Service restarted; explicitly retry to recover' WHERE status='running'")
        self._stop.clear()
        self._thread=threading.Thread(target=self._loop,daemon=True); self._thread.start()

    def stop(self):
        self._stop.set()
        if self._process and self._process.poll() is None: self._terminate(self._process)
        if self._thread: self._thread.join(timeout=5)

    @staticmethod
    def _terminate(process):
        try: os.killpg(process.pid,signal.SIGTERM)
        except ProcessLookupError: pass

    def _loop(self):
        while not self._stop.is_set():
            with self.connect() as con:
                con.execute('BEGIN IMMEDIATE')
                row=con.execute("SELECT * FROM pharma_jobs WHERE status='queued' ORDER BY updated LIMIT 1").fetchone()
                if row:
                    ident=row['id']; lease=uuid.uuid4().hex
                    con.execute("UPDATE pharma_jobs SET status='running',lease=?,attempt=attempt+1,updated=? WHERE id=?",(lease,utc(),ident))
            if not row:
                self._scan_watches(); self._stop.wait(1); continue
            try:
                log=self.root/'case-job-logs'; log.mkdir(exist_ok=True,mode=0o700)
                with (log/(ident+'.log')).open('ab') as output:
                    self._process=subprocess.Popen([sys.executable,'-m','src.manufacturing_data.cmo.case_worker',str(self.root),ident,lease],
                        cwd=Path(__file__).resolve().parents[3],stdout=output,stderr=output,start_new_session=True)
                    started=time.monotonic(); limit=int(os.getenv('PHARMA_JOB_SECONDS','180'))
                    while self._process.poll() is None:
                        with self.connect() as con: state=con.execute('SELECT status FROM pharma_jobs WHERE id=?',(ident,)).fetchone()[0]
                        if state!='running' or self._stop.is_set() or time.monotonic()-started>limit:
                            self._terminate(self._process)
                            try: self._process.wait(timeout=3)
                            except subprocess.TimeoutExpired: os.killpg(self._process.pid,signal.SIGKILL); self._process.wait()
                            with self.connect() as con:
                                con.execute("UPDATE pharma_jobs SET status=?,error=?,updated=? WHERE id=? AND status='running'",('interrupted' if self._stop.is_set() else 'failed','Worker stopped or wall-time budget exhausted',utc(),ident))
                            break
                        self._stop.wait(.3)
                with self.connect() as con: con.execute("UPDATE pharma_jobs SET status='failed',error='Worker exited without a saved result',updated=? WHERE id=? AND status='running'",(utc(),ident))
            except Exception as exc:
                with self.connect() as con: con.execute("UPDATE pharma_jobs SET status='failed',error=?,updated=? WHERE id=? AND status='running'",(str(exc),utc(),ident))
            finally: self._process=None

    def watch(self,case_id,tenant,path,settle_seconds=10):
        self.case(case_id,tenant); folder=Path(path).resolve()
        allowed=os.getenv('PHARMA_WATCH_ROOT')
        if not allowed or not folder.is_relative_to(Path(allowed).resolve()) or not folder.is_dir(): raise ValueError('Folder must exist inside administrator-configured PHARMA_WATCH_ROOT')
        if not 2<=settle_seconds<=3600: raise ValueError('Settling delay must be 2–3600 seconds')
        ident=uuid.uuid4().hex
        with self.connect() as con: con.execute('INSERT INTO pharma_watches VALUES (?,?,?,?,?,?,?)',(ident,case_id,str(folder),settle_seconds,'{}','watching',None))
        return ident

    def _scan_watches(self):
        with self.connect() as con: watches=[dict(r) for r in con.execute('SELECT * FROM pharma_watches')]
        for watch in watches:
            try:
                with self.connect() as con: tenant=con.execute('SELECT p.tenant FROM pharma_cases c JOIN pharma_projects p ON p.id=c.project_id WHERE c.id=?',(watch['case_id'],)).fetchone()[0]
                checkpoint=json.loads(watch['seen']); folder=Path(watch['path'])
                for path in sorted(folder.iterdir()):
                    if path.is_symlink() or not path.is_file() or path.suffix.lower() not in {'.csv','.xlsx','.pdf','.zip'}: continue
                    stat=path.stat(); version=f'{stat.st_size}:{stat.st_mtime_ns}'; previous=checkpoint.get(path.name,{})
                    if previous.get('version')!=version: checkpoint[path.name]={'version':version,'since':time.time()}; continue
                    if previous.get('imported') or time.time()-previous['since']<watch['settle_seconds']: continue
                    if stat.st_size>64*1024*1024: raise ValueError(f'{path.name}: watched-file upload limit is 64 MiB')
                    content=path.read_bytes()
                    if f'{path.stat().st_size}:{path.stat().st_mtime_ns}'!=version: continue
                    imported=self.import_bytes(watch['case_id'],tenant,path.name,content)
                    checkpoint[path.name].update(imported=True,job_id=imported['job_id'])
                with self.connect() as con: con.execute('UPDATE pharma_watches SET seen=?,status=?,error=NULL WHERE id=?',(json.dumps(checkpoint),'watching',watch['id']))
            except Exception as exc:
                with self.connect() as con: con.execute('UPDATE pharma_watches SET status=?,error=? WHERE id=?',('error',str(exc),watch['id']))
