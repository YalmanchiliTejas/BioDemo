from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .ingest import _members, ingest_package
from .store import ManufacturingStore
from .tools import ManufacturingTools

def _coco_inventory(package: Path, store: ManufacturingStore) -> dict:
    stage = None
    source = package
    if package.suffix.lower() == ".zip":
        stage = tempfile.TemporaryDirectory(prefix="manufacturing-coco-")
        source = Path(stage.name)
        for rel,body,_,_ in _members(package):
            target=source/rel
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(body)
    inventory=store.root/"cocoindex_inventory"
    env={**os.environ,"MFG_SOURCE_DIR":str(source),"MFG_INVENTORY_DIR":str(inventory),
         "COCOINDEX_DB":str(store.root/"cocoindex.sqlite"),
         "COCOINDEX_DISABLE_USAGE_TRACKING":"1"}
    try:
        binary=Path(sys.executable).with_name("cocoindex")
        executable=str(binary) if binary.exists() else (shutil.which("cocoindex") or "cocoindex")
        subprocess.run([executable,"update",
                        "src.manufacturing_data.cocoindex_app","-q"],check=True,env=env)
        manifests=[json.loads(p.read_text()) for p in inventory.glob("*.json")]
        return {"files":len(manifests),"inventory_path":str(inventory)}
    finally:
        if stage: stage.cleanup()

def main() -> None:
    parser=argparse.ArgumentParser(description="Batch manufacturing evidence data layer")
    sub=parser.add_subparsers(dest="command",required=True)
    ingest=sub.add_parser("ingest",help="copy and index a folder or ZIP")
    ingest.add_argument("package",type=Path)
    ingest.add_argument("--store",type=Path,required=True)
    ingest.add_argument("--scope",default="default")
    ingest.add_argument("--orchestrator",choices=("cocoindex","checksum"),default="cocoindex")
    ingest.add_argument("--document-backend",choices=("auto","pypdf","docling","chandra","paddleocr-vl"),default="auto")
    ingest.add_argument("--max-rows-per-file",type=int)
    query=sub.add_parser("tool",help="call one RLM data tool with JSON arguments")
    query.add_argument("name",choices=("inspect_data","infer_schema","reconcile_entities","normalize_measurements",
                        "query_data","search_evidence","verify_evidence","extract_region",
                        "get_process_context","get_state_at"))
    query.add_argument("--store",type=Path,required=True)
    query.add_argument("--args",default="{}")
    query.add_argument("--scope",action="append",default=[])
    query.add_argument("--as-of")
    args=parser.parse_args()
    store=ManufacturingStore(args.store)
    if args.command=="ingest":
        out={}
        if args.orchestrator=="cocoindex":
            out["cocoindex"]=_coco_inventory(args.package.resolve(),store)
        out["ingestion"]=ingest_package(args.package,store,access_scope=args.scope,
                                         document_backend=args.document_backend,
                                         max_rows_per_file=args.max_rows_per_file)
    else:
        tools=ManufacturingTools(store,as_of=args.as_of,scopes=tuple(args.scope or ["default"]))
        out=tools.handlers()[args.name](**json.loads(args.args))
    print(json.dumps(out,indent=2,default=str))

if __name__=="__main__": main()
