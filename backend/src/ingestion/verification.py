"""Deterministic checks shared by uploaded deliveries and structured connector records.

Extraction is source-specific. These checks consume canonical observations and
retain original source pointers; they do not call OCR or a model.
"""
from __future__ import annotations
import math
from collections import defaultdict
from .schema import VOCAB, normalize, time_key

VERSION = 'shared-ingestion-verification-1'
ACCEPTED = {'accepted', 'auto_accepted', 'corrected'}
PER_BATCH_DOCUMENTS = {'coa', 'batch_record', 'instrument_export'}


def validate_measurement(m, *, mapping_confirmed, raw_unit=None):
    """Normalize and attach review reasons in place, preserving raw values."""
    codes = m.setdefault('rule_codes', [])
    if not str(m.get('batch', '')).strip() or str(m.get('time', '')).strip() == '':
        codes.append('MISSING_FIELD')
    try:
        time_key(m.get('time'))
    except (ValueError, TypeError):
        codes.append('TIME_ORDER')
    parameter = m.get('parameter')
    if parameter not in VOCAB:
        m.update(value=None, unit=None)
        codes.append('PARAMETER_UNKNOWN')
    else:
        try:
            m['value'], m['unit'] = normalize(m['value_raw'], raw_unit, parameter)
            lo, hi = VOCAB[parameter]['range']
            if not lo <= m['value'] <= hi:
                codes.append('RANGE')
        except (ValueError, TypeError):
            codes.append('UNIT_UNKNOWN' if raw_unit is None or raw_unit == 'unknown' else 'UNIT_CONVERT')
        if raw_unit == 'unspecified' and not m.get('unit_declared'):
            codes.append('UNIT_UNKNOWN')
    if not m.get('source_verified'):
        codes.append('SOURCE_REVIEW')
    if not mapping_confirmed:
        codes.append('DRAFT_MAPPING')
    if m.get('value') is None:
        codes.append('VALUE_INVALID')
    m['rule_codes'] = sorted(set(codes))
    return m


def validate_collection(run, issue, *, previous=None, complete=True, ordered=True):
    """Cross-record checks. Missing-delivery checks apply only to complete snapshots.

    An unordered live stream may legitimately deliver old event times. Such
    arrivals are tracked by intake; they are not a corrupt file row ordering.
    """
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
            if complete and process_batches and m['batch'] not in process_batches:
                m['rule_codes'].append('BATCH_MISMATCH'); issue('BATCH_MISMATCH',path=path,batch=m['batch'])
        structured=[m for m in items if m['source'].get('row') is not None]
        times=defaultdict(list)
        for m in structured:
            if m['parameter']!=structured[0]['parameter']: continue
            try: times[m['batch']].append((m['source']['row'],time_key(m['time'])))
            except ValueError: m['rule_codes'].append('TIME_ORDER')
        for batch,entries in times.items():
            sequence=[t for _,t in sorted(entries)]
            if ordered and any(b<a for a,b in zip(sequence,sequence[1:])):
                issue('TIME_ORDER',path=path,batch=batch)
                for m in items:
                    if m['batch']==batch: m['rule_codes'].append('TIME_ORDER')
    findings, basis = expectations(run, previous) if complete else ([], None)
    for finding in [*(batch_completeness(run) if complete else []), *findings]:
        finding = dict(finding)
        issue(finding.pop('rule_code'), **finding)
    run['expectations_basis'] = basis


def batch_completeness(run):
    """Per-batch documents expected in every delivery that contains the batch."""
    doc_type={d['source_id']:d['doc_type'] for d in run['documents']}
    present=defaultdict(set); batches=set()
    for m in run['measurements']:
        if not m['batch']: continue
        batches.add(m['batch']); present[doc_type.get(m['source_id'])].add(m['batch'])
    findings=[]
    for kind in sorted(PER_BATCH_DOCUMENTS):
        covered=present.get(kind,set())
        # Only meaningful once the delivery itself shows the document is per batch.
        if len(covered)>=2:
            for batch in sorted(batches-covered):
                findings.append({'rule_code':'BATCH_DOCUMENT_MISSING','batch':batch,'doc_type':kind,
                    'message':f'Batch {batch} has no {kind.replace("_"," ")} values although {len(covered)} other batch(es) do'})
    return findings


def expectations(run, previous):
    """Compare with the most recent fully verified delivery from the same CMO."""
    if not previous: return [],None
    findings=[]
    before={d['doc_type'] for d in previous['documents'] if d['doc_type']!='other'}
    now={d['doc_type'] for d in run['documents']}
    for kind in sorted(before-now):
        findings.append({'rule_code':'EXPECTED_DOCUMENT_MISSING','doc_type':kind,'previous_run':previous['id'],
            'message':f'Previous verified delivery included a {kind.replace("_"," ")}; this delivery has none'})
    params_before={m['parameter'] for m in previous['measurements'] if m['status'] in ACCEPTED}
    params_now={m['parameter'] for m in run['measurements']}
    for parameter in sorted(params_before-params_now):
        findings.append({'rule_code':'EXPECTED_PARAMETER_MISSING','parameter':parameter,'previous_run':previous['id'],
            'message':f'{parameter} was reported in the previous verified delivery but is absent here'})
    basis={'run_id':previous['id'],'completed_at':previous.get('completed_at'),
           'document_types':sorted(before),'parameters':sorted(params_before)}
    return findings,basis
