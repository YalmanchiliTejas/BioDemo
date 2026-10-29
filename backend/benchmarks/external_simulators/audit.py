"""Supplemental recorded numerical/provenance checks, separate from agent trials."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

import numpy as np

from .experiment import checked,dump
from .upstream import pen_module


def parity(dataset,output):
    paths=checked(dataset,'protocol.json')['paths']
    module=pen_module(Path(paths['pensim']),Path(paths['native']))
    receipt=json.loads((dataset/'qualification/pensim/baseline.json').read_text())
    points=[]
    for sample in receipt['rhs_samples']:
        for ph in (6.5,7.2):
            for inhibition in (0,1,2):
                for disturbance in (0,1):
                    for viscosity in (0,1):
                        state=np.array(sample['state'],dtype=float)
                        state[6]=10.**(-ph)
                        parameters=np.array(sample['parameters'],dtype=float)
                        parameters[5]=inhibition;parameters[21]=disturbance;parameters[30]=viscosity
                        a=np.array(module.fastodeint.rhs(state.copy(),parameters,sample['time_h']))
                        # The upstream Python RHS mutates pH>=7 inputs; isolate that side effect.
                        b=np.array(module.indpensim_ode_py(sample['time_h'],state.copy(),parameters))
                        error=float(np.max(np.abs(a-b)/(1+np.abs(b))))
                        points.append({'time_h':sample['time_h'],'pH':ph,'inhibition':inhibition,
                                       'disturbance':disturbance,'viscosity':viscosity,'relative_error':error})
    result={'points_checked':len(points),'maximum_relative_error':max(p['relative_error'] for p in points),
            'passed':all(p['relative_error']<1e-8 for p in points),
            'scope':'Native corrected port RHS versus supplied Python RHS; mathematical parity, not experimental accuracy.',
            'points':points}
    dump(output/'native-python-parity.json',result)
    return result


def packet_audit(dataset,output):
    catalogue=checked(dataset,'public/catalogue.json');violations=[];floors=[]
    for item in catalogue:
        case=item['case_id'];packet=checked(dataset,f'public/{case}/packet.json')
        if item['task']=='transfer' and packet['receiving_observations']:
            violations.append({'case':case,'error':'receiving observations before transfer'})
        for row in packet['receiving_observations']:
            if row['time_h']>packet['decision_time_h']+1e-8:
                violations.append({'case':case,'error':'future receiving observation'})
        if item['simulator']=='mab':
            if packet['receiving_specifications']['nominal_source_initial']['temperature']!=36.8:
                violations.append({'case':case,'error':'nominal temperature mismatch'})
        else:
            flags=packet['receiving_specifications']['nominal_control_flags']
            if flags['Dis']!=0:violations.append({'case':case,'error':'hidden nominal future disturbances enabled'})
        truth=checked(dataset,f'evaluator/{case}/truth.json')
        for action,result in truth['complete_trajectories'].items():
            if result.get('audit',{}).get('dissolved_oxygen_floor_events',0):
                floors.append({'case':case,'action':action,'events':result['audit']['dissolved_oxygen_floor_events']})
    result={'packets_checked':len(catalogue),'passed':not violations,'violations':violations,
            'receiving_DO_floor_events':floors,
            'scope':'Programmatic cutoff and declared nominal-configuration checks; not an exhaustive security or scientific review.'}
    dump(output/'packet-audit.json',result)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--dataset',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    values={'parity':parity(args.dataset,args.output),'packets':packet_audit(args.dataset,args.output)}
    print(json.dumps({k:{x:y for x,y in value.items() if x not in ('points',)} for k,value in values.items()},indent=2))
