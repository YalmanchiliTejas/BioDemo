import { useEffect, useState } from 'react';
import { createClient, type SupabaseClient, type User } from '@supabase/supabase-js';
import { clearCache } from './cache';

/**
 * Sign-in and API identity. Supabase Auth when configured at build time; otherwise, and whenever
 * NEXT_PUBLIC_LOCAL_LOGIN=1 under `next dev`, local test accounts checked by the development API.
 * Production builds always use Supabase.
 */
const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL ?? '';
const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? '';
const LOCAL_LOGIN = process.env.NODE_ENV !== 'production' && process.env.NEXT_PUBLIC_LOCAL_LOGIN === '1';
const API = process.env.NEXT_PUBLIC_LIFESCI_API_URL ?? 'http://127.0.0.1:8100';
const LOCAL_SESSION = 'sievance.local-session.v1';
const LOCAL_SESSION_EVENT = 'sievance:local-session';

export type AuthMode = 'supabase' | 'development';
export const authConfigured = () => Boolean(SUPABASE_URL && SUPABASE_ANON_KEY);
export const authMode = (): AuthMode => (process.env.NODE_ENV === 'production' || (authConfigured() && !LOCAL_LOGIN) ? 'supabase' : 'development');
/** True when this mode can sign anyone in: Supabase is configured, or local test accounts are in use. */
export const signInAvailable = () => authMode() === 'development' || authConfigured();

type LocalSession = { tenant_id: string; actor_id: string; email: string; name: string };
function localSession(): LocalSession | null {
  if (typeof window === 'undefined') return null;
  try { return JSON.parse(localStorage.getItem(LOCAL_SESSION) ?? 'null'); } catch { return null; }
}
function setLocalSession(value: LocalSession | null) {
  if (value) localStorage.setItem(LOCAL_SESSION, JSON.stringify(value)); else localStorage.removeItem(LOCAL_SESSION);
  window.dispatchEvent(new Event(LOCAL_SESSION_EVENT));
}
const localUser = (session: LocalSession) => ({
  id: session.actor_id, email: session.email, user_metadata: { full_name: session.name },
  app_metadata: {}, aud: 'local', created_at: '',
}) as unknown as User;

export type LocalAccount = { email: string; name: string; role: string; site_id: string | null };
/** Local test accounts offered by the development API, for the sign-in hint. Never includes the password. */
export async function localAccounts(): Promise<{ accounts: LocalAccount[]; password_env: string; default_password: boolean } | null> {
  try { const response = await fetch(`${API}/v1/dev/accounts`); return response.ok ? await response.json() : null; } catch { return null; }
}

let client: SupabaseClient | null = null;
export function supabase(): SupabaseClient {
  if (!authConfigured()) throw new Error('Sign-in is not configured for this deployment.');
  client ??= createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
    auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
  });
  return client;
}

export async function authHeaders(): Promise<Record<string, string>> {
  if (authMode() !== 'supabase') {
    const session = localSession();
    if (!session) return {};
    // Laptop demo visitors are anonymous; the development API recognises them by this header.
    return { 'X-Tenant-Id': session.tenant_id, 'X-Actor-Id': session.actor_id,
      ...(session.actor_id.startsWith('demo-visitor-') ? { 'X-Demo-Visitor': '1' } : {}) };
  }
  // getSession refreshes an expired access token when a refresh token is available.
  const { data, error } = await supabase().auth.getSession();
  if (error) throw new Error(SIGNED_OUT_MESSAGE);
  if (!data.session) return {};
  const headers: Record<string, string> = { Authorization: `Bearer ${data.session.access_token}` };
  const organization = localStorage.getItem(`sievance.organization:${data.session.user.id}`);
  if (organization) headers['X-Organization-Id'] = organization;
  return headers;
}

/** Only same-site paths are accepted as a post-sign-in destination. */
export function safeNext(value: string | null | undefined, fallback = '/dashboard/') {
  return value && value.startsWith('/') && !value.startsWith('//') && !/[\\\x00-\x20]/.test(value) ? value : fallback;
}

/** After a 401 in Supabase mode, send the person to sign in and bring them back afterwards. */
export function redirectToSignIn(reason: 'expired' | 'required' = 'expired') {
  if (typeof window === 'undefined') return;
  if (window.location.pathname.startsWith('/sign-in')) return;
  const next = `${window.location.pathname}${window.location.search}`;
  window.location.assign(`/sign-in/?next=${encodeURIComponent(next)}&reason=${reason}`);
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
  if (authMode() === 'development') {
    let response: Response;
    try { response = await fetch(`${API}/v1/dev/session`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: email.trim(), password }) }); }
    catch { throw new Error('Cannot reach the local API. Start the backend, then try again.'); }
    if (response.status === 401) throw new Error('Email or password is incorrect.');
    if (response.status === 404) throw new Error('The API is not running in development mode, so local test accounts are unavailable.');
    if (!response.ok) throw new Error('Sign-in failed. Try again.');
    setLocalSession(await response.json());
    return;
  }
  const { error } = await attempt(() => supabase().auth.signInWithPassword({ email: email.trim(), password }));
  const message = plain(error, error?.status === 400 ? 'Email or password is incorrect.' : 'Sign-in failed. Try again, or contact your administrator.');
  if (message) throw new Error(message);
}

