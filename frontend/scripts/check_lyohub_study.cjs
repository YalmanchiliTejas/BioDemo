/* Independently check published denominators, prediction coverage and file hashes. */
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../..');
const publicDir = path.join(root, 'frontend/public/research-results/lyohub');
const data = JSON.parse(fs.readFileSync(path.join(publicDir, 'results.json')));
const manifest = JSON.parse(fs.readFileSync(path.join(publicDir, 'manifest.json')));
for (const [file, hash] of Object.entries(manifest)) {
  assert.equal(crypto.createHash('sha256').update(fs.readFileSync(path.join(publicDir, file))).digest('hex'), hash, file);
}
const references = JSON.parse(fs.readFileSync(path.join(publicDir, 'reference-outcomes.json')));
assert.equal(references.length, 48);
for (const row of data.rows) {
  const reference = references.find(r => r.case_id === row.case_id && r.task === row.task);
  assert(reference);
  const keep = reference.outcomes.keep;
  const expectedCompletion = keep.first_capacity_h === null ? keep.completion_time_h : null;
  assert.equal(row.score.truth.completion_time_h, expectedCompletion);
  const selected = reference.outcomes[row.submission?.action_id];
  const feasible = !!selected && selected.completion_time_h !== null && selected.first_capacity_h === null && selected.first_critical_h === null;
  assert.equal(row.score.selected_feasible, feasible);
  assert.equal(row.score.unsafe_selection, !!selected && !feasible);
  const thermal = keep.first_capacity_h === null ? keep.first_critical_h !== null : keep.first_critical_h !== null && keep.first_critical_h < keep.first_capacity_h ? true : null;
  for (const [kind, truth] of [['thermal', thermal], ['capacity', keep.first_capacity_h !== null]]) {
    const predicted = row.submission?.[kind + '_warning'];
    const expected = row.submission === null ? 'execution_failed' : truth === null ? 'censored' : predicted === null || predicted === undefined ? 'abstain' : (predicted === truth ? 'T' : 'F') + (predicted ? 'P' : 'N');
    assert.equal(row.score[kind], expected);
  }
}
assert.equal(data.rows.length, 240);
assert.equal(data.budget_limited_slots.length, data.rows.filter(r => r.failure_kind === 'admission_denied').length);
for (const slot of data.budget_limited_slots) assert(data.rows.some(r => r.source === 'agent' && r.case_id === slot.case_id && r.task === slot.task && r.arm === slot.arm && r.failure_kind === 'admission_denied'));
const agents = data.rows.filter(r => r.source === 'agent');
assert.equal(agents.length, 144);
assert.equal(new Set(agents.map(r => `${r.case_id}/${r.task}/${r.arm}`)).size, 144);
assert.equal(new Set(agents.map(r => r.case_id)).size, 24);
assert.equal(data.provenance.original_public_packet_hashes_match, 48);
assert.equal(data.protocol.upstream_commit, 'c6a9225a9e551ae4e7c11c1ef056b67c6204afbd');
for (const source of ['agent', 'model']) for (const task of ['all', 'forecast', 'pretransfer']) for (const arm of Object.keys(data.groups[source][task])) {
  const rows = data.rows.filter(r => r.source === source && r.arm === arm && (task === 'all' || r.task === task));
  const g = data.groups[source][task][arm];
  assert.equal(g.planned, rows.length);
  assert.equal(g.feasible, rows.filter(r => r.score.selected_feasible).length);
  assert.equal(g.unsafe, rows.filter(r => r.score.unsafe_selection).length);
  assert.equal(g.submitted, rows.filter(r => r.submission !== null).length);
  assert.equal(g.failed, rows.filter(r => r.submission === null).length);
  assert.equal(g.characterize, rows.filter(r => r.submission?.action_id === 'characterize').length);
  assert.equal(g.feasible + g.unsafe + g.characterize + g.failed, g.planned);
  const errors = rows.filter(r => r.submission?.completion_time_h !== null && r.submission?.completion_time_h !== undefined && r.score.truth.completion_time_h !== null)
    .map(r => Math.abs(r.submission.completion_time_h - r.score.truth.completion_time_h));
  assert.equal(g.predictions, errors.length);
  if (errors.length) assert(Math.abs(g.mae_h - errors.reduce((a,b) => a+b,0) / errors.length) < 1e-9);
  else assert.equal(g.mae_h, null);
  for (const kind of ['thermal','capacity']) assert.equal(Object.values(g[kind]).reduce((a,b) => a+b,0), g.planned);
}
for (const task of ['forecast','pretransfer']) {
  const ids = data.protocol.case_ids.filter(id => ['A','B','C'].every(arm => {
    const r = agents.find(r => r.case_id === id && r.task === task && r.arm === arm);
    return r.submission?.completion_time_h !== null && r.submission?.completion_time_h !== undefined && r.score.truth.completion_time_h !== null;
  }));
  assert.deepEqual(data.paired[task].cases, ids);
}
assert(data.cost.conservative_accounting_usd <= 10 + 1e-7);
assert.equal(data.shared_schema_hashes.length, 1);
assert(fs.existsSync(path.join(root,'frontend/app/(public)/research/lyohub/page.tsx')));
console.log(JSON.stringify({sessions: agents.length, controls: 96, downloads: Object.keys(manifest).length, checks: 'denominators, independent errors, coverage, warning partitions and SHA-256 verified'}));
