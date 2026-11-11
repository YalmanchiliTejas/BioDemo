"""Deterministic characterization algebra; no organism kinetics or manufactured data."""
from dataclasses import dataclass
from pathlib import Path
import hashlib
import itertools
import math
from .schemas import Assumptions
from ..ids import content_hash

VERSION = 'fermentation-characterization-2'
# Power exponents of kLa reported for coalescing (0.4) and non-coalescing (0.7) liquids in stirred tanks
# (van 't Riet 1979). Used only to bound the sensitivity range; never substituted for the source fit.
LITERATURE_POWER_EXPONENTS = (.4, .7)
GAS_EXPONENT_RANGE = (0., .8)
GEOMETRY_MULTIPLIERS = (.5, 2.)
# Screening thresholds for the self-checks below. Declared, not validated acceptance criteria.
SOURCE_POWER_TOLERANCE = .10
GAS_BASIS_TOLERANCE = .25
SCALE_RATIO_LIMIT = 10.
LIMITS = ('Published summaries are not raw trajectories.', 'Scenario feasibility is conditional; rated receiving equipment limits require verification.',
          'No validated fermentation yield or viability model; no production dispatch.')

def fit_source(p):
    lo, hi = p['calibration']
    alpha = math.log(hi['kla_h_inv']/lo['kla_h_inv']) / math.log(hi['aerated_power_density_kw_m3']/lo['aerated_power_density_kw_m3'])
    return {'power_exponent': alpha, 'agitation_exponent': math.log(hi['kla_h_inv']/lo['kla_h_inv'])/math.log(hi['agitation_rpm']/lo['agitation_rpm']),
            'calibration_ids': [lo['id'], hi['id']], 'residual_degrees_of_freedom': 0,
            'gas_exponent_identified': False, 'source_kla_h_inv':lo['kla_h_inv'], 'source_power_w_m3':lo['aerated_power_density_kw_m3']*1000,
            'reported_power_speed_exponent': math.log(hi['aerated_power_density_kw_m3']/lo['aerated_power_density_kw_m3'])/math.log(hi['agitation_rpm']/lo['agitation_rpm']),
            'classification':'fitted_parameter_from_two_rounded_source_summaries'}

def check(identifier, status, observed, limit, message):
    # status: ok | attention | blocking. Blocking means the result is not a basis for a setting until resolved.
    return {'id':identifier,'status':status,'observed':observed,'limit':limit,'message':message}

def worst(checks):
    order=('ok','attention','blocking')
    return max((c['status'] for c in checks), key=order.index, default='ok')

def gas_velocity_ratio(a, b, source_vvm, vvm):
    """Superficial gas velocity ratio receiver/source, and how it was obtained.

    kLa correlations are written in superficial gas velocity, which at equal vvm rises with liquid height.
    With both tank diameters it is exact; otherwise geometric similarity (velocity ~ vvm x V^(1/3)) is an
    explicit assumption, used only as an alternative hypothesis."""
    da, db = a.get('tank_diameter_m'), b.get('tank_diameter_m')
    if da and db:
        return (vvm*b['working_volume_l']/db**2) / (source_vvm*a['working_volume_l']/da**2), 'measured_tank_diameters'
    return vvm/source_vvm * (b['working_volume_l']/a['working_volume_l'])**(1/3), 'assumed_geometric_similarity'

