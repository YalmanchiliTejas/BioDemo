"""Flag ambiguity in the physical glucose export without guessing corrections."""
from collections import defaultdict
from pathlib import Path
import json
from benchmarks.external_simulators.experiment import dump,sha


def audit(root,output):
    import openpyxl
    p=root/'05_glucose_data.xlsx';w=openpyxl.load_workbook(p,data_only=True,read_only=True)
    sheet=w['Sheet2'];rows=[];keys=defaultdict(list)
    for line,values in enumerate(sheet.values,1):
        if line==1:continue
        condition,replicate,hour,value,tp,campaign=values[:6]
        if condition is None:continue
        row={'campaign':str(campaign),'condition':str(condition),'replicate':str(replicate),
            'time_h':None if hour is None else float(hour),'glucose_g_l':None if value is None else float(value),
            'source':{'file':p.name,'sheet':sheet.title,'row':line,'sha256':sha(p)},
            'flags':[]}
        if value is None:row['flags'].append('missing_no_imputation')
        if hour is not None and abs(float(hour)%24.-1.)<1e-8:row['flags'].append('post_feed_origin_unverified_not_independent_assay')
        key=(row['campaign'],row['condition'],row['replicate'],row['time_h']);keys[key].append(len(rows));rows.append(row)
    w.close();duplicates=[]
    for key,indices in keys.items():
        if len(indices)>1:
            for i in indices:rows[i]['flags'].append('duplicate_identity_unresolved')
            duplicates.append({'key':list(key),'source_rows':[rows[i]['source']['row'] for i in indices],
                'values':[rows[i]['glucose_g_l'] for i in indices]})
    receipt={'scope':'Data-quality audit, not physical intervention evaluation','rows':rows,'duplicate_keys':duplicates,
        'missing_rows':sum('missing_no_imputation' in r['flags'] for r in rows),
        'unverified_post_feed_rows':sum('post_feed_origin_unverified_not_independent_assay' in r['flags'] for r in rows),
        'qualified_for_mechanistic_intervention_replay':False,
        'required_clarifications':['LoG replicate identities','actual executed feed times/amounts/composition','measured versus calculated post-feed glucose','per-culture volume/withdrawal records'],
        'policy':'Retain originals and flags. Do not rename duplicate replicate1 to4, infer future feeds from heldout glucose, or count constructed values as independent measurements.'}
    dump(output,receipt);return receipt
