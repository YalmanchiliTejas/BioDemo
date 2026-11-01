/** Read-only projections of saved account work. Never consults benchmark keys or runs a model. */
export type WorkKind = 'holds' | 'deviations' | 'ingestion' | 'scheduling';
export type SourceRow = { line: number; values: Record<string, string> };
export type SourceTable = { name: string; headers: string[]; rows: SourceRow[]; raw: string };
export type SavedTurn = { id: string; user_text: string; reply: string | null; status: string;
  questions?: string[]; issues?: string[]; elapsed_seconds?: number; created_at?: string;
  gateway_runs?: { route?: { model?: string; unqualified?: boolean } | null }[];
  steps?: { node_id: string; title: string; status: string }[] };
export type SavedThread = { id: string; title: string; turns: SavedTurn[] };
type Obj = Record<string, unknown>;
export type WorkResult = { id: string; threadId: string; label: string; kind: WorkKind; turn: SavedTurn;
  sources: SourceTable[]; answer: Obj | null; answerIssue: string | null; synthetic: boolean };
export type DataRow = { id: string; source: string; line: number; cells: string[]; flagged: boolean;
  value?: number; computedAttention?: boolean; start?: number; end?: number; ready?: number; due?: number };
export type WorkView = { title: string; description: string; headers: string[]; rows: DataRow[];
  metrics: { label: string; value: string; note: string }[]; issues: string[];
  lower?: number; upper?: number; maintenance?: [number, number]; chartLabel: string };

export const WORK_KINDS: { id: WorkKind; label: string; title: string }[] = [
  { id: 'holds', label: 'Investigations', title: 'Review batch hold times' },
  { id: 'deviations', label: 'Deviations', title: 'Review assay deviations' },
  { id: 'ingestion', label: 'Data preparation', title: 'Reconcile delivery values' },
  { id: 'scheduling', label: 'Scheduling', title: 'Review the proposed schedule' },
];
const object = (v: unknown): v is Obj => !!v && typeof v === 'object' && !Array.isArray(v);
const finite = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
export function numeric(value: unknown): number | undefined {
  if (typeof value !== 'string' || !value.trim()) return undefined;
  const v = Number(value.replace(',', '.'));return Number.isFinite(v) ? v : undefined;
}
const fmt = (value: number | undefined) => value === undefined ? '—' : Number(value.toPrecision(8)).toString();

/** RFC-style quoted fields, including decimal commas and physical source-line locations. */
export function csvTable(name: string, raw: string): SourceTable | null {
  const records: { cells: string[]; line: number }[] = [];
  let cells: string[] = [], cell = '', quoted = false, line = 1, start = 1;
  for (let i = 0; i <= raw.length; i++) {
    const char = raw[i];
    if (char === '"') {
      if (quoted && raw[i + 1] === '"') { cell += '"'; i++; }
      else if (quoted || cell === '') quoted = !quoted;
      else return null;
    } else if (char === ',' && !quoted) { cells.push(cell); cell = ''; }
    else if ((char === '\n' || i === raw.length) && !quoted) {
      cells.push(cell.replace(/\r$/, ''));cell = '';
      if (cells.some(v => v.trim())) records.push({ cells, line: start });
      cells = [];line++;start = line;
      if (records.length > 1001) return null;
    } else { if (char !== undefined) cell += char; if (char === '\n') line++; }
  }
  if (quoted || records.length < 2) return null;
  const headers = records.shift()!.cells;
  if (new Set(headers).size !== headers.length || headers.length > 64 || records.some(r => r.cells.length !== headers.length)) return null;
  return { name, raw, headers, rows: records.map(r => ({ line: r.line, values: Object.fromEntries(headers.map((h, i) => [h, r.cells[i]])) })) };
}

export function sourceTables(text: string): SourceTable[] {
  const matches = [...text.matchAll(/(?:^|\n)([A-Za-z0-9_. -]{1,100}\.csv)\r?\n/g)];
  const tables = matches.flatMap((m, i) => {
    const raw = text.slice(m.index! + m[0].length, matches[i + 1]?.index ?? text.length).trim();
    const table = csvTable(m[1], raw);return table ? [table] : [];
  });
  return new Set(tables.map(t => t.name)).size === tables.length ? tables : [];
}

