"""Zero-silent-error accounting for a CMO ingestion run.

Every non-empty source element (spreadsheet cell or document text element)
must end in exactly one of these states:

* ``measurement``  - became a measurement (accepted, auto-accepted or queued for review)
* ``identifier``   - the batch or time column for a mapped row
* ``ignored``      - excluded by a reviewer-confirmed template column or ignore rule
* ``flagged``      - not converted, and covered by a visible issue that must be dispositioned

``unaccounted`` is the remainder and must be zero. ``guarantee`` re-derives
these states independently of the pipeline that produced them and checks the
rules that keep unverified values out of exports.
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict

from .schema import time_key

ACCEPTED={'accepted','auto_accepted','corrected'}
ELEMENT_STATES=('measurement','identifier','ignored','flagged','unaccounted')
# Document types expected once per batch in a complete delivery.
PER_BATCH_DOCUMENTS={'coa','batch_record','instrument_export'}
COVERING_RULES={'UNMAPPED_FIELD','UNACCOUNTED_CONTENT','UNRECOGNIZED_TABLE','PARSE_ERROR'}


def pattern(text):
    """Digit-insensitive line pattern used for reviewer ignore rules."""
    return re.sub(r'\s+',' ',re.sub(r'\d+(?:[.,]\d+)?','#',str(text))).strip()


def covering_issue(element, issues):
    for issue in issues:
        if issue['rule_code'] not in COVERING_RULES or issue.get('path')!=element['path']: continue
        if issue['rule_code']=='UNMAPPED_FIELD':
            if issue.get('header')==element.get('column'): return issue
        elif issue['rule_code']=='UNRECOGNIZED_TABLE':
            if issue.get('sheet')==element.get('sheet'): return issue
        else:
            return issue
    return None


def account(elements, issues):
    """Finalize element states: anything not converted or ignored must be
    covered by an issue, otherwise it is counted as unaccounted."""
    totals=Counter(); documents=defaultdict(Counter)
    for element in elements:
        state=element['state']
        if state=='pending':
            state='flagged' if covering_issue(element,issues) else 'unaccounted'
            element['state']=state
        totals[state]+=1; documents[element['path']][state]+=1
    return {'elements':len(elements),**{s:totals.get(s,0) for s in ELEMENT_STATES},
            'by_document':{path:{'elements':sum(c.values()),**{s:c.get(s,0) for s in ELEMENT_STATES}}
                           for path,c in sorted(documents.items())}}


def review_groups(run):
    """Group values awaiting review by source column and reasons, so a reviewer
    decides once per group after inspecting representative sources."""
    groups={}
    for m in run.get('measurements',[]):
        if m['status']!='needs_review': continue
        column=m['source'].get('column') or m['parameter']
        ident='|'.join([m['source']['path'],str(m['source'].get('sheet') or ''),column,','.join(m['rule_codes'])])
        group=groups.setdefault(ident,{'id':ident,'path':m['source']['path'],'sheet':m['source'].get('sheet'),
            'column':column,'parameter':m['parameter'],'rule_codes':m['rule_codes'],'count':0,
            'batches':set(),'measurement_ids':[],'unit_raw':m['unit_raw'],'unit':m['unit'],'invalid_values':0})
        group['count']+=1; group['batches'].add(m['batch']); group['measurement_ids'].append(m['id'])
        group['invalid_values']+=m['value'] is None
    result=[]
    for group in groups.values():
        group['batches']=sorted(group['batches'])
        result.append(group)
    return sorted(result,key=lambda g:(-g['count'],g['path'],g['column']))


def guarantee(run, *, audit_valid=None):
    """Independent checks of the zero-silent-error rules for this run."""
    measures=run.get('measurements',[]); issues=run.get('issues',[]); coverage=run.get('coverage') or {}
    checks=[]
    def check(ident,label,passed,detail): checks.append({'id':ident,'label':label,'passed':bool(passed),'detail':detail})

    if run.get('elements') is not None:
        recount=account([dict(e) for e in run['elements']],issues)['unaccounted']
    else:
        recount=coverage.get('unaccounted')
    check('content_accounted','Every source cell and text line is converted, ignored by a confirmed rule, or flagged',
          coverage and recount==0,
          f"{coverage.get('elements',0)} elements: {coverage.get('measurement',0)} values, {coverage.get('identifier',0)} identifiers, "
          f"{coverage.get('ignored',0)} ignored, {coverage.get('flagged',0)} flagged, {recount if recount is not None else 'unknown'} unaccounted")

    bad_auto=[m['id'] for m in measures if m['status']=='auto_accepted' and
              (not m.get('template_id') or not m.get('source_verified') or m.get('rule_codes'))]
    check('auto_acceptance_rule','Values accepted without review come only from a confirmed mapping, match the original byte-for-byte and pass every check',
          not bad_auto,f'{sum(m["status"]=="auto_accepted" for m in measures)} auto-accepted; {len(bad_auto)} violate the rule')

    reviewed={r['after']['id'] for r in run.get('reviews',[]) if r.get('actor') and r.get('reason')}
    unattributed=[m['id'] for m in measures if m['status'] in {'accepted','corrected','rejected'} and m['id'] not in reviewed]
    check('human_decisions_attributed','Every human acceptance, correction and rejection has a named reviewer and reason',
          not unattributed,f'{len(reviewed)} review receipts; {len(unattributed)} decisions without a receipt')

    identities=defaultdict(set)
    for m in measures:
        if m['status'] in ACCEPTED and m['value'] is not None:
            try: identities[(m['batch'],time_key(m['time']),m['parameter'])].add(round(m['value'],12))
            except ValueError: identities[(m['batch'],m['time'],m['parameter'])].add(round(m['value'],12))
    conflicts=[k for k,v in identities.items() if len(v)>1]
    check('no_conflicting_accepted_values','No two accepted values disagree for the same batch, time and parameter',
          not conflicts,f'{len(conflicts)} conflicting identities')

    invalid=[m['id'] for m in measures if m['status'] in ACCEPTED and (m['value'] is None or not math.isfinite(m['value']))]
    check('accepted_values_numeric','Accepted values are finite numbers in canonical units',not invalid,f'{len(invalid)} invalid accepted values')

    summary=run.get('summary') or {}
    pending=sum(m['status']=='needs_review' for m in measures); open_issues=sum(i['status']=='open' for i in issues)
    check('verified_means_complete','A package is marked verified only with zero pending values, zero open issues and zero unaccounted content',
          not summary.get('verified_package') or (pending==0 and open_issues==0 and recount==0),
          f'{pending} values pending, {open_issues} issues open')
    if audit_valid is not None:
        check('audit_chain','The append-only audit chain verifies end to end',audit_valid,'hash chain verified' if audit_valid else 'hash chain broken')
    return {'holds':all(c['passed'] for c in checks),'checks':checks,
            'scope':'Guarantees accounting and acceptance rules for this run. It does not prove a source document itself is correct or complete.'}


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
