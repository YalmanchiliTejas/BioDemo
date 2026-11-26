/* Worklist UI contract: the list on the Overview against fixed responses in the shape of GET /v1/worklist.
 * What is shown, and exactly what each decision sends. No live backend, no inference, no writes.
 * Needs a local-login Next dev server whose API base is http://127.0.0.1:9 (NEXT_PUBLIC_LOCAL_LOGIN=1).
 * PLAYWRIGHT_MODULE=/path/to/playwright WORKLIST_PREVIEW=http://127.0.0.1:5186 node scripts/check_worklist.cjs [--screenshots=/dir]
 */
const assert = require('node:assert/strict');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.WORKLIST_PREVIEW || 'http://127.0.0.1:5186';
const shots = (process.argv.find(arg => arg.startsWith('--screenshots=')) || '').split('=')[1];
const now = new Date().toISOString(), hourAgo = new Date(Date.now() - 3600e3).toISOString();
const item = (kind, id, title, extra = {}) => ({ id: `${kind}:${id}`, kind, title, detail: '', by: 'system', at: hourAgo, href: null, action: null, ...extra });
const proposal = { action: 'Close deviation', target: 'DEV-77', system: 'quality-review', rationale: 'Glucose in B matched A after the feed change.',
  expected_result: 'The deviation is closed with the comparison attached.', follow_up_measure: null, constraints: ['Rests on values that are still in review; verify the delivery before approving.'],
  risk: 'high', approvers: 'QA', proposed_by: 'the assistant, asked by carla@example.test', rests_on: '1 saved result, 2 source records',
  result_says: 'Glucose, B minus A: 3 matching measured times from 0 h to 48 h. Largest difference -1 g/L at 24 h (9 against 10 g/L); mean difference -0.6 g/L.\n\nThese are measured values at measured times. They describe a difference; they do not explain it.' };
