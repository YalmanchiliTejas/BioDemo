"""Scoped retrieval over schema metadata, bounded Parquet projections and text indexes.

No model calls, evaluator references, or raw numeric-cell full-text indexing.
"""
from __future__ import annotations
import hashlib
import json
import re
import sqlite3
import threading
import time
import resource
import sys
from pathlib import Path

from .terminology import canonical, normalize, query_matches

VERSION = 'retrieval-v2-stable-source-order'
# These are categorical/identifier metadata, not narrative prose. They remain
# available through exact metric/entity/sheet retrieval and query_data.
METADATA = {'status', 'batch id', 'lot id', 'run id', 'reactor id', 'equipment id',
            'sample id', 'entity id', 'available at', 'occurred at', 'field available at'}

class RetrievalEngine:
    def __init__(self, store):
        self.store = store
        self.path = store.root / 'retrieval.sqlite'
        self.lock = threading.RLock()
        self._model = None
        self._schema_cache = {}
        with self.connect() as con:
            con.executescript('''
            CREATE TABLE IF NOT EXISTS versions(source_id TEXT PRIMARY KEY, signature TEXT);
            CREATE TABLE IF NOT EXISTS documents(
                id TEXT PRIMARY KEY, source_id TEXT, scope TEXT, available_at TEXT,
                source_available TEXT, entity_id TEXT, name TEXT, text TEXT, content_hash TEXT);
            CREATE INDEX IF NOT EXISTS documents_scope ON documents(scope,source_id,entity_id);
            CREATE VIRTUAL TABLE IF NOT EXISTS text_fts USING fts5(id UNINDEXED,name,text);
            CREATE TABLE IF NOT EXISTS embeddings(
                id TEXT, model TEXT, content_hash TEXT, vector BLOB, PRIMARY KEY(id,model));
            ''')
            con.execute('BEGIN IMMEDIATE')
            if 'source_path' not in {r[1] for r in con.execute('PRAGMA table_info(documents)')}:
                con.execute('ALTER TABLE documents ADD COLUMN source_path TEXT')
        self.path.chmod(0o600)

    def connect(self):
        con = sqlite3.connect(self.path, timeout=60)
        con.row_factory = sqlite3.Row
        return con

    def schema(self, scopes, as_of=None):
        stat=self.store.db.stat()
        key=(tuple(sorted(scopes)),as_of,stat.st_mtime_ns,stat.st_size)
        if key in self._schema_cache:
            return self._schema_cache[key]
        sources = self.store.visible_sources(scopes=scopes, as_of=as_of)
        output = []
        with self.store.connect() as con:
            for s in sources:
                for p in con.execute('SELECT * FROM sheets WHERE source_id=? ORDER BY sheet_index', (s['id'],)):
                    for c in json.loads(p['schema_json']):
                        output.append({**c, **canonical(c['name'], c['unit']),
                                       'source_id':s['id'], 'sheet':p['sheet']})
                # Legacy files have column metadata as well.
                if not con.execute('SELECT 1 FROM sheets WHERE source_id=?', (s['id'],)).fetchone():
                    for c in con.execute('SELECT * FROM source_columns WHERE source_id=? ORDER BY column_index', (s['id'],)):
                        output.append({**dict(c), **canonical(c['name'], c['unit'])})
        if len(self._schema_cache)>=16:self._schema_cache.clear()
        self._schema_cache[key]=(sources,output)
        return sources, output

    def sync_text(self, scopes):
        """Incremental, source-versioned text index; stored rows are gated at query time.

        Numeric-native columns and categorical metadata never enter this index.
        Mixed/string columns retain nonnumeric prose, even if other rows are numeric.
        """
        sources, schema = self.schema(scopes)
        with self.lock, self.connect() as idx, self.store.connect() as metadata:
            for source in sources:
                sid = source['id']
                parts = [dict(p) for p in metadata.execute('SELECT * FROM sheets WHERE source_id=? ORDER BY sheet_index', (sid,))]
                legacy = [tuple(r) for r in metadata.execute(
                    'SELECT id,name,value_text,available_at,entity_id,access_scope FROM observations '
                    'WHERE source_id=? AND value_number IS NULL ORDER BY id', (sid,))]
                dep = [(p['schema_json'], p['parquet_sha256'], Path(p['parquet_path']).stat().st_mtime_ns,
                        Path(p['parquet_path']).stat().st_size) for p in parts]
                signature = hashlib.sha256(json.dumps([VERSION, source['sha256'], source['pipeline_version'],
                                                       source['available_at'], source['access_scope'], dep, legacy]).encode()).hexdigest()
                old = idx.execute('SELECT signature FROM versions WHERE source_id=?', (sid,)).fetchone()
                if old and old[0] == signature:
                    continue
                names = sorted({c['name'] for c in schema if c['source_id'] == sid
                                and c.get('source_dtype','String') in ('String','Null')
                                and normalize(c['name']) not in METADATA
                                and not re.fullmatch(r'(time|timestamp|date)( (h|hr|hours|min|s|days?))?',normalize(c['name']))})
                names = sorted(set(names) | {r[1] for r in legacy if normalize(r[1]) not in METADATA})
                # An empty projection (as in CHO) avoids opening any Parquet files.
                rows = []
                if names:
                    with self.store.query_connection(scopes=scopes, source_ids=[sid], names=names) as db:
                        cursor = db.execute("SELECT id,source_id,access_scope,available_at,entity_id,name,value_text FROM observations "
                                            "WHERE value_number IS NULL AND length(trim(value_text))>0 ORDER BY id")
                        rows = cursor.fetchall()
                idx.execute('DELETE FROM text_fts WHERE id IN (SELECT id FROM documents WHERE source_id=?)', (sid,))
                idx.execute('DELETE FROM documents WHERE source_id=?', (sid,))
                for identifier, source_id, scope, available, entity, name, text in rows:
                    digest = hashlib.sha256(text.encode()).hexdigest()
                    idx.execute('INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?,?)',
                                (identifier,source_id,scope,available,source['available_at'],entity,name,text,digest,source['path']))
                    idx.execute('INSERT INTO text_fts VALUES (?,?,?)', (identifier,name,text))
                idx.execute('INSERT OR REPLACE INTO versions VALUES (?,?)', (sid,signature))
                idx.execute('DELETE FROM embeddings WHERE id NOT IN (SELECT id FROM documents)')

    @staticmethod
    def text_gate(req, sources):
        clauses = ['d.scope IN (' + (','.join('?' for _ in req.scopes) or 'NULL') + ')',
                   'd.source_id IN (' + (','.join('?' for _ in sources) or 'NULL') + ')']
        params = [*req.scopes, *sources]
        for key,value in [('source_id',req.source_id), ('entity_id',req.entity_id), ('name',req.metric)]:
            if value is not None:
                clauses.append('d.'+key+'=?');params.append(value)
        if req.as_of:
            for key in ['available_at','source_available']:
                clauses.append(f'(d.{key} IS NULL OR julianday(d.{key})<=julianday(?))');params.append(req.as_of)
        return ' AND '.join(clauses), params

    def text_search(self, req, sources):
        start=time.perf_counter()
        self.sync_text(req.scopes)
        indexed=time.perf_counter()
        diagnostics={'index_sync_seconds':indexed-start}
        gate, params = self.text_gate(req, sources)
        terms = re.findall(r'\w+',req.query)
        if not terms:
            return [], 'fts5_bm25', diagnostics
        match = ' OR '.join('"'+t.replace('"','""')+'"' for t in terms)
        with self.connect() as con:
            if req.max_hits_per_source is not None:
                lexical = con.execute('WITH ranked AS MATERIALIZED ('
                    'SELECT d.id,d.source_id,d.source_path,bm25(text_fts,0,2,1) AS score FROM text_fts '
                    'JOIN documents d ON d.id=text_fts.id WHERE text_fts MATCH ? AND '+gate+
                    '), diverse AS (SELECT *,row_number() OVER (PARTITION BY source_id ORDER BY score,id) AS ordinal FROM ranked) '
                    'SELECT id,score FROM diverse WHERE ordinal<=? ORDER BY score,source_path,id LIMIT ? OFFSET ?',
                    [match,*params,req.max_hits_per_source,req.limit,req.offset]).fetchall()
            else:
                lexical = con.execute('SELECT d.id,bm25(text_fts,0,2,1) AS score FROM text_fts '
                                  'JOIN documents d ON d.id=text_fts.id WHERE text_fts MATCH ? AND '+gate+
                                  ' ORDER BY score,d.source_path,d.id LIMIT ? OFFSET ?',
                                  [match,*params,req.limit,req.offset]).fetchall()
            if req.mode == 'lexical':
                diagnostics['ranking_seconds']=time.perf_counter()-indexed
                return [r['id'] for r in lexical], 'fts5_bm25', diagnostics
            # Embeddings are computed only for authorized text. The content hash
            # invalidates changed chunks without re-embedding unchanged records.
            docs = con.execute('SELECT d.* FROM documents d WHERE '+gate+' ORDER BY d.id',params).fetchall()
            if not docs:
                return [], 'semantic_local_persisted', diagnostics
            import numpy as np
            if self._model is None:
                try:
                    from fastembed import TextEmbedding
                except ImportError as exc:
                    raise RuntimeError('Install the existing semantic extra for semantic/hybrid text retrieval') from exc
                self._model = TextEmbedding(model_name='BAAI/bge-small-en-v1.5')
            model = 'BAAI/bge-small-en-v1.5'
            vectors = {}
            missing = []
            for d in docs:
                old = con.execute('SELECT content_hash,vector FROM embeddings WHERE id=? AND model=?',(d['id'],model)).fetchone()
                if old and old['content_hash']==d['content_hash']:
                    vectors[d['id']] = np.frombuffer(old['vector'],dtype=np.float32)
                else:
                    missing.append(d)
            new_vectors=self._model.embed([d['text'] for d in missing]) if missing else ()
            for d,vector in zip(missing,new_vectors):
                vector = np.asarray(vector,dtype=np.float32)
                con.execute('INSERT OR REPLACE INTO embeddings VALUES (?,?,?,?)',
                            (d['id'],model,d['content_hash'],vector.tobytes()))
                vectors[d['id']] = vector
            q = np.asarray(next(iter(self._model.embed([req.query]))),dtype=np.float32)
            diagnostics.update(embedding_candidates=len(docs),embeddings_reused=len(docs)-len(missing),
                               embeddings_created=len(missing))
            ranked = sorted(vectors, key=lambda i: (-float(q@vectors[i]) / max(float(np.linalg.norm(q)*np.linalg.norm(vectors[i])),1e-12),i))
            if req.mode == 'hybrid':
                # Reciprocal-rank fusion; deterministic ties; no score mixing.
                lex = con.execute('SELECT d.id FROM text_fts JOIN documents d ON d.id=text_fts.id '
                                  'WHERE text_fts MATCH ? AND '+gate+' ORDER BY bm25(text_fts,0,2,1),d.source_path,d.id', [match,*params]).fetchall()
                scores = {}
                for ids in ([r['id'] for r in lex],ranked):
                    for rank,identifier in enumerate(ids,1):scores[identifier]=scores.get(identifier,0)+1/(60+rank)
                ranked = sorted(scores,key=lambda i:(-scores[i],i))
            diagnostics['ranking_seconds']=time.perf_counter()-indexed
            return ranked[req.offset:req.offset+req.limit], 'hybrid_rrf' if req.mode=='hybrid' else 'semantic_local_persisted', diagnostics

    def search(self, req):
        start = time.perf_counter()
        cpu_start=time.process_time()
        diagnostics={}
        sources, schema = self.schema(req.scopes, req.as_of)
        source_ids = [s['id'] for s in sources if req.source_id is None or s['id']==req.source_id]
        route = req.evidence_type
        exact = req.observation_id or (req.query if req.query.startswith('b1:') else None)
        metric = req.metric
        matches = sorted({c['name'] for c in schema if query_matches(req.query,c['name'],c['unit'])})
        entity = req.entity_id
        if req.source_id is None and req.query in source_ids:
            source_ids=[req.query]
        with self.store.connect() as con:
            if exact is None and con.execute('SELECT 1 FROM observations WHERE id=? AND source_id IN ('+
                           (','.join('?' for _ in source_ids) or 'NULL')+')', [req.query,*source_ids]).fetchone():
                exact=req.query
            if entity is None and con.execute('SELECT 1 FROM entities WHERE id=? AND source_id IN ('+
                           (','.join('?' for _ in source_ids) or 'NULL')+')', [req.query,*source_ids]).fetchone():
                entity = req.query
        if route == 'auto':
            route = 'exact' if exact else ('structured' if metric or matches or entity or req.sheet or req.source_id or req.query in source_ids else 'narrative')
            if req.mode != 'lexical':route = 'narrative'
        if req.mode != 'lexical' and route != 'narrative':
            raise ValueError('semantic/hybrid modes require narrative evidence')
        setup_done = time.perf_counter()
        if route == 'exact':
            rows = self.store.get_many([exact or req.query],as_of=req.as_of,scopes=req.scopes)
            rows = [r for r in rows if r['source_id'] in source_ids
                    and (entity is None or r['entity_id']==entity)
                    and (metric is None or r['name']==metric)
                    and (req.value_text is None or r['value_text']==req.value_text)
                    and (req.sheet is None or r.get('sheet')==req.sheet)
                    and (req.source_row is None or r.get('source_row')==req.source_row)
                    and (req.time_basis is None or r.get('time_basis')==req.time_basis)
                    and (req.time_min is None or r.get('time_value') is not None and r['time_value']>=req.time_min)
                    and (req.time_max is None or r.get('time_value') is not None and r['time_value']<=req.time_max)]
            method = 'exact_id'
        elif route == 'narrative':
            if req.sheet is not None or req.source_row is not None or req.time_min is not None or req.time_max is not None or req.time_basis is not None or req.value_text is not None:
                raise ValueError('sheet/time filters require evidence_type="structured"')
            ids,method,diagnostics = self.text_search(req,source_ids)
            resolve=time.perf_counter()
            rows = self.store.get_many(ids,as_of=req.as_of,scopes=req.scopes)
            ranked_rows = {r['id']: r for r in rows}
            rows = [ranked_rows[identifier] for identifier in ids if identifier in ranked_rows]
            diagnostics['evidence_resolution_seconds']=time.perf_counter()-resolve
        else:
            names = None
            if metric:
                names = sorted({c['name'] for c in schema if c['name']==metric or query_matches(metric,c['name'],c['unit'])})
                # Legacy metadata may be absent; exact original metric remains valid.
                if not names:names=[metric]
            elif matches:names=matches
            if not names and not entity and not req.sheet and not req.source_id and req.query not in source_ids:
                raise ValueError('structured retrieval requires a metric, entity_id, source_id or sheet filter')
            with self.store.query_connection(as_of=req.as_of,scopes=req.scopes,source_ids=source_ids,
                                              names=names,sheet=req.sheet,entity_id=entity,source_row=req.source_row) as con:
                connected=time.perf_counter()
                diagnostics['database_setup_seconds']=connected-setup_done
                predicates=[];params=[]
                if req.value_text is not None:
                    predicates.append('value_text=?');params.append(req.value_text)
                for bound, op in [(req.time_min,'>='),(req.time_max,'<=')]:
                    if bound is not None:
                        predicates.append('time_value'+op+'?');params.append(bound)
                if req.time_basis:
                    predicates.append('time_basis=?');params.append(req.time_basis)
                sql = 'SELECT * FROM observations'+(' WHERE '+' AND '.join(predicates) if predicates else '')
                sql += " ORDER BY json_extract_string(source_ref,'$.path'),entity_id,sheet,source_row,column_index,id LIMIT ? OFFSET ?"
                cursor=con.execute(sql,[*params,req.limit,req.offset])
                executed=time.perf_counter()
                columns=[c[0] for c in cursor.description]
                rows=[dict(zip(columns,r)) for r in cursor.fetchall()]
                for r in rows:r['source_ref']=json.loads(r['source_ref'])
                diagnostics.update(database_execute_seconds=executed-connected,
                                   database_materialize_seconds=time.perf_counter()-executed)
            method='structured_filtered'
        end=time.perf_counter()
        ids=list(dict.fromkeys(r['id'] for r in rows))
        # A time claim must be able to cite the actual associated clock cell.
        evidence=list(dict.fromkeys([*ids,*[r['time_evidence_id'] for r in rows if r.get('time_evidence_id')]]))
        return {'records':rows,'evidence_ids':evidence,'search_method':method,'retrieval_route':route,
                'truncated_input':False,'ranking':'source/coordinate order' if route!='narrative' else method,
                'diagnostics':{**diagnostics,'route':route,'method':method,
                               'schema_seconds':setup_done-start,'retrieval_seconds':end-setup_done,
                               'total_seconds':end-start,'result_count':len(rows),
                               'cpu_seconds':time.process_time()-cpu_start,
                               'peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024),
                               'source_candidates':len(source_ids),'metric_candidates':len(matches),
                               'rows_scanned':None,'rows_scanned_status':'available in offline DuckDB profiling only'}}
