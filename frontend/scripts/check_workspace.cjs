// Smoke-check the workspace flow and responsive layout against a running Vite server.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs = require('node:fs');
const path = require('node:path');
const base = process.env.WORKSPACE_URL || 'http://127.0.0.1:5180';
const out = process.env.SCREENSHOT_DIR || '/private/tmp/biodemo-frontend-review';
const assert = (condition, message) => { if (!condition) throw Error(message); };

(async () => {
  fs.mkdirSync(out, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' });
  const errors = [];
  page.on('pageerror', error => errors.push(String(error)));
  const overflow = async () => page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
  try {
    await page.goto(`${base}/app?instant`);
    await page.locator('.studio-home h1').waitFor();
    await page.evaluate(() => document.fonts.ready);
    assert(await page.getByRole('complementary', { name: 'Assistant', exact: true }).count() === 0, 'Assistant should be optional by default');
    assert(await page.locator('.ws-contextbar').getByText('Sample mode', { exact: true }).count() === 1, 'Workspace must keep sample mode visible');
    assert(await page.locator('.home-current-thread li').count() === 3, 'Home sample thread should show the 27 h, 48 h and next-step sequence');
    assert(await page.locator('.home-rail .home-sources').count() === 1, 'Home should keep sources in the workbench rail');
    assert(await page.locator('.home-boundary').count() === 1, 'Home should state the demo boundary');
    assert(!await overflow(), 'Desktop page overflows');
    await page.screenshot({ path: path.join(out, 'workspace-desktop.png') });
    await page.getByRole('button', { name: 'Continue investigation', exact: true }).click();
    assert(await page.getByRole('tab', { name: 'Overview', exact: true }).getAttribute('aria-selected') === 'true', 'Primary action should open the saved investigation');
    await page.goBack();
    await page.locator('.studio-home h1').waitFor();
    await page.goForward();
    await page.getByRole('tab', { name: 'Overview', exact: true }).waitFor();
    await page.getByRole('button', { name: 'Open assistant', exact: true }).click();
    await page.getByRole('complementary', { name: 'Assistant', exact: true }).waitFor();
    await page.getByRole('button', { name: 'Close assistant panel' }).click();
    await page.getByRole('button', { name: 'Workspace', exact: true }).click();
    await page.getByRole('button', { name: 'Work queue', exact: true }).click();
    await page.getByRole('heading', { name: 'Work queue', exact: true }).waitFor();
    await page.keyboard.press('Control+k');
    await page.getByRole('dialog', { name: 'Search', exact: true }).waitFor();
    await page.keyboard.press('Escape');
    await page.getByRole('button', { name: 'Workspace', exact: true }).click();
    await page.getByRole('button', { name: 'Continue investigation', exact: true }).click();
    await page.getByRole('tab', { name: 'Next steps', exact: true }).click();
    await page.getByRole('button', { name: 'Review proposed plan', exact: true }).click();
    await page.getByRole('dialog').waitFor();
    await page.keyboard.press('Escape');

    for (const view of ['historian', 'lims', 'mes', 'qms']) {
      await page.goto(`${base}/app?instant&view=${view}`);
      await page.locator('.workspace-view > .host').waitFor();
      const host = await page.locator('.workspace-view > .host').boundingBox();
      assert(host && host.width > 700 && host.height > 500, `${view} should fill the working area`);
      assert(!await overflow(), `${view} page overflows`);
    }

    await page.setViewportSize({ width: 1024, height: 900 });
    await page.goto(`${base}/app?instant`);
    await page.locator('.studio-home h1').waitFor();
    await page.locator('.studio-source').last().scrollIntoViewIfNeeded();
    assert(await page.locator('.sheet-page').evaluate(el => getComputedStyle(el).overflowY === 'auto'), 'Tablet workspace must remain scrollable');
    assert(!await overflow(), 'Tablet workspace overflows');

    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(`${base}/app?instant`);
    await page.locator('.studio-home h1').waitFor();
    assert(await page.locator('.ws-contextbar').isVisible(), 'Mobile workspace must keep the sample/boundary strip visible');
    assert(!await overflow(), 'Mobile workspace overflows');
    await page.screenshot({ path: path.join(out, 'workspace-mobile.png'), fullPage: true });
    await page.getByRole('button', { name: 'Open menu' }).click();
    await page.getByRole('button', { name: /^Work queue/ }).click();
    await page.getByRole('heading', { name: 'Work queue', exact: true }).waitFor();
    await page.getByRole('button', { name: 'Open assistant', exact: true }).click();
    const closeBox = await page.getByRole('button', { name: 'Close assistant panel' }).boundingBox();
    assert(closeBox && closeBox.y >= 0 && closeBox.y + closeBox.height < 844, 'Mobile assistant should open in view');
    await page.getByRole('button', { name: 'Close assistant panel' }).click();

    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: width === 1440 ? 1000 : 844 });
      await page.goto(base);
      await page.getByRole('heading', { level: 1 }).waitFor();
      assert(!await overflow(), 'Landing page overflows');
      await page
        .locator('.lp-system')
        .filter({ hasText: 'LIMS' })
        .getByText(/36 h and 48 h/)
        .waitFor();
      await page
        .locator('.lp-system')
        .filter({ hasText: 'MES' })
        .getByText(/Step 4.3/)
        .waitFor();
      await page.screenshot({ path: path.join(out, `landing-${width}.png`), fullPage: width === 390 });
    }
    assert(errors.length === 0, errors.join('\n'));
    console.log(JSON.stringify({ passed: true, screenshots: out, browserErrors: errors.length }));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
