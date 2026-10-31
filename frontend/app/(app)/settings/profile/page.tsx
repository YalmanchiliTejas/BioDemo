'use client';

import { useEffect, useState, type FormEvent } from 'react';
import Link from 'next/link';
import { ArrowUpRight, Building2, KeyRound, Save, ShieldCheck } from 'lucide-react';
import { SettingsFrame } from '@/components/shell/SettingsFrame';
import { useWorkspace } from '@/lib/workspace-context';
import { sendPasswordReset, updateDisplayName } from '@/lib/auth';
import { setReviewer, useReviewer } from '@/lib/reviewer';

export default function ProfilePage() {
  const workspace = useWorkspace();
  const reviewer = useReviewer();
  const savedName = workspace.mode === 'development' ? reviewer : String(workspace.user?.user_metadata?.full_name || '');
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  useEffect(() => { setName(savedName); }, [savedName]);
  const display = savedName || workspace.email?.split('@')[0] || 'Your profile';
  const initials = display.split(/[\s._-]+/).filter(Boolean).slice(0, 2).map(word => word[0]).join('').toUpperCase();
  async function save(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError(''); setNotice('');
    try {
      if (workspace.mode === 'development') setReviewer(name.trim());
      else await updateDisplayName(name);
      setNotice('Your display name has been saved.');
    } catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  }
  async function reset() {
    if (!workspace.email) return;
    setBusy(true); setError(''); setNotice('');
    try { await sendPasswordReset(workspace.email); setNotice('A password reset link has been requested. Check your email.'); }
    catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  }
  const date = (value?: string) => value ? new Date(value).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) : 'Not available';
  return <SettingsFrame title="My profile" description="Your personal details, sign-in, and the organizations you belong to.">
    <section className="workspace-panel profile-overview"><div className="profile-cover">Your account. Your workspace.</div><div className="profile-identity"><span className="workspace-avatar">{initials}</span><div><h2>{display}</h2><p>{workspace.email || 'Local development identity'}</p></div></div><div className="profile-facts"><div><small>Member since</small><strong>{date(workspace.user?.created_at)}</strong></div><div><small>Last sign-in</small><strong>{date(workspace.user?.last_sign_in_at)}</strong></div><div><small>Organizations</small><strong>{workspace.loadingAccount ? 'Loading…' : workspace.account?.organizations.length ?? 'Unavailable'}</strong></div></div></section>
    {error && <div role="alert" className="workspace-alert">{error}</div>}{notice && <div role="status" className="workspace-alert success">{notice}</div>}
    <div className="settings-grid"><div>
      <section className="settings-section"><h2>Personal information</h2><p>Choose how your name appears in your account.</p><form className="settings-form" onSubmit={save}><div className="settings-field"><label htmlFor="profile-name">Display name</label><input id="profile-name" aria-describedby="profile-name-hint" required autoComplete="name" maxLength={80} value={name} onChange={e => setName(e.target.value)} placeholder="Your name" /><small id="profile-name-hint">{workspace.mode === 'development' ? 'This local reviewer name is stored in your browser.' : 'Review decisions remain attributed to your signed-in identity and email.'}</small></div><label>Sign-in email<input readOnly value={workspace.email || 'Not configured in local development'} autoComplete="email" /></label><button className="chrome-button primary" disabled={busy || !name.trim() || name.trim() === savedName}><Save size={14} />{busy ? 'Saving…' : 'Save changes'}</button></form></section>
      <section className="settings-section"><h2>Your organizations</h2><p>Your access follows the roles and sites assigned by each organization.</p>{workspace.error && <div role="alert" className="workspace-alert">{workspace.error}<button type="button" onClick={workspace.reload} className="chrome-button">Try again</button></div>}{workspace.loadingAccount && <p role="status">Loading memberships…</p>}{workspace.account?.organizations.map(org => <div className="member-row" key={org.id}><Building2 size={18} /><div className="member-description"><strong>{org.name}</strong><small>{org.roles.join(', ')} · {org.site_ids.join(', ') || 'Organization-wide'}</small></div>{org.id === workspace.organization?.id && <span className="status-label verified">Current</span>}</div>)}<Link className="text-action mt-5" href="/account/?manage=1">Manage organizations <ArrowUpRight size={13} /></Link></section>
    </div><div><section className="settings-section"><KeyRound size={21} className="mb-4 text-brand-teal" /><h2>Account security</h2><p>Your sign-in is managed by your identity provider.</p>{workspace.mode === 'supabase' && <button type="button" className="chrome-button" disabled={busy || !workspace.email} onClick={reset}>Request password reset</button>}{workspace.mode === 'development' && <Link href="/sign-in/" className="text-action">Configure sign-in <ArrowUpRight size={13} /></Link>}</section><aside className="settings-aside"><ShieldCheck size={22} /><h3>Personal and organization settings</h3><p>Your display name belongs to you. Memberships, roles and source access belong to the organization.</p></aside></div></div>
  </SettingsFrame>;
}
