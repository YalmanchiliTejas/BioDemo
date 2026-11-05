# Current assistant controlled-world evaluation

This evaluates the existing `Platform` conversation, evidence, action-draft and mission services with the actual configured GLM endpoint. It does not substitute the older Prime investigation harness or inject reference answers into an agent prompt.

The canonical task is [GitHub issue 3](https://github.com/YalmanchiliTejas/BioDemo/issues/3). The governing product direction is [Main_Culture_andETHOS.md](../../../Main_Culture_andETHOS.md).

## Cases and isolation

`scenarios.py` authors eight families: discovery, unit reasoning, effective revisions, incomplete evidence, schedule proposals, approval/source-injection boundaries, saved conversation memory after application restart, and background events. Development and held-out cases use distinct conditions. Each case has its own scoped identities and file-backed SQLite store. Cross-site and cross-tenant sentinel sources are negative controls. Reference files are outside the accessible application tools.

The suite currently has 24 cases per split. These are deliberately small synthetic text worlds, not independently reviewed factory incidents. Repetition measures consistency on the same tasks; 72 trials are 24 cases repeated three times, not 72 independent manufacturing incidents.

## Run without inference

From `backend/`:

```sh
.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_agent_pilot_runner.py tests/test_agent_pilot_graders.py tests/test_agent_pilot_scenarios.py tests/lifesci/test_discovery_clarification.py
.venv/bin/python -m benchmarks.agent_pilot.runner --preflight --suite heldout --output /private/tmp/agent-pilot-preflight
```

Use a fresh directory. Preflight seeds all sources through existing application services and makes no model calls.

## Run the actual agent

The runner reads the existing Modal configuration from the normal local files/environment without logging credentials. It explicitly binds `zai-org/GLM-5.3`; each response must report that exact model. It never opens an environment-configured production database. Paid execution requires `--execute`.

```sh
.venv/bin/python -m benchmarks.agent_pilot.runner \
  --suite heldout --count-per-family 3 --repeats 3 --workers 4 \
  --budget-usd 37 --max-requests 450 --max-seconds 2100 \
  --execute --output results/agent-pilot-NEW/heldout
```

The dollar limit controls conservative admission using declared GLM token-rate estimates. It is not reconciled Modal compute billing. Actual request token ceilings inform reservations; unknown usage retains the reservation. The separate provider-request ceiling is hard. Preserve earlier campaign spending when choosing a continuation budget. There are no campaign-level success retries; the app's normal bounded planning/validation attempts remain included in each episode.

This runner caps each agent provider request at 300 seconds, the ordinary Modal adapter default (runs before 2026-11-05 used 120 seconds, which turned slow answers into timeouts). Empty answers caused by exhausting the normal output-token allowance are retained separately in gateway attempts.

## Evidence and grading

`protocol.json` pins suite and application-source hashes. Each trial preserves its private reference, local database, actual turns/tool artifacts, read source revisions, gateway attempts, model request IDs, judge text and result. `requests/` checkpoints admissions before inference and settlement afterward. JSON and Markdown campaign reports update as trials finish.

Deterministic checks cover required reads, exact source quotes in judge citations, private-sentinel exposure, draft status, absence of action intents, expected background activity, errors and terminal output. A separately prompted model checks factual meaning against the authored oracle. Missing or malformed judgments remain `NOT_GRADED`, never passing. The same-model semantic judge can make correlated mistakes; independent output review is recorded separately and never silently rewrites original attempts.

Numeric reasoning, dates and schedule feasibility are compared with known reference facts by the semantic judge; the current grader does not independently parse and solve arbitrary schedule prose. Independent reference/output audits complement this limitation. Exact quote validation establishes source provenance, not complete semantic support.

Background events enter the real evidence/case service and runtime tick with no intervening user message. A background turn is distinct from an external notification. An unrelated matching event currently can expose missing relevance filtering. Restarts recreate the application against its persisted database; they do not terminate an OS process or establish production worker durability.

## Growing the suite without a dataset

- **Runtime grounding.** Final chat replies carry `claims` (`source_id` + exact quote). The host stores `turn.grounding`: each quote is checked verbatim against an inspected source, and every number in the reply must appear in an inspected source, a user message, a computed artifact, or a `derived` claim. The UI shows unverified items. The grader's `runtime_grounding` check reads the same field. This establishes provenance, not semantic support.
- **Metamorphic variants.** `--perturb rename_ids remove_evidence add_distractor` replaces the selected cases with variants whose expected change is known. Their `banned_tokens` are checked deterministically: old IDs, distractor IDs, and specifics from withdrawn evidence.
- **Cross-family judge.** `--judge-provider anthropic --judge-model claude-sonnet-5-5` (or `openai`) runs the judge on a different model family, using registered prices. Calibrate it before relying on it: `python -m benchmarks.agent_pilot.calibrate export RESULTS labels.csv` produces a blind, shuffled sheet; after a human fills `human_verdict`, `calibrate score RESULTS labels.csv` reports agreement, Cohen's kappa and the judge false-pass rate.
- **Authored and sealed cases.** `--suite authored --cases-dir DIR [--sealed]`; the format is described in [cases/README.md](cases/README.md).
- **Corrections become candidates.** `python -m benchmarks.agent_pilot.harvest --db BACKUP --tenant T --output IGNORED_DIR` exports every mission correction as an unreviewed case. Nothing can grade until a reviewer writes `required_facts`.

## Release interpretation

Report completed, failed, ungraded and unexecuted trials separately, with family-level denominators. A case that safely refuses an answerable request is incomplete. A justified evidence wait can be correct. Preserved failed attempts must not be replaced with later successful attempts.

This local evaluation does not qualify deployed signup, browser behavior, production integrations, enterprise load, scientific model validity, compliance or human-effort savings. Read the independent review and specific failures before selecting the capabilities offered in a supervised pilot. The conservative `ready` field requires every planned trial and gate to pass and is scoped only to this suite.

## Findings, 2026-11-05 (results/agent-pilot-20261104)

| Run (current code = v8) | Passed | No answer | Judged incorrect |
|---|---|---|---|
| held-out, before changes (v5b) | 19/24 | 1 | 0 |
| held-out v8 | 20/24 | 0 | 0 |
| perturbed, before changes (v5b) | 21/41 | 9 | 0 |
| perturbed v8 | 32/41 | 0 | 0 |
| CMO aggregation drafts, first run | 4/12 | 5 | 0 (1 cut off) |
| CMO aggregation drafts v8 | 10/12 | 0 | 0 |

What moved the numbers, measured rather than assumed:
- Reading a case returns its linked evidence text (one hop). The agent previously answered from the case summary without opening the register it cited.
- On the final planning round, read/search workflows are rejected, so the reply is an answer, not "I'll read it now".
- Output floor 32k tokens: blank answers from reasoning exhaustion went from 4/12 to 0/12 on CMO tables.
- Rejected: retrying with `reasoning_effort: low` after exhaustion. It removed blanks but 2 of 5 retried answers were wrong.
- Not the cause: irrelevant context. Simulation schemas are already withheld when nothing is attached.
- Harness: every agent request now has 300 s (production) instead of 120 s.

The GLM judge still emits malformed JSON or nothing on a few percent of trials (fail-closed as NOT_GRADED). Calibration against Claude labels (not human): 0 false passes in 58 pairs, but only 13 FAILs. Label sheets: `results/agent-pilot-20261104/*-labels-claude.csv`.
