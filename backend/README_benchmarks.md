# Manufacturing OS Benchmark — Evaluation Specification

> **Implementation brief for the coding agent**  
> **Status:** Proposed evaluation design. No accuracy, quality, time-savings, or competitor results are claimed by this document.  
> **Scope:** Upgrade the existing CHO and Fresenius benchmarks and evaluation harness. **Do not redesign or replace the Manufacturing OS agent, RLM, data layer, or existing datasets.**

## 1. Objective

We are building an **AI Operating System for Pharmaceutical Manufacturing**. Its first demonstration must show the same agent taking unfamiliar manufacturing evidence through:

**Raw package → autonomous data preparation → relevant evidence discovery → deviation/process investigation → competing RCA hypotheses → affected-scope assessment → L1/L2/L3 triage → evidence requests and reviewable follow-up actions.**

Our primary evaluation question is:

> **Can the Manufacturing OS produce equivalent or better *correct, reviewable investigation outcomes* with fewer *total human-hours* than the existing workflow?**

**Do not equate faster model responses with labor saved.** Measure setup, ingestion, manual mappings, analysis, evidence review, error correction, and coordination. A fast but incorrect or unverifiable output does not count as a completed investigation.

This benchmark must also expose failures, unanswerable cases, uncertainty, and limitations. It is designed for technical validation and credible public reporting, not a staged demo.

## 2. Preserve what exists

Before changing code:

1. Inspect the repository, existing benchmark entry points, RLM harness, data stores, tool contracts, tests, and artifacts.
2. Reuse existing interfaces and datasets; introduce adapters only when necessary.
3. Preserve immutable copies and checksums of currently validated benchmark assets.
4. Report what is already implemented, what is missing, and every migration required.
5. Never write a new benchmark label to make a current agent prediction appear correct.

**Existing benchmark targets:**

| Dataset | Provenance | What we can defensibly test | What we cannot claim |
|---|---|---|---|
| **CHO** | Authentic laboratory-scale CHO cultivation workbooks; published time-aligned CSVs where available | Automated parsing, experiment/reactor identification, units and timestamps, reconstruction, numerical comparisons, evidence grounding, effort | Validated commercial-scale optimization or verified causal explanations without independent labels |
| **Fresenius** | Existing **synthetic 100-batch reconstruction** informed by public FDA findings | Raw-document extraction, cross-batch linking, chronological deviation detection, evidence-backed investigation, proposed RCA hypotheses, triage against a defined rubric | Access to actual internal Fresenius records, independently verified internal root causes, or proof that the agent would have prevented a recall |

Use **one agent implementation and one evaluation interface** for both; do not hardcode case identities, answers, labels, or dedicated prompts.

## 3. Evaluation units and conditions

The fundamental unit is an **investigation case**, not a document or LLM completion.

Each case has:

- `case_id`, `benchmark_id`, and an engineering **objective**.
- A frozen, versioned **raw evidence package** (files and/or historical snapshots).
- An `as_of` timestamp if chronological replay is involved.
- An allowlist of source paths the agent can inspect.
- A hidden reference manifest for objective checks; hidden materials must be inaccessible to the agent.
- A predefined list of required investigation deliverables and a scoring rubric.
- A documented scope of **answerable**, **partially answerable**, and **unanswerable** questions.

### Conditions

Run the following where supported by the data:

1. **Raw/unprepared:** Original unfamiliar files, no manually supplied sheet-to-variable mappings or case-relevant document list. This is the **primary** product benchmark.
2. **Clean/structured (diagnostic):** Same underlying observations supplied in normalized form. This isolates investigation reasoning from ingestion difficulty; **do not** mix these scores into a raw-input claim.
3. **Unfamiliar/held-out:** New file structures, naming conventions, distracting records, and changes not used to tune prompts. Preserve a hidden transformation manifest.
4. **Updated package:** New or corrected evidence arrives after the first investigation; evaluate whether the agent updates conclusions without repetitive manual setup.
5. **Historical replay (Fresenius):** Reveal only evidence actually available at each chosen timestamp.

Freeze held-out cases **before** the final evaluated run. Repeatedly tuning against the same held-out cases invalidates a generalization claim.

## 4. End-to-end tasks

### 4.1 CHO: Real-data engineering and process comparison

**Agent-visible input:** Original raw Excel workbooks and task objective. Keep the published aligned reference CSVs and evaluation mappings hidden during the raw-input test.

**Tasks:**

