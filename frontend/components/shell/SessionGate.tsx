'use client';
import { useEffect, useState } from 'react';
import { authConfigured, redirectToSignIn, selectedOrganization, selectOrganization, useSession } from '@/lib/auth';
import { getAccount, organizationDestination } from '@/lib/organizations-api';

export function SessionGate({ children }: { children: React.ReactNode }) {
  const { user, loading, mode } = useSession();
  const userId = user?.id;
  const [ready, setReady] = useState(false);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  useEffect(()=>{
    if (mode !== 'supabase' || loading || !authConfigured()) return;
    if (!userId) { redirectToSignIn('required'); return; }
    let active = true;
    setReady(false);
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
  }, [userId, loading, mode, attempt]);
  if (mode === 'development') return <>{children}</>;
  if (!authConfigured()) return <div role="alert" className="p-10">Sign-in is not configured for this deployment. Configure the Supabase project URL and public key, then rebuild the frontend.</div>;
  if (error) return <div role="alert" className="p-10">{error}<button className="ml-3 underline" onClick={()=>{setError('');setAttempt(i=>i+1);}}>Try again</button></div>;
  if (loading || !user || !ready) return <div className="p-10" role="status">Checking your workspace access…</div>;
  return <>{children}</>;
}
