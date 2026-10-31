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
from ...ingestion.verification import PER_BATCH_DOCUMENTS
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


def confidence(m):
    """Review-priority score of a measurement, a function of its stored facts.
    Not a calibrated probability of correctness."""
    return 0.0 if m['value'] is None else min(1 if m['template_id'] else 0.6, 1 if m['source_verified'] else 0.5,
                                              1 if not m['rule_codes'] else 0.5)


def relationships(run):
    """Candidate links between each batch's documents and its process export."""
    result=[]; by_batch=defaultdict(set)
    for m in run['measurements']: by_batch[m['batch']].add(m['source']['path'])
    for batch,paths in by_batch.items():
        process_paths=[d['path'] for d in run['documents'] if d['doc_type']=='instrument_export' and d['path'] in paths]
        for path in sorted(paths):
            for process_path in process_paths:
                if path!=process_path:
                    result.append({'left':path,'right':process_path,'batch':batch,'relation':'batch_evidence',
                        'status':'candidate' if any(i['rule_code']=='BATCH_MISMATCH' and i.get('path')==path for i in run['issues']) else 'source_linked'})
    return result


def summarize(run):
    """Derived totals for a completed run; recomputed from current facts on every read."""
    measures=run['measurements']; accepted=[m for m in measures if m['status'] in ACCEPTED]
    coverage=run.get('coverage') or {}
    if run.get('elements') is not None: coverage=run['coverage']=account([dict(e) for e in run['elements']],run['issues'])
    run['relationships']=relationships(run)
    usage=run.get('model_usage',[])
    total=lambda key: sum(x[key] for x in usage) if all(x.get(key) is not None for x in usage) else None
    run['summary']={'measurements':len(measures),'auto_accepted':sum(m['status']=='auto_accepted' for m in measures),
        'accepted':len(accepted),'needs_review':sum(m['status']=='needs_review' for m in measures),
        'rejected':sum(m['status']=='rejected' for m in measures),
        'open_issues':sum(i['status']=='open' for i in run['issues']),
        'review_groups':len(review_groups(run)),
        'unconfirmed_layouts':sum(not l['confirmed'] for l in run.get('layouts',[])),
        'corrections':sum(r['decision']=='correct' for r in run.get('reviews',[])),'model_calls':len(usage),
        'inference_cost_usd':total('cost_usd'),'input_tokens':total('input_tokens'),'output_tokens':total('output_tokens'),
        'elements':coverage.get('elements'),'unaccounted':coverage.get('unaccounted'),
        'verified_package':bool(measures) and all(m['status'] in {'auto_accepted','accepted','corrected','rejected'} for m in measures)
            and not any(i['status']=='open' for i in run['issues']) and not coverage.get('unaccounted')}
    return run['summary']


# Kept as public imports for existing delivery callers.
from ...ingestion.verification import batch_completeness, expectations
