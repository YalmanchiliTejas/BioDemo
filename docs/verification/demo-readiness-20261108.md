# Demo readiness audit — 2026-11-08

## Outcome and release boundary

All 16 seeded persona scenarios completed against the configured production GLM-5.3 endpoint using isolated local synthetic workspaces. The four pharmaceutical-library cases saved real solver results. All four persona browser flows passed: notice and anonymous development sign-in, scenario discovery, model simulation, custom CSV upload, mapping confirmation, verified-data attachment to the assistant, return-session reload, and 390 px mobile layout without page overflow. All 19 seeded library configurations execute through the existing bounded service.

These checks cover host integration and demo usability, not customer validation or calibrated pharmaceutical accuracy. Some live turns recovered from rejected tool arguments; completion is not a claim that future inputs can never fail. Each persona has a separate tenant and role. Existing isolation, permissions, usage caps, expiry, source version checks and approval boundaries remain enforced.

The public API health check returned OK with model availability and no pending outbox events. The public LyoHUB research page and guided tour returned HTTP 200. The public release was a792d0c (PR #32, incorporating code only through 4944afb); it did not contain the later configuration-discovery fix. This audit's corrected branch must ship before the live demo can be considered covered by these checks. The automated browser could not pass the public Cloudflare challenge; a human private-window sign-in check remains required. No CAPTCHA or authentication bypass was added.

## Issues reproduced and fixed

- Returning demo tenants received new scenario cards without new library examples. Versioned, idempotent seed repair runs on workspace access and before assistant message admission; it retains uploads, conversations, counters and original expiry.
- Standard local `--seed-demo` startup omitted the library fixtures. It now uses the same shared seed.
- Catalogue tools exposed equations but no authorized configuration references. They now expose current record IDs with model/version/classification; explicit read/attach is still required before preparation.
- Live GLM calls read the correct record, then treated `simulation_id` as a new run name. The agent schema now names this `context_id`, explicitly requires the existing record ID, and retains legacy `simulation_id` input/persistence compatibility. Conflicting identifiers are rejected. Rejection messages identify already-read context IDs.
- Library reads were not recognized as inspected memory sources. The host records a versioned read receipt; notes can cite it, while a later source edit still requires a new read. Generated or merely listed artifacts are not treated as inspected.
- Anonymous visitors had no email to satisfy mapping review. The prior fix uses the authenticated visitor actor ID. All four browser roles now confirm mappings and attach their own verified delivery.
- The model selector's implicit label included its option text, preventing exact accessible-name selection. Explicit accessible names now cover Model, Current configuration and Operation.
- A stale auth check assumed an implicit Priya session. It now verifies explicit development sessions and rejects development headers in production.

The newer memory/prompt-ordering changes from main were preserved. The release workflow now runs pharmaceutical model regressions and frontend lint/auth/build checks. PR events run checks only; production deployment remains a main/dispatch action.

## Evidence

Machine-readable summaries are in [demo-readiness-20261108](demo-readiness-20261108/). The broad regression selection passed 240 tests; the targeted selection on the combined branch passed 104 tests. The focused live rerun on the combined branch passed all four library scenarios, each with one solver call. The final build generated 58 routes. Live all-scenario data used the production-configured Modal endpoint with requested model `zai-org/GLM-5.3`; route qualification remained unchanged.

Private local execution records (synthetic, no uploaded customer data):

- `/private/tmp/demo-readiness-live-all-16-pre-main-order/` — full 16-scenario run before incorporating main's prompt ordering.
- `/private/tmp/demo-readiness-live-library-v3/` — focused library rerun on the combined branch.
- `/private/tmp/demo-readiness-browser-v2/` — four browser results and desktop/mobile screenshots against the local API.
- Earlier failed live traces and browser results were preserved alongside those directories for comparison.

## Repeat the checks

```sh
# Requires a real local API/frontend; no mocked responses or injected login state.
PLAYWRIGHT_MODULE=/path/to/playwright node frontend/scripts/check_demo_personas.cjs http://127.0.0.1:5189 /private/tmp/new-browser-audit

# Opt-in live inference. Only model credentials are read from the file;
# the runner never reads production database/storage credentials.
PYTHONPATH=backend .venv/bin/python backend/scripts/check_demo_readiness.py \
  --output /private/tmp/new-live-audit --credentials-file backend/.env.local \
  --provider modal --model zai-org/GLM-5.3 --base-url <configured-modal-v1-url> --all-scenarios

PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/lifesci/test_demo_workspaces.py backend/tests/lifesci/test_pharmaceutical_integration.py backend/tests/lifesci/test_tool_loop.py backend/tests/lifesci/test_agent_memory.py backend/tests/lifesci/test_memory_privacy.py -q
```

In `frontend`, run `npm run lint`, `npm run check:auth`, and `npm run build`. Use a fresh live-output directory to retain prior records.
