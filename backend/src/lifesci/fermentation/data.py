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
