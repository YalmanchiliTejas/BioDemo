# Validation record

Implementation target: local `main`, implementation commit `9127ad6`.
Worktree: `/private/tmp/biodemo-main-evals`. The source research checkout was not switched or merged.

## Executed checks

- `python -m pytest backend/tests/lifesci evals/tests -q --tb=short`: **528 passed, 2 skipped** at that point in implementation. The skips were the absent Temporal SDK and independent bioprocess simulator environment. Earlier sandbox failures from local socket restrictions were rerun with local server access; they are not counted as product regressions.
- After the checkpoint/clarification contract fix, the affected conversation, mission, gateway and expanded harness selection: **86 passed**.
- Final fixture changes (including irrelevant source distractors), `python -m pytest evals/tests -q --tb=short`: **13 passed**.
- Exact `.github/workflows/deploy-api.yml` Python test selection: **151 passed**.
- All **12** mission definitions were replayed with explicitly scripted contract providers to check every timeline's application wiring: **no application-operation exceptions**. These are not agent-quality measurements.
- `python -m pip install --no-deps -e ./backend`: editable package build and install succeeded.
- `python -m compileall -q evals backend/src/lifesci` and `git diff --check` succeeded.

The isolated environment used Langfuse 4.18.0, DeepEval 4.3.2 and PyYAML 6.0.3. DeepEval's pytest plugin emitted deprecation warnings; CI disables automatic plugin loading for the deterministic contract job.

## Live model evidence

The preliminary smoke run (`smoke-live.json`) used six successful GLM responses and exposed the prior contract's rejection of checkpoint-plus-questions. It preceded the final implementation and must not be treated as its baseline. Earlier `smoke.json`/`unconfigured.json` are infrastructure/availability preflights, not successful model evaluations.

The versioned complete campaign is recorded separately in `latest.json` with per-mission source fingerprints, actual requested/returned model identities, call receipts, virtual event chronology, resource usage, failed assertions and outstanding coverage. Provider calls in this initial harness use a 120-second timeout floor; each worker operation has a separate 420-second wall limit. These evaluation bounds can differ from deployment configuration; failures at those bounds are not automatically reasoning-accuracy failures. Failed/no-content responses remain admitted requests; provider-reported invoice cost is unknown.

No production records, manufacturing changes, external communications or deployment were performed by these evaluations. Langfuse project credentials were unavailable and the user explicitly deferred configuring them. Local observations are retained; no remote trace URL is invented. DeepEval judge results remain unavailable until a judge is configured and calibrated with domain-aware review.

## Completed campaign and final hardening

The complete real-model campaign at `9127ad6` ran **12 missions, 89 events, 24 distinct sessions, 26 background turns and 85 admitted model requests**. **42** requests returned usable responses from `zai-org/GLM-5.3`; failed requests are retained. All **12** missions failed at least one acceptance condition.

After grader corrections, the recorded outcomes show:

| Check | Result |
| --- | --- |
| Milestone checks | 12 / 43 passed |
| Source/timer background initiation | 11 / 11 passed |
| Useful autonomous progress | 0 / 10 passed |
| Literal cross-session recall | 0 / 11 passed; this is not a semantic memory benchmark |
| Necessary tool checks | 10 / 12 passed |
| Required evidence inspected | 7 / 22 |
| Record Recall@5 | 17 / 22, union across actual query top-five results |
| False in-app interruptions | 5 / 14 negative events |
| Prohibited writes or scope-canary leaks detected | 0 in the recorded deterministic checks |

Top product failures before a pilot: (1) frequent empty model responses after exhausting the output allowance, (2) premature clarification and failure to retain/use source-linked progress, (3) unnecessary publications on irrelevant events. The agent often discovered source IDs without inspecting the originals. These results do not establish causal/numerical accuracy or compliance.

The post-campaign persistence and grader fixes are committed separately at `11fa084`. The **95-test affected selection passed**, including assessment survival through compaction, preservation of unrelated unfinished work, negation/numeric-recall edge cases, alternate durable progress artifacts, virtual versus real timing, and protection against treating scripted runs as live model evidence. The exact deployment selection was rerun after these fixes and again passed **151 tests**. The full 12-mission live campaign was not rerun after those fixes; report `versions` identifies the actual agent and `grader_versions` identifies the regrading code.

Smoke and memory reports replay the real recorded missions; they are **not additional independent trials**. The replay required no new model requests. Restoring the archive to a different directory and replaying with an unavailable original path succeeded.

The 2,507,210-byte archive `campaign-9127ad6-evidence.tar.gz` has SHA-256:

```text
8b204f335b3a3b683810afbdcbc2ca415cea75738c3eab6e084d3250391b465d
```

Exact principal commands, run from `/private/tmp/biodemo-main-evals`:

```bash
/private/tmp/biodemo-evals-venv/bin/python -m evals.runner --suite mission --jobs 3 --provider-env /Users/tejas/Desktop/BioDemo/backend/deploy/aws/production.env --output evals/reports/latest.json
/private/tmp/biodemo-evals-venv/bin/python -m evals.runner --suite mission --replay-report evals/reports/campaign-9127ad6.json --output evals/reports/latest.json
/private/tmp/biodemo-evals-venv/bin/python -m evals.runner --suite smoke --replay-report evals/reports/campaign-9127ad6.json --output evals/reports/smoke-replay.json
/private/tmp/biodemo-evals-venv/bin/python -m evals.runner --suite memory --replay-report evals/reports/campaign-9127ad6.json --output evals/reports/memory.json
/private/tmp/biodemo-evals-venv/bin/python -m pytest evals/tests backend/tests/lifesci/test_engineering_conversation.py backend/tests/lifesci/test_missions.py backend/tests/lifesci/test_gateway.py -q --tb=short
```

Actual architecture exercised: local SQLite, transactional source events, the existing mission coordinator/scheduler, current conversation service, permission-aware workspace tools and the real model gateway. Remote Langfuse is unconfigured by the user's choice; there is no genuine remote trace URL to report. DeepEval judge execution/calibration, reviewed reusable memory consolidation/retirement, chunk ranking, external tool-completion subscriptions, deployed Temporal/integrations, and external notification delivery remain outside the demonstrated coverage. These gaps are separate from the observed agent failures.
