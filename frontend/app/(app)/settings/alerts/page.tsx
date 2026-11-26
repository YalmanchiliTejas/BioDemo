'use client';

import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { SettingsFrame } from '@/components/shell/SettingsFrame';
import { Button, Pill, table } from '@/components/ui';
import { listChannels, listRoutes, saveChannel, saveRoute, SEVERITY_LABEL, testChannel, type AlertChannel, type AlertRoute, type ChannelKind, type Severity } from '@/lib/alerts-api';
import { useWorkspace } from '@/lib/workspace-context';

const ROLES = ['qa', 'qa_reviewer', 'supervisor', 'msat', 'engineering', 'quality_systems', 'maintenance', 'supply_chain', 'operator'];
const KIND_LABEL: Record<ChannelKind, string> = { email: 'Email (SMTP)', slack: 'Slack webhook', teams: 'Microsoft Teams webhook' };
const input = 'h-9 rounded border border-border-hairline bg-surface px-2 text-[13px]';

export default function AlertSettingsPage() {
  const workspace = useWorkspace();
  const admin = (workspace.organization?.roles ?? []).includes('admin') && !(workspace.organization?.site_ids ?? []).length;
  const [channels, setChannels] = useState<AlertChannel[]>([]);
  const [routes, setRoutes] = useState<AlertRoute[]>([]);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [kind, setKind] = useState<ChannelKind>('slack');
  const [form, setForm] = useState({ name: '', webhook_url: '', host: '', port: '587', from_addr: '', username: '', password: '', starttls: true });
  const [route, setRoute] = useState({ site_id: '', min_severity: 'action' as Severity, roles: ['qa', 'supervisor'], channels: [] as string[] });

  const load = useCallback(async () => {
    try { const [c, r] = await Promise.all([listChannels(), listRoutes()]); setChannels(c.channels); setRoutes(r.routes); setError(''); }
    catch (e) { setError((e as Error).message); }
  }, []);
  useEffect(() => { if (admin) void load(); }, [admin, load]);

  async function act(fn: () => Promise<unknown>, done: string) {
    setBusy(true); setError(''); setNotice('');
    try { await fn(); setNotice(done); await load(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  function addChannel(e: FormEvent) {
    e.preventDefault();
    const name = form.name.trim() || KIND_LABEL[kind];
    const body: Parameters<typeof saveChannel>[0] = kind === 'email'
      ? { kind, name, config: { host: form.host, port: Number(form.port), from_addr: form.from_addr, starttls: form.starttls }, secrets: { username: form.username, password: form.password } }
      : { kind, name, secrets: { webhook_url: form.webhook_url } };
    void act(async () => { await saveChannel(body); setForm(f => ({ ...f, name: '', webhook_url: '', password: '' })); }, `${name} saved`);
  }
  function addRoute(e: FormEvent) {
    e.preventDefault();
    void act(() => saveRoute({ site_id: route.site_id.trim() || null, min_severity: route.min_severity, roles: route.roles, channels: route.channels, enabled: true }), 'Route saved');
  }
  const toggle = (list: string[], value: string) => list.includes(value) ? list.filter(v => v !== value) : [...list, value];
  const channelName = (id: string) => id === 'in_app' ? 'In-app' : channels.find(c => c.channel_id === id)?.name ?? id;

  if (!admin) return <SettingsFrame title="Alerts" description="Who hears about deviation signals, and where.">
    <div className="workspace-alert">Only an organization-wide administrator can configure alerts. Alerts routed to you appear under the bell at the top of the page.</div>
  </SettingsFrame>;

  return <SettingsFrame title="Alerts" description="Who hears about deviation signals, and where. A signal is something the data shows for review; opening a deviation stays a person's decision. Alert messages carry the rule, subject, site and a link, never document text.">
    {error && <div role="alert" className="workspace-alert">{error}</div>}
    {notice && <div role="status" className="mb-3 rounded border border-emerald-200 bg-status-success-bg px-3 py-2 text-[13px] text-emerald-700">{notice}</div>}

    <section className="workspace-panel mb-6">
      <div className="border-b border-border-hairline px-4 py-3"><h2 className="text-[14px] font-semibold">Routes</h2>
        <p className="text-[12.5px] text-text-secondary">{routes.some(r => r.default) ? 'No routes yet: signals at “Out of specification” or above go in-app to each site’s QA and supervisors.' : 'Every matching route applies; each person is alerted once per signal and again only if it escalates.'}</p></div>
      <div className={table.wrap}><table className={table.root}>
        <thead><tr>{['Site', 'From severity', 'Roles', 'Channels', ''].map(h => <th key={h} className={table.th}>{h}</th>)}</tr></thead>
        <tbody>{routes.map(r => <tr key={r.route_id} className={table.tr}>
          <td className={table.td}>{r.site_id ?? 'All sites'}</td><td className={table.td}>{SEVERITY_LABEL[r.min_severity]}</td>
          <td className={table.td}>{r.roles.join(', ')}</td><td className={table.td}>{r.channels.map(channelName).join(', ')}</td>
          <td className={table.td}>{r.default ? <Pill tone="muted">default</Pill> : !r.enabled && <Pill tone="muted">off</Pill>}</td></tr>)}</tbody>
      </table></div>
      <form onSubmit={addRoute} className="flex flex-wrap items-end gap-3 border-t border-border-hairline p-4 text-[13px]">
        <label className="flex flex-col gap-1">Site<input value={route.site_id} onChange={e => setRoute({ ...route, site_id: e.target.value })} placeholder="All sites" className={`${input} w-28`} /></label>
        <label className="flex flex-col gap-1">From severity<select value={route.min_severity} onChange={e => setRoute({ ...route, min_severity: e.target.value as Severity })} className={input}>
          {(Object.keys(SEVERITY_LABEL) as Severity[]).map(s => <option key={s} value={s}>{SEVERITY_LABEL[s]}</option>)}</select></label>
        <fieldset className="flex max-w-md flex-wrap gap-x-3 gap-y-1"><legend className="mb-1">Roles</legend>{ROLES.map(r => <label key={r} className="flex items-center gap-1"><input type="checkbox" checked={route.roles.includes(r)} onChange={() => setRoute({ ...route, roles: toggle(route.roles, r) })} />{r}</label>)}</fieldset>
        <fieldset className="flex flex-wrap gap-x-3 gap-y-1"><legend className="mb-1">Channels</legend><label className="flex items-center gap-1 text-text-tertiary"><input type="checkbox" checked disabled />In-app</label>
          {channels.map(c => <label key={c.channel_id} className="flex items-center gap-1"><input type="checkbox" checked={route.channels.includes(c.channel_id)} onChange={() => setRoute({ ...route, channels: toggle(route.channels, c.channel_id) })} />{c.name}</label>)}</fieldset>
        <Button type="submit" variant="primary" size="sm" disabled={busy || !route.roles.length}>Add route</Button>
      </form>
    </section>

    <section className="workspace-panel">
      <div className="border-b border-border-hairline px-4 py-3"><h2 className="text-[14px] font-semibold">Channels</h2>
        <p className="text-[12.5px] text-text-secondary">In-app alerts are always on. Secrets are stored encrypted and never shown again.</p></div>
      {!!channels.length && <div className={table.wrap}><table className={table.root}>
        <thead><tr>{['Name', 'Type', 'Stored secrets', ''].map(h => <th key={h} className={table.th}>{h}</th>)}</tr></thead>
        <tbody>{channels.map(c => <tr key={c.channel_id} className={table.tr}><td className={table.td}>{c.name}</td><td className={table.td}>{KIND_LABEL[c.kind]}</td>
          <td className={table.td}>{c.secret_fields.join(', ') || '—'}</td>
          <td className={table.td}><Button size="sm" disabled={busy} onClick={() => act(() => testChannel(c.channel_id), `Test sent to ${c.name}`)}>Send test</Button></td></tr>)}</tbody>
      </table></div>}
      <form onSubmit={addChannel} className="flex flex-wrap items-end gap-3 border-t border-border-hairline p-4 text-[13px]">
        <label className="flex flex-col gap-1">Type<select value={kind} onChange={e => setKind(e.target.value as ChannelKind)} className={input}>
          {(Object.keys(KIND_LABEL) as ChannelKind[]).map(k => <option key={k} value={k}>{KIND_LABEL[k]}</option>)}</select></label>
        <label className="flex flex-col gap-1">Name<input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder={kind === 'email' ? 'QA mail' : '#qa-alerts'} className={`${input} w-40`} /></label>
        {kind === 'email' ? <>
          <label className="flex flex-col gap-1">SMTP host<input required value={form.host} onChange={e => setForm({ ...form, host: e.target.value })} className={`${input} w-44`} /></label>
          <label className="flex flex-col gap-1">Port<input required value={form.port} onChange={e => setForm({ ...form, port: e.target.value })} className={`${input} w-20`} /></label>
          <label className="flex flex-col gap-1">From<input required type="email" value={form.from_addr} onChange={e => setForm({ ...form, from_addr: e.target.value })} className={`${input} w-52`} /></label>
          <label className="flex flex-col gap-1">Username<input value={form.username} onChange={e => setForm({ ...form, username: e.target.value })} autoComplete="off" className={`${input} w-36`} /></label>
          <label className="flex flex-col gap-1">Password<input type="password" value={form.password} onChange={e => setForm({ ...form, password: e.target.value })} autoComplete="new-password" className={`${input} w-36`} /></label>
          <label className="flex items-center gap-1 pb-2"><input type="checkbox" checked={form.starttls} onChange={e => setForm({ ...form, starttls: e.target.checked })} />STARTTLS</label>
        </> : <label className="flex flex-col gap-1">Webhook URL<input required type="url" value={form.webhook_url} onChange={e => setForm({ ...form, webhook_url: e.target.value })}
          placeholder={kind === 'slack' ? 'https://hooks.slack.com/services/…' : 'https://….webhook.office.com/…'} autoComplete="off" className={`${input} w-96`} /></label>}
        <Button type="submit" variant="primary" size="sm" disabled={busy}>Save channel</Button>
      </form>
    </section>
  </SettingsFrame>;
}
