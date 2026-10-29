'use client';

import { useState } from 'react';
import { postJson, RULES, ruleTitle, type Issue, type Measurement, type Run } from '@/lib/cmo-api';
import { plural, ReasonButton } from './shared';

// Settled by confirming column meanings, so hidden while that step is pending.
const MAPPING_ISSUES = new Set(['LAYOUT_CHANGED', 'UNMAPPED_FIELD', 'UNRECOGNIZED_TABLE', 'MAPPING_UNCERTAIN']);
const NEEDS_REASON = new Set(['EXPECTED_DOCUMENT_MISSING', 'EXPECTED_PARAMETER_MISSING', 'BATCH_DOCUMENT_MISSING', 'MISSING_PAGE', 'MISSING_FIELD',
  'PARSE_ERROR', 'DUPLICATE_CONFLICT', 'DUPLICATE_RECORD', 'BATCH_MISMATCH', 'TIME_ORDER']);
const button = 'h-7 rounded-control border border-border-strong px-2.5 text-xs font-medium text-text-secondary hover:bg-surface-secondary';
const primary = 'h-7 rounded-control bg-brand-teal px-2.5 text-xs font-medium text-white hover:bg-brand-teal-dark';

function describe(issue: Issue & { members?: string[] }) {
  const where = [issue.path, issue.sheet, issue.header && `“${issue.header}”`].filter(Boolean).join(' · ');
  if (issue.rule_code === 'MISSING_FIELD' && issue.row != null && issue.parameter) {
    const n = issue.members?.length ?? 1;
    const name = issue.parameter.replace(/_/g, ' ');
    return [`${name[0].toUpperCase()}${name.slice(1)} not reported in ${plural(n, 'row')}`, `${issue.path} · the cells are blank in the delivered file`];
  }
  switch (issue.rule_code) {
    case 'UNACCOUNTED_CONTENT': return [`${plural(issue.count ?? issue.lines?.length ?? 1, 'line')} in ${issue.path} not turned into data`, 'Read them so nothing is missed.'];
    case 'BATCH_DOCUMENT_MISSING': return [`Batch ${issue.batch} has no ${issue.doc_type?.replace(/_/g, ' ')}`, 'Other batches in this delivery have one.'];
    case 'EXPECTED_DOCUMENT_MISSING': return [`No ${issue.doc_type?.replace(/_/g, ' ')} in this delivery`, 'The last verified delivery from this CMO had one.'];
    case 'EXPECTED_PARAMETER_MISSING': return [`${issue.parameter?.replace(/_/g, ' ')} is missing`, 'It was reported in the last verified delivery.'];
    case 'MISSING_PAGE': return [`${issue.path} is missing pages`, `${issue.actual_pages} of ${issue.expected_pages} pages delivered.`];
    case 'DUPLICATE_CONFLICT': return [`Conflicting ${issue.parameter?.replace(/_/g, ' ')} for batch ${issue.batch} at ${issue.time} h`, where];
    default: return [ruleTitle(issue.rule_code) + (where ? ` · ${where}` : ''), issue.message ?? RULES[issue.rule_code]?.help ?? ''];
  }
}

/** Items the list shows; mapping-related ones wait until formats are confirmed. */
export function visibleToCheck(run: Run, mappingPending: boolean) {
  const open = (run.issues ?? []).filter(i => i.status === 'open' && !(mappingPending && MAPPING_ISSUES.has(i.rule_code)));
  // Blank cells for the same parameter in one file are one decision.
  const issues: Array<Issue & { members: string[] }> = []; const blanks = new Map<string, Issue & { members: string[] }>();
  for (const issue of open) {
    if (issue.rule_code === 'MISSING_FIELD' && issue.row != null && issue.parameter) {
      const key = `${issue.path}|${issue.parameter}`; const existing = blanks.get(key);
      if (existing) { existing.members.push(issue.id); continue; }
      const grouped = { ...issue, members: [issue.id] }; blanks.set(key, grouped); issues.push(grouped);
    } else issues.push({ ...issue, members: [issue.id] });
  }
  const groups = (run.review_groups ?? []).filter(g => !(mappingPending && g.rule_codes.every(c => ['DRAFT_MAPPING', 'LAYOUT_CHANGED'].includes(c))));
  return { issues, groups };
}

type Props = { run: Run; reviewer: string; mappingPending: boolean; onChanged: () => void; onInspect: (m: Measurement) => void };

