from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Iterable

from .models import Observation

DDL = """
CREATE TABLE IF NOT EXISTS sources (
 id TEXT PRIMARY KEY, path TEXT NOT NULL, original_path TEXT NOT NULL, sha256 TEXT NOT NULL,
 size_bytes INTEGER NOT NULL, modified_at TEXT, available_at TEXT, access_scope TEXT NOT NULL,
 format TEXT NOT NULL, extraction_status TEXT NOT NULL, error TEXT, pipeline_version TEXT,
 original_mode INTEGER, routing_json TEXT
);
CREATE TABLE IF NOT EXISTS observations (
 id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(id), name TEXT NOT NULL,
 value_text TEXT, value_number REAL, unit TEXT, occurred_at TEXT, available_at TEXT,
 entity_id TEXT, validation_status TEXT NOT NULL, access_scope TEXT NOT NULL,
 source_ref TEXT NOT NULL, extraction_method TEXT NOT NULL, confidence REAL
);
CREATE TABLE IF NOT EXISTS entities (
 id TEXT PRIMARY KEY, kind TEXT NOT NULL, label TEXT NOT NULL, confidence REAL NOT NULL,
 source_id TEXT NOT NULL REFERENCES sources(id), rationale TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS records (
 id TEXT PRIMARY KEY, kind TEXT NOT NULL, source_id TEXT NOT NULL REFERENCES sources(id),
 sheet TEXT, row_number INTEGER, occurred_at TEXT, available_at TEXT,
 entity_id TEXT, access_scope TEXT NOT NULL, validation_status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS source_columns (
 source_id TEXT NOT NULL REFERENCES sources(id), sheet TEXT, column_index INTEGER NOT NULL,
 name TEXT NOT NULL, unit TEXT, PRIMARY KEY (source_id,sheet,column_index)
);
CREATE TABLE IF NOT EXISTS relations (
 left_id TEXT NOT NULL, right_id TEXT NOT NULL, relation TEXT NOT NULL,
 source_id TEXT NOT NULL, confidence REAL NOT NULL, available_at TEXT,
 PRIMARY KEY (left_id,right_id,relation,source_id)
);
CREATE INDEX IF NOT EXISTS obs_entity ON observations(entity_id);
CREATE INDEX IF NOT EXISTS obs_available ON observations(available_at);
CREATE INDEX IF NOT EXISTS obs_source ON observations(source_id);
"""

