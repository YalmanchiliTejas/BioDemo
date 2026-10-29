"""Bulk structured ingestion. Workers write Arrow batches, never cell objects or SQL rows."""
from __future__ import annotations

import json
import hashlib
import time
import uuid
import zipfile
import posixpath
from xml.etree import ElementTree
from pathlib import Path

import polars as pl
import pyarrow.parquet as pq


def _text(expr: pl.Expr, dtype=None) -> pl.Expr:
    if isinstance(dtype,pl.Datetime):
        suffix='%:z' if dtype.time_zone else ''
        return expr.dt.strftime('%Y-%m-%d %H:%M:%S%.f'+suffix)
    text=expr.cast(pl.String, strict=False)
    return text.str.replace(r'\.0$','') if dtype in (pl.Float32,pl.Float64) else text


def _dates(frame: pl.DataFrame, column: str) -> pl.Expr:
    # Parse distinct strings once; numerical process hours are not calendar dates.
    from .ingest import _iso
    values = frame[column].drop_nulls().unique().to_list()
    return pl.col(column).replace_strict({v: _iso(v) for v in values}, default=None,
                                         return_dtype=pl.String)


def _preserve_mixed_numbers(path: Path, sheet_name: str, frame: pl.DataFrame) -> pl.DataFrame:
    """Calamine's string coercion rounds numeric cells; retain their original XML
    values in mixed text/numeric columns without coercing actual text identifiers.
    Pure numeric columns use native floating-point Arrow values directly.
    """
    candidates={i:frame[name].cast(pl.String).to_list() for i,name in enumerate(frame.columns)
                if frame.schema[name]==pl.String and frame[name].cast(pl.Float64,strict=False).is_not_null().any()}
    if not candidates:return frame
    ns={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
        'r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
    with zipfile.ZipFile(path) as archive:
        date_styles=set()
        if 'xl/styles.xml' in archive.namelist():
            from openpyxl.styles.numbers import BUILTIN_FORMATS,is_date_format
            styles=ElementTree.fromstring(archive.read('xl/styles.xml'))
            formats=dict(BUILTIN_FORMATS)
            for item in styles.findall('m:numFmts/m:numFmt',ns):formats[int(item.attrib['numFmtId'])]=item.attrib['formatCode']
            for index,item in enumerate(styles.findall('m:cellXfs/m:xf',ns)):
                if is_date_format(formats.get(int(item.attrib.get('numFmtId',0)),'')):date_styles.add(index)
        workbook=ElementTree.fromstring(archive.read('xl/workbook.xml'))
        sheet=next(s for s in workbook.find('m:sheets',ns) if s.attrib['name']==sheet_name)
        relationship=sheet.attrib['{'+ns['r']+'}id']
        rels=ElementTree.fromstring(archive.read('xl/_rels/workbook.xml.rels'))
        target=next(r.attrib['Target'] for r in rels if r.attrib['Id']==relationship)
        target=target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/'+target)
        with archive.open(target) as stream:
            for _,element in ElementTree.iterparse(stream,events=('end',)):
                tag=element.tag.rsplit('}',1)[-1]
                if tag=='c':
                    coordinate=element.attrib.get('r','')
                    letters=''.join(c for c in coordinate if c.isalpha())
                    digits=''.join(c for c in coordinate if c.isdigit())
                    column=0
                    for char in letters:column=column*26+ord(char.upper())-64
                    index=int(digits)-2 if digits else -1
                    if column-1 in candidates and 0<=index<frame.height and element.attrib.get('t','n')=='n' and int(element.attrib.get('s',0)) not in date_styles:
                        value=element.find('m:v',ns)
                        if value is not None and value.text is not None:candidates[column-1][index]=value.text
                    element.clear()
                elif tag=='row':element.clear()
    return frame.with_columns([pl.Series(frame.columns[index],values,dtype=pl.String) for index,values in candidates.items()])


def read_sheets(path: Path, max_rows: int | None):
    """Retain physical rows/columns, including blanks, for exact source coordinates."""
    if path.suffix.lower() in {".xlsx", ".xlsm"}:
        import fastexcel
        reader = fastexcel.read_excel(path)
        for name in reader.sheet_names:
            sheet = reader.load_sheet(name, header_row=0, schema_sample_rows=None, n_rows=max_rows,
                                      skip_whitespace_tail_rows=False, whitespace_as_null=False)
            frame = _preserve_mixed_numbers(path,name,sheet.to_polars())
            # Read the actual header cells: generated/deduplicated engine names are not provenance.
            header = reader.load_sheet(name, header_row=None, skip_rows=0, n_rows=1,
                                       dtypes="string").to_polars()
            headers = [str(v) if v is not None else f"column_{i}"
                       for i, v in enumerate(header.row(0) if header.height else [], 1)]
            if len(headers) != frame.width:
                raise ValueError(f"sheet {name!r}: header/data column count differs")
            yield name, headers, frame, 2
    elif path.suffix.lower() in {".csv", ".tsv"}:
        import csv
        separator = '\t' if path.suffix.lower() == '.tsv' else ','
        with path.open(encoding='utf-8-sig', newline='') as stream:
            headers = next(csv.reader(stream, delimiter=separator), [])
        if not headers:
            return
        frame = pl.read_csv(path, separator=separator, has_header=True, infer_schema=False,
                            n_rows=max_rows, encoding='utf8-lossy',
                            new_columns=[f"v{i}" for i in range(1, len(headers)+1)])
        yield None, headers, frame, 2
    elif path.suffix.lower() == '.json':
        records = json.loads(path.read_text(encoding='utf-8'), parse_float=str, parse_int=str)
        if max_rows is not None: records = records[:max_rows]
        # Preserve scalar values in the existing wide-table representation.
        frame = pl.from_dicts(records, infer_schema_length=None, strict=False)
        yield None, frame.columns, frame, 1
    else:
        frame = pl.read_parquet(path, n_rows=max_rows)
        yield None, frame.columns, frame, 1


def prepare_source(source_id: str, rel: str, path: Path, scope: str,
                   available: str | None, output: Path, max_rows: int | None) -> dict:
    from .ingest import _key, _unit, _entity_from_context, _related_entities, ENTITY_WORDS, AVAIL_WORDS, TIME_WORDS
    started = time.monotonic()
    generation = uuid.uuid4().hex
    sheets, entities, relations = [], set(), set()
    files = []
    try:
        for sheet_index, (sheet, headers, raw, row_start) in enumerate(read_sheets(path, max_rows)):
            if len(set(headers)) != len(headers):
                raise ValueError(f"sheet {sheet!r}: duplicate headers require explicit disambiguation")
            columns = [f"v{i}" for i in range(1, len(headers)+1)]
            raw.columns = columns
            frame = raw.select([_text(pl.col(c),raw.schema[c]).alias(c) for c in columns]).with_row_index('__row', offset=row_start)
            fallback_kind, fallback_id = _entity_from_context(rel, sheet, {})
            id_expr, kind_expr = pl.lit(fallback_id, dtype=pl.String), pl.lit(fallback_kind, dtype=pl.String)
            entity_columns = []
            for header, column in zip(headers, columns):
                key = _key(header)
                kind = next((kind for marker,kind in ENTITY_WORDS.items()
                             if marker in key and (key.endswith('id') or key == marker or key.endswith('number'))), None)
                if kind:
                    entity_columns.append((kind, column))
            for kind, column in reversed(entity_columns):
                valid = pl.col(column).is_not_null() & (pl.col(column).str.strip_chars() != '')
                id_expr = pl.when(valid).then(pl.col(column).str.strip_chars()).otherwise(id_expr)
                kind_expr = pl.when(valid).then(pl.lit(kind)).otherwise(kind_expr)
            occurred, published = pl.lit(None, dtype=pl.String), pl.lit(None, dtype=pl.String)
            for header, column in zip(headers, columns):
                key = _key(header)
                if any(word in key for word in AVAIL_WORDS):
                    published = pl.coalesce(_dates(frame, column), published)
                elif any(word in key for word in TIME_WORDS):
                    occurred = pl.coalesce(_dates(frame, column), occurred)
            field_column = next((c for h,c in zip(headers,columns) if _key(h)=='field_available_at'), None)
            field_times = pl.lit(None, dtype=pl.String)
            if field_column:
                # Validate/normalize sparse per-field publication maps once per distinct map.
                from .ingest import _iso
                maps = {}
                for value in frame[field_column].drop_nulls().unique():
                    try:
                        parsed = json.loads(value)
                        maps[value] = json.dumps({k: _iso(v) for k,v in parsed.items()}) if isinstance(parsed,dict) else None
                    except (ValueError, TypeError):
                        maps[value] = None
                field_times = pl.col(field_column).replace_strict(maps, default=None, return_dtype=pl.String)
            frame = frame.with_columns(id_expr.alias('__entity_id'), kind_expr.alias('__entity_kind'),
                                       occurred.alias('__occurred_at'), pl.coalesce(published, pl.lit(available)).cast(pl.String).alias('__available_at'),
                                       field_times.alias('__field_times'))
            for kind, identifier in frame.select('__entity_kind','__entity_id').unique().iter_rows():
                if kind and identifier:
                    entities.add((identifier, kind))
            related = [(kind, pl.col(c).str.strip_chars()) for kind,c in entity_columns]
            related += [(kind, pl.lit(identifier)) for kind,identifier in _related_entities(rel,sheet,{})]
            for kind, expr in related:
                links = frame.select(pl.col('__entity_id').alias('left'), expr.alias('right'), pl.col('__available_at').alias('available')).filter(
                    pl.col('right').is_not_null() & (pl.col('right') != '')).unique()
                for identifier in links['right'].unique():
                    entities.add((identifier, kind))
                # Compact relationships: retain earliest availability for each pair.
                for left, right, when in links.group_by('left','right').agg(pl.col('available').min()).iter_rows():
                    if left and left != right:
                        relations.add((left,right,when))
            schema = []
            for i, (header, column) in enumerate(zip(headers,columns),1):
                series = frame[column]
                populated = series.is_not_null() & (series != '')
                numeric = series.cast(pl.Float64, strict=False)
                schema.append({'index':i,'name':header,'storage':column,'unit':_unit(header),
                               'source_dtype':str(raw.schema[column]),'observations':int(populated.sum()),
                               'numeric':bool(numeric.is_finite().fill_null(False).any())})
            target = output / f'{source_id}-{generation}-{sheet_index:04d}.parquet'
            files.append(target)
            arrow = frame.to_arrow()
            with pq.ParquetWriter(target, arrow.schema, compression='zstd') as writer:
                for batch in arrow.to_batches(max_chunksize=65536):
                    writer.write_batch(batch)
            target.chmod(0o600)
            with target.open('rb') as stream:
                partition_sha256=hashlib.file_digest(stream,'sha256').hexdigest()
            minimum = frame['__available_at'].drop_nulls().min()
            sheets.append({'sheet_index':sheet_index,'sheet':sheet,'path':str(target),'row_count':frame.height,
                           'row_start':row_start,'schema':schema,'min_available_at':minimum,'parquet_sha256':partition_sha256,
                           'observations':sum(c['observations'] for c in schema)})
        return {'sheets':sheets,'entities':sorted(entities),'relations':list(relations),
                'observations':sum(s['observations'] for s in sheets),
                'seconds':round(time.monotonic()-started,3)}
    except BaseException:
        for target in files:
            target.unlink(missing_ok=True)
        raise
