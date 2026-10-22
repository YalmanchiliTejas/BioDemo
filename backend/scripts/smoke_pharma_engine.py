"""Execute the existing Prime harness on a tiny invented case, never a fixture report."""
import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from src.manufacturing_data import ManufacturingStore, ingest_package
from src.manufacturing_data.cmo.settings import load_local_settings
from src.prime_runtime import PrimeManufacturingHarness
from src.state import BlackboardStore
from src.workflows import ManufacturingInvestigationWorkflow


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--seconds',type=int,default=120)
    args=parser.parse_args(); load_local_settings()
    output=args.output.resolve(); output.mkdir(parents=True,exist_ok=False)
    raw=output/'raw'; raw.mkdir()
    (raw/'fermentation.csv').write_text('batch_id,Time (h),product (g/L),pH [pH]\nDEV-A,0,0,7\nDEV-A,2,2,7.1\nDEV-B,0,0,7\nDEV-B,2,1,6.8\n')
    store=ManufacturingStore(output/'store'); ingest=ingest_package(raw,store,access_scope='pharma-smoke')
    boards=BlackboardStore(output/'boards')
    workflow=ManufacturingInvestigationWorkflow(output/'workflow',store,scope='pharma-smoke',blackboards=boards)
    started=time.monotonic(); result={'synthetic':True,'source':'Independent invented development data','ingestion':ingest,'engine':'existing PrimeManufacturingHarness'}
    try:
        harness=PrimeManufacturingHarness.from_env(store=store,blackboards=boards,workflow=workflow,scope='pharma-smoke')
        harness.timeout_seconds=args.seconds; harness.max_tool_calls=12
        harness.execution_policy={'mode':'fixed_v1','soft_tool_calls':12}
        result['report']=harness.run(incident_id='pharma-smoke',problem='Describe the product trajectories by batch. Check original measurements and report that process comparability and causal explanations remain unestablished. Use a bounded descriptive investigation.',new_evidence_ids=[],as_of=datetime.now(timezone.utc).isoformat())
        result['status']='complete'
    except Exception as exc:
        result.update(status='failed',error_type=type(exc).__name__,error=str(exc))
    result['seconds']=time.monotonic()-started
    (output/'result.json').write_text(json.dumps(result,indent=2,default=str)+'\n')
    print(json.dumps({k:result[k] for k in ['status','seconds','engine','error_type','error'] if k in result}),flush=True)


if __name__=='__main__': main()
