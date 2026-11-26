# Current assistant pilot evaluation — November 3, 2026

**Recommendation: use an invited, supervised feedback beta. Keep background follow-up off initially.** The conservative evaluation gate remains false; this is not evidence for an unattended or generally qualified manufacturing launch.

## Completed evaluation

Current corrected agent: 40/40 planned trials; 34 PASS, 2 FAIL, 4 NOT_GRADED. The first full 24-case pass scored 20 PASS, 2 FAIL and 2 NOT_GRADED. Unknown or unexecuted cases are never counted as passing.

The two raw failures are distinct: unrelated evidence caused an unnecessary visible background turn; the draft-retest case also lacked a verified sample/LIMS target, so the independent review found its safe clarification defensible and the forced-draft oracle potentially overstrict. Two ungraded primary cases reflect judge schema/quote failures, not proof that the agent gave wrong answers. Original machine scores remain unchanged.

| Capability | PASS | FAIL | NOT_GRADED |
|---|---:|---:|---:|
| approval | 3 | 1 | 1 |
| background | 3 | 1 | 1 |
| discovery | 5 | 0 | 0 |
| memory | 5 | 0 | 0 |
| missing_evidence | 4 | 0 | 1 |
| revisions | 5 | 0 | 0 |
| scheduling | 5 | 0 | 0 |
| units | 4 | 0 | 1 |

Eight predetermined cases were selected for three total trials each. 8/8 have all three receipts; 6/8 passed all three under the automated gate. Repeats are not additional independent incidents.

Across baseline, calibration and corrected cohorts, 105 real-model trials completed. The baseline retained 51/72 receipts; the remaining 21 were not silently converted to passes. Do not combine old and corrected software into one accuracy claim. The corrected cases were reused after inspecting earlier failures, so their results are regression evidence rather than untouched held-out evidence.

## Changes and verification

- Allowed provisional questions alongside read-only discovery; numerical work and proposals still require essential missing inputs to be resolved.
- Evidence search now checks authorized text/JSON originals as well as metadata, pins the discovered revision, and explicitly reports missing/oversized source gaps. Search is capped at 2 MiB per source and 8 MiB total source text. Search summaries still require a separate source read for inspection.
- Evaluator rejects absent/malformed judges, validates quoted evidence against actual reads, and distinguishes judge-contract failures from agent errors. Unknown usage retains conservative request reservations; a hard provider-request ceiling is separate from estimated billing.
- New evaluator and product regression tests are included in the API CI workflow.

**Fresh checks:** 258 selected backend tests passed; frontend TypeScript passed; whitespace checks passed. The broader backend run reached 696 passes and 10 skips, then stopped at `test_case_comparison.py::ChoCaseTests::test_recorded_prime_pilot_is_wired` because the archived CHO pilot run is absent from this checkout. This is an incomplete full-suite result, not an all-green claim.

## Independent review and remaining issues

A separate coding agent reviewed all 40 corrected outputs (24 primary plus 16 repeats), recalculated unit/date/schedule references, and verified review input hashes. This is not pharmaceutical expert adjudication. It found that some otherwise correct answers add unsupported sampling, authority, or disposition details. Those concerns qualify automated PASS results and remain work before making strong reliability claims. The review also caught overstrict evidence-path and underspecified-target cases in the evaluator itself.

- Fix relevant-versus-irrelevant background visibility before enabling follow-up for initial testers. The negative-control answer was factually correct but still interrupted the user.
- Reduce unsupported extra claims, including assumed release authority and implications of retesting, and extend grading of persistent proposal text.
- Clarify target identifiers and acceptance-limit direction in synthetic worlds; replace evaluation-flavored source identifiers with opaque IDs before a new blind evaluation.
- One repeated retest-draft attempt was blocked because it used uninspected user-instruction evidence in the action basis. The host prevented an invalid draft; this is an observed task failure even though its separate judge was unavailable.
- Repair malformed judge outputs as an explicitly separate evaluator run; preserve original judgments and agent attempts.

## Resources and evidence

Provider requests across these cohorts: 439. Accounted token-rate estimates plus unknown-call reservations: $15.4997, within the approved $50 estimated budget. 7 request(s) lack settled usage; actual Modal invoice cost is unknown. This accounting excludes unrelated historical experiments.

The model endpoint identity was checked against `zai-org/GLM-5.3`. Every trial preserves local conversation/mission IDs, source/tool traces, request IDs, output, and separate judge verdicts. Source snapshots and hashes are retained. No production account, manufacturing system or deployment was changed.

Raw local receipts: `backend/results/agent-pilot-20261103/`. They remain local and ignored by Git; the compact report is retained here. See [summary.json](agent-pilot-20261103/summary.json), [runner and reproduction instructions](../../backend/benchmarks/agent_pilot/README.md), and [tracked evaluation issue](https://github.com/YalmanchiliTejas/BioDemo/issues/3).

## Limits

These are small synthetic text worlds, not customer incidents. The semantic judge uses the same model family as the tested agent; independent coding-agent review helps but does not constitute expert validation. Restart tests recreate the application against persistent SQLite rather than terminating an operating-system process. Background events use actual service/runtime entry points, but external notification delivery and multi-day timing were not qualified. The runner caps provider requests at 120 seconds; the ordinary provider can be configured to wait longer. Numeric and schedule facts are independently audited, but the automated semantic grader is not an independent general numerical solver.

Deployed signup/browser behavior, production connectors, load SLOs, mechanistic process prediction validity, compliance, and observed human-effort savings are outside this campaign. Follow the four pillars during the beta: observe preparation, verification/correction effort, usable decisions and follow-up, and onboarding/permission friction.
