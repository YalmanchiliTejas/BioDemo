"""Reproducible statistics, source-clock alignment, and numerical claim checks.

These operations establish arithmetic and provenance, never biological causation.
"""
from __future__ import annotations

import bisect
import hashlib
import json
import math
import statistics
from collections import defaultdict


VERSION = 'deterministic-analysis-v2'


def _hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest()


def _finite(value):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
        raise ValueError('metric values must be finite numbers')
    return float(value)


def _selection(selection):
    if not isinstance(selection,dict) or not selection.get('name'):
        raise ValueError('a selection requires an exact measurement name')
    clauses, params = ['value_number IS NOT NULL'], []
    for key in ('name','entity_id','source_id','sheet'):
        if key in selection:
            clauses.append(key+' IS NOT DISTINCT FROM ?');params.append(selection[key])
    for key,op in [('time_start','>='),('time_end','<=')]:
        if selection.get(key) is not None:
            clauses.append('time_value'+op+'?');params.append(_finite(selection[key]))
    if set(selection)-{'name','entity_id','source_id','sheet','time_start','time_end'}:
        raise ValueError('unsupported measurement selection field')
    return ' AND '.join(clauses),params


class DeterministicAnalysis:
    def __init__(self,store,*,as_of=None,scopes=('default',)):
        self.store,self.as_of,self.scopes=store,as_of,tuple(scopes)
        self._prepared=None

    def _lineage(self,*,force=False):
        sources=[s for s in self.store.visible_sources(as_of=self.as_of,scopes=self.scopes) if s['extraction_status']=='indexed']
        manifests=self.store.partition_fingerprints([s['id'] for s in sources],force=force)
        return [{'source_id':s['id'],'path':s['path'],'sha256':s['sha256'],'pipeline_version':s['pipeline_version'],
                 'partition_manifest_sha256':manifests[s['id']]} for s in sources]

    def prepare(self):
        if self._prepared is not None:
            return self._prepared
        # All computations happen in DuckDB. No full-table transfer to Python.
        rows=self.store.select("""SELECT source_id,entity_id,sheet,name,unit,time_basis,
            count(*) AS n,avg(value_number) AS mean,stddev_samp(value_number) AS sample_sd,
            min(value_number) AS minimum,max(value_number) AS maximum,
            arg_min(id,value_number) AS minimum_id,arg_max(id,value_number) AS maximum_id,
            arg_min(value_number,time_value) AS first_value,arg_max(value_number,time_value) AS last_value,
            arg_min(id,time_value) AS first_id,arg_max(id,time_value) AS last_id,
            arg_min(time_evidence_id,time_value) AS first_time_id,arg_max(time_evidence_id,time_value) AS last_time_id,
            min(time_value) AS time_start,max(time_value) AS time_end,
            count(time_value) AS timed_n,count(DISTINCT time_value) AS distinct_times,
            count(*) FILTER (WHERE value_number<0) AS negative_n,
            count(*) FILTER (WHERE value_number<0 OR value_number>100) AS outside_percent_n
            FROM observations WHERE value_number IS NOT NULL AND NOT is_time_axis
            GROUP BY source_id,entity_id,sheet,name,unit,time_basis
            ORDER BY source_id,entity_id,sheet,name,time_basis""",as_of=self.as_of,scopes=self.scopes)
        clocks=self.store.select('SELECT source_id,entity_id,sheet,count(*) FILTER (WHERE time_value<previous_time) AS backwards_steps '
            'FROM (SELECT source_id,entity_id,sheet,time_value,lag(time_value) OVER '
            '(PARTITION BY source_id,entity_id,sheet ORDER BY source_row) AS previous_time '
            'FROM observations WHERE is_time_axis AND time_value IS NOT NULL) '
            'GROUP BY source_id,entity_id,sheet',as_of=self.as_of,scopes=self.scopes)
        clock_quality={(r['source_id'],r['entity_id'],r['sheet']):r['backwards_steps'] for r in clocks}
        sources=self._lineage(); source_hashes={r['source_id']:r['sha256'] for r in sources}
        anomalies=[]; ids=set(); compared=defaultdict(list)
        for row in rows:
            row['selection']={k:row[k] for k in ('source_id','entity_id','sheet','name')}
            row['source_sha256']=source_hashes[row['source_id']]
            row['statistics_basis']='observed_timepoints; not independent biological replicates'
            row['source_summary_status']=('reported_mean' if 'mean' in row['name'].lower() else
                                          'reported_sem_not_recomputed' if 'sem' in row['name'].lower() else 'source_measurement')
            row['evidence_ids']=list(dict.fromkeys(row[k] for k in ('minimum_id','maximum_id','first_id','last_id','first_time_id','last_time_id') if row[k]))
            ids.update(row['evidence_ids'])
            row['source_backwards_steps']=clock_quality.get((row['source_id'],row['entity_id'],row['sheet']),0)
            flags=[]
            if row['source_backwards_steps']:flags.append('backwards_source_time; possible reset or out-of-order acquisition')
            if row['timed_n']!=row['n']:flags.append('missing_source_time')
            if row['distinct_times']<row['timed_n']:flags.append('duplicate_source_times')
            if row['n']>=5 and row['minimum']==row['maximum']:flags.append('constant_series; may be intentional')
            if 'sem' in row['name'].lower() and row['negative_n']:flags.append('negative_reported_sem')
            if row['unit']=='%' and row['outside_percent_n']:flags.append('percentage_outside_0_100')
            if flags:anomalies.append({k:row[k] for k in ('source_id','entity_id','sheet','name','minimum','maximum','time_start','time_end','evidence_ids')}|{'flags':flags})
            compared[(row['source_id'],row['name'],row['unit'],row['time_basis'])].append(row)
        comparisons=[]
        for key,group in compared.items():
            if len(group)!=2 or len({r['entity_id'] for r in group})!=2:continue
            left,right=group
            denominator=min(abs(left['maximum']),abs(right['maximum']))
            difference=100*abs(left['maximum']-right['maximum'])/denominator if denominator else None
            comparisons.append({'source_id':key[0],'name':key[1],'unit':key[2],
                                'entity_ids':[left['entity_id'],right['entity_id']],
                                'peak_values':[left['maximum'],right['maximum']],
                                'peak_difference_percent_relative_to_smaller_absolute_peak':difference,
                                'formula':'100 * abs(peak_a - peak_b) / min(abs(peak_a), abs(peak_b))',
                                'status':'descriptive_comparison; design equivalence not established',
                                'evidence_ids':[left['maximum_id'],right['maximum_id']]})
        comparisons.sort(key=lambda r:('mean' in r['name'].lower(),r['peak_difference_percent_relative_to_smaller_absolute_peak'] or 0),reverse=True)
        anomalies.sort(key=lambda r:(any(f.startswith(('negative_reported_sem','percentage_outside')) for f in r['flags']),any(f.startswith(('missing_source_time','duplicate_source_times')) for f in r['flags'])),reverse=True)
        self._prepared={'version':VERSION,'as_of':self.as_of,'scopes':list(self.scopes),
                        'source_versions':sources,'series_count':len(rows),'series':rows,
                        'anomalies':anomalies,'paired_peak_comparisons':comparisons,
                        'evidence_ids':sorted(ids),'limitations':[
                            'Reported mean/SEM columns are source summaries; raw replicate counts are not reconstructed.',
                            'Timepoint standard deviations are descriptive and must not be presented as biological replicate SEMs.',
                            'Anomaly flags and peak comparisons do not establish specification failure or causation.',
                            'Alignment uses source clocks; missing/ambiguous time coordinates are never replaced by row numbers.']}
        from .screening import build_screening
        self._prepared['screening']=build_screening(rows,anomalies,comparisons,sources)
        # Narrative-only sources previously had no initial anchors. These are
        # evidence pointers, never an assertion of completed review.
        for unit in self._prepared['screening']['coverage_units']:
            if unit['series_count']:continue
            anchors=self.store.select('SELECT id FROM observations WHERE source_id=? ORDER BY source_row,id LIMIT 24',
                [unit['source_id']],as_of=self.as_of,scopes=self.scopes)
            unit['evidence_ids']=[r['id'] for r in anchors]
            unit['screening_status']='narrative source anchors available; review required'
            ids.update(unit['evidence_ids'])
        self._prepared['evidence_ids']=sorted(ids)
        return self._prepared

    def compact(self):
        prepared=self.prepare()
        screening={k:v for k,v in prepared['screening'].items() if k not in {'candidates','coverage_units','priority_candidates'}}
        screening['coverage_units']=[{**u,'evidence_ids':u['evidence_ids'][:6],
            'full_anchor_count':len(u['evidence_ids'])} for u in prepared['screening']['coverage_units']]
        screening['priority_candidates']=[{**c,'members':c.get('members',[])[:5],
            'evidence_ids':c['evidence_ids'][:8],'full_anchor_count':len(c['evidence_ids'])}
            for c in prepared['screening']['priority_candidates']]
        peak_keys={(c['source_id'],c.get('name')) for c in screening['priority_candidates'] if c['category']=='paired_measurements'}
        quality_keys={(c['source_id'],e) for c in screening['priority_candidates'] if c.get('members') for e in c['entity_ids']}
        legacy_anomalies=[];included=set()
        for item in prepared['anomalies']:
            key=(item['source_id'],item['entity_id'])
            if key in quality_keys and key not in included:
                legacy_anomalies.append(item);included.add(key)
        return {k:prepared[k] for k in ('version','series_count','source_versions','limitations')}|{
            'screening':screening,
            'anomalies':legacy_anomalies,
            'paired_peak_comparisons':[c for c in prepared['paired_peak_comparisons'] if (c['source_id'],c['name']) in peak_keys],
            'anomaly_count':len(prepared['anomalies']),
            'evidence_ids':list(dict.fromkeys(i for item in screening['priority_candidates']+screening['coverage_units'] for i in item['evidence_ids']))}

    def _values(self,identifiers):
        if not isinstance(identifiers,list) or not identifiers or len(identifiers)>1000:
            raise ValueError('metric input IDs must contain 1-1000 observations')
        if len(set(identifiers))!=len(identifiers):
            raise ValueError('duplicate observations cannot be counted as additional replicates')
        rows=self.store.get_many(identifiers,as_of=self.as_of,scopes=self.scopes)
        if len(rows)!=len(identifiers):raise ValueError('metric cites unavailable evidence')
        for row in rows:_finite(row['value_number'])
        return rows

    @staticmethod
    def _unit(rows):
        units={r['unit'] for r in rows}
        if len(units)!=1:raise ValueError('metric input units differ; normalize them explicitly first')
        return next(iter(units))

    @staticmethod
    def _convert(value,source,target):
        if source==target:return value
        if not source or not target:raise ValueError('cannot compare unknown or incompatible units')
        import pint
        registry=pint.UnitRegistry()
        try:return float(registry.Quantity(value,source).to(target).magnitude)
        except Exception as exc:raise ValueError('metric input units are not compatible') from exc

    def calculate(self,spec):
        if not isinstance(spec,dict):raise ValueError('metric must be an object')
        sources=self._lineage()
        op=spec.get('operation'); ids=[]; assumptions=[]; unit=None
        unary={'mean','sem','sample_sd','sum','minimum','maximum','count'}
        selection=spec.get('selection')
        if op in unary and selection:
            where,params=_selection(selection)
            row=self.store.select('SELECT count(*) AS n,avg(value_number) AS mean,stddev_samp(value_number) AS sample_sd,'
                                  'sum(value_number) AS sum,min(value_number) AS minimum,max(value_number) AS maximum,'
                                  'list(DISTINCT unit) AS units,arg_min(id,value_number) AS min_id,arg_max(id,value_number) AS max_id,'
                                  "count(DISTINCT time_value) AS times,count(time_value) AS timed_n,"
                                  "count(*) FILTER (WHERE lower(name) LIKE '%mean%' OR lower(name) LIKE '%sem%') AS summarized_n "
                                  'FROM observations WHERE '+where,params,as_of=self.as_of,scopes=self.scopes)[0]
            if row['n']==0:raise ValueError('metric selection contains no visible numeric observations')
            if len(row['units'])!=1:raise ValueError('metric selection contains mixed units')
            unit=row['units'][0];n=row['n'];ids=[row['min_id'],row['max_id']]
            if op=='sem':
                if spec.get('sampling_basis')!='independent_replicates' or row['times']>1 or row['summarized_n']:
                    raise ValueError('SEM requires declared independent replicates at one source time; time-series points are not replicates')
                assumptions.append('Independence of replicates is declared, not established by arithmetic.')
            value=n if op=='count' else row['sample_sd']/math.sqrt(n) if op=='sem' and n>=2 else row.get(op)
            if value is None:raise ValueError('sample SD/SEM requires at least two observations')
        elif op in unary:
            rows=self._values(spec.get('evidence_ids'));ids=[r['id'] for r in rows]
            unit=self._unit(rows);values=[r['value_number'] for r in rows];n=len(values)
            if op=='sem':
                if spec.get('sampling_basis')!='independent_replicates' or len({(r.get('time_basis'),r.get('time_value')) for r in rows})>1:
                    raise ValueError('SEM requires declared independent replicates at one source time; time-series points are not replicates')
                if any('sem' in r['name'].lower() or 'mean' in r['name'].lower() for r in rows):
                    raise ValueError('reported means/SEMs cannot substitute for raw replicates')
                assumptions.append('Independence of replicates is declared, not established by arithmetic.')
            if op in {'sem','sample_sd'} and n<2:raise ValueError('sample SD/SEM requires at least two observations')
            value={'mean':lambda:statistics.fmean(values),'sum':lambda:math.fsum(values),'minimum':lambda:min(values),
                   'maximum':lambda:max(values),'count':lambda:n,'sample_sd':lambda:statistics.stdev(values),
                   'sem':lambda:statistics.stdev(values)/math.sqrt(n)}[op]()
        elif op in {'percentage','percent_change','ratio','difference','yield'}:
            numerator=self._values(spec.get('numerator_ids'));denominator=self._values(spec.get('denominator_ids'))
            ids=[r['id'] for r in numerator+denominator]
            numerator_unit=self._unit(numerator);denominator_unit=self._unit(denominator)
            if op=='yield':
                if len(numerator)!=2 or len(denominator)!=2:raise ValueError('yield requires start/end observations for both quantities')
                if not str(spec.get('definition','')).strip():raise ValueError('yield requires an explicit physical definition')
                coordinates=[(r.get('entity_id'),r.get('time_basis'),r.get('time_value')) for r in numerator+denominator]
                if any(c[0] is None or c[1]=='unresolved' or c[2] is None for c in coordinates):raise ValueError('yield requires actual source time coordinates')
                if coordinates[0]!=coordinates[2] or coordinates[1]!=coordinates[3] or coordinates[0][:2]!=coordinates[1][:2] or coordinates[1][2]<=coordinates[0][2]:
                    raise ValueError('yield endpoints must share entity, time basis, and exact start/end times')
                consumed=denominator[0]['value_number']-denominator[1]['value_number']
                if consumed<=0:raise ValueError('yield denominator must be positive substrate consumption')
                value=(numerator[1]['value_number']-numerator[0]['value_number'])/consumed
                unit=f'({numerator_unit or "unknown"})/({denominator_unit or "unknown"})'
                assumptions.append('Apparent concentration-change yield; feed, dilution, volume and mass balance are not validated.')
            else:
                if len(numerator)!=1 or len(denominator)!=1:raise ValueError('ratio/percentage/difference requires one observation on each side')
                if op in {'percentage','ratio'}:
                    left_coordinate=tuple(numerator[0].get(k) for k in ('entity_id','time_basis','time_value'))
                    right_coordinate=tuple(denominator[0].get(k) for k in ('entity_id','time_basis','time_value'))
                    if left_coordinate!=right_coordinate or left_coordinate[2] is None:
                        if not str(spec.get('comparison_basis','')).strip():
                            raise ValueError('unaligned ratio/percentage requires an explicit comparison_basis')
                        assumptions.append('Ratio/percentage is not an aligned same-sample comparison: '+str(spec['comparison_basis']))
                left=numerator[0]['value_number'];right=self._convert(denominator[0]['value_number'],denominator_unit,numerator_unit)
                if op=='difference':value=left-right;unit=numerator_unit
                else:
                    if right==0:raise ValueError('metric denominator is zero')
                    value=(left-right)/right*100 if op=='percent_change' else left/right*(100 if op=='percentage' else 1)
                    unit='%' if op in {'percentage','percent_change'} else 'dimensionless'
        else:raise ValueError('unsupported deterministic metric operation')
        value=_finite(value)
        if op=='count':unit='count'
        if spec.get('claimed_unit') is not None:
            value=self._convert(value,unit,spec['claimed_unit'])
            unit=spec['claimed_unit']
        display_decimals=spec.get('display_decimals')
        if display_decimals is not None and (type(display_decimals) is not int or not -12<=display_decimals<=12):
            raise ValueError('display_decimals must be an integer between -12 and 12')
        display_value=round(value,display_decimals) if display_decimals is not None else value
        if 'claimed_value' in spec:
            if not math.isclose(_finite(spec['claimed_value']),display_value,rel_tol=1e-6,abs_tol=0.0):
                raise ValueError(f'metric {spec.get("metric_id",op)} does not match deterministic calculation')
        lineage={'version':VERSION,'specification':{k:v for k,v in spec.items() if k!='claimed_value'},
                 'as_of':self.as_of,'scopes':self.scopes,'source_versions':sources}
        if unit is None:assumptions.append('Source unit is unspecified; dimensional meaning requires review.')
        receipt={'metric_id':str(spec.get('metric_id') or _hash(lineage)[:24]),'operation':op,'value':value,'unit':unit,
                 'display_value':display_value,'specification':lineage['specification'],'lineage':lineage,'lineage_sha256':_hash(lineage),
                 'evidence_ids':list(dict.fromkeys(ids)),'verification':'arithmetic_verified',
                 'assumptions':assumptions,'causality_verified':False}
        return receipt

    def align(self,left,right,*,method='exact',tolerance_hours=0.0,limit=100,offset=0,allow_time_reordering=False):
        tolerance_hours=_finite(tolerance_hours)
        if tolerance_hours<0 or method not in {'exact','nearest','linear'}:raise ValueError('invalid alignment method/tolerance')
        if not left.get('entity_id') or left.get('entity_id')!=right.get('entity_id'):
            raise ValueError('alignment requires the same explicit entity on both sides')
        series=[];order_warnings=[]
        for selection in (left,right):
            where,params=_selection(selection)
            rows=self.store.select('SELECT id,source_id,sheet,source_row,source_ref,value_number,time_value,time_basis,time_evidence_id '
                                   'FROM observations WHERE '+where+' ORDER BY time_value,id LIMIT 1000001',
                                   params,as_of=self.as_of,scopes=self.scopes)
            if len(rows)>1_000_000:raise ValueError('alignment series too large; narrow the source time interval')
            if not rows:raise ValueError('alignment selection has no visible measurements')
            if any(r['time_value'] is None or not r['time_evidence_id'] for r in rows):raise ValueError('alignment requires actual visible source time coordinates')
            if len({r['time_value'] for r in rows})!=len(rows):raise ValueError('duplicate source timestamps require explicit resolution before alignment')
            source_order=defaultdict(list)
            for r in rows:source_order[(r['source_id'],r['sheet'])].append(r)
            backwards=sum(sum(b['time_value']<a['time_value'] for a,b in zip(ordered,ordered[1:]))
                          for ordered in (sorted(group,key=lambda r:r['source_row']) for group in source_order.values()))
            if backwards and not allow_time_reordering:
                raise ValueError('source time moves backwards; resolve clock resets or explicitly allow_time_reordering')
            if backwards:order_warnings.append({'selection':selection,'backwards_steps':backwards,'clock_reset_resolved':False})
            series.append(rows)
        left_rows,right_rows=series
        if len({r['time_basis'] for r in left_rows+right_rows})!=1:raise ValueError('cannot align different time bases')
        times=[r['time_value'] for r in right_rows];records=[];ids=set()
        for row in left_rows[offset:offset+limit]:
            stamp=row['time_value'];index=bisect.bisect_left(times,stamp)
            item={'left_id':row['id'],'left_value':row['value_number'],'time_value':stamp,
                  'time_basis':row['time_basis'],'left_time_id':row['time_evidence_id'],
                  'status':'unmatched','right_ids':[]}
            candidates=[]
            if index<len(times) and times[index]==stamp:
                candidates=[right_rows[index]];weights=[1.0];item['status']='exact'
            elif method=='nearest':
                choices=[i for i in (index-1,index) if 0<=i<len(times)]
                distance=min((abs(times[i]-stamp) for i in choices),default=math.inf)
                choices=[i for i in choices if math.isclose(abs(times[i]-stamp),distance,rel_tol=0,abs_tol=1e-12)]
                if distance<=tolerance_hours:
                    if len(choices)==1:candidates=[right_rows[choices[0]]];weights=[1.0];item['status']='nearest'
                    else:item['status']='ambiguous_nearest_tie'
            elif method=='linear' and 0<index<len(times):
                low,high=times[index-1:index+1]
                if max(stamp-low,high-stamp)<=tolerance_hours:
                    candidates=[right_rows[index-1],right_rows[index]]
                    weights=[(high-stamp)/(high-low),(stamp-low)/(high-low)];item['status']='interpolated'
            if candidates:
                item.update(right_value=math.fsum(r['value_number']*w for r,w in zip(candidates,weights)),
                            right_ids=[r['id'] for r in candidates],right_time_ids=[r['time_evidence_id'] for r in candidates],
                            right_times=[r['time_value'] for r in candidates],weights=weights,
                            source_refs=[json.loads(r['source_ref']) for r in [row]+candidates])
                ids.update(item['right_ids']+item['right_time_ids'])
            ids.update([row['id'],row['time_evidence_id']]);records.append(item)
        return {'records':records,'method':method,'tolerance_hours':tolerance_hours,
                'left_count':len(left_rows),'right_count':len(right_rows),'evidence_ids':sorted(ids),
                'source_measurements_modified':False,'extrapolation':False,'source_order_warnings':order_warnings,
                'assumptions':['Elapsed source clocks are assumed to share the entity’s recorded origin; calibration is not independently established.']}
