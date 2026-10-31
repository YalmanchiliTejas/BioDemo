"""Public ingestion vocabulary. Contains no benchmark answers or batch identifiers."""
from __future__ import annotations

import math
import re
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

VOCAB = {
    'pH': {'unit':'pH','range':(0,14),'implied_unit':True,'aliases':['pH','Acidity','pH value','culture pH']},
    'temperature': {'unit':'K','range':(250,400),'aliases':['temperature','Temp','vessel temperature','broth temperature','culture temperature','reactor temperature']},
    'dissolved_oxygen': {'unit':'mg/L','range':(0,100),'aliases':['dissolved oxygen','DO2','DO','dO2']},
    'substrate': {'unit':'g/L','range':(0,1000),'aliases':['substrate','Residual sugar','substrate concentration']},
    'product': {'unit':'g/L','range':(0,1000),'aliases':['product','Penicillin','titer','titre','product concentration','product titer']},
    'sugar_feed': {'unit':'L/h','range':(0,100000),'aliases':['sugar feed','Feed rate','glucose feed','substrate feed','sugar feed rate']},
    'aeration': {'unit':'L/h','range':(0,1000000),'aliases':['aeration','air flow','airflow','air flow rate']},
    'agitation': {'unit':'rpm','range':(0,10000),'aliases':['agitation','agitation rate','Agitator RPM','agitator speed','stirrer speed','impeller speed','stir speed']},
    'acid_feed': {'unit':'L/h','range':(0,100000),'aliases':['acid feed','acid feed rate','acid addition']},
    'base_feed': {'unit':'L/h','range':(0,100000),'aliases':['base feed','base feed rate','base addition']},
    'volume': {'unit':'L','range':(0,1000000),'aliases':['volume','vessel volume','working volume','broth volume','liquid volume']},
    'pressure': {'unit':'bar','range':(0,100),'aliases':['pressure','vessel pressure','head pressure','headspace pressure','back pressure']},
    'bioburden': {'unit':'CFU/mL','range':(0,10000000),'aliases':['bioburden','total aerobic count','TAMC']},
    'environment_cfu': {'unit':'CFU/m3','range':(0,10000000),'aliases':['environment cfu','EM CFU','viable air','air viable count']},
    # Mammalian (CHO) cell culture. Saturation and standard-flow units are kept
    # distinct from mass-concentration and actual-flow units; no conversion is assumed.
    'do_saturation': {'unit':'% sat','range':(0,250),'aliases':['dissolved O2','DO saturation','dissolved oxygen saturation','pO2']},
    'dissolved_co2': {'unit':'% sat','range':(0,500),'aliases':['dissolved CO2','pCO2','dCO2']},
    'aeration_standard': {'unit':'sL/h','range':(0,1000000),'aliases':['aeration rate total','total aeration','aeration rate','gas flow total']},
    'viable_cell_density': {'unit':'cells/mL','range':(0,1e9),'aliases':['VCD','VCD mean','viable cell density','viable cell concentration']},
    'total_cell_density': {'unit':'cells/mL','range':(0,1e9),'aliases':['TCD','TCD mean','total cell density']},
    'viability': {'unit':'%','range':(0,100),'aliases':['viability','viability mean','cell viability']},
    'cell_diameter': {'unit':'µm','range':(0,100),'aliases':['avg diameter mean','average diameter','cell diameter','mean cell diameter']},
    'glucose': {'unit':'g/L','range':(0,100),'aliases':['glucose','residual glucose','glucose concentration']},
    'lactate': {'unit':'g/L','range':(0,100),'aliases':['lactate','lactate concentration']},
    'ammonium': {'unit':'mM','range':(0,100),'aliases':['ammonium','ammonia','NH4']},
    'osmolality': {'unit':'mOsm/kg','range':(0,2000),'aliases':['osmolality']},
    'feed_added': {'unit':'g','range':(0,1e7),'aliases':['cumulative feed weight','feed added','cumulative feed']},
    'base_added': {'unit':'g','range':(0,1e7),'aliases':['cumulative NaOH weight','base added','NaOH added','cumulative base']},
    **{f'raman_{n}':{'unit':'unspecified','range':(-1e12,1e12),'aliases':[f'raman {n}']} for n in [1800,1000,500]},
}
TYPES = {'batch_record','instrument_export','lab_results','environmental_monitoring','microbiology','coa',
         'maintenance','deviation_report','investigation_report','other'}

# Literal source spellings -> one canonical spelling. Only spellings, never
# physical conversions; conversions are explicit in ``normalize``.
UNIT_SPELLINGS = {
    'degc':'degC','°c':'degC','ºc':'degC','deg c':'degC','c':'C','celsius':'degC','k':'K','kelvin':'K',
    'g/l':'g/L','mg/l':'mg/L','mg/ml':'mg/mL','g/ml':'g/mL','l/h':'L/h','l/hr':'L/hr','l/hour':'L/h',
    'ml/min':'mL/min','l/min':'L/min','rpm':'rpm','bar':'bar','kpa':'kPa','psi':'psi','mbar':'mbar',
    'cfu/ml':'CFU/mL','cfu/m3':'CFU/m3','cfu/m³':'CFU/m3','l':'L','ml':'mL','ph':'pH','%':'%',
    'unspecified':'unspecified','unknown':'unknown','a.u.':'a.u.','au':'a.u.',
    '% air sat':'% sat','%-sat':'% sat','% sat':'% sat','%sat':'% sat','% air saturation':'% sat',
    'sl/h':'sL/h','slph':'sL/h','cells/ml':'cells/mL','µm':'µm','μm':'µm','um':'µm',
    'mosmol/kg':'mOsm/kg','mosm/kg':'mOsm/kg','g':'g','kg':'kg',
}
# Case matters for these: millimolar is not millimetre.
EXACT_UNITS = {'mM':'mM','mm':'mm'}
TIME_UNITS = {'h','hr','hrs','hour','hours'}
BATCH_HEADERS = {'batch id','lot number','batch','batch number','batch no','lot','lot no','lot id','batch lot','lot batch'}
TIME_HEADERS = {'elapsed h','process hours','time h','hour','hours','elapsed time','elapsed time h','process time',
                'process time h','eft','eft h','culture time','culture time h','age h','time hr','elapsed hours'}
