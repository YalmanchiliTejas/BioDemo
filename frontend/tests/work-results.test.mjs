import assert from 'node:assert/strict';
import test from 'node:test';
import { csvTable, exportTable, projectThread, structuredAnswer, workView } from '../lib/work-results.ts';

const turn = (text, reply, status = 'completed') => ({ id: 'turn-1', user_text: text, reply, status });
const project = t => projectThread({ id: 'thread-1', title: 'Review', turns: [t] })[0];
const holdSource = 'Synthetic example\nholds.csv\nbatch_id,Hold (h)\nA,4\nB,5\n\nprocedure.csv\nbatch_id,Maximum hold (h)\nprocedure,4\n';

test('CSV preserves decimal commas, escaped quotes and physical source lines', () => {
  const parsed = csvTable('records.csv', 'id,value,note\nA,"1,25","a ""quoted"" value"\nB,2,"two\nlines"\nC,3,last\n');
  assert.equal(parsed.rows[0].values.value, '1,25');
  assert.equal(parsed.rows[0].values.note, 'a "quoted" value');
  assert.equal(parsed.rows[2].line, 5);
  assert.equal(csvTable('bad.csv', 'id,value\nA,"unclosed'), null);
});

test('no answer, conflicting answers and narrative summaries never invent results', () => {
  assert.equal(structuredAnswer('No machine-readable result.').answer, null);
  assert.equal(structuredAnswer('{"affected_batch_ids":[]} {"affected_batch_ids":["B"]}').answer, null);
  assert.deepEqual(projectThread({ id: 'summary', title: 'Overview', turns: [turn('Overview of all results', '{"affected_batch_ids":["B"]}')] }), []);
  assert.equal(project(turn(holdSource, null, 'blocked')).answer, null);
});

test('hold boundary is inclusive; a missed agent flag remains visible as a comparison issue', () => {
  const result = project(turn(holdSource, '{"affected_batch_ids":[]}'));
  const view = workView(result);
  assert.equal(view.rows[0].computedAttention, false);
  assert.equal(view.rows[1].computedAttention, true);
  assert.equal(view.rows[1].flagged, false);
  assert.match(view.issues[0], /agent finding differs/);
  assert.deepEqual(view.rows.map(r => r.line), [2, 3]);
});

test('ingestion keeps every conflicting source row and routes unknown IDs explicitly', () => {
  const text = 'delivery.csv\nrecord_id,Raw value,Raw unit\nA,"1,2",g/L\nB,2,mg/L\nB,3,mg/L\n';
  const view = workView(project(turn(text, JSON.stringify({ measurements: [{ record_id: 'A', value_mg_per_l: 1200 }], review_record_ids: ['B', 'unknown'] }))));
  assert.equal(view.rows.length, 3);
  assert.equal(view.rows[0].cells[1], '1,2');
  assert.equal(view.rows[0].cells[3], '1200 mg/L');
  assert(view.rows.slice(1).every(r => r.flagged));
  assert.match(view.issues[0], /unknown.*no source row/);
});

test('schedule checks maintenance, due times, predecessors and shared-line conflicts', () => {
  const text = 'jobs.csv\nbatch_id,duration_hours,ready_hour,due_hour,predecessor\nA,3,2,8,\nB,2,0,9,A\n\ncalendar.csv\nunavailable_start_hour,unavailable_end_hour\n4,6\n';
  const reply = JSON.stringify({ feasible: true, assignments: [{ job_id: 'A', start_hour: 3, end_hour: 6 }, { job_id: 'B', start_hour: 5, end_hour: 7 }] });
  const view = workView(project(turn(text, reply)));
  assert(view.issues.some(i => i.includes('Maintenance overlap')));
  assert(view.issues.some(i => i.includes('Predecessor not complete')));
  assert(view.issues.some(i => i.includes('Line overlap')));
  assert.equal(view.metrics.find(m => m.label === 'Dispatch').value, 'Not performed');
});

test('CSV export quotes data and prevents spreadsheet-formula execution', () => {
  const csv = exportTable({ headers: ['Value'], rows: [{ cells: [' =1+1'] }, { cells: ['a,"b"'] }] });
  assert(csv.includes('"\' =1+1"'));
  assert(csv.includes('"a,""b"""'));
});