class ManufacturingStore:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.root.chmod(0o700)
        self.originals = self.root / "originals"
        self.originals.mkdir(exist_ok=True)
        self.originals.chmod(0o700)
        self.numerical = self.root / "numerical"
        self.numerical.mkdir(exist_ok=True)
        self.numerical.chmod(0o700)
        self.db = self.root / "metadata.sqlite"
        with self.connect() as con:
            con.executescript(DDL)
            if "available_at" not in {row[1] for row in con.execute("PRAGMA table_info(relations)")}:
                con.execute("ALTER TABLE relations ADD COLUMN available_at TEXT")
            if "pipeline_version" not in {row[1] for row in con.execute("PRAGMA table_info(sources)")}:
                con.execute("ALTER TABLE sources ADD COLUMN pipeline_version TEXT")
            if "original_mode" not in {row[1] for row in con.execute("PRAGMA table_info(sources)")}:
                con.execute("ALTER TABLE sources ADD COLUMN original_mode INTEGER")
            if "routing_json" not in {row[1] for row in con.execute("PRAGMA table_info(sources)")}:
                con.execute("ALTER TABLE sources ADD COLUMN routing_json TEXT")
        self.db.chmod(0o600)

    def connect(self):
        con = sqlite3.connect(self.db)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        return con

    @staticmethod
    def digest(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    def visible(self, *, as_of: str | None = None, scopes: Iterable[str] = ("default",),
                entity_id: str | None = None, source_id: str | None = None,
                name: str | None = None, observation_id: str | None = None,
                limit: int | None = 1000, offset: int = 0) -> list[dict]:
        scopes = list(scopes)
        if not scopes:
            return []
        clauses = ["s.extraction_status='indexed'", "o.access_scope IN (" + ",".join("?" for _ in scopes) + ")"]
        params: list = scopes[:]
        if as_of:
            clauses.append("(o.available_at IS NULL OR julianday(o.available_at) <= julianday(?))")
            clauses.append("(s.available_at IS NULL OR julianday(s.available_at) <= julianday(?))")
            params += [as_of, as_of]
        for column, value in (("o.entity_id", entity_id), ("o.source_id", source_id), ("o.name", name), ("o.id", observation_id)):
            if value is not None:
                clauses.append(column + "=?")
                params.append(value)
        sql = "SELECT o.* FROM observations o JOIN sources s ON s.id=o.source_id WHERE " + " AND ".join(clauses) + " ORDER BY o.source_id,o.id"
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([limit,offset])
        with self.connect() as con:
            rows = [dict(row) for row in con.execute(sql, params)]
        for row in rows:
            row["source_ref"] = json.loads(row["source_ref"])
        return rows

    def visible_sources(self, *, as_of: str | None = None, scopes: Iterable[str] = ("default",)) -> list[dict]:
        scopes = list(scopes)
        if not scopes:
            return []
        sql = "SELECT s.* FROM sources s WHERE s.access_scope IN (" + ",".join("?" for _ in scopes) + ")"
        args: list = scopes[:]
        if as_of:
            sql += " AND ((s.available_at IS NOT NULL AND julianday(s.available_at)<=julianday(?)) OR EXISTS "
            sql += "(SELECT 1 FROM observations o WHERE o.source_id=s.id AND o.access_scope=s.access_scope "
            sql += "AND o.available_at IS NOT NULL AND julianday(o.available_at)<=julianday(?)))"
            args.extend([as_of,as_of])
        with self.connect() as con:
            rows = [dict(row) for row in con.execute(sql + " ORDER BY path", args)]
        for row in rows:
            row["routing"] = json.loads(row["routing_json"]) if row.get("routing_json") else None
        return rows

    def add_observations(self, rows: Iterable[Observation], *, batch_size: int = 5000) -> int:
        count = 0
        with self.connect() as con:
            batch = []
            for o in rows:
                for kind,related_id in o.related_entities:
                    con.execute("INSERT OR IGNORE INTO entities VALUES (?,?,?,?,?,?)",
                                (related_id,kind,related_id,0.6,o.source.source_id,
                                 "candidate inferred from source identifier"))
                    if o.entity_id and related_id != o.entity_id:
                        con.execute("INSERT OR IGNORE INTO relations VALUES (?,?,?,?,?,?)",
                                    (o.entity_id,related_id,"co_observed",o.source.source_id,0.6,o.available_at))
                record_id = hashlib.sha256(f"{o.source.source_id}|{o.source.sheet}|{o.source.row}|{o.source.page}".encode()).hexdigest()[:24]
                path = o.source.path.lower()
                record_kind = next((kind for marker,kind in (("deviation","deviation"),("investigation","investigation"),
                    ("maintenance","maintenance"),("lab","laboratory_result"),("sample","sample"),
                    ("batch","batch"),("event","event")) if marker in path),"source_record")
                con.execute("INSERT OR IGNORE INTO records VALUES (?,?,?,?,?,?,?,?,?,?)",
                            (record_id,record_kind,o.source.source_id,o.source.sheet,o.source.row,
                             o.occurred_at,o.available_at,o.entity_id,o.access_scope,o.validation_status))
                if o.entity_id and o.entity_kind:
                    con.execute("INSERT OR IGNORE INTO entities VALUES (?,?,?,?,?,?)",
                                (o.entity_id,o.entity_kind,o.entity_id,0.6,o.source.source_id,
                                 "candidate inferred from explicit identifier column or source label"))
                batch.append((o.observation_id,o.source.source_id,o.name,o.value_text,o.value_number,o.unit,
                              o.occurred_at,o.available_at,o.entity_id,o.validation_status,o.access_scope,
                              o.source.model_dump_json(),o.extraction_method,o.confidence))
                if len(batch) >= batch_size:
                    con.executemany("INSERT OR REPLACE INTO observations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", batch)
                    count += len(batch); batch.clear()
            if batch:
                con.executemany("INSERT OR REPLACE INTO observations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", batch)
                count += len(batch)
        return count

    def export_numerical(self, source_id: str, *, batch_size: int = 50000) -> int:
        """Materialize numeric observations into bounded Parquet shards."""
        import polars as pl
        import pandera.polars as pa
        count = 0
        for path in self.numerical.glob(f"{source_id}-*.parquet"):
            path.unlink()
        with self.connect() as con:
            cursor = con.execute("SELECT id,source_id,name,value_number,unit,occurred_at,available_at,entity_id,access_scope "
                                 "FROM observations WHERE source_id=? AND value_number IS NOT NULL ORDER BY id", (source_id,))
            while chunk := cursor.fetchmany(batch_size):
                frame = pl.DataFrame([dict(row) for row in chunk])
                pa.DataFrameSchema({"value_number":pa.Column(float,nullable=False)}).validate(frame)
                path = self.numerical / f"{source_id}-{count // batch_size:05d}.parquet"
                frame.write_parquet(path)
                path.chmod(0o600)
                count += len(chunk)
        return count
