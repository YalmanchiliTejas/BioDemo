"""CHO bioprocess case study: recorded pipeline vs AI OS comparison.

Sources (all read through :class:`ArtifactStore`):

* ``results/cho/baseline_results.json`` — recorded conventional pipeline run
  over the original workbooks (tasks CHO-01 … CHO-05).
* ``runs/cho-comparison/`` — recorded Prime pilot run over the same workbook
  package (ingestion + one Prime investigation). It is a pilot, not a held-out
  benchmark score: it does not score any CHO task against the publisher
  reference.
* ``benchmarks/cho/reports/full_series_comparison.json`` — full trajectory
  reconstruction scored against the publisher's aligned CSVs.
* ``benchmarks/cho/reports/perturbation_validation.json`` — data-level source
  perturbation check.
* ``benchmarks/cho/reference/objective_summaries.json`` and
  ``process_comparison.json`` — evaluator-only descriptive references over the
  publication-aligned CSVs (no causal labels).
* ``benchmarks/cho/tasks/normalized/manifest.json`` — the recorded one-minute
  normalization manifest.
* ``benchmarks/cho/data_inventory.json`` and ``benchmarks/configs/cho.json`` —
  source inventory and benchmark configuration.

Scored AI-side metrics are reported as *Not measured* with the missing-data
reason: the recorded Prime pilot does not produce scored CHO task values. The
comparison view shows what the recorded pipeline demonstrably does, what the
pilot recorded (unscored), what the evaluation-only references describe, and
what remains unmeasured.
"""

from __future__ import annotations

import csv
from typing import Any

from .scorecard import (
    NOT_MEASURED,
    OBSERVED,
    VERIFIED,
    count_side,
    format_duration_seconds,
    metric,
    not_measured,
    percent_side,
    seconds_side,
    side,
)
from .sources import ArtifactStore

CASE_ID = "cho"
CASE_NAME = "CHO Bioprocess"
CASE_TITLE = "CHO-K1 fed-batch cultivations — process-data reconstruction and reactor comparison"
CASE_QUESTION = (
    "Starting from raw benchtop workbooks only, can an operating layer reconstruct analysis-ready "
    "cultivation trajectories and describe how parallel reactors differ, without manual mappings, "
    "injected tags, or future information?"
)

NO_AI_RUN_REASON = (
    "No AI OS run over the CHO dataset is recorded in this repository. The only recorded execution "
    "is the conventional pipeline in results/cho/baseline_results.json."
)

AI_PILOT_NOT_SCORED_REASON = (
    "A recorded Prime pilot run over the same workbook package exists (runs/cho-comparison), but it does "
    "not score this CHO task against the publisher reference. No scored AI-side value is reported."
)

GROUP_DATA = "Data ingestion & reconstruction"
GROUP_INVESTIGATION = "Investigation & interpretation"
GROUP_PERTURBATION = "Perturbation robustness"
GROUP_EXECUTION = "Recorded execution"

MAX_SERIES_POINTS = 300


def _get(mapping: Any, *path: str, default: Any = None) -> Any:
    current = mapping
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    return float(value) if isinstance(value, (int, float)) else None


def _int_text(value: Any) -> str:
    number = _number(value)
    return f"{int(number):,}" if number is not None else "Not measured"


def _experiment_group_id(grouping: Any) -> str:
    """Map a publisher grouping label ("EXP001_batch", "EXP010_fed-batch") to the comparison experiment id ("EXP001")."""
    text = str(grouping or "")
    for suffix in ("_fed-batch", "_batch"):
        if text.endswith(suffix):
            return text[: -len(suffix)]
    return text


