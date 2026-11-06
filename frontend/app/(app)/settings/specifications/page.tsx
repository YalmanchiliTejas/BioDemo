'use client';

import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { SettingsFrame } from '@/components/shell/SettingsFrame';
import { Button, table } from '@/components/ui';
import { processRequest } from '@/lib/process-api';
import { useWorkspace } from '@/lib/workspace-context';

type Spec = { spec_id: string; site_id: string; parameter: string; unit: string | null; low: number | null; high: number | null;
  critical_low: number | null; critical_high: number | null; equipment_id: string | null; product_id: string | null;
  trend_rules: boolean; source: string; source_ref: string | null; version: number; approved_by: string; reason?: string };

const BLANK = { parameter: '', unit: '', low: '', high: '', critical_low: '', critical_high: '', equipment_id: '', source_ref: '', reason: '' };
const num = (v: string) => (v.trim() === '' ? null : Number(v));
const range = (lo: number | null, hi: number | null, unit: string | null) =>
  lo == null && hi == null ? '—' : `${lo ?? '−∞'} – ${hi ?? '∞'}${unit ? ` ${unit}` : ''}`;

/** Approved limits that live data is checked against. Without one, a parameter raises no signals. */
export default function SpecificationsPage() {
  const workspace = useWorkspace();
  const mySites = workspace.organization?.site_ids ?? [];
  const [specs, setSpecs] = useState<Spec[]>([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [site, setSite] = useState(mySites[0] ?? '');
  const [form, setForm] = useState(BLANK);
  const [trend, setTrend] = useState(true);

  const load = useCallback(async () => {
    try { setSpecs((await processRequest<{ specifications: Spec[] }>('/v1/specifications')).specifications); setError(''); }
    catch (e) { setError((e as Error).message); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  async function save(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError('');
    try {
      await processRequest('/v1/specifications', { site_id: site, parameter: form.parameter.trim(), unit: form.unit.trim() || null,
        low: num(form.low), high: num(form.high), critical_low: num(form.critical_low), critical_high: num(form.critical_high),
        equipment_id: form.equipment_id.trim() || null, source: form.source_ref.trim() ? 'document' : 'manual',
        source_ref: form.source_ref.trim() || null, trend_rules: trend, reason: form.reason.trim() });
      setForm(BLANK); await load();
    } catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }
  const field = (key: keyof typeof BLANK, label: string, opts: { type?: string; placeholder?: string; required?: boolean; wide?: boolean } = {}) =>
    <label className={`flex flex-col gap-1 text-[12px] font-medium text-text-secondary ${opts.wide ? 'sm:col-span-2' : ''}`}>{label}
      <input value={form[key]} required={opts.required} type={opts.type ?? 'text'} step="any" placeholder={opts.placeholder}
        onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))} className="h-9 rounded border border-border-hairline px-2 text-[13px] font-normal text-text-primary" /></label>;

  return <SettingsFrame title="Specifications" description="Approved limits that live process, lab and delivery data is checked against. Outside a limit raises a deviation signal for review; drifting toward one raises an early warning. Only people who can approve may set limits, and every change is a new version with a reason.">
    {error && <div role="alert" className="workspace-alert">{error}</div>}
    <section className="workspace-panel">
      <form onSubmit={save} className="grid gap-3 p-4 sm:grid-cols-4">
        <label className="flex flex-col gap-1 text-[12px] font-medium text-text-secondary">Site
          {mySites.length
            ? <select value={site} onChange={e => setSite(e.target.value)} className="h-9 rounded border border-border-hairline px-2 text-[13px] font-normal">{mySites.map(s => <option key={s}>{s}</option>)}</select>
            : <input required value={site} onChange={e => setSite(e.target.value)} placeholder="Site ID" className="h-9 rounded border border-border-hairline px-2 text-[13px] font-normal" />}</label>
        {field('parameter', 'Parameter', { required: true, placeholder: 'e.g. DO [%]' })}
        {field('unit', 'Unit', { placeholder: '%' })}
        {field('equipment_id', 'Equipment (optional)', { placeholder: 'all equipment' })}
        {field('low', 'Low', { type: 'number' })}
        {field('high', 'High', { type: 'number' })}
        {field('critical_low', 'Critical low', { type: 'number' })}
        {field('critical_high', 'Critical high', { type: 'number' })}
        {field('source_ref', 'Source document', { placeholder: 'e.g. Batch record BR-07 v3', wide: true })}
        {field('reason', 'Reason for this limit', { required: true, wide: true })}
        <label className="flex items-center gap-2 text-[12px] text-text-secondary sm:col-span-3"><input type="checkbox" checked={trend} onChange={e => setTrend(e.target.checked)} />
          Early warning when values drift toward a limit (EWMA / CUSUM / run rules)</label>
        <div className="flex justify-end"><Button type="submit" variant="primary" disabled={busy || !site || !form.parameter.trim() || !form.reason.trim()}>Save limit</Button></div>
      </form>
    </section>
    <section className="workspace-panel mt-4">
      <div className={table.wrap}><table className={table.root}>
        <thead><tr>{['Parameter', 'Site', 'Equipment', 'Limits', 'Critical', 'Early warning', 'Version', 'Approved by'].map(h => <th key={h} className={table.th}>{h}</th>)}</tr></thead>
        <tbody>{specs.length ? specs.map(s => <tr key={s.spec_id} className={table.tr}>
          <td className={table.td}>{s.parameter}{s.source_ref && <span className="block text-[11px] text-text-tertiary">{s.source_ref}</span>}</td>
          <td className={table.td}>{s.site_id}</td><td className={table.td}>{s.equipment_id ?? 'all'}</td>
          <td className={table.td}>{range(s.low, s.high, s.unit)}</td><td className={table.td}>{range(s.critical_low, s.critical_high, s.unit)}</td>
          <td className={table.td}>{s.trend_rules ? 'on' : 'off'}</td><td className={table.td}>v{s.version}</td><td className={table.td}>{s.approved_by}</td>
        </tr>) : <tr><td className={table.td} colSpan={8}>No limits yet. Until a parameter has one, its data is stored but never raises a signal.</td></tr>}</tbody>
      </table></div>
    </section>
  </SettingsFrame>;
}
