/* Browser contract for /cmo: a real delivery from upload to a verified export, counting clicks.
 * Usage: PLAYWRIGHT_MODULE=/path/to/playwright node scripts/check_cmo_deliveries.cjs http://127.0.0.1:5181 /path/to/delivery-folder
 * Requires a running API (isolated CMO_INGESTION_ROOT) reachable from the page. Writes screenshots to CMO_CHECK_ARTIFACTS. */
const fs = require('fs');
const path = require('path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const base = process.argv[2] || 'http://127.0.0.1:5181';
const folder = process.argv[3];
const out = process.env.CMO_CHECK_ARTIFACTS || '/private/tmp/biodemo-cmo-check';
fs.mkdirSync(out, { recursive: true });
const results = [];
const check = (name, ok, detail = '') => { results.push({ name, ok: !!ok, detail }); console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${detail ? ` · ${detail}` : ''}`); };

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  const shot = name => page.screenshot({ path: path.join(out, `${name}.png`), fullPage: true });
  let clicks = 0;
  const click = async locator => { clicks++; await locator.click(); };

  await page.goto(`${base}/cmo/`);
  await page.getByText('Check a CMO delivery').waitFor();
  await page.getByLabel('Your name').fill('Parker (tester)'); await page.keyboard.press('Enter');
  await page.getByLabel('CMO name').fill('Acme Biologics');
  await shot('01-start');
  const files = fs.readdirSync(folder).filter(f => !f.startsWith('.')).map(f => path.join(folder, f));
  clicks++; await page.locator('input[type=file]').setInputFiles(files);
  await page.getByTestId('mappings').waitFor({ timeout: 60000 });
  check('checking starts on file selection', page.url().includes('run='));
  await shot('02-first-pass');

  for (const editor of await page.locator('[data-mapping-editor]').all()) {
    const operator = editor.getByLabel('Meaning of Operator');
    if (await operator.count()) { clicks++; await operator.selectOption('__ignore__'); }
    if ((await editor.innerText()).includes('Comment')) await click(editor.getByRole('button', { name: 'Not process data' }));
  }
  await click(page.getByRole('button', { name: 'Looks right, apply' }));
  await page.waitForFunction(() => !document.querySelector('[data-testid=mappings]') && /Verified|to check/.test(document.querySelector('h1')?.textContent ?? ''), null, { timeout: 60000 });
  await shot('03-after-apply');

  for (let guard = 0; guard < 20; guard++) {
    const list = page.getByTestId('to-check');
    if (!(await list.count())) break;
    const noted = list.getByRole('button', { name: 'Noted' }).first();
    const accept = list.getByRole('button', { name: 'Accept' }).first();
    const dismiss = list.getByRole('button', { name: 'Dismiss' }).first();
    if (await noted.count()) await click(noted);
    else if (await accept.count()) await click(accept);
    else if (await dismiss.count()) { await click(dismiss); await page.getByLabel('Why is this OK?').fill('Confirmed with CMO'); await click(page.getByRole('button', { name: 'Dismiss' }).first()); }
    else break;
    await page.waitForTimeout(400);
  }
  const heading = await page.locator('h1').innerText();
  check('package verified', /Verified/.test(heading), heading);
  await shot('04-verified');
  await click(page.getByTestId('values').locator('tbody tr').first());
  await page.getByText('Original source').waitFor();
  check('source opens from a data row', true);
  await shot('05-source');
  await page.getByRole('button', { name: 'Close source' }).click();
  const [download] = await Promise.all([page.waitForEvent('download'), click(page.getByRole('button', { name: 'Export CSV' }))]);
  const file = path.join(out, download.suggestedFilename()); await download.saveAs(file);
  const csv = fs.readFileSync(file, 'utf8');
  check('export contains verified values with source hashes', csv.includes('source_sha256') && csv.includes('L-2231'), `${csv.trim().split('\n').length - 1} rows`);
  check('clicks from files to verified export', clicks <= 12, `${clicks} clicks (after typing name and CMO once)`);
  check('no browser errors', errors.length === 0, errors.slice(0, 3).join(' | '));
  fs.writeFileSync(path.join(out, 'results.json'), JSON.stringify(results, null, 2));
  await browser.close();
  process.exit(results.every(r => r.ok) ? 0 : 1);
})().catch(e => { console.error(e); process.exit(1); });
