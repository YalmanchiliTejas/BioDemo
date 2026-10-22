from __future__ import annotations

import hashlib
import json
import sqlite3
import re
from contextlib import contextmanager
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
CREATE TABLE IF NOT EXISTS sheets (
 source_id TEXT NOT NULL REFERENCES sources(id), sheet_index INTEGER NOT NULL, sheet TEXT,
 parquet_path TEXT NOT NULL, row_count INTEGER NOT NULL, row_start INTEGER NOT NULL,
 observation_count INTEGER NOT NULL, min_available_at TEXT, schema_json TEXT NOT NULL, parquet_sha256 TEXT,
 PRIMARY KEY (source_id,sheet_index)
);
CREATE INDEX IF NOT EXISTS obs_entity ON observations(entity_id);
CREATE INDEX IF NOT EXISTS obs_available ON observations(available_at);
CREATE INDEX IF NOT EXISTS obs_source ON observations(source_id);
"""

def _excel_column(index: int) -> str:
    name = ''
    while index:
        index, remainder = divmod(index-1,26)
        name = chr(65+remainder)+name
    return name


def _column_key(value: str) -> str:
    return re.sub(r'[^a-z0-9]+','_',value.lower()).strip('_')


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
        self.measurements = self.root / "measurements"
        self.measurements.mkdir(exist_ok=True, mode=0o700)
        self._partition_integrity = {}
        self.db = self.root / "metadata.sqlite"
        with self.connect() as con:
            con.executescript(DDL)
            if "parquet_sha256" not in {row[1] for row in con.execute("PRAGMA table_info(sheets)")}:
                con.execute("ALTER TABLE sheets ADD COLUMN parquet_sha256 TEXT")
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
        clauses, params = [], []
        for column,value in (("entity_id",entity_id),("source_id",source_id),("name",name),("id",observation_id)):
            if value is not None:
                clauses.append(column+'=?'); params.append(value)
        sql = 'SELECT * FROM observations'
        if clauses:
            sql += ' WHERE '+' AND '.join(clauses)
        sql += ' ORDER BY source_id,id'
        if limit is not None:
            sql += ' LIMIT ? OFFSET ?'; params.extend([limit,offset])
        rows = self.select(sql,params,as_of=as_of,scopes=scopes,observation_id=observation_id)
        for row in rows:
            row['source_ref'] = json.loads(row['source_ref'])
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
            sql += "AND o.available_at IS NOT NULL AND julianday(o.available_at)<=julianday(?)) OR EXISTS "
            sql += "(SELECT 1 FROM sheets p WHERE p.source_id=s.id AND p.observation_count>0 "
            sql += "AND (p.min_available_at IS NULL OR julianday(p.min_available_at)<=julianday(?))))"
            args.extend([as_of,as_of,as_of])
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

    def commit_columnar(self, source_id: str, prepared: dict) -> None:
        """Publish completed partitions and compact metadata in one transaction."""
        with self.connect() as con:
            old_paths = [row[0] for row in con.execute('SELECT parquet_path FROM sheets WHERE source_id=?',(source_id,))]
            con.execute('DELETE FROM sheets WHERE source_id=?',(source_id,))
            con.execute('DELETE FROM source_columns WHERE source_id=?',(source_id,))
            con.execute('DELETE FROM relations WHERE source_id=?',(source_id,))
            for sheet in prepared['sheets']:
                con.execute('INSERT INTO sheets VALUES (?,?,?,?,?,?,?,?,?,?)',
                            (source_id,sheet['sheet_index'],sheet['sheet'],sheet['path'],sheet['row_count'],
                             sheet['row_start'],sheet['observations'],sheet['min_available_at'],json.dumps(sheet['schema']),sheet['parquet_sha256']))
                con.executemany('INSERT INTO source_columns VALUES (?,?,?,?,?)',
                                [(source_id,sheet['sheet'],c['index'],c['name'],c['unit']) for c in sheet['schema']])
            con.executemany('INSERT OR IGNORE INTO entities VALUES (?,?,?,?,?,?)',
                            [(identifier,kind,identifier,0.6,source_id,'candidate inferred from source identifier')
                             for identifier,kind in prepared['entities']])
            con.executemany('INSERT OR REPLACE INTO relations VALUES (?,?,?,?,?,?)',
                            [(left,right,'co_observed',source_id,0.6,available)
                             for left,right,available in prepared['relations']])
        for path in old_paths:
            Path(path).unlink(missing_ok=True)
        for path in self.numerical.glob(f'{source_id}-*.parquet'):
            path.unlink()

    @contextmanager
    def query_connection(self, *, as_of: str | None = None, scopes: Iterable[str] = ('default',),
                         observation_id: str | None = None, numeric_only: bool = False,
                         observation_ids: list[str] | None = None,
                         source_ids: list[str] | None = None, names: list[str] | None = None,
                         sheet: str | None = None, entity_id: str | None = None,
                         source_row: int | None = None):
        """DuckDB sees only authorized sources; external I/O is disabled before yielding."""
        import duckdb
        import pyarrow as pa
        scopes = list(scopes)
        connection = duckdb.connect(':memory:', config={'threads': 2})
        try:
            placeholders = ','.join('?' for _ in scopes) or 'NULL'
            with self.connect() as metadata:
                sources = [dict(row) for row in metadata.execute(
                    f"SELECT * FROM sources WHERE extraction_status='indexed' AND access_scope IN ({placeholders})", scopes)]
                if source_ids is not None:
                    sources = [s for s in sources if s['id'] in set(source_ids)]
                partitions = [dict(row) for row in metadata.execute(
                    f"SELECT p.*,s.path,s.access_scope,s.format FROM sheets p JOIN sources s ON p.source_id=s.id "
                    f"WHERE s.extraction_status='indexed' AND s.access_scope IN ({placeholders})", scopes)]
                partitions = [p for p in partitions if p['source_id'] in {s['id'] for s in sources}
                              and (sheet is None or p['sheet'] == sheet)]
                source_ids = [s['id'] for s in sources]
                marks = ','.join('?' for _ in source_ids) or 'NULL'
                # Legacy/document observations remain supported. New structured rows never enter SQLite.
                legacy_sql = f'SELECT * FROM observations WHERE source_id IN ({marks})'
                legacy_params = list(source_ids)
                for key, value in [('name',names),('entity_id',[entity_id] if entity_id is not None else None)]:
                    if value is not None:
                        legacy_sql += ' AND '+key+' IN ('+(','.join('?' for _ in value) or 'NULL')+')'
                        legacy_params.extend(value)
                if sheet is not None:
                    legacy_sql += " AND json_extract(source_ref,'$.sheet')=?"
                    legacy_params.append(sheet)
                if source_row is not None:
                    legacy_sql += " AND json_extract(source_ref,'$.row')=?"
                    legacy_params.append(source_row)
                requested_ids = observation_ids if observation_ids is not None else ([observation_id] if observation_id else None)
                if requested_ids is not None:
                    legacy_sql += ' AND id IN ('+(','.join('?' for _ in requested_ids) or 'NULL')+')'
                    legacy_params.extend(requested_ids)
                legacy = [dict(row) for row in metadata.execute(legacy_sql,legacy_params)]
            fields = [('id',pa.string()),('source_id',pa.string()),('name',pa.string()),
                      ('value_text',pa.string()),('value_number',pa.float64()),('unit',pa.string()),
                      ('occurred_at',pa.string()),('available_at',pa.string()),('entity_id',pa.string()),
                      ('validation_status',pa.string()),('access_scope',pa.string()),('source_ref',pa.string()),
                      ('extraction_method',pa.string()),('confidence',pa.float64()),
                      ('sheet',pa.string()),('source_row',pa.int64()),('column_index',pa.int32()),
                      ('row_id',pa.string()),('time_value',pa.float64()),('time_basis',pa.string()),
                      ('time_evidence_id',pa.string()),('is_time_axis',pa.bool_())]
            for row in legacy:
                ref = json.loads(row['source_ref'])
                row.update(sheet=ref.get('sheet'),source_row=ref.get('row'),is_time_axis=False,
                           time_basis='unresolved')
            connection.register('_legacy_arrow',pa.Table.from_pylist(legacy,schema=pa.schema(fields)))
            connection.execute('CREATE TEMP TABLE _legacy AS SELECT * FROM _legacy_arrow')
            connection.unregister('_legacy_arrow')
            branches = ['SELECT * FROM _legacy']
            lookups = None
            requested = observation_ids if observation_ids is not None else ([observation_id] if observation_id else None)
            if requested is not None:
                lookups = {}
                for identifier in requested:
                    if identifier.startswith('b1:'):
                        try:
                            _,sid,sheet,row,col = identifier.split(':')
                            lookups.setdefault((sid,int(sheet)),[]).append((int(row),int(col)))
                        except (ValueError,TypeError):
                            pass
            def literal(value):
                return 'NULL' if value is None else "'"+str(value).replace("'","''")+"'"
            for index, part in enumerate(partitions):
                matches = lookups.get((part['source_id'],part['sheet_index']),[]) if lookups is not None else None
                if matches is not None and not matches:
                    continue
                columns = json.loads(part['schema_json'])
                from .time_axis import discover_time_axis
                axis = discover_time_axis(columns)
                if names is not None:
                    columns = [c for c in columns if c['name'] in names]
                if matches is not None:
                    wanted_columns = {col for row,col in matches}
                    columns = [c for c in columns if c['index'] in wanted_columns]
                if not columns:
                    continue
                # Create a lazy relation before locking external access; no complete-table copy.
                alias = f'_sheet_{index}'
                connection.from_parquet(part['parquet_path']).create_view(alias)
                columns_sql = ','.join(c['storage'] for c in columns)
                mapping = ','.join('('+','.join([literal(c['storage']),literal(c['name']),literal(c['unit']),str(c['index']),
                                                 literal(_excel_column(c['index']) if part['sheet'] is not None else None)])+')'
                                   for c in columns)
                base = alias
                if entity_id is not None:
                    base = f'(SELECT * FROM {base} WHERE __entity_id={literal(entity_id)})'
                if source_row is not None:
                    base = f'(SELECT * FROM {base} WHERE __row={int(source_row)})'
                if matches is not None:
                    wanted_rows = ','.join(str(row) for row in sorted({row for row,col in matches}))
                    base = f'(SELECT * FROM {base} WHERE __row IN ({wanted_rows}))'
                prefix = f"b1:{part['source_id']}:{part['sheet_index']}:"
                time_value, time_basis, time_id, is_time = 'NULL::DOUBLE', "'unresolved'", 'NULL::VARCHAR', 'FALSE'
                if axis['status'] == 'source_column':
                    time_column = axis['storage']
                    if axis['kind'] == 'elapsed_hours':
                        raw_time = f'TRY_CAST({time_column} AS DOUBLE)*{axis["factor"]}'
                    else:
                        raw_time = f"CASE WHEN regexp_matches({time_column}, '[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}.*(Z|[+-][0-9]{{2}}:[0-9]{{2}})$') THEN epoch(TRY_CAST({time_column} AS TIMESTAMPTZ))/3600.0 END"
                    base = f'(SELECT *, {raw_time} AS __axis_time FROM {base})'
                    raw_time = '__axis_time'
                    time_available = 'greatest(__available_at,json_extract_string(__field_times,'+literal('/'+axis['name'].replace('~','~0').replace('/','~1'))+'))'
                    time_visible = 'TRUE' if not as_of else f'({time_available} IS NULL OR TRY_CAST({time_available} AS TIMESTAMPTZ)<=TRY_CAST({literal(as_of)} AS TIMESTAMPTZ))'
                    time_value = f'CASE WHEN {time_visible} AND isfinite({raw_time}) THEN {raw_time} END'
                    time_basis = f"CASE WHEN ({time_value}) IS NOT NULL THEN {literal(axis['kind'])} ELSE 'unresolved' END"
                    time_id = f'CASE WHEN ({time_value}) IS NOT NULL THEN {literal(prefix)} || CAST(__row AS VARCHAR) || {literal(":"+str(axis["index"]))} END'
                    is_time = f'c.column_index={axis["index"]}'
                confidence_names = [c['name'] for c in columns if any(k in _column_key(c['name']) for k in ('site','process','campaign','batch','run','reactor','equipment','sample'))]
                confidence = ' OR '.join('c.name='+literal(n) for n in confidence_names) or 'FALSE'
                branches.append(f"""SELECT {literal(prefix)} || CAST(__row AS VARCHAR) || ':' || CAST(c.column_index AS VARCHAR) AS id,
                    {literal(part['source_id'])} AS source_id,c.name,u.value_text,
                    CASE WHEN isfinite(TRY_CAST(u.value_text AS DOUBLE)) THEN TRY_CAST(u.value_text AS DOUBLE) END AS value_number,
                    c.unit,__occurred_at AS occurred_at,
                    greatest(__available_at,json_extract_string(__field_times,'/' || replace(replace(c.name,'~','~0'),'/','~1'))) AS available_at,
                    __entity_id AS entity_id,'source_transcribed' AS validation_status,
                    {literal(part['access_scope'])} AS access_scope,
                    json_object('source_id',{literal(part['source_id'])},'path',{literal(part['path'])},'sheet',{literal(part['sheet'])},
                                'row',__row,'column',c.name,'cell',c.letter || CAST(__row AS VARCHAR),
                                'page',NULL,'span',NULL,'region',NULL) AS source_ref,
                    {literal(part['format'].lstrip('.'))} AS extraction_method,
                    CASE WHEN __entity_kind IS NOT NULL AND ({confidence}) THEN 1.0 END AS confidence,
                    {literal(part['sheet'])} AS sheet,__row::BIGINT AS source_row,c.column_index::INTEGER AS column_index,
                    {literal(prefix)} || CAST(__row AS VARCHAR) AS row_id,
                    {time_value} AS time_value,{time_basis} AS time_basis,{time_id} AS time_evidence_id,
                    {is_time} AS is_time_axis
                    FROM (UNPIVOT {base} ON {columns_sql} INTO NAME column_key VALUE value_text) u
                    JOIN (VALUES {mapping}) c(column_key,name,unit,column_index,letter) USING(column_key)
                    WHERE u.value_text <> ''""")
            connection.execute('CREATE VIEW _all_observations AS '+' UNION ALL '.join(branches))
            # Source-level availability also applies to legacy documents.
            source_map = pa.Table.from_pylist([{'source_id':s['id'],'source_available':s['available_at']} for s in sources],
                                              schema=pa.schema([('source_id',pa.string()),('source_available',pa.string())]))
            connection.register('_source_arrow',source_map)
            connection.execute('CREATE TEMP TABLE _source_visibility AS SELECT * FROM _source_arrow')
            connection.unregister('_source_arrow')
            cutoff = ''
            if as_of:
                quoted = literal(as_of)
                cutoff = (f" WHERE (o.available_at IS NULL OR TRY_CAST(o.available_at AS TIMESTAMPTZ)<=TRY_CAST({quoted} AS TIMESTAMPTZ))"
                          f" AND (s.source_available IS NULL OR TRY_CAST(s.source_available AS TIMESTAMPTZ)<=TRY_CAST({quoted} AS TIMESTAMPTZ))")
            if numeric_only:
                cutoff += (' AND ' if cutoff else ' WHERE ')+'o.value_number IS NOT NULL'
            connection.execute('CREATE VIEW observations AS SELECT o.* FROM _all_observations o JOIN _source_visibility s USING(source_id)'+cutoff)
            connection.execute('SET allowed_paths=?',[[p['parquet_path'] for p in partitions]])
            connection.execute('SET enable_external_access=false')
            connection.execute('SET lock_configuration=true')
            yield connection
        finally:
            connection.close()

    def select(self, sql: str, params=(), *, as_of=None, scopes=('default',), observation_id=None) -> list[dict]:
        with self.query_connection(as_of=as_of,scopes=scopes,observation_id=observation_id) as con:
            cursor = con.execute(sql,params)
            columns = [c[0] for c in cursor.description]
            return [dict(zip(columns,row)) for row in cursor.fetchall()]

    def summarize(self, *, as_of=None, scopes=('default',)) -> list[dict]:
        return self.select('SELECT source_id,entity_id,sheet,name,unit,count(*) AS count,count(value_number) AS numeric_count,'
                           'min(id) AS sample_id,arg_min(id,struct_pack(r:=source_row,i:=id)) AS first_id,'
                           'arg_max(id,struct_pack(r:=source_row,i:=id)) AS last_id,'
                           'arg_min(id,struct_pack(v:=value_number,i:=id)) FILTER (WHERE value_number IS NOT NULL) AS minimum_id,'
                           'arg_max(id,struct_pack(v:=value_number,i:=id)) FILTER (WHERE value_number IS NOT NULL) AS maximum_id,'
                           'min(time_value) AS time_min,max(time_value) AS time_max '
                           'FROM observations GROUP BY source_id,entity_id,sheet,name,unit '
                           'ORDER BY source_id,entity_id,sheet,name,unit',as_of=as_of,scopes=scopes)


    def _get_many_batch(self, identifiers: Iterable[str], *, as_of=None, scopes=('default',)) -> list[dict]:
        identifiers = list(dict.fromkeys(map(str,identifiers)))
        if not identifiers:
            return []
        with self.query_connection(as_of=as_of,scopes=scopes,observation_ids=identifiers) as con:
            cursor = con.execute('SELECT * FROM observations WHERE id IN (SELECT unnest(?))',[identifiers])
            columns = [col[0] for col in cursor.description]
            rows = [dict(zip(columns,row)) for row in cursor.fetchall()]
        for row in rows:
            row['source_ref'] = json.loads(row['source_ref'])
        by_id = {row['id']:row for row in rows}
        return [by_id[i] for i in identifiers if i in by_id]

    def get_many(self, identifiers: Iterable[str], *, as_of=None, scopes=('default',)) -> list[dict]:
        """Bound SQL parameters and intermediate buffers independently of citation count."""
        identifiers = list(dict.fromkeys(map(str,identifiers)))
        rows = []
        for offset in range(0,len(identifiers),512):
            rows.extend(self._get_many_batch(identifiers[offset:offset+512],as_of=as_of,scopes=scopes))
        return rows

    def partition_fingerprints(self, source_ids, *, force=False):
        """Verify indexed data has not changed since the source-backed batch was built."""
        source_ids=list(source_ids)
        fingerprints={sid:[] for sid in source_ids}
        with self.connect() as con:
            for sid in source_ids:
                for row in con.execute('SELECT sheet_index,parquet_path,parquet_sha256 FROM sheets WHERE source_id=? ORDER BY sheet_index',(sid,)):
                    expected=row['parquet_sha256']
                    if not expected:
                        raise ValueError('legacy partitions lack an integrity checksum; re-ingest with the current pipeline')
                    target=Path(row['parquet_path']);stat=target.stat()
                    cache_key=(str(target),stat.st_size,stat.st_mtime_ns,expected)
                    if force or cache_key not in self._partition_integrity:
                        with target.open('rb') as stream:
                            actual=hashlib.file_digest(stream,'sha256').hexdigest()
                        if actual!=expected:raise ValueError('Parquet partition differs from the source-backed ingestion checksum')
                        self._partition_integrity[cache_key]=True
                    fingerprints[sid].append((row['sheet_index'],expected))
        return {sid:hashlib.sha256(json.dumps(parts,separators=(',',':')).encode()).hexdigest()
                for sid,parts in fingerprints.items()}
