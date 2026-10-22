"""Chart data from recorded task scores and reviewed human-effort ledgers."""
from __future__ import annotations

from benchmarks.common.human_work import PHASES
from benchmarks.common.case_report import summarize_runs

GATES = ("authorized_evidence_only", "no_future_leakage", "material_citations_verifiable", "original_measurements_unchanged", "no_autonomous_gmp_action", "no_unsupported_verified_cause")


def build_evaluation(store, case_id: str, experiments: dict, ledger: dict) -> dict:
    import json
    summary_path = store.repository / "results/evaluation/summary.json"
    summary = json.loads(summary_path.read_text()) if summary_path.exists() else summarize_runs([])
    primary = summary["cohorts"][case_id]["raw"]
    effort, outcomes = [], []
    for mode, label in (("manual", "Manual engineer"), ("full_rlm", "Manufacturing OS")):
        group = primary["effort"]["groups"][mode]
        effort.append({"label": label, "phases": [
            {"phase": phase, "minutes": group["phases_hours"][phase] * 60 if group["phases_hours"][phase] is not None else None}
            for phase in PHASES], "manual_steps": None, "hours": group["total_human_hours_all_attempts"]})
        outcomes.append({"label": label, "accepted": group["qualified_cases"] if group["quality_qualified_rate"] is not None else None,
                         "assigned": group["attempted_cases"], "rate": group["quality_qualified_rate"],
                         "hours_per_qualified": group["human_hours_per_qualified_case"], "status": group["effort_per_qualified_status"],
                         "gate_failures": None})
    charts = []
    if case_id == "fresenius":
        for field, title, definition in (
            ("cited_critical_lab_recall", "Critical signals cited", "Fraction of visible critical lab signals cited in each task. Missing signals reduce this score."),
            ("analysis_citation_precision", "Citations resolve to available records", "Checks record identity and availability at the cutoff; does not verify the meaning of the claim."),
        ):
            series = []
            for key, label in (("fresenius_parser", "Extraction baseline"), ("fresenius_retrieval", "Retrieval + LLM")):
                tasks = (store.get(key) or {}).get("tasks", [])
                series.append({"label": label, "values": [{"label": t["task"]["id"], "value": t.get("metrics", {}).get(field)} for t in tasks]})
            charts.append({"title": title, "definition": definition, "series": series,
                           "sources": [store.source("fresenius_parser"), store.source("fresenius_retrieval")]})
        qualification = "Legacy retrieval + LLM diagnostic on one synthetic case; these are not Prime OS scores. The extraction baseline produces no investigation citations. Root-cause correctness and claim support need separate domain review."
    else:
        tasks = (store.get("cho_parser") or {}).get("tasks", [])
        by_id = {t["task"]["id"]: t.get("metrics", {}) for t in tasks}
        first, second = by_id.get("CHO-01", {}), by_id.get("CHO-02", {})
        for title, value, definition in (
            ("Inoculation-time agreement", first.get("time_zero_match_fraction"),
             f'{first.get("time_zero_matches", "—")} / {first.get("time_zero_values_checked", "—")} comparable values match; {first.get("time_zero_unavailable_values", "—")} unavailable values reported separately.'),
            ("Full trajectory agreement", second.get("full_series_within_tolerance_fraction"),
             f'{second.get("full_series_within_tolerance", "—")} / {second.get("full_series_comparable_values", "—")} values within tolerance; {second.get("full_series_missing_reconstruction_values", "—")} missing reconstruction values. Tolerance: {second.get("full_series_tolerance", "not recorded")}.'),
        ):
            charts.append({"title": title, "definition": definition,
                           "series": [{"label": "Conventional reconstruction", "values": [{"label": "Recorded run", "value": value}]},
                                      {"label": "Prime OS", "values": [{"label": "Recorded run", "value": None}]}],
                           "sources": [store.source("cho_parser")]})
        qualification = "Agreement with publication-aligned evaluation references measures reconstruction, not biological interpretation. CHO investigation quality and OS productivity have not been scored."
    case_charts = []
    for family, field, title in (
        ("data_preparation", "field_accuracy", "Raw-source field correctness"),
        ("data_preparation", "field_coverage", "Frozen field-check coverage"),
        ("evidence", "critical_evidence_recall", "Critical evidence recall"),
        ("evidence", "citation_location_validity", "Original source locations verified"),
    ):
        series = []
        for mode in ("conventional", "retrieval_llm", "full_rlm"):
            values = []
            for run in primary["runs"]:
                if run["mode"] != mode or not run.get("objective_scores"):
                    continue
                result = run["objective_scores"][family][field]
                values.append({"label": f'{run["case_id"]} / {run["run_id"][:6]}', "value": result["value"], "status": result["status"]})
            if values:
                series.append({"label": primary["effort"]["groups"][mode]["label"], "values": values})
        if series:
            case_charts.append({"title": title, "definition": "Audited v2 case output. Accuracy uses emitted comparable values; coverage reports missing checks separately. Citation checks require original files and locations, not IDs alone.",
                                "series": series, "sources": [{"path": "results/evaluation/summary.json"}]})
    previews = []
    if case_id == "cho":
        for workbook in (store.get("cho_inventory") or {}).get("workbooks", []):
            if workbook.get("experiment") not in {"001", "008"}:
                continue
            sheets = workbook.get("sheets", [])
            for sheet in sheets[::max(1, len(sheets) // 3)][:3]:
                previews.append({"file": workbook["file"], "sheet": sheet["name"],
                                 "rows": sheet.get("rows_observed"), "columns": sheet.get("columns", []),
                                 "preview": sheet.get("first_rows", [])[:6]})
    return {"effort": effort, "outcomes": outcomes, "paired": primary["comparison"]["status"] == "observed", "charts": charts, "case_charts": case_charts, "source_previews": previews,
            "gates": list(GATES), "qualification": qualification,
            "ledger_source": "results/evaluation/summary.json", "comparison": primary["comparison"], "groups": primary["effort"]["groups"],
            "conditions": {key: {"attempts": len(value["runs"]), "status": value["comparison"]["status"]} for key, value in summary["cohorts"][case_id].items()},
            "runs": primary["runs"], "specification": "README_benchmarks.md", "version": "manufacturing-evaluation-v2"}
