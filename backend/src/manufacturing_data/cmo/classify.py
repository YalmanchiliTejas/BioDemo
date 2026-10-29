"""Deterministic document classification from file names, then from content.

CMO files rarely arrive with tidy names. Title lines and table headers are
checked against explicit phrases. A unique best score is required; ties and
weak evidence stay ``other`` so a model or reviewer decides instead.
"""
from __future__ import annotations

from pathlib import Path

from .schema import header_parts, is_batch_header, is_time_header, alias, key

FILENAME_TOKENS = [('environmental','environmental_monitoring'),('microbiology','microbiology'),
                   ('coa','coa'),('maintenance','maintenance'),('deviation','deviation_report'),
                   ('investigation','investigation_report'),('batch record','batch_record'),
                   ('bioreactor','instrument_export'),('fermentation','instrument_export')]

PHRASES = {
    'coa':['certificate of analysis','coa','release specification','conforms to specification'],
    'deviation_report':['deviation report','deviation number','deviation id','deviation description','nonconformance'],
    'investigation_report':['investigation report','root cause','capa','corrective and preventive action'],
    'environmental_monitoring':['environmental monitoring','viable air','settle plate','contact plate','cleanroom monitoring','em cfu','air viable count'],
    'microbiology':['microbiology','bioburden','endotoxin','sterility test','microbial'],
    'maintenance':['maintenance','work order','preventive maintenance','calibration record','equipment repair'],
    'batch_record':['batch record','executed batch record','ebr','batch production record','manufacturing record'],
    'instrument_export':['historian export','bioreactor export','process data export','trend export'],
    'lab_results':['lims','laboratory results','offline analysis','vcd','viability','glucose','lactate','ammonium','osmolality','cell count'],
}


def by_filename(path):
    name=key(Path(path).stem)
    for token,kind in FILENAME_TOKENS:
        if token in name: return kind
    return 'other'


def by_content(lines, headers=()):
    """Return (doc_type, evidence) or ('other', reason). Title lines weigh more."""
    text=[key(line) for line in lines if str(line).strip()]
    scores={kind:0 for kind in PHRASES}; evidence={kind:[] for kind in PHRASES}
    for index,line in enumerate(text[:60]):
        weight=5 if index==0 else 2 if index<4 else 1
        for kind,phrases in PHRASES.items():
            for phrase in phrases:
                if f' {key(phrase)} ' in f' {line} ':
                    scores[kind]+=weight; evidence[kind].append(phrase)
    if headers:
        # A table with batch, time and process-variable columns is a process
        # export regardless of its name, unless most of its variables name a
        # more specific record type (for example viable-air counts).
        variables=[h for h in headers if alias(h)]
        hits={kind:sum(1 for h in headers if any(f' {key(p)} ' in f' {key(h)} ' for p in phrases)) for kind,phrases in PHRASES.items()}
        specific,count=max(hits.items(),key=lambda item:item[1])
        if count and count>len(variables)/2:
            scores[specific]+=4; evidence[specific].append('column names')
        if any(is_batch_header(h) for h in headers) and any(is_time_header(h) for h in headers) and variables:
            scores['instrument_export']+=3; evidence['instrument_export'].append('batch, time and process-variable columns')
        elif len(variables)>=2 and all(header_parts(h)[1] for h in variables):
            scores['instrument_export']+=1; evidence['instrument_export'].append('process-variable columns with units')
    ranked=sorted(scores.items(),key=lambda item:-item[1])
    best,score=ranked[0]
    if score<2: return 'other','No distinctive title or table evidence'
    if ranked[1][1]==score: return 'other',f'Ambiguous between {best} and {ranked[1][0]}'
    return best,'; '.join(dict.fromkeys(evidence[best]))
