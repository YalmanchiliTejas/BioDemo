"""Physical NISTCHO ingestion and whole-campaign split; no causal uplift score.

Published feeding strategies were assigned across different campaigns. This
module verifies source bytes, retains groups and reports observations only.
"""
from pathlib import Path
from collections import defaultdict
import csv,json,hashlib
from benchmarks.external_simulators.experiment import dump,sha

MAPPING={'A':'STD','B':'STD+','C':'LoG+','D':'HiF','E':'HIP','F':'HIP+','G':'LoG'}


def read_growth(root):
    path=root/'01_ViCell_growth_data.csv';rows=[]
    with path.open(encoding='utf-8-sig',newline='') as f:
        for line,row in enumerate(csv.DictReader(f),2):
            item={'campaign':row['Batch'],'condition':row['Condition'],'replicate':row['Replicate'],
                'time_h':float(row['Hours']),'viability_percent':float(row['Viability']),
                'total_VCD_authors_units':float(row['Total_VCD']),
                'source':{'file':path.name,'line':line,'file_sha256':sha(path)}}
            item['culture_id']='/'.join([item['campaign'],item['condition'],item['replicate']]);rows.append(item)
    return rows


def campaign_folds(rows):
    campaigns=sorted({r['campaign'] for r in rows});folds=[]
    for campaign in campaigns:
        train=[r for r in rows if r['campaign']!=campaign];test=[r for r in rows if r['campaign']==campaign]
        if {r['culture_id'] for r in train}&{r['culture_id'] for r in test}:raise ValueError('Culture leakage')
        folds.append({'test_campaign':campaign,'training_cultures':sorted({r['culture_id'] for r in train}),
            'test_cultures':sorted({r['culture_id'] for r in test}),
            'test_conditions_unseen_in_training':sorted({r['condition'] for r in test}-{r['condition'] for r in train})})
    return folds


def summarize(root,out):
    rows=read_growth(root);groups=defaultdict(list)
    for r in rows:groups[(r['campaign'],r['condition'],r['replicate'])].append(r)
    cultures=[]
    for (campaign,condition,replicate),points in groups.items():
        points.sort(key=lambda r:r['time_h']);last=points[-1]
        cultures.append({'campaign':campaign,'condition':condition,'strategy':MAPPING[condition],'replicate':replicate,
            'last_measured_time_h':last['time_h'],'last_measured_viability_percent':last['viability_percent'],
            'last_measured_total_VCD_authors_units':last['total_VCD_authors_units'],
            'peak_total_VCD_authors_units':max(p['total_VCD_authors_units'] for p in points)})
    receipt={'classification':'published_physical_observations_not_agent_evaluation','cultures':cultures,
        'campaign_folds':campaign_folds(rows),'source_manifest_sha256':sha(root/'acquisition.json'),
        'condition_mapping':MAPPING,'license':'CC BY4.0; see acquisition.json for attribution.',
        'limits':['LoG failure and HiF prevention are different campaigns, not randomized same-campaign rescue.',
            'Endpoint sampling times differ; do not call different last samples matched endpoint efficacy.',
            'This is ingestion and experimental grouping, not a validated fed-batch growth or intervention model.',
            'No agent choice or physical counterfactual outcome is imputed.']}
    dump(out,receipt);return receipt
