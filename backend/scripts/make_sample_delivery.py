"""Write a small SYNTHETIC CMO delivery whose files share identifiers, for testing by hand:
ingestion, cross-file links (batch <-> equipment <-> lot <-> deviation) and the assistant building on context.

    python scripts/make_sample_delivery.py /tmp/sample-delivery          # month 1
    python scripts/make_sample_delivery.py /tmp/sample-delivery-2 --month 2

Month 2 reuses equipment BR-07 and lot L-8812 with a new batch, so links and reviews from month 1 can be compared.
Nothing here is real data; every file says so.
"""
from __future__ import annotations

import argparse
import csv
from email.message import EmailMessage
from pathlib import Path

from openpyxl import Workbook

from benchmarks.cmo_ingestion.generate import write_pdf

NOTE = 'SYNTHETIC test data - not a real batch'


def month_one(out: Path) -> None:
    book = Workbook(); sheet = book.active; sheet.title = 'Process'
    sheet.append(['batch_id', 'equipment_id', 'material_lot_id', 'elapsed_h', 'temperature [degC]', 'pH [pH]', 'DO [%]'])
    for h, (t, ph, do) in enumerate([(36.8, 7.02, 61), (36.9, 7.00, 55), (37.0, 6.98, 44), (37.1, 6.95, 33), (37.4, 6.91, 24), (37.2, 6.93, 29)]):
        sheet.append(['B-2024-117', 'BR-07', 'L-8812', h, t, ph, do])
    book.save(out/'batch_record_B-2024-117.xlsx')
    with (out/'batch_record_B-2024-118.csv').open('w', newline='') as f:
        w = csv.writer(f); w.writerow(['batch_id', 'equipment_id', 'material_lot_id', 'elapsed_h', 'temperature [degC]', 'pH [pH]', 'DO [%]'])
        for h, (t, ph, do) in enumerate([(36.7, 7.01, 63), (36.8, 7.00, 58), (36.9, 6.99, 52)]):
            w.writerow(['B-2024-118', 'BR-05', 'L-8812', h, t, ph, do])
    with (out/'deviations.csv').open('w', newline='') as f:
        w = csv.writer(f); w.writerow(['deviation_id', 'batch_id', 'equipment_id', 'occurred_at', 'description'])
        # Batch written without dashes on purpose: the link layer should propose B2024117 = B-2024-117.
        w.writerow(['DEV-31', 'B2024117', 'BR-07', '2024-11-03T04:10:00+00:00', f'Foaming at 4 h, DO fell below 30%; antifoam added manually. {NOTE}'])
    with (out/'lot_master.csv').open('w', newline='') as f:
        w = csv.writer(f); w.writerow(['material_lot_id', 'material_id', 'supplier', 'status'])
        w.writerow(['L-8812', 'AF-204', 'Example Supplier (synthetic)', 'released'])
    write_pdf(out/'coa_L-8812.pdf', ['Certificate of Analysis', NOTE, 'Lot: L-8812', 'Material: AF-204 antifoam emulsion',
                                     'Silicone content: 29.6 % (spec 28-32 %)', 'Released: 2024-10-20'])
    mail = EmailMessage(); mail['From'] = 'qa@cmo.example'; mail['To'] = 'you@example.test'
    mail['Subject'] = 'Batch B-2024-117 deviation DEV-31'; mail['Date'] = 'Mon, 04 Nov 2024 09:00:00 +0000'
    mail.set_content(f'Hi,\nDEV-31 opened for B-2024-117 on BR-07: foaming at 4 h. Antifoam lot L-8812 was in use.\n'
                     f'Root cause not established yet.\n{NOTE}\n')
    (out/'email_DEV-31.eml').write_bytes(bytes(mail))


def month_two(out: Path) -> None:
    with (out/'batch_record_B-2024-131.csv').open('w', newline='') as f:
        w = csv.writer(f); w.writerow(['batch_id', 'equipment_id', 'material_lot_id', 'elapsed_h', 'temperature [degC]', 'pH [pH]', 'DO [%]'])
        for h, (t, ph, do) in enumerate([(36.8, 7.01, 60), (37.0, 6.99, 47), (37.3, 6.94, 31), (37.5, 6.90, 22)]):
            w.writerow(['B-2024-131', 'BR-07', 'L-8812', h, t, ph, do])
    with (out/'deviations.csv').open('w', newline='') as f:
        w = csv.writer(f); w.writerow(['deviation_id', 'batch_id', 'equipment_id', 'occurred_at', 'description'])
        w.writerow(['DEV-38', 'B-2024-131', 'BR-07', '2024-12-02T03:00:00+00:00', f'Foaming at 3 h; DO below 30%. {NOTE}'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('folder', type=Path)
    parser.add_argument('--month', type=int, choices=(1, 2), default=1)
    args = parser.parse_args()
    args.folder.mkdir(parents=True, exist_ok=False)
    (month_one if args.month == 1 else month_two)(args.folder)
    print('\n'.join(sorted(p.name for p in args.folder.iterdir())))
