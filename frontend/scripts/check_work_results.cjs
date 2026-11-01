/* UI contract over saved actual-account receipts. All API calls are intercepted;
 * this does not run inference or claim a deployed workspace change.
 * PLAYWRIGHT_MODULE=/path/to/playwright node scripts/check_work_results.cjs
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fixture = JSON.parse(fs.readFileSync(process.env.WORK_RESULTS_FIXTURE || '/private/tmp/work-results-account-fixture.json'));
const base = process.env.WORK_RESULTS_PREVIEW || 'http://127.0.0.1:5189';
const output = process.env.WORK_RESULTS_ARTIFACTS || '/private/tmp/sievance-structured-work';
const org = { id: 'preview-org', name: 'Saved account preview', roles: ['admin'], site_ids: ['NF1'], onboarding_complete: true };
const routes = Object.values(fixture.threads);
let failList = false;
const demo = process.env.WORK_RESULTS_DEMO === '1';
(async () => {
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage({ viewport: { width: 1540, height: 1100 }, ...(demo ? { recordVideo: { dir: output+'/video', size: { width: 1540, height: 1100 } } } : {}) });
    const exceptions = [];const posts = [];
    page.on('pageerror', e => exceptions.push(e.message));
    await page.addInitScript(() => {
      localStorage.setItem('sievance.local-session.v1', JSON.stringify({ tenant_id: 'preview-org', actor_id: 'preview-user', email: 'preview@example.test', name: 'Local preview' }));
      localStorage.setItem('sievance.organization:preview-user', 'preview-org');
    });
    await page.route('**/*', async route => {
      const req = route.request();const path = new URL(req.url()).pathname;
      if (!path.startsWith('/v1/') && !path.startsWith('/api/')) return route.continue();
      const headers = { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': '*', 'Access-Control-Allow-Methods': 'GET,POST,OPTIONS' };
      if (req.method() === 'OPTIONS') return route.fulfill({ status: 204, headers, body: '' });
      if (req.method() !== 'GET') { posts.push(path);return route.fulfill({ status: 500, headers, body: '{}' }); }
      let data;
      if (path === '/v1/account') data = { actor_id: 'preview-user', organizations: [org] };
      else if (path === '/v1/me') data = { tenant_id: org.id, actor_id: 'preview-user', roles: ['admin'], auth_mode: 'development' };
      else if (path === '/v1/process-model/conversations') {
        if (failList) return route.fulfill({ status: 500, headers, body: JSON.stringify({ detail: 'Saved work service unavailable' }) });
        data = { conversations: routes.map(t => ({ id: t.id, title: t.title })) };
      }
      else if (path.startsWith('/v1/process-model/conversations/')) data = fixture.threads[path.split('/').at(-1)];
      else if (path === '/v1/cmo-datasets') data = { datasets: [] };
      if (!data) return route.fulfill({ status: 404, headers, body: JSON.stringify({ detail: 'Unmocked local preview path' }) });
      return route.fulfill({ status: 200, headers, body: JSON.stringify(data) });
    });
    const check = name => console.log('PASS '+name);
    const workNav = page.getByRole('navigation', { name: 'Work type' });
    if (demo) {
      await page.goto(base+'/workspaces/');
      await page.getByRole('heading', { name: 'Batch holds against the procedure' }).waitFor();
      await page.screenshot({ path: output+'/workspace-preview.png', fullPage: true });
      await page.waitForTimeout(4500);
      await page.locator('[aria-label^="Inspect source row"]').nth(2).click();
      await page.waitForTimeout(3500);
      for (const label of [/Deviations/, /Data preparation/, /Scheduling/]) {
        await workNav.getByRole('button', { name: label }).click();
        await page.locator('#main').evaluate(n => { n.scrollTop = 0; });
        await page.waitForTimeout(4500);
      }
      await page.getByRole('button', { name: 'Ask about these results' }).click();
      await page.getByRole('region', { name: 'Work companion' }).waitFor();
      await page.waitForTimeout(4500);
      assert.deepEqual(posts, []);assert.deepEqual(exceptions, []);
      const video = page.video();await page.context().close();
      fs.copyFileSync(await video.path(), output+'/workspace-demo.webm');
      console.log('Saved local workspace preview; no inference or account mutations.');
      return;
    }
    await page.goto(base+'/workspaces/');
    await page.getByRole('heading', { name: 'Batch holds against the procedure' }).waitFor();
    assert.equal(await page.locator('[data-testid="work-table"] tbody tr').count(), 6);
    assert.equal(await page.getByRole('img', { name: /^Hold duration/ }).count(), 1);
    check('saved account hold data renders as a threshold chart and six source-linked rows');
    await page.locator('[aria-label^="Inspect source row"]').nth(2).click();
    assert((await page.getByTestId('work-source').innerText()).includes('row 4'));
    check('one click traces a finding to the exact source row');
    await page.getByLabel('Filter result rows').fill('Outside limit');
    assert.equal(await page.locator('[data-testid="work-table"] tbody tr').count(), 3);
    await page.getByLabel('Filter result rows').fill('');
    const downloadEvent = page.waitForEvent('download');await page.getByRole('button', { name: 'Export table' }).click();
    const download = await downloadEvent;assert.equal(download.suggestedFilename(), 'work-review.csv');
    await download.saveAs(output+'/review.csv');
    assert(fs.readFileSync(output+'/review.csv','utf8').includes('Agent finding'));
    check('table filtering and spreadsheet-safe CSV export work');
    await page.locator('#main').evaluate(n => { n.scrollTop = 0; });
    await page.screenshot({ path: output+'/investigations.png', fullPage: true });
    await workNav.getByRole('button', { name: /Deviations/ }).click();
    await page.getByRole('heading', { name: 'Assay results against the current specification' }).waitFor();
    assert.equal(await page.locator('[data-testid="work-table"] tbody tr').count(), 6);
    await page.screenshot({ path: output+'/deviations.png', fullPage: true });
    await workNav.getByRole('button', { name: /Data preparation/ }).click();
    await page.getByRole('heading', { name: 'Original values and normalization proposals' }).waitFor();
    assert((await page.getByTestId('work-table').innerText()).includes('Proposed value'));
    await page.screenshot({ path: output+'/ingestion.png', fullPage: true });
    check('deviations show source limits; reconciliation preserves raw values, units and proposed routing');
    await workNav.getByRole('button', { name: /Scheduling/ }).click();
    await page.getByRole('heading', { name: 'Proposed line schedule' }).waitFor();
    assert.equal(await page.locator('[data-testid="work-table"] tbody tr').count(), 4);
    assert((await page.getByRole('img', { name: /^Elapsed hours/ }).getAttribute('aria-label')).includes('hours'));
    assert((await page.getByRole('complementary', { name: 'Work status and evidence' }).innerText()).includes('Not performed'));
    await page.screenshot({ path: output+'/scheduling.png', fullPage: true });
    const blocked = routes.flatMap(t => t.turns).find(t => t.status === 'blocked');
    await page.getByLabel('Saved review').selectOption(blocked.id);
    assert((await page.getByRole('complementary', { name: 'Work status and evidence' }).innerText()).includes('Blocked'));
    assert((await page.getByTestId('work-table').innerText()).includes('Not proposed'));
    check('Gantt proposals retain review questions; blocked work never acquires invented timings');
    const selectedId = routes.find(t => /scheduling/i.test(t.title)).turns.at(-1).id;
    await page.getByLabel('Saved review').selectOption(selectedId);
    await page.reload();await page.getByRole('heading', { name: 'Proposed line schedule' }).waitFor();
    assert.equal(await page.getByLabel('Saved review').inputValue(), selectedId);
    check('saved review links restore the correct workspace after reload');
    await page.getByRole('button', { name: 'Ask about these results' }).click();
    await page.getByRole('region', { name: 'Work companion' }).waitFor();
    assert.equal(posts.length, 0);
    check('assistant receives a bounded selected context; opening it sends no model request');
    await page.getByRole('button', { name: 'Minimize companion', exact: true }).first().click();
    const schedulingThread = routes.find(t => /scheduling/i.test(t.title));
    await page.evaluate(id => localStorage.setItem('biodemo.engineering.conversation.v1', id), schedulingThread.id);
    await page.goto(base+'/home/');
    await page.getByRole('link', { name: 'Open workspace', exact: true }).first().waitFor();
    assert.equal(await page.getByRole('link', { name: 'Open workspace', exact: true }).count(), 15);
    assert.equal(await page.locator('details[open]').filter({ hasText: 'Read the assistant’s explanation' }).count(), 0);
    await page.getByRole('link', { name: 'Open workspace', exact: true }).last().click();
    await page.getByRole('heading', { name: 'Proposed line schedule' }).waitFor();
    check('assistant replies collapse long explanations and link into the corresponding workspace');
    await page.setViewportSize({ width: 390, height: 844 });
    await page.locator('#workspace-navigation').waitFor({ state: 'hidden' });
    await page.locator('#main').evaluate(n => { n.scrollTop = 0; });
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.screenshot({ path: output+'/mobile.png', fullPage: true });
    check('phone layout has no page-level horizontal overflow');
    failList = true;
    await page.getByRole('button', { name: 'Refresh', exact: true }).click();
    await page.getByRole('alert').filter({ hasText: 'Saved work service unavailable' }).waitFor();
    assert.equal(await page.getByTestId('work-table').count(), 0);
    check('API failure clears stale results and never substitutes demo or reference data');
    assert.deepEqual(exceptions, []);assert.deepEqual(posts, []);
    check('no runtime errors and no API mutations or paid inference calls');
  } finally { await browser.close(); }
})();
