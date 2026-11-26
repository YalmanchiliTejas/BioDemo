"""Provider-disabled synthetic Quality acceptance API. Never reads inference credentials."""
from pathlib import Path
import os
import sys
import json
import hashlib
import argparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
# Empty inherited configuration before any application import.
for name in list(os.environ):
    if name not in {'PATH','HOME','TMPDIR','LANG','LC_ALL','LC_CTYPE','SYSTEMROOT'}:
        os.environ[name] = ''

parser = argparse.ArgumentParser()
parser.add_argument('--port', type=int, default=8158)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--acceptance-name')
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
os.environ.update(LIFESCI_AUTH_MODE='development', LIFESCI_DEV_PASSWORD='sievance-local',
    LIFESCI_CORS_ORIGINS='http://127.0.0.1:5198', LIFESCI_MULTI_TENANT='1',
    LIFESCI_DATABASE_URL='sqlite:///' + str(args.output.resolve() / 'records.sqlite'),
    LIFESCI_ENV_FILE='/dev/null', CMO_INGESTION_ROOT=str(args.output.resolve() / 'ingestion'),
    CMO_REPOSITORY_ROOT=str(args.output.resolve() / 'repository'), CMO_HOSTED_INFERENCE_APPROVED='0')
# Disable env-file restoration at its actual loaders before importing the app.
# No environment file is opened and no paid credential is parsed/admitted.
from src.lifesci import envfile
from src.manufacturing_data.cmo import settings as cmo_settings
envfile.load_env_file = lambda *a, **kw: []
cmo_settings.load_local_settings = lambda *a, **kw: None
from src.lifesci.container import Platform
from src.lifesci.store import RecordStore
from src.lifesci.api import create_app
from src.lifesci.devaccounts import ensure_seeded
from src.lifesci import devaccounts
from src.lifesci.organizations import OrganizationService

p = Platform(RecordStore(os.environ['LIFESCI_DATABASE_URL']), providers={})
assert p.store.backend == 'sqlite'
devaccounts.ACCOUNTS = (*devaccounts.ACCOUNTS, devaccounts.DevAccount('dev-adoption','adoption@sievance.local','Synthetic legacy-case contributor','msat','NF1'))
ensure_seeded(p, OrganizationService(p.store, p.identity, ''))
tenant, site = 'demo-northfield', 'NF1'
if not p.store.read().get(tenant,'role_assignment','dev-adoption:msat:NF2'):
    p.identity.assign_role(tenant,'dev-adoption','msat',site_id='NF2',by='synthetic-quality-launcher',reason='Scoped adoption regression')
ctx = p.identity.context_for(tenant, 'dev-msat')
config = dict(gas_exponent=0.5, pressure_gauge_kpa=50., ambient_kpa=100., air_nm3_h=100., oxygen_nm3_h=10.,
    compressor_efficiency=0.7, compressor_inlet_temperature_k=300., electricity_usd_kwh=0.1,
    oxygen_usd_nm3=0.2, air_saturation_mg_l=8., broth_solubility_factor=1., kla_h_inv=10.,
    dissolved_oxygen_mg_l=2., our_mg_l_h=40., kla_baseline_pressure_gauge_kpa=50.)
packet = {'disclosure':'Synthetic acceptance inputs; unqualified conditional calculation, not a plant diagnosis.',
    'untrusted_source_example':'<script>window.__sourceExecuted=true</script>',
    'scientific_models':[{'id':'synthetic-oxygen', 'model_id':'fermentation.pressure_cost',
        'config':{'assumptions':config, 'evidence_classification':'synthetic_assumption', 'source_refs':['synthetic characterization']},
        'assumptions':['Synthetic baseline characterization at 50 kPa gauge'], 'uncertainty':['No calibrated interval'],
        'observations':[{'observable':'scenarios.1.otr_mg_l_h','coordinate':0.,'value':95.,'unit':'mg/(L h)'}]}]}
out = p.evidence.ingest(ctx, source_system='synthetic-historian', source_record_id='oxygen-packet',
    content=json.dumps(packet).encode(), media_type='application/json', site_id=site,
    event_time='2026-11-15T12:00:00+00:00', metadata={'mapped':{'batch_id':'SYN-001','equipment_id':'SYN-V1'}})
ref = {'kind':'evidence','id':out['evidence_id'],'revision':out['revision'],'site_id':site}
prior = json.loads((args.output/'manifest.json').read_text()) if (args.output/'manifest.json').exists() else {}
if p.store.read().get(tenant,'deviation_signal',prior.get('signal_id','')):
    signal = p.signals.get(ctx,prior['signal_id'])
else:
    signal = p.signals.raise_signal(tenant, kind='spec_excursion', severity='action', site_id=site,
    subject={'kind':'batch','id':'SYN-001'}, rule='Synthetic oxygen excursion', rule_key='quality-browser',
    parameter='dissolved_oxygen', value=2., unit='mg/L', limit={'low':3.}, source={'system':'synthetic-historian','record_id':'oxygen-packet'},
    evidence_refs=[ref], associations={'batch_id':'SYN-001','equipment_id':'SYN-V1'},
    event_time='2026-11-15T12:00:00+00:00', observations=[{'value':v,'unit':'mg/L',
        'event_time':f'2026-11-15T{hour}:00:00+00:00','evidence_ref':ref,'batch_id':'SYN-001'} for hour,v in [('10',4.),('11',3.5),('12',2.)]])
