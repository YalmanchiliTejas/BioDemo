from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def generate(benchmark: str) -> Path:
    result_path = ROOT / "results" / benchmark / "baseline_results.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    from benchmarks.common.engineering_work import HEADLINE
    lines = [f"# {benchmark.upper()} benchmark report", "", f"Primary endpoint: **{HEADLINE}**.", "",
             "This automated extraction report does not measure human effort or reviewed engineering work. See `docs/engineering_work_benchmarks.md` for A. total effort, B. unfamiliar data and C. trustworthiness, and the comparison report for any collected effort ledgers.", "",
             "## Dataset and provenance", ""]
    def show(value: object) -> str:
        return "N/A" if value is None else str(value)
    if benchmark == "cho":
        source = json.loads((ROOT / "benchmarks/cho/source_manifest.json").read_text(encoding="utf-8"))
        inventory = json.loads((ROOT / "benchmarks/cho/data_inventory.json").read_text(encoding="utf-8"))
        objective = json.loads((ROOT / "benchmarks/cho/reference/objective_summaries.json").read_text(encoding="utf-8"))
        comparisons = json.loads((ROOT / "benchmarks/cho/reference/process_comparison.json").read_text(encoding="utf-8"))
        lines += [f"Authentic CHO-K1 cultivation measurements from DOI {source['doi']}; archive MD5 `{source['archive_md5']}` (published checksum matched).",
                  f"License: {source['license']}.",
                  f"Inspected {inventory['workbook_count']} original workbooks, {inventory['worksheet_count']} worksheets and {inventory['csv_count']} publication-aligned CSV files.",
                  f"Raw sheets contain {sum(s['rows_observed']-1 for w in inventory['workbooks'] for s in w['sheets']):,} data rows, {sum(s['missing_cells'] for w in inventory['workbooks'] for s in w['sheets']):,} empty cells and {sum(s['backward_timestamp_steps'] for w in inventory['workbooks'] for s in w['sheets'])} backward timestamp steps.",
                  f"Evaluator-only descriptive summaries cover {len(objective['cultivations'])} cultivations; they contain no causal labels.",
                  f"Evaluator-only R01/R02 references cover {len(comparisons['experiments'])} experiments and {sum(len(row['measurements']) for row in comparisons['experiments'].values())} descriptive measurement comparisons. They do not claim statistical significance.",
                  "Agent input was the original workbooks. Aligned CSVs and the structural map remained evaluation-only.", ""]
    else:
        manifest = json.loads((ROOT / "benchmarks/fresenius/raw_package/package_manifest.json").read_text(encoding="utf-8"))
        from benchmarks.common.provenance_validator import validate_mapping
        provenance = validate_mapping(ROOT / "benchmarks/fresenius/raw_package",
                                      ROOT / "benchmarks/fresenius/ground_truth/source_provenance.json")
        lines += ["Reconstructed synthetic manufacturing records derived from frozen `data/v1.1` canonical data. They are not Fresenius internal files.",
                  f"Canonical agent-data SHA-256: `{manifest['source_sha256']}`. Current generated package `{manifest['version']}`: {manifest['record_count']} records across {len(manifest['files'])} files.",
                  "Checksums and roles for every frozen input are recorded in `benchmarks/fresenius/source_manifest.json` and checked by the validation command.",
                  f"Hidden source map: {provenance['mapping_count']} pointers; validation {'PASS' if provenance['pass'] else 'FAIL'}.",
                  "Public FDA sources anchor the case chronology; synthetic records and hidden labels are separate.", ""]
        measured_version = result.get("reproducibility", {}).get("package_version")
        if measured_version is None and manifest["version"] != "fresenius-source-package-v1":
            lines += ["The results below were measured on the earlier 11-file v1 package. The current 14-file v2.1 package adds image-only lab reports, discrete process-event charts, and an aliased lab export with local timestamps and valid ratio conversion. No agent result is claimed for v2.1.", ""]
        data_check = ROOT / "benchmarks/fresenius/reports/data_validation.json"
        if data_check.exists():
            checked = json.loads(data_check.read_text(encoding="utf-8"))
            lines += [f"Data-only validation of all {len(checked['scenarios'])} historical v2.1 snapshots: {'PASS' if checked['pass'] else 'FAIL'}; every source pointer resolves to a record visible at its cutoff. Byte-for-byte rebuild: {checked.get('byte_deterministic_rebuild')}.", ""]
    lines += ["## Tasks, methods and actual results", "",
              f"Execution mode: `{result['mode']}`. OS-level agent filesystem isolation: `{result.get('os_isolated_agent', False)}`. Each task passed its package leakage audit before scoring.", "",
              "| Task | Objective | Measured result | Runtime |", "|---|---|---|---:|"]
    for item in result["tasks"]:
        task = item["task"]
        metrics = item["metrics"]
        if benchmark == "cho":
            if metrics.get("full_trajectory_reconstruction_scored"):
                finding = (f"{metrics['full_series_within_tolerance']:,}/{metrics['full_series_comparable_values']:,} "
                           f"trajectory values within tolerance; {metrics['full_series_missing_reconstruction_values']} unavailable")
            elif metrics.get("workbook_files_parsed"):
                finding = (f"{metrics['workbook_files_parsed']} workbooks; {metrics['worksheets_parsed']} sheets; "
                           f"{metrics.get('time_zero_matches', 0)}/{metrics.get('time_zero_values_checked', 0)} time-zero values matched")
            elif metrics.get("parsed_sheets"):
                finding = f"{metrics['parsed_sheets']} perturbed sheets parsed; semantic consistency unscored"
            else:
                finding = "Investigation not scored"
        else:
            finding = (f"{metrics['extracted_unique_ids']}/{metrics['visible_canonical_records']} record IDs; "
                       f"critical-lab recall {show(metrics.get('critical_lab_recall'))}")
        lines.append(f"| {task['id']} | {task['objective']} | {finding} | {item.get('usage', {}).get('runtime_seconds', '—')} s |")
    lines += ["", "## Failure examples and manual intervention", ""]
    if benchmark == "cho":
        metrics = result["tasks"][0]["metrics"]
        lines += [f"Time-zero mismatches: {metrics.get('time_zero_mismatch_examples', [])}.",
                  f"Unavailable time-zero comparisons: {metrics.get('time_zero_unavailable_values', 0)}.",
                  "No manual workbook mappings were supplied to the extraction worker. The evaluator generated hidden structural matches by exact header equality.",
                  "The baseline produced no process hypotheses or relevance ranking."]
        robustness = next((item for item in result['tasks'] if item['task']['id'] == 'CHO-05'), None)
        if robustness and robustness['metrics'].get('parsed_sheets'):
            original_sheets = len(next(book['sheets'] for book in inventory['workbooks'] if book['file'] == 'EXP001_batch.xlsx'))
            lines.append(f"The perturbation produced {robustness['metrics']['parsed_sheets']} parsed sheets versus {original_sheets} original sheets: the parser included the synthetic irrelevant worksheet, and it did not normalize the renamed or converted temperature channel.")
        perturbation_check = ROOT / "benchmarks/cho/reports/perturbation_validation.json"
        if perturbation_check.exists():
            check = json.loads(perturbation_check.read_text(encoding="utf-8"))
            lines.append(f"A separate data-only perturbation check compared {check['cells_checked']:,} cells and {'passed' if check['pass'] else 'failed'}; this verifies source-format changes, not an agent's interpretation.")
        series_path = ROOT / "benchmarks/cho/reports/full_series_comparison.json"
        if series_path.exists():
            series = json.loads(series_path.read_text(encoding="utf-8"))
            misses = sorted(((entry['aligned_csv'], name, row['pairs']-row['within_tolerance'], row['pairs'])
                             for entry in series['files'] for name, row in entry['measurements'].items()
                             if row['pairs']-row['within_tolerance']), key=lambda row: row[2], reverse=True)[:5]
            lines += ["", "## Full trajectory reconstruction", "",
                      f"A separate fixed-format normalization reads only original workbooks and reconstructs 24 cultivations on a one-minute inline grid. Against the publisher's aligned CSVs, {series['within_tolerance']:,}/{series['comparable_values']:,} comparable values ({series['within_tolerance_fraction']:.3%}) met {series['tolerance']}; {series['missing_reconstruction_values']} reference values had no reconstructed counterpart.",
                      "The normalized error divides absolute error by the larger of the reference channel range, the reference value magnitude and 1e-6. The publisher alignment is a reconstruction reference, not independently verified biological truth.",
                      f"Largest mismatches by count (file, channel, failures, comparisons): {misses}.",
                      "The normalization sorts backward timestamps and does not interpolate across source gaps longer than six minutes. It uses sheet naming conventions and therefore does not demonstrate autonomous schema inference."]
        cho_single = ROOT / "results/cho/retrieval_llm_results.json"
        if cho_single.exists():
            single = json.loads(cho_single.read_text(encoding="utf-8"))
            lines += ["", "## Retrieval plus one-pass reasoning baseline", "",
                      "A source-only parser summarized numeric ranges and source row locations from the original workbooks. A single bounded model call then reviewed at most 96 sheet summaries per task, selected across all 12 workbooks. No publisher-aligned values or hidden mappings were supplied.", "",
                      "| Task | Sheets retrieved | Citation validity | Citations | Input/output tokens | Runtime |",
                      "|---|---:|---:|---:|---:|---:|"]
            for item in single['tasks']:
                m, u = item['metrics'], item['usage']
                citations = len((item.get('analysis') or {}).get('evidence_ids', []))
                lines.append(f"| {item['task']['id']} | {m.get('source_sheets_retrieved', 'N/A')} | {show(m.get('analysis_citation_precision'))} | {citations} | {u.get('input_tokens')}/{u.get('output_tokens')} | {u.get('runtime_seconds')} s |")
            lines += ["", "Citation validity checks sheet identifiers against the original-workbook extraction. It does not score whether the cited variables are relevant or whether proposed process explanations are correct."]
    else:
        metrics = result["tasks"][0]["metrics"]
        lines += [f"The cross-batch extraction surfaced {metrics['extracted_unique_ids']} records while only {metrics['critical_lab_ids_visible']} incident-labeled action/OOS lab records were visible. This illustrates the baseline's lack of prioritization.",
                  "No manual corrections were made during execution. Source generation is programmatic preparation and is not counted as zero engineering labor.",
                  f"Automated snapshot generation plus provenance validation took {[item.get('automated_package_preparation_seconds') for item in result['tasks']]} seconds across the five tasks, separate from agent runtimes.",
                  "The baseline produced no competing hypotheses, scope decisions or recommended actions."]
        single_path = ROOT / "results/fresenius/retrieval_llm_results.json"
        if single_path.exists():
            single = json.loads(single_path.read_text(encoding="utf-8"))
            lines += ["", "## Retrieval plus one-pass reasoning baseline", "",
                      "This baseline used the same staged source snapshots and one model call per task. The model received at most 80 retrieved source rows. The records were extracted by the conventional parser first.", "",
                      "| Task | Critical lab retrieval recall | Citation validity | Citations | Model input/output tokens | Runtime |",
                      "|---|---:|---:|---:|---:|---:|"]
            for item in single["tasks"]:
                m, u = item["metrics"], item["usage"]
                citations = len(item.get("analysis", {}).get("evidence_ids", []))
                lines.append(f"| {item['task']['id']} | {show(m.get('retrieved_critical_lab_recall'))} | {show(m.get('analysis_citation_precision'))} | {citations} | {u.get('input_tokens')}/{u.get('output_tokens')} | {u.get('runtime_seconds')} s |")
            first = next((item for item in single["tasks"] if item["task"]["id"] == "FRE-02"), None)
            if first:
                lines += ["", "First-signal assessment excerpt: " + str(first["analysis"].get("assessment", ""))[:500],
                          "The model's cited IDs are checked against the time-visible canonical set. Citation validity does not prove its interpretations are correct."]
            reliability_path = ROOT / "results/fresenius/reliability_first_signal.json"
            if reliability_path.exists():
                reliability = json.loads(reliability_path.read_text(encoding="utf-8"))
                counts = [len(ids) for ids in reliability['citation_sets']]
                lines += ["", "## First-signal repeatability", "",
                          f"Trigger citation by run: {reliability['trigger_cited_each_run']}. Citation counts were {counts}; pairwise citation Jaccard values were {reliability['pairwise_citation_jaccard']}.",
                          "The spread in citation counts and overlaps measures evidence-selection stability. Three runs are too few for a reliable interval estimate."]
    lines += ["", "## Cost and reproducibility", "",
              "The conventional parser made zero model calls and incurred zero inference token cost. Single-pass model token counts are provider-reported; monetary cost is unknown. Runtime values are machine execution time, not human labor saved.",
              f"Source SHA-256: `{result.get('reproducibility', {}).get('source_sha256')}`. Task-definition SHA-256: `{result.get('reproducibility', {}).get('task_sha256')}`.",
              f"Python: `{result.get('reproducibility', {}).get('python')}`. Parser code SHA-256: `{result.get('reproducibility', {}).get('adapter_code_sha256')}`.",
              "Run the CLI commands in `benchmarks/README.md`; source and package manifests record checksums and versions.", "",
              "## Limitations", "",
              "The deterministic parser results do not establish autonomous investigation performance. Repeated-run confidence intervals are not meaningful for that baseline. The model repeat check is small and limited to FRE-02.",
              "No full Manufacturing RLM score is reported because the existing RLM currently consumes structured factory records rather than these raw packages.", ""]
    path = ROOT / "results" / benchmark / "report.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    comparison = ROOT / "results/benchmark_comparison.md"
    cho_series = ROOT / "benchmarks/cho/reports/full_series_comparison.json"
    cho_result = ROOT / "results/cho/baseline_results.json"
    if cho_series.exists() and cho_result.exists():
        series = json.loads(cho_series.read_text(encoding="utf-8"))
        cho_summary = (f"Its fixed-format baseline reconstructed 24 cultivations from the original workbooks; "
                       f"{series['within_tolerance']:,}/{series['comparable_values']:,} comparable values "
                       f"({series['within_tolerance_fraction']:.3%}) met the documented tolerance against publisher alignment. "
                       "Causal relevance and process explanations remain unscored.")
    else:
        cho_summary = "Its full trajectory comparison has not yet run; causal relevance remains unscored."
    reliability_path = ROOT / "results/fresenius/reliability_first_signal.json"
    reliability_summary = "Repeatability has not been measured."
    if reliability_path.exists():
        reliability = json.loads(reliability_path.read_text(encoding="utf-8"))
        counts = [len(ids) for ids in reliability['citation_sets']]
        reliability_summary = f"Three first-signal repeats cited {counts} records, with pairwise Jaccard overlaps {reliability['pairwise_citation_jaccard']}."
    cho_llm = ROOT / "results/cho/retrieval_llm_results.json"
    if cho_llm.exists():
        llm = json.loads(cho_llm.read_text(encoding="utf-8"))
        cho_summary += f" A one-pass model baseline was run on {len(llm['tasks'])} CHO tasks using source-only sheet summaries; source-citation validity was measured, while causal accuracy was not."
    comparison.write_text("# Benchmark comparison\n\n"
                          "CHO tests authentic experimental bioprocess measurements, especially source discovery and reconstruction. " + cho_summary + "\n\n"
                          "Fresenius tests investigation of simulated manufacturing-quality scenarios constrained by publicly documented FDA findings. The conventional parser recovered all visible record IDs at five replay cutoffs on the earlier v1 export format. A one-pass model retrieved all visible incident action/OOS lab records and made time-valid citations on v1. " + reliability_summary + " The current v2.1 source package adds scanned lab reports, discrete process charts, and a local-time lab export; its five historical snapshots passed data validation, but no agent score exists for v2.1.\n\n"
                          "Neither benchmark alone proves performance on confidential commercial CDMO records or prevention of real-world manufacturing failures. The benefit of the full RLM architecture over simpler baselines remains unmeasured because its raw-source adapter is not yet connected.\n", encoding="utf-8")
    return path
