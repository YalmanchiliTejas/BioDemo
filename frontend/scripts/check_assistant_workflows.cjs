/* Local UI contract: intercepts every API request; no inference or live writes.
 * PLAYWRIGHT_MODULE=/path/to/playwright node scripts/check_assistant_workflows.cjs
 */
const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.ASSISTANT_WORKFLOWS_PREVIEW || 'http://127.0.0.1:5186';
const clone = value => JSON.parse(JSON.stringify(value));
const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; };
const turn = (id, status = 'completed') => ({ id, user_text: `Review ${id}`, status, reply: status === 'completed' ? `Saved answer ${id}` : null,
  questions: [], issues: [], artifacts: [], gateway_runs: [] });
const thread = id => ({ id, revision: 1, title: `Workflow ${id}`, site_id: 'NF1', turn_ids: [`${id}-1`], demo_enabled: false,
  source_ids: [], dataset_ids: ['delivery-1'], mission_status: 'active', turns: [turn(`${id}-1`)] });
const operations = [
  ['find_records', 'Find records', false], ['select_evidence', 'Select evidence', false], ['reconcile', 'Reconcile values', true],
  ['compare', 'Compare batches', true], ['check_gaps', 'Check gaps', true], ['trace_impact', 'Trace impact', false],
  ['prepare_review', 'Prepare review', false], ['review_changes', 'Review changes', false], ['suggest_causes', 'Suggest causes to check', false],
].map(([id, title, requires_dataset]) => ({ id, title, requires_dataset, description: `Run ${title.toLowerCase()} on authorized sources.` }));
const result = { id: 'result-1', operation: 'check_gaps', task_status: 'needs_information', site_id: 'NF1', owner_id: 'fixture-user',
  summary: 'One expected sample is missing.', data: { gaps: [{ batch: 'B-01', parameter: 'pH', time_h: 12, reason: 'missing sample' }] },
  issues: [{ code: 'coverage', message: 'Review the missing 12 hour sample.' }], source_refs: [{ kind: 'evidence', id: 'delivery-1', revision: 3 }],
  elapsed_seconds: 0.25, model_calls: 0, status: 'current', decision_model_calls: 0, decisions: [], template_version: 'fixture',
  timing: { phases: { authorize: 0.01, retrieve: 0.14, calculate: 0.05 }, seconds: 0.25, target_seconds: 10, within_target: true } };
// Four measured pairs shown two at a time: the summary and the series stay complete on every page.
const pairs = [0, 12, 24, 36].map(time_h => ({ parameter: 'pH', left_batch: 'B-01', right_batch: 'B-02', time_h, left_value: 7, right_value: 7 - time_h / 100, difference: -time_h / 100, unit: 'pH' }));
const compared = task => ({ ...result, id: `compare-${task.offset}`, operation: 'compare', task_status: 'needs_information', summary: 'Compared 4 measured pairs. Uses values still in review.', task,
  evidence_state: 'provisional', elapsed_seconds: 14.21, timing: { ...result.timing, seconds: 14.21, within_target: false }, decision_model_calls: 1,
  decisions: [{ task: 'field_meaning', status: 'completed', reason: '', model: 'fixture-decision-model', policy_version: 'fixture', run_id: 'run-fixture', latency_ms: 80,
    answers: [{ question: 'parameter', status: 'advisory', value: 'pH', probability: 0.7149, reason: 'no calibration for this task' }] }],
  issues: [{ code: 'parameter_needs_confirmation', requested: 'acidity', suggested: 'pH', probability: 0.7149, message: '"acidity" is not a recorded parameter name.' }],
  data: { measurements: pairs.slice(task.offset, task.offset + 2).map(({ time_h, left_value }) => ({ batch: 'B-01', parameter: 'pH', time_h, value: left_value, unit: 'pH' })), measurement_count: 8, measurements_offset: task.offset,
    next_offset: task.offset + 2, series_complete: true, truncated: false, series: ['B-01', 'B-02'].map(batch => ({ batch, parameter: 'pH', unit: 'pH', n: 4, min: 6.64, max: 7, first_time_h: 0, last_time_h: 36, points: [[0, 7], [36, 6.64]] })),
    verification: [{ dataset_id: 'delivery-3', state: 'provisional', values_still_in_review_used: 3, open_checks: 2, rejected_values_excluded: 1 }],
    comparisons: pairs.slice(task.offset, task.offset + 2), comparison_count: 4, comparisons_offset: task.offset, comparisons_next_offset: task.offset + 2 < 4 ? task.offset + 2 : null, unmatched_counts: { 'B-01': 1, 'B-02': 0 },
    comparison_summary: [{ parameter: 'pH', unit: 'pH', left_batch: 'B-01', right_batch: 'B-02', matched_times: 4, first_time_h: 0, last_time_h: 36, mean_difference: -0.18123456,
      largest_difference: { time_h: 36, difference: -0.36, left_value: 7, right_value: 6.64 }, difference_definition: 'right batch minus left batch, at the same measured elapsed time' }] } });
const causes = { ...result, id: 'causes-1', operation: 'suggest_causes', summary: 'Screened 2 linked records: 1 hypotheses to check, 1 weakened by timing. No cause is established.', issues: [], task_status: 'completed',
  data: { causal_status: 'hypotheses_only', causal_claim_supported: false, establishing_a_cause: 'A cause is established only by the case review that closes the investigation.',
    subject: { record_id: 'signal-1', kind: 'deviation_signal', label: 'High signal · pH low', time: '2026-11-10T08:00:00Z', time_basis: 'first_at' }, candidate_factors: 2,
    chronology: [{ id: 'F1', record: { kind: 'evidence', id: 'ev-1', revision: 1 }, label: 'Base feed lot L-77', time: '2026-11-09T08:00:00Z', time_basis: 'event_time', link: 'identifier in an ID field of both records', shared_identifiers: ['L-77'], timing: 'recorded_before_or_at_the_subject', screening: 'not_ruled_out' },
      { id: 'F2', record: { kind: 'case', id: 'case-2', revision: 1 }, label: 'Probe replaced', time: '2026-11-11T08:00:00Z', time_basis: 'opened_at', link: 'identifier mentioned in free text; unconfirmed', shared_identifiers: ['B-01'], timing: 'recorded_after_the_subject', screening: 'weakened_by_timing' }],
    hypotheses: [{ id: 'H1', kind: 'hypothesis', factor_id: 'F1', statement: 'Base feed lot L-77 may have contributed.', supported_by: ['Shares L-77 with the subject.'], not_established: ['That the factor was physically involved.'], next_check: 'Confirm the lot usage window.' }],
    contrary_evidence: [{ factor_id: 'F2', finding: 'Its recorded time is after the subject\'s recorded time.', caveat: 'Times are opened_at and first_at: confirm they are occurrence times.' }],
    precedents: [{ case_id: 'NC-7', status: 'closed', recorded_root_cause: 'Base pump calibration drift', cause_status: 'as recorded at closure', similarity: { shared_identifiers: ['L-77'], word_overlap: 0.4 }, label: 'NC-7 pH excursion' }],
    precedent_reuse: 'Reusing a prior investigation still requires the investigation owner\'s approval.', unknowns: ['Whether records you cannot access hold other candidates.'], coverage: 'Linked records at this site only.', next_step: 'No hypothesis here is a finding.' } };