def transfer_point(p, vessel_l, rpm, vvm, gas_exponent=.5, *, kla_model=None):
    a = p['equipment'][0]
    b = next(e for e in p['equipment'] if e['working_volume_l'] == vessel_l)
    f = fit_source(p); row = p['calibration'][0]
    # Constant turbulent power-number and gassing-factor hypothesis. Different blade height and sparger challenge it.
    ratio = b['submerged_impellers']/a['submerged_impellers'] * (b['impeller_diameter_mm']/a['impeller_diameter_mm'])**5 * a['working_volume_l']/b['working_volume_l']
    pd = f['source_power_w_m3'] * ratio * (rpm/row['agitation_rpm'])**3
    source_vvm = row['airflow_l_min']/row['working_volume_l']
    flow_ratio = vvm / source_vvm
    velocity_ratio, velocity_basis = gas_velocity_ratio(a, b, source_vvm, vvm)
    # With measured tank diameters the gas term uses superficial velocity; without them the nominal keeps the
    # declared vvm form and the velocity form is carried as an alternative hypothesis.
    nominal_gas = velocity_ratio if velocity_basis == 'measured_tank_diameters' else flow_ratio
    power_ratio = pd/f['source_power_w_m3']
    factor = 1. if kla_model is None else float(kla_model(pd, vvm, b))
    if not math.isfinite(factor) or not .25 <= factor <= 4.:
        raise ValueError("learned kLa multiplier must remain in [.25, 4]")
    base = f['source_kla_h_inv'] * factor
    kla = base * power_ratio**f['power_exponent'] * nominal_gas**gas_exponent
    alternative = base * power_ratio**f['power_exponent'] * velocity_ratio**gas_exponent
    # Sensitivity bounds, not statistical prediction intervals. They span every declared unknown: the gas
    # exponent, the gas-flow basis, the receiver geometry multiplier and the power exponent (zero-residual
    # two-point fit versus the literature range).
    exponents = sorted({f['power_exponent'], *LITERATURE_POWER_EXPONENTS})
    bounds = [base * power_ratio**alpha * gas**beta * geometry
              for alpha, gas, beta, geometry in itertools.product(exponents, sorted({flow_ratio, velocity_ratio}), GAS_EXPONENT_RANGE, GEOMETRY_MULTIPLIERS)]
    if not all(math.isfinite(x) and x > 0 for x in (pd, kla, alternative, *bounds)):
        raise ValueError('transfer point produced a non-finite or non-positive value')
    return {'receiver_l':vessel_l,'rpm':rpm,'airflow_l_min':vvm*vessel_l,'vvm':vvm,'power_w_m3':pd,'hydrodynamic_power_w':pd*vessel_l/1000,
            'tip_speed_m_s':math.pi*b['impeller_diameter_mm']/1000*rpm/60,'predicted_kla_h_inv':kla,
            'gas_velocity_basis_kla_h_inv':alternative,'gas_velocity_basis':velocity_basis,
            'gas_basis_divergence':alternative/kla-1,
            'sensitivity_low_h_inv':min(bounds),'sensitivity_high_h_inv':max(bounds),
            'sensitivity_label':'Assumed gas exponent 0–0.8, gas term in vvm or superficial velocity, receiver geometry multiplier 0.5–2 and power exponent from the source fit to 0.7; not calibrated confidence bounds'}

