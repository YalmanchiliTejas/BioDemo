"""Author a small, unreviewed measurement-grounded pilot, without altering the app.

The authored runner retains evaluator truth outside its seeded application store.
This script never puts answer_key contents or expected answers into sources.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import time
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
DEMO = ROOT / "backend/benchmarks/cmo_ingestion/demo"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    if path.exists():
        raise FileExistsError(path)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def csv_data(package, name):
    path = DEMO / package / "raw" / name
    with path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    return path, rows


DISCLOSURE = (
    "Public laboratory CHO cultivation measurements attributed by the local dataset "
    "to Zenodo 20829178, DOI 10.5281/zenodo.20829178, CC BY 4.0. "
    "The delivery companies, batch/sample IDs, delivery months, layouts and CoAs are "
    "fictional packaging. The changed delivery contains artificial defects. "
    "This source is a research/demo record, not an approved manufacturing record."
)


def csv_source(key, path):
    return {"key": key, "content": (
        f"{DISCLOSURE}\nSource file: {path.relative_to(ROOT)}\n"
        "The following is the complete CSV, with original header and row order. "
        "Blank fields mean no recorded value; no release specification is supplied.\n"
        + path.read_text()
    )}


def authored(ident, prompt, sources, facts, forbidden, answerable=True):
    return {
        "id": ident, "family": "expert", "review_status": "draft", "reviewer": "",
        "provenance": "AI-authored on 2026-11-14 from existing public CHO measurement CSVs; "
                      "fresh exploratory pilot, not externally held out or expert reviewed. " + DISCLOSURE,
        "prompt": prompt, "sources": sources, "cases": [], "followups": [],
        "truth": {"required_read": [s["key"] for s in sources],
                  "required_facts": facts, "forbidden_claims": forbidden,
                  "banned_tokens": [], "expected_proposals": False,
                  "answerable": answerable},
        "notes": "Private truth is used only by evaluation. Source values are copied verbatim. "
                 "Existing authored runner applies a synthetic wrapper and synthetic=True metadata; "
                 "no verified_dataset status is asserted. Automated same-model scoring is development signal.",
    }


def main():
    fixtures = OUT / "fixtures"
    private = OUT / "private"
    fixtures.mkdir(exist_ok=False)
    private.mkdir(exist_ok=False)
    october, oct_rows = csv_data("cho-returning", "LIMS_offline_results_October.csv")
    november, nov_rows = csv_data("cho-changed", "LIMS_offline_results_November.csv")
    harbor, harbor_rows = csv_data("cho-unseen", "harborview_fedbatch_summary.csv")
    rows_a = [r for r in oct_rows if r["Batch"] == "CHO-004-R01" and r["Time (h)"] in ("19.50", "142.00")]
    assert len(rows_a) == 2
    early, late = rows_a
    glucose_change = Decimal(late["Glucose (g/L)"]) - Decimal(early["Glucose (g/L)"])
    lactate_change = Decimal(late["Lactate (g/L)"]) - Decimal(early["Lactate (g/L)"])
    a = authored(
        "01-returning-glucose-lactate",
        "Using the Northfield October LIMS delivery, compare glucose and lactate for "
        "CHO-004-R01 at 19.50 h and 142.00 h. Give each recorded value with units, "
        "the absolute change (later minus earlier) for each analyte, and cite the "
        "source. Keep the conclusion descriptive; do not infer a root cause or release decision.",
        [csv_source("northfield-october-lims", october)],
        [f"At 19.50 h glucose is {early['Glucose (g/L)']} g/L and lactate is {early['Lactate (g/L)']} g/L.",
         f"At 142.00 h glucose is {late['Glucose (g/L)']} g/L and lactate is {late['Lactate (g/L)']} g/L.",
         f"Glucose change is {glucose_change} g/L (a decrease).",
         f"Lactate change is +{lactate_change} g/L (an increase)."],
        ["A demonstrated root cause is established by these two observations.",
         "The batch is approved for release or the measurements establish release compliance."])

    rows_b = [r for r in harbor_rows if r["Lot"] in ("CHO-012-R01", "CHO-012-R02") and r["EFT (h)"] == "219.00"]
    assert len(rows_b) == 2
    r1, r2 = rows_b
    viability_gap = Decimal(r2["Viability (%)"]) - Decimal(r1["Viability (%)"])
    b = authored(
        "02-unseen-fedbatch-comparison",
        "In the Harborview fed-batch delivery, compare CHO-012-R01 and CHO-012-R02 "
        "at 219.00 h. Report viable cell density, viability, and lactate for each "
        "lot with units. Which lot has the higher viability and by how many percentage "
        "points? Cite the records and keep this as a descriptive comparison.",
        [csv_source("harborview-fedbatch-summary", harbor)],
        [f"CHO-012-R01 at 219.00 h has viable cell density {r1['VCD (cells/mL)']} cells/mL, "
         f"viability {r1['Viability (%)']}%, and lactate {r1['Lactate (g/L)']} g/L.",
         f"CHO-012-R02 at 219.00 h has viable cell density {r2['VCD (cells/mL)']} cells/mL, "
         f"viability {r2['Viability (%)']}%, and lactate {r2['Lactate (g/L)']} g/L.",
         f"CHO-012-R02 viability is higher by {viability_gap} percentage points."],
        ["The two lots are measured at different time points in this comparison.",
         "The comparison establishes process superiority, root cause, or approval for release."])

    conflict_rows = [{"csv_row": i + 2, **r} for i, r in enumerate(nov_rows)
                     if r["Lot"] == "CHO-007-R02" and r["Time (h)"] == "44.00"]
    assert len(conflict_rows) == 2
    x, y = conflict_rows
    c = authored(
        "03-changed-duplicate-conflict",
        "From the Northfield November LIMS delivery, can I use the glucose result "
        "for CHO-007-R02 at 44.00 h as a single confirmed measurement? Report the "
        "relevant sample ID, recorded value or values with units, any evidence issue, "
        "and a suitable review step. Cite the source; do not change or approve any record.",
        [csv_source("northfield-november-lims", november)],
        [f"Sample {x['Sample ID']} for CHO-007-R02 at 44.00 h appears twice with "
         f"glucose {x['Glucose (g/L)']} g/L and {y['Glucose (g/L)']} g/L.",
         "This is a conflicting duplicate for the same sample; the supplied export does not establish which glucose value is authoritative.",
         "A single confirmed glucose value cannot be selected or obtained by silently averaging; reconcile the original laboratory record with the data owner or QC reviewer."],
        ["Either 7.137 g/L or 7.387 g/L is established as the uniquely authoritative glucose result by the supplied export.",
         "The mean 7.262 g/L resolves the duplicate conflict.",
         "The agent approved or changed the laboratory result."], answerable=False)

    raw_dir = DEMO / "cho-changed/raw"
    names = sorted(p.name for p in raw_dir.iterdir() if p.is_file())
    batches = sorted({r["Lot"] for r in nov_rows})
    missing = [batch for batch in batches if f"CoA_{batch}.pdf" not in names]
    assert missing == ["CHO-009-R01"]
    inventory = {"key": "northfield-november-delivery-inventory", "content": (
        DISCLOSURE + "\nComplete file inventory of the received Northfield November "
        "delivery directory, captured before this question. Certificate contents are "
        "not included in this inventory.\n" + "\n".join(names)
    )}
    d = authored(
        "04-changed-missing-certificate",
        "For the Northfield November delivery, compare the lots present in the LIMS "
        "results with the received file inventory. Which lot or lots lack a matching "
        "CoA file? Can the missing certificate be treated as satisfied using only the "
        "available LIMS measurements? Cite both sources and suggest the next evidence "
        "request. Do not release a lot or modify its records.",
        [csv_source("northfield-november-lims", november), inventory],
        ["The November LIMS export contains six distinct lots, CHO-007-R01, CHO-007-R02, CHO-008-R01, CHO-008-R02, CHO-009-R01, and CHO-009-R02.",
         "CHO-009-R01 is the only listed lot without a corresponding CoA_CHO-009-R01.pdf file in the complete received inventory; CHO-009-R02 has its own certificate file.",
         "LIMS measurements do not establish that the missing certificate requirement is satisfied; request the lot-specific certificate from the delivery data owner or QA/CMO contact for review."],
        ["A CoA for CHO-009-R01 is present in the received inventory.",
         "The certificate for CHO-009-R02 also certifies CHO-009-R01.",
         "The missing certificate is satisfied by the available LIMS data alone or the lot is approved for release."], answerable=False)

    cases = [a, b, c, d]
    for case in cases:
        write(fixtures / f"{case['id']}.json", case)

    # Read original evaluation keys only to audit private expected facts/lineage.
    key_receipts = []
    for package, batches_times in [
        ("cho-returning", {("CHO-004-R01", "19.50"), ("CHO-004-R01", "142.00")}),
        ("cho-changed", {("CHO-007-R02", "44.00")}),
        ("cho-unseen", {("CHO-012-R01", "219.00"), ("CHO-012-R02", "219.00")}),
    ]:
        path = DEMO / package / "evaluation/answer_key.json"
        key = json.loads(path.read_text())
        relevant = [f for f in key["fields"] if (f["batch"], f["time"]) in batches_times
                    and f["source"]["path"].endswith(".csv")]
        csv_path = {"cho-returning": october, "cho-changed": november, "cho-unseen": harbor}[package]
        rows = {"cho-returning": oct_rows, "cho-changed": nov_rows, "cho-unseen": harbor_rows}[package]
        for field in relevant:
            source = field["source"]
            raw = rows[source["row"] - 2][source["column"]]
            expected = float(raw) + (273.15 if field["parameter"] == "temperature" else 0) if raw else None
            assert expected == field["value"], (package, field, raw)
        key_receipts.append({"package": package, "private_key_path": str(path.relative_to(ROOT)),
            "private_key_sha256": digest(path), "source": key["source"],
            "selected_field_lineage": relevant, "private_defects": key["defects"],
            "private_transformations": key["transformations"],
            "csv_sha256": digest(csv_path)})
    write(private / "reference-audit.json", {"key_receipts": key_receipts,
        "trend_rows": rows_a, "glucose_change_g_L": str(glucose_change),
        "lactate_change_g_L": str(lactate_change), "comparison_rows": rows_b,
        "viability_difference_percentage_points": str(viability_gap),
        "conflict_rows": conflict_rows, "distinct_november_lots": batches,
        "missing_certificate_lots": missing,
        "inventory": [{"path": n, "sha256": digest(raw_dir / n)} for n in names]})

    from benchmarks.agent_pilot.runner import CampaignBudget, MODEL, RecordedProvider, load_settings
    settings = load_settings()
    provider = RecordedProvider(settings, CampaignBudget(3, 30), "configuration", time.monotonic() + 30)
    provider._check_configuration()
    write(OUT / "pilot-protocol.json", {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "designation": "Exploratory newly authored real-measurement pilot in synthetic application worlds",
        "case_count": len(cases), "expert_reviewed": False, "externally_heldout": False,
        "repeat_count": 1, "workers": 2, "budget_estimate_cap_usd": 3,
        "hard_provider_request_cap": 30, "wall_time_admission_seconds": 900,
        "model": MODEL, "judge_model": MODEL,
        "provider_host": urlparse(provider._base).hostname,
        "credentials_configured": bool(provider._key), "minimum_output_token_ceiling": provider._min_max_tokens,
        "reasoning_effort": provider._reasoning_effort,
        "estimated_token_rates_per_million_usd": {"input": 1.4, "output": 4.4},
        "cost_basis": "Runner-declared conservative token-rate estimate, not verified invoice or a hard dollar guarantee",
        "actual_latency": "Observation timing includes agent inference; result timing adds judge inference; campaign timing is wall clock",
        "private_key_use": "Grading lineage audit only; no private key, truth field or answer summary is seeded into the agent",
        "source_paths_sha256": {str(p.relative_to(ROOT)): digest(p) for p in [october, november, harbor]},
        "fixture_sha256": {p.name: digest(p) for p in sorted(fixtures.glob('*.json'))},
        "limitations": ["AI-authored cases and same-model semantic judge; no independent human expert validation",
            "Real laboratory measurements, invented CMO packaging/IDs/CoAs, artificial duplicate and missing-document defects",
            "Runner retains its generic synthetic source header and metadata; no verified_dataset assertion",
            "Full raw CSVs serialized as searchable text; does not test raw file parsing, deployment, or all workflows",
            "Two cases require uncertainty or missing-evidence handling; four cases are too few for population accuracy",
            "No campaign-level success retries; original failed and ungraded receipts must remain"]})
    print(json.dumps({"fixtures": str(fixtures), "case_ids": [c['id'] for c in cases],
                      "private_reference_audit_passed": True, "configured_model": MODEL}))


if __name__ == "__main__":
    main()
