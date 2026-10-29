"""Exercise existing PDF/DOCX ingestion, in an evaluator-only index, without new parsing code."""
import json
from pathlib import Path
from time import perf_counter


def verify_sources(output):
    from src.manufacturing_data import ManufacturingStore, ingest_package
    root=Path(__file__).resolve().parents[4]
    package=root/'backend/.cache/fermentation-evaluator-source-package'
    package.mkdir(parents=True,exist_ok=True)
    for case in ('sulfolobus','pichia'):
        source=root/'docs/research/fermentation'/case/'article.pdf'
        destination=package/(case+'.pdf')
        if not destination.exists() or destination.read_bytes()!=source.read_bytes():
            destination.write_bytes(source.read_bytes())
    supplement=root/'docs/research/fermentation/sulfolobus/supplement.docx'
    destination=package/'sulfolobus-supplement.docx'
    if not destination.exists() or destination.read_bytes()!=supplement.read_bytes():
        destination.write_bytes(supplement.read_bytes())
    store=ManufacturingStore(root/'backend/.cache/fermentation-evaluator-source-store')
    start=perf_counter()
    result=ingest_package(package,store,access_scope='fermentation-evaluator-only')
    record={'classification':'existing_parser_evaluator_side_execution_not_autonomous_extraction_accuracy',
        'runtime_seconds':perf_counter()-start,'result':result,
        'agent_access':'not supplied; full source papers contain receiving answers','human_preparation_minutes':None}
    path=Path(output);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(record,indent=2,default=str)+'\n')
    return record

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
    print(json.dumps(verify_sources(args.output),indent=2,default=str))
