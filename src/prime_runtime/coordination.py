"""Deterministic work scheduling and report assembly, never scientific approval."""
from copy import deepcopy
import hashlib
import json

KEYED_SECTIONS={'coverage':'unit_id','candidate_reviews':'candidate_id','claims':'claim_id',
                'observed_facts':'claim_id','interpretations':'claim_id','hypotheses':'hypothesis_id',
                'calculated_metrics':'metric_id','temporal_claims':'claim_id'}
LIST_SECTIONS={'open_questions','evidence_requests','tasks','follow_up_actions','decision_branches','findings','resolved_questions','evidence_ids','affected_entity_ids'}
SCALARS={'assessment','cross_scope_synthesis','severity','report_type'}


def merge_report(original, update):
    """Explicit keyed upserts; omitted findings are retained, never invented."""
    if not isinstance(update,dict) or set(update)-KEYED_SECTIONS.keys()-LIST_SECTIONS-SCALARS:
        raise ValueError('Unknown draft report section')
    result=deepcopy(original)
    for key,value in update.items():
        if key in KEYED_SECTIONS:
            if not isinstance(value,list):raise ValueError(key+' must be a list')
            identity=KEYED_SECTIONS[key];items={}
            identifiers=[i.get(identity) for i in value if isinstance(i,dict)]
            if len(identifiers)!=len(set(identifiers)):raise ValueError('duplicate '+identity+' in update')
            for item in result.get(key,[])+value:
                if not isinstance(item,dict) or not isinstance(item.get(identity),str) or not item[identity].strip():
                    raise ValueError(key+' entries require '+identity)
                items[item[identity]]=deepcopy(item)
            result[key]=list(items.values())
        elif key in LIST_SECTIONS:
            if not isinstance(value,list):raise ValueError(key+' must be a list')
            # These lists are explicitly replaced so resolved questions/actions
            # can be removed deliberately rather than accumulating stale work.
            result[key]=deepcopy(value)
        else:result[key]=deepcopy(value)
    return result


