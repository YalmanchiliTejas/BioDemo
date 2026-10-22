"""A small presentation model for the two-case demo, separate from scoring."""
from __future__ import annotations


def _productivity(case: dict) -> dict:
    evaluation = case["evaluation"]
    sides = {}
    for key, outcome in zip(("traditional", "ai"), evaluation["outcomes"]):
        sides[key] = {"value": outcome["hours_per_qualified"], "correctly_completed": outcome["accepted"],
                      "assigned": outcome["assigned"], "person_hours": None}
    return {"label": "Human hours per quality-qualified investigation", "paired": evaluation["paired"], "sides": sides,
            "detail": "Includes setup, preparation, investigation, verification, corrections, coordination and ongoing configuration across all attempts."}



def _days(start: str, end: str) -> int:
    from datetime import datetime
    parse = lambda value: datetime.fromisoformat(value.replace("Z", "+00:00"))
    return (parse(end) - parse(start)).days


def _plant_view(incident, ai: dict, traditional: list[dict]) -> dict | None:
    """Recorded vs projected lot outcomes for a plant-level before/after view.

    The projection applies one explicit assumption: QA accepts the replay's
    cross-batch escalation and holds affected lots that are not yet released.
    """
    escalation = next((e for e in ai.values() if e.get("kind") == "cross_batch_pattern"), None)
    field = next((e for e in traditional if e["kind"] == "field_signal"), None)
    recall = next((e for e in traditional if e["kind"] == "regulatory_outcome"), None)
    reserve = next((e for e in traditional if e["kind"] == "evidence_available"
                    and "Reserve" in e["title"]), None)
    if not (escalation and field):
        return None
    affected = max((e["meta"].get("related_batch_ids", []) for e in ai.values()), key=len)
    batches = {b["batch_id"]: b for b in incident.agent_data["batches"]}
    excursions = {r["batch_id"]: r for r in incident.agent_data["lab_results"]
                  if r["test_name"] == "relative_bioburden_signal" and r["status"] == "action"}
    complaints = incident.agent_data.get("complaints", [])
    at = escalation["timestamp"]
    lots = []
    for batch_id in affected:
        batch, lab = batches.get(batch_id), excursions.get(batch_id)
        if not (batch and lab):
            continue
        shipped_first = batch["first_ship_time"] <= at
        held = batch["disposition_time"] > at
        projected = ("held" if held else "shipped_before_warning" if shipped_first else "released_before_warning")
        lots.append({
            "batch": batch_id, "line": batch["production_line"], "made": batch["start_time"],
            "excursion": {"id": lab["result_id"], "time": lab["timestamp"], "value": lab["numerical_result"]},
            "released": batch["disposition_time"], "shipped": batch["first_ship_time"],
            "complaint": next((c["timestamp"] for c in complaints if c.get("lot") == batch_id), None),
            "recorded": "released_and_shipped", "projected": projected,
        })
    if not lots:
        return None
    held = sum(lot["projected"] == "held" for lot in lots)
    reached = len(lots) - held
    lead = _days(at, field["timestamp"])
    first = min(lot["excursion"]["time"] for lot in lots)
    return {
        "escalation": {"time": at, "id": escalation["id"], "batches": escalation["meta"].get("related_batch_ids", [])},
        "recognized": {"time": field["timestamp"], "id": field["id"]},
        "reserve_failure": {"time": reserve["timestamp"], "id": reserve["id"]} if reserve else None,
        "recall": {"time": recall["timestamp"], "id": recall["id"]} if recall else None,
        "first_signal": first, "lead_days": lead, "lots": lots,
        "kpis": [
            {"label": "Repeat pattern recognized", "before": field["timestamp"][:10], "after": at[:10],
             "before_note": "when a customer complaint arrived", "after_note": "when the second lot failed upstream",
             "delta": f"{lead} days earlier", "kind": "date"},
            {"label": "Flagged lots that reached customers", "before": len(lots), "after": reached,
             "before_note": "all released after passing final tests", "after_note": "shipped before the pattern existed",
             "delta": f"{held} fewer", "kind": "count"},
            {"label": "Flagged lots held for a QA decision", "before": 0, "after": held,
             "before_note": "each closed out on its own", "after_note": "held until the investigation decides",
             "delta": f"+{held}", "kind": "count"},
            {"label": "Investigations running", "before": len(lots), "after": 1,
             "before_note": "separate, batch-by-batch deviations", "after_note": "one linked, cross-batch case",
             "delta": "1 shared case", "kind": "count"},
        ],
        "assumptions": [
            "Data is a synthetic reconstruction informed by public FDA materials, not Fresenius internal records.",
            "The “with agent” track is a deterministic replay. It assumes QA accepts the escalation and holds affected lots that are not yet released.",
            "The agent recommends; people decide. It does not prove the root cause or that the real recall would have been avoided.",
        ],
    }


