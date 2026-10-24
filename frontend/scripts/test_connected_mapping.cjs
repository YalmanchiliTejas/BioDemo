// Exercise connected-mode display mapping, connection decoding and error messages
// without a browser or a server.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { execFileSync } = require('node:child_process');
const root = path.resolve(__dirname, '..');
const out = fs.mkdtempSync(path.join(os.tmpdir(), 'biodemo-connected-mapping-'));
const api = (name) => path.join(root, 'src/os/api', name);
execFileSync(process.execPath, [path.join(root, 'node_modules/typescript/bin/tsc'), api('mapping.ts'), api('connection.ts'), api('client.ts'), '--outDir', out, '--module', 'commonjs', '--target', 'ES2020', '--skipLibCheck', '--strict'], { stdio: 'pipe' });
const map = require(path.join(out, 'mapping.js'));
const conn = require(path.join(out, 'connection.js'));
const client = require(path.join(out, 'client.js'));

const proposal = (over = {}) => ({
  proposal_id: 'prop-1', operation: 'place_hold', target_system: 'MES', target_id: 'F-2408',
  rationale: 'r', expected_result: 'e', owner_id: 'priya', risk: 'medium', required_roles: ['qa'],
  status: 'proposed', execution_status: 'not_started', effectiveness: 'unknown', basis: [],
  stale_reasons: [], revision: 1, requested_by: 'priya', created_at: '2026-10-23T00:00:00+00:00',
  approvals: [], outcomes: [], can_decide: [], content_hash: 'h1', ...over,
});
const label = (over) => map.proposalStatus(proposal(over)).label;

test('every proposal state has its own label and none is conflated with a later state', () => {
  assert.equal(label({}), 'Awaiting approval: qa');
  assert.equal(label({ required_roles: ['qa', 'supervisor'] }), 'Awaiting approval: qa, supervisor');
  assert.equal(label({ status: 'approved', execution_status: 'queued' }), 'Approved — not yet sent');
  assert.equal(label({ status: 'stale' }), 'Evidence changed — needs reassessment');
  assert.equal(label({ status: 'approved', execution_status: 'awaiting_reassessment' }), 'Evidence changed — needs reassessment');
  assert.equal(label({ status: 'rejected' }), 'Rejected');
  assert.equal(label({ status: 'approved', execution_status: 'delivered' }), 'Sent to MES');
  assert.equal(label({ status: 'approved', execution_status: 'unknown' }), 'Delivery unconfirmed — reconciling');
  assert.equal(label({ status: 'approved', execution_status: 'dispatching' }), 'Sending to MES');
  assert.equal(label({ status: 'approved', execution_status: 'failed' }), 'Delivery failed');
  const outcome = { outcome_id: 'o1', observation: 'o', measure: 'm', observed_value: 1, evidence: [], attribution_limits: 'l', recorded_by: 'priya', recorded_at: 'x' };
  assert.equal(label({ status: 'approved', execution_status: 'delivered', outcomes: [outcome] }), 'Outcome recorded');
  assert.equal(label({ status: 'weird' }), 'Status: weird');
  assert.equal(label({ status: 'approved', execution_status: 'queued' }).includes('Sent'), false);
});

test('roles that already approved the current content are no longer awaited', () => {
  const approval = (role, hash) => ({ approval_id: role + hash, proposal_id: 'prop-1', actor_id: 'quinn', role, decision: 'approved', decided_at: 'x', content_hash: hash });
  const p = proposal({ required_roles: ['qa', 'supervisor'], approvals: [approval('qa', 'h1'), approval('supervisor', 'old')] });
  assert.deepEqual(map.pendingRoles(p), ['supervisor']);
  assert.equal(map.proposalStatus(p).label, 'Awaiting approval: supervisor');
});

test('decision, delivery, outcome and effectiveness stay separate and effectiveness is never assumed', () => {
  const stages = Object.fromEntries(map.proposalStages(proposal({ status: 'approved', execution_status: 'queued' })).map((s) => [s.name, s.label]));
  assert.equal(stages.Decision, 'Approved');
  assert.equal(stages.Delivery, 'Approved — not yet sent');
  assert.equal(stages.Outcome, 'No outcome recorded');
  assert.equal(stages.Effectiveness, 'Effectiveness not assessed');
  assert.equal(map.effectivenessLabel('effective'), 'Assessed effective');
  assert.equal(map.effectivenessLabel('ineffective'), 'Assessed not effective');
  assert.equal(map.effectivenessLabel('anything else'), 'Effectiveness not assessed');
  assert.equal(map.proposalStages(proposal())[1].label, 'Nothing sent');
});

