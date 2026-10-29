'use client';

import { useMemo, useState } from 'react';
import { ArrowRight, Loader2 } from 'lucide-react';
import { Button, Callout } from '@/components/ui';
import { cn } from '@/lib/cn';
import { kindLabel, postJson, type Layout, type MappingSpec, type Parameter, type Run } from '@/lib/cmo-api';

const BATCH = '__batch__', TIME = '__time__', IGNORE = '__ignore__', UNDECIDED = '';
const LABEL: Record<string, string> = { [BATCH]: 'batch', [TIME]: 'time', [IGNORE]: 'ignored' };
const NEEDS_UNIT = /\[(unspecified|unknown)\]|^[^[(]*$/i;
// Printed documents have no column headers; these are the fields read from each line.
const shown = (h: string) => ({ batch_id: 'Batch', elapsed_h: 'Hour' } as Record<string, string>)[h] ?? h;

function initial(layout: Layout) {
  return Object.fromEntries(layout.headers.map(h => [h, h === layout.mapping.batch_column ? BATCH : h === layout.mapping.time_column ? TIME
    : layout.mapping.columns[h] ?? (layout.mapping.ignored_columns?.includes(h) ? IGNORE : UNDECIDED)]));
}

function toMapping(layout: Layout, choice: Record<string, string>, units: Record<string, string>): MappingSpec {
  const mapped = layout.headers.filter(h => ![UNDECIDED, IGNORE, BATCH, TIME].includes(choice[h]));
  return { columns: Object.fromEntries(mapped.map(h => [h, choice[h]])),
    batch_column: layout.headers.find(h => choice[h] === BATCH) ?? null, time_column: layout.headers.find(h => choice[h] === TIME) ?? null,
    units: Object.fromEntries(Object.entries(units).filter(([h, u]) => u.trim() && mapped.includes(h))),
    ignored_columns: layout.headers.filter(h => choice[h] === IGNORE) };
}

function problem(layout: Layout, choice: Record<string, string>) {
  const values = layout.headers.map(h => choice[h]);
  const undecided = values.filter(v => v === UNDECIDED).length;
  if (undecided) return `choose a meaning for ${undecided} column${undecided > 1 ? 's' : ''}`;
  const parameters = values.filter(v => ![IGNORE, BATCH, TIME].includes(v)).length;
  if (parameters === 0) return '';
  if (values.filter(v => v === BATCH).length !== 1) return 'choose one batch column';
  if (values.filter(v => v === TIME).length !== 1) return 'choose one time column';
  return '';
}

function Select({ header, value, parameters, onChange }: { header: string; value: string; parameters: Parameter[]; onChange: (v: string) => void }) {
  return (
    <select aria-label={`Meaning of ${header}`} value={value} onChange={e => onChange(e.target.value)}
      className={cn('h-7 rounded-control border px-1.5 text-xs', value === UNDECIDED ? 'border-amber-400 bg-amber-50' : 'border-border-strong')}>
      <option value={UNDECIDED}>Choose…</option><option value={BATCH}>Batch / lot</option><option value={TIME}>Process time</option><option value={IGNORE}>Ignore</option>
      <optgroup label="Parameter">{parameters.map(p => <option key={p.id} value={p.id}>{p.id.replace(/_/g, ' ')} ({p.unit})</option>)}</optgroup>
    </select>
  );
}

/** Proposed column meanings for every new layout, confirmed and applied with one click. */
export function Mappings({ run, layouts, parameters, reviewer, onApplied }: { run: Run; layouts: Layout[]; parameters: Parameter[]; reviewer: string; onApplied: (newRunId: string) => void }) {
  const [choices, setChoices] = useState(() => Object.fromEntries(layouts.map(l => [l.fingerprint, initial(l)])));
  const [units, setUnits] = useState<Record<string, Record<string, string>>>(() => Object.fromEntries(layouts.map(l => [l.fingerprint, l.mapping.units ?? {}])));
  const [editing, setEditing] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const problems = useMemo(() => layouts.map(l => [l, problem(l, choices[l.fingerprint])] as const).filter(([, p]) => p), [layouts, choices]);

  function set(fp: string, header: string, value: string) {
    const next = { ...choices[fp] };
    if (value === BATCH || value === TIME) for (const h of Object.keys(next)) if (next[h] === value) next[h] = UNDECIDED;
    next[header] = value; setChoices({ ...choices, [fp]: next });
  }

  async function apply() {
    setBusy(true); setError('');
    try {
      for (const layout of layouts) {
        await postJson(`/runs/${run.id}/templates`, { fingerprint: layout.fingerprint, mapping: toMapping(layout, choices[layout.fingerprint], units[layout.fingerprint]), actor: reviewer });
      }
      onApplied((await postJson<{ id: string }>(`/runs/${run.id}/reprocess`, { actor: reviewer })).id);
    } catch (e) { setError((e as Error).message); setBusy(false); }
  }

  return (
    <section className="rounded-2xl border border-border-hairline bg-white" data-testid="mappings">
      <div className="border-b border-border-hairline px-6 py-5">
        <h2 className="font-display text-[20px] font-light text-ink">Check how we read {layouts.length === 1 ? 'this file' : `these ${layouts.length} files`}</h2>
        <p className="mt-1 text-[13px] text-text-secondary">Confirm once and {run.cmo}’s future deliveries in the same format are read automatically.</p>
      </div>
      <ul className="divide-y divide-border-hairline">
        {layouts.map(layout => {
          const choice = choices[layout.fingerprint]; const open = editing === layout.fingerprint;
          const ignoreTable = layout.headers.every(h => choice[h] === IGNORE);
          return (
            <li key={layout.fingerprint} className="px-6 py-4" data-mapping-editor={layout.fingerprint}>
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <p className="text-[14px] font-medium text-ink">{layout.path}{layout.sheet ? ` · ${layout.sheet}` : ''} <span className="font-normal text-text-tertiary">· {kindLabel(layout.kind)}</span></p>
                <div className="flex gap-2 text-xs">
                  {!ignoreTable && <button className="text-text-tertiary hover:text-text-primary" onClick={() => setChoices({ ...choices, [layout.fingerprint]: Object.fromEntries(layout.headers.map(h => [h, IGNORE])) })}>Not process data</button>}
                  <button className="text-brand-teal hover:underline" onClick={() => setEditing(open ? null : layout.fingerprint)}>{open ? 'Done' : 'Edit'}</button>
                </div>
              </div>
              {layout.based_on && <p className="mt-1 text-xs text-sky-700">Changed since last time: {[layout.based_on.added_headers.length && `new ${layout.based_on.added_headers.join(', ')}`, layout.based_on.removed_headers.length && `missing ${layout.based_on.removed_headers.join(', ')}`].filter(Boolean).join('; ') || 'column order'}.</p>}
              {ignoreTable ? <p className="mt-1.5 text-xs text-text-secondary">Whole table ignored (for example notes or signatures).</p> : open ? (
                <table className="mt-2 w-full text-xs"><tbody>{layout.headers.map(h => {
                  const parameter = parameters.find(p => p.id === choice[h]);
                  return (
                    <tr key={h} className="border-t border-border-hairline">
                      <td className="py-1.5 pr-2 font-medium">{shown(h)}</td>
                      <td className="py-1.5 pr-2"><Select header={h} value={choice[h]} parameters={parameters} onChange={v => set(layout.fingerprint, h, v)} /></td>
                      <td className="py-1.5">{parameter && NEEDS_UNIT.test(h) && <input aria-label={`Unit for ${h}`} placeholder={`unit, e.g. ${parameter.unit}`} value={units[layout.fingerprint][h] ?? ''}
                        onChange={e => setUnits({ ...units, [layout.fingerprint]: { ...units[layout.fingerprint], [h]: e.target.value } })} className="h-7 w-32 rounded-control border border-border-strong px-1.5" />}</td>
                    </tr>
                  );
                })}</tbody></table>
              ) : (
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {layout.headers.map(h => choice[h] === UNDECIDED
                    ? <span key={h} className="flex items-center gap-1 text-xs"><b>{h}</b><ArrowRight className="h-3 w-3 text-text-muted" /><Select header={h} value={choice[h]} parameters={parameters} onChange={v => set(layout.fingerprint, h, v)} /></span>
                    : <span key={h} className={cn('rounded-pill border px-2 py-0.5 text-xs', choice[h] === IGNORE ? 'border-border-hairline text-text-muted line-through' : 'border-border-hairline bg-surface-secondary text-text-secondary')}>
                        {shown(h)} → {LABEL[choice[h]] ?? choice[h].replace(/_/g, ' ')}</span>)}
                </div>
              )}
            </li>
          );
        })}
      </ul>
      <div className="flex flex-wrap items-center gap-3 border-t border-border-hairline px-6 py-4">
        <Button variant="primary" size="lg" disabled={busy || problems.length > 0 || !reviewer} onClick={apply}>{busy && <Loader2 className="h-4 w-4 animate-spin" />}Looks right, apply</Button>
        <span className="text-xs text-text-tertiary">{!reviewer ? 'Enter your name at the top right first.' : problems.length ? `${problems[0][0].path}: ${problems[0][1]}.` : 'Values that match the original file and pass every check are verified automatically.'}</span>
      </div>
      {error && <Callout tone="critical" className="m-4 mt-0">{error}</Callout>}
    </section>
  );
}
