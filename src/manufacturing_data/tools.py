from __future__ import annotations

import csv
import hashlib
import json
import re
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from .models import ToolRequest, ToolResponse
from .store import ManufacturingStore

class QueryRequest(ToolRequest):
    sql: str

class SearchRequest(ToolRequest):
    query: str
    mode: Literal["lexical","semantic"] = "lexical"

class EvidenceRequest(ToolRequest):
    observation_id: str

class EntityRequest(ToolRequest):
    entity_id: str

class UnitRequest(ToolRequest):
    observation_ids: list[str]
    target_unit: str

class RegionRequest(ToolRequest):
    source_id: str
    sheet: str | None = None
    page: int | None = None
    row: int | None = None
    column: str | None = None
    region: tuple[float,float,float,float] | None = None
    backend: str = "auto"

class ManufacturingTools:
    """The main RLM calls these functions; this class does no investigation planning."""
    def __init__(self, store: ManufacturingStore, *, as_of: str | None = None,
                 scopes: tuple[str,...] = ("default",)):
        self.store = store
        self.as_of = as_of
        self.scopes = scopes

    def _visibility(self, arg: dict) -> dict:
        request = ToolRequest.model_validate({"as_of":self.as_of,"scopes":list(self.scopes),**arg})
        if self.as_of and request.as_of:
            def instant(value: str) -> datetime:
                dt=datetime.fromisoformat(value.replace("Z","+00:00"))
                return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
            if instant(request.as_of)>instant(self.as_of):
                raise PermissionError("cannot advance the session's historical cutoff")
        if not set(request.scopes).issubset(self.scopes):
            raise PermissionError("requested access scope is not granted")
        return request.model_dump()

    def _sources(self, arg: dict) -> list[dict]:
        v = self._visibility(arg)
        return self.store.visible_sources(as_of=v["as_of"], scopes=v["scopes"])

    def _obs(self, arg: dict, *, scan_all: bool = False, **filters) -> list[dict]:
        v = self._visibility(arg)
        return self.store.visible(as_of=v["as_of"],scopes=v["scopes"],limit=None if scan_all else v["limit"],
                                  offset=0 if scan_all else v["offset"],**filters)

    def inspect_data(self, **kwargs) -> dict:
        sources = self._sources(kwargs)
        obs = self._obs(kwargs,scan_all=True)
        by_source = Counter(o["source_id"] for o in obs)
        by_schema=defaultdict(lambda:defaultdict(set))
        with self.store.connect() as con:
            for source in sources:
                for col in con.execute("SELECT sheet,name FROM source_columns WHERE source_id=? ORDER BY column_index",(source["id"],)):
                    by_schema[source["id"]][col["sheet"] or "<file>"].add(col["name"])
        return {"sources":[{"id":s["id"],"path":s["path"],"sha256":s["sha256"],
                            "format":s["format"],"status":s["extraction_status"],
                            "observations":by_source[s["id"]],
                            "sheets":{k:sorted(v) for k,v in by_schema[s["id"]].items()}} for s in sources],
                "variables":dict(Counter(o["name"] for o in obs)),
                "evidence_ids":[o["id"] for o in obs[:1000]],
                "evidence_id_count":len(obs)}

    def infer_schema(self, **kwargs) -> dict:
        obs = self._obs(kwargs,scan_all=True)
        sources=self._sources(kwargs)
        names={o["name"] for o in obs}
        with self.store.connect() as con:
            for source in sources:
                names.update(row[0] for row in con.execute("SELECT name FROM source_columns WHERE source_id=?",(source["id"],)))
        mappings=[]
        for name in sorted(names):
            norm = re.sub(r"[^a-z0-9]+","_",name.lower()).strip("_")
            role = ("time" if any(x in norm for x in ("timestamp","time","date")) else
                    "entity_identifier" if any(x in norm for x in ("batch","lot","run","reactor","equipment","sample")) else
                    "measurement" if any(o["value_number"] is not None for o in obs if o["name"]==name) else "text")
            units = sorted({o["unit"] for o in obs if o["name"]==name and o["unit"]})
            mappings.append({"source_name":name,"suggested_role":role,"units":units,
                             "status":"proposed","evidence_ids":[o["id"] for o in obs if o["name"]==name][:5]})
        return {"mappings":mappings,"evidence_ids":[o["id"] for o in obs[:1000]],
                "evidence_id_count":len(obs)}

    def reconcile_entities(self, **kwargs) -> dict:
        obs = self._obs(kwargs,scan_all=True)
        grouped=defaultdict(list)
        for o in obs:
            if o["entity_id"]: grouped[o["entity_id"]].append(o)
        return {"candidates":[{"entity_id":key,"source_ids":sorted({r["source_id"] for r in rows}),
                                "observation_count":len(rows),"status":"candidate",
                                "evidence_ids":[r["id"] for r in rows[:10]]} for key,rows in grouped.items()],
                "unlinked_observations":sum(not o["entity_id"] for o in obs),
                "evidence_ids":[o["id"] for o in obs[:1000]],"evidence_id_count":len(obs)}

    def normalize_measurements(self, **kwargs) -> dict:
        req = UnitRequest.model_validate({"as_of":self.as_of,"scopes":list(self.scopes),**kwargs})
        self._visibility(req.model_dump())
        import pint
        import polars as pl
        import pandera.polars as pa
        registry = pint.UnitRegistry()
        wanted=set(req.observation_ids)
        rows=[o for o in self._obs({"as_of":req.as_of,"scopes":req.scopes},scan_all=True) if o["id"] in wanted]
        output=[]
        for o in rows:
            item={"observation_id":o["id"],"original_value":o["value_number"],"original_unit":o["unit"]}
            try:
                if o["value_number"] is None or not o["unit"]: raise ValueError("numeric value or unit missing")
                value=registry.Quantity(o["value_number"],o["unit"]).to(req.target_unit).magnitude
                frame=pl.DataFrame({"value_number":[float(value)]})
                pa.DataFrameSchema({"value_number":pa.Column(float,nullable=False)}).validate(frame)
                item.update(value=float(value),unit=req.target_unit,status="normalized")
            except Exception as exc:
                item.update(status="unresolved",reason=str(exc))
            output.append(item)
        return {"measurements":output,"evidence_ids":[o["id"] for o in rows]}

    def query_data(self, **kwargs) -> dict:
        req=QueryRequest.model_validate({"as_of":self.as_of,"scopes":list(self.scopes),**kwargs})
        self._visibility(req.model_dump())
        sql=req.sql.strip()
        if not re.match(r"(?is)^select\s",sql) or ";" in sql or re.search(r"(?i)\b(read_csv|read_parquet|read_json|copy|attach|install|load|pragma|create|delete|insert|update|drop|alter|call|export|import)\b",sql):
            raise ValueError("only a single SELECT over the observations table is allowed")
        import duckdb
        source_ids={s["id"] for s in self._sources({"as_of":req.as_of,"scopes":req.scopes})
                    if s["extraction_status"]=="indexed"}
        paths=[str(p) for source_id in source_ids for p in self.store.numerical.glob(f"{source_id}-*.parquet")]
        con=duckdb.connect(database=":memory:")
        try:
            if paths:
                if req.as_of:
                    con.execute("CREATE TABLE observations AS SELECT * FROM read_parquet(?,union_by_name=true) WHERE available_at IS NULL OR TRY_CAST(available_at AS TIMESTAMPTZ)<=TRY_CAST(? AS TIMESTAMPTZ)",
                                [paths,req.as_of])
                else:
                    con.execute("CREATE TABLE observations AS SELECT * FROM read_parquet(?,union_by_name=true)",[paths])
            else:
                con.execute("CREATE TABLE observations (id VARCHAR,source_id VARCHAR,name VARCHAR,value_number DOUBLE,unit VARCHAR,occurred_at VARCHAR,available_at VARCHAR,entity_id VARCHAR,access_scope VARCHAR)")
            con.execute("SET enable_external_access=false")
            cursor=con.execute("SELECT * FROM ("+sql+") LIMIT ? OFFSET ?",[req.limit,req.offset])
            columns=[x[0] for x in cursor.description]
            values=[list(row) for row in cursor.fetchall()]
            citations=[str(row[columns.index("id")]) for row in values] if "id" in columns else []
            return {"columns":columns,"rows":values,"evidence_ids":citations,
                    "provenance_status":"row_ids" if citations else "aggregate_lineage_unresolved",
                    "source_count":len(source_ids),"parquet_shards":len(paths)}
        finally: con.close()

    def search_evidence(self, **kwargs) -> dict:
        req=SearchRequest.model_validate({"as_of":self.as_of,"scopes":list(self.scopes),**kwargs})
        rows=self._obs({"as_of":req.as_of,"scopes":req.scopes},scan_all=True)
        if req.mode=="semantic":
            try:
                from fastembed import TextEmbedding
            except ImportError as exc:
                raise RuntimeError("Install the existing semantic extra to use local semantic search") from exc
            candidates=[o for o in rows if o["name"]=="document_text" and o["value_text"]]
            model=TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
            vectors=list(model.embed([req.query]+[o["value_text"] for o in candidates]))
            if not vectors:
                return {"records":[],"evidence_ids":[],"search_method":"semantic_local"}
            query_vector=vectors[0]
            ranked=sorted(zip(candidates,vectors[1:]),
                          key=lambda pair:float(query_vector@pair[1]),reverse=True)
            selected=[o for o,_ in ranked[req.offset:req.offset+req.limit]]
            return {"records":selected,"evidence_ids":[o["id"] for o in selected],
                    "search_method":"semantic_local"}
        terms=[term.lower() for term in re.findall(r"\w+",req.query) if len(term)>1]
        hits=[]
        for o in rows:
            hay=f"{o['name']} {o['value_text'] or ''} {o['entity_id'] or ''}".lower()
            score=sum(term in hay for term in terms)
            if score: hits.append((score,o))
        hits.sort(key=lambda x:(-x[0],x[1]["id"]))
        selected=[o for _,o in hits[req.offset:req.offset+req.limit]]
        return {"records":selected,"evidence_ids":[o["id"] for o in selected],
                "search_method":"lexical", "truncated_input":False}

    def verify_evidence(self, **kwargs) -> dict:
        req=EvidenceRequest.model_validate({"as_of":self.as_of,"scopes":list(self.scopes),**kwargs})
        matches=self._obs({"as_of":req.as_of,"scopes":req.scopes},observation_id=req.observation_id)
        if not matches: raise KeyError("evidence not visible")
        o=matches[0]
        with self.store.connect() as con:
            source=dict(con.execute("SELECT * FROM sources WHERE id=?",(o["source_id"],)).fetchone())
        path=self.store.originals/source["sha256"][:2]/(source["sha256"]+Path(source["path"]).suffix.lower())
        integrity=hashlib.sha256(path.read_bytes()).hexdigest()==source["sha256"]
        ref=o["source_ref"]
        observed=None
        if source["format"] in {".csv",".tsv",".xlsx",".xlsm",".parquet"} and ref["row"] is not None:
            from .ingest import _rows
            for sheet,row,headers,values in _rows(path):
                if sheet==ref["sheet"] and row==ref["row"]:
                    observed=str(dict(zip(headers,values)).get(ref["column"]))
                    break
        elif o["extraction_method"]=="pypdf":
            from .ingest import _document_observations
            for candidate in _document_observations(o["source_id"],source["path"],path,o["access_scope"],o["available_at"],"pypdf"):
                if candidate.observation_id==o["id"]:
                    observed=candidate.value_text; break
        return {"observation_id":o["id"],"source_integrity":integrity,
                "value_matches":observed==o["value_text"] if observed is not None else None,
                "observed":observed,"validation_status":o["validation_status"],
                "source_ref":ref,"evidence_ids":[o["id"]]}

    def extract_region(self, **kwargs) -> dict:
        req=RegionRequest.model_validate({"as_of":self.as_of,"scopes":list(self.scopes),**kwargs})
        source=next((s for s in self._sources(req.model_dump()) if s["id"]==req.source_id),None)
        if source is None: raise KeyError("source not visible")
        path=self.store.originals/source["sha256"][:2]/(source["sha256"]+Path(source["path"]).suffix.lower())
        if source["format"] in {".csv",".tsv",".xlsx",".xlsm",".parquet"}:
            from .ingest import _rows
            for sheet,row,headers,values in _rows(path):
                if (req.sheet is None or sheet==req.sheet) and row==req.row:
                    data=dict(zip(headers,values))
                    return {"source_id":req.source_id,"sheet":sheet,"row":row,
                            "data":{req.column:data.get(req.column)} if req.column else data,
                            "status":"source_transcribed"}
            return {"status":"region_not_found"}
        if source["format"]==".pdf":
            from pypdf import PdfReader
            pages=PdfReader(str(path)).pages
            if req.page is None or req.page<1 or req.page>len(pages): raise ValueError("valid page is required")
            text=pages[req.page-1].extract_text() or ""
            if text and req.region is None and req.backend=="auto":
                return {"source_id":req.source_id,"page":req.page,"text":text[:20000],
                        "status":"source_transcribed"}
            import pypdfium2
            image=pypdfium2.PdfDocument(str(path))[req.page-1].render(scale=2).to_pil()
        elif source["format"] in {".png",".jpg",".jpeg",".tif",".tiff"}:
            from PIL import Image
            image=Image.open(path)
        else:
            return {"source_id":req.source_id,"status":"unsupported_region_format"}
        if req.region is not None:
            image=image.crop(tuple(int(v) for v in req.region))
        from .ingest import _document_observations, _ocr_image
        if req.backend in {"auto","tesseract"}:
            text=_ocr_image(image)
            method="tesseract"
        elif req.backend in {"docling","chandra","paddleocr-vl"}:
            with tempfile.TemporaryDirectory(prefix="manufacturing-region-") as directory:
                crop=Path(directory)/"region.png"
                image.save(crop)
                text="\n".join(o.value_text or "" for o in _document_observations(
                    req.source_id,source["path"],crop,source["access_scope"],source["available_at"],req.backend))
            method=req.backend
        else:
            raise ValueError("unknown region extraction backend")
        return {"source_id":req.source_id,"page":req.page,"region":req.region,
                "text":text[:20000],"method":method,"status":"unverified" if text else "unresolved"}

    def get_process_context(self, **kwargs) -> dict:
        req=EntityRequest.model_validate({"as_of":self.as_of,"scopes":list(self.scopes),**kwargs})
        records=self._obs({"as_of":req.as_of,"scopes":req.scopes,"limit":req.limit},entity_id=req.entity_id)
        permitted={s["id"] for s in self._sources(req.model_dump()) if s["extraction_status"]=="indexed"}
        with self.store.connect() as con:
            if req.as_of:
                cursor=con.execute("SELECT * FROM relations WHERE (left_id=? OR right_id=?) AND "
                                   "(available_at IS NULL OR julianday(available_at)<=julianday(?))",
                                   (req.entity_id,req.entity_id,req.as_of))
            else:
                cursor=con.execute("SELECT * FROM relations WHERE left_id=? OR right_id=?",
                                   (req.entity_id,req.entity_id))
            links=[dict(row) for row in cursor if row["source_id"] in permitted]
        return {"entity_id":req.entity_id,"records":records,"source_ids":sorted({o["source_id"] for o in records}),
                "related_entities":sorted({x["right_id"] if x["left_id"]==req.entity_id else x["left_id"] for x in links}),
                "relations":links,"evidence_ids":[o["id"] for o in records]}

    def get_state_at(self, **kwargs) -> dict:
        req=ToolRequest.model_validate({"as_of":self.as_of,"scopes":list(self.scopes),**kwargs})
        if not req.as_of: raise ValueError("as_of required")
        records=self._obs(req.model_dump())
        structured=[s for s in self._sources(req.model_dump()) if s["format"] in
                    {".csv",".tsv",".xlsx",".xlsm",".parquet"}]
        warnings=[]
        with self.store.connect() as con:
            for source in structured:
                fields={row[0].lower() for row in con.execute("SELECT name FROM source_columns WHERE source_id=?",(source["id"],))}
                if "field_available_at" not in fields:
                    warnings.append(f"{source['path']}: field-level publication times absent; row cutoff cannot certify mutable fields")
        return {"as_of":req.as_of,"records":records,"evidence_ids":[o["id"] for o in records],
                "warnings":warnings,"temporal_integrity":"row_level_only" if warnings else "field_level_if_supplied"}

    def handlers(self) -> dict[str,Any]:
        def typed(method):
            def call(**kwargs):
                return ToolResponse.model_validate(method(**kwargs)).model_dump(exclude_unset=True)
            return call
        return {name:typed(getattr(self,name)) for name in ("inspect_data","infer_schema","reconcile_entities",
                "normalize_measurements","query_data","search_evidence","verify_evidence",
                "extract_region","get_process_context","get_state_at")}