test('mission-kind basis is labelled as user-authored with no source evidence', () => {
  assert.equal(map.basisLabel({ kind: 'mission', id: 'msn-1' }), 'User-authored — no source evidence linked');
  assert.equal(map.USER_AUTHORED_BASIS, 'User-authored — no source evidence linked');
  assert.equal(map.isUserAuthoredOnly([{ kind: 'mission', id: 'msn-1' }]), true);
  assert.equal(map.isUserAuthoredOnly([{ kind: 'mission', id: 'msn-1' }, { kind: 'evidence', id: 'e1' }]), false);
  assert.equal(map.isUserAuthoredOnly([]), false);
  assert.deepEqual(map.missionBasis('msn-1'), [{ kind: 'mission', id: 'msn-1' }]);
});

test('evidence basis uses the stored title and falls back to the source identifiers', () => {
  const rec = { id: 'ev1', revision: 2, state: { source_system: 'LIMS', source_record_id: 'F-2408-titer', site_id: 'NF1', metadata: { title: 'SYNTHETIC LIMS F-2408-titer', synthetic: true } } };
  const bare = { id: 'ev2', revision: 1, state: { source_system: 'MES', source_record_id: 'feed-log' } };
  const titles = map.evidenceTitles([rec, bare]);
  assert.equal(map.basisLabel({ kind: 'evidence', id: 'ev1', revision: 2 }, titles), 'SYNTHETIC LIMS F-2408-titer · revision 2');
  assert.equal(map.basisLabel({ kind: 'evidence', id: 'ev2' }, titles), 'MES feed-log');
  assert.equal(map.basisLabel({ kind: 'evidence', id: 'unknown' }, titles), 'Evidence unknown');
  assert.deepEqual(map.evidenceBasis(rec), { kind: 'evidence', id: 'ev1', revision: 2, site_id: 'NF1' });
  assert.deepEqual(map.evidenceBasis(bare), { kind: 'evidence', id: 'ev2', revision: 1 });
});

test('high and critical risk need re-authentication; outcomes only after approval or delivery', () => {
  assert.equal(map.needsReauthentication('high'), true);
  assert.equal(map.needsReauthentication('critical'), true);
  assert.equal(map.needsReauthentication('medium'), false);
  assert.equal(map.canRecordOutcome(proposal()), false);
  assert.equal(map.canRecordOutcome(proposal({ status: 'approved' })), true);
  assert.equal(map.canRecordOutcome(proposal({ status: 'approved', execution_status: 'delivered' })), true);
  assert.equal(map.canRecordOutcome(proposal({ status: 'rejected' })), false);
});

test('missions map to display work items without inventing state', () => {
  const m = map.missionDisplay({ mission_id: 'msn-1', objective: 'Why is titer low?', owner_id: 'priya', scope: { site_ids: ['NF1'] }, constraints: ['a'], notes: [{ note_id: 'n', body: 'b', author: 'priya', at: 'x' }], corrections: [], pending_decisions: [{ decision_id: 'd1', question: 'q', options: [], decider_role: 'qa', status: 'pending' }, { decision_id: 'd2', question: 'q', options: [], decider_role: 'qa', status: 'answered' }], obligations: [], status: 'paused_budget', created_at: '2026-10-23T00:00:00+00:00', revision: 3 });
  assert.equal(m.goal, 'Why is titer low?');
  assert.equal(m.statusLabel, 'Paused — budget');
  assert.equal(m.siteLabel, 'NF1');
  assert.equal(m.noteCount, 1);
  assert.equal(m.pendingDecisionCount, 1);
  assert.equal(map.missionDisplay({ mission_id: 'x', objective: 'y', owner_id: 'z', scope: {}, constraints: [], notes: [], corrections: [], pending_decisions: [], obligations: [], status: 'active', created_at: 'c', revision: 1 }).siteLabel, 'No site scope');
  assert.equal(map.authLabel('development_headers'), 'Development sign-in');
  assert.equal(map.authLabel('oidc'), 'SSO');
  assert.equal(map.initials('priya'), 'P');
  assert.equal(map.initials('priya.raman'), 'PR');
});