- `CHO-01: Inventory and understand` — Identify experiments, cultivations/reactors, sheets, variables, units, and sampling patterns without manual tags.
- `CHO-02: Reconstruct measurements` — Join inline/offline observations and time axes, preserve measured values, deduplicate as appropriate, and retain cell-level provenance.
- `CHO-03: Compare runs` — Quantify process differences with reproducible calculations and transparent assumptions.
- `CHO-04: Investigate variability` — Find supporting/contradictory evidence and offer *hypotheses*, not unsupported proven root causes.
- `CHO-05: Robustness/update` — Repeat under unseen layouts, renaming, relevant new data, and irrelevant noise.

**Objective references:** Published measurements, experimentally documented conditions, and separately checked mappings where available. Specify numeric tolerances; time-alignment outputs may not always match by exact equality.

**Do not compute "RCA accuracy" for CHO** if independently supported causal labels do not exist. Instead score calculation correctness, evidence support, contradictions, and uncertainty.

### 4.2 Fresenius: Deviation, RCA, and triage

**Agent-visible input:** Synthetic manufacturing PDFs, spreadsheets, logs, reports, scans/forms as available, generated from the existing structured 100-batch reconstruction. **Do not pass the underlying canonical JSON or hidden labels directly to the raw-file agent.**

**Tasks:**

- `FRE-01: Autonomous evidence discovery` — Find significant abnormalities among normal and distracting records.
- `FRE-02: First-signal investigation` — At the earliest available meaningful signal, initiate an investigation using only evidence available then.
- `FRE-03: Cross-batch scope` — Reevaluate when additional batches, results, and maintenance/quality evidence arrive.
- `FRE-04: Competing RCA hypotheses` — Cite support **and counterevidence**, specify discriminating checks, preserve unresolved causes.
- `FRE-05: Triage + coordination` — Assign proposed L1/L2/L3 routing according to a **versioned project-specific rubric**, identify missing evidence, and propose appropriate human-reviewed tasks/escalations.
- `FRE-06: Negative controls` — Investigate normal and unrelated abnormal batches; measure false connections and unnecessary escalations.

**Important:** L1/L2/L3 are our *benchmark routing levels*, not universal GMP classifications. Treat hidden simulation incident labels as synthetic assumptions unless independently reviewed. Critical GMP decisions, batch release, CAPA approvals, and physical process changes remain human-authorized.

**Historical integrity:** Enforcement must happen in the storage/tool layer, including file names, metadata, content, and per-field `available_at` as applicable. Do not expose later results, complaints, or FDA findings at earlier replay times. If historical availability is unknown, fail closed for claims depending on it.

## 5. Comparison groups (no fabricated competitor results)

| Group | Workflow | Purpose |
|---|---|---|
| **A. Manual baseline** | Process engineer uses agreed conventional tools (Excel, Python, document readers, etc.) | Measures actual preparation, interpretation, investigation and review effort |
| **B. Conventional software pipeline** | Native parsing, explicit/established mappings, deterministic queries; no autonomous investigator | Isolates benefit of intelligent mapping and investigation |
| **C. Simple AI baseline** | Same permitted raw evidence and parsers, retrieval + single-pass bounded LLM analysis | Tests whether the RLM's recursive execution is worth the overhead |
| **D. Our full Manufacturing OS** | Same raw evidence, manufacturing tools, main RLM, persistent investigation state, RCA/triage | Target system |
| **E. Incumbent product (optional)** | Invert or another product **only if legitimately accessible and capable of the comparable task** | Tests actual competitive performance |

Comparisons must use matched objectives, equivalent *authorized evidence*, the same output-quality rubric, and carefully documented prep/setup conditions. Not all products support the same task; mark unsupported parts **not applicable**, not zero.

**Do not compare our measured output to Invert, Seeq, Aizon, or Leucine marketing claims as though those claims are benchmark results.** Report the competitor as `not_tested` when no fair hands-on comparison exists.

## 6. Quality gates come before efficiency claims

Establish predeclared pass/fail gates **before reviewing evaluated model outputs**. Recommended hard safety/integrity gates:

- No cross-tenant/unauthorized evidence access.
- No future-information leakage in replay.
- No fabricated citations or unverifiable source locations in material findings.
- No unaudited change to original source measurements.
- No autonomous GMP-critical or batch-disposition action.
- No unsupported assertion that a *hypothesized* cause is verified.

Then define with domain reviewers a **minimum acceptable investigation-quality threshold** and acceptable noninferiority margin relative to the manual baseline. Do not invent a universal accuracy threshold for every manufacturing task.

A case counts as **qualified** only if:

1. Its required deliverables exist or it correctly declares the task unanswerable from available evidence.
2. Objective data/evidence checks pass within task-specific tolerances.
3. Its blinded investigation review meets the predeclared minimum.
4. The mandatory integrity and safety gates pass.

An incorrect investigation completed quickly is a **failed case**, not an efficiency win. Separately report qualified-case rate and failure modes.

## 7. Metrics

### 7.1 Data preparation and reconciliation

- File coverage and unsupported-file rate.
- Critical field extraction accuracy (exact match or defined numeric tolerances).
- Experiment/run/batch/equipment/sample linkage precision and recall against verified labels.
- Schema/variable mapping precision and recall, including ambiguous candidates.
- Unit conversion accuracy, timestamp alignment error, and duplicate-record handling.
- Provenance correctness: original source, version, sheet/cell, PDF page/region, log line, or equivalent.
- Contradictions surfaced, silent misjoins, and number of manual mapping/correction actions.

### 7.2 Evidence discovery

- **Critical evidence recall** (primary retrieval safety measure where labels exist).
- Evidence precision, relevant source coverage, and irrelevant evidence burden.
- Citation grounding and retrieval ranking metrics.
- Ability to identify missing or unavailable evidence without inventing it.
- Index coverage and inaccessible-evidence accounting.

**Only calculate supervised relevance metrics where independently defensible relevance annotations exist.** In unknown cases, report coverage and reviewer assessments rather than made-up recall labels.

### 7.3 Investigation, RCA, triage

- Deviation detection recall and false-positive rate, given appropriately labeled incidents/negative controls.
- Time to first **defensible investigation initiation**, measured from the first *available* relevant signal.
- Cross-batch affected-scope precision/recall where labels support it.
- Hypothesis evidence support, contradictory-evidence coverage, discriminating follow-up tests, and uncertainty calibration.
- L1/L2/L3 agreement with a **frozen, independently reviewed routing rubric**; also show confusion matrix and unsafe under-escalation rate.
- Completeness/appropriateness of evidence requests, task routing, coordination plans and human approval gates.
- Human-blinded investigation usefulness and scientific plausibility (clearly distinct from objectively known truth).

If the synthetic Fresenius case has *no independently established internal RCA*, do **not** report root-cause accuracy. Score hypothesis quality and evidence handling instead.

### 7.4 Efficiency and cost

Track **active human time** by stage:

```text
H_total = H_setup_amortized
        + H_data_preparation
        + H_investigation
        + H_verification
        + H_corrections
        + H_coordination
        + H_ongoing_configuration
```

- `H_setup_amortized`: initial setup divided across a **declared, measured** number of cases using that setup. Also show the unamortized first-case total.
- `H_ongoing_configuration`: repeated mapping/template/tool maintenance per case.
- Include human time spent on failed attempts, retries, and rework.
- Track `wall_clock_time`, `agent_runtime`, `tokens`, `inference_cost`, `tool_cost`, and `tool_calls` **separately** from human time.

**Primary reported quantities:**

```text
quality_qualified_rate = qualified_cases / all_attempted_cases

human_hours_per_qualified_case =
    (active_human_hours_excluding_setup_across_all_attempts + allocated_setup_and_maintenance)
    / qualified_cases

paired_human_effort_reduction_pct =
    100 * (1 - H_our_workflow / H_baseline_workflow)
```

Only report the paired percentage when comparing **matched, quality-qualified outcomes** and show the paired sample size. Report the all-attempt qualified-case-rate and effort-per-qualified-case metrics alongside any success-only paired time comparison. Do not hide failures by calculating time savings on successes alone. If there are zero qualified cases, report the effort-per-qualified-case metric as **undefined**, not zero. State how setup was allocated and provide first-case and repeat-case figures separately.

**Key distinction:** `20 seconds of model inference` is **not** `2 hours of engineering labor saved`. The latter requires observing a comparable human workflow.

### 7.5 Reliability and generalization

- Repeated-run result variance; unstable mappings and conclusions.
- Held-out-format performance drop relative to known format.
- Performance on package updates without redoing mappings.
- Cost, time, and error behavior under missing fields, contradictory reports, or difficult scans.
- Model retries, recovery outcomes, and unresolved-evidence reporting.

## 8. Instrument the actual work

Add a **trace logger** covering the full workflow, not just RLM completions.

Each event should record at minimum:

```json
{
  "case_id": "FRE-example",
  "run_id": "run-example",
  "actor": "agent|human|pipeline|evaluator",
  "stage": "ingestion|mapping|analysis|verification|investigation|triage|coordination",
  "action": "schema_mapping_reviewed",
  "started_at": "<ISO-8601>",
  "ended_at": "<ISO-8601>",
  "active_human_seconds": 0,
  "source_refs": [],
  "tool": null,
  "status": "success|partial|unresolved|error",
  "error_code": null,
  "model_id": null,
  "prompt_version": null,
  "input_tokens": null,
  "output_tokens": null,
  "estimated_cost_usd": null
}
```

Actual logs must additionally capture structured outputs, output/evidence IDs, links to correction events, budgets, and relevant environment/version identifiers. The JSON above is a **schema example, not a real run**. Avoid logging proprietary raw source content into general-purpose tracing systems.

For human timing:

- Instrument explicit active-work intervals in the interface where possible.
- Record manual upload/cleanup, mapping, analysis, review and correction actions independently.
- Account for pauses, waiting, and asynchronous coordination separately from active work.
- For manual baseline tasks, use direct observation/timers or an agreed work-log protocol; label self-reported estimates as such.
- Include time required to verify important AI claims; do not treat unreviewed output as completed work.

Use the same stage names and definitions across manual and assisted workflows.

## 9. Human-study protocol

The automatic benchmark scores **technical behavior**, but cannot establish labor savings on its own.

For an initial exploratory pilot, recruit approximately 4–6 process engineers/MSAT scientists, including Parker if available, using **fictional, public, or authorized de-identified data**. No confidential company records are required.

- Use matched tasks at similar difficulty, or have different evaluators work the same frozen case under separate conditions.
- Counterbalance/randomize the order of manual and agent-assisted workflows where possible to mitigate learning effects.
- Document participants' backgrounds, tasks, tools, allowed hints, and time limits.
- Have independent reviewers score the investigation reports **blind to the method** with a versioned rubric.
- Track disagreements among reviewers; use adjudication and report inter-rater agreement where practical.
- Include failed cases and requested clarifications in the outcome report.

**Small-N results are exploratory.** Do not generalize them to all CDMOs or advertise independently validated industry-wide human-hours savings.

## 10. Dataset and evaluation isolation

Require separate read permissions for:

- `agent_input`: original/authorized raw evidence, time-filtered snapshots.
- `reference`: aligned CHO tables, canonical Fresenius records, entity/provenance maps.
- `labels`: incident, scope, triage and evidence annotations.
- `public_outcomes`: later FDA facts used only for retrospective evaluation/presentation.

The agent must not read `reference`, `labels`, or `public_outcomes`. Enforce this at the file and data-access tool boundary, **not solely via prompts**.

For every agent-facing tool, enforce `tenant`, `access_scope`, `as_of`, and permitted source IDs. The ingestion pipeline must not leak future information through document names, metadata, summaries, or search indexes.

Run an automated **leakage and permission audit before scoring**. If it fails, invalidate the run and do not publish scores.

## 11. Benchmark outputs and report structure

Preserve the existing repository layout where possible. Suggested **logical outputs** (not a demand to refactor working paths):

```text
benchmarks/
  README.md                           # This evaluation specification
  manifests/                          # Versioned case/source/condition definitions
  references/                         # Evaluator-only materials
  rubrics/                             # Frozen investigation + triage scoring
  traces/                              # Tool actions and human-effort records
  results/
    cho/
    fresenius/
    comparisons/
  reports/
    cho_report.md
    fresenius_report.md
    effort_report.md
    benchmark_comparison.md
    failure_analysis.md
```

Per-case result must include:

- Dataset/source versions, condition, model/prompt versions, run seed, execution budgets.
- Leakage-audit outcome and qualification gates.
- Data-engineering metrics and extraction/linking examples.
- Evidence retrieval metrics and source references.
- Investigation report, hypotheses/counterevidence, scope and triage outcome.
- Active human time **by stage**, first-case and amortized setup, wall-clock duration, token/tool costs.
- Unsupported claims, failures, unresolved evidence, reviewer scores.

The comparative summary must **not** average CHO and Fresenius into an unexplained universal accuracy score. Present distinct scores and limitations by competency.

## 12. Required evaluation APIs / commands

Adapt to the current codebase rather than inventing a second runner. The benchmark should expose equivalent operations to:

```bash
# Illustrative target CLI; implement or map onto real project commands.
python -m benchmarks.runner inventory --benchmark cho
python -m benchmarks.runner audit --benchmark fresenius --case FRE-02
python -m benchmarks.runner run --benchmark cho --mode conventional --condition raw
python -m benchmarks.runner run --benchmark cho --mode full_rlm --condition raw
python -m benchmarks.runner run --benchmark fresenius --mode full_rlm --condition historical
python -m benchmarks.runner evaluate --run-id <run_id>
python -m benchmarks.runner report --benchmark all
```