adoption_ctx = p.identity.context_for(tenant,'dev-adoption')
adoption_cases = []
for case_id, case_site, oos in [('SYN-LEGACY-OOS-NF2','NF2',True),('SYN-LEGACY-NOTE-NF1','NF1',False)]:
    if args.acceptance_name:
        case_id += '-' + args.acceptance_name
    source_id = ('oos-lab' if oos else 'case-note') + ('-' + args.acceptance_name if args.acceptance_name else '')
    original_text = 'Synthetic original laboratory OOS result' if oos else 'Synthetic original case note'
    existing = p.store.read().get(tenant,'case',case_id)
    if not existing:
        record = p.evidence.ingest(adoption_ctx,source_system='synthetic-legacy',source_record_id=source_id,
            content=original_text.encode(),media_type='text/plain',site_id=case_site,event_time='2026-11-15T12:00:00+00:00')
        source_ref = {'kind':'evidence','id':record['evidence_id'],'revision':record['revision'],'site_id':case_site}
        associations = {'batch_id':'0002' if oos else '0001','equipment_id':'SYN-LV2' if oos else 'SYN-LV1','product_id':'SYN-P','material_id':'SYN-M','supplier_id':'SYN-SUP','lot_id':'0007'}
        if oos:
            origin=p.signals.raise_signal(tenant,kind='lab_oos',severity='action',site_id=case_site,subject={'kind':'batch','id':associations['batch_id']},
                rule='Synthetic laboratory event',rule_key='legacy-adoption',evidence_refs=[source_ref],associations=associations)
            p.signals.open_case(adoption_ctx,origin['signal_id'],owner_id='dev-adoption',qa_reviewer_id='dev-qa',case_id=case_id)
        else:
            p.cases.open(adoption_ctx,case_id,'dev-adoption','dev-qa',case_site)
            p.cases.add_timeline_event(adoption_ctx,case_id,'2026-11-15T12:00:00+00:00','Synthetic historical note',[source_ref])
        with p.store.transaction('synthetic-quality-launcher') as tx:
            saved=tx.require(tenant,'case',case_id)
            tx.put(tenant,'case',case_id,{**saved.state,'title':'Synthetic laboratory event' if oos else 'OOS word alone is not classification',
                'associations':{'lot_id':'0007'} if oos else associations,'priority':'high','initial_risk':'Awaiting qualified assessment',
                'deadline':'2026-12-01T09:30:00+00:00'},expected_revision=saved.revision,action='synthetic_adoption_source')
        p.evidence.ingest(adoption_ctx,source_system='synthetic-legacy',source_record_id=source_id,content=b'Synthetic newer revision',
            media_type='text/plain',site_id=case_site,event_time='2026-11-15T12:05:00+00:00')
    adoption_cases.append({'case_id':case_id,'site_id':case_site,'category':'oos' if oos else 'process_excursion',
        'source_ref':{'kind':'evidence','id':f'synthetic-legacy:{source_id}','revision':1,'site_id':case_site},'original_text':original_text})
response_loss_signals=[]
for index in range(5):
    previous=(prior.get('response_loss_signals') or [])
    previous_id=previous[index]['signal_id'] if index<len(previous) else ''
    if p.store.read().get(tenant,'deviation_signal',previous_id):
        item=p.signals.get(ctx,previous_id)
    else:
        item=p.signals.raise_signal(tenant,kind='spec_excursion',severity='action',site_id=site,
            subject={'kind':'batch','id':'SYN-001'},rule=f'Synthetic response-loss signal {index}',
            rule_key=f'response-loss-regression-{index}',evidence_refs=[ref],associations={'batch_id':'SYN-001','equipment_id':'SYN-V1'},
            event_time='2026-11-15T12:00:00+00:00')
    response_loss_signals.append({'signal_id':item['signal_id']})
(args.output / 'manifest.json').write_text(json.dumps({'signal_id':signal['signal_id'], 'source_ref':ref,
    'adoption_cases':adoption_cases,
    'response_loss_signals':response_loss_signals,
    'source_sha256':hashlib.sha256(p.evidence.original(ctx,ref['id'],ref['revision'])).hexdigest(),
    'pid':os.getpid(),'api':f'http://127.0.0.1:{args.port}', 'database':os.environ['LIFESCI_DATABASE_URL'],
    'providers':[], 'synthetic':True}, indent=2))
if args.acceptance_name:
    from scripts.deviation_acceptance_seed import seed
    seed(p,args.output,args.acceptance_name,packet)
print(f'QUALITY_READY pid={os.getpid()} port={args.port}', flush=True)
import uvicorn
try:
    uvicorn.run(create_app(p), host='127.0.0.1', port=args.port)
finally:
    p.store.release_connections()
