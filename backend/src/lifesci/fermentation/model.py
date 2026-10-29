"""Deterministic characterization algebra; no organism kinetics or manufactured data."""
from dataclasses import dataclass
from pathlib import Path
import hashlib
import itertools
import math
from .schemas import Assumptions
from ..ids import content_hash

VERSION = 'fermentation-characterization-1'
LIMITS = ('Published summaries are not raw trajectories.', 'Scenario feasibility is conditional; rated receiving equipment limits require verification.',
          'No validated fermentation yield or viability model; no production dispatch.')

def fit_source(p):
    lo, hi = p['calibration']
    alpha = math.log(hi['kla_h_inv']/lo['kla_h_inv']) / math.log(hi['aerated_power_density_kw_m3']/lo['aerated_power_density_kw_m3'])
    return {'power_exponent': alpha, 'agitation_exponent': math.log(hi['kla_h_inv']/lo['kla_h_inv'])/math.log(hi['agitation_rpm']/lo['agitation_rpm']),
            'calibration_ids': [lo['id'], hi['id']], 'residual_degrees_of_freedom': 0,
            'gas_exponent_identified': False, 'source_kla_h_inv':lo['kla_h_inv'], 'source_power_w_m3':lo['aerated_power_density_kw_m3']*1000,
            'classification':'fitted_parameter_from_two_rounded_source_summaries'}

def transfer_point(p, vessel_l, rpm, vvm, gas_exponent=.5):
    a = p['equipment'][0]
    b = next(e for e in p['equipment'] if e['working_volume_l'] == vessel_l)
    f = fit_source(p); row = p['calibration'][0]
    # Constant turbulent power-number and gassing-factor hypothesis. Different blade height and sparger challenge it.
    ratio = b['submerged_impellers']/a['submerged_impellers'] * (b['impeller_diameter_mm']/a['impeller_diameter_mm'])**5 * a['working_volume_l']/b['working_volume_l']
    pd = f['source_power_w_m3'] * ratio * (rpm/row['agitation_rpm'])**3
    flow_ratio = vvm / (row['airflow_l_min']/row['working_volume_l'])
    kla = f['source_kla_h_inv'] * (pd/f['source_power_w_m3'])**f['power_exponent'] * flow_ratio**gas_exponent
    # Sensitivity bounds, not statistical prediction intervals. Receiver geometry multiplier is uncalibrated.
    bounds = [f['source_kla_h_inv']*(pd/f['source_power_w_m3'])**f['power_exponent']*flow_ratio**beta*geometry
              for beta, geometry in itertools.product([0., .8], [.5, 2.])]
    return {'receiver_l':vessel_l,'rpm':rpm,'airflow_l_min':vvm*vessel_l,'vvm':vvm,'power_w_m3':pd,'hydrodynamic_power_w':pd*vessel_l/1000,
            'tip_speed_m_s':math.pi*b['impeller_diameter_mm']/1000*rpm/60,'predicted_kla_h_inv':kla,
            'sensitivity_low_h_inv':min(bounds),'sensitivity_high_h_inv':max(bounds),'sensitivity_label':'Assumed gas exponent0–0.8 and receiver geometry multiplier0.5–2; not calibrated confidence bounds'}

