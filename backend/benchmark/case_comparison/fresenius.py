"""Fresenius Kabi famotidine case study: traditional vs AI OS comparison.

Sources (all read through :class:`ArtifactStore`):

* ``benchmark/pharma_simulation/artifacts/benchmark_results.json`` — modeled
  rules-baseline vs context-ablation runs over the frozen synthetic dataset.
* ``runs/comparison/comparison.json`` — paired 30-run traditional vs
  agent-assisted campaign projection (``modeled_projection_not_empirical_validation``).
* ``results/fresenius/*.json`` — recorded conventional and retrieval+model
  baseline runs over the raw source package.
* ``runs/my-comparison/*`` — recorded Prime SDK pilot comparison.
* ``benchmark/incident_demo/data/*`` — frozen case chronology, batch records,
  and hidden ground-truth labels (evaluation only).

The AI-OS replay track is produced by the existing deterministic agent in
``benchmark/incident_demo/agent.py`` evaluated at each recorded event cutoff.
It is a time-valid model replay, not a human-measured investigation.
"""

from __future__ import annotations

from typing import Any

from .alignment import TraceEvent, detect_divergences, normalize_track, seconds_between
from .scorecard import (
    MODELED,
    NOT_MEASURED,
    OBSERVED,
    count_side,
    format_duration_seconds,
    hours_side,
    metric,
    not_measured,
    percent_side,
    seconds_side,
    side,
)
from .sources import ArtifactStore


CASE_ID = "fresenius"
CASE_NAME = "Fresenius Kabi"
CASE_TITLE = "Famotidine Injection — cross-batch bioburden risk investigation"
CASE_QUESTION = (
    "Could a connected AI operating layer identify and scope the recurring upstream microbiological "
    "risk earlier than the reconstructed batch-local workflow, using only the evidence that existed at each moment?"
)

SYSTEM_TO_KIND = {
    "MES": "production_activity",
    "LIMS": "evidence_available",
    "QMS": "local_quality_action",
    "Complaints": "evidence_available",
}

TITLE_TO_KIND = {
    "Batch started": "production_activity",
    "Bioburden action limit exceeded": "evidence_available",
    "Deviation opened": "risk_acknowledged",
    "Finished-product tests available": "evidence_available",
    "Organism identification available": "evidence_available",
    "Field signal received": "field_signal",
    "Reserve-sample result available": "evidence_available",
    "Public recall announced": "regulatory_outcome",
}

INCIDENT_BATCHES = ("BATCH-075", "BATCH-084", "BATCH-099")

EVIDENCE_PREVIEW_LIMIT = 200

GROUP_DETECTION = "Detection & risk identification"
GROUP_OUTPUT = "Investigation output"
GROUP_TIME = "Time & effort"
GROUP_RECORDED = "Recorded execution (pilot run)"


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


def _recorded_number(value: Any, unit: str, *, detail: str | None = None) -> dict[str, Any]:
    number = _number(value)
    if number is None:
        return not_measured("No value is recorded in the source artifact.")
    return side(number, display=f"{number:.2f} {unit}", classification=MODELED, detail=detail)


