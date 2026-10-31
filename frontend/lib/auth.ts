import { useEffect, useState } from 'react';
import { createClient, type SupabaseClient, type User } from '@supabase/supabase-js';

/** Sign-in and API identity. Supabase Auth when configured at build time, otherwise the local development identity. */
const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL ?? '';
const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? '';
const DEV_HEADERS = { 'X-Tenant-Id': 'demo-northfield', 'X-Actor-Id': 'priya' };

export type AuthMode = 'supabase' | 'development';
export const authMode = (): AuthMode => (SUPABASE_URL && SUPABASE_ANON_KEY ? 'supabase' : 'development');

let client: SupabaseClient | null = null;
export function supabase(): SupabaseClient {
  if (authMode() !== 'supabase') throw new Error('Sign-in is not configured for this deployment.');
  client ??= createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
    auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
  });
  return client;
}

export async function authHeaders(): Promise<Record<string, string>> {
  if (authMode() !== 'supabase') return { ...DEV_HEADERS };
  // getSession refreshes an expired access token when a refresh token is available.
  const { data } = await supabase().auth.getSession();
  return data.session ? { Authorization: `Bearer ${data.session.access_token}` } : {};
}

/** Only same-site paths are accepted as a post-sign-in destination. */
export function safeNext(value: string | null | undefined, fallback = '/cmo') {
  return value && value.startsWith('/') && !value.startsWith('//') ? value : fallback;
}

/** After a 401 in Supabase mode, send the person to sign in and bring them back afterwards. */
export function redirectToSignIn() {
  if (authMode() !== 'supabase' || typeof window === 'undefined') return;
  if (window.location.pathname.startsWith('/sign-in')) return;
  const next = `${window.location.pathname}${window.location.search}`;
  window.location.assign(`/sign-in/?next=${encodeURIComponent(next)}&reason=expired`);
}
export const SIGNED_OUT_MESSAGE = 'Your session has ended. Sign in again to continue.';

const NETWORK_MESSAGE = 'Cannot reach the sign-in service. Check your connection and try again.';
function plain(error: { message?: string; status?: number; name?: string } | null, fallback: string) {
  if (!error) return null;
  if (error.name === 'AuthRetryableFetchError' || error.status === 0 || /fetch|network/i.test(error.message ?? '')) return NETWORK_MESSAGE;
  return fallback;
}

async function attempt<T>(run: () => Promise<T>): Promise<T> {
  try { return await run(); } catch { throw new Error(NETWORK_MESSAGE); }
}

export async function signIn(email: string, password: string) {
  const { error } = await attempt(() => supabase().auth.signInWithPassword({ email: email.trim(), password }));
  const message = plain(error, error?.status === 400 ? 'Email or password is incorrect.' : 'Sign-in failed. Try again, or contact your administrator.');
  if (message) throw new Error(message);
}

export async function signOut() {
  if (authMode() !== 'supabase') return;
  await attempt(() => supabase().auth.signOut());
}

export async function sendPasswordReset(email: string) {
  const { error } = await attempt(() => supabase().auth.resetPasswordForEmail(email.trim(), { redirectTo: `${window.location.origin}/set-password/` }));
  const message = plain(error, error?.status === 429 ? 'Too many reset requests. Wait a few minutes, then try again.' : 'The reset email could not be sent. Try again, or contact your administrator.');
  if (message) throw new Error(message);
}

export async function updatePassword(password: string) {
  const { error } = await attempt(() => supabase().auth.updateUser({ password }));
  const message = plain(error, error?.message?.toLowerCase().includes('session')
    ? 'This link has expired or was already used. Request a new one from the sign-in page.'
    : error?.message ?? 'The password could not be saved. Try again.');
  if (message) throw new Error(message);
}

/** The signed-in user in Supabase mode; `loading` is true until the stored session has been read. */
export function useSession() {
  const enabled = authMode() === 'supabase';
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(enabled);
  useEffect(() => {
    if (!enabled) return;
    const auth = supabase().auth;
    let active = true;
    void auth.getSession().then(({ data }) => { if (active) { setUser(data.session?.user ?? null); setLoading(false); } });
    const { data } = auth.onAuthStateChange((_event, session) => { setUser(session?.user ?? null); setLoading(false); });
    return () => { active = false; data.subscription.unsubscribe(); };
  }, [enabled]);
  return { user, email: user?.email ?? null, loading, mode: enabled ? 'supabase' as const : 'development' as const };
}