def build_demo(case: dict) -> dict:
    if case["id"] == "fresenius":
        replay = case["replay"]
        ai = {event["id"]: event for event in replay.get("tracks", {}).get("ai", [])}
        traditional = replay.get("tracks", {}).get("traditional", [])
        definitions = [
            ("AI-EVT-002", "First abnormal result", "Investigate the first excursion",
             "The OS flags the abnormal result for investigation. A recurring pattern is not established yet.",
             "Both workflows see the first signal. The OS keeps the evidence in a connected investigation."),
            ("AI-EVT-006", "Second affected batch", "Connect the pattern across batches",
             "The OS links the repeated microbiological signal and recommends a broader escalation for human approval.",
             "The paths diverge here: the local workflow handles another batch; the OS recognizes recurrence across batches."),
            ("AI-EVT-009", "Third affected batch", "Keep the wider investigation open",
             "The OS maintains the cross-batch risk assessment as a third excursion becomes available.",
             "New evidence extends the same investigation instead of starting another isolated review."),
            ("AI-EVT-010", "Organism identified", "Update the evidence and uncertainty",
             "The OS reassesses the broader microbiological risk using the newly available identification.",
             "The additional evidence is reviewed in the context of the earlier affected batches."),
            ("AI-EVT-011", "Field signal arrives", "Reassess an already escalated pattern",
             "The OS incorporates the field signal into the existing high-risk investigation.",
             "The field signal expands the recorded case; the modeled OS already recognized recurrence at the second excursion."),
            ("AI-EVT-012", "Reserve sample confirms risk", "Recommend critical escalation",
             "Accumulated microbiological evidence leads to a critical escalation recommendation for human review.",
             "Both paths now have stronger evidence. The OS has carried a linked evidence trail through the investigation."),
        ]
        stages = []
        from benchmark.incident_demo import IncidentDemoService
        incident = IncidentDemoService() if ai else None
        for identifier, label, title, detail, divergence in definitions:
            event = ai.get(identifier)
            if event is None:
                continue
            visible = [row for row in traditional if row["timestamp"] <= event["timestamp"]]
            source = visible[-1] if visible else None
            visible_state = incident.visible_state(event["meta"]["cursor"])
            evidence_by_id = visible_state["evidence_by_id"]
            evidence = []
            for evidence_id in event.get("evidence", []):
                record = evidence_by_id.get(evidence_id, {})
                if record.get("test_name") == "relative_bioburden_signal":
                    evidence.append({"id": evidence_id, "batch": record["batch_id"],
                                     "value": record["numerical_result"], "limit": record["action_limit"],
                                     "time": record["timestamp"], "unit": record["unit"],
                                     "basis": "Synthetic source record"})
            evidence.sort(key=lambda row: row["time"])
            # Source excerpts for the visible batches only; future records are
            # excluded by visible_state before this presentation filter.
            relevant_batches = {row["batch"] for row in evidence}
            source_records = []
            for collection in ("lab_results", "deviations", "maintenance", "environmental_monitoring", "complaints"):
                for record in visible_state[collection]:
                    if record.get("batch_id", record.get("linked_batch_id", record.get("lot"))) in relevant_batches:
                        source_records.append({"collection": collection, "record": record})
            batch_ids = event["meta"].get("related_batch_ids", [])
            actions = [row for row in visible if row["kind"] in {"risk_acknowledged", "disposition_decision", "field_signal"}]
            recent_actions = actions[-2:]
            comparison = {
                "evidence": evidence,
                "without": {
                    "title": "Recorded batch-local actions",
                    "scope": "The chronology has no recorded cross-batch escalation at this cutoff."
                             if event["meta"]["cursor"] < 11 else "The field signal has now expanded the recorded case.",
                    "actions": [{"id": row["id"], "text": row["title"], "time": row["timestamp"],
                                 "evidence_ids": row.get("evidence", [])} for row in recent_actions],
                    "decision": "No action recorded yet." if not actions else recent_actions[-1]["detail"],
                    "qualification": "Absence in this reconstructed chronology does not prove what real investigators knew.",
                },
                "with": {
                    "title": "Linked investigation recommendation",
                    "scope": " + ".join(batch_ids) if batch_ids else "Single excursion; recurrence not established.",
                    "actions": [{"id": identifier, "text": f'{event["meta"]["triage_level"]} · {event["severity"]} risk',
                                 "time": event["timestamp"], "evidence_ids": [row["id"] for row in evidence]}],
                    "decision": "Recommend a broader QA-led investigation; human approval required. Root cause remains unconfirmed."
                                if batch_ids else "Investigate the first excursion and seek more evidence; root cause remains unconfirmed.",
                    "qualification": "Deterministic replay output. Use Run agent for a separate live investigation.",
                },
                "change": f'Link {" + ".join(batch_ids)} in one QA-led investigation.' if batch_ids else "No cross-batch divergence established yet.",
                "proof": "This demonstrates a difference in investigation scope in the replay. Human time saved and outcome improvement have not been measured.",
            }
            stages.append({
                "label": label, "time": event["timestamp"], "clock": "Case date",
                "without": {"title": source["title"] if source else "No recorded event",
                            "detail": source["detail"] if source else "No recorded event at this cutoff.",
                            "kind": "Recorded case", "source_ids": [source["id"]] if source else [],
                            "time": source["timestamp"] if source else None},
                "with": {"title": title, "detail": detail, "kind": "Modeled OS replay",
                         "source_ids": [identifier], "time": event["timestamp"]},
                "divergence": divergence, "comparison": comparison, "source_records": source_records,
            })
        return {
            "presentation_version": 7,
            "plant_view": _plant_view(incident, ai, traditional) if incident else None,
            "id": case["id"], "name": "Fresenius Kabi", "title": "The famotidine recall, replayed with the agent on the line.",
            "intro": "Three lots failed an upstream bioburden check over three months. Each passed its final tests and shipped, and the pattern only surfaced when a customer complaint arrived more than ten months after the first failure. Here is the same year without the agent, and projected with it.",
            "badge": "Synthetic reconstruction · projected replay", "clock": "Case chronology · milestones spaced equally",
            "stages": stages, "improvements": [], "productivity": _productivity(case),
            "measurement_note": "The earlier 67% diagnosis-time and 59% effort reductions came from assigned simulation assumptions. They are not evidence of agent productivity.",
            "improvement_note": "Measured engineering productivity is pending. The replay supports an inspectable scope difference, not a measured time-saving claim.",
            "outcome": "The OS connects recurring signals earlier in the reconstructed case and prepares a broader investigation for human review.",
        }

    entries = {row["task"]: row for row in case["replay"]["execution"]["entries"]}
    definitions = [
        ("Raw tables", "Read experimental workbooks", "Extract workbook rows and sheet structure.", "CHO-01",
         "Organize the raw evidence", "Designed to identify experiments, reactors and source measurements in one investigation.",
         "Start from the same raw experimental tables."),
        ("Alignment", "Reconstruct cultivation trajectories", "The conventional pipeline normalizes measurements into cultivation trajectories.", "CHO-02",
         "Link identities, units and time axes", "Designed to align measurements while retaining source references and unresolved gaps.",
         "The intended change is to make alignment and its evidence part of the investigation."),
        ("Analysis", "Engineering interpretation needed", "The parser does not perform the cultivation investigation; this task was not scored.", "CHO-03",
         "Investigate differences", "Designed to compare cultivations and propose evidence-linked explanations with uncertainty.",
         "The intended divergence: move from prepared data to an evidence-linked investigation."),
        ("Validation", "Validate findings separately", "Engineering validation time and decisions were not recorded.", None,
         "Check claims and uncertainty", "Designed to flag constant or confounded channels and withhold unsupported optimization claims.",
         "The intended improvement is fewer unsupported conclusions; this needs a scored comparison."),
        ("Review", "Prepare the engineering review", "End-to-end review and human effort were not measured.", None,
         "Prepare a reviewable comparison", "Designed to present the source evidence, findings and open questions for human approval.",
         "The target is correctly completed work per human-hour, including setup and verification."),
    ]
    stages = []
    for label, title, detail, task, os_title, os_detail, divergence in definitions:
        entry = entries.get(task, {})
        observed = entry.get("seconds") is not None
        comparisons = {
            "Raw tables": ("Workbook rows and sheet structure", "Source-linked experiment and reactor inventory", "Verify every recovered identity against a workbook cell."),
            "Alignment": ("Normalized cultivation trajectories", "Mapping decisions, units and unresolved alignment gaps", "Validate reconstructed values against evaluation references."),
            "Analysis": ("Data reconstruction; no scored engineering interpretation", "An evidence-linked comparison of specific cultivation differences", "Require cited measurements and independent review of each claimed difference."),
            "Validation": ("No recorded claim-validation outcome", "Explicit checks for constant channels, confounding and unsupported causal claims", "Check whether the agent rejects unsupported optimization conclusions."),
            "Review": ("No timed, reviewed end-to-end deliverable", "A reviewable comparison with open questions and traceable calculations", "Measure all setup and review effort; count only accepted deliverables."),
        }
        before, after, check = comparisons[label]
        comparison = {
            "evidence": [],
            "without": {"title": before, "scope": detail, "actions": [], "decision": "Recorded pipeline output" if observed else "Outcome not measured",
                        "qualification": "The conventional parser is not a timed human engineering baseline."},
            "with": {"title": after, "scope": os_detail, "actions": [], "decision": "Proposed output; awaiting a validated agent result",
                     "qualification": "Illustrative workflow, not a recorded OS result."},
            "change": f"Expected output: {after.lower()}.", "proof": check,
        }
        stages.append({"label": label, "time": None, "clock": "Workflow stage",
                       "without": {"title": title, "detail": detail,
                                   "kind": "Recorded pipeline" if observed else "Not measured",
                                   "source_ids": [task] if entry else [], "time": None},
                       "with": {"title": os_title, "detail": os_detail,
                                "kind": "Illustrative OS workflow", "source_ids": [], "time": None},
                       "divergence": divergence, "comparison": comparison})
    return {
        "presentation_version": 7,
        "id": case["id"], "name": "CHO bioprocess", "title": "From experimental tables to a reviewable comparison.",
        "intro": "Follow the work from raw cultivation data through alignment, analysis and engineering review.",
        "badge": "Illustrative workflow · OS comparison not measured", "clock": "Workflow stages · no elapsed time implied",
        "stages": stages, "improvements": [], "productivity": _productivity(case),
        "workload": case["header"]["dataset"], "observation": case["issue_chain"].get("observation"),
        "source_previews": case["evaluation"]["source_previews"],
        "reconstruction": [row for row in case["scorecard"]["metrics"] if row["id"] in {"workbooks_parsed", "source_rows_extracted", "full_series_reconstruction"}],
        "measurement_note": "No paired OS comparison or measured human effort exists for this workflow. An agent report still needs engineering validation.",
        "improvement_note": "Intended improvements, not measured gains. The existing CHO run validates conventional data reconstruction; it does not establish OS productivity or time savings.",
        "outcome": "The proposed OS workflow carries the evidence into analysis and review. A paired run is needed to measure its effect.",
    }
