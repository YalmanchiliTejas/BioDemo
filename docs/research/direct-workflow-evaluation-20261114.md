# Evaluating direct workflows and ongoing responsibilities

Date: 2026-11-14. Research, evaluation tooling and proposed coverage. No external benchmark campaign or manufacturing validation is claimed.

The job is to establish whether direct source-backed work, reusable routines and the existing reasoning agent reduce the effort of obtaining a trustworthy result. Follow [Main_Culture_andETHOS.md](../../Main_Culture_andETHOS.md) and the [proactive assistant contract](../product/proactive-assistant-architecture.md). No additional decision model is proposed.

## What the existing evidence establishes

The repository is not entirely synthetic. [Benchmark limitations](../../backend/docs/benchmark_limitations.md) documents authentic CHO workbooks and a fixed-format reconstruction whose 99.905% agreement measures reconstruction against publisher alignment, not autonomous investigation quality. Fresenius exports use synthetic canonical observations. The [manufacturing workflow benchmark](../../backend/docs/manufacturing-workflow-benchmark.md) and [assistant evaluation research](assistant-multi-turn-evaluation-20261102.md) distinguish synthetic fixtures, host-contract tests and limited real-model functional checks. Preserve these distinctions when comparing a new direct path with the assistant.

## Primary-source shortlist

Provenance, task realism and environment realism are separate properties. Sizes below identify a particular published suite; repeated or parameterized tasks do not establish additional independent incident coverage. Sources and access notices checked on 2026-11-14.

