from . import check


def score(log,required):
    rankings=[(o.get('output') or {}).get('records',[])[:5] for o in log if o['name']=='workspace.search']
    ranked={r['id'] for ranking in rankings for r in ranking}
    inspected={(o.get('output') or {}).get('record',{}).get('id') for o in log if o['name']=='workspace.read'}
    gold={'EVAL:'+d for d in required}
    return {'record_recall_at_5':{'numerator':len(gold&ranked),'denominator':len(gold),
            'value':len(gold&ranked)/len(gold) if gold else None,
            'aggregation':'union of top-5 results from actual queries, not a single-query retrieval benchmark'},
            'required_evidence_inspected':{'numerator':len(gold&inspected),'denominator':len(gold)},
            'rankings':rankings,'inspected':sorted(x for x in inspected if x),
            'chunk_recall':{'status':'NOT_TESTABLE','reason':'Workspace retrieval returns records, not chunks.'}}
