"""The public datasets the skill benchmarks use: where each comes from, under what terms, and how it is fetched.

Every file is downloaded once into backend/.cache/skill-benchmarks/<dataset>/ (never into the repository), checked
against the size and SHA-256 recorded here, and read from there. Nothing is fetched at import time. Dataset files
are data, never code: they are parsed with csv/json/zipfile only.

Sources and terms were checked on 2026-11-15 against each dataset's own page or API.
"""
from __future__ import annotations

import hashlib
import urllib.request
from pathlib import Path

CACHE = Path(__file__).resolve().parents[2] / '.cache' / 'skill-benchmarks'
CHO_ARCHIVE = Path(__file__).resolve().parents[2] / '.cache' / 'cho-source' / 'Dataset.zip'

DATASETS = {
    'cho': {
        'title': 'CHO-K1 bioreactor cultivations', 'doi': '10.5281/zenodo.20829178', 'licence': 'CC-BY-4.0',
        'kind': 'Real laboratory measurements: 24 cultivations (12 experiments x 2 reactors), no fault or quality labels.',
        'files': {'Dataset.zip': {'url': 'https://zenodo.org/api/records/20829178/files/Dataset.zip/content',
                                  'sha256': '46a6b92b77883d56df3be015895d93c85b2b2547121af0b8bc0a92f3fbefd17b'}}},
    'tablet': {
        'title': 'Pharmaceutical tablet manufacturing (Zagar & Mihelic, Scientific Data 2022)',
        'doi': '10.6084/m9.figshare.c.5645578', 'licence': 'CC-BY-4.0',
        'kind': 'Real production data from one manufacturer, anonymised: 1,005 batches, laboratory results, process '
                'summaries and raw-material lots per batch. Every batch was within specification: no failed batches.',
        'files': {'Laboratory.csv': {'url': 'https://ndownloader.figshare.com/files/30966250', 'bytes': 293492},
                  'Process.csv': {'url': 'https://ndownloader.figshare.com/files/30874192', 'bytes': 257208},
                  'Normalization.csv': {'url': 'https://ndownloader.figshare.com/files/30874189', 'bytes': 433}}},
    'fda_drug_recalls': {
        'title': 'openFDA drug enforcement reports', 'doi': None, 'licence': 'CC0-1.0 (openFDA terms of service apply)',
        'kind': 'Real regulatory recall records; FDA: "assume all results are unvalidated". Lot numbers are free text.',
        'files': {'drug-enforcement.json.zip': {
            'url': 'https://download.open.fda.gov/drug/enforcement/drug-enforcement-0001-of-0001.json.zip'}}},
    'fda_device_recalls': {
        'title': 'openFDA device recalls', 'doi': None, 'licence': 'CC0-1.0 (openFDA terms; GMDN terms excluded)',
        'kind': 'Real regulatory recall records with an FDA-assigned general cause category for each recall.',
        'files': {'device-recall.json.zip': {
            'url': 'https://download.open.fda.gov/device/recall/device-recall-0001-of-0001.json.zip'}}},
    'distillation': {
        'title': 'Batch distillation plant anomaly database (RPTU Kaiserslautern-Landau)', 'doi': '10.5281/zenodo.17395544',
        'licence': 'CC-BY-4.0',
        'kind': 'Real laboratory plant, 119 runs, 82 with faults the operators induced and labelled: anomaly times, the sensor '
                'that showed each, what was done to cause it and when. Only the tables are used (19 MB of an 85 GB archive).',
        'files': {}},
    'clinc150': {
        'title': 'CLINC150 intent data with out-of-scope queries', 'doi': None, 'licence': 'CC-BY-3.0',
        'kind': 'Real crowd-written requests to an assistant in 150 intents, plus requests that fit none of them. '
                'General assistant domains, not manufacturing.',
        'files': {'data_full.json': {'url': 'https://raw.githubusercontent.com/clinc/oos-eval/master/data/data_full.json',
                                     'bytes': 2495390}}},
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def path(dataset: str, name: str, *, download: bool = False) -> Path:
    """The local file, fetched if asked and absent. A size or checksum that differs from the record is an error:
    a changed source must be looked at, not silently used."""
    spec = DATASETS[dataset]['files'][name]
    target = CHO_ARCHIVE if dataset == 'cho' else CACHE / dataset / name
    if not target.exists():
        if not download:
            raise FileNotFoundError(f'{dataset}/{name} is not downloaded; run benchmarks/skills/run.py --download')
        target.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(spec['url'], headers={'User-Agent': 'skill-benchmark-fetch/1'})
        with urllib.request.urlopen(request, timeout=300) as response, target.with_suffix(target.suffix + '.part').open('wb') as out:
            for block in iter(lambda: response.read(1 << 20), b''):
                out.write(block)
        target.with_suffix(target.suffix + '.part').rename(target)
    if spec.get('bytes') is not None and target.stat().st_size != spec['bytes']:
        raise ValueError(f'{dataset}/{name}: {target.stat().st_size} bytes, expected {spec["bytes"]}')
    if spec.get('sha256') and sha256(target) != spec['sha256']:
        raise ValueError(f'{dataset}/{name}: checksum differs from the recorded one')
    return target


def provenance(names) -> list[dict]:
    """What the report says about each dataset it used, with the checksum of the exact file read."""
    out = []
    for dataset in names:
        spec = DATASETS[dataset]
        files = {}
        for name in spec['files']:
            target = CHO_ARCHIVE if dataset == 'cho' else CACHE / dataset / name
            if target.exists():
                files[name] = {'bytes': target.stat().st_size, 'sha256': sha256(target)}
        out.append({k: spec[k] for k in ('title', 'doi', 'licence', 'kind')} | {'dataset': dataset, 'files': files})
    return out