class InvestigationCoordinator:
    def __init__(self,prepared):
        screening=prepared['screening']
        self.units={u['unit_id']:u for u in screening['coverage_units']}
        self.candidates={c['candidate_id']:c for c in screening['priority_candidates']}
        self.sources={s['source_id']:s for s in prepared['source_versions']}
        self.source_reads=set();self.draft={};self.assignments={};self.repairs=[]
        self.decisions=[];self.extensions=[];self.evidence_ids=set()

    def task_ids(self):
        return {'source:'+s for s in self.sources}|{'unit:'+u for u in self.units}|{'candidate:'+c for c in self.candidates}|{r['task_id'] for r in self.repairs}

    def task_open(self,task):
        if task not in self.task_ids():return False
        kind,identifier=task.split(':',1)
        if kind=='source':return identifier not in self.source_reads
        if kind=='unit':return next((c.get('status') for c in self.draft.get('coverage',[]) if c['unit_id']==identifier),None) not in {'investigated','reviewed_no_material_signal'}
        if kind=='candidate':return next((c.get('status') for c in self.draft.get('candidate_reviews',[]) if c['candidate_id']==identifier),None) not in {'investigated','contextualized'}
        return any(r['task_id']==task for r in self.repairs)

    def record_evidence(self,rows):
        fresh={r['id'] for r in rows}-self.evidence_ids
        self.evidence_ids.update(fresh);self.source_reads.update(r['source_id'] for r in rows)
        return len(fresh)

    def queue(self,limit=20):
        tasks=[]
        # Source inventory first, including narrative-only maintenance/operator
        # files. Statistical flags cannot exhaust the budget before first reads.
        for sid,source in self.sources.items():
            if sid not in self.source_reads:
                tasks.append({'task_id':'source:'+sid,'kind':'source_inventory','source_id':sid,'path':source['path'],
                              'unit_ids':[u for u,v in self.units.items() if v['source_id']==sid]})
        tasks.extend({'kind':'report_repair',**r} for r in self.repairs)
        for cid,c in self.candidates.items():
            if self.task_open('candidate:'+cid):tasks.append({'task_id':'candidate:'+cid,'kind':'candidate_investigation','candidate_id':cid,'source_id':c['source_id'],'category':c['category']})
        for uid,u in self.units.items():
            if self.task_open('unit:'+uid):tasks.append({'task_id':'unit:'+uid,'kind':'coverage_review','unit_id':uid,'source_id':u['source_id'],'entity_id':u['entity_id']})
        for task in tasks:task['assignment']=self.assignments.get(task['task_id'])
        # Assignments do not remove work; stalled children stay visible to lead.
        return {'total_open_tasks':len(tasks),'tasks':tasks[:limit],
                'unread_source_count':len(set(self.sources)-self.source_reads),
                'pending_unit_count':sum(self.task_open('unit:'+u) for u in self.units),
                'pending_candidate_count':sum(self.task_open('candidate:'+c) for c in self.candidates),
                'phase':'source_inventory' if set(self.sources)-self.source_reads else 'repair' if self.repairs else 'investigation'}

    def repair_queue(self,review,verification=None):
        issues=list(review.get('issues',[]))
        if verification:
            issues+=verification.get('claim_verification',{}).get('issues',[])
            if verification.get('status')!='checks_passed; scientific_review_required':
                issues.append({'code':verification.get('status'),'detail':verification.get('unlinked_numeric_literals',[])})
        actions={'coverage_unresolved':'Read the named source/unit, then explicitly review it or retain unresolved status.',
                 'coverage_not_reviewed':'Add a source-backed disposition for each missing unit.',
                 'temporal_claim_unverified':'Use explicit timezone-qualified timestamp cells or comparable process clocks; otherwise remove unsupported ordering and state the uncertainty.',
                 'claim_numeric_literals_unlinked':'Reference the verified metric and declare display_decimals, or correct the number; never add unrelated citations.',
                 'material_statement_missing_from_claim_ledger':'Add the exact statement to the classified claim ledger.',
                 'counterevidence_search_incomplete':'Investigate counterevidence or explicitly retain an incomplete disposition.'}
        unique={}
        bounded=[]
        for issue in issues:
            field=next((k for k in ('unit_ids','candidate_ids','hypothesis_ids') if isinstance(issue.get(k),list) and len(issue[k])>1),None)
            if field:
                bounded.extend({**issue,field:[identifier]} for identifier in issue[field])
            else:bounded.append(issue)
        for issue in bounded:
            key=json.dumps(issue,sort_keys=True,default=str)
            identifier=hashlib.sha256(key.encode()).hexdigest()[:16]
            unique[key]={'task_id':'repair:'+identifier,'issue':issue,
                         'next_step':actions.get(issue.get('code'),'Correct this specific validation issue; retain all other valid findings.')}
        self.repairs=list(unique.values())
        return deepcopy(self.repairs)

    def convergence(self):
        queue=self.queue(0)
        decisions={d['candidate_id']:d for d in self.decisions}
        absent=[cid for cid in self.candidates if cid not in decisions]
        needs_more=[cid for cid,d in decisions.items() if d['expected_to_change_action'] and
                    (d['available_in_scope'] or not self.draft.get('evidence_requests') or not self.draft.get('open_questions'))]
        return {'operationally_converged':not queue['unread_source_count'] and not queue['pending_unit_count'] and
                not queue['pending_candidate_count'] and not self.repairs and not absent and not needs_more,
                'unread_sources':queue['unread_source_count'],'unresolved_units':queue['pending_unit_count'],
                'unresolved_candidates':queue['pending_candidate_count'],'repair_count':len(self.repairs),
                'candidates_without_stopping_reason':absent,
                'candidates_needing_more_evidence':needs_more,
                'scientific_qualification':'independent_review_pending',
                'basis':'Explicit source review, candidate dispositions, validation and agent-authored marginal-value decisions; not proof that all relevant evidence was discovered.'}

    def snapshot(self):
        return {'draft_report':deepcopy(self.draft),'source_reads':sorted(self.source_reads),
                'assignments':deepcopy(self.assignments),'repair_tasks':deepcopy(self.repairs),
                'stopping_decisions':deepcopy(self.decisions),'budget_changes':deepcopy(self.extensions),
                'convergence':self.convergence()}
