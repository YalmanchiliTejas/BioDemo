'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Building2, Check, ChevronDown, ChevronRight, HelpCircle, LogOut, Menu, Search, Settings, UserRound } from 'lucide-react';
import { organizationDestination } from '@/lib/organizations-api';
import { selectOrganization, signOut } from '@/lib/auth';
import { useWorkspace } from '@/lib/workspace-context';
import { useTutorial } from '@/lib/tutorial-context';
import { setReviewer, useReviewer } from '@/lib/reviewer';
import { NotificationBell } from './NotificationBell';
import { OverallFeedbackButton } from '../process/DemoFeedback';
import { useDemo } from '@/lib/demo-api';

export function TopHeader({ onSearch }: { onSearch: () => void }) {
  const { demo } = useDemo();
  const path = usePathname();
  const workspace = useWorkspace();
  const guide = useTutorial();
  const reviewer = useReviewer();
  const [menu, setMenu] = useState<'account' | 'organization' | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const container = useRef<HTMLElement>(null);
  const trigger = useRef<HTMLButtonElement | null>(null);
  const name = String(workspace.user?.user_metadata?.full_name || workspace.email?.split('@')[0] || reviewer || 'Your account');
  const initials = name.split(/[\s._-]+/).filter(Boolean).slice(0, 2).map(word => word[0]).join('').toUpperCase();
  const organizationName = workspace.organization?.name ?? (workspace.mode === 'development' ? 'Development workspace' : workspace.loadingAccount ? 'Loading…' : 'Select organization');
  useEffect(() => { if (workspace.email) setReviewer(workspace.email); }, [workspace.email]);
  useEffect(() => { setMenu(null); setError(''); }, [path]);
  useEffect(() => {
    if (!menu) return;
    const outside = (e: PointerEvent) => { if (!container.current?.contains(e.target as Node)) setMenu(null); };
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') { setMenu(null); trigger.current?.focus(); } };
    document.addEventListener('pointerdown', outside); document.addEventListener('keydown', key);
    return () => { document.removeEventListener('pointerdown', outside); document.removeEventListener('keydown', key); };
  }, [menu]);
  const toggle = (value: 'account' | 'organization', target: HTMLButtonElement) => { trigger.current = target; setError(''); setMenu(menu === value ? null : value); };
  async function switchTo(id: string) {
    const organization = workspace.account?.organizations.find(org => org.id === id);
    if (!organization || id === workspace.organization?.id) return;
    setBusy(true); setError('');
    try { await selectOrganization(id); window.location.assign(organizationDestination(organization)); }
    catch (err) { setError((err as Error).message); setBusy(false); }
  }
  async function leave() {
    setBusy(true); setError('');
    try { await signOut(); window.location.assign('/sign-in/'); }
    catch (err) { setError((err as Error).message); setBusy(false); }
  }
  return <header ref={container} className="workspace-header">
    <div className="header-start">
      <button type="button" className="chrome-icon mobile-only" aria-label="Open navigation" aria-controls="workspace-navigation" aria-expanded={workspace.mobileOpen} onClick={() => { setMenu(null); guide.close(); workspace.setMobileOpen(true); }}><Menu size={20} /></button>
      <button type="button" className="header-search" aria-label="Search pages" aria-keyshortcuts="Meta+K" onClick={() => { setMenu(null); guide.close(); onSearch(); }}><Search size={15} /><span>Search pages and actions…</span><kbd>⌘K</kbd></button>
    </div>
    <div className="header-actions">
      {workspace.mode === 'development' && <span className="local-badge" title="Signed in with a synthetic local test account. Production builds never offer this.">Local test</span>}
      <div className="chrome-dropdown"><button type="button" data-guide="organization-switcher" className="organization-switcher" aria-label={`Organization: ${organizationName}. Switch organization`} aria-expanded={menu === 'organization'} onClick={e => toggle('organization', e.currentTarget)}><Building2 size={15} /><strong>{organizationName}</strong><ChevronDown size={13} /></button>
        {menu === 'organization' && <div className="chrome-popover" aria-label="Organization switcher"><div className="popover-label">Your organizations</div>{workspace.loadingAccount && <p role="status">Loading organizations…</p>}{workspace.error && <div role="alert"><p>{workspace.error}</p><button type="button" className="popover-item" onClick={workspace.reload}>Try again</button></div>}{workspace.account?.organizations.map(org => <button type="button" className="popover-item" key={org.id} disabled={busy || org.id === workspace.organization?.id} onClick={() => switchTo(org.id)}><Building2 size={15} /><span>{org.name}<small>{org.roles.join(', ')}</small></span>{org.id === workspace.organization?.id && <Check size={15} />}</button>)}{error && <p role="alert">{error}</p>}<div className="popover-divider" /><Link href="/settings/organization/" className="popover-item"><Settings size={15} />Organization settings</Link><Link href="/account/?manage=1" className="popover-item"><span>Manage organizations</span><ChevronRight size={14} /></Link></div>}
      </div>
      {demo && <OverallFeedbackButton />}
      <NotificationBell />
      <button type="button" className="chrome-icon" data-guide="help" aria-label="Open workspace guide" title="Workspace guide" aria-expanded={guide.opened} onClick={() => { setMenu(null); if (guide.opened) guide.close(); else guide.open(); }}><HelpCircle size={18} /></button>
      <div className="chrome-dropdown"><button type="button" className="account-trigger" data-guide="profile" aria-label="Open account menu" aria-expanded={menu === 'account'} onClick={e => toggle('account', e.currentTarget)}><span className="workspace-avatar">{initials}</span></button>
        {menu === 'account' && <div className="chrome-popover account-popover" aria-label="Account menu"><div className="popover-account"><span className="workspace-avatar">{initials}</span><div><strong>{name}</strong><small>{workspace.email ?? 'Not signed in'}</small></div></div><div className="popover-divider" /><Link className="popover-item" href="/settings/profile/"><UserRound size={15} />My profile</Link><button type="button" className="popover-item" disabled={busy} onClick={leave}><LogOut size={15} />{busy ? 'Signing out…' : 'Sign out'}</button>{error && <p role="alert">{error}</p>}</div>}
      </div>
    </div>
  </header>;
}