| Source | Verified provenance and size | Useful coverage | Access and important limits |
| --- | --- | --- | --- |
| [CHO cultivations](https://zenodo.org/records/20829178) | Real laboratory measurements: 24 cultivations across 12 paired experiments, 48 variables, 0.55–0.8 L working volume. | Ingestion, numerical comparisons, time alignment, source references. | Already present locally; CC-BY-4.0 verified in Zenodo API metadata. Laboratory scale; no reviewed production deviation outcomes. |
| [PRONTO](https://zenodo.org/records/1341583) | Real industrial-scale multiphase-flow testbed, with deliberately induced faults. Process measurements, alarms, operational logs, high-frequency sensors and video; 1.7 GB. | Event replay, detection lead time, false alarms, evidence fusion. | Open, CC-BY-4.0 verified in Zenodo API metadata. Physical process analogue; not pharmaceutical production or naturally occurring incident frequencies. |
| [DABstep paper](https://arxiv.org/html/2506.23719v1), [dataset](https://huggingface.co/datasets/adyen/DABstep) | Authors describe anonymized Adyen operational queries and transaction data; 450 instances expanded from 95 core questions, with simplified business documentation. | Documents plus calculations, precise results, reusable analysis functions. | CC-BY-4.0. Small public developer set; main answers hidden behind official scoring. Financial factoid tasks; split by underlying question family. |
| [BIRD](https://bird-bench.github.io/), [paper](https://arxiv.org/abs/2305.03111) | Real database sources with benchmark-authored questions. Original suite: 12,751 question/SQL pairs, 95 databases, 37 domains. | Structured discovery, joins, dirty values, query correctness and efficiency. | CC-BY-SA-4.0; local SQLite subsets are practical. [Mini-Dev](https://github.com/bird-bench/mini_dev) has changed, including October 2026 corrections: pin its revision. SQL quality does not measure ongoing responsibility or approval behavior. |
| [Spider 2.0](https://github.com/xlang-ai/Spider2) | Enterprise database use cases; original paper has 632 workflow problems. Current Lite lists 547 tasks including 135 SQLite; DBT lists 68 DuckDB tasks. | Schema discovery, documentation, multistep transformations. | MIT repository; upstream data terms remain relevant. Current README reports Snowflake account suspension. Prefer local subsets initially; some gold answers are withheld. Do not add counts across variants. |
| [WorkArena](https://github.com/ServiceNow/WorkArena) | Real ServiceNow interface with constructed tasks/data. Current L1: 33 task types and 19,912 instances; WorkArena++: 682 compositional tasks. [Paper](https://arxiv.org/html/2403.07718v1) describes generated knowledge-base content. | Enterprise forms, filtering, lookup and composed workflows. | Apache-2.0 code; [hosted instances](https://huggingface.co/datasets/ServiceNow/WorkArena-Instances) require approval and prohibit production/sensitive data. Browser-agent completion does not evaluate our UI's usability. |
| [τ²-bench paper](https://arxiv.org/html/2506.07982v1), [repository](https://github.com/sierra-research/tau2-bench) | Simulated users, policies and tools. June 2025 telecom suite: 114 tasks sampled from 2,285 generated compositions. | Clarification, coordination, policy checks, final-state outcomes and repeatability. | MIT; agent/user inference costs apply. Useful behavior regression, not manufacturing realism. Repository warns that newer and older releases are not score-comparable. |
| [OpenRCA v1 paper](https://proceedings.iclr.cc/paper_files/paper/2025/file/d29b8d53678015079e1d245c023e49d2-Paper-Conference.pdf), [repository](https://github.com/microsoft/OpenRCA) | Enterprise telemetry, curated labels and LLM-synthesized questions: 335 cases across three systems, 68.5 GB. | Large evidence retrieval and incident time/component/reason analysis. | MIT code; confirm external data reuse terms. Repository recommends 80 GB storage and 32 GB RAM. Selected observable incidents and software-domain tasks; keep v1 separate from v2. |
| [RCAEval paper](https://arxiv.org/html/2412.17015v1), [repository](https://github.com/phamquiluan/RCAEval) | Real telemetry from injected faults on three running microservice systems: 735 cases, 11 fault types. | Incident evidence retrieval and comparison with conventional diagnostic baselines. | Authors' data/code are MIT; bundled third-party methods vary. Current Parquet release is about 3.4 GB and supports per-case downloads. Raw filenames contain labels: use blind task exports. |

Five immediate choices are CHO, PRONTO, DABstep, a pinned BIRD SQLite subset and a blind RCAEval subset. This is a recommendation, not an executed campaign. Start with small inspected subsets and qualified reference review before admitting paid trials.

[AIOpsLab](https://github.com/microsoft/AIOpsLab) is a later interactive option: deployed microservices, injected faults and generated workloads; its [published suite](https://www.microsoft.com/en-us/research/wp-content/uploads/2024/10/AIOpsLab-672458b635d2d.pdf) has 48 problems. MIT code and Kubernetes/Helm requirements make it heavier than offline replay. [DSBench](https://github.com/LiqiangJing/DSBench) restricts commercial dataset development without written permission, despite an open code repository. [InfiAgent-DABench](https://arxiv.org/html/2401.05507v1) generates questions and constraints using GPT-4. Common [CSTR and Tennessee Eastman benchmarks](https://sites.me.ucsb.edu/~ceweb/faculty/seborg/pdfs/BCJ_ACC05_FINAL.pdf) are simulations. None should be mislabeled as observed pharmaceutical incidents.

## Local direct-task replay

[workspace_tasks_replay.py](../../backend/benchmarks/workspace_tasks_replay.py) runs `Platform.workspace_tasks.execute` with no configured providers and blocks gateway/embedding inference. It accepts local, versioned JSON fixtures; downloads nothing; creates a fresh in-memory store for every task/repeat; and preserves exceptions, mismatches and valid `needs_information` results. Reference expectations are never passed to the task service.

Run the included **two-case synthetic contract smoke fixture** from the repository root:

```sh
PYTHONPATH=backend .venv/bin/python -m benchmarks.workspace_tasks_replay \
  --fixture backend/benchmarks/fixtures/workspace_tasks_smoke/fixture.json \
  --output /private/tmp/workspace-tasks-smoke-report.json \
  --repeats 3
```

Choose a new output path for every run. Exit status is zero only if all supplied checks pass and no inference is attempted. Malformed fixtures or source-hash mismatches fail preflight before tasks execute. The runner does not enforce a wall-time deadline.

The [example fixture](../../backend/benchmarks/fixtures/workspace_tasks_smoke/fixture.json) is the format reference:

- `schema_version` is `workspace-tasks-replay-v1`; identify the suite and its provenance category/description.
- `context` identifies the isolated tenant, actor and site. The runner gives that actor the existing `msat` role at that site; it is not a deployment authorization test.
- Each `source` names a payload inside the fixture directory, its SHA-256, source-system/record identity, media type, event time, and provenance including citation and license. Optional `source_revision`, `mapping_version` and `metadata` pass through to ingestion. Initial source identities must be unique.
- Each task has a unique ID, a valid direct-task `request` and a nonempty `expected` object. Expected object keys are checked recursively; arrays have exact order/length; scalars have exact values. `true` does not equal `1`. Source revisions and explicit missing-data outcomes can be checked this way. No fuzzy grader is used.

Payload bytes are verified and frozen before execution. Reports retain fixture/source hashes, provenance declarations, results, differences, exceptions, task states, attempted inference, per-attempt wall durations and nearest-rank latency percentiles with sample counts. Every attempted task contributes to wall latency, including failures. Service invocation latency is also reported separately. Setup/ingestion/checks/cleanup are included in overall attempt latency; fixture loading and report serialization are excluded. Store state is fresh; interpreter/OS caches are uncontrolled. Provider inference cost is zero by construction; total compute cost remains unknown.

Real-data adapters and real reference answers are not included. Numerical operations require the service's supported verified-delivery representation. Run actual ingestion/verification when adapting original workbooks; preserve original hashes, mappings, units and transformation versions. Do not manufacture verification flags or causal labels to make a public dataset fit. A provenance field records a declaration and does not certify permission or data authenticity.

The small implementation establishes direct-task contract replay with minimal infrastructure. A full interactive event environment would cover persistent work and integration recovery but adds infrastructure and simulator validity concerns. Event delivery, deduplication, restart, pause and approval checks remain separate runtime tests until a versioned event replay adapter is implemented.

## Production-derived evaluation and decision measures

The missing external-validity layer is consented, deidentified production trace replay: real requests, source revisions, alarms, deviations, handoffs, reviewer corrections and outcomes. Keep authoritative records in their owning systems. Record consent, permitted uses, retention, deidentification transformations and reference-review provenance. Public datasets cannot establish deployment benefit or compliance.

Freeze development/held-out splits by time, entity, incident/template family and site before creating variants. Keep paired CHO experiments and DABstep core-question variants together. Exclude future events and answer-bearing paths from runtime input. Repeat runs measure variability, not new incidents. Compare direct workflows, the existing assistant and their combined path with identical authorized evidence and declared budgets.

| Pillar | Observable measures |
| --- | --- |
| Easy to Start | Preparation time, required inputs/corrections, first useful result. |
| Easy to Trust | Source/version correctness, numerical checks, unsupported claims, reviewer verification effort. |
| Easy to Act | Reviewable next step, appropriate `needs_information`, follow-up completion and measured outcomes. |
| Easy to Adopt | Integration/setup effort, permission handling, fit to existing records, training burden. |

Report all-request latency, failure/timeout rates, cold/warm conditions and sample denominators. Small pilots do not establish a stable production p99. Amortized cost per successful outcome includes unsuccessful attempts, retries, preprocessing/indexing, infrastructure and recurring monitoring; report simulator/grader expense separately and retain unknown billing as unknown.

For event-driven responsibilities, replay relevant/irrelevant events, late/out-of-order records, corrections, permission revocation, duplicate delivery, restart, pause and definition changes. Check stale proposal invalidation, exact approval-version enforcement, no duplicate effects, no self-trigger loops and no idle inference. Earlier monitoring needs lead-time, missed-event and false-alert-per-operating-period measures, plus qualified review of whether the earlier finding was useful. These remain required coverage; the direct-task smoke fixture does not demonstrate them.
