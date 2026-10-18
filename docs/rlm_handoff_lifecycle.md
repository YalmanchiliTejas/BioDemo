# RLM specialist handoff lifecycle

Run `3ba182a71be34433b6f46e7e8ec46f28` failed after 221.844 seconds despite
an 1800-second deadline. The root returned a progress message while all three
specialists remained running. The JS host immediately disposed the SDK session;
the Python harness then correctly rejected the absence of a submitted report.
Fifteen manufacturing calls remained. No source-verification rejection or
wall-clock timeout caused that failure.

## Implementation

`src/prime_runtime/investigation_lifecycle.mjs` now owns the session lifecycle.
After a lead turn, the host checks the authenticated bridge for an actually
persisted report. If none exists, it calls the SDK's public
`waitForRlmQuiescence(signal)` method. That barrier includes admitted descendants,
their terminal messages, parent follow-up turns, and descendants spawned during
those turns. It does not treat an idle root turn as completed investigation work.

After fan-in, the host checks report persistence again. If the native follow-up
turns did not submit a report, it resumes the lead with a synthesis continuation
using existing evidence and specialist checkpoints. It does not restart the
investigation. A successfully persisted partial report is retained as partial;
progress messages and checkpoints never count as submitted reports.

The existing final-synthesis reserve interrupts exploration and cancels remaining
children, retaining their saved findings. Cancellation of either a root prompt or
the descendant barrier transfers control to synthesis. Cancellation notices drain
before synthesis starts, avoiding concurrent lead prompts. A hard host deadline
bounds prompts, fan-in and bridge checks. The Python worker process-group deadline
remains the final cancellation boundary. Missing reports, bridge failures and
provider failures remain explicit failures; no report is fabricated on shutdown.

`POST /execution-status` on the scoped, authenticated bridge returns submission
state, report status and budget without exposing source records or consuming tool
allowance. Host logs include `awaiting_rlm_quiescence`,
`lead_resumed_for_submission`, `investigation_report_persisted` and deadline events.

The installed SDK was checked to expose `waitForRlmQuiescence`,
`waitForHeadlessIdle` and `cancelRlmChildRun`. An unsupported SDK fails with an
actionable message instead of silently reverting to early shutdown.

## Verification

```sh
node --test tests/test_investigation_lifecycle.mjs tests/test_prime_provider_config.mjs
.venv/bin/python -m pytest -q tests/test_sdk_handoff.py \
  tests/test_investigation_review.py tests/test_prime_runtime.py
```

Lifecycle regressions cover unfinished specialists, nested fan-in, automatic
parent follow-ups, explicit lead continuation, partial submissions, absent
submissions, reserve cancellation during a prompt or barrier, hard deadlines,
provider/bridge failures and missing SDK support.

The integration test executes the real JS host, Python harness, HTTP bridge and
report verification using a synthetic SDK scheduling fixture. Its first root
turn ends while a specialist is active; the specialist saves a checkpoint; the
lead resumes and submits a structurally complete source-checked report. No model
inference or benchmark score is manufactured by this test.

A new live Modal reliability result remains unmeasured: the current execution
environment has no valid Modal proxy credential. Previously recorded failures
and results remain unchanged. Re-run the existing FRE-02 command in the shell
with Modal credentials; its 30-minute benchmark deadline is preserved.