function answerKind(a: Obj): WorkKind | null {
  const ids = (v: unknown) => Array.isArray(v) && v.every(i => typeof i === 'string');
  if (ids(a.affected_batch_ids)) return 'holds';
  if (ids(a.deviation_result_ids)) return 'deviations';
  if (ids(a.review_record_ids) && Array.isArray(a.measurements) && a.measurements.every(m => object(m) && typeof m.record_id === 'string' && finite(m.value_mg_per_l))) return 'ingestion';
  if (typeof a.feasible === 'boolean' && Array.isArray(a.assignments) && a.assignments.every(j => object(j) && typeof j.job_id === 'string' && finite(j.start_hour) && finite(j.end_hour))) return 'scheduling';
  return null;
}

export function structuredAnswer(reply: string | null): { answer: Obj | null; kind: WorkKind | null; issue: string | null } {
  const found: Obj[] = [];
  const text = reply ?? '';
  for (let start = 0; start < text.length; start++) {
    if (text[start] !== '{') continue;
    let depth = 0, quoted = false, escaped = false;
    for (let end = start; end < text.length; end++) {
      const c = text[end];
      if (quoted) { if (escaped) escaped = false; else if (c === '\\') escaped = true; else if (c === '"') quoted = false; }
      else if (c === '"') quoted = true;
      else if (c === '{') depth++;
      else if (c === '}' && --depth === 0) {
        try {
          const value: unknown = JSON.parse(text.slice(start, end + 1));
          if (object(value) && answerKind(value) && !found.some(a => JSON.stringify(a) === JSON.stringify(value))) found.push(value);
        } catch { /* Narrative braces are not structured results. */ }
        break;
      }
    }
  }
  if (found.length !== 1) return { answer: null, kind: null, issue: found.length ? 'Multiple conflicting structured answers. Review the original response.' : null };
  return { answer: found[0], kind: answerKind(found[0]), issue: null };
}

export function projectThread(thread: SavedThread): WorkResult[] {
  return thread.turns.flatMap((turn, i) => {
    const sources = sourceTables(turn.user_text);
    if (!sources.length) return []; // Never turn prose-only summaries into invented data.
    const parsed = structuredAnswer(turn.reply);
    const columns = new Set(sources.flatMap(s => s.headers));
    const sourceKind: WorkKind | null = columns.has('Hold (h)') ? 'holds' : columns.has('Result (mg/L)') ? 'deviations' : columns.has('duration_hours') ? 'scheduling' : columns.has('record_id') && (columns.has('Raw unit') || columns.has('unit')) ? 'ingestion' : null;
    const kind = sourceKind ?? parsed.kind;
    if (!kind) return [];
    const mismatch = parsed.kind && parsed.kind !== kind;
    const label = turn.user_text.split('\n')[0].match(/\b(?:investigations|deviations|ingestion|scheduling)-\d+\b/)?.[0] ?? `Review ${i + 1}`;
    return [{ id: turn.id, threadId: thread.id, label: label + (/follow-up/i.test(turn.user_text.split('\n')[0]) ? ' · Follow-up' : ''),
      kind, turn, sources, answer: mismatch ? null : parsed.answer,
      answerIssue: mismatch ? 'The returned answer does not match the source task.' : parsed.issue,
      synthetic: /\bsynthetic\b/i.test(turn.user_text) }];
  });
}

