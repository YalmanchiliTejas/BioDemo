"""Fixed ingestion workflow extending ManufacturingStore; no investigation runtime.

The evaluator and answer keys are intentionally absent from this module.

Zero silent errors: every non-empty source element ends as a value, an
identifier, a reviewer-confirmed exclusion, or a visible issue (see
``quality.py``). Only values from a confirmed mapping that match their original
bytes and pass every check are accepted without a person.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import re
import threading
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from ..ingest import ingest_package
from ..store import ManufacturingStore
from ..verification import verify_originals
from . import quality
from .classify import by_content, by_filename
from .evidence import evidence_store, original_key, restore
from .persistence import SQLiteRepository, repository
from .providers import ClairicProvider, Provider, Unavailable
from .schema import Classification, Extraction, Mapping, TYPES, VOCAB, draft_mapping, header_parts, key, normalize, time_key

STAGES = ['Ingest','Classify','Parse','Map','Validate','Review','Store/Export']
CONFIGURATIONS = {'auto':'Best available: hosted extraction when configured and approved, otherwise local deterministic parsing',
                  'clairic_decisions':'Docling + Clairic extraction + OpenAI Decisions classification/mapping', 'decisions':'Docling + OpenAI Decisions (classification and mapping)', 'A':'Docling + generative mapping','B':'Docling + Clairic',
                  'C':'Docling + Clairic + Jev','D':'Confirmed deterministic templates',
                  'preview':'Available local parsers + draft aliases (diagnostic baseline)'}
STRUCTURED={'.csv','.xlsx','.xlsm','.tsv','.parquet'}
# Issues that make every value from the same file unsafe to accept unreviewed.
# Coverage and delivery-completeness issues block package verification instead.
NON_BLOCKING_FOR_VALUES={'UNACCOUNTED_CONTENT','UNRECOGNIZED_TABLE','BATCH_DOCUMENT_MISSING','EXPECTED_DOCUMENT_MISSING','EXPECTED_PARAMETER_MISSING'}


# Already attached to exactly the affected values during validation.
VALUE_TAGGED={'DUPLICATE_CONFLICT','DUPLICATE_RECORD','TIME_ORDER','BATCH_MISMATCH'}


def blocks(issue, measurement):
    """Whether an open issue makes a value unsafe to accept without review.

    Scoped to what the issue endangers: a missing cell or an unmapped column
    blocks nothing else, layout issues block that layout, and
    file-level problems (parse errors, missing pages, uncertain classification
    or extraction) block the whole file."""
    code=issue['rule_code']
    if code in NON_BLOCKING_FOR_VALUES or code in VALUE_TAGGED or code=='UNMAPPED_FIELD': return False
    if issue.get('path')!=measurement['source']['path']: return False
    if issue.get('fingerprint') and issue['fingerprint']!=measurement['fingerprint']: return False
    # A blank cell is a visible absence; it does not cast doubt on its neighbours.
    if code=='MISSING_FIELD' and issue.get('row') is not None: return False
    return True
# Minimum header overlap for proposing a changed layout from a confirmed template.
REUSE_OVERLAP=0.5


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',',':'),allow_nan=False).encode()).hexdigest()


def utc(): return datetime.now(timezone.utc).isoformat()


def classify(path):
    return by_filename(path)


def hosted_inference_approved():
    """Organization-level approval to send customer files to the configured
    hosted extraction providers. Off unless an administrator sets it."""
    return os.getenv('CMO_HOSTED_INFERENCE_APPROVED','').strip().lower() in {'1','true','yes'}


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
    # Ordered headers and sheet names are structural for tables, including Raman
    # channel IDs. In printed documents the order of extracted lines varies with
    # text layout, so the set of fields identifies the form.
    names=[key(h) for h in headers]
    if extension.lower() not in STRUCTURED: names=sorted(names)
    return digest({'kind':kind,'sheet':sheet,'headers':names,'format':extension})


class IngestionService:
    def __init__(self, root):
        from .settings import load_local_settings
        load_local_settings()
        self.root=Path(root).resolve(); self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        # Local SQLite file. CaseService keeps its own tables here even when the
        # ingestion records live in PostgreSQL.
        self.db=self.root/'cmo.sqlite'; self._lock=threading.RLock()
        self.repo=repository(self.root)
        self.evidence=evidence_store()

    def connect(self):
        if not isinstance(self.repo,SQLiteRepository): raise RuntimeError('Direct SQL access is only available for the local SQLite backend')
        return self.repo.connect()

    def audit(self, action, **data):
        payload=json.dumps({'at':utc(),'action':action,**data},sort_keys=True,allow_nan=False)
        return self.repo.append_event(payload)

    def verify_audit(self):
        prev='0'*64
        for row in self.repo.events():
            expected=hashlib.sha256((prev+row['payload']).encode()).hexdigest()
            if row['prev_hash']!=prev or row['hash']!=expected: return False
            prev=row['hash']
        return True

    def template(self,cmo,fp): return self.repo.template(cmo,fp)

    def has_kind(self,cmo,kind): return bool(self.repo.templates(cmo,kind))

    def closest_template(self,cmo,kind,headers):
        """Latest confirmed template of the same document kind sharing most headers."""
        best=None; best_overlap=0
        current=set(headers)
        for template in self.repo.templates(cmo,kind):
            previous=set(json.loads(template['headers']))
            overlap=len(previous&current)/len(previous|current) if previous|current else 0
            if overlap>=REUSE_OVERLAP and (overlap>best_overlap or (overlap==best_overlap and best and template['at']>=best['at'])):
                best,best_overlap=template,overlap
        return best

    def confirm_template(self,run_id,fp,mapping,actor,reason,*,origin='human'):
        if not actor.strip() or not reason.strip(): raise ValueError('Actor and reason are required')
        run=self.get(run_id)
        draft=next((d for d in run['layouts'] if d['fingerprint']==fp),None)
        if not draft: raise ValueError('Layout is absent from this run')
        parsed=Mapping.model_validate(mapping).check(draft['headers'])
        accounted={*parsed.columns,*parsed.ignored_columns,*filter(None,[parsed.batch_column,parsed.time_column])}
        ignore_only=not parsed.columns and accounted>=set(draft['headers'])
        if not ignore_only and (not parsed.columns or not parsed.batch_column or not parsed.time_column):
            raise ValueError('Confirm parameter, batch and time mappings explicitly, or ignore every column of a table that holds no process data')
        existing=self.template(run['cmo'],fp); version=existing['version']+1 if existing else 1
        template={'id':uuid.uuid4().hex,'cmo':run['cmo'],'fingerprint':fp,'kind':draft['kind'],'version':version,
                  'mapping':parsed.model_dump_json(),'headers':json.dumps(draft['headers']),
                  'actor':actor,'at':utc(),'origin':origin}
        self.repo.insert_template(template)
        self.audit('template_confirmed',template=template,run_id=run_id,reason=reason)
        return template

    def add_ignore_rule(self,cmo,line_pattern,actor,reason,*,run_id=None):
        if not actor.strip() or not reason.strip(): raise ValueError('Actor and reason are required')
        if not line_pattern.strip() or not re.search(r'[A-Za-z]',line_pattern):
            raise ValueError('Ignore rules need a text pattern; a bare number would hide data')
        rule={'id':uuid.uuid4().hex,'cmo':cmo,'pattern':line_pattern.strip(),'actor':actor,'reason':reason,'at':utc(),'run_id':run_id}
        self.repo.add_ignore_rule(rule); self.audit('ignore_rule_added',rule=rule)
        return rule

    def save(self,run): self.repo.save_run(run)

    def get(self,run_id): return self.repo.get_run(run_id)

    def runs(self,cmo=None): return sorted(self.repo.runs(cmo),key=lambda r:r.get('started_at',''))

    def previous_verified(self,cmo,exclude):
        verified=[r for r in self.runs(cmo) if r['id']!=exclude and r.get('status')=='complete'
                  and (r.get('summary') or {}).get('verified_package') and not r.get('superseded_by')]
        return verified[-1] if verified else None

    @staticmethod
    def resolve_configuration(configuration,*,synthetic=False,approved=False):
        if configuration!='auto': return configuration,[]
        notes=[]
        for candidate in ['clairic_decisions','decisions']:
            reasons=IngestionService.availability(candidate,synthetic=synthetic,approved=approved)
            if not reasons: return candidate,notes
            notes.append(f'{candidate} unavailable: '+'; '.join(reasons))
        return 'D',notes

    @staticmethod
    def availability(configuration,*,synthetic=False,approved=False):
        import importlib.util
        if configuration not in CONFIGURATIONS: raise ValueError('Unknown extraction configuration')
        if configuration=='auto': return []
        if configuration in {'A','B','C'}:
            return ['Historical configuration retired; select clairic_decisions for Clairic extraction and OpenAI Decisions']
        reasons=[]
        if configuration in {'decisions','clairic_decisions'}:
            if importlib.util.find_spec('docling') is None: reasons.append('Docling is not installed')
            artifacts=os.getenv('DOCLING_ARTIFACTS_PATH')
            if not artifacts or not Path(artifacts).is_dir():
                from benchmarks.common.artifact_store import descriptor_for, ROOT as backend_root
                target=artifacts or backend_root/'.cache/cmo-docling-models/docling-project--docling-models'
                try: remote,_=descriptor_for(target)
                except OSError: remote=None
                if remote is None: reasons.append('DOCLING_ARTIFACTS_PATH needs local models or a registered DagsHub model artifact')
            try: Provider('mapping',lambda _:None,synthetic=synthetic,approved=approved)
            except (Unavailable,ValueError) as exc: reasons.append(str(exc))
        if configuration=='clairic_decisions':
            try: ClairicProvider(lambda _:None,synthetic=synthetic,approved=approved)
            except (Unavailable,ValueError) as exc: reasons.append(str(exc))
        return reasons

    def run(self,package,cmo,configuration='preview',*,synthetic=False,approved=False,run_id=None,on_stage=None,project_context=None,package_ref=None):
        # Inference weights must be provisioned locally. Parsing a customer file
        # must never trigger telemetry or a model-weight download.
        os.environ.setdefault('HF_HUB_OFFLINE','1')
        os.environ.setdefault('TRANSFORMERS_OFFLINE','1')
        os.environ.setdefault('HF_HUB_DISABLE_TELEMETRY','1')
        os.environ.setdefault('DO_NOT_TRACK','1')
        package=Path(package).resolve()
        if not cmo.strip(): raise ValueError('CMO name is required')
        started=time.monotonic()
        requested=configuration
        configuration,resolution_notes=self.resolve_configuration(configuration,synthetic=synthetic,approved=approved)
        run={'id':run_id or uuid.uuid4().hex,'cmo':cmo,'configuration':configuration,'requested_configuration':requested,
             'configuration_notes':resolution_notes,'package_ref':package_ref,
             'hosted_inference':{'approved':bool(approved),'synthetic':bool(synthetic),
                                 'basis':'synthetic data' if synthetic else ('deployment approval CMO_HOSTED_INFERENCE_APPROVED' if approved else 'not approved; local parsing only')},
             'started_at':utc(),'status':'running','synthetic':synthetic,'stages':[],
             'layouts':[],'measurements':[],'issues':[],'documents':[],'model_usage':[],'extraction_reviews':[],
             'human_minutes':None,'human_time_status':'not_measured','reviews':[],'elements':[]}
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
            ident=digest([code,context])
            if any(i['id']==ident for i in run['issues']): return
            run['issues'].append({'id':ident,'rule_code':code,'status':'open',**context})
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
            for source in sources.values():
                suffix=Path(source['path']).suffix.lower()
                self.evidence.put(original_key(source['sha256'],suffix),store.originals/source['sha256'][:2]/(source['sha256']+suffix))
            grouped=defaultdict(list)
            for obs in observations: grouped[obs['source_id']].append(obs)
            routes={r['path']:r for r in ingestion['routes']}
            classifier=Provider('classification',model_audit,synthetic=synthetic,approved=approved) if configuration in {'decisions','clairic_decisions'} else None
            for sid,source in sources.items():
                kind=classify(source['path']); method='filename' if kind!='other' else None; evidence=None
                ext=Path(source['path']).suffix.lower()
                candidate_layouts=[]
                if ext in STRUCTURED:
                    with store.connect() as con:
                        for entry in con.execute('SELECT sheet,schema_json FROM sheets WHERE source_id=?',(sid,)):
                            schema=json.loads(entry['schema_json'])
                            candidate_layouts.append((entry['sheet'],[c['name'] for c in schema] if isinstance(schema,list) else list(schema)))
                else:
                    native=document_records(grouped[sid])
                    if native: candidate_layouts.append((None,list(dict.fromkeys(h for row in native for h in row))))
                if kind=='other':
                    # Recover a confirmed classification only from the full layout,
                    # never from a filename cache that could hide a changed form.
                    matches=[{t for t in TYPES if self.template(cmo,fingerprint(t,sheet,headers,ext))}
                             for sheet,headers in candidate_layouts]
                    if matches and all(len(m)==1 for m in matches) and len(set.union(*matches))==1:
                        kind=next(iter(matches[0])); method='confirmed_template'
                if kind=='other':
                    lines=[o['value_text'] for o in grouped[sid] if (o['source_ref'].get('page') or 1)<=2][:80] if ext not in STRUCTURED else []
                    headers=[h for _,hs in candidate_layouts for h in hs]
                    kind,evidence=by_content(lines,headers)
                    method='content' if kind!='other' else None
                if classifier and kind=='other':
                    try:
                        reply=classifier.call('classify',{'filename':source['path'],
                            'text':[o['value_text'] for o in grouped[sid] if (o['source_ref'].get('page') or 1)<=2][:40]},Classification)
                        if reply.doc_type not in TYPES: raise ValueError('Unknown document class')
                        kind=reply.doc_type if reply.confidence>=0.95 else 'other'
                        method='model' if kind!='other' else None
                    except (Unavailable,ValueError) as exc: issue('CLASSIFICATION_UNCERTAIN',path=source['path'],message=str(exc))
                run['documents'].append({'source_id':sid,'path':source['path'],'doc_type':kind,'classification_method':method or 'none',
                    'classification_evidence':evidence,'sha256':source['sha256'],'route':routes.get(source['path'],{}),
                    'extraction_status':source.get('extraction_status')})
                if kind=='other': issue('CLASSIFICATION_UNCERTAIN',path=source['path'])
            stage('Parse')
            verification=verify_originals(store,observations)
            ignore_patterns={rule['pattern'] for rule in self.repo.ignore_rules(cmo)}
            elements={}
            def element(obs,doc,**extra):
                ref=obs['source_ref']
                elements[obs['id']]={'id':obs['id'],'path':doc['path'],'sheet':ref.get('sheet'),'column':ref.get('column'),
                                     'row':ref.get('row'),'page':ref.get('page'),'state':'pending',**extra}
            records=[]
            for doc in run['documents']:
                sid=doc['source_id']; cells=grouped[sid]; ext=Path(doc['path']).suffix.lower()
                if not cells:
                    # A file with no readable content is itself unaccounted information.
                    elements['file:'+doc['path']]={'id':'file:'+doc['path'],'path':doc['path'],'sheet':None,'column':None,
                                                   'row':None,'page':None,'state':'pending'}
                    if not any(i['rule_code']=='PARSE_ERROR' and i.get('path')==doc['path'] for i in run['issues']):
                        issue('UNACCOUNTED_CONTENT',path=doc['path'],lines=[],count=1,
                              message='No readable content was extracted from this file; inspect the original')
                    continue
                if ext in STRUCTURED:
                    rows=defaultdict(dict)
                    for obs in cells:
                        ref=obs['source_ref']; rows[(ref.get('sheet'),ref.get('row'))][ref['column']]=(obs['value_text'],obs)
                        element(obs,doc)
                    with store.connect() as con:
                        schemas={r['sheet']:json.loads(r['schema_json']) for r in con.execute('SELECT * FROM sheets WHERE source_id=?',(sid,))}
                    for (sheet,row),values in rows.items():
                        # Columns absent in a particular row still belong to the layout.
                        schema=schemas[sheet]
                        headers=[c['name'] for c in schema] if isinstance(schema,list) else list(schema)
                        records.append((doc,sheet,headers,values,row))
                else:
                    for obs in cells:
                        element(obs,doc)
                        if quality.pattern(obs['value_text']) in ignore_patterns: elements[obs['id']]['state']='ignored'
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
                    for record in values:
                        for header,(_raw,obs) in record.items():
                            if header not in {'batch_id','elapsed_h'} and obs['id'] in elements: elements[obs['id']]['column']=header
                    headers=list(dict.fromkeys(h for row in values for h in row))
                    # A document with no extracted values needs no separate flag: each
                    # of its lines is listed under UNACCOUNTED_CONTENT below.
                    for row in values: records.append((doc,None,headers,row,None))
                    # Compare printed totals to actual page count, not extracted line count.
                    if ext=='.pdf':
                        from pypdf import PdfReader
                        original=store.originals/doc['sha256'][:2]/(doc['sha256']+'.pdf')
                        pages=len(PdfReader(original).pages)
                        totals=[int(m[1]) for o in cells for m in re.finditer(r'Page\s+\d+\s+of\s+(\d+)',o['value_text'] or '',re.I)]
                        if totals and max(totals)>pages: issue('MISSING_PAGE',path=doc['path'],expected_pages=max(totals),actual_pages=pages)
            stage('Map')
            layouts={}; seen_layout_change=set(); mappings={}; unrecognized=set()
            mapping_provider=(Provider('mapping',model_audit,synthetic=synthetic,approved=approved)
                              if configuration in {'decisions','clairic_decisions'} else None)
            for doc,sheet,headers,values,row_number in records:
                fp=fingerprint(doc['doc_type'],sheet,headers,Path(doc['path']).suffix.lower())
                template=self.template(cmo,fp)
                if fp not in mappings:
                    proposed=draft_mapping(headers)
                    decisions=[]; based_on=None
                    if template: proposed=Mapping.model_validate_json(template['mapping']).check(headers)
                    else:
                        closest=self.closest_template(cmo,doc['doc_type'],headers)
                        if closest:
                            # Propose the confirmed meaning for every header that is
                            # literally unchanged; new headers fall back to aliases.
                            previous=Mapping.model_validate_json(closest['mapping'])
                            shared=set(headers)&set(json.loads(closest['headers']))
                            proposed=Mapping(
                                columns={**{h:p for h,p in proposed.columns.items() if h not in shared},
                                         **{h:p for h,p in previous.columns.items() if h in shared}},
                                batch_column=previous.batch_column if previous.batch_column in shared else proposed.batch_column,
                                time_column=previous.time_column if previous.time_column in shared else proposed.time_column,
                                units={h:u for h,u in previous.units.items() if h in shared},
                                ignored_columns=[h for h in previous.ignored_columns if h in shared]).check(headers)
                            old=json.loads(closest['headers'])
                            based_on={'template_id':closest['id'],'version':closest['version'],
                                      'added_headers':[h for h in headers if h not in old],
                                      'removed_headers':[h for h in old if h not in headers],
                                      'reused_headers':sorted(shared)}
                        if mapping_provider:
                            try:
                                suggested=mapping_provider.call('map_headers',{'headers':headers,'vocabulary':VOCAB,
                                    'sample_rows':[{h:v[0] for h,v in values.items()}]},Mapping).check(headers)
                                decisions=mapping_provider.last_decisions
                                # Confirmed meanings for unchanged headers outrank model proposals.
                                keep=set(based_on['reused_headers']) if based_on else set()
                                proposed=Mapping(columns={**{h:p for h,p in suggested.columns.items() if h not in keep},
                                                          **{h:p for h,p in proposed.columns.items() if h in keep}},
                                                 batch_column=proposed.batch_column if proposed.batch_column in keep else suggested.batch_column or proposed.batch_column,
                                                 time_column=proposed.time_column if proposed.time_column in keep else suggested.time_column or proposed.time_column,
                                                 units=proposed.units,ignored_columns=proposed.ignored_columns).check(headers)
                                if any(d['status']=='review' for d in decisions):
                                    issue('MAPPING_UNCERTAIN',path=doc['path'],message='OpenAI Decisions returned unknown, refusal, ambiguous identifiers, or low confidence')
                            except (Unavailable,ValueError) as exc: issue('MAPPING_UNCERTAIN',path=doc['path'],message=str(exc))
                    mappings[fp]=proposed
                    layout={'fingerprint':fp,'kind':doc['doc_type'],'sheet':sheet,'headers':headers,
                            'mapping':proposed.model_dump(),'decisions':decisions,'template_id':template['id'] if template else None,
                            'template_version':template['version'] if template else None,
                            'confirmed':bool(template),'template_origin':template['origin'] if template else None,
                            'based_on':based_on,'example_source_id':doc['source_id'],'path':doc['path'],'records':0}
                    layouts[fp]=layout
                    tabular_without_parameters=not template and not proposed.columns and row_number is not None
                    if not template and not tabular_without_parameters and self.has_kind(cmo,doc['doc_type']):
                        issue('LAYOUT_CHANGED',path=doc['path'],fingerprint=fp)
                        seen_layout_change.add(fp)
                    if tabular_without_parameters:
                        unrecognized.add(fp)
                        issue('UNRECOGNIZED_TABLE',path=doc['path'],sheet=sheet,fingerprint=fp,headers=headers,
                              message='No column matches a known process parameter. Map columns or ignore the table.')
                    elif proposed.columns and (not proposed.batch_column or not proposed.time_column):
                        issue('MISSING_FIELD',path=doc['path'],fingerprint=fp,message='Batch or time column not mapped')
                mapping=mappings[fp]; layout=layouts[fp]; layout['records']+=1
                ignored=set(mapping.ignored_columns)
                for h,(_raw,obs) in values.items():
                    target=elements.get(obs['id'])
                    if not target or target['state']=='ignored': continue
                    if row_number is not None and h in ignored: target['state']='ignored'
                    elif row_number is not None and h in {mapping.batch_column,mapping.time_column}: target['state']='identifier'
                if fp in unrecognized: continue
                batch=values.get(mapping.batch_column,('',None))[0]; elapsed=values.get(mapping.time_column,('',None))[0]
                # Document forms are sparse: their headers describe different records.
                expected=mapping.columns if row_number is not None else {h:p for h,p in mapping.columns.items() if h in values}
                for h,p in expected.items():
                    if h not in values:
                        issue('MISSING_FIELD',path=doc['path'],row=row_number,parameter=p); continue
                    raw,obs=values[h]
                    unit=header_parts(h)[1]; declared=mapping.units.get(h)
                    if declared and layout['confirmed']: unit=declared
                    measurement={'id':digest([obs['id'],h,p,batch,elapsed,raw]),'evidence_id':obs['id'],'source_id':obs['source_id'],
                        'source':obs['source_ref'],'source_sha256':doc['sha256'],'parameter':p,
                        'batch':str(batch).strip().upper(),'time':str(elapsed),'value_raw':raw,'unit_raw':header_parts(h)[1],
                        'unit_declared':declared if declared and layout['confirmed'] else None,
                        'value':None,'unit':VOCAB[p]['unit'],'template_id':layout['template_id'],'fingerprint':fp,
                        'parser':obs['extraction_method'],'source_verified':verification[obs['id']]['value_matches'] is True and verification[obs['id']]['source_integrity'] and not obs.get('model_extracted',False),
                        'status':'needs_review','rule_codes':[],
                        'extraction_confidence':obs.get('extraction_confidence'),
                        'extraction_spans':obs.get('extraction_spans'),
                        'extraction_review_reasons':obs.get('extraction_review_reasons',[])}
                    if obs['id'] in elements: elements[obs['id']]['state']='measurement'
                    if not batch or not elapsed: measurement['rule_codes'].append('MISSING_FIELD')
                    try: time_key(elapsed)
                    except ValueError: measurement['rule_codes'].append('TIME_ORDER')
                    try:
                        measurement['value'],measurement['unit']=normalize(raw,unit,p)
                        lo,hi=VOCAB[p]['range']
                        if not lo<=measurement['value']<=hi: measurement['rule_codes'].append('RANGE')
                    except (ValueError,TypeError): measurement['rule_codes'].append('UNIT_UNKNOWN' if unit is None or unit=='unknown' else 'UNIT_CONVERT')
                    if not measurement['source_verified']: measurement['rule_codes'].append('SOURCE_REVIEW')
                    if unit=='unspecified' and not measurement['unit_declared']: measurement['rule_codes'].append('UNIT_UNKNOWN')
                    if not layout['confirmed']: measurement['rule_codes'].append('DRAFT_MAPPING')
                    if fp in seen_layout_change: measurement['rule_codes'].append('LAYOUT_CHANGED')
                    if measurement['value'] is None: measurement['rule_codes'].append('VALUE_INVALID')
                    run['measurements'].append(measurement)
                for h in headers:
                    if h not in mapping.columns and h not in {mapping.batch_column,mapping.time_column} and h not in ignored:
                        if row_number is None and h in {'batch_id','elapsed_h'}: continue
                        count=sum(1 for e in elements.values() if e['path']==doc['path'] and e['column']==h and e['sheet']==sheet)
                        issue('UNMAPPED_FIELD',path=doc['path'],header=h,fingerprint=fp,**({'sheet':sheet} if sheet else {}),
                              **({'elements':count} if row_number is not None else {}))
            run['layouts']=list(layouts.values())
            leftover=defaultdict(list)
            for e in elements.values():
                if e['state']=='pending' and Path(e['path']).suffix.lower() not in STRUCTURED and not e['id'].startswith('file:') and e['column'] is None:
                    leftover[e['path']].append(e)
            texts={o['id']:o['value_text'] for o in observations}
            for path,items in leftover.items():
                lines=[{'element_id':e['id'],'page':e['page'],'text':texts.get(e['id'],''),'pattern':quality.pattern(texts.get(e['id'],''))} for e in items]
                issue('UNACCOUNTED_CONTENT',path=path,count=len(items),lines=lines[:500],truncated=len(lines)>500,
                      message=f'{len(items)} text element(s) were not converted into values. Read them, or ignore recurring boilerplate for future deliveries.')
            stage('Validate')
            by_identity=defaultdict(list); by_doc=defaultdict(list)
            for m in run['measurements']:
                try: identity=(m['batch'],time_key(m['time']),m['parameter'])
                except ValueError: identity=(m['batch'],m['time'],m['parameter'])
                by_identity[identity].append(m)
                by_doc[m['source']['path']].append(m)
            suspect_rows=set()
            for group in by_identity.values():
                numbers=[m['value'] for m in group if m['value'] is not None]
                if numbers and any(not math.isclose(n,numbers[0],rel_tol=1e-12,abs_tol=0) for n in numbers):
                    for m in group:
                        m['rule_codes'].append('DUPLICATE_CONFLICT')
                        if m['source'].get('row') is not None: suspect_rows.add((m['source']['path'],m['source'].get('sheet'),m['source']['row']))
                    issue('DUPLICATE_CONFLICT',path=group[-1]['source']['path'],batch=group[0]['batch'],
                          parameter=group[0]['parameter'],time=group[0]['time'])
            for group in by_identity.values():
                numbers=[m['value'] for m in group if m['value'] is not None]
                if len(group)<2 or (numbers and any(not math.isclose(n,numbers[0],rel_tol=1e-12,abs_tol=0) for n in numbers)): continue
                # Agreement across documents corroborates; a repeat inside one
                # file is a duplicated record that a person should resolve.
                paths=defaultdict(list)
                for m in group: paths[m['source']['path']].append(m)
                for path,repeated in paths.items():
                    if len(repeated)>1:
                        for m in repeated: m['rule_codes'].append('DUPLICATE_RECORD')
                        rows={(m['source']['path'],m['source'].get('sheet'),m['source'].get('row')) for m in repeated}
                        # Rows already held by a conflict need no second item to review.
                        if not rows<=suspect_rows:
                            issue('DUPLICATE_RECORD',path=path,batch=group[0]['batch'],parameter=group[0]['parameter'],time=group[0]['time'])
            # Other values on a row holding a conflicting value share its doubt.
            for m in run['measurements']:
                if m['source'].get('row') is not None and (m['source']['path'],m['source'].get('sheet'),m['source']['row']) in suspect_rows \
                        and 'DUPLICATE_CONFLICT' not in m['rule_codes']:
                    m['rule_codes'].append('ROW_CONFLICT')
            doc_types={d['source_id']:d['doc_type'] for d in run['documents']}
            process_batches={m['batch'] for m in run['measurements'] if doc_types.get(m['source_id'])=='instrument_export'}
            for path,items in by_doc.items():
                for m in items:
                    if process_batches and m['batch'] not in process_batches:
                        m['rule_codes'].append('BATCH_MISMATCH'); issue('BATCH_MISMATCH',path=path,batch=m['batch'])
                structured=[m for m in items if m['source'].get('row') is not None]
                times=defaultdict(list)
                for m in structured:
                    if m['parameter']!=structured[0]['parameter']: continue
                    try: times[m['batch']].append((m['source']['row'],time_key(m['time'])))
                    except ValueError: m['rule_codes'].append('TIME_ORDER')
                for batch,entries in times.items():
                    sequence=[t for _,t in sorted(entries)]
                    if any(b<a for a,b in zip(sequence,sequence[1:])):
                        issue('TIME_ORDER',path=path,batch=batch)
                        for m in items:
                            if m['batch']==batch: m['rule_codes'].append('TIME_ORDER')
            previous=self.previous_verified(cmo,run['id'])
            findings,basis=quality.expectations(run,previous)
            for finding in [*quality.batch_completeness(run),*findings]:
                finding=dict(finding); issue(finding.pop('rule_code'),**finding)
            run['expectations_basis']=basis
            for m in run['measurements']:
                blocking=[i['rule_code'] for i in run['issues'] if blocks(i,m)]
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
            run['elements']=list(elements.values())
            run['coverage']=quality.account(run['elements'],run['issues'])
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
        coverage=run.get('coverage') or {}
        if run.get('elements') is not None: coverage=run['coverage']=quality.account([dict(e) for e in run['elements']],run['issues'])
        run['summary']={'measurements':len(measures),'auto_accepted':sum(m['status']=='auto_accepted' for m in measures),
            'accepted':len(accepted),'needs_review':sum(m['status']=='needs_review' for m in measures),
            'rejected':sum(m['status']=='rejected' for m in measures),
            'open_issues':sum(i['status']=='open' for i in run['issues']),
            'review_groups':len(quality.review_groups(run)),
            'unconfirmed_layouts':sum(not l['confirmed'] for l in run.get('layouts',[])),
            'corrections':sum(r['decision']=='correct' for r in run['reviews']),'model_calls':len(run['model_usage']),
            'inference_cost_usd':sum(x['cost_usd'] for x in run['model_usage']) if all(x['cost_usd'] is not None for x in run['model_usage']) else None,
            'input_tokens':sum(x['input_tokens'] for x in run['model_usage']) if all(x['input_tokens'] is not None for x in run['model_usage']) else None,
            'output_tokens':sum(x['output_tokens'] for x in run['model_usage']) if all(x['output_tokens'] is not None for x in run['model_usage']) else None,
            'elements':coverage.get('elements'),'unaccounted':coverage.get('unaccounted'),
            'verified_package':bool(measures) and all(m['status'] in {'auto_accepted','accepted','corrected','rejected'} for m in measures)
                and not any(i['status']=='open' for i in run['issues']) and not coverage.get('unaccounted')}

    def _apply_review(self,run,m,decision,actor,reason,*,value=None,parameter=None,unit=None,batch=None,time_value=None,carried_from=None):
        if decision not in {'accept','correct','reject'}: raise ValueError('Invalid review decision')
        if not actor.strip() or not reason.strip(): raise ValueError('Actor and review reason are required')
        self.original(run['id'],m['source_id'],run=run) # verify original bytes still match before signing
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
            try: time_key(revised['time'])
            except ValueError: raise ValueError('Invalid process hour must be corrected before acceptance')
        receipt={'at':utc(),'actor':actor,'reason':reason,'decision':decision,'before':m,'after':revised}
        if carried_from: receipt['carried_from']=carried_from
        run['reviews'].append(receipt)
        run['measurements']=[revised if x['id']==m['id'] else x for x in run['measurements']]
        self.audit('measurement_review',run_id=run['id'],**receipt)
        return revised

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
            self._apply_review(run,m,decision,actor,reason,value=value,parameter=parameter,unit=unit,batch=batch,time_value=time_value)
            self.summarize(run); self.save(run); return run

    def review_many(self,run_id,items,decision,actor,reason):
        """One reviewer decision for a group of values. Each value still gets its
        own receipt; stale or unacceptable values are reported, not skipped silently."""
        if decision not in {'accept','reject'}: raise ValueError('Group decisions are accept or reject; correct values individually')
        if not actor.strip() or not reason.strip(): raise ValueError('Actor and review reason are required')
        if not items or len(items)>20000: raise ValueError('Select between 1 and 20000 values')
        with self._lock:
            run=self.get(run_id); current={m['id']:m for m in run['measurements']}
            applied=[]; failed=[]
            for item in items:
                m=current.get(item['measurement_id'])
                if not m: failed.append({'measurement_id':item['measurement_id'],'error':'Unknown or superseded measurement'}); continue
                if digest(m)!=item['binding']: failed.append({'measurement_id':m['id'],'error':'Review binding changed; reload'}); continue
                try: applied.append(self._apply_review(run,m,decision,actor,reason)['id'])
                except ValueError as exc: failed.append({'measurement_id':m['id'],'error':str(exc)})
            self.summarize(run); self.save(run)
            return {'applied':len(applied),'failed':failed,'summary':run['summary']}

    def resolve_issue(self,run_id,issue_id,actor,reason,*,ignore_in_future=False,also=()):
        """Record a disposition. ``also`` lists further issue IDs with the same rule
        code that the reviewer settles with the same reason (for example every
        blank glucose cell in one file)."""
        if not actor.strip() or not reason.strip(): raise ValueError('Actor and disposition reason required')
        with self._lock:
            run=self.get(run_id); issue=next((i for i in run['issues'] if i['id']==issue_id),None)
            if not issue: raise KeyError('Unknown issue')
            siblings=[i for i in run['issues'] if i['id'] in set(also) and i['id']!=issue_id]
            if any(i['rule_code']!=issue['rule_code'] or i['status']!='open' for i in siblings):
                raise ValueError('A group decision must cover open issues of one kind')
            for sibling in siblings:
                sibling.update(status='resolved',actor=actor,reason=reason,at=utc(),grouped_with=issue_id)
                self.audit('issue_disposition',run_id=run_id,issue=sibling)
            rules=[]
            if ignore_in_future:
                if issue['rule_code']!='UNACCOUNTED_CONTENT' or not issue.get('lines'):
                    raise ValueError('Only unconverted text lines can become ignore rules')
                existing={r['pattern'] for r in self.repo.ignore_rules(run['cmo'])}
                for pattern in dict.fromkeys(line['pattern'] for line in issue['lines']):
                    if pattern not in existing and re.search(r'[A-Za-z]',pattern):
                        rules.append(self.add_ignore_rule(run['cmo'],pattern,actor,reason,run_id=run_id)['id'])
            issue.update(status='resolved',actor=actor,reason=reason,at=utc(),ignore_rules=rules)
            self.audit('issue_disposition',run_id=run_id,issue=issue)
            if ignore_in_future:
                # The same letterhead on other documents is settled by the same rule.
                patterns={r['pattern'] for r in self.repo.ignore_rules(run['cmo'])}
                for other in run['issues']:
                    if other['status']=='open' and other['rule_code']=='UNACCOUNTED_CONTENT' and other.get('lines') \
                            and all(line['pattern'] in patterns for line in other['lines']):
                        other.update(status='resolved',actor=actor,reason=f'Covered by ignore rule: {reason}',at=utc(),covered_by=issue_id)
                        self.audit('issue_disposition',run_id=run_id,issue=other)
            self.summarize(run); self.save(run); return run

    def carry_over(self,old_id,new_run):
        """Re-apply prior human decisions to a reprocessed run when the decision
        concerns the same source element, raw text and parameter."""
        old=self.get(old_id); carried=[]; skipped=[]
        with self._lock:
            run=self.get(new_run['id'])
            for receipt in old.get('reviews',[]):
                before=receipt['before']
                # A human rejection or correction outranks automatic acceptance;
                # an earlier acceptance adds nothing to an auto-accepted value.
                eligible={'needs_review'} if receipt['decision']=='accept' else {'needs_review','auto_accepted'}
                target=next((m for m in run['measurements'] if m['status'] in eligible and m['evidence_id']==before['evidence_id']
                             and m['parameter']==before['parameter'] and m['value_raw']==before['value_raw']),None)
                if not target: continue
                after=receipt['after']
                try:
                    self._apply_review(run,target,receipt['decision'],receipt['actor'],f"Carried forward from run {old_id[:8]}: {receipt['reason']}",
                        carried_from={'run_id':old_id,'at':receipt['at']},
                        **({'value':after['value_raw'] if after['value'] is None else str(after['value']),'parameter':after['parameter'],'unit':after['unit'],
                            'batch':after['batch'],'time_value':after['time']} if receipt['decision']=='correct' else {}))
                    carried.append(target['id'])
                except ValueError as exc: skipped.append({'measurement_id':target['id'],'error':str(exc)})
            resolved={i['id']:i for i in old.get('issues',[]) if i['status']=='resolved'}
            for item in run['issues']:
                prior=resolved.get(item['id'])
                if item['status']=='open' and prior:
                    item.update(status='resolved',actor=prior['actor'],reason=f"Carried forward from run {old_id[:8]}: {prior['reason']}",at=utc(),carried_from=old_id)
                    self.audit('issue_disposition',run_id=run['id'],issue=item)
            run['carried_over']={'from_run':old_id,'reviews':len(carried),'skipped':skipped}
            self.summarize(run); self.save(run)
            old['superseded_by']=run['id']; self.save(old)
            self.audit('run_superseded',run_id=old_id,superseded_by=run['id'],carried_reviews=len(carried))
            return run

    def original(self,run_id,source_id,*,run=None):
        run=run or self.get(run_id); doc=next((d for d in run['documents'] if d['source_id']==source_id),None)
        if not doc: raise KeyError('Unknown source')
        suffix=Path(doc['path']).suffix.lower()
        path=self.root/'stores'/run['id']/'originals'/doc['sha256'][:2]/(doc['sha256']+suffix)
        if run.get('store') and not path.exists():
            path=Path(run['store'])/'originals'/doc['sha256'][:2]/(doc['sha256']+suffix)
        return restore(self.evidence,original_key(doc['sha256'],suffix),path,doc['sha256']),doc

    def export(self,run_id,*,format='csv',wide=False):
        run=self.get(run_id)
        for source_id in {m['source_id'] for m in run['measurements'] if m['status'] in {'accepted','auto_accepted','corrected'}}:
            self.original(run_id,source_id,run=run)
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
