"""Public ingestion vocabulary. Contains no benchmark answers or batch identifiers."""
from __future__ import annotations

import re
from pydantic import BaseModel, ConfigDict, Field

VOCAB = {
    'pH': {'unit':'pH','range':(0,14),'aliases':['pH','Acidity']},
    'temperature': {'unit':'K','range':(250,400),'aliases':['temperature','Temp']},
    'dissolved_oxygen': {'unit':'mg/L','range':(0,100),'aliases':['dissolved oxygen','DO2']},
    'substrate': {'unit':'g/L','range':(0,1000),'aliases':['substrate','Residual sugar']},
    'product': {'unit':'g/L','range':(0,1000),'aliases':['product','Penicillin','titer']},
    'sugar_feed': {'unit':'L/h','range':(0,100000),'aliases':['sugar feed','Feed rate']},
    'aeration': {'unit':'L/h','range':(0,1000000),'aliases':['aeration']},
    'agitation': {'unit':'rpm','range':(0,10000),'aliases':['agitation','Agitator RPM']},
    'acid_feed': {'unit':'L/h','range':(0,100000),'aliases':['acid feed']},
    'base_feed': {'unit':'L/h','range':(0,100000),'aliases':['base feed']},
    'volume': {'unit':'L','range':(0,1000000),'aliases':['volume','vessel volume']},
    'pressure': {'unit':'bar','range':(0,100),'aliases':['pressure']},
    'bioburden': {'unit':'CFU/mL','range':(0,10000000),'aliases':['bioburden']},
    'environment_cfu': {'unit':'CFU/m3','range':(0,10000000),'aliases':['environment cfu']},
    **{f'raman_{n}':{'unit':'unspecified','range':(-1e12,1e12),'aliases':[f'raman {n}']} for n in [1800,1000,500]},
}
TYPES = {'batch_record','instrument_export','environmental_monitoring','microbiology','coa',
         'maintenance','deviation_report','investigation_report','other'}


def key(value):
    return re.sub(r'[^a-z0-9]+',' ',str(value).casefold()).strip()


def header_parts(header):
    match = re.fullmatch(r'(.*?)\s*\[([^\]]+)\]', header)
    return (match[1].strip(),match[2].strip()) if match else (header,None)


def alias(parameter):
    name = key(header_parts(parameter)[0])
    return next((p for p,v in VOCAB.items() if name in {key(p),*(key(a) for a in v['aliases'])}),None)


class Mapping(BaseModel):
    model_config = ConfigDict(extra='forbid')
    columns: dict[str,str] = Field(default_factory=dict)
    batch_column: str | None = None
    time_column: str | None = None

    def check(self, headers):
        if any(p not in VOCAB for p in self.columns.values()):
            raise ValueError('Mapping uses a parameter outside the public vocabulary')
        if any(h not in headers for h in [*self.columns,*filter(None,[self.batch_column,self.time_column])]):
            raise ValueError('Mapping references an absent source header')
        return self


class Classification(BaseModel):
    model_config = ConfigDict(extra='forbid')
    doc_type: str
    confidence: float = Field(ge=0,le=1)


class ExtractedField(BaseModel):
    model_config = ConfigDict(extra='forbid')
    evidence_id: str
    header: str
    value_raw: str
    batch: str
    time: str
    review_reasons: list[str] = Field(default_factory=list)
    confidence: dict[str,float | None] = Field(default_factory=dict)
    source_spans: dict[str,list[int]] = Field(default_factory=dict)


class Extraction(BaseModel):
    model_config = ConfigDict(extra='forbid')
    fields: list[ExtractedField]
    reviews: list[dict] = Field(default_factory=list)


def draft_mapping(headers):
    return Mapping(columns={h:alias(h) for h in headers if alias(h)},
        batch_column=next((h for h in headers if key(h) in {'batch id','lot number','batch','batch number'}),None),
        time_column=next((h for h in headers if key(h) in {'elapsed h','process hours','time h','hour'}),None))


def normalize(value, raw_unit, parameter):
    """Explicit bioprocess units; dimensional mismatch never silently passes."""
    import math
    number=float(str(value).strip().replace(',','.'))
    if not math.isfinite(number): raise ValueError('Non-finite number')
    canonical=VOCAB[parameter]['unit']
    if raw_unit == canonical: return number,canonical
    conversions={('degC','K'):lambda n:n+273.15, ('C','K'):lambda n:n+273.15,
                 ('mg/mL','g/L'):lambda n:n, ('mg/L','g/L'):lambda n:n/1000,
                 ('g/L','mg/L'):lambda n:n*1000, ('mL/min','L/h'):lambda n:n*0.06,
                 ('kPa','bar'):lambda n:n/100, ('L/hr','L/h'):lambda n:n}
    if (raw_unit,canonical) not in conversions:
        raise ValueError(f'Cannot convert {raw_unit!r} to {canonical}')
    return conversions[(raw_unit,canonical)](number),canonical
