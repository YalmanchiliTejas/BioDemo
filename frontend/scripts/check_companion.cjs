/* Browser contract against the real local API. Model availability is reported, never simulated. */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

async function main() {
  const base = process.argv[2] || 'http://127.0.0.1:5181';
  const out = process.env.COMPANION_ARTIFACTS || '/private/tmp/biodemo-companion-artifacts';
  fs.mkdirSync(out, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  page.setDefaultTimeout(30000);
  const errors = [], posts = [], checks = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('request', r => { if (r.method() === 'POST' && r.url().endsWith('/messages')) posts.push(r.postDataJSON()); });
  const panel = page.getByTestId('work-companion');
  const composer = page.getByLabel('Describe your process problem or follow up', { exact: true });
  const minimize = () => panel.getByRole('button', { name: 'Minimize companion', exact: true }).click();
  try {
    await page.goto(base + '/home/');
    await page.getByRole('heading', { name: 'What are we working on?' }).waitFor();
    await page.getByRole('button', { name: 'New conversation', exact: true }).click();
    await composer.press('Tab');
    await page.keyboard.press('Meta+j');
    assert.equal(await composer.evaluate(el => el === document.activeElement), true);
    await page.screenshot({ path: path.join(out, 'home-desktop.png') });
    const nav = page.getByRole('navigation', { name: 'Primary', exact: true });
    assert.equal(await nav.getByRole('link').count(), 6); // Five destinations plus settings; tools are disclosed on demand.
    await composer.fill('Keep this draft while I inspect the chart.');
    await nav.locator('summary').filter({ hasText: 'Explore tools' }).click();
    await nav.getByRole('link', { name: 'Process simulation', exact: true }).click();
    await page.waitForURL(/\/process-simulation\/?$/);
    assert.equal(await page.getByRole('heading', { name: 'Predictive process engineering', exact: true }).count(), 1,
      'Process simulation must show its own workspace instead of the companion home.');
    await page.getByRole('button', { name: 'Run transfer comparison', exact: true }).waitFor();
    await page.getByRole('button', { name: 'Start model selection', exact: true }).waitFor();
    assert.equal(await nav.getByRole('link', { name: 'Process simulation', exact: true }).getAttribute('aria-current'), 'page');
    assert.equal(await nav.getByRole('link', { name: 'Companion', exact: true }).getAttribute('aria-current'), null);
    await page.getByRole('button', { name: 'Open companion', exact: true }).click();
    assert.equal(await composer.inputValue(), 'Keep this draft while I inspect the chart.');
    await minimize();
    await page.screenshot({ path: path.join(out, 'process-simulation.png') });
    checks.push('Process simulation opens its own workbench and retains the companion draft alongside it.');
    await nav.getByRole('link', { name: 'Workbench', exact: true }).click();
    await page.getByRole('button', { name: 'Open companion', exact: true }).click();
    assert.equal(await composer.inputValue(), 'Keep this draft while I inspect the chart.');
    await minimize();
    checks.push('A single companion preserves the draft across navigation.');

    const selectedText = await page.getByRole('heading', { name: 'Feed-rate attenuation across CMP-26-10' }).evaluate(el => {
      const range = document.createRange(); range.selectNodeContents(el);
      const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range);
      document.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
      return el.textContent;
    });
    await page.getByRole('button', { name: 'Ask about this', exact: false }).click();
    await page.getByTestId('selected-context').waitFor();
    await page.getByText('Inspect selection', { exact: true }).click();
    assert.equal(await page.getByTestId('selected-context').locator('pre').textContent(), selectedText);
    await page.getByRole('button', { name: 'Remove selected context' }).click();
    assert.equal(await page.getByTestId('selected-context').count(), 0);
    await minimize();
    checks.push('Highlighting text offers an explicit attach action; captured text is inspectable and removable.');

    const chart = page.locator('[data-chart-name="Feed rate (PM-204)"]');
    await chart.scrollIntoViewIfNeeded();
    const svg = chart.getByRole('img', { name: /by elapsed hour/ });
    const box = await svg.boundingBox();
    const start = box.x + 48 + (box.width - 100) * 0.88;
    const finish = box.x + 48 + (box.width - 100) * 0.97;
    await page.mouse.move(start, box.y + 80);
    await page.mouse.down(); await page.mouse.move(finish, box.y + 80, { steps: 8 }); await page.mouse.up();
    await chart.getByRole('button', { name: 'Ask companion about Feed rate (PM-204)', exact: true }).click();
    await page.getByTestId('selected-context').waitFor();
    await page.getByText('Inspect selection', { exact: true }).click();
    const attachment = JSON.parse(await page.getByTestId('selected-context').locator('pre').textContent());
    assert.equal(attachment.unit, 'mL/min');
    assert.equal(attachment.series.length, 3);
    assert(attachment.selected_range[0] > 240 && attachment.selected_range[1] < 280);
    assert(attachment.series.some(s => s.points.length));
    for (const series of attachment.series) for (const point of series.points) {
      assert(point.elapsedHours >= attachment.selected_range[0] && point.elapsedHours <= attachment.selected_range[1]);
    }
    await page.getByText('Inspect selection', { exact: true }).click();
    await page.screenshot({ path: path.join(out, 'selected-chart-desktop.png') });
    await composer.fill('Explain the selected feed-rate change and identify the evidence needed to investigate it.');
    await page.getByRole('button', { name: 'Send message', exact: true }).click();
    await page.getByTestId('conversation-turn').waitFor();
    assert.equal(posts.length, 1);
    assert.equal(posts[0].enable_demo, false);
    assert.equal(posts[0].display_context.kind, 'chart');
    assert(posts[0].display_context.page_path.includes('/workbench/AN-104'));
    assert.deepEqual(JSON.parse(posts[0].display_context.content), attachment);
    await panel.getByText(/The engineering assistant is unavailable/).waitFor();
    checks.push('Chart brush sends bounded raw values, units, series IDs, imputation flags and page/time provenance to the real API; unavailable model route is disclosed.');

    await minimize();
    await nav.getByRole('link', { name: 'Sources', exact: true }).click();
    await page.getByRole('button', { name: 'Open companion', exact: true }).click();
    assert.equal(await page.getByTestId('conversation-turn').count(), 1);
    await page.reload();
    await page.getByRole('button', { name: 'Open companion', exact: true }).click();
    await panel.getByText(/The engineering assistant is unavailable/).waitFor();
    await panel.getByText(/^Chart from Feed rate/).click();
    const saved = JSON.parse(await page.getByTestId('conversation-turn').locator('pre').first().textContent());
    assert.deepEqual(saved, attachment);
    checks.push('Conversation and selected chart survive navigation and reload.');
    await nav.getByRole('link', { name: 'Workbench', exact: true }).click();
    await page.getByRole('button', { name: '[Historian_UP01_Oct.csv §4.2]', exact: true }).click();
    await page.getByRole('complementary', { name: 'Inspector', exact: true }).waitFor();
    assert.equal(await panel.isVisible(), false);
    await page.getByRole('button', { name: 'Open companion', exact: true }).click();
    assert.equal(await page.getByRole('complementary', { name: 'Inspector', exact: true }).count(), 0);
    assert.equal(await page.getByTestId('conversation-turn').count(), 1);
    checks.push('Source evidence opens independently; returning to the companion keeps the saved conversation.');
    await page.getByRole('button', { name: 'Expand companion', exact: true }).click();
    assert((await panel.boundingBox()).width > 700);
    await page.getByRole('button', { name: 'Reduce companion', exact: true }).click();
    await page.keyboard.press('Escape');
    await page.getByRole('button', { name: 'Open companion', exact: true }).waitFor();
    await page.keyboard.press('Meta+j');
    await panel.waitFor({ state: 'visible' });
    await page.keyboard.press('Escape');
    checks.push('Companion expands, minimizes with Escape, and restores focus to its launcher.');

    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByRole('button', { name: 'Open companion', exact: true }).click();
    const mobile = await panel.boundingBox();
    assert(mobile.x >= 0 && mobile.x + mobile.width <= 390);
    assert.equal(await panel.evaluate(el => el.scrollWidth <= el.clientWidth + 1), true);
    await page.screenshot({ path: path.join(out, 'companion-mobile.png') });
    await minimize();
    await page.getByRole('button', { name: 'Toggle navigation' }).click();
    await page.getByRole('navigation', { name: 'Primary', exact: true }).filter({ visible: true }).getByRole('link', { name: 'Companion', exact: true }).click();
    await page.getByRole('button', { name: 'New conversation', exact: true }).click();
    await page.getByRole('heading', { name: 'What are we working on?' }).waitFor();
    await page.screenshot({ path: path.join(out, 'home-mobile.png') });
    checks.push('Companion and navigation work at 390px without panel overflow.');
    assert.deepEqual(errors, []);
    fs.writeFileSync(path.join(out, 'checks.json'), JSON.stringify({ checks, errors }, null, 2));
    console.log(JSON.stringify({ checks, errors, artifacts: out }, null, 2));
  } finally { await browser.close(); }
}
main().catch(e => { console.error(e); process.exitCode = 1; });
