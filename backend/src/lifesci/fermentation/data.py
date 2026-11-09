"""Allowlisted public inputs; evaluator targets are deliberately loaded elsewhere."""
import json
from pathlib import Path
from ..ids import content_hash

DATA = Path(__file__).with_name('data')
CASE_IDS = ('sulfolobus', 'pichia')

def project(case_id):
    if case_id not in CASE_IDS:
        raise ValueError('unknown fermentation project')
    value = json.loads((DATA / (case_id + '.public.json')).read_text())
    value['data_hash'] = content_hash(value)
    return value


def oxygen_transfer_summary():
    """Independent CC-BY experimental means, not reconstructed run replicates."""
    import csv,hashlib,io
    raw=(DATA/'oxygen_transfer_darus_5953.csv').read_bytes()
    provenance=json.loads((DATA/'oxygen_transfer_darus_5953.provenance.json').read_text())
    if hashlib.sha256(raw).hexdigest()!=provenance['file_sha256']:raise ValueError('Experimental source file checksum changed')
    rows=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig')),delimiter=';'));observations=[]
    for row in rows:
        for name in ('RT_RT_co_current','RT_PBT_co_current','RT_RT_counter_current','RT_PBT_counter_current'):
            observations.append({'configuration_label':name,'rpm':float(row['rpm']),'vvm':float(row['vvm']),
                'power_w_m3':float(row[name+'_P_V']),'kla_h_inv':float(row[name+'_avg']),
                'reported_std_h_inv':float(row[name+'_std']),'working_volume_l':30.,'reactor_diameter_m':.289,
                'classification':'published_experimental_aggregate_not_independent_batch',
                'source_ref':provenance['dataset_doi']})
    return {'observations':observations,'provenance':provenance,'calibration_status':'uncalibrated',
            'independent_calibration_batches':0,'missing':['Individual trial identifiers and independence verification','Numeric impeller geometry for compatible receiver model inputs'],
            'scope':'One 30 L apparatus; four configuration labels are provenance, not neural ID features. Mean/std are never expanded into fabricated repeats.'}
