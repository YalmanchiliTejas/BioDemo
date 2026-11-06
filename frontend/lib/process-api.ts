import { authHeaders, authMode, redirectToSignIn, SIGNED_OUT_MESSAGE } from './auth';
import { forgetMutable, remember } from './cache';

/** Carries the HTTP status so callers can tell a usage limit (429) or expiry (410) from other failures. */
export class ProcessApiError extends Error {
  constructor(message: string, public status: number) { super(message); }
}

export const PROCESS_API = process.env.NEXT_PUBLIC_LIFESCI_API_URL ?? 'http://127.0.0.1:8100';

export async function processRequest<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${PROCESS_API}${path}`, {
    method: body !== undefined ? 'POST' : 'GET',
    headers: { 'Content-Type': 'application/json', ...(await authHeaders()),
      ...(body !== undefined ? { 'Idempotency-Key': crypto.randomUUID() } : {}) },
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
  });
  if (response.status === 401 && authMode() === 'supabase') { redirectToSignIn(); throw new Error(SIGNED_OUT_MESSAGE); }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new ProcessApiError(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail ?? data), response.status);
  if (body === undefined) remember(path, data); else forgetMutable();
  return data;
}
