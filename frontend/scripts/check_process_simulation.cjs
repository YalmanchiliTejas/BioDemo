/* Real API/UI check. No response interception. Requires playwright. */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

async function main() {
  const base = process.argv[2] || 'http://127.0.0.1:5180';
  const api = process.env.NEXT_PUBLIC_LIFESCI_API_URL || 'http://127.0.0.1:8100';
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
  const checks = [], errors = [];
  page.on('pageerror', error => errors.push(error.message));
  try {
    await page.goto(base+'/process-simulation/advanced/');
    const main = page.locator('main');
    const response = page.waitForResponse(r => r.url() === api+'/v1/process-model/runs' && r.request().method() === 'POST');
    await page.getByRole('button', { name: 'Run transfer comparison', exact: true }).click();
    const executed = await response;
    assert.equal(executed.status(), 200);
    const run = await executed.json();
    await page.getByRole('heading', { name: 'Operating comparisons', exact: true }).waitFor();
    assert.equal(await page.locator('svg[role=img]').count(), 4);
    assert.match(await main.innerText(), /vapor_capacity at 0.00 h/);
    assert.match(await main.innerText(), /-28°C · 5500 vials · recommended/);
    checks.push('Real solver response, plots, constraints and bounded transfer recommendation rendered');
    const proposedResponse = page.waitForResponse(r => r.url().endsWith('/recommendation') && r.request().method() === 'POST');
    await page.getByRole('button', { name: 'Draft for review', exact: true }).click();
    const proposed = await proposedResponse;
    assert.equal(proposed.status(), 200);
    const proposal = await proposed.json();
    await page.getByRole('status').filter({ hasText: 'Review package saved' }).waitFor();
    assert.equal(proposal.execution_status, 'not_started');
    checks.push('Real review proposal persisted without production dispatch');
    await page.getByLabel('Assumed vapor capacity (kg/h)').fill('0.70');
    assert.match(await main.innerText(), /Inputs changed or result is stale/);
    assert(await page.getByRole('button', { name: 'Draft for review', exact: true }).isDisabled());
    const rerun = page.waitForResponse(r => r.url() === api+'/v1/process-model/runs' && r.request().method() === 'POST');
    await page.getByRole('button', { name: 'Run transfer comparison', exact: true }).click();
    assert.equal((await rerun).status(), 200);
    const old = await page.request.get(api+'/v1/proposals/'+proposal.proposal_id, { headers: { 'X-Tenant-Id': 'demo-northfield', 'X-Actor-Id': 'priya' } });
    assert.equal(old.status(), 200);
    assert.equal((await old.json()).status, 'stale');
    checks.push('Revised source invalidated prior proposal; stale controls blocked drafting');
    await page.getByRole('button', { name: 'CDMO operation', exact: true }).click();
    const cdmoResponse = page.waitForResponse(r => r.url() === api+'/v1/process-model/runs' && r.request().method() === 'POST');
    await page.getByRole('button', { name: 'Run CDMO analysis', exact: true }).click();
    const cdmoHTTP = await cdmoResponse;
    assert.equal(cdmoHTTP.status(), 200);
    const cdmo = await cdmoHTTP.json();
    await page.getByRole('heading', { name: 'Deviation investigation', exact: true }).waitFor();
    assert.match(await main.innerText(), /Capacity is not identifiable/);
    assert.match(await main.innerText(), /critical_temperature at/);
    assert.equal(await page.locator('svg[role=img]').count(), 4);
    assert.equal(cdmo.workspace.diagnosis.hypotheses.length, 3);
    assert(cdmo.workspace.diagnosis.observations.every(row => row.time_h <= 6));
    checks.push('Cutoff-only CDMO evidence, future thermal constraint and three hypotheses rendered');
    assert.deepEqual(errors, []);
    const artifactDir = path.resolve('docs/process-simulation/artifacts');
    fs.mkdirSync(artifactDir, { recursive: true });
    await main.evaluate(el => el.scrollTo(0, 1200));
    await page.screenshot({ path: path.join(artifactDir, 'ui-cdmo.png') });
    const result = { status: 'passed', checks, screenshot: 'ui-cdmo.png', live_api: api, interface_url: base+'/process-simulation/advanced/', simulation_ids: [run.id, cdmo.id], proposal_id: proposal.proposal_id, browser_errors: errors, mocked_responses: false };
    fs.writeFileSync(path.join(artifactDir, 'ui-verification.json'), JSON.stringify(result, null, 2)+'\n');
    console.log(JSON.stringify(result, null, 2));
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error.stack); process.exitCode = 1; });