def sulfolobus(config):
    p, s = config['project'], Assumptions.model_validate(config.get('assumptions', {}))
    f=fit_source(p); candidates=[]; recommendations=[]
    for vessel, speeds in [(20,range(150,501,25)), (200,range(60,241,15))]:
        local=[]
        for n, vvm in itertools.product(speeds,[.15,.25,.35]):
            row=transfer_point(p,vessel,n,vvm,s.gas_exponent)
            row['meets_nominal_kla_target']=row['predicted_kla_h_inv'] >= p['reference_kla_h_inv']
            row['within_assumed_power_screen']=row['power_w_m3'] <= s.power_screen_w_m3
            row['robust_to_declared_sensitivity']=row['sensitivity_low_h_inv'] >= p['reference_kla_h_inv']
            row['status']='conditional_screen_pass_requires_characterization' if row['meets_nominal_kla_target'] and row['within_assumed_power_screen'] else 'screen_reject'
            candidates.append(row)
            if row['status'].startswith('conditional'): local.append(row)
        recommendations.append({'receiver_l':vessel,'candidate':min(local,key=lambda x:(x['hydrodynamic_power_w'],x['airflow_l_min'])) if local else None,
                                'approval_status':'engineering_review_required','rated_equipment_feasibility':'unknown'})
    if s.selected_receiver_l not in (20,200): raise ValueError('receiver must be20L or200L')
    selected=transfer_point(p,s.selected_receiver_l,s.rpm,s.airflow_vvm,s.gas_exponent)
    return {'case_id':p['id'],'calibration':f,'selected_scenario':selected,'scenarios':candidates,'recommendations':recommendations,
            'selection_criterion':'Lowest hydrodynamic power among declared grid points meeting nominal kLa and the assumed power screen; air compression is not characterized and rated limits remain unknown.',
            'grid_definition':{'20L_rpm':[150,500,25],'200L_rpm':[60,240,15],'vvm':[.15,.25,.35],'classification':'scenario_search_bounds_not_certified_equipment_limits'},
            'copy_source_recipe':[transfer_point(p,v,355,.51/2,s.gas_exponent) for v in (20,200)],
            'rationale':'Copying rpm changes power density through impeller count, D^5 and volume. Copying L/min changes specific aeration. Constant turbulent power number and vvm kLa scaling are challenged hypotheses, not established receiver correlations.',
            'equations':['P/V proportional to n_impellers × N^3 × D^5 / V at equal density, power number and gassing factor',
                         'kLa/kLa0 = ((P/V)/(P/V)0)^alpha × (vvm/vvm0)^beta × receiver_geometry_factor',
                         'OTR = kLa × (Cstar - C); OUR must not exceed OTR'],
            'oxygen_capacity':None,'oxygen_capacity_reason':'Cstar, absolute DO and OUR are not tabulated; no absolute culture oxygen-feasibility claim.',
            'missing_inputs':p['missing'],'warnings':p['limitations']+list(LIMITS),'biology_prediction':None}

def compression_kw(q, gauge, ambient, eta, inlet_temperature_k=303.15):
    # Nm3 is explicitly 273.15 K / 101.325 kPa, unlike unspecified article flow references.
    # nRT_in ln(Pout/Pin)/eta; isothermal ideal-gas estimate, not measured energy.
    return 101325*q/3600*inlet_temperature_k/273.15*math.log((ambient+gauge)/ambient)/eta/1000