def _reactor_channel_flags(objectives: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Flag channels that are constant (min == max) in a recorded cultivation summary.

    Several R02 probe channels were published as all-zero; their R02−R01 deltas are
    recording artefacts, not process differences. The flags keep those values visible
    while marking them, instead of silently dropping recorded data.
    """
    flags: dict[str, dict[str, str]] = {}
    for cultivation_id, cultivation in (objectives.get("cultivations") or {}).items():
        per_channel: dict[str, str] = {}
        for name, measurement in (cultivation.get("measurements") or {}).items():
            if measurement.get("kind") != "inline":
                continue
            low, high = _number(measurement.get("min")), _number(measurement.get("max"))
            if low is None or high is None or low != high:
                continue
            per_channel[name] = "constant_zero" if high == 0 else "constant"
        flags[cultivation_id] = per_channel
    return flags


class ChoCase:
    """Builds the comparison payload for the CHO case study."""

    def __init__(self, store: ArtifactStore) -> None:
        self.store = store

    # ----------------------------------------------------------------- pilot
    def _pilot(self) -> dict[str, Any] | None:
        """The recorded Prime pilot run, or ``None`` when it is absent."""

        pilot = self.store.get("cho_pilot")
        if not isinstance(pilot, dict) or pilot.get("claim_status") != "pilot_comparison_not_held_out_evaluation":
            return None
        return pilot

    def _ai_reason(self, pilot: dict[str, Any] | None = None) -> str:
        """Missing-data reason for unscored AI-side values under the recorded state."""

        if pilot is None:
            pilot = self._pilot()
        return AI_PILOT_NOT_SCORED_REASON if pilot else NO_AI_RUN_REASON

    def _investigation_ai_reason(self) -> str:
        """Reason for AI-side investigation rows: reference the pilot's unscored outputs."""

        pilot = self._pilot_facts()
        if pilot is None:
            return NO_AI_RUN_REASON
        parts = []
        if pilot.get("hypothesis_count") is not None:
            parts.append(f"{int(pilot['hypothesis_count'])} hypotheses")
        if pilot.get("cited_evidence_count") is not None:
            parts.append(f"{int(pilot['cited_evidence_count'])} cited evidence records")
        summary = " and ".join(parts) if parts else "unscored investigation output"
        return (
            f"The recorded Prime pilot produced {summary}, but nothing was scored against a reference "
            "for this task. No benchmark score is reported."
        )

    def _pilot_facts(self) -> dict[str, Any] | None:
        """Compact recorded facts from the pilot artifact; nothing is computed."""

        pilot = self._pilot()
        if pilot is None:
            return None
        agent = pilot.get("with_agent") or {}
        ingestion = agent.get("ingestion") or {}
        usage = agent.get("rollout_metrics") or {}
        ingestion_seconds = _number(ingestion.get("runtime_seconds"))
        investigation_seconds = _number(agent.get("investigation_seconds"))
        total = None
        if ingestion_seconds is not None and investigation_seconds is not None:
            total = round(ingestion_seconds + investigation_seconds, 3)
        return {
            "as_of": pilot.get("as_of"),
            "objective": pilot.get("objective"),
            "ingestion_seconds": ingestion_seconds,
            "investigation_seconds": investigation_seconds,
            "machine_seconds_total": total,
            "files_indexed": _number(ingestion.get("files_indexed")),
            "observations": _number(ingestion.get("observations")),
            "cited_evidence_count": _number(agent.get("cited_evidence_count")),
            "hypothesis_count": _number(agent.get("hypothesis_count")),
            "pending_evidence_request_count": _number(agent.get("pending_evidence_request_count")),
            "model_calls": _number(usage.get("model_calls")),
            "tool_calls": _number(usage.get("tool_calls")),
            "input_tokens": _number(usage.get("input_tokens")),
            "output_tokens": _number(usage.get("output_tokens")),
            "inference_cost_usd": _number(usage.get("inference_cost_usd")),
            "prime_session_id": usage.get("prime_session_id"),
        }

    # ---------------------------------------------------------------- header
    def header(self) -> dict[str, Any]:
        parser = self.store.get("cho_parser") or {}
        inventory = self.store.get("cho_inventory") or {}
        manifest = self.store.get("cho_normalization_manifest") or {}
        config = self.store.get("cho_config") or {}
        pilot = self._pilot_facts()
        facts = [
            {"id": "DOI", "statement": "CHO-K1 cultivation dataset published on Zenodo (DOI 10.5281/zenodo.20829178), license CC-BY-4.0.", "source": "benchmarks/cho/data_inventory.json"},
            {"id": "CHECKSUM", "statement": "Archive MD5 71b2a35b7df2ed11644ec9f177453772 matched the published checksum.", "source": "results/cho/report.md"},
            {"id": "PIPELINE", "statement": f"Recorded conventional pipeline run at {parser.get('run_at', 'an unrecorded time')} with OS-level agent isolation enabled.", "source": "results/cho/baseline_results.json"},
            {"id": "REFERENCE", "statement": "Evaluator-only descriptive references cover 12 experiments and 672 paired measurement comparisons; they make no significance or causality claim.", "source": "results/cho/report.md"},
            {"id": "NORMALIZATION", "statement": f"One-minute grid normalization ({manifest.get('method', 'linear interpolation')}) processed 24 cultivations in {manifest.get('runtime_seconds', 'an unrecorded number of')} s.", "source": "benchmarks/cho/tasks/normalized/manifest.json"},
        ]
        if pilot and pilot.get("hypothesis_count") is not None and pilot.get("cited_evidence_count") is not None:
            facts.append({
                "id": "PILOT",
                "statement": (
                    f"Recorded Prime pilot run over the same workbooks (as of {pilot.get('as_of')}): "
                    f"{int(pilot['hypothesis_count'])} hypotheses and {int(pilot['cited_evidence_count'])} cited evidence "
                    "records. One unvalidated pilot, not a held-out benchmark score."
                ),
                "source": "runs/cho-comparison/comparison.json",
            })
        return {
            "id": CASE_ID,
            "name": CASE_NAME,
            "title": CASE_TITLE,
            "question": CASE_QUESTION,
            "kind": "Process data intelligence",
            "dataset": {
                "label": "Published CHO-K1 cultivation dataset (Zenodo DOI 10.5281/zenodo.20829178)",
                "version": config.get("benchmark_version"),
                "license": "CC-BY-4.0 — attribution required for redistribution",
                "archive_md5": "71b2a35b7df2ed11644ec9f177453772",
                "records": (
                    f"{_int_text(inventory.get('workbook_count'))} workbooks · "
                    f"{_int_text(inventory.get('worksheet_count'))} worksheets · "
                    "3,251,506 data rows · 24 cultivations · "
                    f"{_int_text(inventory.get('csv_count'))} publication-aligned CSVs"
                ),
                "provenance": (
                    "Authentic cultivation measurements from the published dataset. The publisher's aligned "
                    "CSVs are a reconstruction reference, not independently verified biological truth."
                ),
                "disclaimer": (
                    "Aligned CSVs and descriptive summaries were evaluation-only; the recorded pipeline read "
                    "the original workbooks. No causal labels exist for this dataset."
                ),
            },
            "facts": facts,
            "inputs": [
                self.store.source(key) for key in (
                    "cho_parser", "cho_full_series", "cho_perturbation", "cho_inventory",
                    "cho_objectives", "cho_process_comparison", "cho_normalization_manifest", "cho_config",
                    "cho_pilot", "cho_pilot_report", "cho_pilot_cited",
                )
            ],
        }

    # ------------------------------------------------------------- scorecard
    def scorecard(self) -> dict[str, Any]:
        parser = self.store.get("cho_parser") or {}
        full_series = self.store.get("cho_full_series") or {}
        perturbation = self.store.get("cho_perturbation") or {}
        tasks = {_get(task, "task", "id"): task for task in (parser.get("tasks") or [])}
        cho01 = _get(tasks, "CHO-01", "metrics", default={}) or {}
        cho02 = _get(tasks, "CHO-02", "metrics", default={}) or {}
        cho05 = _get(tasks, "CHO-05", "metrics", default={}) or {}
        pilot = self._pilot_facts()
        parser_source = self.store.source("cho_parser")
        series_source = self.store.source("cho_full_series")
        perturbation_source = self.store.source("cho_perturbation")

        rows: list[dict[str, Any]] = []

        rows.append(metric(
            id="workbooks_parsed",
            label="Workbooks parsed without manual mappings — CHO-01",
            group=GROUP_DATA,
            definition="Share of the 12 original workbooks and 192 worksheets parsed without supplied tags or mappings.",
            direction="higher",
            traditional=count_side(_number(cho01.get("workbook_files_parsed")), 12,
                                   classification=OBSERVED,
                                   detail="Deterministic parser over the original workbooks; 0 manual corrections, 0 clarification requests."),
            ai=not_measured(self._ai_reason()),
            sources=[parser_source],
            note=(f"{_int_text(cho01.get('unique_structural_column_mappings'))} structural column mappings and "
                  f"{_int_text(cho01.get('source_rows_extracted'))} source rows were processed."),
        ))
        rows.append(metric(
            id="time_zero_match",
            label="Inoculation-time alignment correctness — CHO-01",
            group=GROUP_DATA,
            definition="Directly comparable time-zero values that match the publisher's aligned reference within tolerance.",
            direction="higher",
            traditional=count_side(_number(cho01.get("time_zero_matches")), _number(cho01.get("time_zero_values_checked")),
                                   classification=VERIFIED,
                                   detail=("Compared against the publisher's aligned CSVs. "
                                           f"{_int_text(cho01.get('time_zero_unavailable_values'))} values had no aligned counterpart.")
                                   if cho01 else "Recorded metric missing."),
            ai=not_measured(self._ai_reason()),
            sources=[parser_source, series_source],
        ))
        rows.append(metric(
            id="full_series_reconstruction",
            label="Full trajectory reconstruction agreement — CHO-02",
            group=GROUP_DATA,
            definition="Reconstructed trajectory values within normalized absolute error ≤ 0.01 of the publisher's alignment.",
            direction="higher",
            traditional=percent_side(_number(cho02.get("full_series_within_tolerance_fraction")),
                                     classification=VERIFIED, digits=3,
                                     detail=(f"{_int_text(cho02.get('full_series_within_tolerance'))} of "
                                             f"{_int_text(cho02.get('full_series_comparable_values'))} comparable values; "
                                             f"{_int_text(cho02.get('full_series_missing_reconstruction_values'))} reference values "
                                             "had no reconstructed counterpart.") if cho02 else "Recorded metric missing."),
            ai=not_measured(self._ai_reason()),
            sources=[series_source],
            note=("The publisher alignment is a reconstruction reference. The normalization uses sheet-naming "
                  "conventions and does not demonstrate autonomous schema inference."),
        ))
        rows.append(metric(
            id="source_rows_extracted",
            label="Source rows extracted — CHO-01",
            group=GROUP_DATA,
            definition="Data rows read from the original worksheets.",
            direction=None,
            traditional=side(_number(cho01.get("source_rows_extracted")),
                             display=f"{_int_text(cho01.get('source_rows_extracted'))} rows" if cho01 else "Not measured",
                             classification=OBSERVED),
            ai=not_measured(self._ai_reason()),
            sources=[parser_source],
        ))

        rows.append(metric(
            id="cho03_investigation",
            label="Time to identify measurements worth investigating — CHO-03",
            group=GROUP_INVESTIGATION,
            definition="Autonomous identification of variation worth investigating, with citations and uncertainty.",
            direction=None,
            traditional=not_measured("Baseline has no autonomous investigation; the task was not scored."),
            ai=not_measured(self._investigation_ai_reason()),
            sources=[parser_source],
            note="Shown as a gap so the missing measurement is explicit rather than implied.",
        ))
        rows.append(metric(
            id="cho04_comparison",
            label="Cultivation comparison with evidence — CHO-04",
            group=GROUP_INVESTIGATION,
            definition="Descriptive operating differences and abnormal-trend statements with supporting evidence.",
            direction=None,
            traditional=not_measured("Baseline has no autonomous investigation; the task was not scored."),
            ai=not_measured(self._investigation_ai_reason()),
            sources=[parser_source, self.store.source("cho_process_comparison")],
            note=("Evaluator-only descriptive references exist (12 experiments, 672 paired comparisons), but no "
                  "workflow produced them; they are not attributed to either side."),
        ))

        rows.append(metric(
            id="perturbation_sheets_parsed",
            label="Perturbed variant parsed — CHO-05",
            group=GROUP_PERTURBATION,
            definition="Worksheets parsed in the perturbed source package (16 original sheets plus 1 synthetic irrelevant sheet).",
            direction=None,
            traditional=side(_number(cho05.get("parsed_sheets")),
                             display=f"{_int_text(cho05.get('parsed_sheets'))} sheets ({_int_text(cho05.get('parsed_rows'))} rows)"
                             if cho05 else "Not measured",
                             classification=OBSERVED,
                             detail="The parser included the synthetic irrelevant worksheet and did not normalize the renamed or converted temperature channel."),
            ai=not_measured(self._ai_reason()),
            sources=[parser_source],
            note="Semantic consistency of interpretation was not scored: the extraction baseline has no experiment/variable interpretation to compare.",
        ))
        rows.append(metric(
            id="perturbation_source_validation",
            label="Source-format perturbation validation (data level)",
            group=GROUP_PERTURBATION,
            definition="Cell-level check that the perturbed package differs from the source only in the intended ways.",
            direction=None,
            traditional=side(
                1 if perturbation.get("pass") else (0 if perturbation else None),
                display=(f"Passed — {_int_text(perturbation.get('cells_checked'))} cells, "
                         f"{len(perturbation.get('unexpected_changes') or [])} unexpected changes") if perturbation else "Not measured",
                classification=VERIFIED if perturbation else NOT_MEASURED,
                detail="Verifies source-format changes only, not any workflow's interpretation.",
            ),
            ai=not_measured(self._ai_reason()),
            sources=[perturbation_source],
        ))

        total_seconds = sum(
            value for value in (
                _number(_get(tasks, task_id, "usage", "runtime_seconds")) for task_id in ("CHO-01", "CHO-02", "CHO-05")
            ) if value is not None
        ) if tasks else None
        rows.append(metric(
            id="machine_execution_total",
            label="Machine execution time — recorded pipeline",
            group=GROUP_EXECUTION,
            definition="Recorded wall-clock runtime of the scored pipeline tasks (CHO-01 + CHO-02 + CHO-05).",
            direction="lower",
            traditional=seconds_side(total_seconds if total_seconds else None,
                                     detail="105.808 s extraction + 151.255 s normalization + 12.760 s perturbation parse."),
            ai=not_measured(
                "The recorded Prime pilot times ingestion + investigation, not the scored pipeline tasks; "
                "see the AI OS pilot run row."
            ) if pilot else not_measured(self._ai_reason()),
            sources=[parser_source],
            note="Machine time is not human labor time; no human timing was recorded.",
        ))
        if pilot is not None:
            parts = []
            if pilot.get("ingestion_seconds") is not None:
                parts.append(f"{format_duration_seconds(pilot['ingestion_seconds'])} ingestion")
            if pilot.get("investigation_seconds") is not None:
                parts.append(f"{format_duration_seconds(pilot['investigation_seconds'])} investigation")
            rows.append(metric(
                id="ai_pilot_run",
                label="AI OS pilot run — recorded execution",
                group=GROUP_EXECUTION,
                definition="Recorded wall-clock runtime of the Prime pilot run over the same workbook package (workbook ingestion + one investigation).",
                direction=None,
                traditional=not_measured("The pilot is an AI-side run; the conventional pipeline runtime is in the machine-time row above."),
                ai=(
                    side(pilot.get("machine_seconds_total"), display=" + ".join(parts), classification=OBSERVED,
                         detail="Recorded Prime SDK pilot run over the same workbooks; not a held-out benchmark score and not scored against the publisher reference.",
                         unit="seconds")
                    if parts else not_measured(AI_PILOT_NOT_SCORED_REASON)
                ),
                sources=[self.store.source("cho_pilot"), self.store.source("cho_pilot_report")],
                note="Pilot run only: no CHO task was scored against the publisher reference; machine time is not human labor time.",
            ))
        rows.append(metric(
            id="model_cost",
            label="Model calls and inference cost — recorded pipeline",
            group=GROUP_EXECUTION,
            definition=(
                "Provider/model usage recorded for both recorded runs (conventional pipeline and AI OS pilot)."
                if pilot is not None else
                "Provider/model usage recorded for the conventional pipeline run."
            ),
            direction=None,
            traditional=side(0, display="0 model calls · $0.00 inference", classification=OBSERVED,
                             detail="The conventional parser is deterministic and makes no model calls."),
            ai=(
                side(pilot.get("model_calls"),
                     display=(
                         f"{int(pilot['model_calls'])} model calls"
                         + (f" · ${pilot['inference_cost_usd']:.2f} recorded inference" if pilot.get("inference_cost_usd") is not None else "")
                     ),
                     classification=OBSERVED,
                     detail="Recorded Prime pilot usage (root SDK session only; child worker usage not included).")
                if pilot and pilot.get("model_calls") is not None else not_measured(self._ai_reason())
            ),
            sources=[parser_source] + ([self.store.source("cho_pilot")] if pilot else []),
        ))
        rows.append(metric(
            id="human_effort",
            label="Engineering effort — human hours",
            group=GROUP_EXECUTION,
            definition="Human working time spent finding, correlating, and interpreting data.",
            direction=None,
            traditional=not_measured("No human timing was recorded in this benchmark; runtime values are machine execution time."),
            ai=not_measured(
                "No human timing was recorded in this benchmark; the pilot's human-time fields were not supplied."
                if pilot else self._ai_reason()
            ),
            sources=[],
            note="Explicitly not measured: the benchmark records machine runtime, not human labor saved.",
        ))

        headline_ids = {
            "full_series_reconstruction", "time_zero_match", "cho03_investigation", "machine_execution_total",
        }
        if pilot is not None:
            headline_ids.add("ai_pilot_run")
        headline = [row for row in rows if row["id"] in headline_ids]
        return {
            "metrics": rows,
            "headline": headline,
            "groups": [GROUP_DATA, GROUP_INVESTIGATION, GROUP_PERTURBATION, GROUP_EXECUTION],
            "conclusion": (
                (
                    "On the published CHO-K1 dataset the recorded conventional pipeline reconstructs trajectories with "
                    "99.905% numeric agreement to the publisher's alignment and matches every directly comparable "
                    "inoculation time. A recorded Prime pilot run covers the same workbooks and adds unscored AI-side "
                    "execution and investigation output; no CHO task was scored for the AI side, and human effort was "
                    "not measured for either workflow. Those rows are shown as Not measured rather than estimated."
                ) if pilot is not None else (
                    "On the published CHO-K1 dataset the recorded conventional pipeline reconstructs trajectories with "
                    "99.905% numeric agreement to the publisher's alignment and matches every directly comparable "
                    "inoculation time. Investigation, comparison, and human effort were not measured for either a "
                    "conventional investigation or an AI OS run; those rows are shown as Not measured rather than estimated."
                )
            ) if parser else
            "CHO benchmark artifacts are incomplete; only available measurements are shown.",
        }

    # ---------------------------------------------------------------- replay
    def replay(self) -> dict[str, Any]:
        """No two-workflow replay exists for CHO; expose the process viewer instead."""
        parser = self.store.get("cho_parser") or {}
        manifest = self.store.get("cho_normalization_manifest") or {}
        process = self.store.get("cho_process_comparison") or {}
        tasks = parser.get("tasks") or []
        entries = []
        for task in tasks:
            task_id = _get(task, "task", "id")
            runtime = _number(_get(task, "usage", "runtime_seconds"))
            entries.append({
                "task": task_id,
                "objective": _get(task, "task", "objective"),
                "seconds": runtime,
                "display": format_duration_seconds(runtime) if runtime is not None else "Not scored",
                "classification": OBSERVED if runtime is not None else NOT_MEASURED,
                "source": self.store.relative("cho_parser"),
            })
        done = [row for row in entries if row["seconds"] is not None]
        process_view = self._process_view(process, manifest)
        durations = [row.get("duration_hours") for row in process_view.get("cultivations", []) if row.get("duration_hours")]
        pilot = self._pilot_facts()
        ai_run = None
        if pilot is not None:
            ai_run = {
                "recorded": True,
                "kind": "prime_pilot",
                "as_of": pilot.get("as_of"),
                "objective": pilot.get("objective"),
                "ingestion_seconds": pilot.get("ingestion_seconds"),
                "investigation_seconds": pilot.get("investigation_seconds"),
                "machine_seconds_total": pilot.get("machine_seconds_total"),
                "cited_evidence_count": pilot.get("cited_evidence_count"),
                "hypothesis_count": pilot.get("hypothesis_count"),
                "pending_evidence_request_count": pilot.get("pending_evidence_request_count"),
                "model_calls": pilot.get("model_calls"),
                "prime_session_id": pilot.get("prime_session_id"),
                "claim_status": "pilot_comparison_not_held_out_evaluation",
                "note": (
                    "One recorded Prime pilot investigation over the same workbooks. It is not a synchronized "
                    "two-workflow replay, not a held-out benchmark score, and it does not score any CHO task "
                    "against the publisher reference."
                ),
                "sources": [self.store.source("cho_pilot"), self.store.source("cho_pilot_report")],
            }
        return {
            "status": "process_only",
            "reason": (
                (
                    "There is no synchronized two-workflow replay for CHO: the recorded Prime pilot is a one-off "
                    "investigation over the same workbooks, not a time-aligned scored replay, and the conventional "
                    "pipeline is a deterministic batch execution without per-event timestamps. The view below shows "
                    "the recorded executions and the published process trajectories instead."
                ) if ai_run else (
                    "There is no synchronized two-workflow replay for CHO: no AI OS run is recorded, and the "
                    "conventional pipeline is a deterministic batch execution without per-event timestamps. "
                    "The view below shows the recorded execution and the published process trajectories instead."
                )
            ),
            "ai_run": ai_run,
            "clock": {
                "id": "cultivation_time",
                "label": "Cultivation time (h, experiment-relative)",
                "kind": "process_time",
                "is_wall_clock": False,
                "start": 0.0,
                "end": max(durations) if durations else None,
                "note": "Inline trajectories are aligned on each experiment's inoculation time by the publisher.",
            },
            "execution": {
                "label": "Recorded conventional pipeline execution",
                "started_at": parser.get("run_at"),
                "entries": entries,
                "recorded_total_seconds": round(sum(row["seconds"] for row in done), 3) if done else None,
                "note": (
                    "Per-task start times are not recorded, so no wall-clock cursor is implied. Order follows "
                    "baseline_results.json. Values are machine execution time, not human labor."
                ),
            },
            "process": process_view,
            "guardrails": self._guardrails(),
            "tracks": {"traditional": [], "ai": []},
            "divergences": self._process_divergences(process),
        }

    def _process_view(self, process: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
        objectives = self.store.get("cho_objectives") or {}
        flags_by_cultivation = _reactor_channel_flags(objectives)
        experiments = process.get("experiments") or {}
        experiment_rows = []
        for experiment_id, experiment in experiments.items():
            deltas = []
            for name, measurement in (experiment.get("measurements") or {}).items():
                if measurement.get("kind") != "inline":
                    continue
                normalized = _number(measurement.get("mean_delta_over_pair_range"))
                if normalized is None:
                    continue
                deltas.append({
                    "variable": name,
                    "normalized_delta": normalized,
                    "r01_mean": _number(measurement.get("r01_mean")),
                    "r02_mean": _number(measurement.get("r02_mean")),
                    "direction": "r02_higher" if normalized > 0 else ("r02_lower" if normalized < 0 else "equal"),
                    "flags": self._channel_flags(flags_by_cultivation, experiment_id, name),
                })
            # Channels recorded as constant in one reactor are shown last: their
            # deltas are recording artefacts rather than process differences.
            deltas.sort(key=lambda item: (bool(item["flags"]), -abs(item["normalized_delta"])))
            experiment_rows.append({
                "id": experiment_id,
                "process_mode": experiment.get("process_mode"),
                "reactors": experiment.get("reactors"),
                "largest_differences": deltas[:3],
                "flagged_channel_count": sum(1 for item in deltas if item["flags"]),
            })
        cultivations = []
        variables: dict[str, None] = {}
        for row in manifest.get("cultivations") or []:
            inline_file = row.get("inline_file") or ""
            cultivation_id = inline_file.replace("_inline.csv", "")
            mode = "fed-batch" if "fed-batch" in inline_file else ("batch" if "batch" in inline_file else None)
            for name in (row.get("variables") or {}):
                variables.setdefault(name, None)
            cultivations.append({
                "id": cultivation_id,
                "experiment": _experiment_group_id(row.get("experiment")),
                "reactor": row.get("reactor"),
                "process_mode": mode,
                "inline_file": inline_file,
                "offline_file": row.get("offline_file"),
                "source_workbook": row.get("source_workbook"),
                "variable_count": len(row.get("variables") or {}),
                "backward_timestamp_steps_reordered": sum((row.get("reordered_backward_steps") or {}).values()),
                "duration_hours": self._inline_duration_hours(inline_file),
            })
        bom = process.get("interpretation_limit")
        flagged_total = sum(row["flagged_channel_count"] for row in experiment_rows)
        result = {
            "reference_note": (
                "Trajectories come from the publisher's aligned CSVs (evaluation reference) and the recorded "
                "normalization manifest; they are shown for the comparison view only. "
                + (bom or "Descriptive differences only — no significance, relevance, or causal claim.")
            ),
            "experiments": experiment_rows,
            "variables": list(variables),
            "cultivations": cultivations,
        }
        if flagged_total:
            result["flags_note"] = (
                f"{flagged_total} channel pair(s) are marked 'constant' or 'constant_zero' in one reactor's "
                "recorded summary (for example, several R02 probe channels were published as all-zero). Their "
                "deltas describe the recording, not necessarily a process difference, and are listed last."
            )
        return result

    @staticmethod
    def _channel_flags(flags_by_cultivation: dict[str, dict[str, str]], experiment_id: str, variable: str) -> list[str]:
        flags = []
        for reactor in ("R01", "R02"):
            flag = (flags_by_cultivation.get(f"{experiment_id}_{reactor}") or {}).get(variable)
            if flag:
                flags.append(f"{flag}_in_{reactor}")
        return flags

    def _inline_duration_hours(self, inline_file: str) -> float | None:
        """Last time value of an aligned inline CSV; used only for axis bounds."""
        if not inline_file:
            return None
        aligned = self.store.repository / "benchmarks/cho/reference/aligned" / inline_file
        if not aligned.is_file():
            return None
        try:
            with aligned.open("rb") as stream:
                stream.seek(0, 2)
                size = stream.tell()
                window = min(size, 4096)
                stream.seek(size - window)
                tail = stream.read().decode("utf-8", "ignore").rstrip()
            last_line = tail.splitlines()[-1] if tail else ""
            return round(float(last_line.split(",", 1)[0]), 4) if last_line else None
        except (OSError, ValueError, IndexError):
            return None

    def _process_divergences(self, process: dict[str, Any]) -> list[dict[str, Any]]:
        divergences = []
        flags_by_cultivation = _reactor_channel_flags(self.store.get("cho_objectives") or {})
        for experiment_id, experiment in (process.get("experiments") or {}).items():
            best = None
            best_flagged = None
            for name, measurement in (experiment.get("measurements") or {}).items():
                if measurement.get("kind") != "inline":
                    continue
                normalized = _number(measurement.get("mean_delta_over_pair_range"))
                if normalized is None:
                    continue
                candidate = (name, normalized, self._channel_flags(flags_by_cultivation, experiment_id, name))
                if candidate[2]:
                    if best_flagged is None or abs(normalized) > abs(best_flagged[1]):
                        best_flagged = candidate
                elif best is None or abs(normalized) > abs(best[1]):
                    best = candidate
            chosen = best or best_flagged
            if chosen is None:
                continue
            divergences.append({
                "id": f"DIV-{experiment_id}",
                "kind": "reactor_pair_difference",
                "label": f"{experiment_id}: {chosen[0]}",
                "verdict": "descriptive",
                "verdict_label": "Descriptive R02−R01 difference (no causality claim)",
                "difference_seconds": None,
                "normalized_delta": chosen[1],
                "flags": chosen[2],
                "source": "benchmarks/cho/reference/process_comparison.json",
            })
        divergences.sort(key=lambda item: (bool(item["flags"]), -abs(item["normalized_delta"])))
        return divergences

    def _guardrails(self) -> list[dict[str, Any]]:
        pilot = self._pilot_facts()
        return [
            {
                "check": "Aligned CSVs and structural maps were evaluation-only",
                "status": "observed",
                "basis": "The recorded pipeline read the original workbooks; alignment references were used only for scoring.",
                "source": "results/cho/report.md",
            },
            {
                "check": "No causal or statistical claims in the references",
                "status": "observed",
                "basis": "Descriptive summaries state no independence assumption, significance test, relevance label, or causal truth.",
                "source": self.store.relative("cho_process_comparison"),
            },
            {
                "check": "No counterfactual or yield-improvement claims",
                "status": "observed",
                "basis": "The comparison view reports observed trajectories and descriptive deltas only.",
                "source": "benchmark/case_comparison/cho.py",
            },
            {
                "check": ("AI-side benchmark scores withheld where no scored run exists"
                          if pilot else "AI-side metrics withheld where no run exists"),
                "status": "observed",
                "basis": (
                    "The recorded Prime pilot is shown as recorded (unscored) execution and investigation output; "
                    "every scored AI-side benchmark row stays Not measured with the missing-data reason."
                    if pilot else
                    "Every AI-side row resolves to Not measured with the missing-data reason."
                ),
                "source": "runs/cho-comparison/comparison.json" if pilot else "results/cho/report.md",
            },
        ]

    # ---------------------------------------------------------------- effort
    def effort(self) -> dict[str, Any]:
        parser = self.store.get("cho_parser") or {}
        tasks = parser.get("tasks") or []
        pilot = self._pilot_facts()
        machine = []
        for task in tasks:
            task_id = _get(task, "task", "id")
            runtime = _number(_get(task, "usage", "runtime_seconds"))
            machine.append({
                "label": f"{task_id} — {_get(task, 'task', 'objective', default='recorded task')}",
                "seconds": runtime,
                "classification": OBSERVED if runtime is not None else NOT_MEASURED,
                "display": format_duration_seconds(runtime) if runtime is not None else "Not scored",
                "source": self.store.relative("cho_parser"),
            })
        if pilot is not None:
            for label, seconds_key in (
                ("AI OS pilot ingestion (workbooks)", "ingestion_seconds"),
                ("AI OS pilot investigation (Prime SDK)", "investigation_seconds"),
            ):
                seconds = pilot.get(seconds_key)
                machine.append({
                    "label": label,
                    "seconds": seconds,
                    "classification": OBSERVED if seconds is not None else NOT_MEASURED,
                    "display": format_duration_seconds(seconds) if seconds is not None else "Not measured",
                    "source": self.store.relative("cho_pilot"),
                })
        return {
            "basis": (
                (
                    "Recorded executions: the conventional pipeline (results/cho/baseline_results.json) and a "
                    "Prime pilot run over the same workbooks (runs/cho-comparison) whose machine time covers "
                    "workbook ingestion and one investigation. No human timing was recorded for either workflow, "
                    "so no AI-side human-effort figures are computed."
                ) if pilot is not None else (
                    "The only recorded CHO execution is the conventional pipeline. Runtime values are machine "
                    "execution time from results/cho/baseline_results.json; no human timing was recorded. "
                    "No AI OS run exists, so no AI-side effort figures are computed."
                )
            ),
            "phase_rows": [],
            "phase_note": (
                "The benchmark does not decompose the pipeline run into retrieval, correlation, root-cause, "
                "coordination, summary, or approval phases."
            ),
            "engineer_hours": {
                "total_traditional": None,
                "total_ai": None,
                "per_investigation_traditional": None,
                "per_investigation_ai": None,
                "classification": NOT_MEASURED,
                "reason": (
                    "No human timing was recorded for CHO; the pilot's human-time fields were not supplied. "
                    "Runtime is machine execution time, not human labor saved."
                    if pilot is not None else
                    "No human timing was recorded for CHO; runtime is machine execution time, not human labor saved."
                ),
            },
            "machine_execution": machine,
            "model_cost": {
                "model_calls": sum(
                    value for value in (
                        _number(_get(task, "usage", "model_calls")) for task in tasks
                    ) if value is not None
                ) if tasks else None,
                "inference_cost_usd": sum(
                    value for value in (
                        _number(_get(task, "usage", "inference_cost_usd")) for task in tasks
                    ) if value is not None
                ) if tasks else None,
                "classification": OBSERVED if tasks else NOT_MEASURED,
                "note": (
                    "Recorded usage; the conventional parser is deterministic. The AI OS pilot usage is reported "
                    "in the scorecard model-cost row (root SDK session only)."
                    if pilot is not None else
                    "Recorded usage; the conventional parser is deterministic."
                ),
            },
            "unsupported_categories": [
                "Record retrieval — not decomposed; the pipeline reads the package in one pass.",
                "Cross-system correlation — not applicable; the source is a single workbook package.",
                (
                    "Root-cause work — the pilot produced unscored hypotheses; no scored root-cause analysis exists."
                    if pilot is not None else
                    "Root-cause work — no autonomous investigation was recorded (CHO-03/04 were not scored)."
                ),
                "Coordination — not measured.",
                "Summary preparation — not measured.",
                "Review and approval — not measured.",
            ],
            "tracked_effects": {},
            "note": (
                "Waiting/handoff time is not recorded. Only the machine-time categories the recorded runs "
                "support are shown; everything else stays Not measured."
                if pilot is not None else
                "Waiting/handoff time is not recorded. Only the machine-time categories the recorded run "
                "supports are shown; everything else stays Not measured."
            ),
        }

    # -------------------------------------------------------------- evidence
    def evidence(self) -> dict[str, Any]:
        parser = self.store.get("cho_parser") or {}
        full_series = self.store.get("cho_full_series") or {}
        perturbation = self.store.get("cho_perturbation") or {}
        objectives = self.store.get("cho_objectives") or {}
        tasks = {_get(task, "task", "id"): task for task in (parser.get("tasks") or [])}
        cho01 = _get(tasks, "CHO-01", "metrics", default={}) or {}
        cho02 = _get(tasks, "CHO-02", "metrics", default={}) or {}
        cho05 = _get(tasks, "CHO-05", "metrics", default={}) or {}
        run_at = parser.get("run_at")

        def status(*, retrieved_by=None, interpreted=None, missed=False, unavailable=None, not_measured_reason=None) -> dict[str, Any]:
            if not_measured_reason:
                return {"status": "not_measured", "label": "Not measured", "detail": not_measured_reason}
            if unavailable:
                return {"status": "unavailable", "label": "Unavailable", "detail": unavailable}
            if missed:
                return {"status": "missed", "label": "Missed", "detail": retrieved_by or "No recorded retrieval or interpretation."}
            if interpreted:
                return {"status": interpreted[0], "label": interpreted[1], "detail": interpreted[2]}
            return {"status": "retrieved", "label": "Retrieved", "detail": retrieved_by or ""}

        rows = [
            {
                "id": "CHO-01-workbooks",
                "label": "Workbook structure and measurements (12 workbooks, 192 sheets)",
                "type": "source package",
                "timestamp": run_at,
                "entities": ["EXP001…EXP012"],
                "traditional": status(
                    interpreted=("interpreted_correctly", "Retrieved, mapped, interpreted",
                                 f"{_int_text(cho01.get('workbook_files_parsed'))} workbooks parsed; "
                                 f"{_int_text(cho01.get('unique_structural_column_mappings'))} structural column mappings; "
                                 "0 manual corrections, 0 clarification requests.")
                    if cho01 else None,
                ),
                "ai": status(not_measured_reason=self._ai_reason()),
                "influence": "Everything downstream depends on reading the correct structure without injected tags.",
                "sources": [self.store.source("cho_parser"), self.store.source("cho_inventory")],
            },
            {
                "id": "CHO-01-time-zero",
                "label": "Inoculation-time alignment (1,300 comparable values)",
                "type": "alignment check",
                "timestamp": run_at,
                "entities": ["all cultivations"],
                "traditional": status(
                    interpreted=("interpreted_correctly", "Retrieved, interpreted correctly",
                                 f"{_int_text(cho01.get('time_zero_matches'))}/{_int_text(cho01.get('time_zero_values_checked'))} "
                                 f"time-zero values matched; {_int_text(cho01.get('time_zero_unavailable_values'))} had no aligned counterpart.")
                    if cho01 else None,
                ),
                "ai": status(not_measured_reason=self._ai_reason()),
                "influence": "Time alignment is the precondition for comparing trajectories across reactors and experiments.",
                "sources": [self.store.source("cho_parser")],
            },
            {
                "id": "CHO-02-trajectories",
                "label": "Full trajectory reconstruction (10,996,791 comparable values)",
                "type": "reconstruction result",
                "timestamp": run_at,
                "entities": ["24 cultivations", "48 aligned CSVs"],
                "traditional": status(
                    interpreted=("interpreted_correctly", "Retrieved, linked, reconstructed",
                                 f"{_int_text(cho02.get('full_series_within_tolerance'))} of "
                                 f"{_int_text(cho02.get('full_series_comparable_values'))} values within tolerance "
                                 f"(normalized absolute error ≤ {full_series.get('tolerance', '0.01')}); "
                                 f"{_int_text(cho02.get('full_series_missing_reconstruction_values'))} reference values missing.")
                    if cho02 else None,
                ),
                "ai": status(not_measured_reason=self._ai_reason()),
                "influence": "Defines how complete an analysis-ready representation of each cultivation is.",
                "sources": [self.store.source("cho_full_series")],
            },
            {
                "id": "CHO-03-investigation",
                "label": "Variation worth investigating (CHO-03)",
                "type": "investigation task",
                "timestamp": run_at,
                "entities": [],
                "traditional": status(missed=True, retrieved_by="Baseline has no autonomous investigation; the task was not scored."),
                "ai": status(not_measured_reason=self._investigation_ai_reason()),
                "influence": "The recorded baseline never produced a relevance ranking or uncertainty statement.",
                "sources": [self.store.source("cho_parser")],
            },
            {
                "id": "CHO-04-comparison",
                "label": "Cultivation comparison statements (CHO-04)",
                "type": "investigation task",
                "timestamp": run_at,
                "entities": [],
                "traditional": status(missed=True, retrieved_by="Baseline has no autonomous investigation; the task was not scored."),
                "ai": status(not_measured_reason=self._investigation_ai_reason()),
                "influence": "Reactor-pair differences exist only in the evaluator-only reference, not in any recorded workflow output.",
                "sources": [self.store.source("cho_parser"), self.store.source("cho_process_comparison")],
            },
            {
                "id": "CHO-05-perturbation",
                "label": "Perturbed source variant (17 sheets parsed)",
                "type": "perturbation run",
                "timestamp": run_at,
                "entities": ["renamed_header", "unit_conversions", "timestamp_format"],
                "traditional": status(
                    interpreted=("partially_interpreted", "Retrieved, partially interpreted",
                                 f"{_int_text(cho05.get('parsed_sheets'))} sheets / {_int_text(cho05.get('parsed_rows'))} rows parsed, "
                                 "but the synthetic irrelevant sheet was included and the renamed/converted temperature channel "
                                 "was not normalized; semantic consistency was not scored.")
                    if cho05 else None,
                ),
                "ai": status(not_measured_reason=self._ai_reason()),
                "influence": "Shows the recorded pipeline's robustness boundary: format changes that require interpretation are not handled.",
                "sources": [self.store.source("cho_parser"), self.store.source("cho_perturbation")],
            },
            {
                "id": "perturbation-validation",
                "label": "Data-level perturbation validation (2,084,974 cells)",
                "type": "verification",
                "timestamp": run_at,
                "entities": perturbation.get("intentional_change_counts", {}),
                "traditional": status(
                    interpreted=("verified", "Verified at data level",
                                 f"Passed with {len(perturbation.get('unexpected_changes') or [])} unexpected changes across "
                                 f"{_int_text(perturbation.get('cells_checked'))} cells.") if perturbation else None,
                ),
                "ai": status(not_measured_reason=self._ai_reason()),
                "influence": "Confirms the perturbation variant itself is sound; it does not verify any workflow's interpretation.",
                "sources": [self.store.source("cho_perturbation")],
            },
            {
                "id": "reference-summaries",
                "label": "Evaluator-only descriptive references (R01/R02, 672 comparisons)",
                "type": "evaluation reference",
                "timestamp": None,
                "entities": [f"EXP{index:03d}" for index in range(1, 13)],
                "traditional": status(unavailable="Evaluation-only reference; never visible to the recorded workflow."),
                "ai": status(not_measured_reason=self._ai_reason()),
                "influence": "Used only for the process-comparison view; carries no causal labels.",
                "sources": [self.store.source("cho_objectives"), self.store.source("cho_process_comparison")],
            },
            {
                "id": "reference-alignment",
                "label": "Publisher-aligned CSVs (48 files)",
                "type": "evaluation reference",
                "timestamp": None,
                "entities": ["24 cultivations"],
                "traditional": status(unavailable="Publisher alignment used only as reconstruction reference during scoring."),
                "ai": status(not_measured_reason=self._ai_reason()),
                "influence": "Scoring reference for CHO-02; not independently verified biological truth.",
                "sources": [self.store.source("cho_full_series")],
            },
        ]
        return {
            "statuses": ["retrieved", "missed", "interpreted_correctly", "partially_interpreted",
                         "verified", "unavailable", "not_measured"],
            "rows": rows,
            "annotations": {
                "time_zero_mismatch_examples": cho01.get("time_zero_mismatch_examples") or [],
                "perturbation_notes": perturbation_note(cho05),
                "reference_type": objectives.get("ground_truth_type"),
            },
            "basis": (
                (
                    "Statuses are computed from the recorded pipeline metrics (results/cho/baseline_results.json), "
                    "the perturbation report, and the evaluation-only references. No AI-side benchmark cell was "
                    "scored: the recorded Prime pilot is unscored pilot output, and every scored AI-side cell "
                    "carries the missing-data reason."
                ) if self._pilot() else (
                    "Statuses are computed from the recorded pipeline metrics (results/cho/baseline_results.json), "
                    "the perturbation report, and the evaluation-only references. Every AI-side cell carries the "
                    "missing-data reason because no AI OS run over CHO is recorded."
                )
            ),
        }

    # ------------------------------------------------------------ differences
    def differences(self) -> list[dict[str, Any]]:
        process = self.store.get("cho_process_comparison") or {}
        full_series = self.store.get("cho_full_series") or {}
        perturbation = self.store.get("cho_perturbation") or {}
        parser = self.store.get("cho_parser") or {}
        entries: list[dict[str, Any]] = []

        top = []
        flagged_top = []
        flags_by_cultivation = _reactor_channel_flags(self.store.get("cho_objectives") or {})
        for experiment_id, experiment in (process.get("experiments") or {}).items():
            for name, measurement in (experiment.get("measurements") or {}).items():
                if measurement.get("kind") != "inline":
                    continue
                normalized = _number(measurement.get("mean_delta_over_pair_range"))
                if normalized is None:
                    continue
                flags = self._channel_flags(flags_by_cultivation, experiment_id, name)
                (flagged_top if flags else top).append((abs(normalized), experiment_id, name, normalized, flags))
        top.sort(reverse=True, key=lambda item: item[0])
        flagged_top.sort(reverse=True, key=lambda item: item[0])
        if top or flagged_top:
            lead = top or flagged_top
            preview = "; ".join(
                f"{experiment_id} {name}: R02−R01 Δ = {normalized:+.3f} (normalized)"
                for _, experiment_id, name, normalized, _ in lead[:3]
            )
            detail = (
                f"{preview}. These are descriptive differences computed from the publisher's aligned CSVs; "
                "they are not produced by any recorded workflow and carry no causal claim."
            )
            if flagged_top:
                detail += (
                    f" {len(flagged_top)} channel pair(s) with a constant (e.g. all-zero) recording in one reactor "
                    "are excluded from this preview and marked in the process view."
                )
            entries.append({
                "id": "DIFF-DESCRIPTIVE-DELTAS",
                "category": "reference_observation",
                "classification": OBSERVED,
                "title": "Largest recorded R01 vs R02 descriptive differences",
                "detail": detail,
                "refs": [{"kind": "artifact", "id": self.store.relative("cho_process_comparison"),
                          "detail": "mean_delta_over_pair_range per variable"}],
            })

        mismatches = []
        for file in full_series.get("files") or []:
            for name, measurement in (file.get("measurements") or {}).items():
                pairs = _number(measurement.get("pairs"))
                within = _number(measurement.get("within_tolerance"))
                if pairs is None or within is None:
                    continue
                failures = pairs - within
                if failures > 0:
                    mismatches.append((failures, file.get("aligned_csv"), name, pairs))
        mismatches.sort(reverse=True)
        if mismatches:
            preview = "; ".join(
                f"{name} in {file} ({int(failures)}/{int(pairs)} outside tolerance)"
                for failures, file, name, pairs in mismatches[:3]
            )
            entries.append({
                "id": "DIFF-RECONSTRUCTION-GAPS",
                "category": "missed_evidence",
                "classification": VERIFIED,
                "title": "Trajectory values outside tolerance or missing",
                "detail": (
                    f"{preview}. Largest mismatches are concentrated in a few optical/feed channels; "
                    f"{_int_text(full_series.get('missing_reconstruction_values'))} reference values have no reconstructed counterpart."
                ),
                "refs": [{"kind": "artifact", "id": self.store.relative("cho_full_series"),
                          "detail": "within_tolerance vs pairs per file/channel"}],
            })

        if perturbation:
            entries.append({
                "id": "DIFF-PERTURBATION-BOUNDARY",
                "category": "found_by_traditional_only",
                "classification": OBSERVED,
                "title": "Recorded pipeline behaviour on the perturbed variant",
                "detail": (
                    "The parser processed 17 perturbed sheets (16 original + 1 synthetic irrelevant), did not "
                    "normalize the renamed or converted temperature channel, and produced no experiment/variable "
                    "interpretation, so semantic consistency was not scored."
                ),
                "refs": [{"kind": "artifact", "id": self.store.relative("cho_parser"),
                          "detail": "CHO-05 metrics"},
                         {"kind": "artifact", "id": self.store.relative("cho_perturbation"),
                          "detail": "intentional change counts"}],
            })

        if parser:
            pilot = self._pilot_facts()
            if pilot is not None and pilot.get("hypothesis_count") is not None:
                detail = (
                    "The conventional baseline produced no process hypotheses (CHO-03/04 unscored). The recorded "
                    f"Prime pilot produced {int(pilot['hypothesis_count'])} hypotheses with supporting and "
                    "contradicting evidence ids"
                )
                if pilot.get("pending_evidence_request_count") is not None:
                    detail += f" and {int(pilot['pending_evidence_request_count'])} pending evidence requests"
                detail += (
                    ". These are unvalidated pilot outputs, not scored against the publisher reference; nothing "
                    "in this repository supports hypothesis-level claims."
                )
                entries.append({
                    "id": "DIFF-PILOT-HYPOTHESES",
                    "category": "hypotheses",
                    "classification": OBSERVED,
                    "title": "Hypotheses and cited evidence appear only in the recorded AI OS pilot",
                    "detail": detail,
                    "refs": [{"kind": "artifact", "id": self.store.relative("cho_pilot_report"),
                              "detail": "causal_hypotheses with supporting/contradicting evidence ids"}],
                })
            else:
                entries.append({
                    "id": "DIFF-NO-HYPOTHESES",
                    "category": "hypotheses",
                    "classification": NOT_MEASURED,
                    "title": "Hypotheses and next analysis — not produced by any recorded workflow",
                    "detail": (
                        "The baseline produced no process hypotheses or relevance ranking (CHO-03/04 unscored), and no "
                        "AI OS run over CHO is recorded. Nothing in this repository supports hypothesis-level claims."
                    ),
                    "refs": [{"kind": "artifact", "id": self.store.relative("cho_parser"),
                              "detail": "CHO-03/04: 'Baseline has no autonomous investigation.'"}],
                })

        entries.append({
            "id": "DIFF-HUMAN-EFFORT",
            "category": "human_intervention",
            "classification": NOT_MEASURED,
            "title": "Human effort — not measured",
            "detail": (
                "No human timing was recorded for the CHO benchmark. Runtime values are machine execution time "
                "and must not be presented as human labor saved."
            ),
            "refs": [{"kind": "artifact", "id": self.store.relative("cho_parser"),
                      "detail": "usage.runtime_seconds is machine time"}],
        })
        return entries

    # ------------------------------------------------------------ issue chain
    def issue_chain(self) -> dict[str, Any]:
        process = self.store.get("cho_process_comparison") or {}
        manifest = self.store.get("cho_normalization_manifest") or {}
        flags_by_cultivation = _reactor_channel_flags(self.store.get("cho_objectives") or {})
        best = None
        best_flagged = None
        for experiment_id, experiment in (process.get("experiments") or {}).items():
            for name, measurement in (experiment.get("measurements") or {}).items():
                if measurement.get("kind") != "inline":
                    continue
                normalized = _number(measurement.get("mean_delta_over_pair_range"))
                if normalized is None:
                    continue
                candidate = {
                    "experiment": experiment_id,
                    "variable": name,
                    "normalized_delta": normalized,
                    "r01_mean": _number(measurement.get("r01_mean")),
                    "r02_mean": _number(measurement.get("r02_mean")),
                    "source_files": measurement.get("source_files") or [],
                    "flags": self._channel_flags(flags_by_cultivation, experiment_id, name),
                }
                if candidate["flags"]:
                    if best_flagged is None or abs(normalized) > abs(best_flagged["normalized_delta"]):
                        best_flagged = candidate
                elif best is None or abs(normalized) > abs(best["normalized_delta"]):
                    best = candidate
        best = best or best_flagged
        if best is None:
            return {"status": "not_measured", "reason": "No usable process-comparison reference is available."}

        experiment_deltas = []
        experiment = (process.get("experiments") or {}).get(best["experiment"], {})
        for name, measurement in (experiment.get("measurements") or {}).items():
            if measurement.get("kind") != "inline":
                continue
            normalized = _number(measurement.get("mean_delta_over_pair_range"))
            if normalized is None:
                continue
            experiment_deltas.append({
                "variable": name,
                "normalized_delta": normalized,
                "r01_mean": _number(measurement.get("r01_mean")),
                "r02_mean": _number(measurement.get("r02_mean")),
                "flags": self._channel_flags(flags_by_cultivation, best["experiment"], name),
            })
        experiment_deltas.sort(key=lambda item: (bool(item["flags"]), -abs(item["normalized_delta"])))
        cultivation_id = None
        for row in manifest.get("cultivations") or []:
            if str(row.get("experiment") or "").startswith(best["experiment"]):
                cultivation_id = (row.get("inline_file") or "").replace("_inline.csv", "")
                break

        not_recorded = {
            "status": "not_measured",
            "reason": (
                "The recorded baseline stops at data reconstruction; it produced no hypotheses, "
                "ranking, or next-analysis statements."
            ),
        }
        return {
            "status": "partial",
            "reason": (
                (
                    "The difference→variable→hypothesis investigation chain was never scored for CHO: the baseline "
                    "task set stops at reconstruction (CHO-03/04 unscored), and the recorded Prime pilot is unscored "
                    "pilot output, not a validated chain. Only the observed descriptive difference and its variables "
                    "can be shown."
                ) if self._pilot() else (
                    "The difference→variable→hypothesis investigation chain was never executed for CHO: the baseline "
                    "task set stops at reconstruction (CHO-03/04 unscored) and no AI OS run exists. Only the observed "
                    "descriptive difference and its variables can be shown."
                )
            ),
            "observation": {
                "difference": (
                    f"{best['experiment']} — {best['variable']}: R02 mean {best['r02_mean']:.4g} vs R01 mean {best['r01_mean']:.4g} "
                    f"(normalized Δ = {best['normalized_delta']:+.3f}). Largest recorded descriptive reactor-pair difference."
                    + (f" Flagged: {', '.join(best['flags'])} — the delta describes a constant recording rather than "
                       "necessarily a process difference." if best["flags"] else "")
                ),
                "classification": OBSERVED,
                "flags": best["flags"],
                "variables": experiment_deltas[:6],
                "hypotheses": not_recorded,
                "supporting_evidence": {
                    "status": "observed",
                    "records": best["source_files"],
                    "classification": "evaluation_reference",
                    "detail": "Publisher-aligned CSVs; available for analysis, evaluation-only in this benchmark.",
                },
                "contradictory_evidence": not_recorded,
                "next_analysis": not_recorded,
            },
            "moment": {"cultivation": cultivation_id, "clock": "cultivation_time"},
            "guardrails": self._guardrails(),
        }

    # ------------------------------------------------------------ presentation
    def presentation(self) -> dict[str, Any]:
        parser = self.store.get("cho_parser") or {}
        full_series = self.store.get("cho_full_series") or {}
        perturbation = self.store.get("cho_perturbation") or {}
        pilot = self._pilot_facts()
        observed_findings: list[str] = []
        unavailable = [
            "CHO-03 and CHO-04 were not scored; the baseline has no autonomous investigation.",
            "CHO-05 semantic consistency was not scored: the extraction baseline has no interpretation to compare.",
            "Human engineering effort was not measured; runtime values are machine execution time.",
            "Reactor-pair differences are descriptive; no significance, relevance, or causal claim is supported.",
        ]
        limitations = [
            "The publisher's aligned CSVs are a reconstruction reference used for scoring, not independently verified biological truth.",
            "The recorded normalization uses sheet-naming conventions; it does not demonstrate autonomous schema inference.",
            "No counterfactual or yield-improvement claim can be made from this dataset.",
        ]
        if pilot is not None:
            facts = []
            if pilot.get("model_calls") is not None:
                facts.append(f"{int(pilot['model_calls'])} model calls")
            if pilot.get("cited_evidence_count") is not None:
                facts.append(f"{int(pilot['cited_evidence_count'])} cited evidence records")
            if pilot.get("hypothesis_count") is not None:
                facts.append(f"{int(pilot['hypothesis_count'])} hypotheses")
            if pilot.get("machine_seconds_total") is not None:
                facts.append(f"{format_duration_seconds(pilot['machine_seconds_total'])} machine time (ingestion + investigation)")
            observed_findings.append(
                "Recorded AI OS pilot run over the same workbooks: "
                + (", ".join(facts) if facts else "unscored investigation output")
                + ". One unvalidated pilot, not a held-out benchmark score; no CHO task was scored for the AI side."
            )
            unavailable.insert(
                0,
                "No scored AI-side benchmark values exist: the recorded Prime pilot did not score any CHO task "
                "against the publisher reference, so scored AI-side metrics remain Not measured.",
            )
            limitations.append(
                "The Prime pilot is a single unvalidated run over this dataset; it does not establish repeatability "
                "or generalization."
            )
        else:
            unavailable.insert(
                0,
                "No AI OS run over the CHO dataset is recorded anywhere in the repository: every AI-side metric is Not measured.",
            )
        return {
            "headline": (
                (
                    "Authentic CHO process data: the recorded pipeline reconstructs 99.905% of trajectory values "
                    "against the publisher's alignment. A recorded Prime pilot ran over the same workbooks and adds "
                    "unscored AI-side output; human effort was never measured."
                ) if pilot is not None else (
                    "Authentic CHO process data: the recorded pipeline reconstructs 99.905% of trajectory values "
                    "against the publisher's alignment — investigation, comparison, and human effort were never measured."
                )
            ),
            "steps": [
                {"id": "scorecard", "label": "Scorecard — what was and was not measured"},
                {"id": "process", "label": "Process data — reactor-pair differences (descriptive)"},
                {"id": "evidence", "label": "Evidence trail, references, and guardrails"},
                {"id": "summary", "label": "Verified vs unavailable findings"},
            ],
            "verified_findings": [
                f"Dataset provenance: Zenodo DOI 10.5281/zenodo.20829178, CC-BY-4.0, archive MD5 matched; "
                f"{_int_text((self.store.get('cho_inventory') or {}).get('workbook_count'))} workbooks and "
                f"{_int_text((self.store.get('cho_inventory') or {}).get('csv_count'))} aligned CSVs inspected.",
                f"Reconstruction agreement: {_int_text(full_series.get('within_tolerance'))} of "
                f"{_int_text(full_series.get('comparable_values'))} comparable values within normalized tolerance "
                f"({per_mille(full_series.get('within_tolerance_fraction'))}); {_int_text(full_series.get('missing_reconstruction_values'))} reference values missing.",
                f"Inoculation-time alignment: 1,300/1,300 comparable values matched; 44 had no aligned counterpart.",
                f"Perturbation validation: {_int_text(perturbation.get('cells_checked'))} cells checked, "
                f"{len(perturbation.get('unexpected_changes') or [])} unexpected changes.",
            ],
            "modeled_findings": observed_findings,
            "unavailable_findings": unavailable,
            "limitations": limitations,
        }

    # ------------------------------------------------------------------ build
    def build(self) -> dict[str, Any]:
        return {
            "id": CASE_ID,
            "header": self.header(),
            "scorecard": self.scorecard(),
            "replay": self.replay(),
            "effort": self.effort(),
            "evidence": self.evidence(),
            "differences": self.differences(),
            "issue_chain": self.issue_chain(),
            "presentation": self.presentation(),
        }

    # ----------------------------------------------------------------- series
    def series(self, cultivation: str, variables: list[str], max_points: int = 240) -> dict[str, Any]:
        """Downsampled inline trajectories for the process view (aligned reference files)."""
        manifest = self.store.get("cho_normalization_manifest") or {}
        inline_file = None
        variables_available: list[str] = []
        for row in manifest.get("cultivations") or []:
            candidate = row.get("inline_file") or ""
            if candidate in {cultivation, f"{cultivation}_inline.csv"} or candidate.startswith(cultivation):
                inline_file = candidate
                variables_available = list(row.get("variables") or {})
                break
        if not inline_file:
            raise KeyError(f"cultivation not found in the normalization manifest: {cultivation}")
        aligned = self.store.repository / "benchmarks/cho/reference/aligned" / inline_file
        if not aligned.is_file():
            raise KeyError(f"aligned reference file is not available: {inline_file}")

        requested = [name for name in variables if name in variables_available] or variables_available[:1]
        timeline: list[float] = []
        columns: dict[str, list[float | None]] = {name: [] for name in requested}
        try:
            with aligned.open(newline="", encoding="utf-8") as stream:
                reader = csv.reader(stream)
                header = next(reader, None) or []
                index = {name: position for position, name in enumerate(header)}
                for row in reader:
                    if not row:
                        continue
                    try:
                        timeline.append(float(row[0]))
                    except (ValueError, IndexError):
                        continue
                    for name in requested:
                        position = index.get(name)
                        value = None
                        if position is not None and position < len(row):
                            try:
                                value = float(row[position])
                            except ValueError:
                                value = None
                        columns[name].append(value)
        except OSError as exc:
            raise KeyError(f"could not read {inline_file}: {exc}") from exc

        stride = max(1, len(timeline) // max(1, min(max_points, MAX_SERIES_POINTS)))
        series = {}
        for name in requested:
            points = [
                [round(timeline[position], 4), columns[name][position]]
                for position in range(0, len(timeline), stride)
                if columns[name][position] is not None
            ]
            values = [value for _, value in points if value is not None]
            series[name] = {
                "points": points,
                "min": round(min(values), 6) if values else None,
                "max": round(max(values), 6) if values else None,
                "count": len(points),
            }
        return {
            "cultivation": inline_file.replace("_inline.csv", ""),
            "file": inline_file,
            "role": "publisher-aligned reference (evaluation-only)",
            "downsample_stride": stride,
            "duration_hours": round(timeline[-1], 4) if timeline else None,
            "variables": series,
            "available_variables": variables_available,
        }


def perturbation_note(cho05: dict[str, Any]) -> list[str]:
    if not cho05:
        return []
    return [
        "The parser included the synthetic irrelevant worksheet (17 parsed vs 16 original sheets).",
        "The renamed and unit-converted temperature channel was not normalized.",
        "Semantic consistency of interpretation was not scored.",
    ]


def per_mille(value: Any) -> str:
    number = _number(value)
    return f"{number * 100:.3f}%" if number is not None else "Not measured"
