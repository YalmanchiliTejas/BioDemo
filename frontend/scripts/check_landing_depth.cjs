// Verify landing depth motion, the architecture explanation and the reduced-motion fallback.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs = require('node:fs');
const path = require('node:path');
const base = process.env.WORKSPACE_URL || 'http://127.0.0.1:5180';
const out = '/private/tmp/biodemo-landing-depth';
const assert = (value, message) => { if (!value) throw Error(message); };

(async () => {
  fs.mkdirSync(out, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'no-preference' });
  const errors = [];
  page.on('pageerror', error => errors.push(String(error)));
  try {
    await page.goto(base);
    await page.locator('#hero-h').waitFor();
    await page.evaluate(() => document.fonts.ready);
    await page.waitForTimeout(300);

    const pose = selector => page.locator(selector).evaluate(el => getComputedStyle(el).transform);
    const start = {
      atmosphere: await pose('.lp-hero-atmosphere'),
      panel: await pose('.lp-hero-sample'),
    };
    await page.evaluate(() => scrollTo(0, 500));
    await page.waitForTimeout(250);
    const moved = {
      atmosphere: await pose('.lp-hero-atmosphere'),
      panel: await pose('.lp-hero-sample'),
    };
    assert(start.atmosphere !== moved.atmosphere, 'Hero field should move with scroll');
    assert(start.panel !== moved.panel, 'Sample panel should move with scroll');
    assert(await page.locator('.lp-hero-status').count() === 1, 'Hero should state its system boundary');
    assert(await page.locator('.lp-float-a').count() === 0, 'Hero should not float a random image card');

    await page.locator('#architecture').scrollIntoViewIfNeeded();
    await page.waitForTimeout(800);
    assert(await page.locator('.lp-arch-step').count() === 3, 'Architecture should explain three layers');
    assert(await page.locator('.lp-arch-layer').count() === 3, 'Architecture map should show three layers');
    assert(await page.locator('.lp-arch-flow').count() === 2, 'Architecture map should show two handoffs');
    assert(await page.getByText('In this demo', { exact: true }).count() === 1, 'Architecture must state the demo boundary');
    assert(await page.getByText('In a real deployment', { exact: true }).count() === 1, 'Architecture must state the production requirement');
    assert(await page.locator('.lp-arch-sticky').count() === 0, 'Architecture should not pin the screen');
    assert(await page.locator('.lp-arch-map-column').evaluate(el => getComputedStyle(el).position) !== 'sticky', 'Architecture map should scroll with the page');
    assert(await page.getByRole('tablist', { name: 'Explore our product pillars' }).count() === 0, 'The four-pillar product tour should be removed');
    assert(await page.locator('#product').count() === 0, 'The retired product tour section should not remain');

    const fieldPose = () => page.locator('.lp-arch-field').evaluate(el => getComputedStyle(el).transform);
    const mapPose = () => page.locator('.lp-arch-map-column').evaluate(el => getComputedStyle(el).transform);
    const fieldStart = await fieldPose();
    const mapStart = await mapPose();
    await page.evaluate(() => scrollBy(0, 360));
    await page.waitForTimeout(300);
    assert(fieldStart !== await fieldPose(), 'Architecture field should move with scroll');
    assert(mapStart !== await mapPose(), 'Architecture plate should move at a different scroll rate');

    for (let index = 0; index < 3; index += 1) {
      const y = await page.locator('.lp-arch-step').nth(index).evaluate(
        el => el.getBoundingClientRect().top + window.scrollY - window.innerHeight * 0.5,
      );
      await page.evaluate(y => scrollTo(0, y), y);
      await page.waitForTimeout(650);
      const active = await page.locator('.lp-arch-step[data-active="true"]').getAttribute('data-step');
      assert(active === String(index), `Architecture step ${index} should become active`);
    }
    await page.locator('.lp-arch-step').nth(0).scrollIntoViewIfNeeded();
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(out, 'architecture.png') });

    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.evaluate(() => scrollTo(0, 0));
    await page.waitForTimeout(250);
    assert(await pose('.lp-hero-atmosphere') === 'none', 'Reduced motion must remove hero depth');
    assert(await pose('.lp-hero-sample') === 'none', 'Reduced motion must remove panel depth');
    assert(await pose('.lp-arch-field') === 'none', 'Reduced motion must remove architecture depth');
    assert(await pose('.lp-arch-map-column') === 'none', 'Reduced motion must remove architecture plate parallax');
    assert(await page.locator('.lp-hero-scan').evaluate(el => getComputedStyle(el).opacity) === '0', 'Reduced motion must hide the scan line');
    assert(await page.locator('.lp-arch-flow-packet').first().evaluate(el => getComputedStyle(el).opacity) === '0', 'Reduced motion must hide data packets');
    assert(await page.locator('.lp-arch-flow-packet').first().evaluate(el => getComputedStyle(el).animationName) === 'none', 'Architecture packets should not loop continuously');

    for (const width of [320, 390, 768, 1024, 1440]) {
      await page.setViewportSize({ width, height: width < 768 ? 844 : 1000 });
      await page.goto(base);
      await page.locator('#hero-h').waitFor();
      assert(!await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), `Landing overflows at ${width}`);
    }
    assert(errors.length === 0, errors.join('\n'));
    console.log(JSON.stringify({ passed: true, screenshots: out, browserErrors: errors.length }));
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exit(1); });
