"""Effective source calibration using available DO/product, with explicit priors.

No perfect substrate, hidden receiver parameters or future outcome fitting.
Uncertainty is a declared sensitivity ensemble, not a calibrated probability.
"""
from copy import deepcopy
import json
import numpy as np
from scipy.optimize import least_squares
from .pensim import simulate,outcomes

KEYS=('kla_factor','growth_factor','production_factor')
SOURCE_BOUNDS=([.765,.878,.878],[1.235,1.122,1.122])


def fit_source(paths,rows):
    # Avoid treating hundreds of correlated sensor points as independent assays.
    selected=[r for r in rows if r['field']=='P' or (r['field']=='DO2' and abs(r['time_h']/4-round(r['time_h']/4))<1e-7)]
    if len([r for r in selected if r['field']=='P'])<4:raise ValueError('Insufficient source product assays')
    def residual(z):
        factors=dict(zip(KEYS,map(float,np.exp(z))))
        result=simulate(paths,seed=0,factors=factors,transfer_multiplier=1.,decision_h=52.)
        lookup={round(r['time_h'],6):r['state'] for r in result['trace']}
        errors=[(lookup[round(r['time_h'],6)][r['field']]-r['value'])/(.3 if r['field']=='DO2' else .1) for r in selected]
        # Effective kinetics are weakly identifiable; shrink to simulator prior.
        return np.r_[errors,z/np.array([.118,.061,.061])]
    fit=least_squares(residual,np.zeros(3),bounds=(np.log(SOURCE_BOUNDS[0]),np.log(SOURCE_BOUNDS[1])),max_nfev=35,diff_step=.001,loss='soft_l1')
    return {'factors':dict(zip(KEYS,map(float,np.exp(fit.x)))),'success':bool(fit.success),'cost':float(fit.cost),
        'fields':['P','DO2'],'source_times_h':sorted(set(r['time_h'] for r in selected)),
        'bounds':SOURCE_BOUNDS,'uncertainty':'Declared sensitivity bounds, not empirically calibrated receiver probabilities.'}


class ReceivingModel:
    def __init__(self,paths,source_fit):self.paths=paths;self.source_fit=deepcopy(source_fit);self.updates={};self.evidence_key=None
    def update(self,packet):
        clock=packet['decision_time_h'];rows=packet['receiving_observations']
        if any(r['available_at_h']>clock+1e-8 or r['time_h']>clock+1e-8 for r in rows):raise ValueError('Future observation in model update')
        key=json.dumps(rows,sort_keys=True)+str(clock)
        if self.evidence_key==key:return
        # Candidate onset search is fixed; no true receiver onset is supplied.
        recent=[r for r in rows if r['field']=='DO2' and r['time_h']>=40 and abs(r['time_h']-round(r['time_h']))<1e-7]
        if not recent:raise ValueError('No usable receiver oxygen observations')
        choices=[]
        for onset in [44.,48.,50.]:
            def residual(z):
                r=simulate(self.paths,seed=0,factors=self.source_fit['factors'],disturbance_h=onset,transfer_multiplier=float(np.exp(z[0])),decision_h=clock)
                lookup={round(v['time_h'],6):v['state']['DO2'] for v in r['trace']}
                return np.r_[[(lookup[round(v['time_h'],6)]-v['value'])/.3 for v in recent],z/.4]
            fit=least_squares(residual,[0.],bounds=([np.log(.4)],[np.log(1.4)]),max_nfev=20,diff_step=.001,loss='soft_l1')
            choices.append((float(fit.cost),onset,float(np.exp(fit.x[0]))))
        cost,onset,multiplier=min(choices)
        self.evidence_key=key
        self.updates={'time_h':clock,'estimated_change_h':onset,'estimated_transfer_multiplier':multiplier,'cost':cost,'latest_observation_h':max(r['time_h'] for r in rows)}
    def __call__(self,packet,action):
        self.update(packet)
        result=simulate(self.paths,seed=0,factors=self.source_fit['factors'],disturbance_h=self.updates['estimated_change_h'],transfer_multiplier=self.updates['estimated_transfer_multiplier'],decision_h=packet['decision_time_h'],action=action)
        return {'classification':'model_prediction_not_observation','model_update':deepcopy(self.updates),'outcome_prediction':outcomes(result)}


class SensitivityReceivingModel(ReceivingModel):
    """Fixed finite sensitivity set; ranges are not calibrated confidence bounds."""
    def __call__(self,packet,action):
        central=super().__call__(packet,action)
        variants=[]
        # Fixed prior-scale perturbations, never selected using receiver outcomes.
        for kla,growth,production in [(.88,1.,1.),(1.12,1.,1.),(1.,.94,.94),(1.,1.06,1.06)]:
            factors=deepcopy(self.source_fit['factors'])
            factors['kla_factor']*=kla;factors['growth_factor']*=growth;factors['production_factor']*=production
            run=simulate(self.paths,seed=0,factors=factors,disturbance_h=self.updates['estimated_change_h'],transfer_multiplier=self.updates['estimated_transfer_multiplier'],decision_h=packet['decision_time_h'],action=action)
            variants.append(outcomes(run))
        members=[central['outcome_prediction'],*variants]
        central['sensitivity']={'members':len(members),'feasible_members':sum(v['post_decision_feasible'] for v in members),
            'product_mass_kg_range':[min(v['product_mass_kg'] for v in members),max(v['product_mass_kg'] for v in members)],
            'minimum_do_mg_l_range':[min(v['post_decision']['minimum_do_mg_l'] for v in members if v['post_decision']['minimum_do_mg_l'] is not None),max(v['post_decision']['minimum_do_mg_l'] for v in members if v['post_decision']['minimum_do_mg_l'] is not None)] if action!='stop' else None,
            'interpretation':'Finite assumed parameter sensitivity, not probability of feasibility or calibrated uncertainty coverage.'}
        return central
