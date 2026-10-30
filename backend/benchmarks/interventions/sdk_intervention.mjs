/** Restricted research session using the existing Prime SDK and provider config.
 * JSON-line IPC: the model can invoke only the enumerated host tools. No native
 * kernel, filesystem, shell, browser, plugins, memories or child agents are active.
 */
import { createInterface } from 'node:readline';
import { createRequire } from 'node:module';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { createHash } from 'node:crypto';
import { configureProjectProvider, validateModalAuthentication } from '../../src/prime_runtime/provider_config.mjs';

const pending = new Map();
let initialResolve;
const initial = new Promise(resolve => { initialResolve = resolve; });
const reader = createInterface({ input: process.stdin });
reader.on('line', line => {
  const value = JSON.parse(line);
  if (value.type === 'initialize') initialResolve(value);
  else if (value.type === 'tool_result' && pending.has(value.id)) {
    pending.get(value.id)(value.result); pending.delete(value.id);
  }
});
const input = await initial;
const emit = value => process.stdout.write(JSON.stringify(value) + '\n');
const sdk = await import(pathToFileURL(join(input.bundle_root, 'packages/coding-agent/dist/index.js')).href);
const require = createRequire(join(input.bundle_root, 'packages/coding-agent/package.json'));
const { Type } = await import(pathToFileURL(require.resolve('typebox')).href);
const { AuthStorage, ModelRegistry, DefaultResourceLoader, SettingsManager, SessionManager, createAgentSession } = sdk;
const authStorage = AuthStorage.create();
const modelRegistry = ModelRegistry.create(authStorage);
configureProjectProvider(authStorage, modelRegistry);
const slash = input.model.indexOf('/');
const configured = modelRegistry.find(input.model.slice(0, slash), input.model.slice(slash + 1));
if (!configured) throw Error('Configured research model is unavailable');
// Same response ceiling, reasoning setting and model object in both arms.
const model = { ...configured, maxTokens: input.max_output_tokens };
const settings = SettingsManager.inMemory({ packages: [], extensions: [], skills: [], promptTemplates: [],
  compaction: { enabled: false }, retry: { enabled: false } });
const loader = new DefaultResourceLoader({ cwd: input.cwd, agentDir: input.cwd,
  settingsManager: settings, bundledSkillsDir: null, noThemes: true, noExtensions: true,
  noSkills: true, noPromptTemplates: true, noContextFiles: true, systemPrompt: input.system_prompt });
await loader.reload();
let ordinal = 0;
let submitted = null;
let session;
const bridge = async (name, args) => {
  const id = String(++ordinal);
  emit({ type: 'tool_request', id, name, args });
  const result = await new Promise(resolve => pending.set(id, resolve));
  if (name === 'submit_decision' && result.accepted) {
    submitted = args;
    // Submission freezes the decision. Do not spend another model turn to
    // paraphrase it or let the model revise after receiving evaluator feedback.
    setTimeout(() => session?.abort().catch(() => {}), 0);
  }
  return { content: [{ type: 'text', text: JSON.stringify(result) }], details: {} };
};
const choice = values => Type.Union(values.map(value => Type.Literal(value)));
const ids = input.public_schema;
const submissionFields = {
  predictions: Type.Object(Object.fromEntries((ids.forecast_fields ?? ['product_concentration','process_indicator']).map(k => [k, Type.Number({minimum:0})])), {additionalProperties:false, description:'Predictions at the exact packet forecast times in packet physical units. Always predict KEEP even when selecting another action.'}),
  action_id: choice(ids.actions), rationale: Type.String(), uncertainty: Type.String(),
  evidence: Type.Array(Type.String()),
};
const definitions = [
  { name: 'python_analysis', description: 'Run general-purpose numerical Python in an OS sandbox with network and hidden-file access denied. data is the current public packet; np, math and json are available. Print a compact result. No persistent kernel.',
    parameters: Type.Object({ code: Type.String({ maxLength: 18000 }) }) },
  { name: 'submit_decision', description: 'Freeze terminal KEEP predictions and your selected allowed action exactly once. Include rationale, uncertainty and concrete evidence references. No evaluator outcome or score is returned.',
    parameters: Type.Object(submissionFields, { additionalProperties: false }) },
];
if (ids.measurements) definitions.push({ name: 'request_measurement', description: 'Request a permitted assay. The process continues under KEEP until its result arrives. Returns only evidence available at the advanced clock; at most one extra assay.', parameters: Type.Object({ measurement: choice(ids.measurements) }, { additionalProperties: false }) });
if (input.arm === 'B') definitions.push({ name: 'physical_forward_model',
  description: 'Evaluate the nominal source-calibrated external physical model for one action. Returns predictions, not receiving measurements. This uses a nominal batch, not the hidden evaluator realization. No optimal-action ranking or score.',
  parameters: Type.Object({ action_id: choice(ids.actions) }, { additionalProperties: false }) });