export async function signOut() {
  clearCache();
  if (authMode() !== 'supabase') { setLocalSession(null); return; }
  const { error } = await attempt(() => supabase().auth.signOut());
  if (error) throw new Error('Sign-out failed. Try again.');
}

export async function sendPasswordReset(email: string) {
  if (authMode() !== 'supabase') throw new Error('Local test accounts share one password, set by LIFESCI_DEV_PASSWORD on the API.');
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

/** Personal display metadata; approval attribution continues to use verified identity. */
export async function updateDisplayName(name: string) {
  const full_name = name.trim();
  if (!full_name || full_name.length > 80) throw new Error('Enter a display name between 1 and 80 characters.');
  const { error } = await attempt(() => supabase().auth.updateUser({ data: { full_name } }));
  const message = plain(error, 'Your display name could not be saved. Try again.');
  if (message) throw new Error(message);
}

/** The signed-in user in Supabase mode; `loading` is true until the stored session has been read. */
export function useSession() {
  const enabled = authMode() === 'supabase' && authConfigured();
  const local = authMode() === 'development';
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(enabled || local);
  useEffect(() => {
    if (!local) return;
    const read = () => { const session = localSession(); setUser(session ? localUser(session) : null); setLoading(false); };
    read();
    window.addEventListener(LOCAL_SESSION_EVENT, read);
    window.addEventListener('storage', read);
    return () => { window.removeEventListener(LOCAL_SESSION_EVENT, read); window.removeEventListener('storage', read); };
  }, [local]);
  useEffect(() => {
    if (!enabled) return;
    const auth = supabase().auth;
    let active = true;
    void auth.getSession().then(({ data }) => { if (active) { setUser(data.session?.user ?? null); setLoading(false); } }).catch(() => { if (active) setLoading(false); });
    const { data } = auth.onAuthStateChange((_event, session) => { setUser(session?.user ?? null); setLoading(false); });
    return () => { active = false; data.subscription.unsubscribe(); };
  }, [enabled]);
  return { user, email: user?.email ?? null, loading, mode: authMode() };
}


export async function signUp(email: string, password: string) {
  const { data, error } = await attempt(() => supabase().auth.signUp({
    email: email.trim(), password,
    options: { emailRedirectTo: `${window.location.origin}/account/` },
  }));
  const message = plain(error, error?.status === 429 ? 'Too many requests. Wait a few minutes and try again.' : 'Account creation failed. Try again or contact your administrator.');
  if (message) throw new Error(message);
  return Boolean(data.session);
}

/** Demo workspaces: one click, no account. Supabase anonymous sign-in in production; on a laptop
 *  (local test accounts) a generated local demo actor, which the development API accepts the same way. */
export class DemoSignedInError extends Error {
  constructor(public email: string) { super(`You're signed in as ${email}. The demo runs in a separate, anonymous workspace.`); }
}

export async function signInForDemo() {
  if (authMode() === 'development') {
    const current = localSession();
    if (current?.actor_id.startsWith('demo-visitor-')) return;
    const id = `demo-visitor-${Math.random().toString(36).slice(2, 10)}`;
    setLocalSession({ tenant_id: 'demo-pending', actor_id: id, email: '', name: 'Demo visitor' });
    return;
  }
  const { data } = await attempt(() => supabase().auth.getSession());
  const user = data.session?.user;
  if (user?.is_anonymous) return; // a returning demo visitor keeps their workspace
  // A real account never gets a demo tenant; say so instead of failing at the API.
  if (user) throw new DemoSignedInError(user.email ?? 'an account');
  const { error } = await attempt(() => supabase().auth.signInAnonymously());
  if (error && /anonymous sign-ins are disabled/i.test(error.message ?? ''))
    throw new Error('Demo sign-in isn’t switched on for this site yet (Supabase anonymous sign-ins are disabled).');
  const message = plain(error, 'The demo could not start. Try again in a moment.');
  if (message) throw new Error(message);
}

/** Local demo sessions send the tenant in a header, so point it at the new demo workspace. */
export function adoptLocalDemoTenant(tenant: string) {
  const session = localSession();
  if (session && authMode() === 'development') setLocalSession({ ...session, tenant_id: tenant });
}

export async function selectOrganization(id: string) {
  let userId = localSession()?.actor_id;
  if (authMode() === 'supabase') {
    const { data, error } = await supabase().auth.getSession();
    userId = error ? undefined : data.session?.user.id;
  }
  if (!userId) throw new Error(SIGNED_OUT_MESSAGE);
  if (localStorage.getItem(`sievance.organization:${userId}`) !== id) clearCache();
  localStorage.setItem(`sievance.organization:${userId}`, id);
  // Drop the previous workspace's display preferences when changing organizations.
  localStorage.removeItem('mos.context.v1');
}

export function selectedOrganization(userId: string) {
  return localStorage.getItem(`sievance.organization:${userId}`);
}
