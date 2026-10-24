// Connection settings for the optional "connected mode". Sample mode is the default and
// the fallback for anything unreadable. Decoding never throws and never writes.

export const CONNECTION_KEY = "manufacturing-os:connection:v1";
export const DEFAULT_TENANT = "demo-northfield";
export const DEFAULT_ACTOR = "priya";

export type ConnectionMode = "sample" | "connected";
export type Connection = {
  mode: ConnectionMode;
  tenant: string;
  actor: string;
};

// Identifiers travel in HTTP headers, so keep them to a conservative alphabet.
const IDENTIFIER = /^[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}$/;
export const isIdentifier = (value: unknown): value is string =>
  typeof value === "string" && IDENTIFIER.test(value);

export const sampleConnection = (): Connection => ({
  mode: "sample",
  tenant: DEFAULT_TENANT,
  actor: DEFAULT_ACTOR,
});

export type LoadedConnection = {
  connection: Connection;
  /** True when something was stored but could not be used. The stored value is left as it is. */
  corrupt: boolean;
};

export function decodeConnection(raw: string | null | undefined): LoadedConnection {
  if (raw === null || raw === undefined) {
    return { connection: sampleConnection(), corrupt: false };
  }
  try {
    const value: unknown = JSON.parse(raw);
    if (typeof value !== "object" || value === null || Array.isArray(value)) {
      throw new Error("not an object");
    }
    const { mode, tenant, actor } = value as Record<string, unknown>;
    if (mode !== "sample" && mode !== "connected") throw new Error("bad mode");
    if (!isIdentifier(tenant) || !isIdentifier(actor)) throw new Error("bad identity");
    return { connection: { mode, tenant, actor }, corrupt: false };
  } catch {
    return { connection: sampleConnection(), corrupt: true };
  }
}

export function encodeConnection(connection: Connection): string {
  return JSON.stringify({
    mode: connection.mode,
    tenant: connection.tenant,
    actor: connection.actor,
  });
}

export function loadConnection(): LoadedConnection {
  try {
    return decodeConnection(localStorage.getItem(CONNECTION_KEY));
  } catch {
    return { connection: sampleConnection(), corrupt: false };
  }
}

export function saveConnection(connection: Connection): boolean {
  try {
    localStorage.setItem(CONNECTION_KEY, encodeConnection(connection));
    return true;
  } catch {
    return false;
  }
}