def self_checks(p, fit, selected, rows):
    """Run on every result from calibration-side data only: what this calculation cannot support."""
    lo, hi = p['calibration']; source = p['equipment'][0]
    predicted_hi = fit['source_power_w_m3'] * (hi['agitation_rpm']/lo['agitation_rpm'])**3
    power_error = predicted_hi/(hi['aerated_power_density_kw_m3']*1000) - 1
    range_low, range_high = sorted((lo['aerated_power_density_kw_m3']*1000, hi['aerated_power_density_kw_m3']*1000))
    scale = selected['receiver_l']/source['working_volume_l']
    local = [r for r in rows if r['receiver_l'] == selected['receiver_l']]
    robust = sum(r['robust_to_declared_sensitivity'] for r in local)
    in_range = range_low <= selected['power_w_m3'] <= range_high
    literature = min(LITERATURE_POWER_EXPONENTS) <= fit['power_exponent'] <= max(LITERATURE_POWER_EXPONENTS)
    divergence = abs(selected['gas_basis_divergence'])
    return [
        check('source_power_law', 'ok' if abs(power_error) <= SOURCE_POWER_TOLERANCE else 'attention', power_error, SOURCE_POWER_TOLERANCE,
              f"Speed-cubed power scaling reproduces the second source point within {power_error:+.0%}; the reported power follows speed to the {fit['reported_power_speed_exponent']:.2f}."),
        check('calibration_degrees_of_freedom', 'attention' if fit['residual_degrees_of_freedom'] == 0 else 'ok', fit['residual_degrees_of_freedom'], 1,
              'The power exponent comes from two points with nothing left over to test it.'),
        check('power_exponent_plausibility', 'ok' if literature else 'attention', fit['power_exponent'], list(LITERATURE_POWER_EXPONENTS),
              'Fitted power exponent compared with the 0.4–0.7 range reported for stirred tanks.'),
        check('gas_exponent_identified', 'ok' if fit['gas_exponent_identified'] else 'attention', fit['gas_exponent_identified'], True,
              'Both source points share one airflow, so the gas exponent is an assumption.'),
        check('power_within_calibrated_range', 'ok' if in_range else 'attention', selected['power_w_m3'], [range_low, range_high],
              'Selected power density compared with the range the source fit covers.'),
        check('scale_extrapolation', 'blocking' if scale > SCALE_RATIO_LIMIT and fit['residual_degrees_of_freedom'] == 0 else 'ok', scale, SCALE_RATIO_LIMIT,
              f"Receiver is {scale:g} times the source volume; an untested two-point fit is not carried further than {SCALE_RATIO_LIMIT:g} times."),
        check('gas_basis_agreement', 'ok' if divergence <= GAS_BASIS_TOLERANCE else 'blocking', selected['gas_basis_divergence'], GAS_BASIS_TOLERANCE,
              f"Writing the gas term in superficial velocity ({selected['gas_velocity_basis']}) changes predicted kLa by {selected['gas_basis_divergence']:+.0%}."),
        check('robust_scenarios', 'ok' if robust else 'blocking', robust, 1,
              f"{robust} of {len(local)} screened settings for this receiver meet the target across the declared sensitivity range."),
    ]

