# Prime Agent SDK integration

Prime Agent is the sole Manufacturing OS RLM runtime. BioDemo supplies the
manufacturing domain layer; it does not implement a second lead agent or
recursive worker engine.

```text
FastAPI rollout request
  → src/prime_runtime/harness.py
  → src/prime_runtime/sdk_runner.mjs
  → Prime SDK createAgentSession() / SessionManager
  ↔ native Prime Python kernel and rlm.spawn children
  ↔ prime_skills/manufacturing_os/
  ↔ src/prime_runtime/bridge.py
  ↔ ManufacturingStore + ten ManufacturingTools
  → Blackboard + graphs + review workflow
```

BioDemo is Python and the SDK is TypeScript, so the harness starts a local Node
host for each rollout. The host calls `createAgentSession()` directly; it does
not invoke the Prime CLI or call a remote Prime Agent API. A saved SDK session
file is reopened when the same incident continues. The bridge gives the skill
only time- and tenant-scoped evidence, and rejects report citations that were
not supplied or retrieved in the run. A successful `submit_report()` persists
the Blackboard and creates a human-reviewable investigation update.

The host needs a Prime checkout with built
`packages/coding-agent/dist/index.js` and installed Node dependencies. Set
`PRIME_AGENT_BUNDLE_ROOT` to its path. Optional settings are
`BIODEMO_PRIME_MODEL=provider/model`, `BIODEMO_PRIME_TIMEOUT` (seconds), and
`BIODEMO_PRIME_SDK_COMMAND` (host command override for tests).

The retrospective UI's case router under `benchmark/application/` is a
deterministic demonstration and does not run Manufacturing OS investigations.
The CHO and Fresenius baseline programs under `benchmarks/` measure extraction
and one-pass analysis separately; they do not impersonate Prime.

Prime's Node process and Python kernel are not an OS sandbox. Held-out
benchmark evaluation and confidential tenant deployments require an external
filesystem isolation boundary. The current tests use a fake SDK host to verify
bridge scope, report persistence, and session resume. They do not measure live
model reasoning or native child-agent quality.