test('a corrupt or unusable saved connection decodes to sample mode and is flagged', () => {
  const bad = ['{', 'null', '[]', '"connected"', '{"mode":"connected"}', '{"mode":"other","tenant":"a","actor":"b"}', '{"mode":"connected","tenant":"","actor":"b"}', '{"mode":"connected","tenant":"a\\nX-Evil: 1","actor":"b"}', '{"mode":"connected","tenant":"a","actor":5}', ''];
  for (const raw of bad) {
    const loaded = conn.decodeConnection(raw);
    assert.equal(loaded.connection.mode, 'sample', raw);
    assert.equal(loaded.corrupt, true, raw);
  }
  const missing = conn.decodeConnection(null);
  assert.equal(missing.connection.mode, 'sample');
  assert.equal(missing.corrupt, false);
  assert.equal(missing.connection.tenant, 'demo-northfield');
  assert.equal(missing.connection.actor, 'priya');
});

test('a valid connection round-trips through its stored form', () => {
  const chosen = { mode: 'connected', tenant: 'demo-northfield', actor: 'quinn' };
  const loaded = conn.decodeConnection(conn.encodeConnection(chosen));
  assert.deepEqual(loaded.connection, chosen);
  assert.equal(loaded.corrupt, false);
  assert.equal(conn.CONNECTION_KEY, 'manufacturing-os:connection:v1');
});

test('reading a corrupt saved connection never overwrites it', () => {
  const writes = [];
  global.localStorage = { getItem: () => '{not json', setItem: (...args) => writes.push(args), removeItem: (...args) => writes.push(args) };
  const loaded = conn.loadConnection();
  assert.equal(loaded.connection.mode, 'sample');
  assert.equal(loaded.corrupt, true);
  assert.deepEqual(writes, []);
  global.localStorage = { getItem: () => { throw new Error('blocked'); } };
  assert.equal(conn.loadConnection().connection.mode, 'sample');
  delete global.localStorage;
});

test('server errors become readable messages', () => {
  assert.equal(client.describeError(403, { error: 'forbidden', detail: 'role qa not held' }), 'Not permitted: role qa not held');
  assert.equal(client.describeError(409, { error: 'conflict', detail: 'proposal at revision 4' }), 'This changed since you loaded it. Refresh and review the current version.');
  assert.equal(client.describeError(400, { error: 'invalid', detail: 'proposal is approved' }), 'proposal is approved');
  assert.equal(client.describeError(422, { detail: [{ loc: ['body', 'objective'], msg: 'String should have at least 3 characters' }] }), 'objective: String should have at least 3 characters');
  assert.equal(client.describeError(404, { error: 'not_found', detail: 'mission x' }), 'Not found: mission x');
  assert.match(client.describeError(500, null), /could not complete/);
  assert.equal(client.describeError(403, null), 'Not permitted: this action is not allowed for you');
});

test('the client sends tenant and actor headers, an idempotency key on POSTs, and never a role', async () => {
  const calls = [];
  global.fetch = async (url, init) => { calls.push({ url, init }); return { ok: true, status: 200, json: async () => ({ items: [] }) }; };
  const c = client.createClient({ tenant: 'demo-northfield', actor: 'priya' });
  await c.listMissions();
  await c.createMission({ objective: 'Find out why', owner_id: 'priya', scope: { site_ids: ['NF1'] } });
  await c.createMission({ objective: 'Find out why', owner_id: 'priya', scope: { site_ids: ['NF1'] } }, 'fixed-key-12345');
  assert.equal(calls[0].url, '/v1/missions');
  assert.equal(calls[0].init.headers['X-Tenant-Id'], 'demo-northfield');
  assert.equal(calls[0].init.headers['X-Actor-Id'], 'priya');
  assert.equal(calls[0].init.headers['Idempotency-Key'], undefined);
  assert.ok(calls[1].init.headers['Idempotency-Key'].length >= 8);
  assert.equal(calls[2].init.headers['Idempotency-Key'], 'fixed-key-12345');
  for (const call of calls) assert.equal(Object.keys(call.init.headers).some((k) => /role/i.test(k)), false);
  global.fetch = async () => { throw new TypeError('network'); };
  await assert.rejects(() => c.me(), /Could not reach the server/);
  delete global.fetch;
});
