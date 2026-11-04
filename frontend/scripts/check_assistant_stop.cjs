/* Local browser UI contract only: every API request is intercepted. No backend,
 * inference, manufacturing action, or deployed account is exercised.
 * Run with a local-login Next dev server and PLAYWRIGHT_MODULE=/path/to/playwright.
 */
const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.ASSISTANT_STOP_PREVIEW || 'http://127.0.0.1:5186';
const deferred = () => {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return { promise, resolve };
};
const clone = value => JSON.parse(JSON.stringify(value));
const thread = id => ({ id, revision: 1, title: `Stop fixture ${id}`, turn_ids: [`turn-${id}`],
  demo_enabled: false, source_ids: [], dataset_ids: [], mission_status: 'active',
  turns: [{ id: `turn-${id}`, user_text: `Review fixture ${id}`, status: 'running',
    reply: null, questions: [], issues: [], artifacts: [], gateway_runs: [] }] });

async function fixture(browser) {
  const context = await browser.newContext();
  const page = await context.newPage();
  page.setDefaultTimeout(15000);
  const errors = [], unexpected = [], posts = [];
  const threads = { A: thread('A'), B: thread('B') };
  const stops = {}, polls = {};
  page.on('pageerror', error => errors.push(error.message));
  await page.addInitScript(() => {
    localStorage.setItem('sievance.local-session.v1', JSON.stringify({
      tenant_id: 'stop-fixture', actor_id: 'fixture-user', email: 'fixture@example.test', name: 'UI fixture' }));
    localStorage.setItem('sievance.organization:fixture-user', 'stop-fixture');
    localStorage.setItem('biodemo.engineering.conversation.v1', 'A');
  });
  const headers = { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': '*', 'Access-Control-Allow-Methods': 'GET,POST,OPTIONS' };
  const respond = (route, data, status = 200) => route.fulfill({ status, headers, body: JSON.stringify(data) });
  await page.route('**/*', async route => {
    const req = route.request(), path = new URL(req.url()).pathname;
    if (!path.startsWith('/v1/') && !path.startsWith('/api/')) return route.continue();
    if (req.method() === 'OPTIONS') return route.fulfill({ status: 204, headers, body: '' });
    if (req.method() === 'POST') posts.push(path);
    if (path === '/v1/account') return respond(route, { actor_id: 'fixture-user', organizations: [{
      id: 'stop-fixture', name: 'Local UI fixture', roles: ['admin'], site_ids: ['NF1'], onboarding_complete: true }] });
    if (path === '/v1/me') return respond(route, { tenant_id: 'stop-fixture', actor_id: 'fixture-user', roles: ['admin'], auth_mode: 'development' });
    if (path === '/v1/process-model/conversations') return respond(route, {
      conversations: Object.values(threads).map(({ id, title }) => ({ id, title })) });
    const match = path.match(/^\/v1\/process-model\/conversations\/([AB])(?:\/(stop))?$/);
    if (match) {
      const id = match[1];
      if (req.method() === 'POST' && match[2] === 'stop') {
        const pending = stops[id];
        assert(pending, `Unexpected Stop request for ${id}`);
        pending.entered.resolve();
        const response = await pending.release.promise;
        return respond(route, response.data, response.status || 200);
      }
      if (req.method() === 'GET' && !match[2]) {
        const snapshot = clone(threads[id]);
        const pending = polls[id];
        if (pending) {
          delete polls[id]; pending.entered.resolve();
          await pending.release.promise;
        }
        return respond(route, snapshot);
      }
    }
    unexpected.push(`${req.method()} ${path}`);
    return respond(route, { detail: 'Unexpected UI fixture request' }, 404);
  });
  await page.goto(base + '/home/', { waitUntil: 'domcontentloaded', timeout: 60000 });
  const chat = page.getByTestId('engineering-chat');
  await chat.getByText('Review fixture A', { exact: true }).waitFor();
  await chat.getByRole('button', { name: 'Stop work', exact: true }).waitFor();
  const stopGate = id => (stops[id] = { entered: deferred(), release: deferred() });
  const cancel = id => {
    threads[id].turns[0].status = 'cancelled';
    threads[id].turns[0].system_message = `Stopped fixture ${id}`;
    return clone(threads[id]);
  };
  const open = async id => {
    const menu = chat.locator('summary').filter({ hasText: 'Conversations' });
    await menu.click();
    await chat.getByRole('button', { name: `Stop fixture ${id}`, exact: true }).click();
    await menu.click();
    await chat.getByText(`Review fixture ${id}`, { exact: true }).waitFor();
  };
  const verify = () => {
    assert.deepEqual(errors, []);
    assert.deepEqual(unexpected, []);
    assert(posts.every(path => /\/conversations\/[AB]\/stop$/.test(path)), 'Only fixture Stop POSTs are allowed');
  };
  return { page, chat, context, threads, stops, polls, stopGate, cancel, open, verify };
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  try {
    {
      const f = await fixture(browser);
      try {
        const a = f.stopGate('A');
        await f.chat.getByRole('button', { name: 'Stop work', exact: true }).click();
        await a.entered.promise;
        const cancelledA = f.cancel('A');
        // A poll sees cancellation while the Stop POST is still awaiting acknowledgment.
        await f.chat.getByText('Stopped fixture A', { exact: true }).waitFor();
        assert(await f.chat.getByRole('button', { name: 'Stopping…', exact: true }).isDisabled());
        assert.equal(await f.chat.getByText('Stopping work…', { exact: true }).count(), 1);
        await f.chat.getByLabel('Describe your process problem or follow up', { exact: true }).fill('Follow-up');
        assert(await f.chat.getByRole('button', { name: 'Send message', exact: true }).isDisabled());
        // Another conversation retains its own Stop control during A's pending acknowledgment.
        await f.open('B');
        const b = f.stopGate('B');
        assert(await f.chat.getByRole('button', { name: 'Stop work', exact: true }).isEnabled());
        await f.chat.getByRole('button', { name: 'Stop work', exact: true }).click();
        await b.entered.promise;
        a.release.resolve({ data: cancelledA });
        await f.chat.getByText('Review fixture B', { exact: true }).waitFor();
        assert.equal(await f.chat.getByText('Stopping work…', { exact: true }).count(), 1);
        b.release.resolve({ data: f.cancel('B') });
        await f.chat.getByRole('button', { name: 'Stopping…', exact: true }).waitFor({ state: 'hidden' });
        await f.chat.getByText('Stopped fixture B', { exact: true }).waitFor();
        assert(await f.chat.getByRole('button', { name: 'Send message', exact: true }).isEnabled());
        f.verify();
        console.log('PASS delayed Stop acknowledgment survives cancellation polling and concurrent conversation switching');
      } finally { await f.context.close(); }
    }
    {
      const f = await fixture(browser);
      try {
        const failed = f.stopGate('A');
        await f.chat.getByRole('button', { name: 'Stop work', exact: true }).click();
        await failed.entered.promise;
        failed.release.resolve({ status: 503, data: { detail: 'Fixture Stop temporarily unavailable' } });
        await f.chat.getByRole('alert').filter({ hasText: 'Fixture Stop temporarily unavailable' }).waitFor();
        assert(await f.chat.getByRole('button', { name: 'Stop work', exact: true }).isEnabled());
        const retry = f.stopGate('A');
        await f.chat.getByRole('button', { name: 'Stop work', exact: true }).click();
        await retry.entered.promise;
        retry.release.resolve({ data: f.cancel('A') });
        await f.chat.getByText('Stopped fixture A', { exact: true }).waitFor();
        assert.equal(await f.chat.getByRole('alert').count(), 0);
        f.verify();
        console.log('PASS failed Stop remains visible and retryable');
      } finally { await f.context.close(); }
    }
    {
      const f = await fixture(browser);
      try {
        const stale = { entered: deferred(), release: deferred() };
        f.polls.A = stale;
        await stale.entered.promise;
        const stopped = f.stopGate('A');
        await f.chat.getByRole('button', { name: 'Stop work', exact: true }).click();
        await stopped.entered.promise;
        stopped.release.resolve({ data: f.cancel('A') });
        await f.chat.getByText('Stopped fixture A', { exact: true }).waitFor();
        const response = f.page.waitForResponse(r => r.request().method() === 'GET' && /\/conversations\/A$/.test(r.url()));
        stale.release.resolve();
        await response;
        // Give the old fetch and React a rendering opportunity after its response.
        await f.page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
        assert.equal(await f.chat.getByRole('button', { name: 'Stop work', exact: true }).count(), 0);
        assert.equal(await f.chat.getByText('Stopped fixture A', { exact: true }).count(), 1);
        f.verify();
        console.log('PASS an old in-flight running poll cannot revive an acknowledged cancelled turn');
      } finally { await f.context.close(); }
    }
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
