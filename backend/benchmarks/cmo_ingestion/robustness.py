"""Mutation robustness of CMO delivery ingestion under an already-confirmed template.

A clean delivery with known truth is ingested and its templates confirmed. Each
named mutation then corrupts a copy the way real exports get corrupted and is
re-ingested by the same CMO. The danger case is a wrong value auto-accepted
under a confirmed mapping. Deterministic, local, no network, no model calls.

Run from backend: .venv/bin/python -m benchmarks.cmo_ingestion.robustness --output DIR
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import shutil
import sys
import tempfile
import traceback
import zipfile
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook, load_workbook

from src.manufacturing_data.cmo import quality
from src.manufacturing_data.cmo.pipeline import IngestionService
from src.manufacturing_data.cmo.schema import normalize

CMO = 'robustness-cmo'
HEADERS = ['Lot', 'Elapsed time (h)', 'Temperature (°C)', 'pH', 'DO (mg/L)']
UNITS = {'temperature': '°C', 'pH': None, 'dissolved_oxygen': 'mg/L'}
PARAMS = ['temperature', 'pH', 'dissolved_oxygen']  # column order after Lot/time
ACCEPTED = {'auto_accepted', 'accepted', 'corrected'}
CSV, XLSX = 'export_L1.csv', 'export_L2.xlsx'


def base_rows(lot, offset):
    return [[lot, t, round(37 + offset + t / 10, 3), round(7.0 + t / 100, 3), round(6.5 - t / 10, 3)] for t in range(4)]


def tkey(time):
    try:
        return float(time)
    except (TypeError, ValueError):
        return str(time)


def truth_for(rows):
    out = {}
    for lot, t, *values in rows:
        for param, raw in zip(PARAMS, values):
            out[(lot, tkey(t), param)] = normalize(str(raw), UNITS[param], param)[0]
    return out


# --- file helpers ---------------------------------------------------------------
def write_csv(path, rows, headers=HEADERS):
    with path.open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(headers)
        w.writerows(rows)


def read_csv(path):
    with path.open(newline='', encoding='utf-8') as f:
        return list(csv.reader(f))


def write_xlsx(path, rows, headers=HEADERS, sheet='Process'):
    book = Workbook()
    ws = book.active
    ws.title = sheet
    ws.append(headers)
    for row in rows:
        ws.append(row)
    book.save(path)


def read_xlsx(path):
    ws = load_workbook(path).active
    return [list(r) for r in ws.iter_rows(values_only=True)]


def edit_csv(raw, fn):
    rows = read_csv(raw / CSV)
    fn(rows)
    with (raw / CSV).open('w', newline='', encoding='utf-8') as f:
        csv.writer(f, lineterminator='\n').writerows(rows)


def edit_xlsx(raw, fn):
    rows = read_xlsx(raw / XLSX)
    fn(rows)
    write_xlsx(raw / XLSX, rows[1:], headers=rows[0])


def write_base(raw):
    raw.mkdir(parents=True)
    l1, l2 = base_rows('L-1', 0), base_rows('L-2', 0.5)
    write_csv(raw / CSV, l1)
    write_xlsx(raw / XLSX, l2)
    return truth_for(l1 + l2)


# --- mutations ------------------------------------------------------------------
# Each takes the copied raw dir and returns (package_path, truth_overrides).
# Overrides map a truth key to its new canonical value, or None to drop it.
def m_crlf(raw):
    p = raw / CSV
    p.write_bytes(p.read_bytes().replace(b'\n', b'\r\n'))
    return raw, {}


def m_bom(raw):
    p = raw / CSV
    p.write_bytes(b'\xef\xbb\xbf' + p.read_bytes())
    return raw, {}


def m_latin1(raw):
    p = raw / CSV
    p.write_bytes(p.read_text(encoding='utf-8').encode('latin-1'))
    return raw, {}


def m_whitespace(raw):
    edit_csv(raw, lambda rows: [r.__setitem__(i, f'  {v} ') for r in rows[1:] for i, v in enumerate(r) if i >= 1])
    return raw, {}


def m_reorder(raw):
    edit_csv(raw, lambda rows: [r.__setitem__(slice(3, 5), [r[4], r[3]]) for r in rows])
    return raw, {}


def m_blank_rows(raw):
    edit_csv(raw, lambda rows: rows.insert(2, []) or rows.insert(4, ['', '', '', '', '']))
    return raw, {}


def m_header_case(raw):
    edit_csv(raw, lambda rows: rows.__setitem__(0, [h.upper() for h in rows[0]]))
    return raw, {}


def m_comma_decimal(raw):
    edit_csv(raw, lambda rows: rows[2].__setitem__(2, rows[2][2].replace('.', ',')))
    return raw, {}  # European decimal: the true value is unchanged (37.1 °C)


def m_thousands(raw):
    edit_csv(raw, lambda rows: rows[3].__setitem__(4, '1,234'))
    return raw, {('L-1', 2.0, 'dissolved_oxygen'): 1234.0}


def m_scientific(raw):
    edit_csv(raw, lambda rows: rows[1].__setitem__(2, '3.7e1'))
    return raw, {}


def m_unicode_minus(raw):
    edit_csv(raw, lambda rows: rows[1].__setitem__(2, '−5'))
    return raw, {('L-1', 0.0, 'temperature'): normalize('-5', '°C', 'temperature')[0]}


def m_placeholders(raw):
    def fn(rows):
        rows[1][3], rows[2][3], rows[3][4] = 'N/A', 'ND', '<0.1'
    edit_csv(raw, fn)
    return raw, {('L-1', 0.0, 'pH'): None, ('L-1', 1.0, 'pH'): None, ('L-1', 2.0, 'dissolved_oxygen'): None}


def m_fahrenheit_converted(raw):
    def fn(rows):
        rows[0][2] = 'Temperature (°F)'
        for r in rows[1:]:
            r[2] = str(round(float(r[2]) * 9 / 5 + 32, 4))
    edit_csv(raw, fn)
    return raw, {}  # canonical K unchanged; correct conversion or review are both safe


def m_fahrenheit_mislabeled(raw):
    edit_csv(raw, lambda rows: rows[0].__setitem__(2, 'Temperature (°F)'))
    return raw, {}  # values are still °C; the true value is the °C reading


def m_conflicting_duplicate(raw):
    def fn(rows):
        dup = list(rows[2])
        dup[2] = '45.0'
        rows.insert(3, dup)
    edit_csv(raw, fn)
    return raw, {}  # the original reading is truth; 45.0 must not be accepted


def m_truncated_row(raw):
    edit_csv(raw, lambda rows: rows.__setitem__(2, rows[2][:3]))
    return raw, {('L-1', 1.0, 'pH'): None, ('L-1', 1.0, 'dissolved_oxygen'): None}


def m_extra_cells(raw):
    edit_csv(raw, lambda rows: [r.extend(['9.99', 'stray']) for r in rows[1:]])
    return raw, {}


def m_empty_csv(raw):
    (raw / CSV).write_bytes(b'')
    return raw, {k: None for k in truth_for(base_rows('L-1', 0))}


def m_zero_byte_xlsx(raw):
    (raw / XLSX).write_bytes(b'')
    return raw, {k: None for k in truth_for(base_rows('L-2', .5))}


def m_corrupt_xlsx(raw):
    p = raw / XLSX
    p.write_bytes(p.read_bytes()[: p.stat().st_size // 2])
    return raw, {k: None for k in truth_for(base_rows('L-2', .5))}


def m_csv_as_xlsx(raw):
    (raw / CSV).rename(raw / 'export_L1.xlsx')
    return raw, {}


def m_excel_serial_time(raw):
    def fn(rows):
        for i, r in enumerate(rows[1:]):
            r[1] = datetime(2026, 10, 1, i)
    edit_xlsx(raw, fn)
    return raw, {}  # elapsed hours replaced by wall clock: truth keys must be flagged if not found


def m_nested_folder(raw):
    sub = raw / 'site' / 'batch records'
    sub.mkdir(parents=True)
    (raw / CSV).rename(sub / CSV)
    return raw, {}


def m_zip_traversal(raw):
    package = raw.parent / 'delivery.zip'
    with zipfile.ZipFile(package, 'w') as z:
        for p in sorted(raw.iterdir()):
            z.write(p, p.name)
        z.writestr('../evil.csv', 'Lot,Elapsed time (h),pH\nL-9,0,1.0\n')
    return package, {k: None for k in truth_for(base_rows('L-1', 0) + base_rows('L-2', .5))}


def m_zip_clean(raw):
    package = raw.parent / 'delivery.zip'
    with zipfile.ZipFile(package, 'w') as z:
        for p in sorted(raw.iterdir()):
            z.write(p, p.name)
    return package, {}


def m_huge_cell(raw):
    edit_csv(raw, lambda rows: rows[2].__setitem__(3, 'x' * 1_000_000))
    return raw, {('L-1', 1.0, 'pH'): None}


# name -> (function, expected behaviour, detectable). Undetectable mutations
# are recorded but excluded from the gate: no parser can tell °C from a °F label.
MUTATIONS = {
    'crlf_line_endings': (m_crlf, 'same values', True),
    'utf8_bom': (m_bom, 'same values', True),
    'latin1_encoding': (m_latin1, 'same values or flagged', True),
    'whitespace_padded_cells': (m_whitespace, 'same values', True),
    'column_reorder': (m_reorder, 'same values or review', True),
    'blank_rows_inserted': (m_blank_rows, 'same values', True),
    'header_case_change': (m_header_case, 'same values or review', True),
    'comma_decimal': (m_comma_decimal, '37,1 read as 37.1 or flagged', True),
    'thousands_separator': (m_thousands, '1,234 read as 1234 or flagged, never 1.234', True),
    'scientific_notation': (m_scientific, '3.7e1 read as 37', True),
    'unicode_minus': (m_unicode_minus, '−5 read as -5 or flagged', True),
    'placeholders_na_nd_lt': (m_placeholders, 'N/A, ND, <0.1 flagged, never a number', True),
    'fahrenheit_converted': (m_fahrenheit_converted, 'converted correctly or review', True),
    'fahrenheit_label_celsius_values': (m_fahrenheit_mislabeled, 'undetectable from data; recorded only', False),
    'conflicting_duplicate_row': (m_conflicting_duplicate, 'conflict flagged, 45.0 never accepted', True),
    'truncated_row': (m_truncated_row, 'missing cells flagged', True),
    'extra_trailing_cells': (m_extra_cells, 'stray cells flagged, values unchanged', True),
    'empty_csv': (m_empty_csv, 'file flagged', True),
    'zero_byte_xlsx': (m_zero_byte_xlsx, 'file flagged', True),
    'corrupt_xlsx': (m_corrupt_xlsx, 'parse error flagged', True),
    'csv_saved_as_xlsx': (m_csv_as_xlsx, 'parsed or flagged', True),
    'excel_datetime_in_elapsed_hours': (m_excel_serial_time, 'flagged, not silently reinterpreted', True),
    'nested_folder': (m_nested_folder, 'same values', True),
    'zip_package': (m_zip_clean, 'same values', True),
    'zip_path_traversal': (m_zip_traversal, 'package rejected explicitly, nothing written outside', True),
    'huge_cell': (m_huge_cell, 'cell flagged', True),
}


# --- harness ----------------------------------------------------------------------
def primed_service(root):
    """A service whose CMO has confirmed the clean delivery's templates."""
    service = IngestionService(root / 'store')
    raw = root / 'base'
    truth = write_base(raw)
    run = service.run(raw, CMO, 'D')
    if run['status'] != 'complete':
        raise RuntimeError(f'clean base failed: {run.get("error")}')
    for layout in run['layouts']:
        service.confirm_template(run['id'], layout['fingerprint'], layout['mapping'], 'robustness-qa', 'Checked against clean base')
    clean = service.run(raw, CMO, 'D')
    if not clean['summary']['verified_package']:
        raise RuntimeError('clean base is not auto-verified after confirmation')
    return service, raw, truth