const trendSeries = ['B-01', 'B-02'].map((batch, index) => ({ key: `run-${index + 1}:${batch}`, batch, run_id: `run-${index + 1}`, cmo: 'Fixture CDMO', delivery_name: `Delivery ${index + 1}`, completed_at: '2026-11-14T12:00:00Z', delivery_verified: true, time_basis: 'recorded_hours', unit: 'pH',
  points: [[0, 7, `${batch}-0`], [12, 6.8, `${batch}-12`]], points_total: 2, points_without_time: 0, sampled_every: 1,
  summary: { n: 2, mean: 6.9, min: { time_h: 12, value: 6.8, id: `${batch}-12` }, max: { time_h: 0, value: 7, id: `${batch}-0` }, first: { time_h: 0, value: 7, id: `${batch}-0` }, last: { time_h: 12, value: 6.8, id: `${batch}-12` } } }));
const trendData = { parameters: [{ id: 'pH', units: ['pH'], batches: 2, values: 4 }], batches: trendSeries, deliveries: 2, parameter: 'pH', series: trendSeries, standouts: { from_sampled_profiles: false } };

async function fixture(browser, { running = false, long = false, artifacts = false, unpublished = false, unverified = false, publicationFails = false, chatSite = 'NF1', overlapping = false, failedRoutine = false, decisionModel = false } = {}) {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage(); page.setDefaultTimeout(12000);
  const errors = [], unexpected = [], posts = [], threads = { A: thread('A'), B: thread('B') }, routines = [];
  threads.A.site_id = chatSite;
  if (long) threads.A.turns = Array.from({ length: 22 }, (_, i) => turn(`history-${i}`));
  if (running) threads.A.turns.at(-1).status = 'running';
  if (artifacts) {
    routines.push({ id: 'routine-1', revision: 1, site_id: 'NF1', name: 'Proposed evidence check', description: 'Review event evidence', status: 'draft', triggers: ['deviation'], every_minutes: null, max_runs: 3, runs_admitted: 0, thread_id: 'A', updated_at: '2026-11-14T12:00:00Z', runs: [],
      task: { operation: 'check_gaps', site_id: 'NF1', query: '', kinds: [], record_refs: [{ kind: 'evidence', id: 'delivery-1', revision: 3, site_id: 'NF1' }, { kind: 'case', id: 'case-keep', revision: 2, site_id: 'NF1' }], dataset_ids: ['delivery-1'], series: [{ dataset_id: 'delivery-1', batch: 'B-01' }], batches: ['B-01'], parameter: 'pH', target_unit: null, expected_parameters: ['pH'], expected_document_kinds: [], expected_times: [12], process_stage: null, effective_at: null, record_id: null, record_kind: null, limit: 50 } });
    threads.A.turns[0].artifacts = [{ id: 'routine-1', kind: 'assistant_routine', title: 'Proposed evidence check' }, { id: 'result-1', kind: 'workspace_task_result', title: 'Saved task result' }];
  }
  if (failedRoutine) Object.assign(routines[0], { status: 'active', latest_result: result, runs: [{ id: 'earlier-run', status: 'completed', result_id: 'result-1', finished_at: '2026-11-14T12:00:00Z' }, { id: 'failed-run', status: 'failed', issues: [{ code: 'source_limit_exceeded', message: 'PRIVATE SOURCE VALUE 9173' }], finished_at: '2026-11-14T13:00:00Z' }] });
  let messageGate;
  let datasetGate;
  let sourceRevoked = false;
  const datasets = [{ id: 'delivery-1', run_id: 'run-1', revision: 3, site_id: 'NF1', status: 'current', cmo: 'Fixture CDMO', delivery_name: 'Verified delivery', measurements: 18, batches: ['B-01'], parameters: ['pH'], verification: 'verified' },
    ...(!unpublished ? [{ id: 'delivery-2', run_id: 'run-2', revision: 3, site_id: 'NF1', status: 'current', cmo: 'Fixture CDMO', delivery_name: 'Second verified delivery', measurements: 18, batches: ['B-02'], parameters: ['pH'], verification: 'verified' }] : [])];
  // Listed only when the page asks for deliveries still in review.
  const inReview = { id: 'delivery-3', run_id: 'run-3', revision: 1, site_id: 'NF1', status: 'current', cmo: 'Fixture CDMO', delivery_name: 'Delivery in review', measurements: 12, batches: ['B-01', 'B-02'], parameters: ['pH', 'Glucose'],
    verification: 'provisional', review: { pending_values: 12, rejected_values: 1, open_issues: 3, open_issue_counts: { unit: 3 } } };
  page.on('pageerror', error => errors.push(error.message));
  await page.addInitScript(() => {
    localStorage.setItem('sievance.local-session.v1', JSON.stringify({ tenant_id: 'workflow-fixture', actor_id: 'fixture-user', email: 'fixture@example.test', name: 'UI fixture' }));
    localStorage.setItem('sievance.organization:fixture-user', 'workflow-fixture');
    localStorage.setItem('biodemo.engineering.conversation.v1:fixture-user:workflow-fixture', 'A');
  });
  const headers = { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': '*', 'Access-Control-Allow-Methods': 'GET,POST,OPTIONS' };
  const respond = (route, data, status = 200) => route.fulfill({ status, headers, body: JSON.stringify(data) });
  await page.route('**/*', async route => {
    const req = route.request(), url = new URL(req.url()), path = url.pathname;
    if (!path.startsWith('/v1/') && !path.startsWith('/api/')) return route.continue();
    if (req.method() === 'OPTIONS') return route.fulfill({ status: 204, headers, body: '' });
    const body = req.method() === 'POST' ? req.postDataJSON() : null;
    if (body) posts.push({ path, body });
    if (path === '/v1/account') return respond(route, { actor_id: 'fixture-user', organizations: [{ id: 'workflow-fixture', name: 'Local UI fixture', roles: ['admin'], site_ids: ['NF1', 'NF2'], onboarding_complete: true }] });
    if (path === '/v1/me') return respond(route, { tenant_id: 'workflow-fixture', actor_id: 'fixture-user', roles: ['admin'], auth_mode: 'development' });
    if (path === '/v1/notifications') return respond(route, { items: [], unread: 0 });
    if (path === '/v1/demo/workspace') return respond(route, { detail: 'No demo workspace in this fixture' }, 404);
    if (path === '/v1/specifications') return respond(route, { specifications: [] });
    if (path === '/api/cmo-ingestion/trends') { const data = clone(trendData); if (unverified) data.series[1].delivery_verified = false; if (overlapping) { data.series = trendSeries.flatMap(series => ['A', 'B'].map(batch => ({ ...series, key: `${series.run_id}:${batch}`, batch }))); data.batches = data.series; data.parameters[0].batches = 4; } return respond(route, data); }
    if (path === '/v1/process-model/conversations') {
      if (body) { threads.C = { ...thread('C'), site_id: body.site_id, turns: [], turn_ids: [], dataset_ids: [] }; return respond(route, threads.C); }
      return respond(route, { conversations: Object.values(threads).map(({ id, title }) => ({ id, title })) });
    }
    const conversation = path.match(/^\/v1\/process-model\/conversations\/([ABC])(?:\/(messages))?$/);
    if (conversation) {
      const id = conversation[1];
      if (conversation[2] === 'messages') {
        assert(messageGate, 'Unexpected chat send'); messageGate.entered.resolve(); await messageGate.release.promise;
        threads[id].turns.push({ ...turn(`${id}-sent`), user_text: body.text }); threads[id].revision++;
      }
      return respond(route, clone(threads[id]));
    }
    if (path === '/v1/workspace-tasks/catalog') return respond(route, { operations, template_version: 'fixture', decision_model: decisionModel
      ? { enabled: true, model: 'fixture-decision-model', calibrated_tasks: {}, acceptance: 'Applied only where calibrated.', configuration_issue: null } : { enabled: false } });
    if (path === '/v1/workspace-tasks/route') {
      const suggested_task = { operation: 'compare', dataset_ids: ['delivery-3'], parameter: 'pH', batches: ['B-01', 'B-02'] };
      if (body.text.includes('?')) return respond(route, { route: 'assistant', basis: 'host_rules', task: null, suggested_task: null, reason: 'the request asks a question or for reasoning; that is the assistant\'s work', decisions: [] });
      if (body.text.includes('acidity')) return respond(route, { route: 'assistant', basis: 'decision_model', task: null, suggested_task, reason: 'suggested by the decision model, not applied: no calibration for this task', decisions: [] });
      return respond(route, { route: 'direct', basis: 'host_rules', suggested_task: null, reason: 'every word of the request matched one task, one delivery and recorded names', decisions: [],
        task: { operation: 'compare', site_id: 'NF1', query: '', kinds: [], record_refs: [], dataset_ids: body.dataset_ids, series: [], batches: ['B-01', 'B-02'], parameter: 'pH', target_unit: null, expected_parameters: [], expected_document_kinds: [], expected_times: [], process_stage: null, effective_at: null, record_id: null, record_kind: null, limit: 2, offset: 0, include_unverified: false, use_decision_model: true } });
    }
    if (path === '/v1/workspace-tasks/run') return respond(route, body.operation === 'compare' ? compared(body) : body.operation === 'suggest_causes' ? causes : result);
    if (path === '/v1/workspace-tasks/results/result-1') return respond(route, result);
    const saved = path.match(/^\/v1\/workspace-tasks\/results\/(?:compare-(\d+)|causes-1)$/);
    if (saved) return respond(route, saved[1] ? compared({ operation: 'compare', site_id: 'NF1', dataset_ids: ['delivery-3'], limit: 2, offset: Number(saved[1]) }) : causes);
    if (path === '/v1/records/evidence/delivery-1') return sourceRevoked ? respond(route, { detail: 'Source access revoked' }, 403) : respond(route, { id: 'delivery-1', revision: 4, state: { site_id: 'NF1', source_system: 'cmo-verified-delivery', source_record_id: 'run-1', metadata: { classification: 'verified_cmo_dataset' } }, audit: [] });
    if (path === '/v1/assistant-routines') {
      if (body) { const routine = { ...body, id: 'routine-1', revision: 1, site_id: body.task.site_id, status: 'draft', runs_admitted: 0, thread_id: 'A', updated_at: '2026-11-14T12:00:00Z', runs: [] }; routines.push(routine); return respond(route, routine); }
      return respond(route, { routines });
    }
    const routinePath = path.match(/^\/v1\/assistant-routines\/([^/]+)(?:\/(activate|pause|update|run))?$/);
    if (routinePath) {
      const routine = routines.find(r => r.id === routinePath[1]); assert(routine, 'Unknown routine');
      const action = routinePath[2];
      if (action === 'run') { routine.latest_result = result; routine.revision += 2; return respond(route, result); }
      if (action) { assert.equal(body.expected_revision, routine.revision, 'Use current definition revision'); if (action === 'update') Object.assign(routine, body, { status: 'draft' }); else routine.status = action === 'activate' ? 'active' : 'paused'; routine.revision++; }
      return respond(route, clone(routine));
    }
    if (path === '/v1/cmo-datasets') {
      if (body) { assert.equal(body.run_id, 'run-2'); if (publicationFails) return respond(route, { detail: 'Source verification changed; review the delivery again' }, 409); const published = { id: 'new-delivery-2', run_id: body.run_id, revision: 7, site_id: 'NF1', status: 'current', cmo: 'Fixture CDMO', delivery_name: 'Published selected delivery', measurements: 18, batches: ['B-02'], parameters: ['pH'], verification: 'verified' }; datasets.push(published); return respond(route, published); }
      if (datasetGate) { const gate = datasetGate; datasetGate = null; gate.entered.resolve(); await gate.release.promise; }
      return respond(route, { datasets: url.searchParams.get('include_provisional') === 'true' ? [...datasets, inReview] : datasets });
    }
    unexpected.push(`${req.method()} ${path}`); return respond(route, { detail: 'Unexpected fixture request' }, 404);
  });
  await page.goto(base + '/home/', { waitUntil: 'domcontentloaded', timeout: 60000 });
  const chat = page.getByTestId('engineering-chat'); await chat.getByText(long ? 'Review history-0' : 'Review A-1', { exact: true }).waitFor();
  const composer = chat.getByLabel('Describe your process problem or follow up', { exact: true });
  const open = async id => {
    const nav = chat.getByRole('navigation', { name: 'Conversation history' });
    if (!(await nav.isVisible())) await chat.getByRole('button', { name: 'Conversation history', exact: true }).click();
    await nav.getByRole('button', { name: `Workflow ${id}`, exact: true }).click();
    await chat.getByText(`Review ${id}-1`, { exact: true }).waitFor();
  };
  return { context, page, chat, composer, threads, posts, open, revokeSource: () => { sourceRevoked = true; }, gate: () => (messageGate = { entered: deferred(), release: deferred() }), datasetGate: () => (datasetGate = { entered: deferred(), release: deferred() }),
    verify: () => { assert.deepEqual(errors, []); assert.deepEqual(unexpected, []); } };
}

const scenarios = {
  async draft(browser) {
    const f = await fixture(browser);
    try {
      await f.composer.fill('First request'); const gate = f.gate(); await f.chat.getByRole('button', { name: 'Send message', exact: true }).click(); await gate.entered.promise;
      await f.composer.fill('Keep my next question'); gate.release.resolve(); await f.chat.getByText('Saved answer A-sent', { exact: true }).waitFor();
      assert.equal(await f.composer.inputValue(), 'Keep my next question', 'Late send acknowledgment must preserve a newer draft');
      await f.open('B'); await f.composer.fill('Separate B draft'); await f.open('A'); assert.equal(await f.composer.inputValue(), 'Keep my next question', 'Drafts belong to conversations');
      await f.page.reload(); await f.chat.getByText('Review A-1', { exact: true }).waitFor(); assert.equal(await f.composer.inputValue(), 'Keep my next question', 'Draft survives reload in this account'); f.verify();
    } finally { await f.context.close(); }
  },
  async scroll(browser) {
    const f = await fixture(browser, { running: true, long: true });
    try {
      const log = f.chat.getByRole('log');
      const scrollTop = () => log.evaluate(node => { let parent = node.parentElement; while (parent && !/(auto|scroll)/.test(getComputedStyle(parent).overflowY)) parent = parent.parentElement; return (parent || document.scrollingElement).scrollTop; });
      await log.evaluate(node => { let parent = node.parentElement; while (parent && !/(auto|scroll)/.test(getComputedStyle(parent).overflowY)) parent = parent.parentElement; (parent || document.scrollingElement).scrollTop = 0; });
      f.threads.A.turns.at(-1).status = 'completed'; f.threads.A.turns.at(-1).reply = 'Latest result arrived';
      await f.chat.getByText('Latest result arrived', { exact: true }).waitFor();
      assert((await scrollTop()) < 30, 'A completion must not pull a reader away from older messages'); f.verify();
    } finally { await f.context.close(); }
  },
  async work(browser) {
    const f = await fixture(browser);
    try {
      await f.composer.fill('Chat draft stays here'); await f.chat.getByRole('button', { name: 'Work', exact: true }).click();
      await f.chat.getByLabel('Task', { exact: true }).selectOption('check_gaps');
      await f.chat.getByRole('group', { name: 'Expected parameters', exact: true }).getByRole('checkbox', { name: 'pH', exact: true }).check();
      await f.chat.getByRole('button', { name: 'Run task', exact: true }).click();
      await f.chat.getByText('One expected sample is missing.', { exact: true }).waitFor();
      const sent = f.posts.find(p => p.path === '/v1/workspace-tasks/run').body;
      assert.equal(sent.site_id, 'NF1'); assert.deepEqual(sent.dataset_ids, ['delivery-1']); assert.deepEqual(sent.expected_parameters, ['pH']);
      assert.equal(sent.offset, 0); assert.equal(sent.include_unverified, false, 'Values still in review are never included by default'); assert.equal(sent.use_decision_model, true);
      await f.chat.getByText('Answered in 0.25 s', { exact: true }).waitFor();
      await f.chat.getByRole('table').getByText('B-01', { exact: true }).waitFor();
      await f.chat.getByText('Sources · 1 references', { exact: true }).click();
      await f.chat.getByRole('button', { name: 'Inspect source delivery-1', exact: true }).click();
      await f.chat.getByText(/Current revision 4 differs from referenced revision 3/).waitFor();
      assert.equal(await f.chat.getByRole('link', { name: 'Open original delivery and source viewer' }).getAttribute('href'), '/cmo/?run=run-1');
      if (process.argv.includes('--screenshots')) { await f.chat.getByTestId('task-result').scrollIntoViewIfNeeded(); await f.page.screenshot({ path: '/private/tmp/direct-assistant-work-result.png' }); }
      await f.chat.getByRole('button', { name: 'Inspect source delivery-1', exact: true }).click(); f.revokeSource();
      await f.chat.getByRole('button', { name: 'Inspect source delivery-1', exact: true }).click();
      await f.chat.getByRole('alert').filter({ hasText: 'Source access revoked' }).waitFor();
      assert.equal(await f.chat.getByRole('link', { name: 'Open original delivery and source viewer' }).count(), 0, 'A denied refresh must not retain the previous source view');
      await f.chat.getByRole('button', { name: 'Chat', exact: true }).click(); assert.equal(await f.composer.inputValue(), 'Chat draft stays here'); f.verify();
      await f.page.reload(); await f.chat.getByRole('button', { name: 'Work', exact: true }).click();
      await f.chat.getByText('One expected sample is missing.', { exact: true }).waitFor();
      assert.equal(f.posts.filter(p => p.path === '/v1/workspace-tasks/run').length, 1, 'Reload retrieves the saved result without rerunning the task');
    } finally { await f.context.close(); }
  },
  async routine(browser) {
    const f = await fixture(browser);
    try {
      await f.chat.getByRole('button', { name: 'Routines', exact: true }).click();
      await f.chat.getByRole('button', { name: 'New routine', exact: true }).click();
      await f.chat.getByLabel('Routine name', { exact: true }).fill('Early batch review');
      await f.chat.getByLabel('Task', { exact: true }).selectOption('check_gaps');
      await f.chat.getByRole('group', { name: 'Expected parameters', exact: true }).getByRole('checkbox', { name: 'pH', exact: true }).check();
      await f.chat.getByLabel('Early warnings and deviations', { exact: true }).check();
      await f.chat.getByRole('button', { name: 'Save draft', exact: true }).click();
      await f.chat.getByRole('heading', { name: 'Early batch review', exact: true }).waitFor();
      assert.equal(f.posts.filter(p => /\/activate$/.test(p.path)).length, 0, 'Saving a draft must not authorize standing work');
      await f.chat.getByRole('button', { name: 'Review activation', exact: true }).click();
      assert(await f.chat.getByRole('button', { name: 'Activate routine', exact: true }).isDisabled());
      await f.chat.getByLabel(/I authorize this routine/).check(); await f.chat.getByRole('button', { name: 'Activate routine', exact: true }).click();
      await f.chat.getByRole('button', { name: 'Pause routine', exact: true }).click();
      await f.chat.getByText('Paused', { exact: true }).waitFor();
      await f.chat.getByRole('button', { name: 'Run once', exact: true }).click();
      await f.chat.getByRole('button', { name: 'Run routine', exact: true }).click();
      await f.chat.getByText('One expected sample is missing.', { exact: true }).waitFor();
      assert.equal(f.posts.find(p => /\/activate$/.test(p.path)).body.acknowledge_inference, true);
      const run = f.posts.find(p => /\/run$/.test(p.path)).body; assert(!('operation' in run.parameters)); assert(!('site_id' in run.parameters));
      await f.chat.getByRole('button', { name: 'Edit routine', exact: true }).click();
      await f.chat.getByLabel('Routine name', { exact: true }).fill('Reviewed batch checks'); await f.chat.getByRole('button', { name: 'Save draft', exact: true }).click();
      await f.chat.getByRole('heading', { name: 'Reviewed batch checks', exact: true }).waitFor(); f.verify();
    } finally { await f.context.close(); }
  },
  async trends(browser) {
    const f = await fixture(browser);
    try {
      await f.page.goto(base + '/trends/', { waitUntil: 'domcontentloaded' });
      await f.page.getByRole('button', { name: 'Check gaps', exact: true }).click();
      const work = f.chat.getByRole('region', { name: 'Direct work', exact: true });
      await work.getByLabel('Task', { exact: true }).waitFor();
      assert.equal(await work.getByLabel('Task', { exact: true }).inputValue(), 'check_gaps');
      assert.equal(await work.getByLabel('Parameter', { exact: true }).inputValue(), 'pH');
      const batch = work.getByRole('group', { name: 'Batches', exact: true }).getByRole('checkbox', { name: 'B-02', exact: true });
      assert(await batch.isChecked(), 'The batch chosen on the chart is ticked'); assert(await batch.isDisabled(), 'Exact chart selections lock the batch list');
      await work.getByRole('button', { name: 'Run task', exact: true }).click();
      await f.chat.getByText('One expected sample is missing.', { exact: true }).waitFor();
      const sent = f.posts.find(p => p.path === '/v1/workspace-tasks/run').body;
      assert.deepEqual(sent.dataset_ids, ['delivery-2']); assert.deepEqual(sent.batches, ['B-02']); assert.equal(sent.parameter, 'pH');
      assert.equal(sent.site_id, 'NF1'); f.verify();
    } finally { await f.context.close(); }
  },
  async typed(browser) {
    const f = await fixture(browser, { decisionModel: true });
    try {
      await f.chat.getByRole('button', { name: 'Work', exact: true }).click();
      const work = f.chat.getByRole('region', { name: 'Direct work', exact: true }), request = work.getByLabel('Type what you need', { exact: true });
      const runs = () => f.posts.filter(p => p.path === '/v1/workspace-tasks/run');
      await work.getByText(/Decision model fixture-decision-model is on for matching names and ordering results/).waitFor();
      // A question is never run: the reason is shown and the person chooses the assistant.
      await request.fill('Why did pH drop in B-02?'); await work.getByRole('button', { name: 'Run', exact: true }).click();
      await work.getByText(/Not run directly: the request asks a question or for reasoning/).waitFor();
      assert.deepEqual(f.posts.find(p => p.path === '/v1/workspace-tasks/route').body, { site_id: 'NF1', text: 'Why did pH drop in B-02?', dataset_ids: ['delivery-1'], include_unverified: false });
      assert.equal(await work.getByRole('button', { name: 'Use this selection', exact: true }).count(), 0); assert.equal(runs().length, 0, 'A request for reasoning runs nothing');
      // A suggestion fills the form and waits for the person.
      await request.fill('compare acidity between B-01 and B-02'); await work.getByRole('button', { name: 'Run', exact: true }).click();
      await work.getByText(/Suggested selection: Compare batches · pH · B-01, B-02 · Delivery in review/).waitFor();
      await work.getByRole('button', { name: 'Use this selection', exact: true }).click();
      assert.equal(await work.getByLabel('Task', { exact: true }).inputValue(), 'compare'); assert.equal(await work.getByLabel('Parameter', { exact: true }).inputValue(), 'pH');
      assert(await work.getByRole('checkbox', { name: 'Use delivery Delivery in review', exact: true }).isChecked());
      await work.getByText('12 values still in review · 3 open checks', { exact: true }).waitFor();
      const include = work.getByRole('checkbox', { name: 'Include values still in review', exact: true });
      assert.equal(await include.isChecked(), false, 'Unreviewed values are an explicit choice'); assert.equal(runs().length, 0, 'Using a suggestion runs nothing');
      await include.check(); await work.getByRole('button', { name: 'Run task', exact: true }).click();
      const card = work.getByTestId('task-result').first(); await card.getByText('Took 14.2 s · over the 10 s target', { exact: true }).waitFor();
      assert.equal(runs().at(-1).body.include_unverified, true); assert.deepEqual(runs().at(-1).body.dataset_ids, ['delivery-3']);
      await card.getByText('Uses values still in review', { exact: true }).waitFor();
      await card.getByText('Delivery in review: 3 values still in review used · 2 open checks · 1 rejected value left out', { exact: true }).waitFor();
      const summary = card.getByRole('table', { name: /Differences between batches/ });
      await summary.getByText('B-02 − B-01', { exact: true }).waitFor(); await summary.getByText(/-0\.36 pH at 36 h/).waitFor();
      await summary.getByText('-0.1812 pH', { exact: true }).waitFor(); await summary.getByText('B-02 6.64 · B-01 7 pH', { exact: true }).waitFor();
      await card.getByText('All 8 values are included.', { exact: true }).waitFor();
      assert(!(await card.getByRole('table', { name: /Values by batch and parameter/ }).innerText()).includes('[['), 'Series points are summarised, not dumped');
      await card.getByText(/^comparisons · rows 1 to 2 of 4$/i).waitFor();
      await card.getByText('Decision model: 1 suggestion', { exact: true }).click();
      await card.getByText(/suggestion only \(not calibrated for this task\)/).waitFor(); await card.getByText(/model probability 71.5%/).waitFor();
      await card.getByRole('button', { name: 'Show next rows', exact: true }).click(); await card.getByText(/^comparisons · rows 3 to 4 of 4$/i).waitFor();
      assert.equal(runs().at(-1).body.offset, 2); assert.equal(runs().at(-1).body.include_unverified, true, 'The next page reruns the same task');
      await summary.getByText('B-02 − B-01', { exact: true }).waitFor(); await card.getByText('Summaries above cover every row.', { exact: true }).waitFor();
      // A name the decision model only suggests is confirmed by the person, never applied silently.
      await work.getByLabel('Parameter', { exact: true }).selectOption(''); const before = runs().length;
      await card.getByText('Did you mean pH?', { exact: true }).waitFor(); await card.getByRole('button', { name: 'Use pH', exact: true }).click();
      assert.equal(await work.getByLabel('Parameter', { exact: true }).inputValue(), 'pH'); assert.equal(runs().length, before, 'Accepting a suggested name does not run the task');
      // Exactly one routine task runs straight away, and says why.
      const direct = f.page.waitForResponse(r => r.request().method() === 'POST' && new URL(r.url()).pathname === '/v1/workspace-tasks/run');
      await request.fill('compare pH between B-01 and B-02'); await work.getByRole('button', { name: 'Run', exact: true }).click();
      await work.getByText(/Ran directly: every word of the request matched one task/).waitFor(); await direct;
      assert.equal(runs().length, before + 1, 'One routine task runs once, straight away'); assert.equal(runs().at(-1).body.operation, 'compare'); assert.equal(runs().at(-1).body.include_unverified, false);
      assert.equal(await work.getByLabel('Task', { exact: true }).inputValue(), 'compare', 'The form shows what ran');
      if (process.argv.includes('--screenshots')) await f.page.screenshot({ path: '/private/tmp/direct-assistant-typed-request.png', fullPage: true });
      await request.fill('Why did pH drop in B-02?'); await work.getByRole('button', { name: 'Run', exact: true }).click();
      await work.getByRole('button', { name: 'Ask the assistant', exact: true }).click();
      await f.page.waitForFunction(() => document.querySelector('#engineering-message')?.value === 'Why did pH drop in B-02?');
      assert.equal(f.posts.filter(p => /\/messages$/.test(p.path)).length, 0, 'Handing over prepares a draft, without invoking reasoning'); f.verify();
    } finally { await f.context.close(); }
  },
  async causes(browser) {
    const f = await fixture(browser);
    try {
      await f.chat.getByRole('button', { name: 'Work', exact: true }).click();
      const work = f.chat.getByRole('region', { name: 'Direct work', exact: true });
      await work.getByLabel('Task', { exact: true }).selectOption('suggest_causes');
      await work.getByLabel('Record or identifier', { exact: true }).fill('signal-1'); await work.getByLabel('Record type', { exact: true }).selectOption('deviation_signal');
      await work.getByLabel('Description', { exact: true }).fill('pH dropped below the limit'); await work.getByRole('button', { name: 'Run task', exact: true }).click();
      const card = work.getByTestId('task-result').first(); await card.getByText('Hypotheses to check. No cause is established.', { exact: true }).waitFor();
      const sent = f.posts.find(p => p.path === '/v1/workspace-tasks/run').body;
      assert.equal(sent.record_id, 'signal-1'); assert.equal(sent.record_kind, 'deviation_signal'); assert.equal(sent.query, 'pH dropped below the limit');
      await card.getByRole('region', { name: 'Hypotheses', exact: true }).getByText('Base feed lot L-77 may have contributed.', { exact: true }).waitFor();
      await card.getByRole('region', { name: 'Weakened by timing', exact: true }).getByText('Probe replaced', { exact: true }).waitFor();
      await card.getByRole('region', { name: 'Timeline', exact: true }).getByText('Weakened by timing: recorded after the subject', { exact: true }).waitFor();
      await card.getByRole('region', { name: 'Similar closed cases', exact: true }).getByText(/Recorded root cause: Base pump calibration drift/).waitFor();
      await card.getByRole('region', { name: 'What was not checked', exact: true }).getByText('Whether records you cannot access hold other candidates.', { exact: true }).waitFor();
      const text = await card.innerText(); assert(!/opened_at|first_at|not_ruled_out|hypotheses_only/.test(text.split('Calculation and source record')[0]), 'The view uses plain words, not field names');
      assert.equal(await card.getByRole('table').count(), 0, 'Causes have a dedicated view, not generic tables');
      if (process.argv.includes('--screenshots')) await f.page.screenshot({ path: '/private/tmp/direct-assistant-causes.png', fullPage: true });
      await card.getByRole('button', { name: 'Continue in the assistant', exact: true }).click();
      await f.page.waitForFunction(() => document.querySelector('#engineering-message')?.value.includes('causes-1'));
      assert.equal(f.posts.filter(p => /\/messages$/.test(p.path)).length, 0); f.verify();
    } finally { await f.context.close(); }
  },
  async direct_turn(browser) {
    const f = await fixture(browser);
    try {
      // A reply the host calculated: one step, no model run, and the saved task result as its artifact.
      const step = { node_id: 'direct', title: 'Calculated from the records', task_kind: 'workspace_task', depends_on: [], status: 'completed', issues: [] };
      const timing = { answer_seconds: 0.42, model_calls: 0, path: 'direct', target_seconds: 10, within_target: true };
      f.threads.A.turns = [{ ...turn('direct'), reply: 'One expected sample is missing in B-01.', steps: [step], response_mode: 'direct_task', timing, artifacts: [{ id: 'result-1', kind: 'workspace_task_result', title: 'Saved task result' }],
        routing: { route: 'direct', basis: 'host_rules', reason: 'every word of the request matched one task, one delivery and recorded names', suggested_task: null, decisions: [] } },
        { ...turn('slow'), steps: [step], timing: { ...timing, answer_seconds: 184.2, path: 'assistant', within_target: false } }];
      await f.page.reload(); await f.chat.getByText('One expected sample is missing in B-01.', { exact: true }).waitFor();
      const turns = f.chat.getByTestId('conversation-turn');
      await turns.nth(0).getByText('Calculated directly from the records · no model wrote this answer', { exact: true }).waitFor();
      await turns.nth(0).getByText('· 1 step · 0.4 s', { exact: true }).waitFor(); await turns.nth(0).getByText('How I worked this out').click();
      await turns.nth(0).getByText(/Calculated directly: every word of the request matched one task/).waitFor();
      await turns.nth(0).getByTestId('task-result').getByText('Answered in 0.25 s', { exact: true }).waitFor();
      await turns.nth(1).getByText('· 184 s · over the 10 s target', { exact: true }).waitFor();
      assert.equal(await turns.nth(1).getByText(/no model wrote this answer/).count(), 0, 'Only host-calculated replies carry the label'); f.verify();
    } finally { await f.context.close(); }
  },
  async mobile(browser) {
    const f = await fixture(browser, { long: true });
    try {
      await f.page.setViewportSize({ width: 390, height: 844 });
      const box = await f.composer.boundingBox(); assert(box && box.y >= 0 && box.y + box.height <= 844, 'Composer remains visible on a narrow screen');
      await f.composer.fill('Mobile draft'); await f.chat.getByRole('button', { name: 'Work', exact: true }).click();
      await f.chat.getByLabel('Task', { exact: true }).waitFor();
      const overflow = await f.chat.evaluate(element => element.scrollWidth > element.clientWidth + 1); assert.equal(overflow, false, 'Assistant fits the mobile viewport');
      await f.chat.getByRole('button', { name: 'Chat', exact: true }).click(); assert.equal(await f.composer.inputValue(), 'Mobile draft'); f.verify();
    } finally { await f.context.close(); }
  },
  async publish(browser) {
    const f = await fixture(browser, { unpublished: true });
    try {
      await f.page.goto(base + '/trends/', { waitUntil: 'domcontentloaded' });
      await f.page.getByRole('button', { name: 'Check gaps', exact: true }).click();
      const work = f.chat.getByRole('region', { name: 'Direct work', exact: true });
      await work.getByRole('button', { name: 'Run task', exact: true }).click();
      await work.getByText('One expected sample is missing.', { exact: true }).waitFor();
      const publication = f.posts.find(p => p.path === '/v1/cmo-datasets'); assert.equal(publication.body.run_id, 'run-2'); assert.equal(publication.body.site_id, 'NF1');
      const sent = f.posts.find(p => p.path === '/v1/workspace-tasks/run').body;
      assert.deepEqual(sent.dataset_ids, ['new-delivery-2']); assert.deepEqual(sent.record_refs, [{ kind: 'evidence', id: 'new-delivery-2', revision: 7, site_id: 'NF1' }]); f.verify();
    } finally { await f.context.close(); }
  },
  async unverified(browser) {
    const f = await fixture(browser, { unpublished: true, unverified: true });
    try {
      await f.page.goto(base + '/trends/', { waitUntil: 'domcontentloaded' }); await f.page.getByRole('button', { name: 'Check gaps', exact: true }).click();
      await f.page.getByText(/selected deliveries still need source verification/).waitFor();
      assert.equal(f.posts.length, 0, 'Unverified sources must not be published or run'); f.verify();
    } finally { await f.context.close(); }
  },
  async selection_race(browser) {
    const f = await fixture(browser, { unpublished: true });
    try {
      await f.page.goto(base + '/trends/', { waitUntil: 'domcontentloaded' }); const gate = f.datasetGate();
      await f.page.getByRole('button', { name: 'Check gaps', exact: true }).click(); await gate.entered.promise;
      await f.page.getByRole('row').filter({ has: f.page.getByRole('checkbox', { name: 'Show batch B-01' }) }).click(); gate.release.resolve();
      await f.page.getByText(/Selection changed. Start the task again/).waitFor();
      assert.equal(await f.page.getByTestId('work-companion').isVisible(), false); assert.equal(f.posts.length, 0, 'An old selection cannot publish sources or open work after the selection changes');
      const cancelled = f.datasetGate(); await f.page.getByRole('button', { name: 'Check gaps', exact: true }).click(); await cancelled.entered.promise;
      await f.page.getByRole('button', { name: 'Cancel task preparation', exact: true }).click();
      const response = f.page.waitForResponse(r => r.request().method() === 'GET' && new URL(r.url()).pathname === '/v1/cmo-datasets'); cancelled.release.resolve(); await response;
      await f.page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
      await f.page.getByText(/Task preparation cancelled/).waitFor(); assert.equal(await f.page.getByTestId('work-companion').isVisible(), false); assert.equal(f.posts.length, 0); f.verify();
    } finally { await f.context.close(); }
  },
  async publication_recheck(browser) {
    const f = await fixture(browser, { unpublished: true, publicationFails: true });
    try {
      await f.page.goto(base + '/trends/', { waitUntil: 'domcontentloaded' }); await f.page.getByRole('button', { name: 'Check gaps', exact: true }).click();
      await f.page.getByText('Source verification changed; review the delivery again', { exact: true }).waitFor();
      assert.equal(await f.page.getByTestId('work-companion').isVisible(), false); assert.equal(f.posts.filter(p => p.path === '/v1/workspace-tasks/run').length, 0); f.verify();
    } finally { await f.context.close(); }
  },
  async artifacts(browser) {
    const f = await fixture(browser, { artifacts: true });
    try {
      await f.chat.getByText('One expected sample is missing.', { exact: true }).waitFor();
      await f.chat.getByRole('button', { name: 'Review routine', exact: true }).click();
      await f.chat.getByRole('heading', { name: 'Proposed evidence check', exact: true }).waitFor();
      assert.equal(f.posts.length, 0, 'Inspecting the agent proposal must not activate or run it');
      await f.chat.getByRole('button', { name: 'Review activation', exact: true }).click();
      assert(await f.chat.getByRole('button', { name: 'Activate routine', exact: true }).isDisabled()); f.verify();
    } finally { await f.context.close(); }
  },
  async routine_edit(browser) {
    const f = await fixture(browser, { artifacts: true });
    try {
      await f.chat.getByRole('button', { name: 'Review routine', exact: true }).click();
      await f.chat.getByRole('button', { name: 'Edit routine', exact: true }).click(); await f.chat.getByLabel('Routine name', { exact: true }).fill('Keep this unsaved edit');
      await f.chat.getByRole('button', { name: 'Chat', exact: true }).click(); await f.chat.getByRole('button', { name: 'Routines', exact: true }).click();
      assert.equal(await f.chat.getByLabel('Routine name', { exact: true }).inputValue(), 'Keep this unsaved edit'); f.verify();
    } finally { await f.context.close(); }
  },
  async series(browser) {
    const f = await fixture(browser, { overlapping: true });
    try {
      await f.page.goto(base + '/trends/', { waitUntil: 'domcontentloaded' });
      await f.page.getByRole('row').filter({ has: f.page.getByRole('checkbox', { name: 'Show batch A', exact: true }) }).filter({ hasText: 'Delivery 1' }).click();
      await f.page.getByRole('button', { name: 'Check gaps', exact: true }).click();
      const work = f.chat.getByRole('region', { name: 'Direct work', exact: true });
      await work.getByRole('button', { name: 'Run task', exact: true }).click(); await work.getByText('One expected sample is missing.', { exact: true }).waitFor();
      assert.deepEqual(f.posts.find(p => p.path === '/v1/workspace-tasks/run').body.series, [{ dataset_id: 'delivery-1', batch: 'A' }, { dataset_id: 'delivery-2', batch: 'B' }]);
      await work.getByRole('checkbox', { name: 'Use delivery Verified delivery', exact: true }).uncheck();
      await work.getByRole('button', { name: 'Save as routine', exact: true }).click();
      const routines = f.chat.getByRole('region', { name: 'Reusable routines', exact: true });
      await routines.getByLabel('Routine name', { exact: true }).fill('Exactly selected batches'); await routines.getByRole('button', { name: 'Save draft', exact: true }).click();
      await routines.getByRole('heading', { name: 'Exactly selected batches', exact: true }).waitFor();
      const saved = f.posts.find(p => p.path === '/v1/assistant-routines').body.task;
      assert.deepEqual(saved.dataset_ids, ['delivery-2']); assert.deepEqual(saved.series, [{ dataset_id: 'delivery-2', batch: 'B' }]);
      assert.deepEqual(saved.record_refs, [{ kind: 'evidence', id: 'delivery-2', revision: 3, site_id: 'NF1' }]);
      await f.chat.getByRole('button', { name: 'Work', exact: true }).click(); await work.getByRole('button', { name: 'Use all batches in selected deliveries', exact: true }).click();
      await work.getByRole('button', { name: 'Run task', exact: true }).click(); await work.getByRole('button', { name: 'Run task', exact: true }).waitFor();
      await f.page.waitForFunction(() => !document.querySelector('[aria-label="Direct work"]')?.textContent.includes('Running task…'));
      const expanded = f.posts.filter(p => p.path === '/v1/workspace-tasks/run').at(-1).body; assert.deepEqual(expanded.series, []); assert.deepEqual(expanded.batches, []); f.verify();
    } finally { await f.context.close(); }
  },
  async routine_failure(browser) {
    const f = await fixture(browser, { artifacts: true, failedRoutine: true });
    try {
      await f.chat.getByRole('button', { name: 'Review routine', exact: true }).click();
      await f.chat.getByText('Latest run needs attention', { exact: true }).waitFor();
      await f.chat.getByText('Source selection exceeded the allowed limit.', { exact: true }).waitFor();
      await f.chat.getByText('Previous completed result', { exact: true }).waitFor();
      assert(!(await f.chat.innerText()).includes('PRIVATE SOURCE VALUE 9173'), 'Latest run notice must not reveal raw exceptions or source values'); f.verify();
      if (process.argv.includes('--screenshots')) { await f.chat.getByRole('heading', { name: 'Proposed evidence check', exact: true }).scrollIntoViewIfNeeded(); await f.page.screenshot({ path: '/private/tmp/direct-assistant-routine.png' }); }
    } finally { await f.context.close(); }
  },
  async multisite(browser) {
    const f = await fixture(browser, { chatSite: 'NF2' });
    try {
      await f.composer.fill('Keep my NF2 draft');
      await f.page.goto(base + '/trends/', { waitUntil: 'domcontentloaded' }); await f.page.getByRole('button', { name: 'Check gaps', exact: true }).click();
      const work = f.chat.getByRole('region', { name: 'Direct work', exact: true });
      await work.getByRole('button', { name: 'Run task', exact: true }).click(); await work.getByText('One expected sample is missing.', { exact: true }).waitFor();
      assert.equal(f.posts.find(p => p.path === '/v1/workspace-tasks/run').body.site_id, 'NF1');
      await work.getByRole('button', { name: 'Ask about this result', exact: true }).click();
      await f.page.waitForFunction(() => document.querySelector('#engineering-message')?.value.includes('result-1'));
      assert.equal(f.posts.find(p => p.path === '/v1/process-model/conversations').body.site_id, 'NF1');
      assert.equal(f.posts.filter(p => /\/messages$/.test(p.path)).length, 0, 'Handoff prepares a draft, without invoking reasoning');
      await f.open('A'); assert.equal(await f.composer.inputValue(), 'Keep my NF2 draft'); f.verify();
    } finally { await f.context.close(); }
  },
  async routine_source_removal(browser) {
    const f = await fixture(browser, { artifacts: true });
    try {
      await f.chat.getByRole('button', { name: 'Review routine', exact: true }).click(); await f.chat.getByRole('button', { name: 'Run once', exact: true }).click();
      await f.chat.getByRole('checkbox', { name: 'Use delivery Verified delivery', exact: true }).uncheck();
      await f.chat.getByRole('button', { name: 'Run routine', exact: true }).click();
      await f.chat.getByRole('region', { name: 'Reusable routines', exact: true }).getByText('One expected sample is missing.', { exact: true }).waitFor();
      const parameters = f.posts.find(p => p.path === '/v1/assistant-routines/routine-1/run').body.parameters;
      assert.deepEqual(parameters.dataset_ids, []); assert.deepEqual(parameters.series, []); assert.deepEqual(parameters.batches, []);
      assert.deepEqual(parameters.record_refs, [{ kind: 'case', id: 'case-keep', revision: 2, site_id: 'NF1' }], 'Removing a dataset removes only its paired evidence reference'); f.verify();
    } finally { await f.context.close(); }
  },
};
async function main() {
  const browser = await chromium.launch({ headless: true });
  try { for (const [name, run] of Object.entries(scenarios)) { if (process.argv[2] && name !== process.argv[2]) continue; await run(browser); console.log(`PASS ${name}`); } }
  finally { await browser.close(); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
