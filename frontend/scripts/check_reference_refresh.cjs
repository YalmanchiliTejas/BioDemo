// Verify task handoff, workflow discovery and the actual-product pillar walkthrough.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs = require('node:fs');
const base = process.env.WORKSPACE_URL || 'http://127.0.0.1:5183';
const out = '/private/tmp/biodemo-reference-refresh';
const assert = (value, message) => { if (!value) throw Error(message); };
(async () => {
  fs.mkdirSync(out, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  try {
    await page.goto(base);
    await page.locator('#hero-h').waitFor();
    await page.evaluate(() => document.fonts.ready);
    await page.locator('.ambient-image img').evaluate(el => el.decode());
    assert(await page.getByRole('button', { name: 'Open in workspace', exact: true }).isDisabled(), 'An empty goal must not submit');
    await page.getByLabel('Your question or goal').fill('Review the approved cleaning record for Suite 2');
    await page.getByLabel('Starting context').selectOption('none');
    await page.getByRole('button', { name: 'Open in workspace', exact: true }).click();
    await page.locator('.studio-home h1').waitFor();
    assert(!page.url().includes('cleaning'), 'Goal text must not appear in the URL');
    assert(/draft=/.test(page.url()), 'The handoff must have a matching draft token');
    assert(await page.getByLabel('Your question or goal').inputValue() === 'Review the approved cleaning record for Suite 2', 'The exact entered goal must reach the workspace');
    assert(await page.getByLabel('Starting context').inputValue() === 'none', 'Context choice must survive the handoff');
    assert(await page.locator('.ws-work-row').count() === 1, 'Landing handoff must not silently create work or run analysis');
    await page.getByRole('button', { name: 'Start work', exact: true }).click();
    await page.getByRole('heading', { name: 'Review the approved cleaning record for Suite 2', exact: true }).waitFor();
    await page.getByText('Goal saved. No new analysis has run.', { exact: true }).waitFor();
    assert(!/draft=/.test(page.url()), 'Completed handoff token must leave the work URL');
    await page.goBack();
    await page.locator('.studio-home h1').waitFor();
    assert(!/draft=/.test(page.url()), 'Back navigation must not restore a consumed handoff token');
    assert(await page.getByRole('alert').count() === 0, 'Completed work must not produce a false draft-recovery error');
    await page.goto(`${base}/app?draft=missing-draft`);
    await page.getByRole('alert').getByText(/Your draft could not be restored/).waitFor();

    await page.goto(base);
    await page.getByRole('group', { name: 'Filter starting points' }).getByRole('button', { name: 'Verify', exact: true }).click();
    assert(await page.locator('.workflow-card').count() === 2, 'Workflow filter must show relevant examples');
    await page.locator('.workflow-card').filter({ hasText: 'Bring a new question to the workspace' }).getByRole('button', { name: 'Try this starting point' }).click();
    assert(await page.getByLabel('Your question or goal').inputValue() === 'Review cleaning verification for Suite 2', 'Workflow choice must populate the editable composer');
    assert(await page.getByLabel('Starting context').inputValue() === 'none', 'Own-context example must not acquire invented sample data');

    assert(await page.getByRole('tablist', { name: 'Explore our product pillars' }).count() === 0, 'The four-pillar product tour should be removed');
    assert(await page.locator('#architecture').count() === 1, 'Architecture should remain the product explanation');
    await page.locator('#architecture').scrollIntoViewIfNeeded();
    await page.waitForTimeout(500);
    await page.screenshot({ path: `${out}/architecture-desktop.png` });

    await page.goto(`${base}/app?intent=comparison`);
    assert(await page.getByLabel('Your question or goal').inputValue() === 'Compare F-2408 with the six R7 reference batches', 'Existing intent links must continue to work');
    await page.getByText('Find a starting point for your work', { exact: true }).click();
    await page.locator('.workflow-card').filter({ hasText: 'Bring a new question to the workspace' }).getByRole('button', { name: 'Try this starting point' }).click();
    assert(await page.getByLabel('Starting context').inputValue() === 'none', 'Workspace gallery must preserve scope');

    for (const width of [320, 390, 768, 1024, 1440]) {
      await page.setViewportSize({ width, height: width < 768 ? 844 : 1000 });
      for (const url of [base, `${base}/app?instant`]) {
        await page.goto(url);
        await page.getByRole('heading', { level: 1 }).waitFor();
        assert(!await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), `Page overflow at ${width} / ${url}`);
        if (url !== base) await page.getByRole('button', { name: 'New work', exact: true }).last().click();
        const boxes = await page.locator('.goal-toolbar').evaluate(el => {
          const select = el.querySelector('select').getBoundingClientRect();
          const button = el.querySelector('button').getBoundingClientRect();
          return {
            selectRight: select.right,
            buttonLeft: button.left,
            selectBottom: select.bottom,
            buttonTop: button.top,
          };
        });
        assert(
          boxes.selectRight <= boxes.buttonLeft + 1 ||
            boxes.selectBottom <= boxes.buttonTop + 1,
          `Context selector must not overlap the action at ${width}`,
        );
        if ([390, 1440].includes(width)) await page.screenshot({ path: `${out}/${url === base ? 'landing' : 'workspace'}-${width}.png`, fullPage: width === 390 });
      }
    }
    const blockedContext = await browser.newContext();
    await blockedContext.addInitScript(() => { const original = Storage.prototype.setItem; Storage.prototype.setItem = function (...args) { if (this === window.sessionStorage) throw new DOMException('Session unavailable', 'SecurityError'); return original.apply(this, args); }; });
    const blocked = await blockedContext.newPage();
    await blocked.goto(base);
    await blocked.getByLabel('Your question or goal').fill('Retain this goal when draft storage is unavailable');
    await blocked.getByRole('button', { name: 'Open in workspace', exact: true }).click();
    await blocked.getByRole('alert').getByText(/could not carry your draft/).waitFor();
    assert(await blocked.getByLabel('Your question or goal').inputValue() === 'Retain this goal when draft storage is unavailable', 'Storage failure must preserve the entered text');
    assert(new URL(blocked.url()).pathname === '/', 'Failed handoff must not navigate away');
    await blockedContext.close();
    assert(errors.length === 0, errors.join('\n'));
    console.log(JSON.stringify({ passed: true, browserErrors: errors.length, screenshots: out }));
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exit(1); });
