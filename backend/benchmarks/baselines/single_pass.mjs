/** One synthesis call through the installed Prime provider registry. No agent/tools/memory. */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { configureProjectProvider, validateModalAuthentication } from '../../src/prime_runtime/provider_config.mjs';

const input = JSON.parse(readFileSync(0, 'utf8'));
const sdk = await import(pathToFileURL(join(input.bundle_root, 'packages/coding-agent/dist/index.js')).href);
const ai = await import(pathToFileURL(join(input.bundle_root, 'packages/ai/dist/index.js')).href);
const auth = sdk.AuthStorage.create();
const registry = sdk.ModelRegistry.create(auth);
configureProjectProvider(auth, registry);
const slash = input.model.indexOf('/');
const model = registry.find(input.model.slice(0, slash), input.model.slice(slash + 1));
if (!model) throw Error('Single-pass model is unavailable in the installed registry');
await validateModalAuthentication(model, registry);
const resolved = await registry.getApiKeyAndHeaders(model);
if (!resolved.ok) throw Error('Single-pass provider authentication is unavailable');
const response = await ai.completeSimple(resolved.requestModel ?? model, {
  systemPrompt: input.system_prompt,
  messages: [{ role: 'user', content: input.prompt, timestamp: Date.now() }],
  tools: [],
}, {
  apiKey: resolved.apiKey, headers: resolved.headers,
  maxTokens: input.max_output_tokens, signal: AbortSignal.timeout(input.timeout_ms),
});
// No auth objects, request headers, URLs or credentials are persisted.
process.stdout.write(JSON.stringify({
  model: input.model, stop_reason: response.stopReason,
  text: response.content.filter(c => c.type === 'text').map(c => c.text).join(''),
  usage: { input_tokens: response.usage.input, output_tokens: response.usage.output,
    cached_input_tokens: response.usage.cacheRead, model_calls: 1,
    inference_cost_usd: null, cost_status: 'provider_billing_not_captured',
    usage_scope: 'single_synthesis_call; no_tools_or_memory', model_id: input.model },
}) + '\n');
