// Typed client for the /v1 API. Development sign-in sends tenant and actor headers only;
// roles always come from the server.

import type {
  ConnectorCatalog,
  ConnectorConfig,
  ConnectorRecord,
  DecisionInput,
  EvidenceRecord,
  Health,
  Me,
  Mission,
  MissionInput,
  MissionNote,
  Outcome,
  OutcomeInput,
  Proposal,
  ProposalInput,
  StreamResult,
} from "./types";

export * from "./types";

export const CONFLICT_MESSAGE =
  "This changed since you loaded it. Refresh and review the current version.";

export class ApiError extends Error {
  readonly status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function detailText(body: unknown): string {
  if (!body || typeof body !== "object") return "";
  const detail = (body as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === "string") return item;
        const { msg, loc } = (item ?? {}) as { msg?: unknown; loc?: unknown };
        const where = Array.isArray(loc)
          ? loc.filter((p) => p !== "body").join(".")
          : "";
        return `${where ? `${where}: ` : ""}${typeof msg === "string" ? msg : "invalid value"}`;
      })
      .join("; ");
  }
  return "";
}

/** Readable message for a failed response. `body` is the parsed JSON body, if any. */
export function describeError(status: number, body: unknown): string {
  const detail = detailText(body);
  if (status === 403) return `Not permitted: ${detail || "this action is not allowed for you"}`;
  if (status === 409) return CONFLICT_MESSAGE;
  if (status === 400 || status === 422) return detail || "The server rejected this request.";
  if (status === 401) return `Sign-in required: ${detail || "the server did not accept this identity"}`;
  if (status === 404) return detail ? `Not found: ${detail}` : "Not found.";
  return "The server could not complete this request. Try again; if it continues, ask an administrator to check the server log.";
}

export type ClientIdentity = { tenant: string; actor: string };

export const newIdempotencyKey = () => crypto.randomUUID();

export function createClient(identity: ClientIdentity, baseUrl = "") {
  async function request<T>(
    method: "GET" | "POST",
    path: string,
    body?: unknown,
    idempotencyKey?: string,
    withIdentity = true,
  ): Promise<T> {
    const headers: Record<string, string> = { Accept: "application/json" };
    if (withIdentity) {
      headers["X-Tenant-Id"] = identity.tenant;
      headers["X-Actor-Id"] = identity.actor;
    }
    if (method === "POST") {
      headers["Content-Type"] = "application/json";
      headers["Idempotency-Key"] = idempotencyKey ?? newIdempotencyKey();
    }
    let response: Response;
    try {
      response = await fetch(`${baseUrl}${path}`, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch {
      throw new ApiError(0, "Could not reach the server. Check that it is running and try again.");
    }
    let parsed: unknown = null;
    try {
      parsed = await response.json();
    } catch {
      parsed = null;
    }
    if (!response.ok) throw new ApiError(response.status, describeError(response.status, parsed));
    return parsed as T;
  }
  const q = (params: Record<string, string | number | undefined>) => {
    const search = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) if (v !== undefined) search.set(k, String(v));
    const text = search.toString();
    return text ? `?${text}` : "";
  };
  const enc = encodeURIComponent;
  return {
    connectorCatalog: () => request<ConnectorCatalog>("GET", "/v1/connectors/catalog"),
    listConnectors: () => request<{ items: ConnectorRecord[] }>("GET", "/v1/connectors").then((r) => r.items),
    configureConnector: (input: ConnectorConfig) => request<ConnectorRecord>("POST", "/v1/connectors", input),
    previewConnector: (id: string) => request<Record<string, unknown>>("POST", `/v1/connectors/${enc(id)}/preview`),
    syncConnector: (id: string) => request<Record<string, unknown>>("POST", `/v1/connectors/${enc(id)}/sync`),
    health: () => request<Health>("GET", "/v1/health", undefined, undefined, false),
    me: () => request<Me>("GET", "/v1/me"),
    listMissions: () => request<{ items: Mission[] }>("GET", "/v1/missions").then((r) => r.items),
    getMission: (id: string) => request<Mission>("GET", `/v1/missions/${enc(id)}`),
    createMission: (input: MissionInput, key?: string) =>
      request<Mission>("POST", "/v1/missions", input, key),
    addNote: (id: string, body: string, key?: string) =>
      request<MissionNote>("POST", `/v1/missions/${enc(id)}/notes`, { body }, key),
    stream: (id: string, after: number) =>
      request<StreamResult>("GET", `/v1/missions/${enc(id)}/stream${q({ after })}`),
    listProposals: (id: string) =>
      request<{ items: Proposal[] }>("GET", `/v1/missions/${enc(id)}/proposals`).then((r) => r.items),
    listAllProposals: () =>
      request<{ items: Proposal[] }>("GET", "/v1/proposals").then((r) => r.items),
    propose: (input: ProposalInput, key?: string) =>
      request<Proposal>("POST", "/v1/proposals", input, key),
    decide: (id: string, input: DecisionInput) =>
      request<{ proposal: Proposal }>("POST", `/v1/proposals/${enc(id)}/decisions`, input),
    recordOutcome: (id: string, input: OutcomeInput) =>
      request<Outcome>("POST", `/v1/proposals/${enc(id)}/outcomes`, input),
    listEvidence: (limit = 200, cursor?: string) =>
      request<{ items: EvidenceRecord[]; next_cursor: string | null }>(
        "GET",
        `/v1/records/evidence${q({ limit, cursor })}`,
      ),
  };
}

export type ApiClient = ReturnType<typeof createClient>;

export const errorMessage = (error: unknown): string =>
  error instanceof Error ? error.message : "Something went wrong.";
