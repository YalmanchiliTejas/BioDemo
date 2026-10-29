/* Real API/browser contract. No response interception and no mock AI performance claims. */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

async function main() {
  const base = process.argv[2] || 'http://127.0.0.1:5180';
  const out = path.resolve('docs/process-simulation/conversation-artifacts');
  fs.mkdirSync(out, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1080 } });
  page.setDefaultTimeout(60000);
  const errors = [], checks = [], posts = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('request', r => { if (r.method() === 'POST') posts.push({ url: r.url(), body: r.postDataJSON() }); });
  try {
    await page.goto(base+'/home/');
    await page.getByRole('heading', { name: /What are we working on/ }).waitFor();
    assert.equal(await page.getByRole('button', { name: 'Save engineer-authored pipeline' }).count(), 0);
    await page.screenshot({ path: path.join(out, 'chat-start.png') });
    checks.push('Conversation is the primary entry, with no model-selection form or save/execute prerequisite.');
    const text = 'We are transferring a freeze-drying process. What equipment characterization is missing before you can simulate it?';
    await page.getByLabel('Describe your process problem or follow up', { exact: true }).fill(text);
    await page.getByRole('button', { name: 'Send message', exact: true }).click();
    await page.getByTestId('conversation-turn').waitFor();
    // This live environment has no qualified route. Do not replace it with a fixture.
    await page.getByText(/The engineering assistant is unavailable/).waitFor();
    const messageRequest = posts.find(p => p.url.endsWith('/messages'));
    assert(messageRequest && messageRequest.body.text === text);
    assert.equal(messageRequest.body.enable_demo, false);
    const id = await page.evaluate(() => localStorage.getItem('biodemo.engineering.conversation.v1'));
    assert(id);
    const headers = { 'X-Tenant-Id': 'demo-northfield', 'X-Actor-Id': 'priya' };
    const api = process.env.NEXT_PUBLIC_LIFESCI_API_URL || 'http://127.0.0.1:8100';
    const saved = await (await page.request.get(`${api}/v1/process-model/conversations/${id}`, { headers })).json();
    assert.equal(saved.turns[0].status, 'agent_unavailable');
    assert.equal(saved.turns[0].artifacts.length, 0);
    checks.push('Free-text request reached the real gateway; unavailable route disclosed without fake planning or simulations.');
    await page.reload();
    await page.getByText(text, { exact: true }).waitFor();
    await page.getByText(/The engineering assistant is unavailable/).waitFor();
    assert.equal(await page.getByTestId('conversation-turn').count(), 1);
    checks.push('Conversation and failure record survive reload.');
    await page.getByRole('button', { name: 'Retry this request', exact: true }).click();
    await page.getByText(/The engineering assistant is unavailable/).waitFor();
    assert.equal(await page.getByTestId('conversation-turn').count(), 1);
    checks.push('Retry preserves the original user turn.');
    await page.screenshot({ path: path.join(out, 'chat-route-unavailable.png') });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByLabel('Describe your process problem or follow up', { exact: true }).waitFor();
    assert.equal(await page.locator('[data-testid="engineering-chat"]').evaluate(el => el.scrollWidth <= el.clientWidth+1), true);
    await page.screenshot({ path: path.join(out, 'chat-mobile.png') });
    checks.push('Composer and conversation fit a 390px viewport.');
    if (process.env.CHAT_FIXTURE_ID) {
      await page.setViewportSize({ width: 1440, height: 1080 });
      await page.evaluate(id => localStorage.setItem('biodemo.engineering.conversation.v1', id), process.env.CHAT_FIXTURE_ID);
      await page.reload();
      await page.getByRole('heading', { name: 'Calculated process forecast' }).first().waitFor();
      await page.getByRole('img', { name: /Predicted interface temperature by elapsed hour/ }).first().waitFor();
      await page.getByRole('heading', { name: 'Operating scenario comparison' }).waitFor();
      await page.getByRole('img', { name: /Scenario vapor-capacity margin by elapsed hour/ }).waitFor();
      await page.getByRole('columnheader', { name: 'Vapor margin (kg/h)' }).waitFor();
      await page.getByRole('button', { name: '3D review', exact: true }).first().click();
      await page.locator('canvas[aria-label="3D vial cutaway showing computed remaining ice and dried layer"]').first().waitFor();
      assert(await page.locator('canvas').first().evaluate(el => el.width > 0 && el.height > 0));
      await page.locator('canvas').first().scrollIntoViewIfNeeded();
      // Annotate this screenshot so it cannot be mistaken for a live LLM run
      // when shared independently of the report. No network data is changed.
      await page.evaluate(() => {
        const label = document.createElement('div');
        label.textContent = 'UI CONTRACT TEST · SCRIPTED PLANNER / REAL SOLVER OUTPUT';
        Object.assign(label.style, { position: 'fixed', top: '62px', right: '20px', zIndex: '10000', background: '#fff7df', color: '#674c0a', padding: '8px 12px', fontSize: '12px', border: '1px solid #e0c67a', borderRadius: '4px' });
        document.body.appendChild(label);
      });
      await page.screenshot({ path: path.join(out, 'chat-test-planner-real-solvers.png') });
      checks.push('Explicitly labeled TEST PLANNER fixture renders actual executed solver artifacts, charts, scenario comparison and WebGL vial review. This is a UI contract check, not live AI performance.');
    }
    assert.deepEqual(errors, []);
    fs.writeFileSync(path.join(out, 'browser-checks.json'), JSON.stringify({ checks, errors, live_route: 'unavailable', full_render_fixture: !!process.env.CHAT_FIXTURE_ID }, null, 2));
    console.log(JSON.stringify({ checks, errors }, null, 2));
  } finally { await browser.close(); }
}
main().catch(e => { console.error(e); process.exitCode = 1; });
