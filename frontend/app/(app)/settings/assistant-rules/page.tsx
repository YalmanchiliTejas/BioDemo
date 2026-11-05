'use client';

import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { SettingsFrame } from '@/components/shell/SettingsFrame';
import { Button, Pill, table, type Tone } from '@/components/ui';
import { processRequest } from '@/lib/process-api';
import { useWorkspace } from '@/lib/workspace-context';

type Rule = { rule_id: string; scope: 'user' | 'site' | 'org'; site_id: string | null; owner_id: string | null; text: string;
  status: 'proposed' | 'active' | 'retired'; proposed_by: string; proposed_by_kind: string; created_at: string; revision: number };

const TONE: Record<Rule['status'], Tone> = { proposed: 'warning', active: 'success', retired: 'muted' };
const SCOPE = { user: 'Just me', site: 'A site', org: 'Whole organization' } as const;
// Mirrors roles.py; the server enforces authority regardless of what is shown here.
const APPROVERS = ['admin', 'qa', 'qa_reviewer', 'supervisor', 'msat', 'engineering', 'quality_systems'];

export default function AssistantRulesPage() {
  const workspace = useWorkspace();
  const me = workspace.account?.actor_id ?? workspace.user?.id ?? '';
  const roles = workspace.organization?.roles ?? [];
  const siteLimited = (workspace.organization?.site_ids ?? []).length > 0;
  const [rules, setRules] = useState<Rule[]>([]);
  const [error, setError] = useState('');
  const [text, setText] = useState('');
  const [scope, setScope] = useState<Rule['scope']>('user');
  const [site, setSite] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try { setRules((await processRequest<{ items: Rule[] }>('/v1/assistant-rules')).items); setError(''); }
    catch (e) { setError((e as Error).message); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const mayDecide = (r: Rule) => r.scope === 'user' ? r.owner_id === me
    : roles.some(role => APPROVERS.includes(role)) && !(r.scope === 'org' && siteLimited);

  async function act(fn: () => Promise<unknown>) {
    setBusy(true); setError('');
    try { await fn(); await load(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  function propose(e: FormEvent) {
    e.preventDefault();
    void act(async () => { await processRequest('/v1/assistant-rules', { scope, text, site_id: scope === 'site' ? site : null }); setText(''); });
  }
  function decide(rule: Rule, verb: 'activate' | 'retire') {
    const reason = verb === 'activate' ? 'Reviewed and adopted as a standing rule' : 'No longer applies';
    void act(() => processRequest(`/v1/assistant-rules/${rule.rule_id}/${verb}`, { reason }));
  }

  return <SettingsFrame title="Assistant rules" description="Standing instructions the assistant follows in every conversation. Proposed rules do nothing until someone with authority activates them.">
    {error && <div role="alert" className="workspace-alert">{error}</div>}
    <section className="workspace-panel">
      <form onSubmit={propose} className="flex flex-col gap-3 p-4">
        <label className="text-[13px] font-medium">New rule
          <textarea required maxLength={2000} rows={2} value={text} onChange={e => setText(e.target.value)}
            placeholder="e.g. Always flag dissolved oxygen below 30% for review" className="mt-1 w-full rounded border border-border-hairline p-2 text-[13px]" /></label>
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-[13px] font-medium">Applies to
            <select value={scope} onChange={e => setScope(e.target.value as Rule['scope'])} className="ml-2 h-9 rounded border border-border-hairline px-2 text-[13px]">
              {(Object.keys(SCOPE) as Rule['scope'][]).map(s => <option key={s} value={s}>{SCOPE[s]}</option>)}
            </select></label>
          {scope === 'site' && <label className="text-[13px] font-medium">Site
            <input required value={site} onChange={e => setSite(e.target.value)} className="ml-2 h-9 rounded border border-border-hairline px-2 text-[13px]" /></label>}
          <Button type="submit" variant="primary" disabled={busy || !text.trim()}>Propose rule</Button>
        </div>
      </form>
    </section>
    <section className="workspace-panel">
      <div className={table.wrap}><table className={table.root}>
        <thead><tr>{['Rule', 'Applies to', 'Proposed by', 'Status', ''].map(h => <th key={h} className={table.th}>{h}</th>)}</tr></thead>
        <tbody>{rules.map(r => <tr key={r.rule_id} className={table.tr}>
          <td className={table.td}>{r.text}</td>
          <td className={table.td}>{r.scope === 'site' ? `Site ${r.site_id}` : SCOPE[r.scope]}</td>
          <td className={table.td}>{r.proposed_by}{r.proposed_by_kind !== 'person' && <span className="text-text-tertiary"> (assistant)</span>}</td>
          <td className={table.td}><Pill tone={TONE[r.status]}>{r.status}</Pill></td>
          <td className={table.td}>{mayDecide(r) && <span className="flex gap-2">
            {r.status === 'proposed' && <Button size="sm" disabled={busy} onClick={() => decide(r, 'activate')}>Activate</Button>}
            {r.status !== 'retired' && <Button size="sm" variant="ghost" disabled={busy} onClick={() => decide(r, 'retire')}>Retire</Button>}
          </span>}</td>
        </tr>)}
        {!rules.length && <tr><td className={table.td} colSpan={5}>No rules yet.</td></tr>}</tbody>
      </table></div>
    </section>
  </SettingsFrame>;
}