/** Everything that still needs a person, one line each, with direct actions. */
export function ToCheck({ run, reviewer, mappingPending, onChanged, onInspect }: Props) {
  const [reading, setReading] = useState<string | null>(null);
  const [error, setError] = useState('');
  const byId = new Map((run.measurements ?? []).map(m => [m.id, m]));
  const { issues, groups } = visibleToCheck(run, mappingPending);
  const hidden = (run.review_groups?.length ?? 0) - groups.length;
  if (!issues.length && !groups.length) return null;

  async function act(call: () => Promise<unknown>) {
    setError('');
    try { await call(); onChanged(); } catch (e) { setError((e as Error).message); }
  }
  const resolve = (issue: Issue & { members: string[] }, extra: { reason?: string; ignore_in_future?: boolean } = {}) =>
    act(() => postJson(`/runs/${run.id}/issues`, { issue_id: issue.id, also: issue.members.slice(1), actor: reviewer, ...extra }));
  const decideGroup = (ids: string[], decision: 'accept' | 'reject', reason?: string) =>
    act(() => postJson(`/runs/${run.id}/reviews/bulk`, { items: ids.map(id => ({ measurement_id: id, binding: byId.get(id)!.review_binding })), decision, actor: reviewer, reason }));

  return (
    <section className="rounded-2xl border border-border-hairline bg-white" data-testid="to-check">
      <div className="border-b border-border-hairline px-6 py-5">
        <h2 className="font-display text-[20px] font-light text-ink">To check <span className="text-text-tertiary">· {issues.length + groups.length}</span></h2>
        {hidden > 0 && <p className="mt-0.5 text-xs text-text-tertiary">{plural(hidden, 'more group')} of values will be checked automatically once the file formats above are confirmed.</p>}
      </div>
      {!reviewer && <p className="px-6 py-2 text-xs text-status-warning">Enter your name at the top right; it is recorded on each decision.</p>}
      {error && <p className="px-6 py-2 text-xs text-status-critical">{error}</p>}
      <ul className="divide-y divide-border-hairline">
        {issues.map(issue => {
          const [title, detail] = describe(issue);
          return (
            <li key={issue.id} className="px-6 py-3.5">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="min-w-0"><p className="text-[14px] text-ink">{title}</p>{detail && <p className="truncate text-xs text-text-tertiary">{detail}</p>}</div>
                <div className="flex flex-wrap items-center gap-1.5">
                  {issue.lines?.length ? <button className={button} onClick={() => setReading(reading === issue.id ? null : issue.id)}>{reading === issue.id ? 'Hide' : 'Read'}</button> : null}
                  {NEEDS_REASON.has(issue.rule_code)
                    ? <ReasonButton label="Dismiss" placeholder="Why is this OK?" onConfirm={reason => resolve(issue, { reason })} />
                    : <>
                        {issue.rule_code === 'UNACCOUNTED_CONTENT' && issue.lines?.length ? <button className={button} disabled={!reviewer} onClick={() => resolve(issue, { ignore_in_future: true })} title={`Skip these lines in future deliveries from ${run.cmo}`}>Ignore from now on</button> : null}
                        <button className={primary} disabled={!reviewer} onClick={() => resolve(issue)}>Noted</button>
                      </>}
                </div>
              </div>
              {reading === issue.id && issue.lines && (
                <ol className="mt-2 max-h-48 overflow-y-auto rounded-control bg-surface-secondary/60 p-2 font-mono text-[11.5px]">
                  {issue.lines.map(line => <li key={line.element_id}><span className="mr-2 text-text-muted">p{line.page ?? '?'}</span>{line.text}</li>)}
                </ol>
              )}
            </li>
          );
        })}
        {groups.map(group => {
          const first = byId.get(group.measurement_ids[0]);
          const reasons = group.rule_codes.filter(c => c !== 'DRAFT_MAPPING').map(ruleTitle).join(' · ') || 'Format not confirmed yet';
          return (
            <li key={group.id} className="flex flex-wrap items-center justify-between gap-2 px-6 py-3.5">
              <div className="min-w-0">
                <p className="text-[13px]">{plural(group.count, `${group.parameter.replace(/_/g, ' ')} value`)} <span className="text-text-tertiary">from “{group.column}”</span></p>
                <p className="truncate text-xs text-text-tertiary">{reasons} · {group.path}</p>
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                {first && <button className={button} onClick={() => onInspect(first)}>View source</button>}
                <button className={primary} disabled={!reviewer || group.invalid_values === group.count} onClick={() => decideGroup(group.measurement_ids, 'accept')}>Accept</button>
                <ReasonButton label="Reject" danger placeholder="Why reject these values?" onConfirm={reason => decideGroup(group.measurement_ids, 'reject', reason)} />
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
