"""Evaluation-only source-location comparison; never imported by agent tools."""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from importlib import metadata
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parent

def _connect(store: Path):
    con=sqlite3.connect(f"file:{store/'metadata.sqlite'}?mode=ro",uri=True)
    con.row_factory=sqlite3.Row
    return con

def cho(store: Path) -> dict:
    reference=json.loads((ROOT/"cho/reference/structural_map.json").read_text())
    with _connect(store) as con:
        columns={(row["path"],row["sheet"],row["column_index"]):row["name"]
                 for row in con.execute("SELECT s.path,c.sheet,c.column_index,c.name FROM source_columns c JOIN sources s ON s.id=c.source_id")}
        from src.manufacturing_data import ManufacturingStore
        bulk=ManufacturingStore(store)
        scopes=tuple(row[0] for row in con.execute('SELECT DISTINCT access_scope FROM sources'))
        counts=bulk.select('SELECT entity_id,count(*) AS count FROM observations GROUP BY entity_id',scopes=scopes)
        entities={row['entity_id'] for row in counts if row['entity_id']}
        obs_count=sum(row['count'] for row in counts)
        sources=con.execute("SELECT count(*) FROM sources WHERE extraction_status='indexed'").fetchone()[0]
        hashes={row["path"]:row["sha256"] for row in con.execute("SELECT path,sha256 FROM sources")}
        signatures=sorted({row[0] for row in con.execute("SELECT pipeline_version FROM sources")})
    mapped=0
    failures=[]
    for item in reference["mappings"]:
        key=(item["workbook"],item["source"]["sheet"],item["source"]["column"])
        actual=columns.get(key)
        if actual==item["aligned_column"]:
            mapped+=1
        elif len(failures)<20:
            failures.append({"source":key,"expected":item["aligned_column"],"observed":actual})
    expected_runs={f"EXP{i:03d}/R{reactor:02d}" for i in range(1,13) for reactor in (1,2)}
    return {"benchmark":"cho","source_files":sources,"observations":obs_count,
            "sampling":"first 20 data rows per worksheet; source headers complete",
            "reference_columns":len(reference["mappings"]),"exact_header_matches":mapped,
            "exact_header_match_rate":mapped/len(reference["mappings"]),
            "expected_runs":len(expected_runs),"recovered_expected_runs":len(entities&expected_runs),
            "additional_entity_candidates":len(entities-expected_runs),"failure_examples":failures,
            "source_sha256":hashes,"pipeline_signatures":signatures}

def fresenius(store: Path) -> dict:
    mappings=json.loads((ROOT/"fresenius/ground_truth/source_provenance.json").read_text())["mappings"]
    package=ROOT/"fresenius/raw_package"
    source_values={}
    for rel in sorted({m["source_file"] for m in mappings if "row" in m or "cell" in m}):
        path=package/rel
        if path.suffix.lower()==".csv":
            with path.open(newline="",encoding="utf-8-sig") as handle:
                reader=csv.DictReader(handle)
                for rowno,row in enumerate(reader,2):
                    for column,value in row.items():
                        source_values[(rel,rowno,column)]=value
        elif path.suffix.lower()==".xlsx":
            from openpyxl import load_workbook
            book=load_workbook(path,read_only=True,data_only=True)
            for sheet in book:
                for row in sheet:
                    for cell in row:
                        source_values[(rel,sheet.title,cell.coordinate)]=cell.value
            book.close()
    with _connect(store) as con:
        from src.manufacturing_data import ManufacturingStore
        bulk=ManufacturingStore(store)
        scopes=tuple(row[0] for row in con.execute('SELECT DISTINCT access_scope FROM sources'))
        observations=bulk.select('SELECT source_ref,value_text,extraction_method FROM observations',scopes=scopes)
        for row in observations:
            row['path']=json.loads(row['source_ref'])['path']
        sources=con.execute("SELECT count(*) FROM sources WHERE extraction_status='indexed'").fetchone()[0]
        hashes={row["path"]:row["sha256"] for row in con.execute("SELECT path,sha256 FROM sources")}
        signatures=sorted({row[0] for row in con.execute("SELECT pipeline_version FROM sources")})
    locations=set()
    text_by_page={}
    method_counts=Counter()
    for o in observations:
        ref=json.loads(o["source_ref"])
        method_counts[o["extraction_method"]]+=1
        if ref.get("cell"):
            locations.add((o["path"],ref.get("sheet"),ref["cell"]))
        if ref.get("row") and ref.get("column"):
            locations.add((o["path"],ref["row"],ref["column"]))
        if ref.get("page"):
            text_by_page.setdefault((o["path"],ref["page"]),[]).append(o["value_text"] or "")
    covered=Counter(); total=Counter(); blank=Counter(); failures=[]
    for m in mappings:
        path=m["source_file"]
        kind="structured" if "row" in m or "cell" in m else "document"
        total[kind]+=1
        if "cell" in m:
            key=(path,m["sheet"],m["cell"])
            expected_value=source_values.get(key)
            found=key in locations
        elif "row" in m:
            key=(path,m["row"],m["column"])
            expected_value=source_values.get(key)
            found=key in locations
        else:
            expected=str(m.get("source_span") or "").strip()
            body="\n".join(text_by_page.get((path,m.get("page")),[]))
            found=bool(expected and expected in body)
        if kind=="structured" and (expected_value is None or expected_value==""):
            blank[kind]+=1
            continue
        if found: covered[kind]+=1
        elif len(failures)<20:
            failures.append({"source_file":path,"row":m.get("row"),"cell":m.get("cell"),
                             "page":m.get("page"),"canonical_field":m["canonical_field"]})
    return {"benchmark":"fresenius","source_files":sources,"observations":len(observations),
            "reference_locations":dict(total),"blank_reference_cells":dict(blank),
            "nonempty_reference_locations":{kind:count-blank[kind] for kind,count in total.items()},
            "covered_nonempty_locations":dict(covered),
            "coverage_rate":{kind:covered[kind]/(count-blank[kind]) for kind,count in total.items()},
            "extraction_methods":dict(method_counts),"failure_examples":failures,
            "source_sha256":hashes,"pipeline_signatures":signatures}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--cho-store",type=Path)
    p.add_argument("--fresenius-store",type=Path)
    p.add_argument("--output",type=Path)
    p.add_argument("--cho-runtime",type=float,help="measured wall seconds for ingestion")
    p.add_argument("--fresenius-runtime",type=float,help="measured wall seconds for ingestion")
    args=p.parse_args()
    result={}
    result["environment"]={"python":sys.version.split()[0],"packages":{
        name:metadata.version(name) for name in ("duckdb","polars","pydantic","pint","pandera","openpyxl","pypdf","cocoindex","docling")}}
    if args.cho_store: result["cho"]=cho(args.cho_store)
    if args.fresenius_store: result["fresenius"]=fresenius(args.fresenius_store)
    result["execution"]={"cho_wall_seconds":args.cho_runtime,
                         "fresenius_wall_seconds":args.fresenius_runtime,
                         "model_calls":0,"input_tokens":0,"output_tokens":0,
                         "inference_cost_usd":0,"manual_mappings":0,
                         "manual_data_corrections":0}
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))

if __name__=="__main__": main()
