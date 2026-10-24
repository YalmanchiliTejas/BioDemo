---
status: proposed
---
# Persistent missions separated from reasoning workers

Manufacturing missions persist goals, evidence context, unfinished work and decisions independently of any model session or worker. Retain Prime behind a versioned reasoning interface and use Temporal for production mission scheduling, durable waits and recovery, with domain records outside workflow history. This preserves existing evidence tooling and permits runtime replacement while accepting orchestration/versioning overhead instead of building all multi-day execution semantics ourselves. See D07–D12 in the [decision log](../product/life-sciences-platform/decision-log.md).
