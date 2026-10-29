# Connect your agent LLMs for development testing

These settings connect the **language models that plan and interpret work**. The numerical simulation models remain independently registered and reproducible.

## Configure the connection

Edit `backend/.env.local` on your machine, preserving existing settings. The backend loads this file at startup; real environment variables take precedence. Do not put keys in frontend variables or chat messages.

For an Anthropic API model:

```dotenv
LIFESCI_LLM_PROVIDER=anthropic
LIFESCI_LLM_MODEL=YOUR_EXACT_API_MODEL_ID
ANTHROPIC_API_KEY=YOUR_API_KEY
LIFESCI_ALLOW_UNQUALIFIED_ROUTES=1
```

For an OpenAI API model instead:

```dotenv
LIFESCI_LLM_PROVIDER=openai
LIFESCI_LLM_MODEL=YOUR_EXACT_API_MODEL_ID
OPENAI_API_KEY=YOUR_API_KEY
LIFESCI_ALLOW_UNQUALIFIED_ROUTES=1
```

Replace the model placeholder with an exact API identifier accessible to your account. A chat-product subscription/session is not automatically a backend API credential. The app does not invent a model name, verify account access from a name, or auto-qualify your model.

One configured model fills both roles by default:

| Role | Existing task kind | Behavior |
|---|---|---|
| Planner | `investigation_planning` | Clarifies the problem; selects registered scientific operations, models and workflow dependencies |
| Interpreter | `comparison_explanation` | Interprets executed calculations when the planned workflow requests assessment |

To use a different interpreter, optionally add:

```dotenv
LIFESCI_INTERPRETER_MODEL=YOUR_OTHER_MODEL_ID
# Only necessary if the interpreter uses another provider:
LIFESCI_INTERPRETER_PROVIDER=openai
OPENAI_API_KEY=YOUR_OTHER_PROVIDER_KEY
```

Model bindings are explicit. A failed configured model does not silently fall back to a different default provider/model. Other platform task kinds retain their existing routing rules. Model and endpoint/pricing changes produce a new profile version, preventing reuse of cache entries from the previous configuration.

`LIFESCI_ALLOW_UNQUALIFIED_ROUTES=1` uses the existing development routing mode. It permits real test calls while retaining `route.unqualified=true`, mandatory review and a visible development label in the chat. It does not create a passing evaluation, scientifically validate a simulator, approve a recommendation, or authorize a production change. Without that setting, the ordinary task-specific qualification gate remains enforced. Real calls consume the provider account's quota/billing.

## Restart and check

Stop the running backend in its terminal, then start it again with your preferred development database:

```sh
cd backend
LIFESCI_DATABASE_URL=sqlite:////private/tmp/biodemo-lyo-test.db ../.venv/bin/python -m src.lifesci serve --seed-demo --port 8100
```

To retain your current conversations, keep the database URL you already use. The path above matches this demonstration's current local server.

Start the frontend in another terminal if it is not already running:

```sh
cd frontend
npm run dev
```

If you serve the static `frontend/dist` preview, rebuild it once with `npm run build` to include the development-route label. API credentials are server-side; changing them does not require embedding keys in or rebuilding the frontend.

Inspect the selected routes without making a paid inference request:

```sh
curl -sS http://127.0.0.1:8100/v1/process-model/llm-connection \
  -H 'X-Tenant-Id: demo-northfield' \
  -H 'X-Actor-Id: priya'
```

`configured_not_connectivity_tested` means a route and provider adapter are present; it is not an authentication or model-access test. `missing_provider_credentials` identifies a missing provider key. `route_blocked` reports missing configuration or a qualification gate. The response contains no keys or endpoint URLs. These headers are for the existing local development identity; deployed authentication remains deployment-specific.

Open [Process engineering](http://127.0.0.1:5180/process-simulation/) and send a small clarification task first, such as “What information would you need to assess a freeze-drying transfer?” Inspect **Execution record** for the actual provider, model, version, attempts, usage and route state. Then try the explicitly labeled freeze-drying example and follow up with an operating scenario. An earlier unavailable request can be retried without creating another user message.

If a request fails, its execution record distinguishes invalid credentials, inaccessible model identifiers, provider errors, routing gates, invalid workflow JSON and budget exhaustion. Configuration diagnostics intentionally do not claim that a real model run succeeded.

## Custom endpoints and cost accounting

`OPENAI_BASE_URL` and `ANTHROPIC_BASE_URL` can point at an explicitly chosen compatible API server. A root URL or one ending in `/v1` is accepted. The current OpenAI adapter calls `/v1/responses`; the Anthropic adapter calls `/v1/messages`. A server exposing only `/v1/chat/completions` is **not** supported by these adapters. Share the server type if another protocol is needed; do not assume every “OpenAI-compatible” endpoint supports Responses.

Known prices can be configured through `LIFESCI_LLM_INPUT_USD_PER_MTOK`, `LIFESCI_LLM_OUTPUT_USD_PER_MTOK` and `LIFESCI_LLM_CACHED_INPUT_USD_PER_MTOK`. For a separately overridden interpreter use the corresponding `LIFESCI_INTERPRETER_*` names. All rates must be finite and nonnegative.

Without all three rates, the profile explicitly labels its 10/50/10 defaults as **development budgeting assumptions, not provider prices**. Gateway `cost_usd` remains a profile-based estimate, not a reconciled invoice; route metadata retains the assumption/rate basis. Actual token usage remains recorded. Set appropriate rates before using dollar estimates for comparisons. These numbers do not constitute a claim about any model's actual current price.

## Implementation and checks

`gateway/configuration.py` reads the model identifiers and creates versioned task profiles; `Router` enforces the explicit bindings and existing qualification policy. Provider adapters own secrets. `/v1/process-model/llm-connection` exposes configuration status. No provider call or qualification is triggered by editing the file or checking status.

Tests cover strict versus development routing, one/two-provider setups, absence of silent fallback, invalid configuration, price/version metadata, endpoint normalization, secret-free diagnostics, and configured-model execution through the conversation/gateway using an explicit test provider. These are contract tests, not live account-access checks or measured LLM scientific performance. No user credential has been configured and no live provider success is claimed by this change.

Executed checks for this follow-up: **394 life-sciences tests passed** in 72.32 s; focused configuration/gateway/conversation group **38 passed**; frontend production build and TypeScript validation passed; whitespace checks passed. No live provider request was made.
