"""Retrospective Sulfolobus correction case, summary measurements only.

No invented trajectories, assays, physical execution or causal agent-uplift score.
The500rpm observed outcome is kept outside the agent packet until commitment.
"""
from pathlib import Path
from copy import deepcopy
import argparse,json
from src.lifesci.envfile import load_env_file
from src.lifesci.fermentation.research_route import hosted_research_profile
from benchmarks.external_simulators.experiment import dump,sha
from . import run_agents

SYSTEM='''Review this published-summary oxygen-transfer problem and propose a reviewable next action. Source water characterization and observed culture oxygen limitation are supplied; the published corrective outcome is withheld until your recommendation is frozen. Only packet data and host tools may be used. This is retrospective summary reconstruction; do not claim a new lab experiment, raw receiving trajectory, observed product mass, or physical equipment execution. Water kLa is not validated broth kLa. Equipment ratings and OUR are missing. You may recommend a conditional adjustment, unchanged operation, characterization, or stopping, with rationale and explicit limits. No additional assays are available in this public record: request_measurement cannot supply missing author-held data. If a model tool is present, its power-law sensitivity exponents are assumed, not fitted from the withheld correction. Compare useful options but do not claim a unique validated setting. submit_decision freezes the recommendation; predictions must be empty. Evidence references should use the packet's section/table identifiers.'''
DOI='https://doi.org/10.3389/fbioe.2023.1160012'
ACTIONS={'keep_355rpm':{'rpm':355},'conditional_500rpm':{'rpm':500},'characterize_before_action':{'operation':'request broth characterization/equipment review'},'stop':{'operation':'stop pending review'}}


class SummarySession:
    def __init__(self,model=False):self.model=model;self.committed=False;self.events=[]
    def public_packet(self):
        return {'task':'published_summary_corrective_case','decision_time_h':0.,'source_clock':'Summary evidence, no raw experimental time series available.',
            'allowed_actions':ACTIONS,'measurement_menu':{},'evidence':[
                {'source':'Rastadter2023 Table2','classification':'water_characterization_measurement','vessel_l':2,'temperature_c':75,'sparger':'ring','rpm':355,'air_l_min':.51,'kla_per_h':32.6},
                {'source':'Rastadter2023 Table2','classification':'water_characterization_measurement','vessel_l':2,'temperature_c':75,'sparger':'micro','rpm':355,'air_l_min':.51,'kla_per_h':38.8},
                {'source':'Rastadter2023 section3.1','classification':'published_cultivation_observation','sparger':'ring','rpm':355,'observation':'DO below20%, oxygen supplementation required; no raw DO curve in public data.'}],
            'operating_inputs':{'air_l_min':.51,'author_calculated_power_kw_m3':{'355rpm':.25,'500rpm':.63}},
            'missing':['rated maximum rpm/torque','broth kLa response','OUR','raw DO and viability trajectories','matched product mass'],
            'scope':'One retrospective source-summary case, no independent agent-effect or production-improvement claim.'}
    def measure(self,name):raise ValueError('No additional public assay or raw trajectory available; do not fabricate results')
    def predict(self,action):
        if self.committed or not self.model:raise ValueError('Model unavailable')
        if action not in ACTIONS:raise ValueError('Unknown action')
        if action in ['characterize_before_action','stop']:
            value={'classification':'no_process_prediction','action_id':action}
        else:
            ratio=1. if action=='keep_355rpm' else .63/.25
            values=[32.6*ratio**a for a in [.2,.4,.6]]
            value={'classification':'conditional_water_kLa_sensitivity_not_observation','action_id':action,
                'kla_per_h_range':[min(values),max(values)],'assumed_power_exponents':[.2,.4,.6],
                'equation':'kLa=source_kLa*(planned_author_calculated_PgV/source_PgV)^alpha',
                'limits':'Single ring-source characterization cannot identifyalpha. These exponents are sensitivity assumptions, not attributed to this paper. No broth DO, viability, product mass or safety outcome predicted.'}
        self.events.append({'kind':'model_prediction','result':deepcopy(value)});return value
    def recommend(self,action,*,rationale,uncertainty,evidence):
        if self.committed or action not in ACTIONS:raise ValueError('Invalid/duplicate recommendation')
        self.committed=True
        proposal={'action_id':action,'rationale':rationale,'uncertainty':uncertainty,'evidence':evidence,'approval_status':'not_approved','execution':'none'}
        self.events.append({'kind':'reviewable_recommendation','proposal':proposal})
        outcome={'source':DOI,'locations':['Table2','section3.1'],'classification':'previously_published_summary_revealed_after_commitment',
            'reported_correction':{'ring_rpm':500,'air_l_min':.51,'water_kla_per_h':38.8,'oxygen_supplementation':'could be omitted','viability_change':'almost6percentage_points; summary phrase, not fabricated precise replicate data'},
            'product_mass':None,'raw_timecourse':None,'agent_action_physically_executed':False}
        self.events.append({'kind':'published_outcome_comparison','outcome':outcome})
        return {'proposal':proposal,'published_evidence':outcome,'events':deepcopy(self.events),
            'comparison':'Matches reported adjustment direction' if action=='conditional_500rpm' else 'Alternative/deferral; not scored as experimentally wrong from this one published correction.'}


def run(output):
    if output.exists():raise ValueError('Fresh physical replay output required')
    output.mkdir(parents=True);repo=Path(__file__).resolve().parents[3];load_env_file(repo/'backend/.env.local');profile=hosted_research_profile()
    if profile is None:raise ValueError('No research model configured')
    dump(output/'protocol.json',{'scope':'One retrospective published-summary case; not blinded independent validation. Prior exposure/pretraining memorization cannot be excluded.','doi':DOI,'source_manifest_sha256':sha(repo/'docs/research/fermentation/sulfolobus/source-manifest.json'),'model':profile.provider+'/'+profile.model,'exponents':'assumed0.2,0.4,0.6; no correction-target fit','outcome_policy':'Reveal published result only after recommendation; do not count recommendation as executed experiment.'})
    run_agents.SYSTEM=SYSTEM # This process only; no frozen PenSim source file changes.
    results={}
    for arm in ['A','B']:
        results[arm]=run_agents.attempt(SummarySession(model=arm=='B'),arm,profile.provider+'/'+profile.model,output/arm)
        print(json.dumps({'arm':arm,'status':results[arm]['status']}),flush=True)
    dump(output/'results.json',{'classification':'retrospective_physical_summary_replay_not_new_experiment','records':results})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.output.resolve())