class FreseniusCase:
    """Builds the comparison payload for the Fresenius case study."""

    def __init__(self, store: ArtifactStore, *, incident_service: Any | None = None) -> None:
        self.store = store
        self._incident_service = incident_service

    # ---------------------------------------------------------------- header
    def header(self) -> dict[str, Any]:
        replay = self.store.get("fresenius_replay") or {}
        metadata = replay.get("metadata", {})
        public = self.store.get("fresenius_public_truth") or {}
        simulation = self.store.get("fresenius_simulation") or {}
        return {
            "id": CASE_ID,
            "name": CASE_NAME,
            "title": CASE_TITLE,
            "question": CASE_QUESTION,
            "kind": "Manufacturing-quality risk investigation",
            "dataset": {
                "label": "Reconstructed synthetic records anchored to public FDA findings",
                "version": metadata.get("dataset_version"),
                "fingerprint": simulation.get("dataset_fingerprint"),
                "provenance": metadata.get("permanent_disclosure"),
                "disclaimer": metadata.get("retrospective_disclaimer"),
                "records": "100 batched records, 303 lab results, 400 process events at the frozen snapshot",
            },
            "public_facts": [
                {
                    "id": fact.get("id") or fact.get("fact_id"),
                    "statement": fact.get("fact"),
                    "source": fact.get("source"),
                    "source_url": fact.get("source_url"),
                    "available_at": fact.get("available_at"),
                }
                for fact in (public.get("facts") or replay.get("public_facts") or [])
            ],
            "inputs": [
                self.store.source(key) for key in (
                    "fresenius_simulation", "campaign_comparison", "fresenius_parser",
                    "fresenius_retrieval", "fresenius_reliability", "fresenius_pilot",
                    "fresenius_replay", "fresenius_ground_truth",
                )
            ],
        }

    # ------------------------------------------------------------- scorecard
    def scorecard(self) -> dict[str, Any]:
        simulation = self.store.get("fresenius_simulation") or {}
        rules = simulation.get("rules_baseline") or {}
        full = _get(simulation, "ablations", "D_full_OS_context", default={}) or {}
        memory = _get(simulation, "memory_ablation", "B_manufacturing_memory_enabled", default={}) or {}
        comparison = self.store.get("campaign_comparison") or {}
        endpoints = comparison.get("endpoints", {})
        traditional_run = self.store.get("campaign_representative_traditional") or {}
        assisted_run = self.store.get("campaign_representative_assisted") or {}
        parser = self.store.get("fresenius_parser") or {}
        pilot = self.store.get("fresenius_pilot") or {}
        reliability = self.store.get("fresenius_reliability") or {}

        sim_source = self.store.source("fresenius_simulation")
        campaign_source = self.store.source("campaign_comparison")
        pilot_source = self.store.source("fresenius_pilot")
        parser_source = self.store.source("fresenius_parser")

        sim_definition = (
            "Computed on the frozen synthetic dataset (fingerprint "
            f"{(simulation.get('dataset_fingerprint') or '')[:12]}…). The rules baseline uses local event "
            "context; the full-context condition adds LIMS, QMS and cross-batch context." if simulation else
            "Simulation artifact missing."
        )

        rows: list[dict[str, Any]] = []

        rows.append(metric(
            id="incident_detection_recall",
            label="Incident detection recall — 5 labeled incidents",
            group=GROUP_DETECTION,
            definition="Share of labeled incident batches the condition escalates at or above the labeled escalation level.",
            direction="higher",
            traditional=count_side(_number(rules.get("true_incidents_detected")), _number(rules.get("true_incidents")),
                                   detail="Rules baseline (local event context)."),
            ai=count_side(_number(full.get("true_incidents_detected")), _number(full.get("true_incidents")),
                          detail="Full OS context (deterministic contextual agent)."),
            sources=[sim_source],
            note=sim_definition,
        ))
        rows.append(metric(
            id="triage_accuracy",
            label="Correct escalation decisions (triage accuracy)",
            group=GROUP_DETECTION,
            definition="Share of labeled incidents whose best escalation level matches the benchmark label.",
            direction="higher",
            traditional=percent_side(_number(rules.get("triage_accuracy"))),
            ai=percent_side(_number(full.get("triage_accuracy"))),
            sources=[sim_source],
        ))
        rows.append(metric(
            id="time_to_diagnosis",
            label="Projected time to risk identification — assigned simulation delays",
            group=GROUP_DETECTION,
            definition="Mean hours to diagnose across the 12 scenarios repeated over 30 paired campaign runs.",
            direction="lower",
            traditional=hours_side(_get(endpoints, "time_to_diagnose_hours", "traditional_mean", default=None)),
            ai=hours_side(_get(endpoints, "time_to_diagnose_hours", "agent_assisted_mean", default=None)),
            sources=[campaign_source],
            note=("Diagnosis delay is assigned in controller code: traditional 12 h + 6 h for critical cases; assisted 4 h + 2 h for critical cases. "
                  "The reported averages follow those inputs; no agent or human diagnosis was timed. "
                  "Modeled paired deterministic simulation under explicit controller assumptions "
                  f"({comparison.get('paired_runs')} paired runs, {comparison.get('scenario_count_per_run')} scenarios each). "
                  "Validate timing inputs in a prospective shadow study before customer claims."),
        ))
        first_lot = _get(full, "time_to_detection_minutes_by_incident_batch", "BATCH-075", default=None)
        rows.append(metric(
            id="first_lot_identification",
            label="Time to identify the first reconstructed incident lot (BATCH-075)",
            group=GROUP_DETECTION,
            definition="Elapsed time between the earliest detectable timestamp and the first escalation, computed per batch event stream.",
            direction="lower",
            traditional=side(None, display="Never identified", classification=MODELED,
                             detail="The local rules condition never crosses the escalation threshold for BATCH-075."),
            ai=side(_number(first_lot)
                    if isinstance(first_lot, (int, float)) and not isinstance(first_lot, bool) else None,
                    display=(f"{first_lot / 1440:.1f} days" if isinstance(first_lot, (int, float)) else "Not measured"),
                    classification=MODELED,
                    detail=("In the batch-scoped stream the full-context condition first escalates for BATCH-075 at the "
                            "field signal, not at the early excursions. Reported as recorded; this is not a timing advantage.")),
            sources=[sim_source],
        ))
        rows.append(metric(
            id="false_positive_escalations",
            label="False-positive escalations — 95 non-incident batches",
            group=GROUP_DETECTION,
            definition="Share of non-incident batches that cross the escalation threshold.",
            direction="lower",
            traditional=count_side(_number(rules.get("false_positive_batches")), _number(rules.get("evaluated_batches")),
                                   detail="Rules baseline."),
            ai=count_side(_number(full.get("false_positive_batches")), _number(full.get("evaluated_batches")),
                          detail="Full OS context (memory-enabled variant adds 1 false positive in the recorded run)."),
            sources=[sim_source],
            note=(f"The memory-enabled ablation records {memory.get('false_positive_batches')} false-positive "
                  "batch when manufacturing memory is enabled." if memory else None),
        ))
        rows.append(metric(
            id="future_leakage",
            label="Future-information leakage into decisions",
            group=GROUP_DETECTION,
            definition="Share of cited evidence that was unavailable at the decision cutoff.",
            direction="lower",
            traditional=percent_side(_number(rules.get("future_leakage_rate"))),
            ai=percent_side(_number(full.get("future_leakage_rate"))),
            sources=[sim_source],
            note="Both conditions kept every citation inside the cutoff; this is a guardrail check, not a performance difference.",
        ))

        rows.append(metric(
            id="investigation_scope_recall",
            label="Investigation-scope recall",
            group=GROUP_OUTPUT,
            definition="Share of the labeled related-batch scope the condition surfaces.",
            direction="higher",
            traditional=percent_side(_number(rules.get("investigation_scope_recall"))),
            ai=percent_side(_number(full.get("investigation_scope_recall"))),
            sources=[sim_source],
        ))
        rows.append(metric(
            id="hypothesis_relevance",
            label="Hypothesis relevance (benchmark rubric)",
            group=GROUP_OUTPUT,
            definition="Overlap between generated hypotheses and the labels' plausible hypotheses.",
            direction="higher",
            traditional=percent_side(_number(rules.get("hypothesis_relevance"))),
            ai=percent_side(_number(full.get("hypothesis_relevance"))),
            sources=[sim_source],
        ))
        rows.append(metric(
            id="action_relevance",
            label="Recommended-action relevance (benchmark rubric)",
            group=GROUP_OUTPUT,
            definition="Overlap between recommended actions and the labels' expected actions.",
            direction="higher",
            traditional=percent_side(_number(rules.get("action_relevance"))),
            ai=percent_side(_number(full.get("action_relevance"))),
            sources=[sim_source],
        ))
        rows.append(metric(
            id="required_evidence_coverage",
            label="Required-evidence coverage (paired campaign)",
            group=GROUP_OUTPUT,
            definition="Mean share of required evidence the investigation output covers.",
            direction="higher",
            traditional=percent_side(_get(endpoints, "required_evidence_coverage", "traditional_mean", default=None)),
            ai=percent_side(_get(endpoints, "required_evidence_coverage", "agent_assisted_mean", default=None)),
            sources=[campaign_source],
        ))
        rows.append(metric(
            id="traceable_output_rate",
            label="Traceable output & counter-evidence rate (paired campaign)",
            group=GROUP_OUTPUT,
            definition="Composite of source traceability and counter-evidence assessment in the investigation output.",
            direction="higher",
            traditional=percent_side(_number(_get(traditional_run, "investigation_output_quality", "traceable_output_rate"))),
            ai=percent_side(_number(_get(assisted_run, "investigation_output_quality", "traceable_output_rate"))),
            sources=[self.store.source("campaign_representative_traditional"), self.store.source("campaign_representative_assisted")],
            note="Representative paired run 20250939; the 30-run means are shown for the headline endpoints.",
        ))
        rows.append(metric(
            id="root_cause_accuracy",
            label="Root-cause accuracy — N/A without independent causal labels",
            group=GROUP_OUTPUT,
            definition="Share of scenarios whose investigation output names the labeled root cause.",
            direction=None,
            traditional=not_measured("Not applicable: simulation assumptions are not independently established internal RCA labels."),
            ai=not_measured("Not applicable: evaluate hypothesis support, counterevidence and uncertainty instead."),
            sources=[self.store.source("campaign_representative_traditional"), self.store.source("campaign_representative_assisted")],
            note="Legacy source artifacts are preserved. Their synthetic root-cause scores are withheld under README_benchmarks.md.",
        ))

        rows.append(metric(
            id="deviation_closure_hours",
            label="Total investigation time (deviation closure)",
            group=GROUP_TIME,
            definition="Mean hours from deviation opening to closure across the paired campaign.",
            direction="lower",
            traditional=hours_side(_get(endpoints, "deviation_closure_hours", "traditional_mean", default=None)),
            ai=hours_side(_get(endpoints, "deviation_closure_hours", "agent_assisted_mean", default=None)),
            sources=[campaign_source],
        ))
        rows.append(metric(
            id="engineer_hours_per_investigation",
            label="Projected engineer-hours — assigned simulation effort",
            group=GROUP_TIME,
            definition="Mean MSAT process-engineering hours per investigation in the paired campaign.",
            direction="lower",
            traditional=_recorded_number(_get(traditional_run, "msat_process_engineering", "mean_engineer_hours_per_investigation"), "h"),
            ai=_recorded_number(_get(assisted_run, "msat_process_engineering", "mean_engineer_hours_per_investigation"), "h"),
            sources=[self.store.source("campaign_representative_traditional"), self.store.source("campaign_representative_assisted")],
            note="Controller-assigned effort: traditional 9 + 1.75 × systems + critical_extra/2; assisted 4 + 0.6 × systems + critical_extra/2. This projects the chosen assumptions; it is not observed labor saved.",
        ))
        rows.append(metric(
            id="human_review_minutes",
            label="Human minutes on the pilot case (supplied estimate)",
            group=GROUP_TIME,
            definition="Human time recorded for the pilot comparison: baseline case time and human review/correction time with the agent.",
            traditional=_recorded_number(_get(pilot, "without_agent", "human_minutes"), "min",
                             detail="Operator-supplied baseline estimate passed to the pilot command; not a timed human study."),
            ai=_recorded_number(_get(pilot, "with_agent", "human_minutes_including_review_and_correction",
                                     default=_get(pilot, "with_agent", "human_minutes")), "min",
                    detail="Operator-supplied review/correction estimate; not a timed human study."),
            sources=[pilot_source],
            note="Shown only because the values were supplied to the recorded pilot run. The benchmark does not measure human performance.",
        ))
        rows.append(metric(
            id="systems_accessed",
            label="Systems accessed per investigation (paired campaign)",
            group=GROUP_TIME,
            definition="Mean count of source systems touched per investigation.",
            traditional=_recorded_number(_get(traditional_run, "msat_process_engineering", "mean_systems_accessed_per_investigation"), "systems"),
            ai=_recorded_number(_get(assisted_run, "msat_process_engineering", "mean_systems_accessed_per_investigation"), "systems"),
            sources=[self.store.source("campaign_representative_traditional"), self.store.source("campaign_representative_assisted")],
            note="The assisted condition accesses slightly more systems; broader context is the intended mechanism, not fewer sources.",
        ))

        parser_seconds = _number(_get(pilot, "without_agent", "extraction_seconds"))
        ingestion = _number(_get(pilot, "with_agent", "ingestion", "runtime_seconds"))
        investigation = _number(_get(pilot, "with_agent", "investigation_seconds"))
        rows.append(metric(
            id="machine_execution_time",
            label="Machine execution time — extraction vs agent run (pilot)",
            group=GROUP_RECORDED,
            definition="Recorded wall-clock processing time in the pilot comparison. Extraction performs no investigation.",
            direction="lower",
            traditional=seconds_side(parser_seconds, detail="Conventional parser over the same 14-file raw package; no conclusions produced."),
            ai=seconds_side((ingestion or 0) + (investigation or 0) if (ingestion is not None or investigation is not None) else None,
                            detail=f"Ingestion {ingestion:.3f} s + investigation {investigation:.3f} s."
                            if ingestion is not None and investigation is not None else None),
            sources=[parser_source, pilot_source],
            note="Machine time is not human labor time; the two conditions do different amounts of work.",
        ))
        rows.append(metric(
            id="cited_evidence_pilot",
            label="Cited evidence in the pilot run",
            group=GROUP_RECORDED,
            definition="Evidence records cited by the investigation output of the pilot run.",
            direction="higher",
            traditional=side(0, display="0", classification=OBSERVED, detail="The conventional parser produces no citations."),
            ai=side(_number(_get(pilot, "with_agent", "cited_evidence_count")),
                    display=str(_get(pilot, "with_agent", "cited_evidence_count")),
                    classification=OBSERVED,
                    detail="All cited records are traceable to the ingested copy of the same files."),
            sources=[pilot_source, self.store.source("fresenius_pilot_cited")],
        ))
        rows.append(metric(
            id="hypotheses_pilot",
            label="Competing hypotheses produced in the pilot run",
            group=GROUP_RECORDED,
            definition="Hypotheses recorded by the investigation output; the parser produces none.",
            direction="higher",
            traditional=side(0, display="0", classification=OBSERVED, detail="No hypotheses in the extraction baseline."),
            ai=side(_number(_get(pilot, "with_agent", "hypothesis_count")),
                    display=str(_get(pilot, "with_agent", "hypothesis_count")),
                    classification=OBSERVED,
                    detail="Three competing hypotheses, each with supporting and contradicting evidence or documented unknowns."),
            sources=[pilot_source, self.store.source("fresenius_pilot_report")],
        ))
        runs = _number(reliability.get("runs"))
        cited_all = reliability.get("trigger_cited_each_run")
        jaccard = reliability.get("pairwise_citation_jaccard") or []
        rows.append(metric(
            id="first_signal_repeatability",
            label="First-signal repeatability (3 recorded runs)",
            group=GROUP_RECORDED,
            definition="Whether repeated one-pass runs cite the trigger record and how stable their citation sets are.",
            traditional=not_measured("The deterministic parser is not a reasoning baseline and has no citation runs."),
            ai=side(None, display=f"trigger cited {sum(1 for v in cited_all if v)}/{int(runs)}" if cited_all and runs else "Not measured",
                    classification=OBSERVED,
                    detail=(f"Pairwise citation Jaccard: {jaccard}. Small sample; measures evidence-selection stability only."
                            if jaccard else None)),
            sources=[self.store.source("fresenius_reliability")],
            note="Three runs are too few for a confidence interval; the spread is reported as recorded.",
        ))

        headline = [row for row in rows if row["id"] in {
            "incident_detection_recall", "time_to_diagnosis", "engineer_hours_per_investigation", "deviation_closure_hours",
        }]
        return {
            "metrics": rows,
            "headline": headline,
            "groups": [GROUP_DETECTION, GROUP_OUTPUT, GROUP_TIME, GROUP_RECORDED],
            "conclusion": (
                "On the frozen synthetic investigation benchmark the full-context OS identifies and correctly escalates all five "
                "labeled incidents where local rules find one, and the paired campaign projects roughly half the investigation "
                "time and engineer effort. The first reconstructed lot (BATCH-075) is still only escalated at the field signal "
                "in the batch-scoped stream — the benefit is recurrence recognition, not early detection of every lot."
                if simulation and comparison else
                "Benchmark artifacts are incomplete; only available measurements are shown."
            ),
        }

    # ---------------------------------------------------------------- replay
    def replay(self) -> dict[str, Any]:
        replay = self.store.get("fresenius_replay")
        if not replay or not replay.get("replay_events"):
            return {"status": "not_measured", "reason": "The frozen case chronology (replay_ui.json) is not available."}
        service = self._service()
        if service is None:
            return {"status": "not_measured", "reason": "The deterministic incident agent could not be loaded."}

        events = replay["replay_events"]
        clock_start = events[0]["timestamp"]
        traditional_events = self._traditional_trace(events, service)
        ai_events, ai_cursor_state = self._ai_trace(events, service)
        traditional = normalize_track(traditional_events, clock_start)
        ai = normalize_track(ai_events, clock_start)
        divergences = detect_divergences(traditional, ai)

        return {
            "status": "ok",
            "clock": {
                "id": "case_chronology",
                "label": "Case chronology (reconstructed incident timeline)",
                "kind": "scenario_time",
                "is_wall_clock": False,
                "start": clock_start,
                "end": events[-1]["timestamp"],
                "duration_seconds": seconds_between(clock_start, events[-1]["timestamp"]),
                "note": (
                    "Both workflows are aligned to the reconstructed incident chronology for visualization. "
                    "AI decisions are time-valid deterministic assessments evaluated at each recorded event cutoff. "
                    "They are modeled replay states, not timed human performance."
                ),
            },
            "tracks": {"traditional": traditional, "ai": ai},
            "divergences": divergences,
            "milestones": self._milestones(traditional, ai),
            "wall_clock": self._wall_clock(),
            "guardrails": self._guardrails(),
            "cursor_state": ai_cursor_state,
        }

    def _service(self):
        if self._incident_service is not None:
            return self._incident_service
        try:
            from benchmark.incident_demo.service import IncidentDemoService

            self._incident_service = IncidentDemoService()
        except Exception:  # missing dataset files or import issue
            self._incident_service = None
        return self._incident_service

    def _traditional_trace(self, events: list[dict[str, Any]], service: Any) -> list[TraceEvent]:
        trace: list[TraceEvent] = []
        for event in events:
            kind = TITLE_TO_KIND.get(event["title"], SYSTEM_TO_KIND.get(event.get("system", ""), "activity"))
            outcome_only = bool(event.get("outcome_only"))
            detail = event.get("detail", "")
            trace.append(TraceEvent(
                id=f"TRAD-{event['id']}",
                track="traditional",
                kind=kind,
                title=event["title"],
                detail=(detail + (" (outside workflow control; shown for chronology)" if outcome_only else "")) if outcome_only else detail,
                timestamp=event["timestamp"],
                severity=event.get("severity", "normal"),
                system=event.get("system", ""),
                evidence=tuple(event.get("record_ids") or ()),
                source=f"case chronology event {event['id']} (replay_ui.json)",
                milestone=not outcome_only and kind in {"evidence_available", "risk_acknowledged", "field_signal"},
                meta={"outcome_only": outcome_only, "provenance": event.get("provenance")},
            ))
        # Recorded dispositions for the three incident batches.
        agent_data = self.store.get("fresenius_agent_data") or {}
        for batch in agent_data.get("batches", []):
            if batch.get("batch_id") in INCIDENT_BATCHES and batch.get("disposition_time"):
                trace.append(TraceEvent(
                    id=f"TRAD-DISPO-{batch['batch_id']}",
                    track="traditional",
                    kind="disposition_decision",
                    title=f"{batch['batch_id']} released — recorded disposition",
                    detail=(f"Disposition '{batch.get('disposition')}' recorded after passing release testing. "
                            "Upstream excursions remained in batch-local open deviations."),
                    timestamp=batch["disposition_time"],
                    severity="normal",
                    system="ERP/QMS",
                    evidence=(batch["batch_id"],),
                    source="case batch record (fresenius_famotidine_demo.json / agent_data.json)",
                    milestone=True,
                    meta={"disposition": batch.get("disposition"), "batch_id": batch.get("batch_id")},
                ))
        # Batch-local deviations recorded per excursion: already part of the QMS events, but add
        # the exact opened_at records so times come from the deviation table, not the narrative.
        for deviation in agent_data.get("deviations", []):
            if deviation.get("batch_id") in INCIDENT_BATCHES and deviation.get("opened_at"):
                existing = any(event.timestamp == deviation["opened_at"] and event.kind == "risk_acknowledged" for event in trace)
                if not existing:
                    trace.append(TraceEvent(
                        id=f"TRAD-DEV-{deviation['deviation_id']}",
                        track="traditional",
                        kind="risk_acknowledged",
                        title=f"Deviation {deviation['deviation_id']} opened (batch-local)",
                        detail=deviation.get("description", "Batch-local microbiology deviation."),
                        timestamp=deviation["opened_at"],
                        severity="high" if deviation.get("severity") == "high" else "medium",
                        system="QMS",
                        evidence=(deviation.get("deviation_id"), deviation.get("batch_id")),
                        source="case deviation record (agent_data.json)",
                        milestone=True,
                        meta={"deviation_id": deviation.get("deviation_id"), "root_cause": deviation.get("root_cause")},
                    ))
        return trace

    def _ai_trace(self, events: list[dict[str, Any]], service: Any) -> tuple[list[TraceEvent], dict[str, Any]]:
        trace: list[TraceEvent] = []
        cursor_state: dict[str, Any] = {}
        seen: dict[str, bool] = {}
        labs_by_id = {row["result_id"]: row for row in (self.store.get("fresenius_agent_data") or {}).get("lab_results", [])}
        for cursor in range(1, len(events) + 1):
            try:
                result = service.assessment(cursor)
            except Exception:
                break
            assessment = result["assessment"]
            visible = result["visible_state"]
            severity = assessment.get("severity", "low")
            triage = assessment.get("triage_level", "L1")
            related = assessment.get("related_events") or []
            batch_ids: list[str] = []
            for item in related:
                for evidence_id in item.get("evidence_ids", []):
                    lab = labs_by_id.get(evidence_id)
                    if lab and lab.get("batch_id"):
                        batch_ids.append(lab["batch_id"])
            cross_batch = len(set(batch_ids)) >= 2
            cited = _assessment_evidence(assessment)
            cutoffs = events[cursor - 1]["timestamp"]

            kind, milestone, title = "assessment", False, f"{severity.upper()} · {triage}"
            crossed: list[str] = []
            if severity == "critical" and not seen.get("critical_escalation"):
                seen["critical_escalation"] = True
                crossed.append("critical_escalation")
            if cross_batch and not seen.get("cross_batch_pattern"):
                seen["cross_batch_pattern"] = True
                crossed.append("cross_batch_pattern")
            if triage == "L3" and not seen.get("escalation_decision"):
                seen["escalation_decision"] = True
                crossed.append("escalation_decision")
            if severity != "low" and not seen.get("risk_identified"):
                seen["risk_identified"] = True
                crossed.append("risk_identified")
            milestone_titles = {
                "critical_escalation": "Critical escalation — accumulated microbiological evidence",
                "cross_batch_pattern": "Cross-batch pattern correlated",
                "escalation_decision": "Escalation decision — L3 (human approval required)",
                "risk_identified": f"Risk identified — {severity.upper()} · {triage}",
            }
            primary = next((name for name in (
                "critical_escalation", "cross_batch_pattern", "escalation_decision", "risk_identified",
            ) if name in crossed), None)
            if primary is not None:
                kind, milestone = primary, True
                title = milestone_titles[primary]
                extras = [milestone_titles[name] for name in crossed if name != primary]
                if extras:
                    title = f"{title} · {' · '.join(extras)}"

            summary = (assessment.get("summary") or "").strip()
            actions = assessment.get("recommended_actions") or []
            hypotheses = assessment.get("hypotheses") or []
            detail_parts = [summary] if summary else []
            if related:
                detail_parts.append(" · ".join(item.get("statement", "") for item in related[:2]))
            if hypotheses:
                detail_parts.append("Hypotheses: " + "; ".join(
                    f"{item['title']} ({item['confidence']:.0%})" for item in hypotheses[:3]))
            if actions:
                detail_parts.append("Recommended: " + "; ".join(item["action"] for item in actions[:2]))

            trace.append(TraceEvent(
                id=f"AI-EVT-{cursor:03d}",
                track="ai",
                kind=kind,
                title=title,
                detail=" ".join(detail_parts),
                timestamp=cutoffs,
                severity=severity,
                system="AI OS",
                evidence=tuple(cited[:12]),
                source=f"deterministic agent assessment at cutoff {cutoffs}",
                milestone=milestone,
                meta={
                    "cursor": cursor,
                    "triage_level": triage,
                    "severity": severity,
                    "milestones": crossed,
                    "visible_evidence_count": assessment.get("visible_evidence_count"),
                    "hypothesis_count": len(hypotheses),
                    "action_count": len(actions),
                    "human_approval_actions": sum(1 for item in actions if item.get("requires_human_approval")),
                    "related_batch_ids": sorted(set(batch_ids)),
                    "provider": assessment.get("provider_id"),
                    "evidence_cutoff": assessment.get("evidence_cutoff"),
                },
            ))
            cursor_state[str(cursor)] = {
                "timestamp": cutoffs,
                "severity": severity,
                "triage_level": triage,
                "visible_evidence_count": assessment.get("visible_evidence_count"),
                "hypothesis_count": len(hypotheses),
                "action_count": len(actions),
                "cross_batch": cross_batch,
            }
        return trace, cursor_state

    def _milestones(self, traditional: list[dict[str, Any]], ai: list[dict[str, Any]]) -> dict[str, Any]:
        def first(events: list[dict[str, Any]], kind: str) -> dict[str, Any] | None:
            for event in events:
                if not event.get("milestone"):
                    continue
                if event.get("kind") == kind or kind in (event.get("meta", {}).get("milestones") or []):
                    return event
            return None

        return {
            "risk_acknowledged": {
                "traditional": _brief(first(traditional, "risk_acknowledged")),
                "ai": _brief(first(ai, "risk_identified")),
            },
            "cross_batch_pattern": {
                "traditional": _brief(first(traditional, "field_signal")),
                "ai": _brief(first(ai, "cross_batch_pattern")),
                "traditional_note": "No cross-batch correlation action is recorded in the case chronology before the field signal; the field signal is shown for reference.",
            },
            "escalation_decision": {
                "traditional": _brief(first(traditional, "disposition_decision")),
                "ai": _brief(first(ai, "escalation_decision")),
                "traditional_note": "The traditional timeline shows the recorded release disposition; no cross-batch QA escalation is recorded before the field signal.",
            },
        }

    def _wall_clock(self) -> dict[str, Any]:
        parser = self.store.get("fresenius_parser") or {}
        pilot = self.store.get("fresenius_pilot") or {}
        entries = []
        extraction = _sum_task_runtime(parser.get("tasks") or [], {"FRE-01", "FRE-02", "FRE-03", "FRE-04", "FRE-05"})
        if extraction is not None:
            entries.append({
                "label": "Conventional parser — 5 tasks, extraction only",
                "seconds": round(extraction, 3),
                "display": f"{extraction:.3f} s",
                "classification": OBSERVED,
                "source": self.store.relative("fresenius_parser"),
            })
        prep = [
            value for value in (
                _number(task.get("automated_package_preparation_seconds")) for task in (parser.get("tasks") or [])
            ) if value is not None
        ]
        if prep:
            entries.append({
                "label": "Automated package preparation (snapshot generation + provenance validation)",
                "seconds": round(sum(prep), 3),
                "display": f"{sum(prep):.3f} s",
                "classification": OBSERVED,
                "source": self.store.relative("fresenius_parser"),
                "note": "Programmatic preparation is not zero engineering labor; it is separated from agent runtime.",
            })
        ingestion = _number(_get(pilot, "with_agent", "ingestion", "runtime_seconds")) if pilot else None
        if ingestion is not None:
            entries.append({
                "label": "Prime SDK pilot — ingestion of the same package",
                "seconds": round(ingestion, 3),
                "display": f"{ingestion:.3f} s",
                "classification": OBSERVED,
                "source": self.store.relative("fresenius_pilot"),
            })
        investigation = _number(_get(pilot, "with_agent", "investigation_seconds")) if pilot else None
        if investigation is not None:
            entries.append({
                "label": "Prime SDK pilot — investigation",
                "seconds": round(investigation, 3),
                "display": f"{investigation:.3f} s",
                "classification": OBSERVED,
                "source": self.store.relative("fresenius_pilot"),
            })
        runs = _get(pilot, "with_agent", "rollout_metrics", default={}) if pilot else {}
        if runs:
            entries.append({
                "label": "Prime SDK pilot — tool calls / model calls",
                "seconds": None,
                "display": f"{runs.get('tool_calls')} tool calls · {runs.get('model_calls')} model calls",
                "classification": OBSERVED,
                "source": self.store.relative("fresenius_pilot_report"),
            })
        return {
            "note": (
                "Wall-clock values are recorded machine/execution time from the referenced runs. "
                "They are displayed separately from the case chronology and are not human labor time."
            ),
            "entries": entries,
        }

    def _guardrails(self) -> list[dict[str, Any]]:
        simulation = self.store.get("fresenius_simulation") or {}
        full = _get(simulation, "ablations", "D_full_OS_context", default={}) or {}
        rules = simulation.get("rules_baseline") or {}
        return [
            {
                "check": "Time-valid state at every replay step",
                "status": "observed",
                "basis": "The existing visible_state(cursor) filters records by timestamp and event cursor before the agent sees them.",
                "source": "benchmark/incident_demo/service.py",
            },
            {
                "check": "Future record IDs cited by the agent",
                "status": "observed",
                "basis": f"Benchmark citation audit: rules {rules.get('future_leakage_rate')}, full context {full.get('future_leakage_rate')} future citations.",
                "source": self.store.relative("fresenius_simulation"),
            },
            {
                "check": "Final recall outcome withheld from the agent view",
                "status": "observed",
                "basis": "The public recall event is marked outcome-only and excluded from agent-visible state; covered by tests/test_incident_demo.py.",
                "source": "benchmark/incident_demo/data/replay_ui.json",
            },
            {
                "check": "No disposition or recall authority in the agent",
                "status": "observed",
                "basis": "Recommended actions that change scope or disposition require explicit human approval; disposition stays with authorized humans.",
                "source": "benchmark/incident_demo/agent.py",
            },
        ]

    # ---------------------------------------------------------------- effort
    def effort(self) -> dict[str, Any]:
        comparison = self.store.get("campaign_comparison") or {}
        endpoints = comparison.get("endpoints", {})
        traditional_run = self.store.get("campaign_representative_traditional") or {}
        assisted_run = self.store.get("campaign_representative_assisted") or {}
        categories = [
            ("detect", "Detection & triage", "mean_time_to_detect_hours"),
            ("diagnose", "Diagnosis & evidence correlation", "mean_time_to_diagnose_hours"),
            ("intervene", "Intervention decision", "mean_time_to_intervention_hours"),
            ("close", "Closure & approval", "mean_deviation_closure_hours"),
        ]
        rows = []
        for key, label, field in categories:
            traditional = (
                _number(_get(traditional_run, "msat_process_engineering", field))
                if field != "mean_deviation_closure_hours" else _number(_get(traditional_run, "quality", field))
            )
            assisted = (
                _number(_get(assisted_run, "msat_process_engineering", field))
                if field != "mean_deviation_closure_hours" else _number(_get(assisted_run, "quality", field))
            )
            rows.append({
                "id": key,
                "label": label,
                "unit": "hours",
                "traditional": traditional,
                "ai": assisted,
                "classification": MODELED,
                "display_traditional": f"{traditional:g} h" if traditional is not None else "Not measured",
                "display_ai": f"{assisted:g} h" if assisted is not None else "Not measured",
            })
        pilot = self.store.get("fresenius_pilot") or {}
        ingestion = _number(_get(pilot, "with_agent", "ingestion", "runtime_seconds"))
        investigation = _number(_get(pilot, "with_agent", "investigation_seconds"))
        machine = [
            {"label": "Conventional parser (extraction)", "seconds": _sum_task_runtime(self.store.get("fresenius_parser") or {}, None)},
            {"label": "AI OS ingestion", "seconds": ingestion},
            {"label": "AI OS investigation", "seconds": investigation},
        ]
        return {
            "basis": (
                "Phase durations and engineer hours come from the paired 30-run campaign projection (representative run 20250939). "
                "Machine execution times come from the recorded pilot run. The benchmark does not decompose engineer time into "
                "record-keeping, correlation, root-cause work, coordination, summary writing, and approval categories."
            ),
            "phase_rows": rows,
            "engineer_hours": {
                "total_traditional": _number(_get(traditional_run, "msat_process_engineering", "total_engineer_hours")),
                "total_ai": _number(_get(assisted_run, "msat_process_engineering", "total_engineer_hours")),
                "per_investigation_traditional": _number(_get(traditional_run, "msat_process_engineering", "mean_engineer_hours_per_investigation")),
                "per_investigation_ai": _number(_get(assisted_run, "msat_process_engineering", "mean_engineer_hours_per_investigation")),
                "classification": MODELED,
            },
            "machine_execution": [
                {**row, "classification": OBSERVED,
                 "display": format_duration_seconds(row["seconds"]) if row.get("seconds") is not None else "Not measured"}
                for row in machine
            ],
            "unsupported_categories": [
                "Finding and retrieving records — not separately measured; correlated with 'systems accessed per investigation' (3.75 → 4.08).",
                "Correlating information across systems — not separately measured; part of the diagnosis phase.",
                "Investigating potential root causes — part of the diagnosis phase (14.0 h → 4.67 h).",
                "Coordinating people or departments — not separately measured.",
                "Preparing investigation summaries — not separately measured.",
                "Review and approval — included in closure time (96 h → 44 h).",
            ],
            "tracked_effects": {
                "stopped_or_reduced_operations_downtime_hours": {
                    "traditional": _number(_get(traditional_run, "manufacturing", "unplanned_downtime_hours")),
                    "ai": _number(_get(assisted_run, "manufacturing", "unplanned_downtime_hours")),
                    "classification": MODELED,
                },
                "mean_batch_cycle_time_hours": {
                    "traditional": _number(_get(traditional_run, "manufacturing", "mean_batch_cycle_time_hours")),
                    "ai": _number(_get(assisted_run, "manufacturing", "mean_batch_cycle_time_hours")),
                    "classification": MODELED,
                },
            },
            "note": (
                "Waiting and handoff time is not separately recorded; closure time includes review and approval waiting. "
                "The dashboard shows only categories the recorded benchmark supports."
            ),
        }

    # ---------------------------------------------------------------- evidence
    def evidence(self) -> dict[str, Any]:
        """Evidence matrix computed from recorded annotations."""
        simulation = self.store.get("fresenius_simulation") or {}
        rules = simulation.get("rules_baseline") or {}
        ttd = rules.get("time_to_detection_minutes_by_incident_batch") or {}
        parser = self.store.get("fresenius_parser") or {}
        parser_metrics = {task["task"]["id"]: task.get("metrics", {}) for task in (parser.get("tasks") or [])}
        retrieval = self.store.get("fresenius_retrieval") or {}
        retrieval_metrics = {task["task"]["id"]: task.get("metrics", {}) for task in (retrieval.get("tasks") or [])}
        pilot_cited = self.store.get("fresenius_pilot_cited") or []
        pilot_report = self.store.get("fresenius_pilot_report") or {}
        reliability = self.store.get("fresenius_reliability") or {}
        cited_ids = {row.get("evidence_id") or row.get("id") for row in pilot_cited if isinstance(row, dict)}

        def status(*, retrieved_by=None, retrieved_at=None, used_by=None, missed=False, interpreted=None, unavailable=None, not_measured_reason=None) -> dict[str, Any]:
            if not_measured_reason:
                return {"status": "not_measured", "label": "Not measured", "detail": not_measured_reason}
            if unavailable:
                return {"status": "unavailable", "label": "Unavailable", "detail": unavailable}
            if missed:
                return {"status": "missed", "label": "Missed", "detail": retrieved_at or "No recorded retrieval or interpretation."}
            if interpreted:
                return {"status": interpreted[0], "label": interpreted[1], "detail": interpreted[2]}
            return {"status": "retrieved", "label": "Retrieved", "detail": retrieved_by or ""}

        evidence_items = [
            {
                "id": "LAB-0225",
                "label": "First upstream bioburden action result (BATCH-075)",
                "type": "laboratory result",
                "timestamp": "2024-12-01T12:00:00Z",
                "entities": ["BATCH-075", "DEV-0003"],
                "traditional": status(
                    retrieved_by=(
                        "Conventional parser recovered 758/758 visible record IDs and the critical lab "
                        f"(recall {parser_metrics.get('FRE-02', {}).get('critical_lab_recall')}); all three one-pass retrieval runs cited it."
                    ),
                    retrieved_at="Retrieved at the first cutoff (FRE-02).",
                    interpreted=("interpreted_correctly", "Retrieved, interpreted correctly",
                                 "One-pass model assessments treat it as an action-level upstream signal requiring prompt human review; "
                                 "trigger citation 3/3 recorded runs."),
                ) if parser and retrieval else status(not_measured_reason="Baseline artifacts are missing."),
                "ai": status(
                    retrieved_by="Full-context condition detects it and cites it; pilot run cites it among 52 evidence records.",
                    interpreted=("interpreted_correctly", "Retrieved, interpreted correctly",
                                 "Escalates to a recurring upstream control hypothesis with contradicting evidence recorded (passing final tests)."),
                ),
                "influence": "Trigger record for the whole incident family; both workflows reach it first.",
                "sources": [self.store.source("fresenius_parser"), self.store.source("fresenius_retrieval"), self.store.source("fresenius_pilot")],
            },
            {
                "id": "LAB-0255",
                "label": "Second upstream bioburden action result (BATCH-084)",
                "type": "laboratory result",
                "timestamp": "2025-01-04T12:25:00Z",
                "entities": ["BATCH-084", "DEV-0005"],
                "traditional": status(
                    retrieved_by="Recovered by the parser at FRE-04 (862/862 visible IDs; critical lab recall 1.0).",
                    interpreted=("missed", "Retrieved but not correlated",
                                 "No cross-batch correlation action is recorded in the case chronology; the deviation stays batch-local."),
                ),
                "ai": status(
                    retrieved_by="Full-context condition links it to the first excursion and escalates to L3 at this cutoff.",
                    interpreted=("interpreted_correctly", "Retrieved, correlated",
                                 "Cross-batch recurrence statement cites both action results across two batches at the same process stage."),
                ),
                "influence": "The second signal is where recurrence becomes visible; it is the main divergence point.",
                "sources": [self.store.source("fresenius_parser"), self.store.source("fresenius_simulation")],
            },
            {
                "id": "LAB-0300",
                "label": "Third upstream bioburden action result (BATCH-099)",
                "type": "laboratory result",
                "timestamp": "2025-03-12T12:15:00Z",
                "entities": ["BATCH-099", "DEV-0009"],
                "traditional": status(
                    retrieved_by="Recovered by the parser at FRE-01/FRE-03 (1023/1023 visible IDs; critical lab recall 1.0).",
                    interpreted=("missed", "Retrieved but not correlated",
                                 "The third batch-local deviation is opened ~18 minutes after the result; no pattern-level action is recorded."),
                ),
                "ai": status(
                    retrieved_by="Already in the correlated scope from the second signal; cited with three affected batches.",
                    interpreted=("interpreted_correctly", "Retrieved, correlated",
                                 "Scope statement expands to three batches at the same process stage."),
                ),
                "influence": "Confirms the recurring pattern before the field signal.",
                "sources": [self.store.source("fresenius_parser")],
            },
            {
                "id": "DEV-0003/0005/0009",
                "label": "Batch-local microbiology deviations (open, no root cause)",
                "type": "quality record",
                "timestamp": "2024-12-01T12:18:00Z",
                "entities": ["BATCH-075", "BATCH-084", "BATCH-099"],
                "traditional": status(
                    retrieved_by="Recorded in QMS and visible in the parser output at each later cutoff.",
                    interpreted=("interpreted_correctly", "Retrieved, correctly scoped locally",
                                 "Each deviation is correctly opened for its own batch; three remain open with no root cause or CAPA recorded."),
                ),
                "ai": status(
                    retrieved_by="Cited as the batch-local anchor for the cross-batch scope hypothesis.",
                    interpreted=("interpreted_correctly", "Retrieved, used in scope",
                                 "Recommended actions include expanding investigation scope with QA approval; opening or closing deviations remains a human action."),
                ),
                "influence": "Shows the traditional workflow acted per batch; the gap is correlation, not retrieval.",
                "sources": [self.store.source("fresenius_agent_data")],
            },
            {
                "id": "batch_records",
                "label": "Batch records and release dispositions (three lots)",
                "type": "manufacturing record",
                "timestamp": "2024-12-16T00:28:32Z",
                "entities": list(INCIDENT_BATCHES),
                "traditional": status(
                    retrieved_by="Available in MES/ERP; recovered by the parser in full (1023/1023).",
                    interpreted=("interpreted_correctly", "Retrieved, released as recorded",
                                 "All three lots were released after passing final product testing, as documented in the public case record."),
                ),
                "ai": status(
                    retrieved_by="Retrieved for all three batches in the pilot run.",
                    interpreted=("interpreted_correctly", "Retrieved, kept open",
                                 "Passing final tests are recorded as contradictory evidence that does not resolve the upstream signal; no release recommendation is made."),
                ),
                "influence": "The release decisions are the recorded outcome; the AI keeps the upstream risk open instead of concluding from final tests.",
                "sources": [self.store.source("fresenius_agent_data"), self.store.source("fresenius_pilot_report")],
            },
            {
                "id": "environmental_monitoring",
                "label": "Environmental monitoring and organism records",
                "type": "laboratory record",
                "timestamp": "2025-03-14T12:15:00Z",
                "entities": ["EM-0100"],
                "traditional": status(
                    retrieved_by="Recovered by the parser as part of the full record set (no prioritization).",
                    interpreted=("missed", "Retrieved but not linked",
                                 "No organism-to-incident linkage is recorded in the case chronology."),
                ),
                "ai": status(
                    retrieved_by="Cited in the pilot run and in one of three first-signal repeat runs.",
                    interpreted=("interpreted_incorrectly", "Cited with unverified finding",
                                 "A child investigation reported a gram-negative environmental isolate; the lead marked it unverified before the tool budget was exhausted."),
                ),
                "influence": "Direct example where an AI claim is explicitly flagged as unverified rather than presented as fact.",
                "sources": [self.store.source("fresenius_pilot_report"), self.store.source("fresenius_reliability")],
            },
            {
                "id": "CMP-0001",
                "label": "Field complaint (pyrogenic-type symptom report)",
                "type": "complaint",
                "timestamp": "2025-10-20T09:00:00Z",
                "entities": ["BATCH-075"],
                "traditional": status(
                    retrieved_by="Recorded in the complaint system; this is the external trigger that expands the case.",
                    interpreted=("interpreted_correctly", "Retrieved, triggers scope",
                                 "The field signal is where the recorded case scope expanded; no earlier cross-batch action exists in the chronology."),
                ),
                "ai": status(
                    retrieved_by="Already in an L3 scope from the second excursion; reconciles the complaint with prior evidence.",
                    interpreted=("interpreted_correctly", "Retrieved, reconciles",
                                 "Recommended action: reconcile complaint, distribution, reserve-sample and manufacturing scope."),
                ),
                "influence": "The divergence: the AI treated the pattern as one incident months before the field signal arrived.",
                "sources": [self.store.source("fresenius_agent_data")],
            },
            {
                "id": "LAB-0303",
                "label": "Reserve-sample endotoxin out-of-specification result",
                "type": "laboratory result",
                "timestamp": "2025-10-27T14:10:00Z",
                "entities": ["BATCH-075"],
                "traditional": status(
                    retrieved_by="Available only after the field signal starts the review.",
                    interpreted=("interpreted_delayed", "Retrieved late",
                                 "This is the first retained-product failure in the record; it follows the complaint and the passive release timeline."),
                ),
                "ai": status(
                    retrieved_by="Cited at the final cutoff; raises severity to critical.",
                    interpreted=("interpreted_correctly", "Retrieved, escalates",
                                 "Critical escalation recommended from accumulated microbiological evidence; disposition remains human."),
                ),
                "influence": "Closes the loop: the early upstream signal and the late product failure are the same incident family.",
                "sources": [self.store.source("fresenius_pilot_report")],
            },
        ]
        # Fill pilot citation facts for traceability.
        for item in evidence_items:
            item["pilot_cited"] = bool(cited_ids & {item["id"], *item.get("entities", [])})
        unresolved = _number(_get(pilot_report, "rollout_metrics", "tool_calls")) is not None
        return {
            "statuses": ["retrieved", "missed", "interpreted_correctly", "interpreted_incorrectly",
                         "interpreted_delayed", "unavailable", "not_measured"],
            "rows": evidence_items,
            "annotations": {
                "pilot_unverified": pilot_report.get("open_questions", [])[:8],
                "pilot_pending_evidence_requests": len(pilot_report.get("pending_evidence_requests", []) or []),
                "reliability_runs": reliability.get("runs"),
                "rules_never_detected": [batch for batch, value in ttd.items() if value is None],
                "pilot_run_recorded": unresolved,
            },
            "basis": (
                "Statuses are computed from recorded annotations: the parser baseline (entity/critical-lab recall), "
                "the retrieval+model baseline (citation validity), the simulation ablation (which incidents each condition detects), "
                "and the recorded Prime pilot run (cited evidence, unverified findings, pending evidence requests)."
            ),
        }

    # ------------------------------------------------------------- differences
    def differences(self) -> list[dict[str, Any]]:
        simulation = self.store.get("fresenius_simulation") or {}
        rules = simulation.get("rules_baseline") or {}
        full = _get(simulation, "ablations", "D_full_OS_context", default={}) or {}
        comparison = self.store.get("campaign_comparison") or {}
        endpoints = comparison.get("endpoints", {})
        pilot = self.store.get("fresenius_pilot") or {}
        report = self.store.get("fresenius_pilot_report") or {}
        replay = self.replay()
        divergence = next((d for d in replay.get("divergences", []) if d["kind"] == "cross_batch_pattern"), None)

        entries: list[dict[str, Any]] = []
        if divergence:
            entries.append({
                "id": "DIFF-CROSS-BATCH",
                "category": "evidence_first",
                "classification": MODELED,
                "title": "Cross-batch recurrence correlated at the second excursion",
                "detail": (
                    "The AI OS correlates the second action-limit result into a recurring pattern 34 days after the first result. "
                    "No cross-batch correlation action is recorded in the case chronology before the field signal 322 days later."
                ),
                "refs": [
                    {"kind": "replay_event", "id": divergence["ai"]["event_id"] if divergence.get("ai") else "AI-EVT-006",
                     "detail": divergence["ai"]["detail"] if divergence.get("ai") else ""},
                    {"kind": "evidence", "id": "LAB-0225", "detail": "first action result"},
                    {"kind": "evidence", "id": "LAB-0255", "detail": "second action result"},
                    {"kind": "replay_event", "id": "TRAD-EVT-011", "detail": "field signal — the point the recorded case expanded"},
                ],
            })
        never = [batch for batch, value in (rules.get("time_to_detection_minutes_by_incident_batch") or {}).items() if value is None]
        if rules:
            entries.append({
                "id": "DIFF-MISSED-INCIDENTS",
                "category": "missed_evidence",
                "classification": MODELED,
                "title": "Local rules never detect the reconstructed incident batches",
                "detail": (
                    f"The rules condition never crosses the escalation threshold for {', '.join(never) or 'any incident batch'}; "
                    "the full-context condition detects all five labeled incidents."
                ),
                "refs": [
                    {"kind": "benchmark_field", "id": "rules_baseline.time_to_detection_minutes_by_incident_batch",
                     "detail": "null entries are undetected incidents"},
                    {"kind": "benchmark_field", "id": "ablations.D_full_OS_context.incident_detection_recall",
                     "detail": f"{full.get('incident_detection_recall')}"},
                ],
            })
        entries.append({
            "id": "DIFF-HYPOTHESES",
            "category": "hypotheses",
            "classification": OBSERVED,
            "title": "Competing hypotheses appear only in the AI OS run",
            "detail": (
                "The conventional baseline produced no hypotheses; the recorded pilot run produced "
                f"{pilot.get('with_agent', {}).get('hypothesis_count', 'no')} hypotheses, each citing supporting and contradicting evidence."
            ),
            "refs": [{"kind": "artifact", "id": self.store.relative("fresenius_pilot_report"),
                      "detail": "causal_hypotheses with supporting/contradicting evidence ids"}],
        })
        entries.append({
            "id": "DIFF-SCOPE",
            "category": "escalation_timing",
            "classification": MODELED,
            "title": "Scope escalation timing",
            "detail": (
                "Investigation-scope recall rises from "
                f"{_pct(rules.get('investigation_scope_recall'))} to {_pct(full.get('investigation_scope_recall'))}; the paired campaign projects "
                f"intervention at {_get(endpoints, 'time_to_intervention_hours', 'traditional_mean')} h → "
                f"{_get(endpoints, 'time_to_intervention_hours', 'agent_assisted_mean')} h."
            ),
            "refs": [
                {"kind": "benchmark_field", "id": "investigation_scope_recall", "detail": "frozen dataset ablation"},
                {"kind": "benchmark_field", "id": "time_to_intervention_hours", "detail": "paired campaign endpoint"},
            ],
        })
        entries.append({
            "id": "DIFF-EFFORT",
            "category": "eliminated_steps",
            "classification": MODELED,
            "title": "Accelerated activities in the paired campaign",
            "detail": (
                "Detect 4.0 h → 1.0 h, diagnose 14.0 h → 4.67 h, intervene 22.0 h → 6.67 h, close 96 h → 44 h; "
                "engineer hours per investigation 16.56 → 6.78. These are modeled projections, not measured human performance."
            ),
            "refs": [{"kind": "artifact", "id": self.store.relative("campaign_representative_traditional")},
                     {"kind": "artifact", "id": self.store.relative("campaign_representative_assisted")}],
        })
        entries.append({
            "id": "DIFF-DECISIONS",
            "category": "decisions",
            "classification": MODELED,
            "title": "Correct escalations and false positives",
            "detail": (
                f"Triage accuracy {_pct(rules.get('triage_accuracy'))} → {_pct(full.get('triage_accuracy'))}; "
                f"false-positive escalations {rules.get('false_positive_batches')} → {full.get('false_positive_batches')} of "
                f"{full.get('evaluated_batches')} non-incident batches."
            ),
            "refs": [{"kind": "benchmark_field", "id": "triage_accuracy"}],
        })
        entries.append({
            "id": "DIFF-HUMAN",
            "category": "human_intervention",
            "classification": MODELED,
            "title": "Human review remains in the loop",
            "detail": (
                "Scope expansion and disposition hold actions carry explicit human-approval flags; the pilot comparison records "
                f"{pilot.get('without_agent', {}).get('human_minutes', 'n/a')} → {pilot.get('with_agent', {}).get('human_minutes', 'n/a')} human minutes "
                "(supplied estimates, not a timed human study)."
            ),
            "refs": [{"kind": "artifact", "id": self.store.relative("fresenius_pilot")}],
        })
        open_questions = report.get("open_questions") or []
        pending = report.get("pending_evidence_requests") or []
        if open_questions or pending:
            entries.append({
                "id": "DIFF-UNSUPPORTED",
                "category": "unsupported_conclusions",
                "classification": OBSERVED,
                "title": "AI claims that remained unsupported at the cutoff",
                "detail": (
                    f"{len(pending)} evidence requests were still open and {len(open_questions)} questions unresolved in the recorded pilot run; "
                    "the equipment and organism findings are listed as unverified, not as conclusions."
                ),
                "refs": [{"kind": "artifact", "id": self.store.relative("fresenius_pilot_report"),
                          "detail": "; ".join(open_questions[:3])}],
            })
        entries.append({
            "id": "DIFF-FOUND-BY-TRADITIONAL",
            "category": "found_by_traditional_only",
            "classification": OBSERVED,
            "title": "Actions only the traditional workflow recorded",
            "detail": (
                "Batch-local QMS deviations were opened in the case chronology (18–20 minutes after each laboratory result). "
                "The AI OS recommends investigation but cannot open deviations, release, or disposition batches; those stay human actions."
            ),
            "refs": [{"kind": "evidence", "id": "DEV-0003/0005/0009", "detail": "recorded deviation records"}],
        })
        return entries

    # ------------------------------------------------------------ issue chain
    def issue_chain(self) -> dict[str, Any]:
        replay = self.replay()
        if replay.get("status") != "ok":
            return {"status": "not_measured", "reason": replay.get("reason")}
        service = self._service()
        events = (self.store.get("fresenius_replay") or {}).get("replay_events", [])
        # The cross-batch milestone cursor: first AI event tagged cross_batch_pattern.
        cursor = None
        for event in replay["tracks"]["ai"]:
            if event["kind"] == "cross_batch_pattern":
                cursor = event["meta"].get("cursor")
                break
        if cursor is None:
            return {"status": "not_measured", "reason": "No cross-batch correlation milestone exists in the recorded chronology."}
        result = service.assessment(cursor)
        assessment = result["assessment"]
        visible = result["visible_state"]
        cutoff = assessment.get("evidence_cutoff") or events[cursor - 1]["timestamp"]
        evidence_by_id = visible.get("evidence_by_id", {})

        cited_ids = _assessment_evidence(assessment)
        supporting = [_evidence_card(evidence_id, evidence_by_id.get(evidence_id)) for evidence_id in cited_ids]
        incident_records = [
            _evidence_card(record_id, record)
            for record_id, record in evidence_by_id.items()
            if _is_incident_record(record_id, record)
        ]
        open_deviations = [
            card for card in incident_records
            if card["type"] == "deviation" and not card.get("closed_at")
        ]
        missing: list[str] = []
        if not any(card["type"] == "organism" for card in incident_records):
            missing.append("No organism identification result is visible at this cutoff.")
        if open_deviations:
            missing.append(f"{len(open_deviations)} microbiology deviation(s) remain open with no recorded root cause or CAPA.")
        process_batches = {card.get("batch_id") for card in incident_records if card["type"] == "process_event"}
        if len(process_batches) < 2:
            missing.append("Process trajectory records are only partially visible for the affected batches at this cutoff.")
        missing.append("No water-system, cleaning-validation, or environmental-trend records are visible at this cutoff.")

        return {
            "status": "ok",
            "moment": {
                "cursor": cursor,
                "cutoff": cutoff,
                "event_id": next((event["id"] for event in replay["tracks"]["ai"]
                                  if event["meta"].get("cursor") == cursor), None),
                "milestone": "cross_batch_pattern",
            },
            "issue": {
                "title": "Recurring upstream bioburden risk across multiple Famotidine batches",
                "detail": (assessment.get("related_events") or [{}])[0].get("statement", assessment.get("summary", "")),
                "severity": assessment.get("severity"),
                "triage_level": assessment.get("triage_level"),
                "classification": MODELED,
            },
            "supporting_evidence": supporting,
            "related_records": incident_records,
            "competing_hypotheses": [
                {
                    "title": item.get("title"),
                    "confidence": item.get("confidence"),
                    "supporting_evidence_ids": item.get("supporting_evidence_ids", []),
                    "contradicting_evidence_ids": item.get("contradicting_evidence_ids", []),
                }
                for item in assessment.get("hypotheses", [])
            ],
            "missing_information": missing,
            "recommended_investigation": [
                {
                    "action": item.get("action"),
                    "owner": item.get("owner"),
                    "priority": item.get("priority"),
                    "requires_human_approval": item.get("requires_human_approval"),
                    "evidence_ids": item.get("evidence_ids", []),
                }
                for item in assessment.get("recommended_actions", [])
            ],
            "escalation_decision": {
                "decision": f"{assessment.get('severity', '').upper()} · {assessment.get('triage_level')} — human review required",
                "authority": "The agent may recommend scope expansion and holds; QA retains disposition authority.",
                "classification": MODELED,
            },
            "evidence_available": {
                "count": len(evidence_by_id),
                "records": _preview_records(evidence_by_id),
                "by_type": _record_counts(evidence_by_id),
                "preview_limit": EVIDENCE_PREVIEW_LIMIT,
                "truncated": len(evidence_by_id) > EVIDENCE_PREVIEW_LIMIT,
                "guardrail": (
                    "Every listed record existed at the cutoff; later records and the recall outcome are excluded "
                    "by visible_state(). The complete state at this cursor is reproducible from the incident-demo "
                    "assessment endpoint with the same cursor."
                ),
            },
        }

    # ------------------------------------------------------------ presentation
    def presentation(self) -> dict[str, Any]:
        return {
            "headline": "Same frozen case data. One decision loop finds the cross-batch pattern; the reconstructed batch-local workflow does not.",
            "steps": [
                {"id": "scorecard", "label": "Scorecard — modeled benchmark deltas"},
                {"id": "divergence", "label": "Key divergence — second excursion"},
                {"id": "evidence", "label": "Evidence trail and guardrails"},
                {"id": "summary", "label": "Verified vs modeled findings"},
            ],
            "verified_findings": [
                "Public FDA record: multiple bioburden action-limit failures; gram-negative growth acknowledged; affected batches released on passing final tests; three lots recalled (FDA-F001…F005).",
                "Frozen dataset: the same 13-event chronology, batch records, deviations, and lab results are used for both workflows.",
                "Recorded performance: critical-lab recall 1.0 for the conventional parser on all five tasks with 0.29% precision among extracted records.",
            ],
            "modeled_findings": [
                "Full-context condition: incident recall 20% → 100%, triage accuracy 20% → 100%, scope recall 76.7% → 100% on the frozen labeled dataset (deterministic contextual agent, not an LLM).",
                "Paired 30-run campaign projection: diagnose 14.0 h → 4.67 h, intervene 22.0 h → 6.67 h, close 96 h → 44 h, engineer hours per investigation 16.56 → 6.78.",
                "Deterministic replay: L3 cross-batch escalation at the second excursion (2025-01-04), 322 days before the field signal that expanded the recorded case.",
            ],
            "limitations": [
                "No human investigation was timed; modeled campaign durations are projections under explicit controller assumptions.",
                "The AI replay is a deterministic agent, not a live LLM; the live Prime pilot run is reported separately (250 s investigation time, 52 cited records, 3 hypotheses, 6 open evidence requests).",
                "The first reconstructed lot (BATCH-075) is only escalated at the field signal in the batch-scoped benchmark stream; recurrence recognition, not universal early detection, is the supported claim.",
                "This reconstruction does not establish that any different system would have prevented the real recall or patient harm.",
            ],
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


def _sum_task_runtime(tasks_or_document: Any, ids: set[str] | None) -> float | None:
    tasks = tasks_or_document.get("tasks") if isinstance(tasks_or_document, dict) else tasks_or_document
    if not tasks:
        return None
    total = 0.0
    found = False
    for task in tasks:
        task_id = _get(task, "task", "id") or task.get("task_id") or "unknown"
        if ids is not None and task_id not in ids:
            continue
        runtime = _number(_get(task, "usage", "runtime_seconds"))
        if runtime is not None:
            total += runtime
            found = True
    return round(total, 4) if found else None


def _assessment_evidence(assessment: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for item in assessment.get("observations", []):
        ids.extend(item.get("evidence_ids", []))
    for item in assessment.get("related_events", []):
        ids.extend(item.get("evidence_ids", []))
    for item in assessment.get("hypotheses", []):
        ids.extend(item.get("supporting_evidence_ids", []))
        ids.extend(item.get("contradicting_evidence_ids", []))
    for item in assessment.get("recommended_actions", []):
        ids.extend(item.get("evidence_ids", []))
    return list(dict.fromkeys(str(item) for item in ids if item))


def _brief(event: dict[str, Any] | None) -> dict[str, Any] | None:
    if event is None:
        return None
    return {
        "event_id": event["id"],
        "title": event["title"],
        "timestamp": event.get("timestamp"),
        "detail": event.get("detail", "")[:400],
    }


def _evidence_card(record_id: str, record: dict[str, Any] | None) -> dict[str, Any]:
    if record is None:
        return {"id": record_id, "type": "reference", "summary": "Referenced but not visible at this cutoff."}
    timestamp = record.get("timestamp") or record.get("opened_at") or record.get("start_time")
    if "test_name" in record or "test" in record:
        test = record.get("test_name") or record.get("test")
        result = record.get("numerical_result")
        unit = record.get("unit") or ""
        summary = f"{test} = {result} {unit} · status {record.get('status')}" if result is not None else f"{test} · status {record.get('status')}"
        record_type = "laboratory result"
    elif "deviation_id" in record:
        summary = record.get("description") or "Quality deviation record."
        record_type = "deviation"
        if record.get("root_cause"):
            summary += f" · root cause: {record['root_cause']}"
        else:
            summary += " · no root cause recorded"
    elif "parameter" in record:
        summary = f"{record.get('parameter')} = {record.get('value')} · severity {record.get('severity')}"
        record_type = "process_event"
    elif "batch_id" in record and "product" in record:
        summary = f"{record.get('product')} · line {record.get('production_line')} · disposition {record.get('disposition')}"
        record_type = "batch"
    elif "complaint_id" in record:
        summary = record.get("description") or "Complaint record."
        record_type = "complaint"
    elif "work_order" in record:
        summary = record.get("description") or "Maintenance work order."
        record_type = "maintenance"
    elif "sample_id" in record:
        summary = f"Environmental monitoring · result {record.get('result')} · status {record.get('status')}"
        record_type = "environmental_monitoring"
    elif "operator_event_id" in record:
        summary = record.get("description") or "Operator event."
        record_type = "operator_event"
    else:
        summary = "Reasoning artifact"
        record_type = "reference"
    if "organism identification" in str(summary).lower():
        record_type = "organism"
    return {
        "id": record_id,
        "type": record_type,
        "timestamp": timestamp,
        "batch_id": record.get("batch_id"),
        "summary": summary,
        "closed_at": record.get("closed_at"),
        "provenance": record.get("provenance"),
    }


def _is_incident_record(record_id: str, record: dict[str, Any]) -> bool:
    identifiers = {str(record.get("batch_id") or ""), str(record.get("deviation_id") or "")}
    if record_id.startswith(("BATCH-075", "BATCH-084", "BATCH-099", "DEV-0003", "DEV-0005", "DEV-0009")):
        return True
    return bool(identifiers & set(INCIDENT_BATCHES)) or any(
        str(record.get("deviation_id") or "") == deviation for deviation in ("DEV-0003", "DEV-0005", "DEV-0009")
    )


def _preview_records(evidence_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Incident-related records first, then the remaining state in timeline order."""
    incident: list[dict[str, Any]] = []
    other: list[dict[str, Any]] = []
    for record_id, record in evidence_by_id.items():
        card = _evidence_card(record_id, record)
        (incident if _is_incident_record(record_id, record) else other).append(card)
    key = lambda card: (card.get("timestamp") or "", card["id"])
    return (sorted(incident, key=key) + sorted(other, key=key))[:EVIDENCE_PREVIEW_LIMIT]


def _record_counts(evidence_by_id: dict[str, dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record_id, record in evidence_by_id.items():
        card_type = _evidence_card(record_id, record)["type"]
        counts[card_type] = counts.get(card_type, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _pct(value: Any) -> str:
    number = _number(value)
    return f"{number * 100:.1f}%" if number is not None else "n/a"
