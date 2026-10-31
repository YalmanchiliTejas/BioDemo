'use client';
import { useEffect, useState, type FormEvent } from 'react';
import Link from 'next/link';
import { BrandMark } from '@/components/shell/BrandMark';
import { authConfigured, redirectToSignIn, safeNext, selectOrganization, signOut, useSession } from '@/lib/auth';
import { connectorRequest } from '@/lib/connectors-api';
import { getAccount, organizationDestination, type Account, type Organization } from '@/lib/organizations-api';

export default function AccountPage() {
  const { user, loading } = useSession();
  const userId = user?.id;
  const [account, setAccount] = useState<Account | null>(null);
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  useEffect(()=>{
    if (loading || !authConfigured()) return;
    if (!userId) { redirectToSignIn('required'); return; }
    let active = true;
    getAccount().then(async a=>{
      if (!active) return;
      const explicit = new URLSearchParams(window.location.search).get('manage') === '1';
      if (a.organizations.length === 1 && !explicit) {
        await selectOrganization(a.organizations[0].id);
        const next = safeNext(new URLSearchParams(window.location.search).get('next'), '/cmo/');
        window.location.assign(organizationDestination(a.organizations[0], next));
      } else setAccount(a);
    }).catch(err=>{ if (active) setError(err.message); });
    return ()=>{ active = false; };
  }, [userId, loading, attempt]);
  async function enter(org: Organization) {
    setBusy(true); setError('');
    try { await selectOrganization(org.id); window.location.assign(organizationDestination(org)); }
    catch(err) { setError((err as Error).message); setBusy(false); }
  }
  async function create(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError('');
    try { await enter(await connectorRequest<Organization>('/account/organizations', {name})); }
    catch(err) { setError((err as Error).message); setBusy(false); }
  }
  return <main className="min-h-screen bg-canvas px-5 py-8"><div className="mx-auto max-w-xl"><header className="flex items-center justify-between"><BrandMark href="/"/><Link href="/sign-in/" className="text-sm text-brand-teal">Sign in</Link></header>
    <section className="mt-12 rounded-xl border border-border-hairline bg-white p-7"><h1 className="text-3xl font-medium">Your organizations</h1><p className="mt-3 text-sm text-text-secondary">{user?.email}</p>
      {!authConfigured() && <p role="alert" className="setup-message error mt-5">Sign-in is not configured. Ask your administrator to configure Supabase.</p>}
      {error && <div role="alert" className="setup-message error mt-5">{error}<button className="setup-text-link" onClick={()=>{setError('');setAttempt(i=>i+1);}}>Try again</button></div>}
      {!account && !error && authConfigured() && <p className="mt-6" role="status">Loading your organizations…</p>}
      {account && <><div className="mt-6 space-y-3">{account.organizations.map(org=><button key={org.id} onClick={()=>void enter(org)} disabled={busy} className="w-full rounded-lg border border-border-hairline p-4 text-left hover:bg-surface-secondary"><span className="block font-medium">{org.name}</span><span className="mt-1 block text-xs text-text-secondary">{org.roles.join(', ')} · {org.site_ids.length?org.site_ids.join(', '):'Organization-wide'}</span></button>)}</div>
      {!account.organizations.length && <p className="mt-5 text-sm leading-6">You do not have access to an organization yet. Create one below, or ask your administrator to grant access to this email address.</p>}
      {account.can_create_organization && <form className="auth-fields mt-8" onSubmit={create}><h2 className="text-lg font-medium">Create an organization</h2><label>Organization name<input required minLength={2} maxLength={120} value={name} onChange={e=>setName(e.target.value)} autoComplete="organization"/></label><p className="text-xs leading-5 text-text-secondary">You will be its administrator. Team access stays under your control. Each account can create one organization and join other organizations.</p><button disabled={busy} className="setup-primary">{busy?'Please wait…':'Create organization & continue'}</button></form>}
      </>}
      {user && <button className="setup-text-link mt-8" onClick={async()=>{try {await signOut();window.location.assign('/sign-in/');}catch(err){setError((err as Error).message);}}}>Sign out</button>}
    </section></div></main>;
}