let list, fail = null, sent = [];
function fresh() {
  list = { site_id: 'NF1', as_of: now, done_since: now,
    needs_you: [
      item('signal', 's1', 'DO 10 % is below the lower limit of 30 %', { detail: 'batch B-117 · Critical · seen 2 times. A signal is for review, not a confirmed deviation.', severity: 'critical', href: '/signals/?id=s1', action: { type: 'acknowledge', signal_id: 's1' } }),
      item('approval', 'p1', 'Approve or decline: Close deviation · DEV-77', { detail: proposal.rationale, by: 'assistant', proposal, action: { type: 'decide', proposal_id: 'p1', revision: 3, roles: ['qa'], recent_sign_in: true } }),
      item('question', 't1', 'The assistant asks: Which batch do you mean?', { detail: 'It needs this to continue “Forecast the batch”.', by: 'assistant', href: '/home/?conversation=c1', action: { type: 'answer', conversation_id: 'c1', revision: 4, questions: ['Which batch do you mean?'] } }),
      item('request', 'r1', 'carla@example.test asks: Missing lactate for batch C', { detail: 'Please send the lactate results for C.', by: 'carla', action: { type: 'reply', request_id: 'r1', revision: 1 } }),
      item('missing_evidence', 'pc1', 'November delivery from Source lab: 1 required item not in this delivery', { detail: 'Checked against 2 approved requirements when it was published. Missing: Lactate. A request is drafted; choose who to ask.', href: '/workbench/?datasets=ds1',
        action: { type: 'send_request', result_id: 'res1', title: 'Missing evidence: 1 item', description: 'These expected values were not found in the deliveries selected.\n- Lactate (approved specification manual)' } }),
      item('quality', 'C1', 'pH excursion in B-117: approve the local preparation or return it', { detail: 'Quality event C1.', href: '/quality/?case=C1' }),
      item('delivery', 'run1', 'October delivery from Acme: 6 values and 1 issue to check', { detail: 'Nothing from this delivery is treated as verified until these are decided.', href: '/cmo/?run=run1' }),
    ],
    in_progress: [item('assistant', 't2', 'The assistant is working on: Compare the last two lots', { by: 'assistant', href: '/home/?conversation=c2' }),
      item('proposal', 'p2', 'Approved, not yet carried out: Place hold · LOT-12', { detail: 'Approval is not execution. A connection to MES can carry this out; it is complete only with a receipt from MES (now: queued).' })],
    done: [1, 2, 3, 4, 5].map(n => item('request', `d${n}`, `carla@example.test replied: Question ${n}`, { detail: 'Not sampled on that run.' })),
    counts: { needs_you: 7, in_progress: 2, done: 5 },
    covers: ['actions proposed for approval', 'requests between colleagues', 'open signals'], not_covered: ['routine and rule drafts'], unavailable: [] };
}
(async () => {
  fresh();
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1440, height: 1100 } });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('console', m => { if (m.type() === 'error' && !/404|409|403|500|Failed to load resource/.test(m.text())) errors.push('console: ' + m.text()); });
  await page.addInitScript(() => {
    localStorage.setItem('sievance.local-session.v1', JSON.stringify({ tenant_id: 'preview-org', actor_id: 'preview-user', email: 'p@example.test', name: 'Priya Preview' }));
    localStorage.setItem('sievance.organization:preview-user', 'preview-org');
  });
  await page.route('**/*', async route => {
    const request = route.request(), url = new URL(request.url());
    if (url.origin === new URL(base).origin) return route.continue();
    const headers = { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': '*', 'Access-Control-Allow-Methods': 'GET,POST,OPTIONS', 'Content-Type': 'application/json' };
    if (request.method() === 'OPTIONS') return route.fulfill({ status: 204, headers, body: '' });
    if (url.host !== '127.0.0.1:9') return route.abort();
    const p = url.pathname, json = (data, status = 200) => route.fulfill({ status, headers, body: JSON.stringify(data) });
    const org = { id: 'preview-org', name: 'Preview Biologics', roles: ['qa'], site_ids: ['NF1'], onboarding_complete: true };
    if (request.method() === 'POST') {
      sent.push({ path: p, body: request.postDataJSON() });
      if (fail) { const f = fail; fail = null; return json({ detail: f.detail }, f.status); }
      const gone = { '/v1/proposals/p1/decisions': 'approval:p1', '/v1/work-requests/r1/answer': 'request:r1', '/v1/process-model/conversations/c1/messages': 'question:t1', '/v1/signals/s1/acknowledge': 'signal:s1', '/v1/workspace-tasks/results/res1/request-evidence': 'missing_evidence:pc1' }[p];
      if (gone) { list.needs_you = list.needs_you.filter(i => i.id !== gone); list.counts.needs_you = list.needs_you.length; }
      return json({});
    }
    if (p === '/v1/account') return json({ actor_id: 'preview-user', organizations: [org], can_create_organization: true });
    if (p === '/v1/me') return json({ tenant_id: org.id, actor_id: 'preview-user', roles: ['qa'], site_ids: ['NF1'] });
    if (p === '/v1/worklist') return list === null ? json({ detail: 'Preview service unavailable' }, 500) : json(list);
    if (p === '/v1/notifications') return json({ items: [], unread: 0 });
    if (p === '/v1/worklist/people') return json({ people: [{ id: 'u-carla', label: 'carla@example.test' }, { id: 'u-quinn', label: 'quinn@example.test' }] });
    if (p === '/api/cmo-ingestion/runs') return json({ runs: [] });
    if (p === '/v1/signals') return json({ signals: [] });
    if (p === '/v1/quality/workspaces') return json({ items: [] });
    if (p === '/v1/process-model/conversations') return json({ conversations: [] });
    return json({ detail: `Unmocked: ${p}` }, 404);
  });
  const pass = name => console.log('PASS ' + name);
  const wl = page.getByTestId('worklist');
  const row = text => wl.getByTestId('worklist-item').filter({ hasText: text });
  const open = async () => { await page.goto(base + '/dashboard/'); await wl.getByTestId('worklist-item').first().waitFor({ timeout: 90000 }); };
  const last = () => sent[sent.length - 1];

  await open();
  await wl.getByRole('heading', { name: '7 things need you' }).waitFor();
  assert.equal(await page.locator('.attention-summary').count(), 0, 'the one-sentence summary is replaced by the list');
  assert.equal(await wl.getByTestId('worklist-needs_you').getByTestId('worklist-item').count(), 7);
  assert.equal(await wl.getByTestId('worklist-in_progress').getByTestId('worklist-item').count(), 2);
  assert.equal(await wl.getByTestId('worklist-done').getByTestId('worklist-item').count(), 3, 'done shows the newest three until asked');
  await wl.getByRole('button', { name: 'Show all 5' }).click();
  assert.equal(await wl.getByTestId('worklist-done').getByTestId('worklist-item').count(), 5);
  await wl.getByText('This list reads actions proposed for approval, requests between colleagues and open signals. It does not yet read routine and rule drafts').waitFor();
  assert.equal(await row('Close deviation · DEV-77').getByText('Drafted by the assistant').count(), 1);
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'page overflows');
  if (shots) await page.screenshot({ path: path.join(shots, 'worklist-desktop.png'), fullPage: true });
  pass('one list: what needs the person, what is in progress, what was finished, and what the list covers');

  // Approval: everything the proposal states is shown before the decision; declining needs a reason.
  const approval = row('Close deviation · DEV-77');
  await approval.getByRole('button', { name: 'Review' }).click();
  const form = approval.getByRole('form', { name: 'Decide: Close deviation · DEV-77' });
  for (const text of ['Glucose in B matched A after the feed change.', 'The deviation is closed with the comparison attached.', '1 saved result, 2 source records', 'QA · high risk', 'the assistant, asked by carla@example.test',
    'Largest difference -1 g/L at 24 h (9 against 10 g/L)', 'They describe a difference; they do not explain it.',
    'Rests on values that are still in review', 'It does not carry the action out', 'needs a sign-in from the last 15 minutes']) await form.getByText(text, { exact: false }).first().waitFor();
  if (shots) await page.screenshot({ path: path.join(shots, 'worklist-approval.png'), fullPage: false });
  const before = sent.length;
  await form.getByRole('button', { name: 'Decline' }).click();
  await form.getByRole('alert').filter({ hasText: 'Give a reason' }).waitFor();
  assert.equal(sent.length, before, 'declining without a reason sends nothing');
  // Disagreeing is as quick as agreeing: a common reason is one click, and it can still be edited.
  await form.getByRole('group', { name: 'Common reasons to decline' }).getByRole('button', { name: 'More data is needed first.' }).click();
  assert.equal(await form.getByRole('textbox', { name: 'Reason', exact: true }).inputValue(), 'More data is needed first.');
  fail = { status: 409, detail: 'proposal changed: now revision 4; review the current content' };
  await form.getByRole('button', { name: 'Decline' }).click();
  await approval.getByRole('alert').filter({ hasText: 'This changed after the list was read' }).waitFor();
  assert.deepEqual(last(), { path: '/v1/proposals/p1/decisions', body: { expected_revision: 3, decision: 'rejected', role: 'qa', comment: 'More data is needed first.' } });
  await form.getByRole('textbox', { name: 'Reason', exact: true }).fill('');
  fail = { status: 403, detail: 'high-risk approval requires a recent sign-in; sign in again, then retry' };
  await form.getByRole('button', { name: 'Approve' }).click();
  await form.getByRole('alert').filter({ hasText: 'requires a recent sign-in' }).waitFor();
  assert.equal(await row('Close deviation · DEV-77').count(), 1, 'a refused approval leaves the item in place');
  fail = { status: 409, detail: 'proposal changed: now revision 4; review the current content' };
  await form.getByRole('button', { name: 'Approve' }).click();
  await approval.getByRole('alert').filter({ hasText: 'This changed after the list was read' }).waitFor();
  await form.getByRole('textbox', { name: 'Reason', exact: true }).fill('Checked against the batch record.');
  await form.getByRole('button', { name: 'Approve' }).click();
  await wl.getByTestId('worklist-notice').filter({ hasText: 'Approved: Close deviation · DEV-77. Your approval is recorded; carrying it out is a separate step' }).waitFor();
  assert.deepEqual(last(), { path: '/v1/proposals/p1/decisions', body: { expected_revision: 3, decision: 'approved', role: 'qa', comment: 'Checked against the batch record.' } });
  await wl.getByRole('heading', { name: '6 things need you' }).waitFor();
  assert.equal(await row('Close deviation · DEV-77').count(), 0);
  pass('an approval shows what it rests on, refuses a silent decline, reports a refusal or a changed record, and sends the exact revision');

  // A colleague's request is answered in place.
  const request = row('Missing lactate for batch C');
  await request.getByRole('button', { name: 'Reply' }).click();
  assert(await request.getByRole('button', { name: 'Send reply' }).isDisabled());
  await request.getByLabel('Your reply').fill('Not sampled on that run; see LIMS-4411.');
  await request.getByRole('button', { name: 'Send reply' }).click();
  await wl.getByTestId('worklist-notice').filter({ hasText: 'Reply sent. carla@example.test will see it in their list.' }).waitFor();
  assert.deepEqual(last(), { path: '/v1/work-requests/r1/answer', body: { expected_revision: 1, reply: 'Not sampled on that run; see LIMS-4411.' } });
  pass('a request from a colleague is answered where it is listed');

  // A delivery was checked when it was published; what is missing arrives with the request already drafted.
  const lacking = row('November delivery from Source lab');
  await lacking.getByText('Checked against 2 approved requirements when it was published. Missing: Lactate.', { exact: false }).waitFor();
  assert.equal(await lacking.getByRole('link', { name: 'Open' }).getAttribute('href'), '/workbench/?datasets=ds1');
  await lacking.getByRole('button', { name: 'Send request' }).first().click();
  const send = lacking.getByRole('form', { name: 'Send this request' });
  assert((await send.getByLabel('Request', { exact: true }).inputValue()).includes('- Lactate (approved specification manual)'), 'the drafted request is shown, ready to edit');
  assert(await send.getByRole('button', { name: 'Send request' }).isDisabled(), 'a request needs someone to ask');
  await send.locator('select[aria-label="Who to ask"]').selectOption({ label: 'carla@example.test' });
  await send.getByLabel('Subject', { exact: true }).fill('Lactate for the November delivery');
  if (shots) await page.screenshot({ path: path.join(shots, 'worklist-drafted-request.png'), fullPage: false });
  await send.getByRole('button', { name: 'Send request' }).click();
  await wl.getByTestId('worklist-notice').filter({ hasText: 'Request sent to carla@example.test. They are notified, and their reply will appear here.' }).waitFor();
  assert.deepEqual(last(), { path: '/v1/workspace-tasks/results/res1/request-evidence', body: { owner_id: 'u-carla', title: 'Lactate for the November delivery',
    description: 'These expected values were not found in the deliveries selected.\n- Lactate (approved specification manual)' } });
  assert.equal(await row('November delivery from Source lab').count(), 0);
  pass('missing evidence found by the automatic check arrives with its request drafted; the person picks a colleague and sends it');

  // The assistant's question is answered without opening the conversation.
  const question = row('Which batch do you mean?');
  await question.getByRole('button', { name: 'Answer' }).click();
  await question.getByLabel('Which batch do you mean?').fill('B-200');
  await question.getByRole('button', { name: 'Send answers' }).click();
  await wl.getByTestId('worklist-notice').filter({ hasText: 'Answer sent. The assistant is continuing' }).waitFor();
  assert.deepEqual(last(), { path: '/v1/process-model/conversations/c1/messages', body: { text: '1. Which batch do you mean?\n   B-200', expected_revision: 4 } });
  pass('the assistant\'s question is answered from the list, as the next message in that conversation');

  // A signal is acknowledged in place; the evidence stays one click away.
  const signal = row('DO 10 % is below the lower limit');
  assert.equal(await signal.getAttribute('data-severity'), 'critical');
  assert.equal(await signal.getByRole('link', { name: 'Open' }).getAttribute('href'), '/signals/?id=s1');
  await signal.getByRole('button', { name: 'Acknowledge' }).click();
  await wl.getByTestId('worklist-notice').filter({ hasText: 'Acknowledged: DO 10 % is below the lower limit' }).waitFor();
  assert.equal(last().path, '/v1/signals/s1/acknowledge');
  await wl.getByRole('heading', { name: '2 things need you' }).waitFor();
  assert.equal(await row('October delivery from Acme').getByRole('link', { name: 'Open' }).getAttribute('href'), '/cmo/?run=run1');
  pass('a signal is acknowledged in place, and items decided elsewhere link straight to where they are decided');

  // Honest when part of it, or all of it, cannot be read.
  fresh(); list.needs_you = []; list.counts.needs_you = 0; list.unavailable = [{ source: 'signals', covers: 'open signals' }];
  await open().catch(() => undefined);
  await page.goto(base + '/dashboard/');
  await wl.getByRole('heading', { name: 'Nothing found that needs you, but part of the list could not be read' }).waitFor({ timeout: 60000 });
  await wl.getByTestId('worklist-unavailable').filter({ hasText: 'Could not read open signals. Anything waiting there is not listed below.' }).waitFor();
  fresh(); list.needs_you = []; list.counts.needs_you = 0;
  await page.goto(base + '/dashboard/');
  await wl.getByRole('heading', { name: 'Nothing needs you right now' }).waitFor({ timeout: 60000 });
  await wl.getByText('Nothing is waiting on you.').waitFor();
  list = null;
  await page.evaluate(() => sessionStorage.clear());
  await page.goto(base + '/dashboard/');
  await wl.getByRole('alert').filter({ hasText: 'The list could not be refreshed, so it may be out of date' }).or(wl.getByRole('alert').filter({ hasText: 'could not be read' })).first().waitFor({ timeout: 60000 });
  pass('the list says when part of it could not be read, and never reports that as nothing waiting');

  // Phone width.
  fresh();
  await page.setViewportSize({ width: 390, height: 844 });
  await open();
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'page overflows at phone width');
  await row('Close deviation · DEV-77').getByRole('button', { name: 'Review' }).click();
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'open approval overflows at phone width');
  if (shots) await page.screenshot({ path: path.join(shots, 'worklist-mobile.png'), fullPage: true });
  pass('no horizontal overflow at phone width, with a decision open');

  assert.deepEqual(errors, []);
  pass('no browser errors');
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
