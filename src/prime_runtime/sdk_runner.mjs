/** Single-run TypeScript SDK host. JSON on stdin; structured events on stdout. */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const input = JSON.parse(readFileSync(0, "utf8"));
const sdkPath = join(input.bundle_root, "packages/coding-agent/dist/index.js");
const sdk = await import(pathToFileURL(sdkPath).href);
const { AuthStorage, ModelRegistry, SessionManager, DefaultResourceLoader, createAgentSession, getAgentDir } = sdk;

// Discovery is limited to the two required skills. SDK sessions retain Prime's
// native kernel and child-agent runtime; the manufacturing bridge bounds data.
const loader = new DefaultResourceLoader({
  cwd: input.cwd,
  agentDir: getAgentDir(),
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
let model;
if (input.model) {
  const slash = input.model.indexOf("/");
  if (slash < 1) throw new Error("BIODEMO_PRIME_MODEL must be provider/model");
  model = modelRegistry.find(input.model.slice(0, slash), input.model.slice(slash + 1));
  if (!model) throw new Error(`Prime SDK model is unavailable: ${input.model}`);
}

const manager = input.session_file
  ? SessionManager.open(input.session_file, input.session_dir, input.cwd)
  : SessionManager.create(input.cwd, input.session_dir);
const { session } = await createAgentSession({
  cwd: input.cwd,
  sessionManager: manager,
  resourceLoader: loader,
  authStorage,
  modelRegistry,
  tools: ["ipython"],
  ...(model ? { model } : {}),
});
let error;
try {
  console.log(JSON.stringify({ type: "session", id: session.sessionId, file: session.sessionFile }));
  const unsubscribe = session.subscribe((event) => {
    if (event.type === "message_end" && event.message?.role === "assistant") {
      console.log(JSON.stringify({ type: "message_end", message: {
        role: "assistant", usage: event.message.usage ?? null,
      } }));
    }
  });
  try {
    await session.prompt(input.prompt);
    console.log(JSON.stringify({ type: "session", id: session.sessionId, file: session.sessionFile }));
    error = session.agent.state.errorMessage;
  } finally {
    unsubscribe();
  }
  if (error) throw new Error(error);
} finally {
  session.dispose();
}