def sulfolobus(config, *, kla_model=None):
    p, s = config['project'], Assumptions.model_validate(config.get('assumptions', {}))
    f=fit_source(p); candidates=[]; recommendations=[]
    for vessel, speeds in [(20,range(150,501,25)), (200,range(60,241,15))]:
        local=[]
        for n, vvm in itertools.product(speeds,[.15,.25,.35]):
            row=transfer_point(p,vessel,n,vvm,s.gas_exponent,kla_model=kla_model)
            row['meets_nominal_kla_target']=row['predicted_kla_h_inv'] >= p['reference_kla_h_inv']
            row['within_assumed_power_screen']=row['power_w_m3'] <= s.power_screen_w_m3
            row['robust_to_declared_sensitivity']=row['sensitivity_low_h_inv'] >= p['reference_kla_h_inv']
            row['margin_over_target']=row['predicted_kla_h_inv']/p['reference_kla_h_inv']-1
            row['meets_target_with_margin']=row['margin_over_target'] >= s.kla_target_margin
            row['meets_margin_on_both_gas_bases']=min(row['predicted_kla_h_inv'],row['gas_velocity_basis_kla_h_inv'])/p['reference_kla_h_inv']-1 >= s.kla_target_margin
            row['status']='conditional_screen_pass_requires_characterization' if row['meets_nominal_kla_target'] and row['within_assumed_power_screen'] else 'screen_reject'
            candidates.append(row)
            if row['status'].startswith('conditional'): local.append(row)
        # Prefer a setting that holds up over one that only just passes: the strongest non-empty tier wins,
        # and lowest power is the tie-break inside it.
        tiers=[('meets_target_across_declared_sensitivity',[r for r in local if r['robust_to_declared_sensitivity']]),
               ('meets_margin_on_both_gas_bases',[r for r in local if r['meets_margin_on_both_gas_bases']]),
               ('meets_margin_on_nominal_only',[r for r in local if r['meets_target_with_margin']]),
               ('meets_nominal_target_without_margin',local)]
        basis,chosen=next(((name,group) for name,group in tiers if group),('no_setting_passed_the_screen',[]))
        recommendations.append({'receiver_l':vessel,'candidate':min(chosen,key=lambda x:(x['hydrodynamic_power_w'],x['airflow_l_min'])) if chosen else None,
                                'selection_basis':basis,'target_margin_required':s.kla_target_margin,
                                'settings_meeting_target_across_sensitivity':sum(r['robust_to_declared_sensitivity'] for r in local),
                                'approval_status':'engineering_review_required','rated_equipment_feasibility':'unknown'})
    if s.selected_receiver_l not in (20,200): raise ValueError('receiver must be20L or200L')
    selected=transfer_point(p,s.selected_receiver_l,s.rpm,s.airflow_vvm,s.gas_exponent,kla_model=kla_model)
    checks=self_checks(p,f,selected,candidates)
    source_row=p['calibration'][0]; source_vvm=source_row['airflow_l_min']/source_row['working_volume_l']
    return {'case_id':p['id'],'calibration':f,'selected_scenario':selected,'scenarios':candidates,'recommendations':recommendations,
            'self_checks':checks,'self_check_status':worst(checks),
            'selection_criterion':'Among declared grid points meeting nominal kLa and the assumed power screen: settings that meet the target across the declared sensitivity range first, then settings with the declared margin on both gas-flow bases, then on the nominal basis, then bare passes; lowest hydrodynamic power within the chosen group. Air compression is not characterized and rated limits remain unknown.',
            'grid_definition':{'20L_rpm':[150,500,25],'200L_rpm':[60,240,15],'vvm':[.15,.25,.35],'classification':'scenario_search_bounds_not_certified_equipment_limits'},
            'copy_source_recipe':[transfer_point(p,v,source_row['agitation_rpm'],source_vvm,s.gas_exponent,kla_model=kla_model) for v in (20,200)],
            'copy_source_recipe_basis':'Source agitation speed and source vvm applied unchanged at each receiver.',
            'rationale':'Copying rpm changes power density through impeller count, D^5 and volume. Holding vvm constant raises superficial gas velocity with scale. Constant turbulent power number and vvm kLa scaling are challenged hypotheses, not established receiver correlations.',
            'equations':['P/V proportional to n_impellers × N^3 × D^5 / V at equal density, power number and gassing factor',
                         'kLa/kLa0 = ((P/V)/(P/V)0)^alpha × (gas/gas0)^beta × receiver_geometry_factor; gas is vvm, or superficial velocity where tank diameters are known',
                         'OTR = kLa × (Cstar - C); OUR must not exceed OTR'],
            'oxygen_capacity':None,'oxygen_capacity_reason':'Cstar, absolute DO and OUR are not tabulated; no absolute culture oxygen-feasibility claim.',
            'missing_inputs':p['missing'],'warnings':p['limitations']+list(LIMITS),'biology_prediction':None}

def compression_kw(q, gauge, ambient, eta, inlet_temperature_k=303.15):
    # Nm3 is explicitly 273.15 K / 101.325 kPa, unlike unspecified article flow references.
    # nRT_in ln(Pout/Pin)/eta; isothermal ideal-gas estimate, not measured energy.
    return 101325*q/3600*inlet_temperature_k/273.15*math.log((ambient+gauge)/ambient)/eta/1000

PLACEHOLDER_INPUTS = ('kla_h_inv', 'our_mg_l_h', 'dissolved_oxygen_mg_l', 'air_saturation_mg_l', 'broth_solubility_factor')
BASELINE_GAUGE_KPA = 50
PRESSURE_SCREEN_KPA = (50, 150)
DELIVERY_MATCH_TOLERANCE = .05

