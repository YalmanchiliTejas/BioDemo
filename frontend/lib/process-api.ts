import { authHeaders, authMode, redirectToSignIn, SIGNED_OUT_MESSAGE } from './auth';

export const PROCESS_API = process.env.NEXT_PUBLIC_LIFESCI_API_URL ?? 'http://127.0.0.1:8100';

export async function processRequest<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${PROCESS_API}${path}`, {
    method: body !== undefined ? 'POST' : 'GET',
    headers: { 'Content-Type': 'application/json', ...(await authHeaders()),
      ...(body !== undefined ? { 'Idempotency-Key': crypto.randomUUID() } : {}) },
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
  });
  if (response.status === 401 && authMode() === 'supabase') { redirectToSignIn(); throw new Error(SIGNED_OUT_MESSAGE); }
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail ?? data));
  return data;
}