const customTools = definitions.map(d => ({ ...d, label: d.name, executionMode: 'sequential',
  execute: async (_id, args) => bridge(d.name, args) }));
const names = definitions.map(d => d.name);
({ session } = await createAgentSession({ cwd: input.cwd, agentDir: input.cwd, authStorage, modelRegistry,
  settingsManager: settings, resourceLoader: loader, sessionManager: SessionManager.inMemory(input.cwd),
  model, thinkingLevel: 'low', tools: names, allowedToolNames: names, initialActiveToolNames: names,
  customTools, noTools: 'builtin', includeGoals: false, includeCompactSkill: false,
  rlmMaxDepth: 0, prewarmIpythonKernel: false, telemetryDisabled: true }));
const active = session.getActiveToolNames().sort();
if (JSON.stringify(active) !== JSON.stringify([...names].sort())) throw Error('Unexpected active SDK capability');
// GLM-5.3 always thinks; the old generic SDK "off" setting leaves the native
// template at its maximum default. Apply the documented native low setting to
// BOTH arms, without changing the user's saved provider or production routes.
// https://recipes.vllm.ai/zai-org/GLM-5.3#reasoning-modes
const previousPayload = session.agent.onPayload;
let requests = 0;
session.agent.onPayload = async (payload, currentModel) => {
  if (++requests > input.max_model_calls) throw Error('Frozen model-request ceiling reached');
  const altered = previousPayload ? await previousPayload(payload, currentModel) : undefined;
  const actual = altered ?? payload;
  actual.reasoning_effort = 'low';
  actual.chat_template_kwargs = { ...(actual.chat_template_kwargs ?? {}), reasoning_effort: 'low' };
  emit({ type: 'request_configuration', reasoning_effort: 'low',
    max_tokens: actual.max_tokens ?? actual.max_completion_tokens,
    tool_names: (actual.tools ?? []).map(t => t.function?.name).filter(Boolean) });
  return actual;
};
await validateModalAuthentication(session.model, modelRegistry);
emit({ type: 'capability_audit', active_tools: active, native_kernel: false, children: false,
  external_retrieval: false, cwd_memory_loaded: false, model: input.model,
  shared_tool_schema_sha256: createHash('sha256').update(JSON.stringify(definitions.filter(d=>d.name!=='physical_forward_model'))).digest('hex') });
const usage = [];
let modelCalls = 0;
const unsubscribe = session.subscribe(event => {
  if (event.type === 'tool_execution_end') {
    emit({ type: 'sdk_tool_execution', name: event.toolName, is_error: !!event.isError,
      error: event.isError ? (event.result?.content ?? []).filter(b=>b.type==='text').map(b=>b.text).join('\n').slice(0,1500) : null });
  }
  if (event.type === 'message_start' && event.message?.role === 'assistant') {
    modelCalls += 1;
    emit({ type: 'model_start', ordinal: modelCalls });
    if (modelCalls > input.max_model_calls) void session.abort();
  }
  if (event.type === 'message_end' && event.message?.role === 'assistant') {
    usage.push(event.message.usage ?? null);
    emit({ type: 'model_usage', usage: event.message.usage ?? null,
      stop_reason: event.message.stopReason,
      content_types: (event.message.content ?? []).map(block => block.type) });
  }
});
let timedOut = false;
const timer = setTimeout(() => { timedOut = true; void session.abort(); }, input.timeout_seconds * 1000);
try {
  if (!input.preflight) {
    await session.prompt(input.prompt);
    if (!submitted && !timedOut && modelCalls < input.max_model_calls) {
      await session.prompt('Finish the task now using submit_decision. Explicitly state uncertainty if you cannot establish a conclusion.');
    }
  }
  emit({ type: 'finished', status: input.preflight ? 'preflight_passed' : submitted ? 'completed' : timedOut ? 'timeout' : 'no_submission',
    decision: submitted, model_calls: modelCalls, usage,
    error: submitted ? null : session.agent.state.errorMessage ?? null });
} catch (error) {
  emit({ type: 'finished', status: submitted ? 'completed' : timedOut ? 'timeout' : 'failed',
    decision: submitted, model_calls: modelCalls, usage,
    error: submitted ? null : String(error.message ?? error).slice(0, 1200) });
} finally {
  clearTimeout(timer); unsubscribe(); session.dispose(); reader.close();
}
