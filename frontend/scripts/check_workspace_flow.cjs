// Context stays attached while moving between evidence, tools and follow-up.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs = require('node:fs');
const base = process.env.WORKSPACE_URL || 'http://127.0.0.1:5184';
const out = '/private/tmp/biodemo-workspace-flow';
const assert = (value, message) => { if (!value) throw Error(message); };
(async () => {
  fs.mkdirSync(out, { recursive: true });
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' });
  const errors = [];
  page.on('pageerror', error => errors.push(String(error)));
  try {
    await page.goto(`${base}/app?instant`);
    await page.locator('.studio-home h1').waitFor();
    await page.evaluate(() => document.fonts.ready);
    await page.locator('.ambient-image img').evaluate(el => el.decode());
    const row = await page.locator('.studio-work-list .ws-work-row').first().boundingBox();
    assert(row.y + row.height < 800, 'Resumable work must be visible without scrolling on desktop');
    await page.screenshot({ path: `${out}/home.png` });
    await page.getByRole('button', { name: 'Continue investigation', exact: true }).click();
    await page.getByText('Reduced oxygen transfer', { exact: true }).click();
    await page.getByText('DO falls as agitation reaches its ceiling.', { exact: false }).waitFor();
    await page.getByRole('tab', { name: 'Evidence', exact: true }).click();
    const evidenceUrl = page.url();
    assert(new URL(evidenceUrl).searchParams.get('work') === 'sample-f2408', 'Evidence must retain the current work');
    await page.locator('.flow-evidence-full .ev').first().click();
    await page.getByRole('dialog').waitFor();
    await page.keyboard.press('Escape');
    assert(page.url() === evidenceUrl, 'Closing a source must return to the same evidence view');
    await page.getByRole('tab', { name: 'Trends', exact: true }).click();
    await page.getByRole('heading', { name: 'Batch trends & comparison' }).waitFor();
    await page.reload();
    assert(await page.getByRole('tab', { name: 'Trends', exact: true }).getAttribute('aria-selected') === 'true', 'Reload must preserve the selected work view');
    await page.goBack();
    assert(await page.getByRole('tab', { name: 'Evidence', exact: true }).getAttribute('aria-selected') === 'true', 'Back must restore the prior work view');
    await page.getByRole('tab', { name: 'Evidence', exact: true }).press('ArrowRight');
    assert(await page.getByRole('tab', { name: 'Trends', exact: true }).getAttribute('aria-selected') === 'true', 'Work tabs must support arrow keys');
    await page.getByRole('tab', { name: 'Next steps', exact: true }).click();
    await page.getByRole('button', { name: 'Track sample checks', exact: true }).first().click();
    assert(await page.locator('.ws-action-card').count() === 3, 'Sample checks must attach to current work');
    await page.getByRole('tab', { name: 'Overview', exact: true }).click();
    await page.getByRole('tab', { name: 'Overview', exact: true }).waitFor();
    await page.waitForFunction(() => document.querySelector('#work-tab-overview').getAttribute('aria-selected') === 'true');
    await page.screenshot({ path: `${out}/work.png` });
    await page.getByRole('button', { name: 'Open scientific workspace', exact: true }).click();
    await page.getByRole('button', { name: 'Back to this work', exact: false }).click();
    assert(new URL(page.url()).searchParams.get('work') === 'sample-f2408', 'Scientific tools must return to the originating work');
    await page.getByRole('navigation', { name: 'Manufacturing OS' }).getByRole('button', { name: 'New work', exact: true }).click();
    await page.getByLabel('Your question or goal').fill('Prepare a record review');
    await page.getByLabel('Starting context').selectOption('none');
    await page.getByRole('button', { name: 'Start work', exact: true }).click();
    await page.getByRole('tab', { name: 'Next steps', exact: true }).click();
    assert(await page.locator('.ws-action-card').count() === 0, 'A new work item must not show another work item’s actions');
    assert(await page.getByRole('button', { name: 'Track sample checks', exact: true }).count() === 0, 'A context-free item must not offer sample recommendations');
    await page.getByRole('navigation', { name: 'Manufacturing OS' }).getByRole('button', { name: 'Workspace', exact: true }).click();
    assert(await page.getByRole('dialog').count() === 0, 'Returning home must not reopen a consumed new-work request');
    for (const width of [320, 390, 768, 1024, 1440]) {
      await page.setViewportSize({ width, height: 900 });
      await page.goto(`${base}/app?instant&view=item&work=sample-f2408`);
      for (const tab of ['Overview', 'Evidence', 'Trends', 'Next steps', 'Notes']) {
        await page.getByRole('tab', { name: new RegExp(`^${tab}`) }).click();
        assert(!await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), `Overflow: ${width} / ${tab}`);
        if (width === 390 && tab === 'Overview') await page.screenshot({ path: `${out}/work-mobile.png`, fullPage: true });
      }
    }
    assert(!errors.length, errors.join('\n'));
    console.log(JSON.stringify({ passed: true, screenshots: out, browserErrors: errors.length }));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
