"""Validate architecture traceability; optionally render Markdown from the CSV.

Run: python3 docs/product/life-sciences-platform/check_plan.py [--render]
This checks plan integrity, not product behavior or customer qualification.
"""

import argparse
import csv
import re
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
FIELDS = [
    "id", "kind", "capability", "source_refs", "module", "phase",
    "foundation_path", "acceptance", "research", "design", "implemented",
    "verified", "implementation_evidence", "verification_evidence",
]
MODULES = ["CORE", "INT", "PROC", "EXEC", "LAB", "QUAL", "SCI", "NET", "COLLAB", "ASSURE", "AGENT"]
STATES = ["research", "design", "implemented", "verified"]


def render(rows):
    def cell(value):
        return value.replace("|", "\\|").replace("\n", " ")

    counts = Counter(row["kind"] for row in rows)
    lines = [
        "# Life-sciences capability checklist", "",
        "Generated from [the canonical CSV](capability-checklist.csv). "
        "Update the CSV, then run `python3 docs/product/life-sciences-platform/check_plan.py --render`.", "",
        "Sources: [official offering inventory](../../research/apprentice-life-sciences-source-inventory.md) "
        "and [code inventory](../../research/life-sciences-codebase-inventory.md). "
        "Design: [architecture](architecture.md), [decisions](decision-log.md), "
        "[model policy](model-routing.md), [delivery and verification](delivery-and-verification.md).", "",
        "## Status and evidence", "",
        f"{len(rows)} tracked items: {counts['capability']} capabilities and {counts['assessment']} assessments. "
        "R = researched/mapped; D = design specified; I = integrated implementation; V = executed verification. "
        "R/D do not imply I/V. Related code and simulation fixtures are foundations only. "
        "Checking I or V requires linked evidence in the CSV. Qualification for a customer's intended use is separate.", "",
        "Source IDs map to the official inventory. USER identifies requested behavior; DESIGN identifies "
        "engineering requirements derived in this proposal. Assessment rows track vendor claims/unknowns "
        "without promising those claims or private implementation parity. Acceptance is conjunctive: all "
        "listed behavior, applicable devices/adapters/methods and shared verification controls must pass; "
        "a single illustrative test does not complete a bundled capability.", "",
    ]
    for module in MODULES:
        lines += [f"## {module}", "",
                  "| ID / kind | Capability | Source | Phase | Existing foundation | Acceptance | R / D / I / V |",
                  "| --- | --- | --- | --- | --- | --- | --- |"]
        for row in rows:
            if row["module"] != module:
                continue
            foundation = row["foundation_path"]
            link = f"[{foundation}](../../../{foundation})" if foundation else "None identified"
            state = " / ".join("[x]" if row[key] == "true" else "[ ]" for key in STATES)
            values = [f"{row['id']} · {row['kind']}", row["capability"], row["source_refs"],
                      row["phase"], link, row["acceptance"], state]
            lines.append("| " + " | ".join(cell(value) for value in values) + " |")
        lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--render", action="store_true")
    args = parser.parse_args()
    with (HERE / "capability-checklist.csv").open(newline="") as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames
        rows = list(reader)
    errors = []
    if headers != FIELDS:
        raise SystemExit(f"Unexpected CSV schema: {headers}")
    inventory = (ROOT / "docs/research/apprentice-life-sciences-source-inventory.md").read_text()
    source_ids = set(re.findall(r"\*\*([A-Z][A-Z0-9]*-?\d{2}) —", inventory))
    referenced = set()
    ids = [row["id"] for row in rows]
    if len(ids) != len(set(ids)) or not rows:
        errors.append("Missing rows or duplicate capability IDs")
    for row in rows:
        label = row["id"]
        if not re.fullmatch(r"LS-\d{3}", label):
            errors.append(f"{label}: invalid ID")
        if row["kind"] not in {"capability", "assessment"}:
            errors.append(f"{label}: invalid kind")
        if row["module"] not in MODULES or row["phase"] not in set("012345"):
            errors.append(f"{label}: invalid module/phase")
        if not row["capability"] or not row["acceptance"]:
            errors.append(f"{label}: missing capability/acceptance")
        refs = set(row["source_refs"].split(";"))
        unknown = refs - source_ids - {"USER", "DESIGN"}
        if unknown:
            errors.append(f"{label}: unknown sources {sorted(unknown)}")
        referenced |= refs & source_ids
        for key in STATES:
            if row[key] not in {"true", "false"}:
                errors.append(f"{label}: {key} must be true/false")
        if row["implemented"] == "true" and not row["implementation_evidence"].strip():
            errors.append(f"{label}: implemented without evidence")
        if row["verified"] == "true" and (row["implemented"] != "true" or not row["verification_evidence"].strip()):
            errors.append(f"{label}: verified without implementation and verification evidence")
        path = row["foundation_path"]
        if path and not (ROOT / path).is_file():
            errors.append(f"{label}: missing foundation {path}")
    if source_ids - referenced:
        errors.append(f"Unmapped source features: {sorted(source_ids - referenced)}")
    if set(MODULES) - {row['module'] for row in rows}:
        errors.append("Some architecture modules have no checklist rows")
    decision_ids = re.findall(r"^\| (D\d{2}) \|", (HERE / "decision-log.md").read_text(), re.M)
    if len(decision_ids) != len(set(decision_ids)) or not decision_ids:
        errors.append("Missing or duplicated decision IDs")
    expected = render(rows)
    if args.render and not errors:
        (HERE / "capability-checklist.md").write_text(expected)
    elif not (HERE / "capability-checklist.md").exists() or (HERE / "capability-checklist.md").read_text() != expected:
        errors.append("Markdown differs from CSV; run with --render")
    files = list(HERE.glob("*.md")) + list((ROOT / "docs/adr").glob("*.md"))
    files += [ROOT / "docs/research" / name for name in (
        "apprentice-life-sciences-source-inventory.md", "life-sciences-codebase-inventory.md",
        "life-sciences-architecture-sources.md")]
    for path in files:
        for target in re.findall(r"\]\(([^)]+)\)", path.read_text()):
            if "://" in target or target.startswith("#"):
                continue
            if not (path.parent / target.split("#")[0]).exists():
                errors.append(f"{path.relative_to(ROOT)}: missing local link {target}")
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"PASS: {len(rows)} items; {len(source_ids)} source features mapped; {len(decision_ids)} decisions; local links and status evidence checks valid.")
    print("Statuses: " + ", ".join(f"{key}={sum(row[key] == 'true' for row in rows)}" for key in STATES))
    print("This validates documentation integrity, not feature functionality or qualification.")


if __name__ == "__main__":
    main()
