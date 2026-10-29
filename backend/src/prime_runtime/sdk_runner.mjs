/** Single-run TypeScript SDK host. JSON on stdin; structured events on stdout. */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { configureProjectProvider, validateModalAuthentication } from "./provider_config.mjs";
import { runInvestigation } from "./investigation_lifecycle.mjs";
import { COMPACTION_RESERVE_TOKENS, compactionWindow } from "./compaction_policy.mjs";

const input = JSON.parse(readFileSync(0, "utf8"));
const sdkPath = join(input.bundle_root, "packages/coding-agent/dist/index.js");
const sdk = await import(pathToFileURL(sdkPath).href);
const { AuthStorage, ModelRegistry, SessionManager, DefaultResourceLoader, SettingsManager, createAgentSession, getAgentDir } = sdk;

// Evaluation uses the same SDK with an isolated resource directory. Preserve
// configured model selection, while excluding unrelated globally installed
// packages, memories and context from raw-evidence trials.
let evaluationSettings;
const agentDir = input.evaluation_mode ? join(input.cwd, ".evaluation-agent") : getAgentDir();
if (input.evaluation_mode) {
  const configured = SettingsManager.create(input.cwd, getAgentDir());
  evaluationSettings = SettingsManager.inMemory({
    defaultProvider: configured.getDefaultProvider(),
    defaultModel: configured.getDefaultModel(),
    packages: [], extensions: [], skills: [], promptTemplates: [],
  });
}

// Discovery is limited to the two required skills. SDK sessions retain Prime's
// native kernel and child-agent runtime; the manufacturing bridge bounds data.
const loader = new DefaultResourceLoader({
  cwd: input.cwd,
  agentDir,
  ...(evaluationSettings ? { settingsManager: evaluationSettings, bundledSkillsDir: null, noThemes: true } : {}),
  noExtensions: true,
  noSkills: true,
  noPromptTemplates: true,
  noContextFiles: true,
  additionalSkillPaths: input.skill_paths,
  appendSystemPrompt: [input.system_prompt],
});
await loader.reload();

const authStorage = AuthStorage.create();
const modelRegistry = ModelRegistry.create(authStorage);
configureProjectProvider(authStorage, modelRegistry);
let model;
if (input.model) {
  const slash = input.model.indexOf("/");
  if (slash < 1) throw new Error("BIODEMO_PRIME_MODEL must be provider/model");
  model = modelRegistry.find(input.model.slice(0, slash), input.model.slice(slash + 1));
  if (!model) throw new Error(`Prime SDK model is unavailable: ${input.model}`);
}
let defaultModel;
if (!model && input.compaction_target_tokens != null) {
  const configured = evaluationSettings ??
    (typeof SettingsManager.create === "function" ? SettingsManager.create(input.cwd, agentDir) : undefined);
  const provider = configured?.getDefaultProvider(), id = configured?.getDefaultModel();
  if (provider && id) defaultModel = modelRegistry.find(provider, id) ?? undefined;
}
const compaction = compactionWindow(model ?? defaultModel, input.compaction_target_tokens);
// Prime summarizes history once context exceeds contextWindow - reserveTokens.
// The full model window (1M for GLM-5.3) is never reached, so every turn resends
// the whole history. A session-local window makes summarizing start at the
// target while the default reserve keeps the summary request well-formed.
// Children inherit this model object and therefore the same policy.
if (compaction) model = { ...(model ?? defaultModel), contextWindow: compaction.context_window };

const manager = input.session_file
  ? SessionManager.open(input.session_file, input.session_dir, input.cwd)
  : SessionManager.create(input.cwd, input.session_dir);
