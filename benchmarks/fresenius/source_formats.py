from __future__ import annotations

import random
from collections import defaultdict
from io import BytesIO
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


SCAN_SEED = 417


def add_scanned_lab_report(output: Path, rows: list[dict], mapping: list[dict]) -> tuple[Path, int]:
    """Image-only duplicate lab export; every printed row maps to a canonical record."""
    from PIL import Image, ImageDraw, ImageFont

    path = output / "laboratory" / "scanned_lab_review.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(path), pagesize=letter, invariant=1)
    font = ImageFont.load_default(size=22)
    rng = random.Random(SCAN_SEED)
    per_page = 20
    for offset in range(0, len(rows), per_page):
        page = offset // per_page + 1
        image = Image.new("RGB", (1600, 2200), "white")
        draw = ImageDraw.Draw(image)
        draw.text((90, 90), "SYNTHETIC FACTORY RECORDS - scanned lab review", fill="black", font=font)
        draw.text((90, 145), "Duplicate review export; observations come from the canonical simulation.",
                  fill="black", font=font)
        for position, row in enumerate(rows[offset:offset+per_page]):
            y = 240 + position * 88
            identifier = row["_evidence_id"]
            batch = row.get("batch_id") or ""
            value = row.get("numerical_result")
            unit = row.get("unit") or ""
            line = f"{identifier} | {batch} | {row.get('available_at', '')} | {value if value is not None else ''} {unit}"
            draw.text((90, y), line, fill="black", font=font)
            draw.line((90, y+48, 1500, y+48), fill=(180, 180, 180), width=1)
            mapping.append({"source_file": str(path.relative_to(output)), "page": page,
                            "section": "scanned lab review", "image_region": [34, 792-(y+55)*792/2200,
                                                                          575, 792-(y-5)*792/2200],
                            "source_span": line, "canonical_record_id": identifier,
                            "canonical_field": "summary"})
        # Fixed, sparse scan artifacts outside the text area.
        for _ in range(50):
            x = rng.choice([rng.randrange(10, 65), rng.randrange(1535, 1590)])
            draw.point((x, rng.randrange(10, 2180)), fill=(210, 210, 210))
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        buffer.seek(0)
        pdf.drawImage(ImageReader(buffer), 0, 0, width=612, height=792)
        pdf.showPage()
    pdf.save()
    return path, len(rows)


def add_discrete_process_charts(output: Path, rows: list[dict], mapping: list[dict]) -> tuple[Path, int]:
    """Plot existing process-summary events as points, never interpolated trajectories."""
    path = output / "manufacturing" / "process_event_points.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if isinstance(row.get("value"), (int, float)):
            grouped[str(row.get("parameter") or "unspecified")].append(row)
    pdf = canvas.Canvas(str(path), pagesize=letter, invariant=1)
    page = 0
    for parameter in sorted(grouped):
        ordered = sorted(grouped[parameter], key=lambda row: (row.get("timestamp", ""), row["_evidence_id"]))
        for offset in range(0, len(ordered), 25):
            page += 1
            chunk = ordered[offset:offset+25]
            pdf.setFont("Helvetica-Bold", 10)
            pdf.drawString(38, 752, "SYNTHETIC FACTORY RECORDS - discrete process events")
            pdf.setFont("Helvetica", 8)
            pdf.drawString(38, 734, f"Parameter: {parameter}; page {page}")
            pdf.drawString(38, 720, "Each point is one recorded event. No continuous trajectory is inferred.")
            low = min(float(row["value"]) for row in chunk)
            high = max(float(row["value"]) for row in chunk)
            span = high-low or 1.0
            pdf.line(55, 360, 575, 360)
            pdf.line(55, 360, 55, 680)
            for index, row in enumerate(chunk):
                x = 65 + index * 500/max(1, len(chunk)-1)
                y = 370 + (float(row["value"])-low)/span*300
                pdf.circle(x, y, 2.5, stroke=1, fill=0)
                table_y = 340-index*11
                line = f"{row['_evidence_id']}  {row.get('batch_id', '')}  {row.get('timestamp', '')}  {row['value']}"
                pdf.setFont("Helvetica", 6)
                pdf.drawString(55, table_y, line[:115])
                mapping.append({"source_file": str(path.relative_to(output)), "page": page,
                                "section": "discrete event chart", "point_region": [x-3, y-3, x+3, y+3],
                                "source_span": line, "canonical_record_id": row["_evidence_id"],
                                "canonical_field": "value"})
            pdf.showPage()
    pdf.save()
    return path, sum(len(group) for group in grouped.values())