Suggested minimal interfaces:

```python
run_case(case_manifest, agent_adapter, condition, trace_sink) -> RunArtifact
score_objective(run_artifact, hidden_reference) -> ObjectiveScores
score_review(run_artifact, rubric, blinded_reviewers) -> ReviewScores
aggregate_effort(run_artifacts, human_logs, allocation_policy) -> EffortReport
produce_comparison(run_ids, quality_policy) -> ComparisonReport
```

Use the existing manufacturing tools and RLM API; instrument them rather than reimplementing them.

## 13. Implementation sequence

**Step 1 — Audit and freeze:** Inventory existing CHO/Fresenius assets, current scores, tool traces, data leakage boundaries, existing benchmark metrics. Freeze manifests and store checksums.

**Step 2 — Add case-based evaluation:** Define `case_id`, objective, input allowlist, historical snapshot, deliverables, reference IDs, evaluation criteria and versions.

**Step 3 — Instrument end-to-end traces:** Capture parsing, mappings, source citations, RLM calls, investigation steps, human interventions, approvals/request status, costs and timing.

**Step 4 — Implement objective scorers:** Extraction, normalization, entity links, reference-grounded retrieval, document citation validity, temporal leakage, deviation/scope/triage where labels exist.

**Step 5 — Implement qualitative review:** Predefine blind investigation-quality rubric; maintain independent reviewers and adjudication; explicitly distinguish hypothesized from established RCA.

**Step 6 — Add honest baselines:** Conventional parser pipeline and single-pass AI first; manual pilot instrumentation next; accessible incumbent products only when fairly runnable.

**Step 7 — Introduce held-out formats and updates:** Evaluate unknown schemas, additional files, revisions and distractors without retuning the agent on the test set.

**Step 8 — Run and report:** Execute actual tests; publish numbers only from successful runs, with failure cases, confidence/uncertainty, limitations and reproducibility manifests.

## 14. Acceptance criteria / automated tests

A coding agent should not mark this done unless the following tests exist and run:

- [ ] Existing CHO and Fresenius benchmarks still execute after changes.
- [ ] The same agent adapter works with both datasets.
- [ ] Hidden reference files and incident labels are inaccessible to agent tools.
- [ ] Historical `as_of` and permission constraints are enforced, including source-document metadata.
- [ ] Structured-file values are scored against independent references with documented tolerances.
- [ ] Source citations resolve to original files, versions and locations.
- [ ] Unverifiable citations and unsupported causal certainty fail the corresponding quality checks.
- [ ] Negative-control batches contribute to false-positive and escalation metrics.
- [ ] L1/L2/L3 uses a frozen benchmark rubric rather than the model grading itself.
- [ ] Data preparation, verification and correction actions are separately timed.
- [ ] Failed attempts contribute to total engineering effort and qualified-case rate.
- [ ] Benchmarks report `not_tested` for inaccessible incumbents and `not_applicable` when reference labels do not exist.
- [ ] Reports clearly distinguish actual results from illustrative assumptions.
- [ ] Repeated runs produce reproducible manifests and comparable metrics.

## 15. Reporting rules for LinkedIn and design partners

We want to credibly say:

> **"We evaluate pharmaceutical manufacturing AI on the work it actually eliminates, not only how quickly it generates an analysis. Our benchmarks include raw-data preparation, unfamiliar investigations, human verification, and scientific correctness."**

That is a **benchmarking principle**, not an already-proven competitive advantage.

We can make a savings claim only when we have measured human effort on a comparable workflow and passed the same quality gate. Name the benchmark data honestly: **real experimental CHO measurements** versus **synthetic, FDA-anchored Fresenius reconstruction**. Do not imply either is confidential commercial factory data or that the agent demonstrably prevented a real event.

## 16. What the coding agent must return

1. Brief repo audit and changes made (reuse vs. new code).
2. Exact run/evaluate/report commands that executed successfully.
3. Passing/failing test summary, including temporal and permission leakage checks.
4. Sample machine-readable per-case results and end-to-end trace.
5. Benchmark comparison report with actual measurements, **N/A** or **not tested** where appropriate.
6. Known limitations, missing labels, missing human-study data and next blockers.

**Final instruction:** Upgrade the evaluation layer first. **Do not replace the existing Manufacturing OS architecture**, re-create the CHO/Fresenius sources, add unneeded infrastructure, or advertise engineering time savings without real measurements. The goal is to expose whether the current system actually removes work *while preserving correct, auditable manufacturing investigations*.