def mutated(raw, name, workdir):
    target = workdir / name / 'delivery'
    target.parent.mkdir(parents=True)
    shutil.copytree(raw, target)
    package, overrides = MUTATIONS[name][0](target)
    return package, overrides


def signature(run):
    return sorted((m['batch'], str(tkey(m['time'])), m['parameter'], None if m['value'] is None else round(m['value'], 9), m['status'])
                  for m in run.get('measurements', []))


def evaluate_mutation(name, service, raw, truth, workdir):
    fn, expected, detectable = MUTATIONS[name]
    row = {'mutation': name, 'expected': expected, 'gated': detectable, 'checks': {}}
    checks = row['checks']
    try:
        package, overrides = mutated(raw, name, workdir)
        expected_truth = {**truth, **overrides}
        expected_truth = {k: v for k, v in expected_truth.items() if v is not None}
        dropped = {k for k, v in overrides.items() if v is None}
        run = service.run(package, CMO, 'D')
    except Exception as exc:
        checks['no_crash'] = {'passed': False, 'detail': f'{type(exc).__name__}: {exc}', 'trace': traceback.format_exc(limit=3)}
        return row
    status = run.get('status')
    explicit = status == 'complete' or (status in {'failed', 'unavailable'} and (run.get('error') or run.get('unavailable_reasons')))
    checks['no_crash'] = {'passed': bool(explicit), 'detail': f'status={status} error={run.get("error")}'}
    # Usability, not safety: one bad file or cell should not fail the whole delivery.
    if name != 'zip_path_traversal':
        checks['delivery_survives'] = {'passed': status == 'complete', 'detail': run.get('error')}
    measures = run.get('measurements', [])

    wrong = []
    for m in measures:
        key = (m['batch'], tkey(m['time']), m['parameter'])
        if m['status'] in ACCEPTED and key in truth:
            want = expected_truth.get(key)
            if want is None or m['value'] is None or not math.isclose(m['value'], want, rel_tol=1e-6):
                wrong.append({'key': list(key), 'accepted': m['value'], 'truth': want, 'raw': m.get('value_raw'),
                              'status': m['status'], 'source': m['source'].get('path')})
    checks['no_silent_wrong_value'] = {'passed': not wrong, 'detail': wrong[:5]}

    if status == 'complete':
        g = quality.guarantee(run)
        checks['guarantee_holds'] = {'passed': g['holds'], 'detail': [c['id'] for c in g['checks'] if not c['passed']]}
    else:
        checks['guarantee_holds'] = {'passed': True, 'detail': 'run did not complete; nothing was accepted'}

    present = {(m['batch'], tkey(m['time']), m['parameter']) for m in measures}
    # A value queued for review with a reason is visible even if its time key changed.
    in_review = {(m['batch'], m['parameter']) for m in measures if m['status'] == 'needs_review' and m.get('rule_codes')}
    flagged_paths = {i.get('path') for i in run.get('issues', []) if i.get('status') == 'open'}
    unaccounted = (run.get('coverage') or {}).get('unaccounted')
    silent = []
    if status == 'complete':
        for key in truth:
            if key in present or (key[0], key[2]) in in_review:
                continue
            # A missing value is visible when some open issue covers the delivery.
            if not flagged_paths:
                silent.append(list(key))
        if unaccounted:
            silent.append(f'{unaccounted} unaccounted elements')
    checks['no_silent_omission'] = {'passed': not silent, 'detail': silent[:5],
                                    'expected_drops': len(dropped)}

    try:
        sigs = []
        for i in range(2):
            fresh = workdir / name / f'fresh{i}'
            s2, raw2, _ = primed_service(fresh)
            p2, _ = mutated(raw2, name, fresh / 'mut')
            sigs.append(signature(s2.run(p2, CMO, 'D')))
        checks['deterministic'] = {'passed': sigs[0] == sigs[1] == signature(run), 'detail': None}
    except Exception as exc:
        checks['deterministic'] = {'passed': False, 'detail': f'{type(exc).__name__}: {exc}'}

    if name == 'zip_path_traversal':
        escaped = (workdir / name / 'evil.csv').exists() or (workdir / 'evil.csv').exists() or any(
            p.name == 'evil.csv' for p in Path(service.root).rglob('*'))
        rejected = status != 'complete' or any('unsafe' in json.dumps(i).lower() for i in run.get('issues', []))
        checks['zip_safety'] = {'passed': not escaped and rejected, 'detail': f'escaped={escaped} rejected={rejected}'}

    row['counts'] = {
        'status': status,
        'auto_accepted': sum(m['status'] == 'auto_accepted' for m in measures),
        'needs_review': sum(m['status'] == 'needs_review' for m in measures),
        'flagged': (run.get('coverage') or {}).get('flagged'),
        'open_issues': sum(i.get('status') == 'open' for i in run.get('issues', [])),
        'issue_codes': sorted({i['rule_code'] for i in run.get('issues', [])}),
    }
    return row