def oxygen_scenario(a, label, gauge, oxygen_nm3_h):
    """One aeration strategy at a gauge pressure. All oxygen-transfer inputs are declared assumptions."""
    y_air=.2095
    y=(a.air_nm3_h*y_air+oxygen_nm3_h)/(a.air_nm3_h+oxygen_nm3_h)
    absolute=a.ambient_kpa+gauge
    # The declared kLa belongs to air alone at the baseline pressure. At a fixed normal flow the actual gas
    # volume falls as absolute pressure rises, and kLa follows actual gas velocity to the gas exponent.
    actual_flow_ratio=(a.air_nm3_h+oxygen_nm3_h)/a.air_nm3_h*(a.ambient_kpa+BASELINE_GAUGE_KPA)/absolute
    kla=a.kla_h_inv*actual_flow_ratio**a.gas_exponent
    cstar=a.air_saturation_mg_l*a.broth_solubility_factor*absolute/a.ambient_kpa*y/y_air
    otr=kla*(cstar-a.dissolved_oxygen_mg_l)
    kw=compression_kw(a.air_nm3_h,gauge,a.ambient_kpa,a.compressor_efficiency,a.compressor_inlet_temperature_k)
    return {'label':label,'pressure_gauge_kpa':gauge,'pressure_absolute_kpa':absolute,'inlet_oxygen_mole_fraction':y,
            'kla_h_inv':kla,'actual_gas_flow_ratio_to_baseline':actual_flow_ratio,
            'cstar_mg_l':cstar,'otr_mg_l_h':otr,'our_margin_mg_l_h':otr-a.our_mg_l_h,'compressor_kw':kw,
            'oxygen_nm3_h':oxygen_nm3_h,'partial_cost_usd_h':kw*a.electricity_usd_kwh+oxygen_nm3_h*a.oxygen_usd_nm3,
            'classification':'assumed_characterization_and_prices'}

def matched_delivery(a, target_otr):
    """Air-only pressure that delivers the same oxygen as the supplemental-oxygen case, so costs compare like for like."""
    low, high = PRESSURE_SCREEN_KPA
    at=lambda gauge: oxygen_scenario(a,'Pressurized air at matched oxygen delivery',gauge,0.)
    if at(high)['otr_mg_l_h'] < target_otr:
        return {'attainable':False,'reason':f'Air alone does not reach the supplemental-oxygen transfer rate within {high} kPa gauge under the declared assumptions.','scenario':None}
    if at(low)['otr_mg_l_h'] >= target_otr:
        return {'attainable':True,'reason':'Air alone at the baseline pressure already delivers at least as much.','scenario':at(low)}
    for _ in range(60):  # transfer rate rises monotonically with pressure for gas exponents up to 1
        middle=(low+high)/2
        if at(middle)['otr_mg_l_h'] < target_otr: low=middle
        else: high=middle
    return {'attainable':True,'reason':None,'scenario':at(high)}

