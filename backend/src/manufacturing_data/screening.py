"""Balanced, source-derived screening candidates; never specification or cause labels."""
from collections import Counter
import hashlib
import json
import re
from .terminology import canonical, normalize

VERSION='screening-v2'

def identifier(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,default=str).encode()).hexdigest()[:20]

def family(name, unit=None):
    mapped=canonical(name,unit)['canonical_name']
    return mapped or normalize(re.sub(r'\b(mean|sem|sd|std)\b','',re.sub(r'\([^)]*\)','',name),flags=re.I))

def build_screening(series, anomalies, comparisons, source_versions):
    units={};groups={}
    for row in series:
        key=(row['source_id'],row['entity_id'])
        unit=units.setdefault(key,{'unit_id':identifier(key),'source_id':key[0],'entity_id':key[1],
                                  'series_count':0,'measurement_families':set(),'evidence_ids':[],
                                  'screening_status':'screened; agent review not established'})
        unit['series_count']+=1;unit['measurement_families'].add(family(row['name'],row['unit']))
        unit['evidence_ids'].extend(row['evidence_ids'])
    for source in source_versions:
        if not any(key[0]==source['source_id'] for key in units):
            key=(source['source_id'],None)
            units[key]={'unit_id':identifier(key),'source_id':key[0],'entity_id':None,'series_count':0,
                        'measurement_families':set(),'evidence_ids':[],
                        'screening_status':'no numeric series; narrative review required'}
    for unit in units.values():
        unit['measurement_families']=sorted(unit['measurement_families'])
        unit['evidence_ids']=list(dict.fromkeys(unit['evidence_ids']))
    # Group shared symptoms, not supposed causes. Clock problems repeated on
    # every measurement are one review candidate with all member flags retained.
    for anomaly in anomalies:
        for flag in anomaly['flags']:
            category=('clock_quality' if flag.startswith(('backwards_source_time','duplicate_source_times','missing_source_time'))
                      else 'constant_series' if flag.startswith('constant_series') else 'measurement_quality')
            key=(anomaly['source_id'],anomaly['entity_id'],category,
                 None if category=='clock_quality' else anomaly['sheet'])
            g=groups.setdefault(key,{'candidate_id':identifier(key),'source_id':key[0],
                'entity_ids':[key[1]] if key[1] else [],'category':category,
                'measurement_family':category,'members':[],'evidence_ids':[],
                'priority_signal':1.0,'limitations':['Grouped symptoms may represent several acquisition events; shared cause is not established.']})
            g['members'].append({'sheet':anomaly['sheet'],'name':anomaly['name'],'flag':flag})
            g['evidence_ids'].extend(anomaly['evidence_ids'])
    candidates=list(groups.values())
    for g in candidates:
        g['evidence_ids']=list(dict.fromkeys(g['evidence_ids']))
        g['member_flag_count']=len(g['members'])
    for c in comparisons:
        if re.search(r'\bsem\b',c['name'],re.I):continue # retain in full statistics; not a separate phenotype
        a,b=c['peak_values'];scale=abs(a)+abs(b)
        symmetric=200*abs(a-b)/scale if scale else 0.0
        candidates.append({'candidate_id':identifier([c['source_id'],c['name'],c['unit'],c['entity_ids']]),
            'source_id':c['source_id'],'entity_ids':c['entity_ids'],'category':'paired_measurements',
            'measurement_family':family(c['name'],c['unit']),'name':c['name'],'unit':c['unit'],
            'peak_values':c['peak_values'],'absolute_peak_difference':abs(a-b),
            'symmetric_peak_difference_percent':symmetric,
            'formula':'200 * abs(a-b) / (abs(a)+abs(b)); both zero => 0',
            'priority_signal':symmetric/200,'evidence_ids':c['evidence_ids'],
            'limitations':['Peaks may occur at different times; magnitude is not operational severity or statistical significance.',
                           'Design equivalence and measurement uncertainty require review.']})
    # Include endpoint deterioration even when paired peaks are similar. This is
    # a descriptive screening signal, not proof of cell death or process failure.
    for r in series:
        maximum,last=r['maximum'],r['last_value']
        if maximum is None or last is None or r['time_end'] is None or maximum<=0:continue
        drop=(maximum-last)/maximum
        if drop<=0:continue
        key=[r['source_id'],r['entity_id'],r['sheet'],r['name'],'endpoint_change']
        candidates.append({'candidate_id':identifier(key),'source_id':r['source_id'],
            'entity_ids':[r['entity_id']] if r['entity_id'] else [],'category':'endpoint_change',
            'measurement_family':family(r['name'],r['unit']),'name':r['name'],'unit':r['unit'],
            'peak_value':maximum,'last_value':last,'peak_to_last_fraction':drop,
            'formula':'(observed maximum - last source-time value) / observed maximum',
            'priority_signal':min(drop,1),'evidence_ids':list(dict.fromkeys([r['maximum_id'],r['last_id'],r['last_time_id']])),
            'limitations':['End-of-run decline can be expected by design; no supplied operating threshold.',
                           'The peak and last measurement need not be independent replicates.']})
    for c in candidates:c['evidence_ids']=[i for i in c['evidence_ids'] if i]
    remaining=sorted(candidates,key=lambda c:c['candidate_id']);selected=[];seen_sources=set();seen_families=set();seen_categories=set()
    category_counts=Counter()
    while remaining and len(selected)<12:
        def score(c):
            return (2*(c['source_id'] not in seen_sources)+2*(c['measurement_family'] not in seen_families)+
                    (c['category'] not in seen_categories)+c['priority_signal'])
        chosen=min(remaining,key=lambda c:(-(c['source_id'] not in seen_sources),category_counts[c['category']],-score(c),c['candidate_id']))
        reasons=['bounded descriptive signal; not severity']
        if chosen['source_id'] not in seen_sources:reasons.append('additional source coverage')
        if chosen['measurement_family'] not in seen_families:reasons.append('additional measurement-family coverage')
        if chosen['category'] not in seen_categories:reasons.append('additional screening category')
        selected.append({**chosen,'selection_reasons':reasons})
        seen_sources.add(chosen['source_id']);seen_families.add(chosen['measurement_family']);seen_categories.add(chosen['category'])
        category_counts[chosen['category']]+=1
        remaining.remove(chosen)
    return {'version':VERSION,'coverage_units':sorted(units.values(),key=lambda u:(u['source_id'],u['entity_id'] or '')),
            'raw_anomaly_flag_count':sum(len(a['flags']) for a in anomalies),
            'anomaly_series_count':len(anomalies),'grouped_quality_candidate_count':len(groups),
            'candidate_count':len(candidates),'candidates':candidates,'priority_candidates':selected,
            'policy':'source/family/category diversity plus bounded descriptive differences; heuristic, not site triage',
            'screening_is_investigation':False}