def run_harness(workdir, names=None):
    workdir = Path(workdir)
    service, raw, truth = primed_service(workdir / 'primary')
    rows = [evaluate_mutation(n, service, raw, truth, workdir / 'mutations') for n in (names or MUTATIONS)]
    gate = [r['mutation'] for r in rows if r['gated'] and not all(
        r['checks'].get(c, {}).get('passed', True) for c in ('no_crash', 'no_silent_wrong_value'))]
    return {'scope': 'CMO pipeline config D under a confirmed template; synthetic delivery; local only. '
                     'Does not establish correctness of any real CMO format or document extraction.',
            'truth_values': len(truth), 'mutations': rows, 'gate_failures': gate}


CHECKS = ('no_crash', 'no_silent_wrong_value', 'guarantee_holds', 'no_silent_omission', 'deterministic', 'zip_safety', 'delivery_survives')


def markdown(report):
    mark = lambda r, c: '' if c not in r['checks'] else ('pass' if r['checks'][c]['passed'] else '**FAIL**')
    lines = ['# CMO ingestion robustness', '', report['scope'], '',
             '| Mutation | Expected | ' + ' | '.join(CHECKS) + ' | auto | review | flagged | issues |',
             '|' + '---|' * (len(CHECKS) + 6)]
    for r in report['mutations']:
        c = r.get('counts', {})
        name = r['mutation'] + ('' if r['gated'] else ' (ungated)')
        lines.append(f"| {name} | {r['expected']} | " + ' | '.join(mark(r, k) for k in CHECKS) +
                     f" | {c.get('auto_accepted', '')} | {c.get('needs_review', '')} | {c.get('flagged', '')} | {', '.join(c.get('issue_codes', []))} |")
    lines += ['', f"Gate failures (crash or silent wrong value): {report['gate_failures'] or 'none'}"]
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory() as tmp:
        report = run_harness(tmp)
    (args.output / 'report.json').write_text(json.dumps(report, indent=2, default=str) + '\n')
    (args.output / 'report.md').write_text(markdown(report))
    print(markdown(report))
    sys.exit(1 if report['gate_failures'] else 0)


if __name__ == '__main__':
    main()