const { session } = await createAgentSession({
  cwd: input.cwd,
  sessionManager: manager,
  resourceLoader: loader,
  authStorage,
  modelRegistry,
  ...(evaluationSettings ? { agentDir, settingsManager: evaluationSettings } : {}),
  tools: ["ipython"],
  ...(input.rlm_max_depth != null ? { rlmMaxDepth: input.rlm_max_depth } : {}),
  ...(model ? { model } : {}),
});
let error;
let fatalProviderError;
let modelStarted;
let modelOrdinal = 0;
try {
  await validateModalAuthentication(session.model, modelRegistry);
  console.log(JSON.stringify({ type: "session", id: session.sessionId, file: session.sessionFile,
    model: session.model ? `${session.model.provider}/${session.model.id}` : null }));
  if (compaction) {
    if (typeof session.settingsManager?.applyOverrides !== "function") {
      throw new Error("Prime SDK cannot apply the session compaction policy; set BIODEMO_COMPACTION_TARGET_TOKENS=off");
    }
    session.settingsManager.applyOverrides({ compaction: { enabled: true, reserveTokens: COMPACTION_RESERVE_TOKENS } });
    console.log(JSON.stringify({ type: "compaction_policy", ...compaction, reserve_tokens: COMPACTION_RESERVE_TOKENS }));
  }
  const unsubscribe = session.subscribe((event) => {
    if (event.type === "rlm_child_update") {
      const child = event.child ?? {};
      // Metadata only: never copy answer previews, notes, source text or errors
      // into profiling receipts. Snapshot duration is not per-model-call time.
      console.log(JSON.stringify({type:"child_activity",recorded_at:new Date().toISOString(),
        child_id:child.id,parent_id:child.parentId,status:child.status,model:child.model,
        duration_ms:child.durationMs,last_activity_at:child.lastActivityAt,
        stale_ms:child.activityStaleMs,activity:child.activity?.kind,
        tool:child.activity?.toolName,tool_use_count:child.toolUseCount,
        token_count:child.tokenCount,usage_scope:"sdk_child_snapshot_not_additive"}));
    }
    if (event.type === "message_start" && event.message?.role === "assistant") {
      modelStarted = new Date().toISOString();
      modelOrdinal += 1;
      console.log(JSON.stringify({type:"model_start",model_call:modelOrdinal,started_at:modelStarted,
        usage_scope:"root_sdk_session_only"}));
    }
    if (event.type === "message_end" && event.message?.role === "assistant") {
      if (/\b402\b|insufficient balance/i.test(event.message.errorMessage ?? "")) {
        fatalProviderError = "provider_payment_required: 402 insufficient balance; investigation not executed";
        void session.abort().catch(() => undefined);
      }
      console.log(JSON.stringify({ type: "message_end", message: {
        role: "assistant", usage: event.message.usage ?? null,
      }, started_at: modelStarted ?? null, ended_at: new Date().toISOString(),
      model_call: modelOrdinal, usage_scope: "root_sdk_session_only" }));
    }
  });
  try {
    const bridge = JSON.parse(readFileSync(process.env.BIODEMO_PRIME_BRIDGE_CONFIG, 'utf8'));
    await runInvestigation(session, {
      prompt:input.prompt, timeoutSeconds:input.timeout_seconds,
      finalizationReserveSeconds:input.finalization_reserve_seconds,
      specialistWrapupSeconds:input.specialist_wrapup_seconds ?? 0,
      getFatalError:() => fatalProviderError,
      emit:event => console.log(JSON.stringify(event)),
      readStatus:async () => {
        const response = await fetch(bridge.url + '/execution-status', {
          method:'POST', headers:{Authorization:`Bearer ${bridge.token}`,'Content-Type':'application/json'},
          body:'{}', signal:AbortSignal.timeout(5000),
        });
        if (!response.ok) throw Error(`Manufacturing bridge execution-status failed: HTTP ${response.status}`);
        return response.json();
      },
    });
    console.log(JSON.stringify({ type: "session", id: session.sessionId, file: session.sessionFile }));
    error = fatalProviderError ?? session.agent.state.errorMessage;
  } finally {
    if (typeof session.getContextTree === "function") {
      const summarize = (node) => ({id:node.id,status:node.status,model:node.model,
        own_usage:node.ownUsage,attributed_total_usage:node.totalUsage,
        children:(node.children ?? []).map(summarize)});
      console.log(JSON.stringify({type:"session_usage_tree",recorded_at:new Date().toISOString(),
        tree:summarize(session.getContextTree()),cost_status:"provider_prices_and_unpersisted_calls_may_be_missing"}));
    }
    unsubscribe();
  }
  if (error) throw new Error(error);
} finally {
  session.dispose();
}
