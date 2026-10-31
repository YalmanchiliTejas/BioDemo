'use client';

import { useEffect, useState, type FormEvent } from 'react';
import Link from 'next/link';
import { ArrowUpRight, Building2, ChevronDown, Plus, ShieldCheck, Users } from 'lucide-react';
import { SettingsFrame } from '@/components/shell/SettingsFrame';
import { connectorRequest } from '@/lib/connectors-api';
import { type Member } from '@/lib/organizations-api';
import { useWorkspace } from '@/lib/workspace-context';

const roles = ['admin', 'operator', 'supervisor', 'qa', 'qa_reviewer', 'msat', 'engineering', 'maintenance', 'supply_chain', 'manufacturing_systems', 'quality_systems'];
const roleLabel = (role: string) => role.replace(/_/g, ' ').replace(/\b\w/g, value => value.toUpperCase());
export default function OrganizationPage() {
  const { organization, user, error: accountError, loadingAccount, reload } = useWorkspace();
  const [members, setMembers] = useState<Member[] | null>(null);
  const [email, setEmail] = useState('');
  const [role, setRole] = useState('operator');
  const [site, setSite] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [pending, setPending] = useState<Member | null>(null);
  const [attempt, setAttempt] = useState(0);
  const admin = !!organization?.roles.includes('admin') && !organization.site_ids.length;
  useEffect(() => {
    let active = true; setMembers(null); setError('');
    if (admin) connectorRequest<{ items: Member[] }>('/organization/members').then(response => { if (active) setMembers(response.items); }).catch(err => { if (active) setError(err.message); });
    return () => { active = false; };
  }, [organization?.id, admin, attempt]);
  async function grant(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError(''); setNotice('');
    try {
      await connectorRequest('/organization/members', { email: email.trim(), role, site_id: site.trim() || null });
      setNotice('Access granted. The person can select this organization after signing in.'); setEmail(''); setAttempt(i => i + 1);
    } catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  }
  async function revoke(member: Member) {
    setBusy(true); setError(''); setNotice('');
    try {
      await connectorRequest('/organization/members', { actor_id: member.actor_id, role: member.role, site_id: member.site_id, operation: 'revoke' });
      setNotice('Role revoked. Future requests use the updated permissions.'); setPending(null); setAttempt(i => i + 1);
    } catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  }
  return <SettingsFrame title="Organization & team" description="Your shared workspace, who can access it, and the scope of their work.">
    {(error || accountError) && <div role="alert" className="workspace-alert"><p>{error || accountError}</p><button type="button" className="chrome-button" onClick={() => accountError ? reload() : setAttempt(i => i + 1)}>Try again</button></div>}{notice && <div role="status" className="workspace-alert success">{notice}</div>}
    {loadingAccount && <p role="status" className="mb-5 text-xs text-text-secondary">Loading your organization…</p>}
    <div className="settings-grid"><div><section className="settings-section"><div className="mb-5 flex items-center gap-3"><span className="workspace-avatar"><Building2 size={18} /></span><div><h2>{organization?.name || 'Organization details'}</h2><span className="text-xs text-text-tertiary">Your current workspace</span></div></div><dl><div className="settings-row"><dt>Organization name</dt><dd>{organization?.name || (loadingAccount ? 'Loading…' : 'Unavailable')}</dd></div><div className="settings-row"><dt>Organization ID</dt><dd><code>{organization?.id || 'Unavailable'}</code></dd></div><div className="settings-row"><dt>Your roles</dt><dd>{organization?.roles.map(roleLabel).join(', ') || 'Unavailable'}</dd></div><div className="settings-row"><dt>Your site scope</dt><dd>{organization ? organization.site_ids.join(', ') || 'Organization-wide' : 'Unavailable'}</dd></div></dl><Link className="text-action mt-5" href="/account/?manage=1">Switch or manage organizations <ArrowUpRight size={13} /></Link></section>
      <section className="settings-section" id="members"><div className="flex items-center gap-2"><Users size={17} className="text-brand-teal" /><h2 className="!mb-0">Team access</h2></div><p className="!mt-3">Roles and sites determine what each person can view and do.</p>
        {organization && !admin && <p>Only an organization administrator can manage memberships and roles.</p>}
        {admin && <><details className="mb-6 rounded-lg border border-border-hairline p-4"><summary><span className="flex items-center gap-2"><Plus size={15} />Grant team access</span><ChevronDown size={15} /></summary><p>The person must register first. Grant only the roles and sites they need.</p><form className="settings-form" onSubmit={grant}><label>Account email<input required type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="colleague@company.com" /></label><div className="settings-two"><label>Role<select value={role} onChange={e => { setRole(e.target.value); if (e.target.value === 'admin') setSite(''); }}>{roles.map(value => <option value={value} key={value}>{roleLabel(value)}</option>)}</select></label><label>Site scope<input disabled={role === 'admin'} maxLength={80} value={site} onChange={e => setSite(e.target.value)} placeholder="Organization-wide" /></label></div><small>Leave site blank for organization-wide access. Administrative access does not grant quality approval or production execution authority.</small><button disabled={busy} className="chrome-button primary">{busy ? 'Saving…' : 'Grant access'}</button></form></details>
          <h3 className="text-xs font-medium">Current role assignments {members && <span className="ml-2 text-text-tertiary">{members.length}</span>}</h3>
          {!members && !error && <p role="status" className="mt-4 text-xs text-text-secondary">Loading role assignments…</p>}
          {members?.length === 0 && <p className="mt-4 text-xs text-text-secondary">No role assignments returned.</p>}
          <div className="member-list">{members?.map(member => { const label = member.email || (member.actor_id === user?.id ? user.email : member.actor_id) || member.actor_id; const isPending = pending?.actor_id === member.actor_id && pending?.role === member.role && pending?.site_id === member.site_id; return <div key={`${member.actor_id}:${member.role}:${member.site_id}`}><div className="member-row"><span className="workspace-avatar">{label.slice(0, 2).toUpperCase()}</span><div className="member-description"><strong>{label}</strong><small>{roleLabel(member.role)} · {member.site_id || 'Organization-wide'}</small></div><button type="button" disabled={busy} className="member-revoke" onClick={() => setPending(member)}>Revoke role</button></div>{isPending && <div className="member-confirm">Revoke {roleLabel(member.role)} access for {label} at {member.site_id || 'all sites'}?<div><button type="button" className="chrome-button" disabled={busy} onClick={() => setPending(null)}>Cancel</button><button type="button" className="chrome-button" disabled={busy} onClick={() => revoke(member)}>Confirm revocation</button></div></div>}</div>; })}</div>
        </>}
      </section>
    </div><aside className="settings-aside"><ShieldCheck size={24} /><h3>Access with clear boundaries</h3><p>Source data and actions remain scoped to the permissions assigned to each account.</p><h3>Bringing your team on board?</h3><p>Ask colleagues to create an account first, then grant them the relevant role and site access.</p></aside></div>
  </SettingsFrame>;
}