def pichia(config):
    p, a = config['project'], Assumptions.model_validate(config.get('assumptions', {}))
    y_air=.2095
    y_enriched=(a.air_nm3_h*y_air+a.oxygen_nm3_h)/(a.air_nm3_h+a.oxygen_nm3_h)
    pressure_ratio=(a.ambient_kpa+a.pressure_gauge_kpa)/(a.ambient_kpa+50)
    rows=[]
    for label, pg, y, o2 in [('Supplemental oxygen',50,y_enriched,a.oxygen_nm3_h),('Pressurized air',a.pressure_gauge_kpa,y_air,0.)]:
        cstar=a.air_saturation_mg_l*a.broth_solubility_factor*(a.ambient_kpa+pg)/a.ambient_kpa*y/y_air
        otr=a.kla_h_inv*(cstar-a.dissolved_oxygen_mg_l)
        kw=compression_kw(a.air_nm3_h,pg,a.ambient_kpa,a.compressor_efficiency,a.compressor_inlet_temperature_k)
        cost=kw*a.electricity_usd_kwh+o2*a.oxygen_usd_nm3
        rows.append({'label':label,'pressure_gauge_kpa':pg,'pressure_absolute_kpa':a.ambient_kpa+pg,'inlet_oxygen_mole_fraction':y,
                     'cstar_mg_l':cstar,'otr_mg_l_h':otr,'our_margin_mg_l_h':otr-a.our_mg_l_h,'compressor_kw':kw,
                     'oxygen_nm3_h':o2,'partial_cost_usd_h':cost,'classification':'assumed_characterization_and_prices'})
    delta_hour=rows[0]['partial_cost_usd_h']-rows[1]['partial_cost_usd_h']
    extra_feed_cost=a.extra_methanol_l*a.methanol_usd_l if a.extra_methanol_l is not None else None
    break_even=(rows[1]['compressor_kw']-rows[0]['compressor_kw'])*a.electricity_usd_kwh/a.oxygen_nm3_h if a.oxygen_nm3_h else None
    source=p['calibration'][0]['outcomes']
    return {'case_id':p['id'],'scenarios':rows,'pressure_saturation_ratio_air_only':pressure_ratio,
            'pressure_curve':[{'pressure_gauge_kpa':x,'saturation_ratio':(a.ambient_kpa+x)/(a.ambient_kpa+50)} for x in range(50,151,10)],
            'economics':{'classification':'modeled_partial_operating_cost_not_measured_savings','common_basis_hours':a.comparison_hours,
                         'oxygen_delivery_savings_usd_h':delta_hour,'oxygen_delivery_savings_usd_basis':delta_hour*a.comparison_hours,
                         'extra_methanol_cost_usd':extra_feed_cost,'net_after_extra_feed_usd':delta_hour*a.comparison_hours-extra_feed_cost if extra_feed_cost is not None else None,
                         'break_even_oxygen_usd_nm3':break_even,'excluded':['cooling','agitation electricity','occupancy','capital','downstream recovery','methanol unless specified'],
                         'flow_basis':'Nm3 at273.15K and101.325kPa; compressor inlet temperature separately declared. Paper flow reference conditions are unknown.'},
            'empirical_baseline':{'enzyme_activity_u_l':source['volumetric_enzyme_activity']['value'],'enzyme_production_mg_l':source['volumetric_enzyme_production']['value'],
                                  'classification':'constant10L endpoint empirical baseline; not pressure kinetics'},
            'recommendation':'Characterize kLa, OUR and DO at proposed pressure and verify vessel/filter/relief ratings. Air-only may reduce oxygen-delivery cost under the declared assumptions; replicated feed/productivity outcomes are required before transfer.',
            'conditional_oxygen_feasible':rows[1]['our_margin_mg_l_h']>=0,'equipment_pressure_rating_verified':False,
            'equations':['P_absolute = P_gauge + P_ambient','Cstar proportional to absolute O2 partial pressure at constant temperature and broth',
                         'OTR = kLa × (Cstar - C)','W_isothermal = P_inlet × Q_inlet × ln(P_out/P_in) / efficiency'],
            'warnings':p['limitations']+list(LIMITS)+['Solubility, broth correction, kLa, OUR, DO, gas usage and prices are user assumptions, not Liu measurements.','Dry ideal gas, uniform DO and constant kLa; no exhaust oxygen depletion or hydrostatic correction.'],
            'missing_inputs':p['missing'],'biology_prediction':None}

@dataclass(frozen=True)
class FermentationAdapter:
    id: str
    case_id: str
    run: object
    version: str=VERSION
    @property
    def digest(self):
        return hashlib.sha256(Path(__file__).read_bytes()+Path(__file__).with_name('schemas.py').read_bytes()).hexdigest()
    def describe(self):
        return {'id':self.id,'version':self.version,'implementation_digest':self.digest,'title':'Aerobic transfer characterization · '+self.case_id,
                'process_family':'aerobic_fermentation','qualification':'unqualified characterization / literature benchmark',
                'source':'10.3389/fbioe.2023.1160012' if self.case_id=='sulfolobus' else '10.1038/srep18439',
                'required_inputs':['project','assumptions'],'limitations':list(LIMITS),'supported_outputs':['oxygen_transfer','constraints','conditional_strategy'],'units':'explicitly suffixed keys'}
    def applicability(self,config):
        ok=config.get('project',{}).get('id')==self.case_id
        return {'applicable':ok,'missing_inputs':[] if ok else ['matching fermentation project'],'issues':[], 'note':'Characterization input sufficiency does not validate transfer.'}

def adapters():
    return {x.id:x for x in [FermentationAdapter('fermentation.oxygen_transfer','sulfolobus',sulfolobus),FermentationAdapter('fermentation.pressure_cost','pichia',pichia)]}

def calculate(public_project, assumptions=None):
    a=Assumptions.model_validate(assumptions or {})
    function=sulfolobus if public_project['id']=='sulfolobus' else pichia
    return function({'project':public_project,'assumptions':a.model_dump()})
