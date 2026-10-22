/** Project-owned provider overrides; credentials stay in memory. */
export function configureProjectProvider(authStorage, modelRegistry, env = process.env) {
  const configuredToken = env.BIODEMO_MODAL_PROXY_TOKEN?.trim() || env.MODAL_PROXY_TOKEN?.trim();
  const token = configuredToken?.replace(/^Bearer\s+/i, "");
  const baseUrl = env.BIODEMO_MODAL_BASE_URL?.trim();
  if (!token && !baseUrl) return;
  if (token && /[\r\n]/.test(token)) {
    throw new Error("BIODEMO_MODAL_PROXY_TOKEN must be a single-line token");
  }
  if (baseUrl) {
    const url = new URL(baseUrl);
    if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password) {
      throw new Error("BIODEMO_MODAL_BASE_URL must be an HTTP(S) URL without embedded credentials");
    }
  }
  if (token) authStorage.setRuntimeApiKey("modal", token);
  modelRegistry.registerProvider("modal", {
    ...(baseUrl ? { baseUrl } : {}),
    ...(token ? { authHeader: true } : {}),
  });
}

export async function validateModalAuthentication(model, modelRegistry) {
  if (model?.provider !== "modal") return;
  const resolved = await modelRegistry.getApiKeyAndHeaders(model);
  const authorization = resolved.headers?.Authorization ?? resolved.headers?.authorization ??
    (resolved.apiKey ? `Bearer ${resolved.apiKey}` : "");
  if (!resolved.ok || !/^Bearer wk-[^.\s]+\.ws-[^\s]+$/.test(authorization)) {
    throw new Error("Modal proxy authentication is missing or has the wrong format. Export " +
      "BIODEMO_MODAL_PROXY_TOKEN or MODAL_PROXY_TOKEN as wk-<id>.ws-<secret> in the shell " +
      "launching the investigation. .env.local is not automatically loaded.");
  }
}
