/* Real API/browser contract, with published summaries and actual deterministic calculations. */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
async function main() {
  const base=process.argv[2] || 'http://127.0.0.1:5181';
  const out=process.env.FERMENTATION_ARTIFACTS || path.resolve('docs/research/fermentation/results/ui');
  fs.mkdirSync(out,{recursive:true});
  const browser=await chromium.launch({headless:true});
  const page=await browser.newPage({viewport:{width:1440,height:1080}});
  page.setDefaultTimeout(30000);
  const errors=[],checks=[],posts=[];
  page.on('pageerror',e=>errors.push(e.message));
  page.on('request',r=>{if(r.method()==='POST')posts.push(r.url());});
  const panel=page.getByTestId('fermentation-transfer');
  async function tab(name) { await panel.getByRole('radio',{name,exact:true}).click(); }
  async function assess() {
    const response=page.waitForResponse(r=>r.url().endsWith('/evaluate') && r.request().method()==='POST');
    await panel.getByRole('button',{name:'Run deterministic assessment',exact:true}).click();
    const http=await response;assert.equal(http.status(),200,await http.text());
    const value=await http.json();assert.equal(value.execution_status,'completed');return value;
  }
  try {
    await page.goto(base+'/tech-transfer/');
    await panel.getByRole('heading',{name:'Sulfolobus · 2 L to 20 L and 200 L',exact:true}).waitFor();
    await tab('Reactors');
    assert.match(await panel.innerText(),/52 mm/);assert.match(await panel.innerText(),/200 mm/);
    await tab('Assess');
    const sulfur=await assess();
    assert.deepEqual(sulfur.validation.rows.map(r=>r.measured),[40.5,41.1]);
    assert(sulfur.validation.rows[1].relative_error<-.3);
    assert.equal(sulfur.prediction.biology_prediction,null);
    await panel.getByRole('heading',{name:'Withheld experimental comparison'}).waitFor();
    await panel.screenshot({path:path.join(out,'sulfolobus.png')});
    checks.push('Sulfolobus equipment, actual model error, withheld water kLa summaries and conditional strategies render in the existing transfer page.');
    await tab('Review');
    const reviewResponse=page.waitForResponse(r=>r.url().endsWith('/review') && r.request().method()==='POST');
    await panel.getByRole('button',{name:'Draft engineering review',exact:true}).click();
    const proposal=await (await reviewResponse).json();
    assert.equal(proposal.execution_status,'not_started');assert.deepEqual(proposal.required_roles,['engineering']);
    await panel.getByText(new RegExp(proposal.proposal_id)).waitFor();
    const agentResponse=page.waitForResponse(r=>r.url().endsWith('/agent-assessment') && r.request().method()==='POST');
    await panel.getByRole('button',{name:'Ask existing Prime agent',exact:true}).click();
    const attempt=await (await agentResponse).json();
    assert.equal(attempt.scientific_scores,null);
    if(attempt.adapter_result.research_only){
      assert.match(attempt.adapter_result.model,/^modal\//);
      assert(['blocked','completed'].includes(attempt.status));
      if(attempt.status==='blocked')assert.match(attempt.adapter_result.issues.join(' '),/Hosted Modal authentication is unavailable/);
    } else assert.equal(attempt.status,'unresolved');
    await panel.getByText(`Prime assessment: ${attempt.output?.analysis?.report_type==='partial_investigation'?'partial investigation':attempt.status}`,{exact:true}).waitFor();
    checks.push('Version-bound engineering review uses the existing proposal mechanism. The scoped Modal research attempt preserves unknown scientific scores and exposes credential recovery when needed.');
    await panel.getByLabel('Fermentation transfer project',{exact:true}).selectOption('pichia');
    // Tab is retained, while scenario and result state reset.
    await tab('Assess');
    const first=await assess();
    assert.equal(first.prediction.pressure_saturation_ratio_air_only,201.325/151.325);
    assert.equal(first.prediction.equipment_pressure_rating_verified,false);
    assert.deepEqual(first.validation.rows.map(r=>r.measured),[600,900]);
    assert.equal(first.prediction.economics.net_after_extra_feed_usd,null);
    await panel.getByLabel('Oxygen ($/Nm³)',{exact:true}).fill('0.01');
    await panel.getByText(/Inputs changed/).waitFor();
    const second=await assess();
    assert(second.prediction.economics.oxygen_delivery_savings_usd_h<0);
    assert(second.prediction.economics.oxygen_delivery_savings_usd_h<first.prediction.economics.oxygen_delivery_savings_usd_h);
    await panel.screenshot({path:path.join(out,'pichia-cost-sensitivity.png')});
    checks.push('Pichia gauge-pressure physics, empirical endpoint comparator and partial-cost sensitivity execute through the real API; changing oxygen price can reverse the modeled advantage.');
    const chart=panel.locator('[data-chart-name="Enzyme mass · empirical endpoint baseline"]');
    await chart.getByRole('button',{name:/Ask companion about/}).click();
    await page.getByTestId('selected-context').waitFor();
    await page.getByText('Inspect selection',{exact:true}).click();
    const attached=JSON.parse(await page.getByTestId('selected-context').locator('pre').textContent());
    assert(attached.series[0].points[0].receiver_volume_l != null);
    assert.equal(attached.series[0].points[0].elapsedHours,undefined);
    await page.getByTestId('work-companion').getByRole('button',{name:'Minimize companion',exact:true}).click();
    checks.push('Existing companion accepts the comparison chart with volume coordinates instead of mislabeling them as elapsed time.');
    await page.setViewportSize({width:390,height:844});
    await panel.scrollIntoViewIfNeeded();
    assert.equal(await panel.evaluate(el=>el.scrollWidth<=el.clientWidth+1),true);
    await page.locator('#main').evaluate(el=>el.scrollTop=0);
    await page.screenshot({path:path.join(out,'pichia-mobile.png')});
    checks.push('The new transfer panel fits a390px viewport.');
    assert(!posts.some(url=>/dispatch|execute-intent|release_batch/.test(url)));
    assert.deepEqual(errors,[]);
    fs.writeFileSync(path.join(out,'checks.json'),JSON.stringify({checks,errors,real_api:true,production_writes:false},null,2)+'\n');
    console.log(JSON.stringify({checks,errors,artifacts:out},null,2));
  } finally { await browser.close(); }
}
main().catch(e=>{console.error(e);process.exitCode=1;});
