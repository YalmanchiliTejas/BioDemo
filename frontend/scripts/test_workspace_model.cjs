// Exercise durable work semantics without a browser or backend.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { execFileSync } = require('node:child_process');
const root = path.resolve(__dirname, '..');
const out = fs.mkdtempSync(path.join(os.tmpdir(), 'biodemo-workspace-model-'));
execFileSync(process.execPath, [path.join(root, 'node_modules/typescript/bin/tsc'), path.join(root, 'src/os/workspace-model.ts'), '--outDir', out, '--module', 'commonjs', '--target', 'ES2020', '--skipLibCheck'], { stdio: 'pipe' });
const model = require(path.join(out, 'workspace-model.js'));
const at = '2026-10-22T20:00:00.000Z';
const proposal = { workId: model.SAMPLE_ID, title: 'Verify the DO reading', owner: 'Process engineer', rationale: 'The probe may be drifting', expected: 'Independent reading with timestamp', constraint: 'No setpoint changes', evidenceIds: ['S1'] };

test('a new goal survives serialization with its scope and notes intact', () => {
  const original = model.initialWorkspace();
  const added = model.createWork(original, { goal: '  Review a cleaning record  ', kind: 'data-review', context: 'none' }, 'cleaning', at);
  const noted = model.addNote(added, 'cleaning', 'Need the approved record version', 'Reviewer', 'note-1', at);
  const restored = model.decodeWorkspace(JSON.stringify(noted));
  assert.equal(restored.work[0].goal, 'Review a cleaning record');
  assert.equal(restored.work[0].context, 'none');
  assert.equal(restored.work[0].notes[0].body, 'Need the approved record version');
  assert.equal(original.work.length, 1, 'Prior state must stay unchanged');
});
test('an unsupported or corrupt saved workspace is rejected instead of being treated as success', () => {
  for (const value of ['{', '{"version":99}', '{"version":1,"work":{},"actions":[]}']) assert.throws(() => model.decodeWorkspace(value));
});
test('malformed note data cannot enter the renderer through saved storage', () => {
  const d = model.initialWorkspace(); d.work[0].notes.push({ id: 'x', body: {}, at, author: 'Someone' });
  assert.throws(() => model.decodeWorkspace(JSON.stringify(d)));
});
test('actions cannot point to missing work and duplicate identifiers are rejected', () => {
  assert.throws(() => model.proposeAction(model.initialWorkspace(), { ...proposal, workId: 'missing' }, 'Reviewer', 'a', at));
  const d = model.initialWorkspace(); d.work.push(d.work[0]);
  assert.throws(() => model.decodeWorkspace(JSON.stringify(d)));
});
test('a proposal cannot skip local review or claim an outcome without progress', () => {
  const d = model.proposeAction(model.initialWorkspace(), proposal, 'Engineer', 'a', at);
  assert.throws(() => model.transitionAction(d, 'a', 'in_progress', 'Started', 'Engineer', at));
  assert.throws(() => model.transitionAction(d, 'a', 'outcome_recorded', 'Done', 'Engineer', at));
  assert.throws(() => model.transitionAction(d, 'a', 'reviewed', ' ', 'Engineer', at));
});
test('each action stage retains the actor, explanation and observed outcome', () => {
  let d = model.proposeAction(model.initialWorkspace(), proposal, 'Engineer', 'a', at);
  d = model.transitionAction(d, 'a', 'reviewed', 'Checked the source and constraints', 'Reviewer', at);
  d = model.transitionAction(d, 'a', 'in_progress', 'Independent reading requested', 'Engineer', at);
  d = model.transitionAction(d, 'a', 'outcome_recorded', 'Portable probe read 26%; cause still uncertain', 'Engineer', at);
  const restored = model.decodeWorkspace(JSON.stringify(d));
  assert.equal(restored.actions[0].status, 'outcome_recorded');
  assert.equal(restored.actions[0].events.length, 4);
  assert.equal(restored.actions[0].events[3].note, 'Portable probe read 26%; cause still uncertain');
  assert.throws(() => model.transitionAction(d, 'a', 'proposed', 'Reset', 'Engineer', at));
});
test('saved status must agree with the last action event', () => {
  const d = model.proposeAction(model.initialWorkspace(), proposal, 'Engineer', 'a', at);
  d.actions[0].status = 'outcome_recorded';
  assert.throws(() => model.decodeWorkspace(JSON.stringify(d)));
});
test('blank goals and invalid work categories do not create work', () => {
  assert.throws(() => model.createWork(model.initialWorkspace(), { goal: ' ', kind: 'question', context: 'none' }, 'x', at));
  assert.throws(() => model.createWork(model.initialWorkspace(), { goal: 'Goal', kind: 'unknown', context: 'none' }, 'x', at));
});