export function workView(result: WorkResult): WorkView {
  const { kind, answer, sources } = result;
  const issues = result.answerIssue ? [result.answerIssue] : [];
  const source = (column: string) => sources.find(s => s.headers.includes(column));
  if (kind === 'holds' || kind === 'deviations') {
    const holds = kind === 'holds';
    const data = source(holds ? 'Hold (h)' : 'Result (mg/L)');
    const spec = source(holds ? 'Maximum hold (h)' : 'revision');
    const current = holds ? spec?.rows : spec?.rows.filter(r => r.values.revision === 'current');
    const bounds = current?.length === 1 ? current[0].values : undefined;
    const lower = holds ? undefined : numeric(bounds?.['Lower (mg/L)']);
    const upper = numeric(bounds?.[holds ? 'Maximum hold (h)' : 'Upper (mg/L)']);
    if (upper === undefined || (!holds && lower === undefined)) issues.push('A unique comparison limit is missing. Source review is required.');
    const flags = (answer?.[holds ? 'affected_batch_ids' : 'deviation_result_ids'] ?? []) as string[];
    const known = new Set(data?.rows.map(r => r.values[holds ? 'batch_id' : 'result_id']));
    for (const id of flags) if (!known.has(id)) issues.push(`Agent returned ${id}, which has no matching source row.`);
    const rows = (data?.rows ?? []).map(r => {
      const v = r.values;const id = v[holds ? 'batch_id' : 'result_id'];const value = numeric(v[holds ? 'Hold (h)' : 'Result (mg/L)']);
      const exceed = value !== undefined && upper !== undefined && (value > upper || (lower !== undefined && value < lower));
      if (answer && value !== undefined && upper !== undefined && exceed !== flags.includes(id)) issues.push(`${id}: the agent finding differs from the source-limit comparison.`);
      return { id, source: data!.name, line: r.line, value, computedAttention: exceed, flagged: flags.includes(id),
        cells: [id, ...(holds ? [] : [v.batch_id]), `${fmt(value)} ${holds ? 'h' : 'mg/L'}`, upper === undefined ? 'Limit missing' : holds ? `≤ ${upper} h` : `${lower}–${upper} mg/L`,
          value === undefined || upper === undefined ? 'Unknown' : exceed ? 'Outside limit' : 'Within limit', !answer ? 'No answer' : flags.includes(id) ? 'Flagged for review' : 'Not flagged'] };
    });
    return { title: holds ? 'Batch holds against the procedure' : 'Assay results against the current specification',
      description: holds ? 'Hold durations with the maximum shown as a dashed line.' : 'The shaded band shows the source-labeled current specification.',
      headers: [holds ? 'Batch' : 'Assay', ...(holds ? [] : ['Batch']), 'Observed', 'Source limit', 'Calculated comparison', 'Agent finding'], rows, issues, lower, upper,
      chartLabel: holds ? 'Hold duration (hours)' : 'Assay result (mg/L)',
      metrics: [{ label: holds ? 'Batches' : 'Assays', value: String(rows.length), note: 'In supplied source rows' }, { label: 'Flagged by agent', value: answer ? String(flags.length) : '—', note: 'Awaiting source review' },
        { label: 'Source limit', value: upper === undefined ? 'Missing' : holds ? `${upper} h` : `${lower}–${upper}`, note: holds ? 'Maximum inclusive hold' : 'mg/L · current-labeled SOP' }] };
  }
  if (kind === 'ingestion') {
    const data = source('record_id');const proposed = (answer?.measurements ?? []) as { record_id: string; value_mg_per_l: number }[];
    const review = (answer?.review_record_ids ?? []) as string[];const counts = new Map<string, number>();
    for (const row of data?.rows ?? []) counts.set(row.values.record_id, (counts.get(row.values.record_id) ?? 0) + 1);
    if (new Set(proposed.map(p => p.record_id)).size !== proposed.length) issues.push('The returned normalization contains duplicate record IDs.');
    for (const p of proposed) if (!counts.has(p.record_id)) issues.push(`Agent returned ${p.record_id}, which has no source row.`);
    for (const id of review) if (!counts.has(id)) issues.push(`Review record ${id} has no source row.`);
    const rows = (data?.rows ?? []).map(r => { const v = r.values;const id = v.record_id;const p = proposed.find(x => x.record_id === id);
      return { id: `${id}:${r.line}`, source: data!.name, line: r.line, flagged: review.includes(id),
        cells: [id, v['Raw value'] ?? v.value ?? '', v['Raw unit'] || v.unit || 'Missing', p ? `${fmt(p.value_mg_per_l)} mg/L` : '—', !answer ? 'No answer' : review.includes(id) ? 'Needs review' : p ? 'Proposed value' : 'Not returned', (counts.get(id) ?? 0) > 1 ? 'Duplicate source ID' : '—'] }; });
    return { title: 'Original values and normalization proposals', description: 'Values remain proposals until their sources and any conflicts are reviewed.',
      headers: ['Record', 'As supplied', 'Source unit', 'Agent normalization', 'Review route', 'Source issue'], rows, issues, chartLabel: 'Record routing',
      metrics: [{ label: 'Source rows', value: String(rows.length), note: `${counts.size} unique record IDs` }, { label: 'Normalized proposals', value: answer ? String(proposed.length) : '—', note: 'Not approved measurements' },
        { label: 'Needs review', value: answer ? String(review.length) : '—', note: 'Missing values or conflicts' }] };
  }
  const jobs = source('duration_hours');const calendar = source('unavailable_start_hour');
  const window = calendar?.rows[0]?.values;const m0 = numeric(window?.unavailable_start_hour), m1 = numeric(window?.unavailable_end_hour);
  const maintenance: [number, number] | undefined = m0 !== undefined && m1 !== undefined && m1 >= m0 ? [m0, m1] : undefined;
  const assignments = (answer?.assignments ?? []) as { job_id: string; start_hour: number; end_hour: number }[];
  const planned = new Map(assignments.map(j => [j.job_id, j]));
  if (answer?.feasible === false && assignments.length) issues.push('The agent reports infeasibility but also supplies job timings.');
  if (planned.size !== assignments.length) issues.push('The proposal repeats a job ID.');
  if (answer?.feasible === true && planned.size !== jobs?.rows.length) issues.push('The proposal does not cover every source job.');
  const known = new Set(jobs?.rows.map(r => r.values.batch_id));
  for (const a of assignments) if (!known.has(a.job_id)) issues.push(`Proposed job ${a.job_id} has no source row.`);
  const rows = (jobs?.rows ?? []).map(r => {
    const v = r.values, id = v.batch_id, a = planned.get(id);const ready = numeric(v.ready_hour), due = numeric(v.due_hour), duration = numeric(v.duration_hours);
    const violations: string[] = [];
    if (a) {
      if (ready === undefined || due === undefined || duration === undefined) violations.push('Missing source constraint');
      if (a.start_hour < (ready ?? Infinity)) violations.push('Before ready time');
      if (a.end_hour > (due ?? -Infinity)) violations.push('After due time');
      if (a.end_hour <= a.start_hour || Math.abs(a.end_hour - a.start_hour - (duration ?? NaN)) > 1e-8) violations.push('Duration mismatch');
      if (maintenance && a.start_hour < maintenance[1] && a.end_hour > maintenance[0]) violations.push('Maintenance overlap');
      if (v.predecessor && (!planned.has(v.predecessor) || a.start_hour < planned.get(v.predecessor)!.end_hour)) violations.push('Predecessor not complete');
      if (assignments.some(b => b !== a && b.start_hour < a.end_hour && a.start_hour < b.end_hour)) violations.push('Line overlap');
    }
    for (const violation of violations) issues.push(`${id}: ${violation}`);
    return { id, source: jobs!.name, line: r.line, ready, due, start: a?.start_hour, end: a?.end_hour, flagged: violations.length > 0,
      cells: [id, `${fmt(duration)} h`, fmt(ready), fmt(due), v.predecessor || 'None', a ? `${a.start_hour}–${a.end_hour} h` : 'Not proposed', a ? violations.join(' · ') || 'Listed constraints met' : 'No timing to check'] };
  });
  if (!maintenance) issues.push('Maintenance limits could not be resolved from the source.');
  return { title: 'Proposed line schedule', description: 'Bars are the agent’s proposal. The grey window is source-supplied maintenance. Nothing has been dispatched.',
    headers: ['Job', 'Duration', 'Ready (h)', 'Due (h)', 'Predecessor', 'Proposed timing', 'Calculated checks'], rows, issues, maintenance, chartLabel: 'Elapsed hours',
    metrics: [{ label: 'Jobs', value: String(rows.length), note: 'One shared line' }, { label: 'Proposed makespan', value: assignments.length ? `${Math.max(...assignments.map(a => a.end_hour))} h` : '—', note: answer?.feasible === false ? 'Agent reports infeasibility' : 'Conditional on supplied constraints' },
      { label: 'Dispatch', value: 'Not performed', note: 'Reviewer authorization required' }] };
}

/** Spreadsheet-safe CSV export of the visible work table, never an approval. */
export function exportTable(view: WorkView): string {
  const cell = (v: string) => '"' + (/^\s*[=+\-@]/.test(v) ? "'" + v : v).replaceAll('"', '""') + '"';
  return [view.headers, ...view.rows.map(r => r.cells)].map(row => row.map(cell).join(',')).join('\r\n');
}
