'use client';

import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { selectedOrganization, useSession } from './auth';
import { getAccount, type Account, type Organization } from './organizations-api';

type Workspace = ReturnType<typeof useSession> & {
  account: Account | null; organization: Organization | null; error: string; loadingAccount: boolean;
  mobileOpen: boolean; setMobileOpen: (value: boolean) => void;
  collapsed: boolean; setCollapsed: (value: boolean) => void; reload: () => void;
};
const Context = createContext<Workspace | null>(null);

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const session = useSession();
  const [account, setAccount] = useState<Account | null>(null);
  const [error, setError] = useState('');
  const [loadingAccount, setLoadingAccount] = useState(true);
  const [attempt, setAttempt] = useState(0);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [collapsed, setCollapsedState] = useState(false);
  useEffect(() => { try { setCollapsedState(localStorage.getItem('sievance.navigation.v1') === 'collapsed'); } catch { /* Session preference only. */ } }, []);
  useEffect(() => {
    let active = true;
    setLoadingAccount(true); setError(''); setAccount(null);
    getAccount().then(value => { if (active) setAccount(value); }).catch(err => { if (active) setError(err.message); }).finally(() => { if (active) setLoadingAccount(false); });
    return () => { active = false; };
  }, [session.user?.id, attempt]);
  const selected = account ? selectedOrganization(session.user?.id ?? account.actor_id) : null;
  const organization = account?.organizations.find(org => org.id === selected) ?? (account?.organizations.length === 1 ? account.organizations[0] : null) ?? null;
  const setCollapsed = (value: boolean) => {
    setCollapsedState(value);
    try { localStorage.setItem('sievance.navigation.v1', value ? 'collapsed' : 'expanded'); } catch { /* Session preference only. */ }
  };
  return <Context.Provider value={{ ...session, account, organization, error, loadingAccount, mobileOpen, setMobileOpen, collapsed, setCollapsed, reload: () => setAttempt(i => i + 1) }}>{children}</Context.Provider>;
}

export function useWorkspace() {
  const value = useContext(Context);
  if (!value) throw new Error('WorkspaceProvider is required');
  return value;
}
