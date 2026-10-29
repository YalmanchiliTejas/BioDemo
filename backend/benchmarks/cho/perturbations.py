from __future__ import annotations

import hashlib
import json
from pathlib import Path


from benchmarks.common.artifact_store import uses_assets

ROOT = Path(__file__).resolve().parent


@uses_assets(ROOT / "raw", ROOT / "reference/aligned")
def generate(seed: int = 417) -> dict:
    """Deterministic source-format changes only; biological values are untouched."""
    from openpyxl import load_workbook
    import random
    rng = random.Random(seed)
    original = ROOT / "raw/workbooks/EXP001_batch.xlsx"
    if not original.exists():
        raise FileNotFoundError(original)
    book = load_workbook(original)
    manifest = {"seed": seed, "source": original.name,
                "source_sha256": hashlib.sha256(original.read_bytes()).hexdigest(),
                "label": "synthetic perturbation of authentic measurements",
                "changes": []}
    sheet = book["R01_inline_ProcessParameters"]
    old = sheet.cell(1, 4).value
    sheet.cell(1, 4).value = "Temp [°C]"
    manifest["changes"].append({"type": "column_rename", "sheet": sheet.title, "cell": "D1", "original": old, "new": "Temp [°C]"})
    converted = book["R02_inline_ProcessParameters"]
    converted.cell(1, 4).value = "Temperature (°F)"
    for row in range(2, converted.max_row+1):
        cell = converted.cell(row, 4)
        if isinstance(cell.value, (int, float)):
            cell.value = cell.value*9/5+32
    manifest["changes"].append({"type": "valid_unit_conversion", "sheet": converted.title,
                                "column": "D", "rows": [2, converted.max_row],
                                "from_unit": "°C", "to_unit": "°F", "formula": "F = C * 9/5 + 32"})
    timestamp_sheet = book["R01_online_Feed"]
    for row in range(2, timestamp_sheet.max_row+1):
        cell = timestamp_sheet.cell(row, 1)
        if isinstance(cell.value, (int, float)):
            cell.value = format(cell.value, ".15g")
    manifest["changes"].append({"type": "timestamp_format", "sheet": timestamp_sheet.title,
                                "column": "A", "rows": [2, timestamp_sheet.max_row],
                                "format": "decimal string, 15 significant digits"})
    optional = book["R01_inline_Turbidity"]
    old_status = optional.cell(10, 4).value
    optional.cell(10, 4).value = None
    manifest["changes"].append({"type": "missing_optional_status", "sheet": optional.title,
                                "cell": "D10", "original": old_status})
    secondary = book["R02_offline_MediumAnalysis"]
    duplicate_index = rng.randint(3, min(8, secondary.max_row))
    values = [cell.value for cell in secondary[duplicate_index]]
    secondary.append(values)
    manifest["changes"].append({"type": "duplicate_record", "sheet": secondary.title,
                                "source_row": duplicate_index, "new_row": secondary.max_row})
    distractor = book.create_sheet("Instrument service notes", 0)
    distractor.append(["Note", "This synthetic worksheet contains no cultivation measurements."])
    manifest["changes"].append({"type": "irrelevant_sheet", "sheet": distractor.title})
    reordered = book._sheets.pop(2)
    book._sheets.insert(1, reordered)
    manifest["changes"].append({"type": "sheet_reorder", "sheet": reordered.title, "new_index": 1})
    output = ROOT / "tasks/perturbed/EXP001_batch_perturbed.xlsx"
    output.parent.mkdir(parents=True, exist_ok=True)
    book.save(output)
    manifest["output_sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
    hidden = ROOT / "reference/perturbation_manifest.json"
    hidden.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    print(json.dumps(generate(), indent=2))
