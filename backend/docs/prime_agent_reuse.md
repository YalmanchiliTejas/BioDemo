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
  ↔ ManufacturingStore + scoped ManufacturingTools
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
`BIODEMO_PRIME_MODEL=provider/model` and
`BIODEMO_PRIME_SDK_COMMAND` (host command override for tests).

Modal authentication can be configured in this project's
`src/prime_runtime/provider_config.mjs`, which the SDK host loads before
creating a session. Set `BIODEMO_MODAL_PROXY_TOKEN` to the full proxy token
(`wk-<id>.ws-<secret>`). The runtime applies it to the `modal` provider in memory
and sends `Authorization: Bearer <token>`, overriding saved provider API keys
and Authorization headers. Credentials are not put into the stdin request,
report, or configuration files by this override.

`MODAL_PROXY_TOKEN` is also accepted; `BIODEMO_MODAL_PROXY_TOKEN` takes
precedence when both are present. Before sending the investigation prompt,
the runtime checks the resolved Authorization header for the required proxy
token format. This detects missing/malformed credentials locally; only the
Modal endpoint can establish whether a correctly formatted token is valid.

```bash
export BIODEMO_PRIME_MODEL=modal/zai-org/GLM-5.3
export BIODEMO_MODAL_PROXY_TOKEN='<your-full-modal-proxy-token>'
# Optional: override the endpoint registered in models.json.
# export BIODEMO_MODAL_BASE_URL='https://your-endpoint.modal.direct/v1'
.venv/bin/python -m benchmarks.common.benchmark_runner \
  --benchmark cho --mode full_rlm --case CHO-04 --condition raw
```

These variables must be exported in the launching shell. `.env.local` is not
automatically loaded by this command. The model definition remains in the
registered Modal provider; changing authentication does not replace the agent
runtime or require rebuilding the adjacent SDK checkout.

The retrospective UI's case router under `benchmark/application/` is a
deterministic demonstration and does not run Manufacturing OS investigations.
The CHO and Fresenius baseline programs under `benchmarks/` measure extraction
and one-pass analysis separately; they do not impersonate Prime.

Prime's Node process and Python kernel are not an OS sandbox. Held-out
benchmark evaluation and confidential tenant deployments require an external
filesystem isolation boundary. The current tests use a fake SDK host to verify
bridge scope, report persistence, and session resume. They do not measure live
model reasoning or native child-agent quality.


The runtime also prepares deterministic source statistics before inference and
checks structured metrics, source values and time alignment at submission.
See [the verification layer](deterministic_verification.md) for the report
contract, operational routing policy and source-store migration.
