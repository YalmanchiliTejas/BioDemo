"""Excerpts of an original file for a reviewer: the rows around a cited cell, or the opening of a document.

Read straight from the stored original (already checked against its hash by the caller), never from
extracted values, so what is shown is what was delivered. Sizes are bounded; nothing here writes.
"""
from __future__ import annotations

import csv
from pathlib import Path

TABLES = {'.xlsx', '.xlsm', '.csv', '.tsv'}
TEXTS = {'.txt', '.log', '.docx', '.json'}
IMAGES = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.tif': 'image/tiff', '.tiff': 'image/tiff'}
MAX_AROUND = 25
MAX_COLUMNS = 80
MAX_CELL = 200
MAX_TEXT = 6000


def _cell(value):
    if value is None: return None
    text = str(value)
    return text if len(text) <= MAX_CELL else text[:MAX_CELL] + '…'


def _window(row, around):
    """Data rows to return: centred on ``row`` when one is cited, otherwise the first rows. Row 1 is the header."""
    around = max(0, min(int(around), MAX_AROUND))
    if row is None: return 2, 2 + 2 * around
    if row < 1: raise ValueError('Row outside the file')
    return max(2, row - around), row + around


def table_rows(path: Path, *, sheet=None, row=None, around=5):
    """Header and a window of rows from a spreadsheet or delimited file, exactly as stored."""
    suffix = path.suffix.lower()
    first, last = _window(row, around)
    result = {'row': row, 'sheet': None, 'sheets': [], 'sheet_assumed': False}
    if suffix in {'.xlsx', '.xlsm'}:
        from openpyxl import load_workbook
        book = load_workbook(path, read_only=True, data_only=False)
        try:
            names = book.sheetnames
            if sheet is not None and sheet not in names: raise KeyError('Unknown sheet')
            # A location recorded without its sheet can only be shown on a guess; say so.
            result.update(sheets=names, sheet=sheet or names[0], sheet_assumed=sheet is None and len(names) > 1)
            page = book[result['sheet']]
            headers = [c.value for c in next(page.iter_rows(min_row=1, max_row=1), [])]
            rows = [{'row': n, 'values': [_cell(c.value) for c in cells][:MAX_COLUMNS]}
                    for n, cells in enumerate(page.iter_rows(min_row=first, max_row=last), first)]
            total = page.max_row
        finally:
            book.close()
    elif suffix in {'.csv', '.tsv'}:
        with path.open(newline='', encoding='utf-8-sig', errors='replace') as stream:
            reader = csv.reader(stream, delimiter='\t' if suffix == '.tsv' else ',')
            headers = next(reader, [])
            rows, total = [], 1
            for n, values in enumerate(reader, 2):
                total = n
                if first <= n <= last: rows.append({'row': n, 'values': [_cell(v) for v in values][:MAX_COLUMNS]})
    else:
        raise ValueError('This file is not a table')
    return {**result, 'headers': [_cell(h) for h in headers][:MAX_COLUMNS], 'rows': rows, 'total_rows': total,
            'columns_truncated': len(headers) > MAX_COLUMNS}


def preview(path: Path):
    """What kind of thing a file is and enough of it to recognise it: opening rows, opening text, or a page count."""
    suffix = path.suffix.lower()
    if suffix in TABLES: return {'kind': 'table', **table_rows(path, around=4)}
    if suffix == '.pdf':
        import pypdfium2
        pdf = pypdfium2.PdfDocument(str(path))
        try: return {'kind': 'pdf', 'pages': len(pdf)}
        finally: pdf.close()
    if suffix in IMAGES: return {'kind': 'image'}
    if suffix in TEXTS:
        from .intake import document_text
        text = document_text(path) if suffix != '.json' else None
        if text is None: text = path.read_bytes()[:MAX_TEXT * 4].decode('utf-8', errors='replace')
        return {'kind': 'text', 'text': text[:MAX_TEXT], 'truncated': len(text) > MAX_TEXT}
    return {'kind': 'none'}
