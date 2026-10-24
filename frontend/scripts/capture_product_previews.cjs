// Capture the actual product UI for the landing-page tour. No fabricated screens.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const path = require('node:path');
const base = process.env.WORKSPACE_URL || 'http://127.0.0.1:5183';
const folder = path.resolve(__dirname, '../public/os/assets');
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' });
  try {
    const shots = [
      { url: '/app?instant', name: 'workspace-preview.jpg' },
      { url: '/app?instant&view=item&work=sample-f2408&section=evidence', name: 'evidence-preview.jpg' },
      { url: '/app?instant&view=actions', name: 'actions-preview.jpg', setup: async () => { await page.getByRole('button', { name: 'Track sample checks', exact: true }).first().click(); } },
      { url: '/app?instant&view=sources', name: 'sources-preview.jpg' },
    ];
    for (const shot of shots) {
      await page.goto(base + shot.url);
      await page.locator('.workspace-view h1').waitFor();
      await page.evaluate(() => document.fonts.ready);
      if (shot.setup) await shot.setup();
      await page.waitForTimeout(250);
      await page.screenshot({ path: path.join(folder, shot.name), type: 'jpeg', quality: 88 });
    }
    console.log('Captured four actual product views.');
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exit(1); });
