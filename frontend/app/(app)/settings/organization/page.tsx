'use client';
import { useEffect, useState, type FormEvent } from 'react';
import Link from 'next/link';
import { connectorRequest } from '@/lib/connectors-api';
import { getAccount, type Organization, type Member } from '@/lib/organizations-api';
import { selectedOrganization, useSession } from '@/lib/auth';
const roles = ['admin','operator','supervisor','qa','qa_reviewer','msat','engineering','maintenance','supply_chain','manufacturing_systems','quality_systems'];
export default function OrganizationPage() {
  const { user } = useSession();
  const [organization, setOrganization] = useState<Organization | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [email, setEmail] = useState('');
  const [role, setRole] = useState('operator');
  const [site, setSite] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const admin = organization?.roles.includes('admin') && !organization.site_ids.length;
  async function loadMembers() { const response = await connectorRequest<{items: Member[]}>('/organization/members'); setMembers(response.items); }
  useEffect(()=>{
    let active=true;
    getAccount().then(async a=>{
      if (!active) return;
      const org = a.organizations.find(o=>o.id===selectedOrganization(a.actor_id)) ?? a.organizations[0];
      setOrganization(org ?? null);
      if(org?.roles.includes('admin') && !org.site_ids.length) await loadMembers();
    }).catch(err=>{if(active)setError(err.message);});
    return ()=>{active=false;};
  },[]);
  async function grant(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError(''); setNotice('');
    try { await connectorRequest('/organization/members',{email:email.trim(),role,site_id:site.trim()||null}); await loadMembers(); setNotice('Access granted. The person can select this organization after signing in.'); setEmail(''); }
    catch(err){setError((err as Error).message);}finally{setBusy(false);}
  }
  async function revoke(m: Member) {
    setBusy(true); setError(''); setNotice('');
    try { await connectorRequest('/organization/members',{actor_id:m.actor_id,role:m.role,site_id:m.site_id,operation:'revoke'}); await loadMembers(); setNotice('Role revoked. Future requests use the updated permissions.'); }
    catch(err){setError((err as Error).message);}finally{setBusy(false);}
  }
  return <div className="mx-auto max-w-4xl p-5 sm:p-8"><h1 className="text-2xl font-medium">Organization & access</h1><p className="mt-3 text-lg">{organization?.name}</p><p className="mt-2 text-sm text-text-secondary">Your roles: {organization?.roles.join(', ') || 'Loading…'} · Scope: {organization?.site_ids.join(', ') || 'Organization-wide'}</p>
    <Link href="/account/?manage=1" className="mt-4 inline-block text-sm text-brand-teal underline">Switch organization or create your organization</Link>
    {error&&<p role="alert" className="setup-message error mt-5">{error}</p>}{notice&&<p role="status" className="setup-message mt-5">{notice}</p>}
    {organization && !admin && <p className="mt-8 text-sm">Only an organization administrator can manage memberships and roles.</p>}
    {admin&&<><form onSubmit={grant} className="auth-fields mt-8 rounded-xl border border-border-hairline bg-white p-6"><h2 className="text-lg font-medium">Grant team access</h2><p className="text-sm leading-6 text-text-secondary">The person must register first. Grant access only to the organization and sites they need. Administrative access does not grant quality approval or production execution authority.</p>
      <label>Account email<input required type="email" value={email} onChange={e=>setEmail(e.target.value)}/></label>
      <label>Role<select value={role} onChange={e=>{setRole(e.target.value);if(e.target.value==='admin')setSite('');}} className="rounded-lg border border-border-hairline p-3">{roles.map(r=><option key={r}>{r}</option>)}</select></label>
      <label>Site scope<input disabled={role==='admin'} maxLength={80} value={site} onChange={e=>setSite(e.target.value)} placeholder="Leave blank for organization-wide access"/></label>
      <button disabled={busy} className="setup-primary">{busy?'Saving…':'Grant access'}</button>
    </form><h2 className="mt-10 text-lg font-medium">Current role assignments</h2><div className="mt-4 space-y-3">{members.map(m=><div key={`${m.actor_id}:${m.role}:${m.site_id}`} className="flex flex-wrap items-center justify-between gap-4 rounded-lg border border-border-hairline bg-white p-4"><div className="min-w-0"><p className="break-all text-sm" title={m.actor_id}>{m.email || (m.actor_id === user?.id ? user.email : m.actor_id)}</p><p className="mt-2 text-sm">{m.role} · {m.site_id || 'Organization-wide'}</p></div><button disabled={busy} onClick={()=>void revoke(m)} className="text-sm text-red-700 underline disabled:opacity-40">Revoke role</button></div>)}</div></>}
  </div>;
}
