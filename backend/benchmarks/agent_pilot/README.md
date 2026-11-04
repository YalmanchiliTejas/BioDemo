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

This runner caps each provider request at 120 seconds for a bounded pilot check. The ordinary Modal adapter defaults to a 300-second timeout unless configured otherwise; a failure against this evaluation deadline is not proof that an unbounded later answer would be wrong. Empty answers caused by exhausting the normal output-token allowance are retained separately in gateway attempts.

## Evidence and grading

`protocol.json` pins suite and application-source hashes. Each trial preserves its private reference, local database, actual turns/tool artifacts, read source revisions, gateway attempts, model request IDs, judge text and result. `requests/` checkpoints admissions before inference and settlement afterward. JSON and Markdown campaign reports update as trials finish.

Deterministic checks cover required reads, exact source quotes in judge citations, private-sentinel exposure, draft status, absence of action intents, expected background activity, errors and terminal output. A separately prompted model checks factual meaning against the authored oracle. Missing or malformed judgments remain `NOT_GRADED`, never passing. The same-model semantic judge can make correlated mistakes; independent output review is recorded separately and never silently rewrites original attempts.

Numeric reasoning, dates and schedule feasibility are compared with known reference facts by the semantic judge; the current grader does not independently parse and solve arbitrary schedule prose. Independent reference/output audits complement this limitation. Exact quote validation establishes source provenance, not complete semantic support.

Background events enter the real evidence/case service and runtime tick with no intervening user message. A background turn is distinct from an external notification. An unrelated matching event currently can expose missing relevance filtering. Restarts recreate the application against its persisted database; they do not terminate an OS process or establish production worker durability.

## Release interpretation

Report completed, failed, ungraded and unexecuted trials separately, with family-level denominators. A case that safely refuses an answerable request is incomplete. A justified evidence wait can be correct. Preserved failed attempts must not be replaced with later successful attempts.

This local evaluation does not qualify deployed signup, browser behavior, production integrations, enterprise load, scientific model validity, compliance or human-effort savings. Read the independent review and specific failures before selecting the capabilities offered in a supervised pilot. The conservative `ready` field requires every planned trial and gate to pass and is scoped only to this suite.
