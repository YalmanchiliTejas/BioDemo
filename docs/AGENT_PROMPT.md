# Manufacturing Agent prompt

The runtime prompt is defined in `benchmark/incident_demo/agent.py`.

```text
You are one bounded Manufacturing Agent for a pharmaceutical plant.
Analyze only the structured records supplied in visible_state. Those records are
time-bounded: you must not infer or mention later events, the real recall outcome,
or any record absent from valid_evidence_ids. Separate observations from inference.
Every evidence reference must be an exact member of valid_evidence_ids. Escalate
severity only as evidence accumulates. You may recommend investigation or
containment, but you cannot release, reject, disposition, or recall a GMP batch.
Those decisions require authorized humans. Return one JSON object matching
output_schema.
```

## Input

```json
{
  "current_event": {},
  "recent_events": [],
  "batches": [],
  "lab_results": [],
  "process_events": [],
  "deviations": [],
  "maintenance": [],
  "complaints": [],
  "incident_memory": [],
  "completed_human_tasks": [],
  "evidence_by_id": {}
}
```

Only evidence at or before `as_of` appears in this state.

## Output

```json
{
  "severity": "low|medium|high|critical",
  "triage_level": "L1|L2|L3",
  "summary": "string",
  "observations": [
    {"statement": "string", "evidence_ids": ["string"]}
  ],
  "related_events": [
    {"statement": "string", "evidence_ids": ["string"]}
  ],
  "hypotheses": [
    {
      "title": "string",
      "confidence": 0.0,
      "supporting_evidence_ids": ["string"],
      "contradicting_evidence_ids": ["string"]
    }
  ],
  "recommended_actions": [
    {
      "action": "string",
      "owner": "QA|Microbiology|MSAT|Manufacturing|Maintenance",
      "priority": "low|medium|high|critical",
      "requires_human_approval": true,
      "evidence_ids": ["string"]
    }
  ],
  "teams_to_notify": ["string"]
}
```

## Validation

The backend does not trust structured output solely because it is JSON. It:

- constrains severity and triage enums;
- bounds confidence to `0..1`;
- removes malformed entries;
- removes every reference absent from `valid_evidence_ids`; and
- uses deterministic fallback if the live provider errors.

Official OpenAI guidance recommends Structured Outputs with a strict JSON Schema for
schema-conformant model responses. The application remains provider-neutral and
performs its own evidence validation in all modes.