def pichia(config):
    p, a = config['project'], Assumptions.model_validate(config.get('assumptions', {}))
    pressure_ratio=(a.ambient_kpa+a.pressure_gauge_kpa)/(a.ambient_kpa+BASELINE_GAUGE_KPA)
    rows=[oxygen_scenario(a,'Supplemental oxygen',BASELINE_GAUGE_KPA,a.oxygen_nm3_h),
          oxygen_scenario(a,'Pressurized air',a.pressure_gauge_kpa,0.)]
    delta_hour=rows[0]['partial_cost_usd_h']-rows[1]['partial_cost_usd_h']
    extra_feed_cost=a.extra_methanol_l*a.methanol_usd_l if a.extra_methanol_l is not None else None
    break_even=(rows[1]['compressor_kw']-rows[0]['compressor_kw'])*a.electricity_usd_kwh/a.oxygen_nm3_h if a.oxygen_nm3_h else None
    matched=matched_delivery(a,rows[0]['otr_mg_l_h'])
    if matched['scenario']:
        matched['oxygen_delivery_savings_usd_h']=rows[0]['partial_cost_usd_h']-matched['scenario']['partial_cost_usd_h']
        matched['oxygen_delivery_savings_usd_basis']=matched['oxygen_delivery_savings_usd_h']*a.comparison_hours
    defaults=Assumptions()
    placeholders=[name for name in PLACEHOLDER_INPUTS if getattr(a,name)==getattr(defaults,name)]
    delivery_gap=rows[1]['otr_mg_l_h']/rows[0]['otr_mg_l_h']-1 if rows[0]['otr_mg_l_h'] else float('inf')
    checks=[
        check('oxygen_inputs_declared','blocking' if placeholders else 'ok',placeholders,[],
              'Oxygen-transfer inputs still at their placeholder values; feasibility and cost follow from placeholders, not from this process.' if placeholders
              else 'Oxygen-transfer inputs were all declared for this assessment.'),
        check('equal_oxygen_delivery','ok' if abs(delivery_gap)<=DELIVERY_MATCH_TOLERANCE else 'attention',delivery_gap,DELIVERY_MATCH_TOLERANCE,
              f"The two strategies as entered deliver oxygen {delivery_gap:+.0%} apart; compare cost at matched delivery."),
        check('matched_delivery_attainable','ok' if matched['attainable'] else 'blocking',matched['attainable'],True,
              matched['reason'] or 'An air-only pressure matching the supplemental-oxygen transfer rate exists inside the screened range.'),
        check('net_oxygen_absorption','ok' if min(r['otr_mg_l_h'] for r in rows)>0 else 'blocking',min(r['otr_mg_l_h'] for r in rows),0,
              'Dissolved oxygen compared with saturation: a negative transfer rate means oxygen leaves the liquid.'),
        check('demand_covered','ok' if rows[1]['our_margin_mg_l_h']>=0 else 'blocking',rows[1]['our_margin_mg_l_h'],0,
              'Pressurized-air transfer rate compared with the declared oxygen uptake rate.'),
    ]
    source=p['calibration'][0]['outcomes']
    return {'case_id':p['id'],'scenarios':rows,'pressure_saturation_ratio_air_only':pressure_ratio,
            'pressure_curve':[{'pressure_gauge_kpa':x,'saturation_ratio':(a.ambient_kpa+x)/(a.ambient_kpa+BASELINE_GAUGE_KPA)} for x in range(50,151,10)],
            'matched_oxygen_delivery':matched,'self_checks':checks,'self_check_status':worst(checks),
            'economics':{'classification':'modeled_partial_operating_cost_not_measured_savings','common_basis_hours':a.comparison_hours,
                         'oxygen_delivery_savings_usd_h':delta_hour,'oxygen_delivery_savings_usd_basis':delta_hour*a.comparison_hours,
                         'extra_methanol_cost_usd':extra_feed_cost,'net_after_extra_feed_usd':delta_hour*a.comparison_hours-extra_feed_cost if extra_feed_cost is not None else None,
                         'break_even_oxygen_usd_nm3':break_even,'excluded':['cooling','agitation electricity','occupancy','capital','downstream recovery','methanol unless specified'],
                         'flow_basis':'Nm3 at273.15K and101.325kPa; compressor inlet temperature separately declared. Paper flow reference conditions are unknown.'},
            'empirical_baseline':{'enzyme_activity_u_l':source['volumetric_enzyme_activity']['value'],'enzyme_production_mg_l':source['volumetric_enzyme_production']['value'],
                                  'classification':'constant10L endpoint empirical baseline; not pressure kinetics'},
            'recommendation':'Characterize kLa, OUR and DO at proposed pressure and verify vessel/filter/relief ratings. Air-only may reduce oxygen-delivery cost under the declared assumptions; replicated feed/productivity outcomes are required before transfer.',
            'conditional_oxygen_feasible':rows[1]['our_margin_mg_l_h']>=0,
            'oxygen_feasibility_basis':'placeholder_inputs' if placeholders else 'declared_inputs',
            'equipment_pressure_rating_verified':False,
            'equations':['P_absolute = P_gauge + P_ambient','Cstar proportional to absolute O2 partial pressure at constant temperature and broth',
                         'kLa = kLa_declared × (actual gas flow / baseline actual gas flow)^beta; actual flow falls with absolute pressure at fixed normal flow',
                         'OTR = kLa × (Cstar - C)','W_isothermal = P_inlet × Q_inlet × ln(P_out/P_in) / efficiency'],
            'warnings':p['limitations']+list(LIMITS)+['Solubility, broth correction, kLa, OUR, DO, gas usage and prices are user assumptions, not Liu measurements.','Dry ideal gas and uniform DO; kLa follows actual gas flow by the assumed gas exponent. No exhaust oxygen depletion, hydrostatic or dissolved carbon dioxide correction.'],
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
