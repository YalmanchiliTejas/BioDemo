---
name: manufacturing-os
description: Investigate a manufacturing evidence package with Prime Agent's persistent Python kernel and native child agents, using scoped BioDemo data tools and a validated Blackboard report.
---

# Manufacturing OS investigation

Import the Python API in Prime's persistent kernel:

```python
from manufacturing_os import context, inspect_data, search_evidence, verify_evidence, submit_report
case = context()
```

`context()` returns the incident objective, historical cutoff, seed evidence,
current Blackboard, tool names, and remaining tool budget. The bridge fixes the
scope and cutoff; arguments cannot expand them. Available read tools are
`inspect_data`, `infer_schema`, `reconcile_entities`, `normalize_measurements`,
`query_data`, `search_evidence`, `verify_evidence`, `extract_region`,
`get_process_context`, and `get_state_at`. Import any of them from
`manufacturing_os`. Their arguments mirror the ManufacturingTools API:

```python
search_evidence(query="reactor pressure", limit=20)
get_process_context(entity_id="batch-id")
verify_evidence(observation_id="observation-id")
normalize_measurements(observation_ids=["id"], target_unit="milligram/liter")
query_data(sql="SELECT id, name, value_number, unit FROM observations WHERE name = 'pH'", limit=50)
extract_region(source_id="source-id", sheet="Sheet1", row=12, column="Result")
get_state_at(limit=100)
```

Use the kernel to inspect and transform returned evidence. Keep source IDs and
observation IDs with claims. For independent questions, use Prime's native
`rlm.spawn(..., name="...")`; children can use the same skill. Ask children to
send back concise cited findings and contradictions with
`await agent_message.send(..., receiver_role="parent")`. Wait for their replies
before citing their findings. The lead owns synthesis.

The lead must finish by calling `submit_report(report)`. The server rejects
citations that were not supplied as seed evidence or returned by a tool in this
run. Use this shape:

```python
submit_report({
  "assessment": "What the evidence currently supports and what remains unknown",
  "severity": "LOW",  # LOW, MEDIUM, HIGH, CRITICAL
  "evidence_ids": ["observation-id"],
  "findings": [{"statement": "Cited finding", "evidence_ids": ["observation-id"],
                "uncertainties": []}],
  "resolved_questions": [{"question": "What was measured?",
                          "finding": "Source value verified", "evidence_ids": ["observation-id"]}],
  "hypotheses": [{
    "hypothesis_id": "H-1", "statement": "Testable explanation",
    "causal_parent_ids": [], "causal_child_ids": [], "confidence": 0.3,
    "supporting_evidence_ids": ["observation-id"],
    "contradicting_evidence_ids": [], "unknowns": ["Missing evidence"],
    "tests_or_observations_that_would_discriminate": ["Independent check"]
  }],
  "open_questions": ["Missing evidence"],
  "evidence_requests": [{
    "evidence_type": "source review", "target": "batch-id",
    "reason": "Resolve conflict", "priority": "medium",
    "decision_dependency": "scope decision"
  }],
  "tasks": [{
    "owner": "QA", "action": "Review the investigation",
    "priority": "medium", "evidence_ids": ["observation-id"],
    "reason": "Human review is required"
  }],
  "decision_branches": [{
    "decision_id": "D-1", "condition": "Independent check confirms the signal",
    "if_true": [], "if_false": [],
    "actions_available_now": ["Review historical records"],
    "pending_dependencies": []
  }]
})
```

Do not invent observations, use future information, or declare a root cause
confirmed from a candidate hypothesis. `submit_report` creates reviewable
state; it cannot approve or execute regulated actions.
