'use client';

import { useState } from 'react';
import { parameterLabel, postJson, RULES, ruleTitle, type Issue, type Measurement, type Run } from '@/lib/cmo-api';
import { plural, ReasonButton } from './shared';
import { canShow, FilePreview, SourceContext, sourceIdFor, type Location } from './SourceContext';

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
    const name = parameterLabel(issue.parameter);
    return [`${name[0].toUpperCase()}${name.slice(1)} not reported in ${plural(n, 'row')}`, `${issue.path} · the cells are blank in the delivered file`];
  }
  switch (issue.rule_code) {
    case 'UNACCOUNTED_CONTENT': return [`${plural(issue.count ?? issue.lines?.length ?? 1, 'line')} in ${issue.path} not turned into data`, 'Read them so nothing is missed.'];
    case 'BATCH_DOCUMENT_MISSING': return [`Batch ${issue.batch} has no ${issue.doc_type?.replace(/_/g, ' ')}`, 'Other batches in this delivery have one.'];
    case 'EXPECTED_DOCUMENT_MISSING': return [`No ${issue.doc_type?.replace(/_/g, ' ')} in this delivery`, 'The last verified delivery from this CDMO had one.'];
    case 'EXPECTED_PARAMETER_MISSING': return [`${parameterLabel(issue.parameter ?? '')} is missing`, 'It was reported in the last verified delivery.'];
    case 'MISSING_PAGE': return [`${issue.path} is missing pages`, `${issue.actual_pages} of ${issue.expected_pages} pages delivered.`];
    case 'DUPLICATE_CONFLICT': return [`Conflicting ${parameterLabel(issue.parameter ?? '')} for batch ${issue.batch} at ${issue.time} h`, where];
    default: return [ruleTitle(issue.rule_code) + (where ? ` · ${where}` : ''), issue.message ?? RULES[issue.rule_code]?.help ?? ''];
  }
}

/** The column a missing value belongs in: the one this file's confirmed format maps to the issue's parameter. */
function columnFor(run: Run, issue: Issue) {
  if (!issue.parameter) return undefined;
  for (const layout of run.layouts ?? []) {
    if (layout.path !== issue.path) continue;
    const header = Object.entries(layout.mapping.columns).find(([, parameter]) => parameter === issue.parameter)?.[0];
    if (header) return header;
  }
  return undefined;
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
  // The one item whose place in the file is open, and which of a group's values is being looked at.
  const [showing, setShowing] = useState<string | null>(null);
  const [position, setPosition] = useState(0);
  const show = (id: string) => { setShowing(showing === id ? null : id); setPosition(0); };
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
          const sourceId = sourceIdFor(run, issue.path);
          const page = issue.lines?.[0]?.page;
          // A cited row or page is shown directly. A conflict names a batch, time and parameter instead: show each value it is about.
          const places: Array<{ label?: string; location: Location }> = sourceId && issue.path && canShow(issue.path) && (issue.row != null || page != null)
            ? [{ location: { sourceId, path: issue.path, sheet: issue.sheet, row: issue.row, column: issue.header ?? columnFor(run, issue), page } }]
            : issue.batch != null && issue.parameter && issue.time != null
              ? (run.measurements ?? []).filter(m => m.batch === issue.batch && m.parameter === issue.parameter && String(m.time) === String(issue.time) && canShow(m.source.path)).slice(0, 4)
                  .map(m => ({ label: `${m.value_raw}${m.unit_raw ? ` ${m.unit_raw}` : ''}`, location: { sourceId: m.source_id, path: m.source.path, sheet: m.source.sheet, row: m.source.row, column: m.source.column, page: m.source.page, region: m.source.region } }))
              : [];
          // Otherwise the item is about a whole file: show the file.
          const wholeFile = !places.length && sourceId && issue.path ? { sourceId, path: issue.path } : null;
          const place = places.length > 0 || wholeFile;
          return (
            <li key={issue.id} className="px-6 py-3.5">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="min-w-0"><p className="text-[14px] text-ink">{title}</p>{detail && <p className="truncate text-xs text-text-tertiary">{detail}</p>}</div>
                <div className="flex flex-wrap items-center gap-1.5">
                  {issue.lines?.length ? <button className={button} onClick={() => setReading(reading === issue.id ? null : issue.id)}>{reading === issue.id ? 'Hide' : 'Read'}</button> : null}
                  {place && <button className={button} aria-expanded={showing === issue.id} onClick={() => show(issue.id)}>{showing === issue.id ? 'Hide file' : 'Show in file'}</button>}
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
              {place && showing === issue.id && <div className="mt-2 space-y-2">
                {issue.members.length > 1 && <p className="text-[11px] text-text-tertiary">Showing the first of {issue.members.length} rows.</p>}
                {places.map((p, i) => <div key={i}>
                  {p.label && <p className="mb-1 text-[11px] text-text-tertiary">Reads <span className="font-mono text-text-primary">{p.label}</span> here:</p>}
                  <SourceContext runId={run.id} location={p.location} /></div>)}
                {wholeFile && <FilePreview runId={run.id} sourceId={wholeFile.sourceId} path={wholeFile.path} />}
              </div>}
            </li>
          );
        })}
        {groups.map(group => {
          const first = byId.get(group.measurement_ids[0]);
          const reasons = group.rule_codes.filter(c => c !== 'DRAFT_MAPPING').map(ruleTitle).join(' · ') || 'Format not confirmed yet';
          const index = Math.min(position, group.measurement_ids.length - 1);
          const current = showing === group.id ? byId.get(group.measurement_ids[index]) : undefined;
          return (
            <li key={group.id} className="px-6 py-3.5">
             <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="min-w-0">
                <p className="text-[13px]">{plural(group.count, `${parameterLabel(group.parameter)} value`)} <span className="text-text-tertiary">from “{group.column}”</span></p>
                <p className="truncate text-xs text-text-tertiary">{reasons} · {group.path}</p>
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                {first && canShow(first.source.path) && <button className={button} aria-expanded={showing === group.id} onClick={() => show(group.id)}>{showing === group.id ? 'Hide file' : 'Show in file'}</button>}
                {first && <button className={button} onClick={() => onInspect(current ?? first)} title="Open one value to accept, correct or reject it on its own">Decide one value</button>}
                <button className={primary} disabled={!reviewer || group.invalid_values === group.count} onClick={() => decideGroup(group.measurement_ids, 'accept')}>Accept</button>
                <ReasonButton label="Reject" danger placeholder="Why reject these values?" onConfirm={reason => decideGroup(group.measurement_ids, 'reject', reason)} />
              </div>
             </div>
              {current && <div className="mt-2">
                <div className="mb-1 flex flex-wrap items-center gap-2 text-[11px] text-text-tertiary">
                  <span>Value {index + 1} of {group.measurement_ids.length}:</span>
                  <span className="font-mono text-text-primary">{current.value_raw}{current.unit_raw ? ` ${current.unit_raw}` : ''}</span>
                  <span>batch {current.batch || '—'} · {current.time || '—'} h</span>
                  {group.measurement_ids.length > 1 && <span className="ml-auto flex items-center gap-1">
                    <button className={button} disabled={index === 0} onClick={() => setPosition(index - 1)}>Previous</button>
                    <button className={button} disabled={index >= group.measurement_ids.length - 1} onClick={() => setPosition(index + 1)}>Next</button></span>}
                </div>
                <SourceContext runId={run.id} location={{ sourceId: current.source_id, path: current.source.path, sheet: current.source.sheet, row: current.source.row, column: current.source.column, page: current.source.page, region: current.source.region }} />
              </div>}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
