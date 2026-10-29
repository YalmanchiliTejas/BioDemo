/* Live pipeline and 3D check; no response interception or mocked solver outputs. */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

async function main() {
  const base = process.argv[2] || 'http://127.0.0.1:5180';
  const api = process.env.NEXT_PUBLIC_LIFESCI_API_URL || 'http://127.0.0.1:8100';
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1500, height: 1100 } });
  const errors = [], presetRequests = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => { if (request.method() === 'POST' && request.url() === api+'/v1/process-model/runs') presetRequests.push(request.url()); });
  page.setDefaultTimeout(60000);
  const checks = [];
  const postResponse = suffix => page.waitForResponse(response => response.url().endsWith(suffix) && response.request().method() === 'POST');
  const headers = { 'X-Tenant-Id': 'demo-northfield', 'X-Actor-Id': 'priya' };
  try {
    await page.goto(base+'/process-simulation/advanced/');
    await page.getByRole('button', { name: 'CDMO operation', exact: true }).click();
    const contextResponse = postResponse('/contexts');
    await page.getByRole('button', { name: 'Start model selection', exact: true }).click();
    const contextHTTP = await contextResponse;
    assert.equal(contextHTTP.status(), 200);
    const context = await contextHTTP.json();
    assert.equal(context.classification, 'analysis_inputs_not_predictions');
    assert.equal(presetRequests.length, 0);
    await page.getByRole('heading', { name: 'Model selection and analysis pipeline', exact: true }).waitFor();
    checks.push('Started from versioned inputs without executing the hard-wired preset comparison');
    const plannedResponse = postResponse('/agent-plan');
    await page.getByRole('button', { name: 'Ask agent to plan analysis', exact: true }).click();
    const agentPlanHTTP = await plannedResponse;
    assert.equal(agentPlanHTTP.status(), 200);
    const agentPlan = await agentPlanHTTP.json();
    if (agentPlan.status === 'agent_unavailable') {
      assert.equal(agentPlan.plan, null);
      await page.getByText('Agent planning unavailable', { exact: true }).waitFor();
      checks.push('Real planning route unavailability was disclosed without a fabricated plan');
    } else {
      assert.equal(agentPlan.status, 'plan_created');
      assert.equal(agentPlan.plan.authored_by.kind, 'agent');
      checks.push('Actual agent-created plan was persisted');
    }
    await page.getByRole('checkbox', { name: 'Use explicit thermal assumptions for the transient model', exact: true }).check();
    await page.getByLabel('Pipeline calibration', { exact: true }).selectOption('kv_scale');
    const planResponse = postResponse('/pipelines');
    await page.getByRole('button', { name: 'Save engineer-authored pipeline', exact: true }).click();
    const planHTTP = await planResponse;
    assert.equal(planHTTP.status(), 200);
    const plan = await planHTTP.json();
    assert.equal(plan.authored_by.kind, 'person');
    assert.equal(plan.inputs[0].kind, 'physical_analysis_context');
    assert.equal(plan.pinned_models.length, 2);
    assert.equal(plan.source_snapshot.prior_diagnostic_fits_reused, false);
    const executionResponse = postResponse('/execute');
    await page.getByRole('button', { name: 'Execute saved pipeline', exact: true }).click();
    const executionHTTP = await executionResponse;
    assert.equal(executionHTTP.status(), 200);
    const analysis = await executionHTTP.json();
    assert.equal(analysis.execution_status, 'completed');
    assert.equal(analysis.models.length, 2);
    assert(analysis.models.every(model => model.status === 'completed' && model.holdout_evaluation.coverage === 1));
    assert(analysis.training_observations.every(row => row.time_h <= 3));
    assert(analysis.holdout_observations.every(row => row.time_h > 3 && row.time_h <= 6));
    assert(analysis.resource_usage.solver_calls <= analysis.resource_usage.maximum_solver_calls);
    await page.getByRole('heading', { name: 'Holdout residuals', exact: true }).waitFor();
    checks.push('Executed both selected models with separate fit/holdout windows, uncertainty and bounded solver use');
    await page.getByLabel('Model for 3D and uncertainty', { exact: true }).selectOption('lyo.transient_lumped');
    const canvas = page.locator('canvas[aria-label^="3D vial cutaway"]');
    await canvas.waitFor({ state: 'visible' });
    await page.waitForFunction(() => !!document.querySelector('canvas[data-frame-time-h]'));
    const before = Number(await canvas.getAttribute('data-frame-time-h'));
    const slider = page.getByLabel('3D review time', { exact: true });
    await slider.focus();
    await slider.press('End');
    await page.waitForFunction(value => Number(document.querySelector('canvas')?.dataset.frameTimeH) > value, before);
    await slider.press('Home');
    for (let i = 0; i < 4; i++) await slider.press('PageUp');
    const root = path.resolve('docs/process-simulation/model-selection-artifacts');
    fs.mkdirSync(root, { recursive: true });
    await page.getByRole('heading', { name: '3D engineering review · lyo.transient_lumped', exact: true }).locator('..').screenshot({ path: path.join(root, 'ui-vial-review.png') });
    checks.push('Real WebGL 3D scene loaded; time scrubber updated executed model states and review image was captured');
    const assessedResponse = postResponse('/agent-assessment');
    await page.getByRole('button', { name: 'Ask agent to assess results', exact: true }).click();
    const assessmentHTTP = await assessedResponse;
    assert.equal(assessmentHTTP.status(), 200);
    const assessment = await assessmentHTTP.json();
    assert(['agent_unavailable', 'interpretation_created'].includes(assessment.status));
    if (assessment.status === 'agent_unavailable') assert.equal(assessment.interpretation, null);
    const reviewedResponse = postResponse('/review');
    await page.getByRole('button', { name: 'Create engineering review', exact: true }).click();
    const reviewHTTP = await reviewedResponse;
    assert.equal(reviewHTTP.status(), 200);
    const review = await reviewHTTP.json();
    assert.deepEqual(review.required_roles, ['engineering']);
    assert.equal(review.execution_status, 'not_started');
    checks.push('Saved engineering review through the existing proposal service without dispatch');
    await page.getByText('Propose a new model adapter for review', { exact: true }).click();
    await page.getByLabel('Proposed model title', { exact: true }).fill('Review only distributed model');
    await page.getByLabel('Sources and license', { exact: true }).fill('Proposed original implementation; independent source and license review required.');
    await page.getByLabel('Governing equations', { exact: true }).fill('Conservation of energy, Fourier heat conduction, and a moving sublimation interface.');
    await page.getByLabel('Required inputs and units (one per line)', { exact: true }).fill('Conductivity W/(m K)\nGeometry m\nInitial temperature K');
    await page.getByLabel('Verification and independent validation plan', { exact: true }).fill('Verify balances and mesh/time convergence, then compare with prespecified independent temperature measurements.');
    const adapterResponse = postResponse('/adapter-proposals');
    await page.getByRole('button', { name: 'Submit adapter review proposal', exact: true }).click();
    const adapterHTTP = await adapterResponse;
    assert.equal(adapterHTTP.status(), 200);
    const adapter = await adapterHTTP.json();
    assert.equal(adapter.payload.registry_status, 'not_registered');
    assert.equal(adapter.execution_status, 'not_started');
    const catalog = await page.request.get(api+'/v1/process-model/catalog', { headers });
    assert.equal((await catalog.json()).models.length, 2);
    checks.push('New adapter proposal retained equations, units, license and validation plan without registering or executing code');
    await page.getByLabel('Planned shelf at 8 h (°C)', { exact: true }).fill('-16');
    const changedResponse = postResponse('/contexts');
    await page.getByRole('button', { name: 'Start model selection', exact: true }).click();
    assert.equal((await changedResponse).status(), 200);
    for (const [url, id] of [['/v1/process-model/pipelines/', plan.id], ['/v1/process-model/analyses/', analysis.id], ['/v1/proposals/', review.proposal_id]]) {
      const response = await page.request.get(api+url+id, { headers });
      assert.equal(response.status(), 200);
      assert.equal((await response.json()).status, 'stale');
    }
    checks.push('Source revision change invalidated the prior pipeline, scientific result and engineering review');
    assert.deepEqual(errors, []);
    const verification = { status: 'passed', checks, browser_errors: errors, mocked_responses: false, planning_status: agentPlan.status,
      assessment_status: assessment.status, source_context_id: context.id, plan_id: plan.id, analysis_id: analysis.id,
      review_id: review.proposal_id, adapter_proposal_id: adapter.proposal_id, solver_calls: analysis.resource_usage.solver_calls,
      screenshot: 'ui-vial-review.png' };
    fs.writeFileSync(path.join(root, 'ui-verification.json'), JSON.stringify(verification, null, 2)+'\n');
    console.log(JSON.stringify(verification, null, 2));
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error.stack); process.exitCode = 1; });

