# Sievance mission evaluations

Implements [the supplied framework](../Sievance_Agent_Evaluation_Complete_README.md) on the current assistant, mission runtime, evidence services and registered tools. Read [IMPLEMENTATION_NOTES.md](IMPLEMENTATION_NOTES.md) for the repository audit and integration decisions.

The unit is an ongoing mission, including different conversations, source events, scheduled work and replacement processes. The runner never calls an LLM to impersonate background execution. It ingests through EvidenceService, then ticks the existing application Runtime; only application code can initiate an assistant turn.

## Setup and run

From the repository root, with Python 3.11+:

```bash
python -m venv .venv-evals
.venv-evals/bin/pip install -e './backend[lifesci-platform]' -r evals/requirements.txt
cp evals/.env.example evals/.env
# Fill in provider configuration; Langfuse and judge configuration are optional.
set -a
source evals/.env
set +a
.venv-evals/bin/python -m evals.runner --suite smoke --output evals/reports/latest.json
.venv-evals/bin/python -m evals.runner --suite mission --output evals/reports/latest.json
.venv-evals/bin/python -m evals.runner --suite memory --output evals/reports/memory.json
```

You may instead pass `--provider-env /path/to/provider.env`. Only allowlisted provider keys are read from that file. Database URLs, production tenants and connector configuration are not loaded. Use a configured model account; calls incur its normal inference cost. Missing credentials produce an explicit unavailable result, not a scripted success.

`--jobs 1..3` runs independent missions concurrently. `--repetitions 1..5` repeats fresh trials; `--variants 1..5` varies public source presentation. Variants are **not** provider random seeds: the existing provider protocol does not expose generation seeds. `--case batch_risk_watch` selects a case. `--compare prior.json` records per-case status changes. Save each report to a new filename if you want to preserve previous summaries; underlying run evidence always gets a unique directory.

Optional `--judge-model MODEL` (or `SIEVANCE_EVAL_JUDGE_MODEL`) runs installed DeepEval retention, completeness, goal, tool, custom UX and applicable RAG metrics. Optional `--simulator-model MODEL` adds a real session driven by DeepEval's ConversationSimulator, with at most three simulated user turns; its outputs still pass through the same application and final hard gates. These options require the selected judge/simulator provider credentials and incur separate calls. Deterministic replay is the default.

Exit codes: **0** all measured checks pass, **1** an observed failure, **2** unavailable required coverage/model. A failing report is a valid evaluation result; a runner exception is reported separately. Advisory judge scores cannot override deterministic failures. Unavailable domain validation, remote export, simulator fidelity and deployment coverage remain visible even when host contracts pass.

## What executes

Three public synthetic worlds seed 12 cases:

- `batch_risk_watch`, `site_transfer_followthrough`, `sop_change_monitor`.
- `blocked_task_resumption`, `blocked_task_remains_blocked`, `tool_failure_recovery`.
- `irrelevant_event_flood`, `cross_tenant_memory_isolation`, `conflicting_source_revision`.
- `approval_boundary`, `scheduled_followup`, `misleading_document`.

A new file-backed SQLite store and random tenant are created for every case, variant and repetition. Every adapter operation runs in a **separate process** with a restricted environment; only the real store retains the agent's state. Opening the second session calls the real conversation service with the existing mission ID. No old transcript or hidden reference is passed to the new session.

The transfer positive control supplies the application's established published/reconstructed example context only at the later specifications event. This permits a real registered calculation, explicitly labeled conditional/synthetic. Other transfer cases retain missing model applicability: capacity alone must not authorize fabricated simulation inputs. These fixtures do not validate a manufacturing model.

Read-only transport failure injection wraps the actual registered tool, once, and preserves a persistent failure counter. All other tool code and outputs remain real. Test writes target only the isolated store; no external notifications, connectors or production dispatch are configured. Per-mission provider/tool admissions, timeline steps, drain steps and subprocess wall time are bounded. A killed/admitted provider request remains charged against the request count even if its outcome is unknown.

## Fixtures and assertions

`fixtures/worlds/*.yaml` contains public structured facts and rendered documents. `fixtures/truth/*.yaml` contains runner-only reference labels and is never ingested, indexed or passed to the agent/simulator. `missions/*.yaml` is the executable scenario definition. Regenerate the checked-in fixtures with `python -m evals.generate_fixtures`.

Assertions cover source-event-to-background correlation, actual new tool work and durable assessments, positive/negative publication behavior, distinct persisted sessions, narrow literal recall, current source revisions, tool prerequisites, simulation execution, recovery, duplicate work, budgets, and forbidden writes/explicit unsafe claims. Unknown assertion names and unordered timestamps are errors. Literal recall and explicit forbidden-phrase checks are deliberately labeled narrow: they do not establish semantic causal/physics correctness.

## Evidence and observability

Each run retains an application database, per-event before/after snapshots, actual tool arguments/results, ranked workspace IDs, model identities/usage, and local observation parent IDs. It does not log hidden chain of thought. Reports contain event timelines, counts/denominators, statuses and outstanding coverage. Zero-denominator ratios are `null`/N/A.

Langfuse is optional until credentials are configured. `evals/.env.example` includes the required fields. Application instrumentation uses supported observation APIs and queue-persisted parent correlation; mission ID is stable metadata while each real conversation has its own session ID. Synthetic eval content capture is explicitly enabled in workers. Production telemetry defaults to metadata only; enable with `LIFESCI_TELEMETRY=langfuse` and install the optional SDK. Local observations never pretend to be Langfuse trace IDs. When configured, remote IDs are verified through the observations API, and deterministic/DeepEval scores are attached to their traces. Export failures retain local evidence and remain visible.

Before using judge scores for a pilot, review at least 3–5 saved judgments against domain-aware expectations. Record verdict agreements/disagreements; no automatic calibration claim is made.

## Tests and practical limits

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest evals/tests backend/tests/lifesci/test_engineering_conversation.py backend/tests/lifesci/test_missions.py -q
```

Tests with FakeProvider are explicitly **scripted contract tests**, not model-quality results. Process persistence tests use actual separate workers and SQLite. GitHub Actions runs contracts without inference credentials; live suites are an explicit operator action.

Scope limits appear in every report: record retrieval has no chunk ranking; reviewed reusable knowledge consolidation/retirement is separate from mission assessments; numerical/causal correctness needs qualified review; external delivery and deployed Temporal/MES/LIMS/QMS paths are not exercised locally. No benchmark result establishes GMP compliance or real factory benefit.
