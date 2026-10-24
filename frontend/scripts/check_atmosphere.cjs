// Verify background controls, accessibility and motion performance against Vite.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs = require('node:fs');
const path = require('node:path');
const base = process.env.WORKSPACE_URL || 'http://127.0.0.1:5180';
const out = '/private/tmp/biodemo-atmosphere-review';
const assert = (value, message) => { if (!value) throw Error(message); };

(async () => {
  fs.mkdirSync(out, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const errors = [];
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'no-preference' });
    page.on('pageerror', e => errors.push(String(e)));
    await page.goto(base);
    await page.locator('#hero-h').waitFor();
    await page.locator('.ambient-image img').evaluate(el => el.decode());
    await page.evaluate(() => document.fonts.ready);
    await page.waitForTimeout(2400);
    assert(await page.locator('.atmosphere').getAttribute('data-active') === 'true', 'Visible background should run');
    const pose = () => page.locator('.ambient-image').evaluate(el => getComputedStyle(el).transform);
    const moving = await pose();
    await page.waitForTimeout(400);
    assert(moving !== await pose(), 'Background should visibly move');

    // Profile a settled loop: transform/opacity motion should not lay out the page.
    const cdp = await page.context().newCDPSession(page);
    const trace = [];
    cdp.on('Tracing.dataCollected', ({ value }) => trace.push(...value));
    await cdp.send('Tracing.start', { categories: 'devtools.timeline', transferMode: 'ReportEvents' });
    await page.waitForTimeout(1500);
    const complete = new Promise(resolve => cdp.once('Tracing.tracingComplete', resolve));
    await cdp.send('Tracing.end');
    await complete;
    const layouts = trace.filter(event => event.name === 'Layout').length;
    const paints = trace.filter(event => event.name === 'Paint').length;
    assert(layouts <= 1, `Background must not cause repeated layout (${layouts})`);

    await page.getByRole('button', { name: 'Pause background animation', exact: true }).click();
    await page.waitForTimeout(100);
    const frozen = await pose();
    await page.waitForTimeout(350);
    assert(frozen === await pose(), 'Pause should freeze the current frame');
    assert(await page.getByRole('button', { name: 'Resume background animation' }).getAttribute('aria-pressed') === 'true', 'Pause must be announced');
    await page.screenshot({ path: path.join(out, 'landing-paused.png') });
    await page.reload();
    await page.getByRole('button', { name: 'Resume background animation' }).waitFor();
    await page.goto(`${base}/app?instant`);
    await page.locator('.studio-home h1').waitFor();
    await page.getByRole('button', { name: 'Resume background animation' }).click();
    await page.waitForTimeout(450);
    const workPose = () => page.locator('.ambient-image').evaluate(el => getComputedStyle(el).transform);
    const workStart = await workPose();
    await page.waitForTimeout(300);
    assert(workStart !== await workPose(), 'Workspace background must resume');
    await page.screenshot({ path: path.join(out, 'workspace-motion.png') });
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.getByRole('button', { name: 'Reduced motion: background animation disabled by system preference' }).waitFor();
    assert(await page.locator('.ambient-image').evaluate(el => getComputedStyle(el).animationName) === 'none', 'Live preference change must disable ambient motion');
    await page.screenshot({ path: path.join(out, 'workspace-reduced.png') });

    await page.goto(base);
    await page.locator('#hero-h').waitFor();
    await page.screenshot({ path: path.join(out, 'landing-reduced.png') });
    await page.emulateMedia({ reducedMotion: 'no-preference' });
    await page.getByRole('button', { name: 'Pause background animation', exact: true }).waitFor();
    await page.evaluate(() => {
      const section = document.querySelector('#thread');
      if (section) window.scrollTo(0, section.getBoundingClientRect().top + scrollY);
    });
    await page.waitForFunction(() => document.querySelector('.atmosphere')?.dataset.active === 'false');
    await page.locator('.lp-thread-grid.reveal').waitFor();
    await page.waitForTimeout(1000);
    assert(await page.locator('.lp-thread-grid.reveal').evaluate(el => getComputedStyle(el).opacity) === '1', 'Revealed content must be readable');

    for (const width of [320, 390, 768, 1024, 1440]) {
      await page.setViewportSize({ width, height: width < 768 ? 844 : 1000 });
      await page.goto(base);
      await page.locator('#hero-h').waitFor();
      await page.locator('.ambient-image img').evaluate(el => el.decode());
      await page.waitForTimeout(1500);
      assert(!await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), `Landing overflow at ${width}`);
      const cta = await page.locator('.lp-hero-copy .goal-submit').boundingBox();
      assert(cta && cta.y + cta.height < (width < 768 ? 844 : 1000), `Hero CTA must fit at ${width}`);
      if ([390, 1440].includes(width)) await page.screenshot({ path: path.join(out, `landing-${width}.png`) });
    }
    assert(errors.length === 0, errors.join('\n'));
    console.log(JSON.stringify({ passed: true, layouts, paints, screenshots: out, browserErrors: errors.length }));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
