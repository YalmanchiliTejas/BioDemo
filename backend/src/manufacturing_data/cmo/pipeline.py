"""Fixed ingestion workflow extending ManufacturingStore; no investigation runtime.

The evaluator and answer keys are intentionally absent from this module.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
import sqlite3
import threading
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from ..ingest import ingest_package
from ..store import ManufacturingStore
from ..verification import verify_originals
from .providers import ClairicProvider, Provider, Unavailable
from .schema import Classification, Extraction, Mapping, TYPES, VOCAB, draft_mapping, header_parts, key, normalize

STAGES = ['Ingest','Classify','Parse','Map','Validate','Review','Store/Export']
CONFIGURATIONS = {'clairic_decisions':'Docling + Clairic extraction + OpenAI Decisions classification/mapping', 'decisions':'Docling + OpenAI Decisions (classification and mapping)', 'A':'Docling + generative mapping','B':'Docling + Clairic',
                  'C':'Docling + Clairic + Jev','D':'Confirmed deterministic templates',
                  'preview':'Available local parsers + draft aliases (diagnostic baseline)'}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',',':'),allow_nan=False).encode()).hexdigest()


def utc(): return datetime.now(timezone.utc).isoformat()


def classify(path):
    name=key(Path(path).stem)
    for token, kind in [('environmental','environmental_monitoring'),('microbiology','microbiology'),
                        ('coa','coa'),('maintenance','maintenance'),('deviation','deviation_report'),
                        ('investigation','investigation_report'),('batch record','batch_record'),
                        ('bioreactor','instrument_export'),('fermentation','instrument_export')]:
        if token in name: return kind
    return 'other'


def document_records(observations):
    """Conservative printable form parser; unsupported forms remain review items."""
    result=[]
    for obs in observations:
        for text in (obs['value_text'] or '').splitlines():
            parts=re.split(r'\s+[|;]\s+', text.strip())
            if len(parts) != 3: continue
            batch=re.fullmatch(r'Batch:\s*(\S+)',parts[0]); hour=re.fullmatch(r'Hour:\s*(\S+)',parts[1])
            field=re.fullmatch(r'(.+?\[[^\]]+\]):\s*([-+\d.eE,]+)', parts[2])
            if not (batch and hour and field): continue
            result.append({'batch_id':(batch[1],obs),'elapsed_h':(hour[1],obs),field[1]:(field[2],obs)})
    return result


def fingerprint(kind, sheet, headers, extension):
    # Ordered headers and sheet names are structural, including Raman channel IDs.
    return digest({'kind':kind,'sheet':sheet,'headers':[key(h) for h in headers],'format':extension})


class IngestionService:
    def __init__(self, root):
        from .settings import load_local_settings
        load_local_settings()
        self.root=Path(root).resolve(); self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.db=self.root/'cmo.sqlite'; self._lock=threading.RLock()
        with self.connect() as con:
            con.executescript('''
            CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, cmo TEXT, config TEXT, result TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS templates(id TEXT PRIMARY KEY, cmo TEXT, fingerprint TEXT,
              kind TEXT, version INTEGER, mapping TEXT, headers TEXT, actor TEXT, at TEXT, origin TEXT);
            CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT, payload TEXT,
              prev_hash TEXT NOT NULL, hash TEXT NOT NULL);
            CREATE TRIGGER IF NOT EXISTS immutable_events_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'append only'); END;
            CREATE TRIGGER IF NOT EXISTS immutable_events_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT,'append only'); END;
            CREATE TRIGGER IF NOT EXISTS immutable_templates_update BEFORE UPDATE ON templates BEGIN SELECT RAISE(ABORT,'version templates'); END;
            CREATE TRIGGER IF NOT EXISTS immutable_templates_delete BEFORE DELETE ON templates BEGIN SELECT RAISE(ABORT,'append only'); END;
            ''')

    def connect(self):
        con=sqlite3.connect(self.db,timeout=30); con.row_factory=sqlite3.Row
        return con

    def audit(self, action, **data):
        with self._lock, self.connect() as con:
            row=con.execute('SELECT hash FROM events ORDER BY seq DESC LIMIT 1').fetchone()
            prev=row[0] if row else '0'*64
            payload=json.dumps({'at':utc(),'action':action,**data},sort_keys=True,allow_nan=False)
            hashed=hashlib.sha256((prev+payload).encode()).hexdigest()
            con.execute('INSERT INTO events(payload,prev_hash,hash) VALUES (?,?,?)',(payload,prev,hashed))
        return hashed

    def verify_audit(self):
        prev='0'*64
        with self.connect() as con:
            for row in con.execute('SELECT * FROM events ORDER BY seq'):
                expected=hashlib.sha256((prev+row['payload']).encode()).hexdigest()
                if row['prev_hash']!=prev or row['hash']!=expected: return False
                prev=row['hash']
        return True

    def template(self,cmo,fp):
        with self.connect() as con:
            row=con.execute('SELECT * FROM templates WHERE cmo=? AND fingerprint=? ORDER BY version DESC LIMIT 1',(cmo,fp)).fetchone()
        return dict(row) if row else None

    def has_kind(self,cmo,kind):
        with self.connect() as con:
            return bool(con.execute('SELECT 1 FROM templates WHERE cmo=? AND kind=? LIMIT 1',(cmo,kind)).fetchone())

    def confirm_template(self,run_id,fp,mapping,actor,reason,*,origin='human'):
        if not actor.strip() or not reason.strip(): raise ValueError('Actor and reason are required')
        run=self.get(run_id)
        draft=next((d for d in run['layouts'] if d['fingerprint']==fp),None)
        if not draft: raise ValueError('Layout is absent from this run')
        parsed=Mapping.model_validate(mapping).check(draft['headers'])
        if not parsed.columns or not parsed.batch_column or not parsed.time_column:
            raise ValueError('Confirm parameter, batch and time mappings explicitly')
        existing=self.template(run['cmo'],fp); version=existing['version']+1 if existing else 1
        template={'id':uuid.uuid4().hex,'cmo':run['cmo'],'fingerprint':fp,'kind':draft['kind'],'version':version,
                  'mapping':parsed.model_dump_json(),'headers':json.dumps(draft['headers']),
                  'actor':actor,'at':utc(),'origin':origin}
        with self.connect() as con:
            con.execute('INSERT INTO templates VALUES (:id,:cmo,:fingerprint,:kind,:version,:mapping,:headers,:actor,:at,:origin)',template)
        self.audit('template_confirmed',template=template,run_id=run_id,reason=reason)
        return template

    def save(self,run):
        with self.connect() as con:
            con.execute('INSERT OR REPLACE INTO runs VALUES (?,?,?,?)',
                        (run['id'],run['cmo'],run['configuration'],json.dumps(run,allow_nan=False)))

    def get(self,run_id):
        with self.connect() as con: row=con.execute('SELECT result FROM runs WHERE id=?',(run_id,)).fetchone()
        if not row: raise KeyError('Unknown run')
        return json.loads(row[0])

    @staticmethod
    def availability(configuration,*,synthetic=False,approved=False):
        import importlib.util
        import os
        if configuration not in CONFIGURATIONS: raise ValueError('Unknown extraction configuration')
        if configuration in {'A','B','C'}:
            return ['Historical configuration retired; select clairic_decisions for Clairic extraction and OpenAI Decisions']
        reasons=[]
        if configuration in {'decisions','clairic_decisions'}:
            if importlib.util.find_spec('docling') is None: reasons.append('Docling is not installed')
            artifacts=os.getenv('DOCLING_ARTIFACTS_PATH')
            if not artifacts or not Path(artifacts).is_dir():
                reasons.append('DOCLING_ARTIFACTS_PATH must point to locally provisioned parser models')
            try: Provider('mapping',lambda _:None,synthetic=synthetic,approved=approved)
            except (Unavailable,ValueError) as exc: reasons.append(str(exc))
        if configuration=='clairic_decisions':
            try: ClairicProvider(lambda _:None,synthetic=synthetic,approved=approved)
            except (Unavailable,ValueError) as exc: reasons.append(str(exc))
        return reasons

    def run(self,package,cmo,configuration='preview',*,synthetic=False,approved=False,run_id=None,on_stage=None,project_context=None):
        import os
        # Inference weights must be provisioned locally. Parsing a customer file
        # must never trigger telemetry or a model-weight download.
        os.environ.setdefault('HF_HUB_OFFLINE','1')
        os.environ.setdefault('TRANSFORMERS_OFFLINE','1')
        os.environ.setdefault('HF_HUB_DISABLE_TELEMETRY','1')
        os.environ.setdefault('DO_NOT_TRACK','1')
        package=Path(package).resolve()
        if not cmo.strip(): raise ValueError('CMO name is required')
        started=time.monotonic()
        run={'id':run_id or uuid.uuid4().hex,'cmo':cmo,'configuration':configuration,
             'started_at':utc(),'status':'running','synthetic':synthetic,'stages':[],
             'layouts':[],'measurements':[],'issues':[],'documents':[],'model_usage':[],'extraction_reviews':[],
             'human_minutes':None,'human_time_status':'not_measured','reviews':[]}
        run.update({k:v for k,v in (project_context or {}).items() if k in {'project_tenant','project_id','case_id'}})
        store=ManufacturingStore(self.root/'stores'/run['id'])
        run['store']=str(store.root)
        def stage(name,state='running'):
            if run['stages'] and run['stages'][-1]['state']=='running':
                previous=run['stages'][-1]
                previous['state']='complete'
                previous['duration_seconds']=time.monotonic()-started-previous['elapsed_seconds']
            event={'stage':name,'state':state,'elapsed_seconds':time.monotonic()-started}
            run['stages'].append(event); self.save(run)
            if on_stage: on_stage(event)
        def issue(code,**context):
            run['issues'].append({'id':digest([code,context]),'rule_code':code,'status':'open',**context})
        def model_audit(record):
            run['model_usage'].append({k:v for k,v in record.items() if k not in {'prompt','response'}})
            self.audit('model_call',run_id=run['id'],**record)
        unavailable=self.availability(configuration,synthetic=synthetic,approved=approved)
        if unavailable:
            run.update(status='unavailable',unavailable_reasons=unavailable,runtime_seconds=time.monotonic()-started)
            self.save(run); return run
        try:
            stage('Ingest')
            # Reuses the original parser, immutable source storage, native sheet readers and OCR.
            ingestion=ingest_package(package,store,access_scope=cmo,
                document_backend='docling' if configuration in {'decisions','clairic_decisions'} else 'pypdf',workers=2)
            run['ingestion']=ingestion
            for error in ingestion['errors']: issue('PARSE_ERROR',**error)
            stage('Classify')
            observations=store.visible(scopes=(cmo,),limit=None)
            sources={s['id']:s for s in store.visible_sources(scopes=(cmo,))}
            grouped=defaultdict(list)
            for obs in observations: grouped[obs['source_id']].append(obs)
            routes={r['path']:r for r in ingestion['routes']}
            classifier=Provider('classification',model_audit,synthetic=synthetic,approved=approved) if configuration in {'decisions','clairic_decisions'} else None
            for sid,source in sources.items():
                kind=classify(source['path'])
                if classifier and kind=='other':
                    # Recover a confirmed classification only from the full layout,
                    # never from a filename cache that could hide a changed form.
                    ext=Path(source['path']).suffix.lower()
                    candidate_layouts=[]
                    if ext in {'.csv','.xlsx','.xlsm','.tsv','.parquet'}:
                        with store.connect() as con:
                            for entry in con.execute('SELECT sheet,schema_json FROM sheets WHERE source_id=?',(sid,)):
                                schema=json.loads(entry['schema_json'])
                                candidate_layouts.append((entry['sheet'],[c['name'] for c in schema] if isinstance(schema,list) else list(schema)))
                    else:
                        native=document_records(grouped[sid])
                        if native: candidate_layouts.append((None,list(dict.fromkeys(h for row in native for h in row))))
                    matches=[{t for t in TYPES if self.template(cmo,fingerprint(t,sheet,headers,ext))}
                             for sheet,headers in candidate_layouts]
                    if matches and all(len(m)==1 for m in matches) and len(set.union(*matches))==1:
                        kind=next(iter(matches[0]))
                if classifier and kind=='other':
                    try:
                        reply=classifier.call('classify',{'filename':source['path'],
                            'text':[o['value_text'] for o in grouped[sid] if (o['source_ref'].get('page') or 1)<=2][:40]},Classification)
                        if reply.doc_type not in TYPES: raise ValueError('Unknown document class')
                        kind=reply.doc_type if reply.confidence>=0.95 else 'other'
                    except (Unavailable,ValueError) as exc: issue('CLASSIFICATION_UNCERTAIN',path=source['path'],message=str(exc))
                run['documents'].append({'source_id':sid,'path':source['path'],'doc_type':kind,
                    'sha256':source['sha256'],'route':routes.get(source['path'],{})})
                if kind=='other': issue('CLASSIFICATION_UNCERTAIN',path=source['path'])
            stage('Parse')
            verification=verify_originals(store,observations)
            records=[]
            for doc in run['documents']:
                sid=doc['source_id']; cells=grouped[sid]; ext=Path(doc['path']).suffix.lower()
                if ext in {'.csv','.xlsx','.xlsm','.tsv','.parquet'}:
                    rows=defaultdict(dict)
                    for obs in cells:
                        ref=obs['source_ref']; rows[(ref.get('sheet'),ref.get('row'))][ref['column']]=(obs['value_text'],obs)
                    with store.connect() as con:
                        schemas={r['sheet']:json.loads(r['schema_json']) for r in con.execute('SELECT * FROM sheets WHERE source_id=?',(sid,))}
                    for (sheet,row),values in rows.items():
                        # Columns absent in a particular row still belong to the layout.
                        schema=schemas[sheet]
                        headers=[c['name'] for c in schema] if isinstance(schema,list) else list(schema)
                        if not any(header_parts(h)[1] for h in headers): continue
                        records.append((doc,sheet,headers,values,row))
                else:
                    values=document_records(cells)
                    native_headers=list(dict.fromkeys(h for record in values for h in record))
                    known=self.template(cmo,fingerprint(doc['doc_type'],None,native_headers,ext)) if values else None
                    if configuration=='clairic_decisions' and not known:
                        values=[]
                        try:
                            extractor=ClairicProvider(model_audit,synthetic=synthetic,approved=approved)
                            for offset in range(0,len(cells),100):
                                chunk=cells[offset:offset+100]
                                reply=extractor.call('extract',{'elements':[{'evidence_id':o['id'],'text':o['value_text']} for o in chunk]},Extraction)
                                lookup={o['id']:o for o in chunk}
                                for review in reply.reviews:
                                    run['extraction_reviews'].append({'path':doc['path'],**review})
                                    issue('EXTRACTION_UNCERTAIN',path=doc['path'],evidence_id=review.get('evidence_id'),
                                          offset=review.get('offset'),message='; '.join(review.get('reasons',[])) or review.get('reason','Extraction requires review'))
                                for field in reply.fields:
                                    obs=lookup.get(field.evidence_id)
                                    if not obs or any(v not in obs['value_text'] for v in [field.value_raw,field.batch,field.time,field.header]):
                                        raise ValueError('Clairic extraction is not supported by the cited source element')
                                    obs={**obs,'model_extracted':True,'extraction_confidence':field.confidence,
                                         'extraction_spans':field.source_spans,'extraction_review_reasons':field.review_reasons}
                                    values.append({'batch_id':(field.batch,obs),'elapsed_h':(field.time,obs),field.header:(field.value_raw,obs)})
                        except (Unavailable,ValueError) as exc:
                            issue('EXTRACTION_UNCERTAIN',path=doc['path'],message=str(exc))
                    headers=list(dict.fromkeys(h for row in values for h in row))
                    for row in values: records.append((doc,None,headers,row,None))
                    if not values: issue('MISSING_FIELD',path=doc['path'],message='No supported measurements extracted from document')
                    # Compare printed totals to actual page count, not extracted line count.
                    if ext=='.pdf':
                        from pypdf import PdfReader
                        original=store.originals/doc['sha256'][:2]/(doc['sha256']+'.pdf')
                        pages=len(PdfReader(original).pages)
                        totals=[int(m[1]) for o in cells for m in re.finditer(r'Page\s+\d+\s+of\s+(\d+)',o['value_text'] or '',re.I)]
                        if totals and max(totals)>pages: issue('MISSING_PAGE',path=doc['path'],expected_pages=max(totals),actual_pages=pages)
            stage('Map')
            layouts={}; seen_layout_change=set(); mappings={}
            mapping_provider=(Provider('mapping',model_audit,synthetic=synthetic,approved=approved)
                              if configuration in {'decisions','clairic_decisions'} else None)
            for doc,sheet,headers,values,row_number in records:
                fp=fingerprint(doc['doc_type'],sheet,headers,Path(doc['path']).suffix.lower())
                template=self.template(cmo,fp)
                if fp not in mappings:
                    proposed=draft_mapping(headers)
                    decisions=[]
                    if template: proposed=Mapping.model_validate_json(template['mapping']).check(headers)
                    elif mapping_provider:
                        try:
                            proposed=mapping_provider.call('map_headers',{'headers':headers,'vocabulary':VOCAB,
                                'sample_rows':[{h:v[0] for h,v in values.items()}]},Mapping).check(headers)
                            decisions=mapping_provider.last_decisions
                            if any(d['status']=='review' for d in decisions):
                                issue('MAPPING_UNCERTAIN',path=doc['path'],message='OpenAI Decisions returned unknown, refusal, ambiguous identifiers, or low confidence')
                        except (Unavailable,ValueError) as exc: issue('MAPPING_UNCERTAIN',path=doc['path'],message=str(exc))
                    mappings[fp]=proposed
                    layout={'fingerprint':fp,'kind':doc['doc_type'],'sheet':sheet,'headers':headers,
                            'mapping':proposed.model_dump(),'decisions':decisions,'template_id':template['id'] if template else None,
                            'confirmed':bool(template),'template_origin':template['origin'] if template else None,
                            'example_source_id':doc['source_id'],'path':doc['path']}
                    layouts[fp]=layout
                    if not template and self.has_kind(cmo,doc['doc_type']):
                        issue('LAYOUT_CHANGED',path=doc['path'],fingerprint=fp)
                        seen_layout_change.add(fp)
                mapping=mappings[fp]; layout=layouts[fp]
                if not mapping.batch_column or not mapping.time_column:
                    issue('MISSING_FIELD',path=doc['path'],row=row_number,message='Batch or time column not mapped')
                batch=values.get(mapping.batch_column,('',None))[0]; elapsed=values.get(mapping.time_column,('',None))[0]
                # Document forms are sparse: their headers describe different records.
                expected=mapping.columns if row_number is not None else {h:p for h,p in mapping.columns.items() if h in values}
                for h,p in expected.items():
                    if h not in values:
                        issue('MISSING_FIELD',path=doc['path'],row=row_number,parameter=p); continue
                    raw,obs=values[h]; unit=header_parts(h)[1]
                    measurement={'id':digest([obs['id'],h,p,batch,elapsed,raw]),'evidence_id':obs['id'],'source_id':obs['source_id'],
                        'source':obs['source_ref'],'source_sha256':doc['sha256'],'parameter':p,
                        'batch':str(batch).strip().upper(),'time':str(elapsed),'value_raw':raw,'unit_raw':unit,
                        'value':None,'unit':VOCAB[p]['unit'],'template_id':layout['template_id'],'fingerprint':fp,
                        'parser':obs['extraction_method'],'source_verified':verification[obs['id']]['value_matches'] is True and verification[obs['id']]['source_integrity'] and not obs.get('model_extracted',False),
                        'status':'needs_review','rule_codes':[],
                        'extraction_confidence':obs.get('extraction_confidence'),
                        'extraction_spans':obs.get('extraction_spans'),
                        'extraction_review_reasons':obs.get('extraction_review_reasons',[])}
                    if not batch or not elapsed: measurement['rule_codes'].append('MISSING_FIELD')
                    try:
                        hour=float(str(elapsed).replace(',','.'))
                        if not math.isfinite(hour) or hour<0: raise ValueError('Invalid elapsed time')
                    except ValueError: measurement['rule_codes'].append('TIME_ORDER')
                    try:
                        measurement['value'],measurement['unit']=normalize(raw,unit,p)
                        lo,hi=VOCAB[p]['range']
                        if not lo<=measurement['value']<=hi: measurement['rule_codes'].append('RANGE')
                    except (ValueError,TypeError): measurement['rule_codes'].append('UNIT_UNKNOWN' if unit is None or unit=='unknown' else 'UNIT_CONVERT')
                    if not measurement['source_verified']: measurement['rule_codes'].append('SOURCE_REVIEW')
                    if unit=='unspecified': measurement['rule_codes'].append('UNIT_UNKNOWN')
                    if not layout['confirmed']: measurement['rule_codes'].append('DRAFT_MAPPING')
                    if fp in seen_layout_change: measurement['rule_codes'].append('LAYOUT_CHANGED')
                    if measurement['value'] is None: measurement['rule_codes'].append('VALUE_INVALID')
                    run['measurements'].append(measurement)
                for h in headers:
                    if h not in mapping.columns and h not in {mapping.batch_column,mapping.time_column}:
                        context={'path':doc['path'],'header':h,'fingerprint':fp}
                        ident=digest(['UNMAPPED_FIELD',context])
                        if not any(i['id']==ident for i in run['issues']): issue('UNMAPPED_FIELD',**context)
            run['layouts']=list(layouts.values())
            stage('Validate')
            by_identity=defaultdict(list); by_doc=defaultdict(list)
            for m in run['measurements']:
                by_identity[(m['batch'],m['time'],m['parameter'])].append(m)
                by_doc[m['source']['path']].append(m)
            for group in by_identity.values():
                numbers=[m['value'] for m in group if m['value'] is not None]
                if numbers and any(not math.isclose(n,numbers[0],rel_tol=1e-12,abs_tol=0) for n in numbers):
                    for m in group: m['rule_codes'].append('DUPLICATE_CONFLICT')
                    issue('DUPLICATE_CONFLICT',path=group[-1]['source']['path'],batch=group[0]['batch'],
                          parameter=group[0]['parameter'],time=group[0]['time'])
            process_batches={m['batch'] for m in run['measurements'] if next(d for d in run['documents'] if d['source_id']==m['source_id'])['doc_type']=='instrument_export'}
            for path,items in by_doc.items():
                for m in items:
                    if process_batches and m['batch'] not in process_batches:
                        m['rule_codes'].append('BATCH_MISMATCH'); issue('BATCH_MISMATCH',path=path,batch=m['batch'])
                structured=[m for m in items if m['source'].get('row') is not None]
                times=defaultdict(list)
                for m in structured:
                    if m['parameter']!=structured[0]['parameter']: continue
                    try: times[m['batch']].append((m['source']['row'],float(m['time'])))
                    except ValueError: m['rule_codes'].append('TIME_ORDER')
                for batch,entries in times.items():
                    sequence=[t for _,t in sorted(entries)]
                    if any(b<a for a,b in zip(sequence,sequence[1:])):
                        issue('TIME_ORDER',path=path,batch=batch)
                        for m in items:
                            if m['batch']==batch: m['rule_codes'].append('TIME_ORDER')
            for m in run['measurements']:
                blocking=[i['rule_code'] for i in run['issues'] if i.get('path')==m['source']['path']]
                m['rule_codes']=sorted(set(m['rule_codes']+blocking))
                if not m['rule_codes']: m['status']='auto_accepted'
                m['confidence']=0.0 if m['value'] is None else min(1 if m['template_id'] else 0.6,
                    1 if m['source_verified'] else 0.5,1 if not m['rule_codes'] else 0.5)
            relationships=[]
            by_batch=defaultdict(set)
            for m in run['measurements']: by_batch[m['batch']].add(m['source']['path'])
            for batch,paths in by_batch.items():
                process_paths=[d['path'] for d in run['documents'] if d['doc_type']=='instrument_export' and d['path'] in paths]
                for path in sorted(paths):
                    for process_path in process_paths:
                        if path!=process_path:
                            relationships.append({'left':path,'right':process_path,'batch':batch,'relation':'batch_evidence',
                                'status':'candidate' if any(i['rule_code']=='BATCH_MISMATCH' and i.get('path')==path for i in run['issues']) else 'source_linked'})
            run['relationships']=relationships
            stage('Review','pending' if any(m['status']=='needs_review' for m in run['measurements']) or run['issues'] else 'complete')
            stage('Store/Export','complete')
            run.update(status='complete',runtime_seconds=time.monotonic()-started,completed_at=utc())
            self.summarize(run); self.save(run)
            self.audit('run_completed',run_id=run['id'],configuration=configuration,summary=run['summary'])
            return run
        except Exception as exc:
            run.update(status='failed',error=f'{type(exc).__name__}: {exc}',runtime_seconds=time.monotonic()-started)
            self.save(run); self.audit('run_failed',run_id=run['id'],error=run['error'])
            return run

    def summarize(self,run):
        measures=run['measurements']; accepted=[m for m in measures if m['status'] in {'auto_accepted','accepted','corrected'}]
        run['summary']={'measurements':len(measures),'auto_accepted':sum(m['status']=='auto_accepted' for m in measures),
            'accepted':len(accepted),'needs_review':sum(m['status']=='needs_review' for m in measures),
            'open_issues':sum(i['status']=='open' for i in run['issues']),
            'corrections':sum(r['decision']=='correct' for r in run['reviews']),'model_calls':len(run['model_usage']),
            'inference_cost_usd':sum(x['cost_usd'] for x in run['model_usage']) if all(x['cost_usd'] is not None for x in run['model_usage']) else None,
            'input_tokens':sum(x['input_tokens'] for x in run['model_usage']) if all(x['input_tokens'] is not None for x in run['model_usage']) else None,
            'output_tokens':sum(x['output_tokens'] for x in run['model_usage']) if all(x['output_tokens'] is not None for x in run['model_usage']) else None,
            'verified_package':bool(measures) and all(m['status'] in {'auto_accepted','accepted','corrected','rejected'} for m in measures) and not any(i['status']=='open' for i in run['issues'])}

    def review(self,run_id,measurement_id,decision,actor,reason,*,binding,value=None,parameter=None,unit=None,batch=None,time_value=None):
        if decision not in {'accept','correct','reject'}: raise ValueError('Invalid review decision')
        if not actor.strip() or not reason.strip(): raise ValueError('Actor and review reason are required')
        with self._lock:
            run=self.get(run_id); m=next((m for m in run['measurements'] if m['id']==measurement_id),None)
            if not m:
                if any(x['id']==measurement_id for x in run.get('superseded_measurements',[])):
                    raise ValueError('Review binding changed; measurement was superseded, reopen the current source')
                raise KeyError('Unknown measurement')
            if binding != digest(m): raise ValueError('Review binding changed; reopen the current source')
            self.original(run_id,m['source_id']) # verify original bytes still match before signing
            if decision!='reject' and m['source']['path'].lower().endswith('.pdf') and not m['source'].get('page'):
                raise ValueError('PDF value lacks a precise page citation; source localization is required before acceptance')
            revised=dict(m)
            if decision=='correct':
                if value is None: raise ValueError('Corrected value is required')
                p=parameter or m['parameter']
                if p not in VOCAB: raise ValueError('Unknown canonical parameter')
                n,u=normalize(value,unit or m['unit'],p)
                # A real excursion is not a transcription error. Preserve the
                # review warning while allowing an explicitly reasoned correction.
                if not VOCAB[p]['range'][0]<=n<=VOCAB[p]['range'][1]:
                    revised['rule_codes']=list(dict.fromkeys([*m['rule_codes'],'RANGE']))
                revised.update(value=n,unit=u,parameter=p,status='corrected')
                if batch is not None: revised['batch']=batch.strip().upper()
                if time_value is not None: revised['time']=str(time_value).strip()
                revised['id']=uuid.uuid4().hex
                revised['supersedes']=m['id']
                run.setdefault('superseded_measurements',[]).append({**m,'status':'superseded','superseded_by':revised['id']})
            else: revised['status']='accepted' if decision=='accept' else 'rejected'
            if decision=='accept' and m['value'] is None: raise ValueError('Invalid numeric value must be corrected or rejected')
            if decision!='reject':
                if not revised['batch']: raise ValueError('Batch identity is required before acceptance')
                try:
                    elapsed=float(revised['time'].replace(',','.'))
                    if not math.isfinite(elapsed) or elapsed<0: raise ValueError('Invalid process hour')
                except ValueError: raise ValueError('Invalid process hour must be corrected before acceptance')
            receipt={'at':utc(),'actor':actor,'reason':reason,'decision':decision,'before':m,'after':revised}
            run['reviews'].append(receipt)
            run['measurements']=[revised if x['id']==measurement_id else x for x in run['measurements']]
            self.audit('measurement_review',run_id=run_id,**receipt)
            self.summarize(run); self.save(run); return run

    def resolve_issue(self,run_id,issue_id,actor,reason):
        if not actor.strip() or not reason.strip(): raise ValueError('Actor and disposition reason required')
        with self._lock:
            run=self.get(run_id); issue=next((i for i in run['issues'] if i['id']==issue_id),None)
            if not issue: raise KeyError('Unknown issue')
            issue.update(status='resolved',actor=actor,reason=reason,at=utc())
            self.audit('issue_disposition',run_id=run_id,issue=issue)
            self.summarize(run); self.save(run); return run

    def original(self,run_id,source_id):
        run=self.get(run_id); doc=next((d for d in run['documents'] if d['source_id']==source_id),None)
        if not doc: raise KeyError('Unknown source')
        store=ManufacturingStore(run['store'])
        path=store.originals/doc['sha256'][:2]/(doc['sha256']+Path(doc['path']).suffix.lower())
        with path.open('rb') as stream: hashed=hashlib.file_digest(stream,'sha256').hexdigest()
        if hashed!=doc['sha256']: raise ValueError('Source integrity failed')
        return path,doc

    def export(self,run_id,*,format='csv',wide=False):
        run=self.get(run_id)
        for source_id in {m['source_id'] for m in run['measurements'] if m['status'] in {'accepted','auto_accepted','corrected'}}:
            self.original(run_id,source_id)
        rows=[{'batch':m['batch'],'time':m['time'],'parameter':m['parameter'],'value':m['value'],'unit':m['unit'],
               'value_raw':m['value_raw'],'unit_raw':m['unit_raw'],'status':m['status'],'source':json.dumps(m['source'],sort_keys=True),
               'source_sha256':m['source_sha256'],'evidence_id':m['evidence_id']} for m in run['measurements'] if m['status'] in {'accepted','auto_accepted','corrected'}]
        if wide:
            # Keep multiple sources instead of silently overwriting duplicate measurements.
            groups=defaultdict(dict)
            for row in rows:
                name=row['parameter']; ident=(row['batch'],row['time'])
                group=groups[ident]; group.update(batch=row['batch'],time=row['time'])
                if name in group and group[name]!=row['value']: raise ValueError('Wide export has conflicting accepted values')
                group[name]=row['value']; group[name+'_unit']=row['unit']
                group[name+'_sources']=group.get(name+'_sources','')+row['source']+'\n'
            rows=list(groups.values())
        headers=list(dict.fromkeys(k for row in rows for k in row)) or ['batch','time','parameter','value','unit','source']
        if format=='xlsx':
            from openpyxl import Workbook
            book=Workbook(); sheet=book.active; sheet.title='Verified measurements'; sheet.append(headers)
            for row in rows: sheet.append([self.safe_cell(row.get(h,'')) for h in headers])
            output=io.BytesIO(); book.save(output); return output.getvalue()
        if format!='csv': raise ValueError('Unsupported export format')
        output=io.StringIO(newline=''); writer=csv.DictWriter(output,fieldnames=headers); writer.writeheader()
        writer.writerows({k:self.safe_cell(v) for k,v in row.items()} for row in rows)
        return output.getvalue().encode()

    @staticmethod
    def safe_cell(value):
        if isinstance(value,str) and (value[:1] in {'\t','\r','\n'} or value.lstrip()[:1] in {'=','+','-','@'}):
            return "'"+value
        return value
