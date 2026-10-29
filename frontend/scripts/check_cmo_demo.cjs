/* Browser contract for the guided CHO demo: landing page → September → October → November.
 * Usage: PLAYWRIGHT_MODULE=/path/to/playwright node scripts/check_cmo_demo.cjs http://127.0.0.1:5180
 * Needs a running API with the CHO demo packages. Screenshots go to CMO_CHECK_ARTIFACTS. */
const fs = require('fs');
const path = require('path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const base = process.argv[2] || 'http://127.0.0.1:5180';
const out = process.env.CMO_CHECK_ARTIFACTS || '/private/tmp/biodemo-cmo-demo';
fs.mkdirSync(out, { recursive: true });
const results = [];
const check = (name, ok, detail = '') => { results.push({ name, ok: !!ok, detail }); console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${detail ? ` · ${detail}` : ''}`); };

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('response', async r => { if (r.status() >= 400) errors.push(`${r.status()} ${r.url()} ${await r.text().catch(() => '')}`); });
  const shot = (name, full = true) => page.screenshot({ path: path.join(out, `${name}.png`), fullPage: full });
  let clicks = 0;
  const click = async locator => { clicks++; await locator.click(); };
  const opened = month => page.waitForFunction(m => (document.querySelector('main p')?.textContent ?? '').includes(m) || document.body.innerText.includes(`${m} runs`), month, { timeout: 90000 });
  const settled = () => page.waitForFunction(() => /Verified|to check|Confirm how/.test(document.querySelector('h1')?.textContent ?? '') && !document.body.innerText.includes('Checking the delivery'), null, { timeout: 90000 });
  const heading = () => page.locator('h1').innerText();

  await page.goto(`${base}/`, { waitUntil: 'networkidle' });
  await shot('00-landing');
  check('landing page renders', /AI operating system for pharmaceutical manufacturing/.test(await heading()));
  await click(page.getByRole('link', { name: 'Try the live demo' }).first());
  await page.getByTestId('demo').waitFor();
  await shot('01-start', false);

  // September: first delivery.
  await click(page.getByTestId('demo').getByRole('button', { name: /Start/ }).first());
  await settled();
  await shot('02-september-first');
  for (const editor of await page.locator('[data-mapping-editor]').all()) {
    for (const select of await editor.locator('select').all()) { clicks++; await select.selectOption('__ignore__'); }
  }
  await click(page.getByRole('button', { name: 'Looks right, apply' }));
  await page.waitForFunction(() => !document.querySelector('[data-testid=mappings]'), null, { timeout: 90000 });
  await settled();
  await shot('03-september-applied');
  for (let guard = 0; guard < 15; guard++) {
    const list = page.getByTestId('to-check');
    if (!(await list.count())) break;
    const ignore = list.getByRole('button', { name: 'Ignore from now on' }).first();
    const dismiss = list.getByRole('button', { name: 'Dismiss' }).first();
    const noted = list.getByRole('button', { name: 'Noted' }).first();
    const accept = list.getByRole('button', { name: 'Accept' }).first();
    if (await ignore.count()) await click(ignore);
    else if (await dismiss.count()) { await click(dismiss); await page.getByLabel('Why is this OK?').fill('Not measured at these timepoints'); await click(page.getByRole('button', { name: 'Dismiss' }).first()); }
    else if (await noted.count()) await click(noted);
    else if (await accept.count()) await click(accept);
    else break;
    await page.waitForTimeout(500);
  }
  check('September verified', /Verified/.test(await heading()), `${clicks} clicks so far`);
  await shot('04-september-verified');

  // October: same formats.
  const septemberClicks = clicks;
  await click(page.getByRole('button', { name: /Open October/ }));
  await page.waitForFunction(() => /OCTOBER RUNS|October runs/i.test(document.querySelector('main')?.innerText.slice(0, 400) ?? ''), null, { timeout: 90000 });
  await settled();
  await shot('05-october');
  const october = await heading();
  check('October needs no column decisions', !(await page.getByTestId('mappings').count()), october);
  for (let guard = 0; guard < 6; guard++) {
    const dismiss = page.getByTestId('to-check').getByRole('button', { name: 'Dismiss' }).first();
    if (!(await dismiss.count())) break;
    await click(dismiss); await page.getByLabel('Why is this OK?').fill('Not measured at these timepoints'); await click(page.getByRole('button', { name: 'Dismiss' }).first());
    await page.waitForTimeout(500);
  }
  check('October verified', /Verified/.test(await heading()), `${clicks - septemberClicks} clicks for October`);

  // November: changed layout.
  await click(page.getByRole('button', { name: /Open November/ }));
  await page.waitForFunction(() => /November runs/i.test(document.querySelector('main')?.innerText.slice(0, 400) ?? ''), null, { timeout: 90000 });
  await settled();
  await shot('06-november');
  const text = await page.locator('main').innerText();
  check('November shows the layout change', /Changed since last time/.test(text));
  check('November flags the conflicting lab result', /Conflicting glucose/.test(text));
  check('November flags the missing certificate', /has no certificate of analysis|has no coa/i.test(text));

  await page.goto(`${base}/case-studies/`, { waitUntil: 'networkidle' });
  check('case studies still render', (await page.locator('[data-testid=case-study-story]').count()) === 1);
  check('no browser errors', errors.length === 0, errors.slice(0, 3).join(' | '));
  fs.writeFileSync(path.join(out, 'results.json'), JSON.stringify(results, null, 2));
  await browser.close();
  process.exit(results.every(r => r.ok) ? 0 : 1);
})().catch(e => { console.error(e); process.exit(1); });
