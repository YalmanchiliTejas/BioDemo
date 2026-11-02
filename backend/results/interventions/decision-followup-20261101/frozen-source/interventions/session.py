"""Sequential host boundary: available evidence → proposal → simulated outcome.

Predictor is injected from a frozen source-calibrated model implementation; it
receives a public evidence packet only. Never fit or select on hidden outcomes.
"""
from copy import deepcopy
from .pensim import simulate,outcomes,observations,ACTIONS,stop_classification


class InterventionSession:
    def __init__(self,paths,hidden,source_observations,*,predictor=None):
        self.paths=paths;self.hidden=deepcopy(hidden);self.source=deepcopy(source_observations)
        self.clock=hidden.get('decision_h',52.);self.predictor=predictor
        self.events=[];self.committed=False;self.measurements=0
        self.reference=simulate(paths,**self.hidden,action='keep')
    def packet(self):
        return {'task':'investigate_and_recommend_intervention','decision_time_h':self.clock,
            'source_observations':deepcopy(self.source),
            'receiving_observations':observations(self.reference,self.clock,noise_seed=self.hidden['seed']+100000),
            'allowed_actions':deepcopy(ACTIONS),'minimum_do_mg_l':2.,
            'measurement_menu':{'extra_product_assay':{'turnaround_h':4.,'work_minutes':20.,'basis':'Explicit task assumption; off-cycle lab capacity is not established by the paper.'}},
            'scope':'Research simulation. A recommendation is not approval or physical equipment execution.'}
    def measure(self,name):
        if self.committed:raise ValueError('Recommendation already frozen')
        if name!='extra_product_assay' or self.measurements>=1:raise ValueError('Measurement outside frozen budget/menu')
        sample=self.clock;arrives=sample+4.
        row=next(r for r in self.reference['trace'] if abs(r['time_h']-sample)<1e-7)
        self.clock=arrives;self.measurements+=1
        result={'field':'P','time_h':sample,'available_at_h':arrives,'value':row['state']['P'],'unit':'g/L',
            'noise_policy':'Ideal extra assay assumption; routine observations have simulated noise.'}
        # The extra assay is appended to public evidence only after its arrival.
        self.source_extra=result;self.events.append({'kind':'measurement','result':deepcopy(result)})
        return self.public_packet()
    def public_packet(self):
        p=self.packet()
        if hasattr(self,'source_extra'):p['receiving_observations'].append(deepcopy(self.source_extra))
        return p
    def predict(self,action):
        if self.committed:raise ValueError('Recommendation already frozen')
        if action not in ACTIONS:raise ValueError('Action outside menu')
        if self.predictor is None:raise ValueError('No supplied model in this arm')
        result=self.predictor(self.public_packet(),action)
        self.events.append({'kind':'model_prediction','action_id':action,'time_h':self.clock,'result':deepcopy(result)})
        return result
    def recommend(self,action,*,rationale,uncertainty,evidence):
        if self.committed or action not in ACTIONS:raise ValueError('Invalid or duplicate recommendation')
        if not rationale or not uncertainty or not isinstance(evidence,list):raise ValueError('Reviewable explanation required')
        self.committed=True
        proposal={'action_id':action,'decision_time_h':self.clock,'rationale':rationale,'uncertainty':uncertainty,
            'evidence':deepcopy(evidence),'approval_status':'not_approved_for_manufacturing','execution':'virtual_replay_only'}
        self.events.append({'kind':'recommendation','proposal':proposal})
        # Hidden outcome becomes available only AFTER the recommendation is fixed.
        config=dict(self.hidden,decision_h=self.clock)
        actual=outcomes(simulate(self.paths,**config,action=action))
        self.events.append({'kind':'simulated_outcome','outcome':deepcopy(actual)})
        return {'proposal':proposal,'outcome':actual,'measurement_requests':self.measurements,
            'assumed_measurement_work_minutes':20.*self.measurements,'physical_decision_delay_h':self.clock-self.hidden.get('decision_h',52.),
            'events':deepcopy(self.events),'observed_human_time_saved':None}