TIME_STEMS = {'time','elapsed','elapsed time','process time','culture time','age','eft','duration'}


def key(value):
    return re.sub(r'[^a-z0-9]+',' ',str(value).casefold()).strip()


def canonical_unit(unit):
    if unit is None: return None
    text=str(unit).strip()
    if text in EXACT_UNITS: return EXACT_UNITS[text]
    return UNIT_SPELLINGS.get(text.casefold(),text)


def known_unit(text):
    text=text.strip()
    return text in EXACT_UNITS or text.casefold() in UNIT_SPELLINGS or text.casefold() in TIME_UNITS


def header_parts(header):
    """Split a header into (name, literal unit). Brackets always denote a unit;
    parentheses only when their content is a recognised unit spelling."""
    text=str(header)
    match = re.fullmatch(r'(.*?)\s*\[([^\]]+)\]', text)
    if match: return (match[1].strip(),match[2].strip())
    match = re.fullmatch(r'(.*?)\s*\(([^()]+)\)', text)
    if match and known_unit(match[2]):
        return (match[1].strip(),match[2].strip())
    return (text,None)


def alias(parameter):
    name, unit = header_parts(parameter)
    name = key(name)
    match = next((p for p,v in VOCAB.items() if name in {key(p),*(key(a) for a in v['aliases'])}),None)
    # The printed unit can say a DO reading is a saturation, not a concentration.
    if match=='dissolved_oxygen' and canonical_unit(unit)=='% sat': return 'do_saturation'
    return match


def is_batch_header(header):
    return key(header) in BATCH_HEADERS or key(header_parts(header)[0]) in BATCH_HEADERS


def is_time_header(header):
    name,unit=header_parts(header)
    if key(header) in TIME_HEADERS or key(name) in TIME_HEADERS: return True
    return unit is not None and unit.casefold() in TIME_UNITS and key(name) in TIME_STEMS


class Mapping(BaseModel):
    model_config = ConfigDict(extra='forbid')
    columns: dict[str,str] = Field(default_factory=dict)
    batch_column: str | None = None
    time_column: str | None = None
    # Reviewer declarations that remove repeated per-value work on returning
    # deliveries: units for headers that print none (or an ambiguous one), and
    # columns deliberately excluded from the dataset.
    units: dict[str,str] = Field(default_factory=dict)
    ignored_columns: list[str] = Field(default_factory=list)

    def check(self, headers):
        if any(p not in VOCAB for p in self.columns.values()):
            raise ValueError('Mapping uses a parameter outside the public vocabulary')
        referenced=[*self.columns,*filter(None,[self.batch_column,self.time_column]),*self.units,*self.ignored_columns]
        if any(h not in headers for h in referenced):
            raise ValueError('Mapping references an absent source header')
        if set(self.ignored_columns)&{*self.columns,self.batch_column,self.time_column}:
            raise ValueError('A column cannot be both mapped and ignored')
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
    return Mapping(columns={h:alias(h) for h in headers if alias(h) and not is_batch_header(h) and not is_time_header(h)},
        batch_column=next((h for h in headers if is_batch_header(h)),None),
        time_column=next((h for h in headers if is_time_header(h)),None))


def time_key(value):
    """Order/identity key for a process time: elapsed hours or an ISO timestamp.
    Raises ValueError for anything else; never guesses a format."""
    text=str(value).strip()
    try:
        hour=float(text.replace(',','.'))
        if not math.isfinite(hour) or hour<0: raise ValueError('Invalid elapsed time')
        return hour
    except ValueError:
        pass
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?',text):
        stamp=datetime.fromisoformat(text.replace('Z','+00:00'))
        if stamp.tzinfo is None:
            raise ValueError('Timestamp lacks a UTC offset; declare the time zone before acceptance')
        return stamp.timestamp()
    raise ValueError('Process time must be elapsed hours or an ISO timestamp with offset')


def normalize(value, raw_unit, parameter):
    """Explicit bioprocess units; dimensional mismatch never silently passes."""
    number=float(str(value).strip().replace(',','.'))
    if not math.isfinite(number): raise ValueError('Non-finite number')
    canonical=VOCAB[parameter]['unit']
    unit=canonical_unit(raw_unit)
    if unit is None and VOCAB[parameter].get('implied_unit'): unit=canonical
    if unit == canonical: return number,canonical
    conversions={('degC','K'):lambda n:n+273.15, ('C','K'):lambda n:n+273.15,
                 ('mg/mL','g/L'):lambda n:n, ('mg/L','g/L'):lambda n:n/1000,
                 ('g/L','mg/L'):lambda n:n*1000, ('mL/min','L/h'):lambda n:n*0.06,
                 ('L/min','L/h'):lambda n:n*60, ('kPa','bar'):lambda n:n/100, ('mbar','bar'):lambda n:n/1000,
                 ('psi','bar'):lambda n:n*0.0689475729, ('L/hr','L/h'):lambda n:n, ('mL','L'):lambda n:n/1000}
    if (unit,canonical) not in conversions:
        raise ValueError(f'Cannot convert {raw_unit!r} to {canonical}')
    return conversions[(unit,canonical)](number),canonical
