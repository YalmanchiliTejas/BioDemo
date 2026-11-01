# Actual GLM agent accuracy evaluation

The headline scores come from GLM 5.3 executing tasks through the Prime SDK and
the scoped Manufacturing OS source tools. Deterministic ingestion tests and unit
tests are not substituted for agent predictions. Exact scores and durations are
generated from the final cohort's receipts rather than copied into this handoff.

## Final cohort

The private raw receipts are archived in DagsHub. The checksum-pinned recovery
pointer is `backend/benchmarks/assets/agent-accuracy-20261101.json`; public case
study assets remain local. From `backend/`, restore before running the reproduction
commands below:

```sh
.tools/benchmark-offload/bin/python -m scripts.data_artifacts fetch \
  benchmarks/assets/agent-accuracy-20261101.json results/agent-accuracy-20261101
```

`backend/results/agent-accuracy-20261101/complete/` contains the frozen protocol,
60 case manifests and hidden keys, model admission ledger, actual attempts, source
audits, model logs and summary. It has 15 tasks per workflow, dispatched at
concurrency two with a 120-second isolated agent-worker deadline per task. Measured
durations also include setup, source checks and receipt persistence.

The completed cohort scored **53/60 (88.3%)**: investigations 15/15, deviations
15/15, ingestion 14/15 and scheduling 9/15. Seven failures are retained: five
timeouts and two answer-format failures. One of the format failures ended
with introductory text instead of the requested task answer. All 60 selected executions passed source and OS-isolation checks.

The original admission phase reached 37 tasks; 23 were rejected before any model
usage or generated content. Only those 23 untouched tasks were resumed with the
same frozen inputs and runtime. The merged receipts retain both financial ledgers
and the selection proof; no paid failed attempt was replaced.

- Investigation tasks screen six batch holds against a supplied limit, including
  equal-to-limit and normal controls. They do not establish causal RCA accuracy.
- Deviation tasks flag assays against the explicitly source-labeled current SOP,
  with obsolete bounds as controls. Historical effective-time reconstruction is
  not validated by these fixtures.
- Ingestion tasks ask the agent to normalize CSV values, interpret decimal commas,
  reject unsupported units, handle missing values and route conflicting duplicates.
  They do not measure OCR accuracy.
- Scheduling tasks require a feasible minimum-makespan proposal for four jobs on
  one line, including ready times, precedence, hard due times and maintenance.
  Infeasible inputs are included. Proposals are not dispatched.

Cases are controlled synthetic operational fixtures with developer-authored rules,
not independently adjudicated factory incidents. Data variants share four templates.
All reference keys are independently recomputed from the source CSVs; scheduling
uses a bitmask dynamic program to cross-check the generator's exhaustive permutations.
The resulting `reference-audit.json` is downloadable with the public scores.

The agent returns its own structured answer and supporting observation IDs. Gold
keys stay outside its staged sources and are OS-denied. The deterministic parser
accepts exactly one structured answer, including JSON surrounded by explanatory
prose; it does not interpret prose, call a judge model, select the best of multiple
answers or consult the key while extracting a prediction. Missing, malformed,
timed-out and incorrect answers remain failures. No scored-case success retry is
substituted for an earlier failure.

Task-level answer accuracy is separate from full investigation/QA-report completion.
The native task-response interface is opt-in evaluation instrumentation. Production
investigation mode still requires its existing validated submit_report path. Neither
mode approves a batch release, deviation closure or manufacturing action.

## Retained earlier cohorts

- `workflow-benchmark-20261031/`: component ingestion, deterministic baseline and
  initial full-report attempts. Its 300 ingestion repeats are not agent accuracy.
- `agent-accuracy-20261101/calibration/`: an excluded calibration attempt stopped
  at a conservative admission cap.
- `agent-accuracy-20261101/scored/`: the first report-oriented protocol. Four runs
  reached inference and timed out; subsequent tasks were blocked by admission.
  This is a pipeline diagnostic, not a 60-case model-content accuracy result.
- `agent-accuracy-20261101/native-scored/`: native task answers under the earlier
  strict output parser and task-time setup. Forty-six tasks reached the model;
  fourteen were not admitted. Original adapter failures remain unchanged.
- `agent-accuracy-20261101/recovered-v3/`: offline deterministic recovery of those
  original emitted answers. It recovered 42 answers without inference. An ambiguous
  investigation prompt asked for affected batches while also saying to include
  normal controls, so its investigation percentages are not headline evidence.

The final cohort uses clearer instructions, fresh fixture values, a parser fixed
before execution, and no QA-finalization reserve in task-answer mode. It is reported
separately; no before/after model-uplift claim is made from these protocol changes.

## Performance, costs and limits

Latency covers the local agent pipeline at concurrency two, including tools and
validation. Submitted-answer latency and all-attempt terminal durations are separate.
At fifteen cases per family, nearest-rank p99 is the maximum observed value; it is
not a stable production SLO. Timeouts are not dropped from task correctness.

Each admission phase had a $9 incremental cap, with conservative in-flight
reservations and settlement using provider token counters. Unknown usage retained
its reservation. The completed cohort's settled-token estimate is $5.3338; it is
not a reconciled invoice and can omit requests whose usage was unavailable.
A read-only Modal billing snapshot after completion reported **$15.89 metered**
($15.88891076 LLM tokens), with $0 billed after account credits. This account-level
snapshot includes earlier benchmark diagnostics and is not an isolated cohort
invoice or a promise of free future calls. The $50 ceiling was not exhausted.
No new cloud worker or GPU instance was provisioned.

No independently observed human-effort savings, regulatory compliance, causal
accuracy, production scheduling qualification or factory-wide generalization is
claimed. A qualified reviewer should inspect the task definitions and source
boundaries before reusing these results in manufacturer-facing claims.

## Local presentation and reproduction

The local public `/case-studies/#workflows` tab opens actual-agent accuracy. Its
public files are under `frontend/public/case-study-results/agent-accuracy/`. Only
selected scores, synthetic source rows, predictions, keys and checksums are exported;
credentials, SDK transcripts and raw error logs remain private. Deployment remains
the user's responsibility; no deployment or push was performed.

From `backend/`, to regenerate the completed public artifacts:

```sh
.venv/bin/python scripts/audit_agent_accuracy_references.py \
  --suite results/agent-accuracy-20261101/complete
.venv/bin/python scripts/export_agent_accuracy.py \
  --suite results/agent-accuracy-20261101/complete \
  --output ../frontend/public/case-study-results/agent-accuracy
```

Creating a new paid campaign requires a fresh frozen output directory and accounting
for previous spend; do not reset a ledger or rerun only failed cases for a headline.

The 27-second `walkthrough.mp4` in the public result directory walks through saved
scores and a retained failure. It is visibly labeled as recorded results, not live
inference. Browser QA verified all 60 case records, four download checksums and
390px mobile layout. Ten Python evaluation/proxy tests and eighteen Node runtime
checks passed; TypeScript and whitespace checks passed.
