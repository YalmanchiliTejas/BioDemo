/* Real local browser journey. No route interception or fabricated API responses.
 * Requires browser_server.py and Next dev pointed at its isolated API.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { performance } = require('node:perf_hooks');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const args = process.argv.slice(2);
const arg = (key, fallback) => args.includes(key) ? args[args.indexOf(key) + 1] : fallback;
const root = path.resolve(__dirname, '../..');
const base = arg('--base', 'http://127.0.0.1:5197');
const api = arg('--api', 'http://127.0.0.1:8147');
const output = path.resolve(arg('--output', path.join(root, 'backend/results/browser-journey-20261115/browser')));
const manifestPath = path.join(root, 'backend/results/browser-journey-20261115/data-manifest.json');
const manifest = JSON.parse(fs.readFileSync(manifestPath));
const repeats = Number(arg('--repeats', '3'));
const explain = !args.includes('--skip-explain');
assert(!fs.existsSync(output), 'Choose a new output directory; previous attempts are preserved.');
assert(Number.isInteger(repeats) && repeats > 0 && repeats <= 3);
fs.mkdirSync(output, { recursive: true });
const write = (name, value) => fs.writeFileSync(path.join(output, name), JSON.stringify(value, null, 2) + '\n');
const digest = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const near = (actual, expected) => typeof actual === 'number' && Math.abs(actual - expected) <= Math.max(1e-8, Math.abs(expected) * .005);
const caseRef = manifest.cases.find(c => c.id === 'cho-changed:glucose');
const delivery = manifest.deliveries[caseRef.package];
const keyPath = path.join(root, 'backend/benchmarks/cmo_ingestion/demo', caseRef.package, 'evaluation/answer_key.json');
const key = JSON.parse(fs.readFileSync(keyPath));
const expectedPoints = Object.fromEntries(key.fields.filter(f => f.present && f.parameter === caseRef.parameter
  && [caseRef.left, caseRef.right].includes(f.batch) && !(f.batch === caseRef.right && Number(f.time) === 44))
  .map(f => [`${f.batch}@${Number(f.time)}`, Number(f.value)]));
const protocol = {
  started_at: new Date().toISOString(), mode: 'real_browser_real_local_api', base, api, repeats, optional_live_explanation: explain,
  browser_script_sha256: digest(fs.readFileSync(__filename)), manifest_sha256: digest(fs.readFileSync(manifestPath)),
  reference: caseRef, expected_chart_points: expectedPoints, answer_key_sha256: digest(fs.readFileSync(keyPath)), delivery: { id: delivery.id, run_id: delivery.run_id },
  scenario: 'Select provisional CHO glucose batches, inspect the 44 h duplicate conflict in its original rows and a PDF, record a review decision, reload.',
  decision: 'Do not choose an unsupported conflicting value. Keep the issue open and record the need for clarification.',
  no_mocks: 'No Playwright route interception, response fulfillment, fake model, or service worker. Every application API response comes from the real isolated backend.',
  timing: 'Monotonic time around browser actions through visible DOM completion and two animation frames. Full scripted journey includes automation/assertion overhead; screenshot overhead is separately recorded. Sign-in and optional explanation are separate.',
  limits: ['Script knows where controls are; this is not human usability or decision-time evidence.',
    'Next development server and local SQLite; first route compilation can affect the first attempt.',
    'Real public measurements in fictional delivery layouts with a labelled artificial conflict; calibration/ingestion occurred before the browser journey.',
    'All data stays provisional. No real-world action, review approval, or external message is sent.',
    'Three repeats of one workflow are not three independent scientific cases.']
};
write('protocol.json', protocol);

async function journey(browser, repeat) {
  const dir = path.join(output, `repeat-${repeat}`);
  fs.mkdirSync(dir);
  const row = { repeat, status: 'running', phases: {}, checks: {}, actions: [], api_requests: [], errors: [], failed_requests: [], external_requests: [], external_navigations: [], downloads: [], screenshots: [], screenshot_seconds: 0 };
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, serviceWorkers: 'block' });
  await context.tracing.start({ screenshots: true, snapshots: true, sources: true });
  const page = await context.newPage();
  page.setDefaultTimeout(30000);
  const outstanding = new Set();
  const apiResponses = [];
  let journeyStart;
  const capture = promise => { outstanding.add(promise); promise.finally(() => outstanding.delete(promise)); };
  context.on('page', p => { if (p !== page) row.external_navigations.push({ kind: 'new_page', url: p.url() }); });
  page.on('pageerror', error => row.errors.push(String(error)));
  page.on('download', download => row.downloads.push(download.suggestedFilename()));
  page.on('requestfailed', request => row.failed_requests.push({ url: request.url(), failure: request.failure() }));
  page.on('request', request => {
    if (/^https?:/.test(request.url()) && !request.url().startsWith(base) && !request.url().startsWith(api)) row.external_requests.push(request.url());
  });
  page.on('framenavigated', frame => {
    if (frame === page.mainFrame() && /^https?:/.test(frame.url()) && !frame.url().startsWith(base)) row.external_navigations.push({ kind: 'navigation', url: frame.url() });
  });
  page.on('response', response => {
    if (!response.url().startsWith(api)) return;
    capture((async () => {
      const request = response.request(), at = new URL(response.url()).pathname;
      const record = { path: at, method: request.method(), status: response.status(), resource_type: request.resourceType() };
      if (!at.startsWith('/v1/dev/')) {
        try { record.request = request.postDataJSON(); } catch { /* GET or binary */ }
      }
      try {
        await response.finished();
        const timing = request.timing();
        record.response_end_ms = timing.responseEnd;
        const type = response.headers()['content-type'] || '';
        if (type.includes('application/json') && !at.startsWith('/v1/dev/')) {
          record.response = await response.json();
          apiResponses.push(record);
        } else if (/\/pages\//.test(at)) {
          const bytes = await response.body(); record.bytes = bytes.length; record.sha256 = digest(bytes);
        }
      } catch (error) { record.capture_error = String(error); }
      row.api_requests.push(record);
    })());
  });
  const rendered = () => page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  const phase = async (name, action) => {
    const start = performance.now(), wall = Date.now();
    try { const result = await action(); await rendered(); return result; }
    finally { row.phases[name] = { seconds: (performance.now() - start) / 1000, wall_seconds: (Date.now() - wall) / 1000 }; console.log(JSON.stringify({ repeat, phase: name, seconds: row.phases[name].seconds })); }
  };
  const click = async (label, locator) => { row.actions.push({ kind: 'click', label }); await locator.click(); };
  const fill = async (label, locator, value) => { row.actions.push({ kind: 'type', label }); await locator.fill(value); };
  const select = async (label, locator, value) => { row.actions.push({ kind: 'select', label, value }); await locator.selectOption(value); };
  const shot = async name => {
    const start = performance.now();
    await page.screenshot({ path: path.join(dir, name + '.png'), fullPage: true });
    row.screenshot_seconds += (performance.now() - start) / 1000; row.screenshots.push(`repeat-${repeat}/${name}.png`);
  };
  const pictureResponse = predicate => page.waitForResponse(response => {
    if (!response.url().endsWith('/templates/batch_picture/preview') || response.request().method() !== 'POST') return false;
    try { return predicate(response.request().postDataJSON().selection); } catch { return false; }
  }, { timeout: 45000 });
  const pairVisible = async () => {
    await page.getByTestId('comparison-table').getByText(`${caseRef.right} minus ${caseRef.left}`, { exact: true }).waitFor();
    await page.locator(`[data-point^="${caseRef.left}@"]`).first().waitFor();
    await page.locator(`[data-point^="${caseRef.right}@"]`).first().waitFor();
  };
  try {
    await phase('sign_in', async () => {
      await page.goto(`${base}/sign-in/?next=${encodeURIComponent('/workbench/?datasets=' + delivery.run_id)}`, { waitUntil: 'domcontentloaded' });
      await fill('Local test email', page.getByLabel('Work email'), 'msat@sievance.local');
      await fill('Local test password', page.getByLabel('Password', { exact: true }), 'sievance-local');
      await click('Sign in', page.getByRole('button', { name: 'Sign in', exact: true }));
      await page.getByTestId('workbench').waitFor({ timeout: 60000 });
    });
    row.actions_before_journey = row.actions.length;
    journeyStart = performance.now();
    let selectedPicture;
    await phase('open_data_to_first_chart', async () => {
      await page.goto(`${base}/workbench/?datasets=${encodeURIComponent(delivery.run_id)}`, { waitUntil: 'domcontentloaded' });
      await page.getByLabel('Parameter', { exact: true }).waitFor();
      await select('Parameter', page.getByLabel('Parameter', { exact: true }), 'glucose');
      const next = pictureResponse(s => s.parameter === 'glucose' && s.include_unverified === true);
      await click('Include values still in review', page.getByRole('checkbox', { name: 'Include values still in review' }));
      assert.equal((await next).status(), 200);
      await page.locator('[data-point]').first().waitFor();
      await page.getByTestId('finding-in-review').waitFor();
    });
    await phase('select_batches_to_updated_chart', async () => {
      const batches = page.getByRole('group', { name: 'Batches', exact: true });
      await click(caseRef.left, batches.getByRole('button', { name: caseRef.left, exact: true }));
      const next = pictureResponse(s => s.parameter === 'glucose' && s.batches.length === 2 && s.batches.includes(caseRef.left) && s.batches.includes(caseRef.right));
      await click(caseRef.right, batches.getByRole('button', { name: caseRef.right, exact: true }));
      const response = await next; assert.equal(response.status(), 200); selectedPicture = await response.json();
      await pairVisible();
    });
    const result = selectedPicture.results.compare, summary = result.data.comparison_summary[0];
    row.checks.correct_pair = summary.left_batch === caseRef.left && summary.right_batch === caseRef.right;
    row.checks.correct_mean = near(summary.mean_difference, caseRef.expected.mean_difference);
    row.checks.correct_largest_difference = near(Math.abs(summary.largest_difference.difference), caseRef.expected.largest_abs_difference);
    row.checks.correct_largest_time = caseRef.expected.largest_at.includes(summary.largest_difference.time_h);
    row.checks.correct_matched_samples = summary.matched_times === caseRef.expected.matched_times;
    row.checks.correct_unit = summary.unit === caseRef.unit;
    row.rendered_comparison = await page.getByTestId('comparison-table').innerText();
    row.rendered_chart_points = await page.locator('[data-point]').evaluateAll(nodes => nodes.map(n => ({ point: n.getAttribute('data-point'), label: n.getAttribute('aria-label') })));
    row.checks.all_reference_points_drawn = Object.keys(expectedPoints).length === row.rendered_chart_points.length
      && row.rendered_chart_points.every(p => Object.hasOwn(expectedPoints, p.point));
    row.checks.rendered_point_values_match_key = row.rendered_chart_points.every(p => {
      const value = p.label.match(/ h, ([\d,.-]+) g\/L/);
      return value && near(Number(value[1].replaceAll(',', '')), expectedPoints[p.point]);
    });
    row.checks.only_requested_batches_drawn = row.rendered_chart_points.every(p => [caseRef.left, caseRef.right].some(b => p.point.startsWith(b + '@')));
    row.checks.conflicting_point_excluded = !row.rendered_chart_points.some(p => p.point === caseRef.right + '@44');
    row.checks.no_model_needed_for_chart = selectedPicture.model_calls === 0;
    const conflict = page.getByTestId('finding-conflict').filter({ hasText: `${caseRef.right} has` });
    await conflict.waitFor(); row.rendered_conflict = await conflict.innerText();
    row.checks.conflict_visible = row.rendered_conflict.includes('44 h') && row.rendered_conflict.includes('different glucose');
    await page.getByTestId('region-picture').scrollIntoViewIfNeeded();
    await shot('01-chart-and-conflict');
    await phase('point_to_source_locator', async () => {
      const point = page.locator(`[data-point^="${caseRef.left}@"]`).first();
      await point.focus(); row.actions.push({ kind: 'keyboard', label: 'Open chart point source' }); await page.keyboard.press('Enter');
      await page.getByTestId('source-panel').getByRole('link', { name: 'Open this delivery', exact: true }).first().waitFor();
      row.source_locator = await page.getByTestId('source-panel').innerText();
      assert(row.source_locator.includes('LIMS_offline_results_November.csv'));
    });
    // Add a reference-bearing check before leaving: its saved plan retains the selected evidence.
    await phase('save_evidence_backed_review_step', async () => {
      await click('Add a check to next steps', page.getByRole('button', { name: 'Add a check to next steps', exact: true }).first());
      const step = page.getByTestId('plan-step').first(); await step.waitFor();
      await click('Edit review step', step.getByRole('button', { name: 'Edit step', exact: true }));
      await fill('Review step', step.getByLabel('Step text'), 'Review conflicting glucose at CHO-007-R02 / 44 h against the delivered source before using that sample.');
      await click('Save review step', step.getByRole('button', { name: 'Save', exact: true }));
      await step.getByText('Review conflicting glucose at CHO-007-R02 / 44 h against the delivered source before using that sample.', { exact: true }).waitFor();
    });
    await phase('open_conflict_and_original_rows', async () => {
      await click('Open the delivery to resolve', conflict.getByRole('link', { name: 'Open the delivery to resolve', exact: true }));
      const issue = page.getByTestId('to-check').locator('li').filter({ hasText: `Conflicting glucose for batch ${caseRef.right}` }).first();
      await issue.waitFor({ timeout: 60000 });
      await click('Show conflicting values in original file', issue.getByRole('button', { name: 'Show in file', exact: true }));
      await issue.getByTestId('rows-around').nth(1).waitFor();
      row.original_conflict_context = await issue.innerText();
      row.checks.two_original_rows_visible = await issue.getByTestId('rows-around').count() === 2;
      row.checks.surrounding_rows_visible = await issue.getByTestId('rows-around').first().locator('tbody tr').count() > 1;
    });
    await shot('02-original-conflict-context');
    await phase('open_original_pdf_preview', async () => {
      await click('Open original certificate PDF', page.getByTestId('delivery-files').getByRole('button').filter({ hasText: 'CoA_CHO-007-R01.pdf' }).first());
      const pdf = page.getByTestId('page-at'); await pdf.waitFor();
      await pdf.locator('img').waitFor();
      await page.waitForFunction(() => [...document.querySelectorAll('[data-testid="page-at"] img')].some(img => img.complete && img.naturalWidth > 0));
      row.checks.original_pdf_rendered = true;
    });
    await shot('03-original-pdf');
    row.actions.push({ kind: 'keyboard', label: 'Close PDF preview' }); await page.keyboard.press('Escape');
    await phase('record_decision_and_reload', async () => {
      await click('Return to workbench', page.getByRole('navigation', { name: 'Primary', exact: true }).getByRole('link', { name: 'Workbench', exact: true }));
      const step = page.getByTestId('plan-step').filter({ hasText: 'Review conflicting glucose at CHO-007-R02 / 44 h' }).first();
      await step.waitFor(); await pairVisible();
      await click('Mark source review done', step.getByRole('button', { name: 'Mark done', exact: true }));
      const outcome = 'Reviewed both original rows: they disagree. Keep the 44 h conflict unresolved and obtain clarification before using either value. This completes the source inspection, not the delivery review.';
      await fill('Source review outcome', step.getByLabel('Outcome', { exact: true }), outcome);
      await click('Save review outcome', step.getByRole('button', { name: 'Save as done', exact: true }));
      await page.getByRole('list', { name: 'Steps done', exact: true }).getByText(outcome, { exact: false }).waitFor();
      await page.reload({ waitUntil: 'domcontentloaded' });
      await page.getByRole('list', { name: 'Steps done', exact: true }).getByText(outcome, { exact: false }).waitFor();
      await pairVisible(); await page.getByTestId('finding-conflict').waitFor();
      row.checks.decision_survives_reload = true;
      row.checks.conflict_remains_visible_after_decision = true;
      row.saved_outcome = outcome;
    });
    row.journey_wall_seconds = (performance.now() - journeyStart) / 1000;
    row.journey_without_screenshot_seconds = row.journey_wall_seconds - row.screenshot_seconds;
    row.journey_action_count = row.actions.length - row.actions_before_journey;
    await shot('04-saved-decision');
    if (explain) await phase('optional_modal_explanation', async () => {
      const next = page.waitForResponse(r => /\/workspace-tasks\/results\/[^/]+\/explain$/.test(new URL(r.url()).pathname) && r.request().method() === 'POST', { timeout: 180000 });
      await click('Explain this picture', page.getByRole('button', { name: 'Explain this picture', exact: true }));
      const response = await next;
      row.explanation = { http_status: response.status(), result: await response.json() };
      await page.locator('[data-testid="explanation"], [data-testid="explanation-withheld"]').first().waitFor({ timeout: 30000 });
      row.explanation.rendered_text = await page.getByRole('region', { name: 'Explain this picture' }).innerText();
    });
    if (explain) await shot('05-modal-explanation');
    await Promise.allSettled([...outstanding]);
    const plans = apiResponses.filter(r => /\/v1\/work-plans\/[^/]+$/.test(r.path) && r.method === 'GET').map(r => r.response);
    const plan = plans.findLast(p => p.steps?.some(s => s.outcome === row.saved_outcome));
    row.persisted_plan = plan;
    row.checks.saved_decision_has_evidence = Boolean(plan?.steps.some(s => s.outcome === row.saved_outcome && s.result_id) && plan?.result_ids?.length);
    row.checks.no_external_application = row.external_navigations.length === 0 && row.downloads.length === 0;
    row.checks.no_browser_exception = row.errors.length === 0;
    row.checks.real_api_traffic = row.api_requests.some(r => r.path.endsWith('/batch_picture/preview') && r.status === 200)
      && row.api_requests.some(r => r.path.includes('/rows/') && r.status === 200)
      && row.api_requests.some(r => r.path.includes('/pages/') && r.status === 200);
    row.status = Object.values(row.checks).every(Boolean) ? 'passed' : 'failed';
  } catch (error) {
    row.status = 'error'; row.error = { message: String(error), stack: error.stack };
    if (journeyStart) row.elapsed_at_error_seconds = (performance.now() - journeyStart) / 1000;
    try { row.body_at_error = await page.locator('body').innerText(); await shot('failure'); } catch { /* retain original error */ }
  } finally {
    await Promise.allSettled([...outstanding]);
    await context.tracing.stop({ path: path.join(dir, 'trace.zip') });
    fs.writeFileSync(path.join(dir, 'result.json'), JSON.stringify(row, null, 2) + '\n');
    await context.close();
  }
  console.log(JSON.stringify({ repeat, status: row.status, checks: row.checks, error: row.error?.message, total_seconds: row.journey_wall_seconds }));
  return row;
}

(async () => {
  const browser = await chromium.launch();
  const rows = [];
  try {
    for (let repeat = 1; repeat <= repeats; repeat++) {
      rows.push(await journey(browser, repeat));
      write('report.json', { protocol, planned: repeats, completed: rows.length, passed: rows.filter(r => r.status === 'passed').length, rows });
    }
  } finally { await browser.close(); }
  process.exitCode = rows.every(r => r.status === 'passed') ? 0 : 1;
})().catch(error => { write('fatal.json', { error: String(error), stack: error.stack }); console.error(error); process.exitCode = 1; });
