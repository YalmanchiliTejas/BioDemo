"""Host-only LIVE nominal simulator tool: no evaluator dataset or realization seed.

The packet contains all nominal initialization/equation assumptions. Native
simulation is isolated in this process because its parameter array is global.
"""
import argparse
import json
from pathlib import Path

from .experiment import scenario,metrics,model_prediction


def forward(packet,action,paths):
    if packet.get('experiment_version','').startswith('operating-challenges-'):
        from .challenges import forward as challenge_forward
        return challenge_forward(packet,action,paths)
    if packet['simulator']=='cho_real':
        from .cho_real import forward as cho_forward
        return cho_forward(packet,action)
    if action not in packet['allowed_actions']:
        raise ValueError('Action outside public grid')
    specs=packet['receiving_specifications']
    cap=specs.get('receiving_nominal_aeration_factor_vs_source',specs.get('receiving_nominal_balanced_flow_factor_vs_source'))
    fit=packet['source_calibration'].get('physical_parameter_fit')
    factors={k:fit[k] for k in ('kla_factor','growth_factor')} if fit else None
    result=scenario(packet['simulator'],0,cap,action,packet['task'],paths,nominal=True,parameter_overrides=factors)
    value=metrics(packet['simulator'],result,cutoff=80. if packet['simulator']=='pensim' and packet['task']!='transfer' else 0.)
    response=model_prediction(packet,{action:value},action)
    response['execution']='Fresh external-simulator execution in a separate credential-free host worker.'
    response['horizon_h']=specs['horizon_h']
    return response


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--packet',type=Path,required=True)
    p.add_argument('--action',required=True)
    p.add_argument('--pensim',required=True)
    p.add_argument('--smpl',required=True)
    p.add_argument('--native',required=True)
    args=p.parse_args()
    print(json.dumps(forward(json.loads(args.packet.read_text()),args.action,
        {'pensim':args.pensim,'smpl':args.smpl,'native':args.native}),allow_nan=False))
