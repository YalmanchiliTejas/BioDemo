'use client';
import { useEffect, useState } from 'react';
import { redirectToSignIn, selectedOrganization, selectOrganization, signInAvailable, useSession } from '@/lib/auth';
import { getAccount, organizationDestination } from '@/lib/organizations-api';
import { cached } from '@/lib/cache';

/** Supabase accounts and local test accounts follow the same path: signed in, a member, an organization selected. */
export function SessionGate({ children }: { children: React.ReactNode }) {
  const { user, loading } = useSession();
  const userId = user?.id;
  // A cached account means this tab already passed the gate; still re-check in the background.
  const [ready, setReady] = useState(() => !!cached('connector:/account'));
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  useEffect(()=>{
    if (loading || !signInAvailable()) return;
    if (!userId) { redirectToSignIn('required'); return; }
    let active = true;
    if (!cached('connector:/account')) setReady(false);
    getAccount().then(async account=>{
      if (!active) return;
      const selected = selectedOrganization(userId);
      const org = account.organizations.find(o=>o.id===selected) ?? (account.organizations.length===1?account.organizations[0]:null);
      if (!org) { window.location.assign('/account/'); return; }
      await selectOrganization(org.id);
      const target = organizationDestination(org);
      if (target === '/onboarding/start/' && !window.location.pathname.startsWith('/onboarding/')) { window.location.assign(target); return; }
      if (active) setReady(true);
    }).catch(err=>{ if(active) setError(err.message); });
    return ()=>{ active=false; };
  }, [userId, loading, attempt]);
  if (!signInAvailable()) return <div role="alert" className="p-10">Sign-in is not configured for this deployment. Configure the Supabase project URL and public key, then rebuild the frontend.</div>;
  if (error) return <div role="alert" className="p-10">{error}<button className="ml-3 underline" onClick={()=>{setError('');setAttempt(i=>i+1);}}>Try again</button></div>;
  if (loading || !user || !ready) return <div className="p-10" role="status">Checking your workspace access…</div>;
  return <>{children}</>;
}
