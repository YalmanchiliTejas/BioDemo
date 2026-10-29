/* Real browser and deterministic API checks; no model-performance score is inferred. */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

async function main() {
  const base=process.argv[2] || 'http://127.0.0.1:5181';
  const out=path.resolve('docs/research/fermentation/results/case-study-ui');
  fs.mkdirSync(out,{recursive:true});
  const browser=await chromium.launch({headless:true});
  const page=await browser.newPage({viewport:{width:1440,height:1080}});
  const errors=[],checks=[],writes=[];
  page.on('pageerror',e=>errors.push(e.message));
  page.on('request',r=>{if(r.method()==='POST')writes.push(r.url());});
  const story=page.getByTestId('case-study-story');
  const panel=page.getByTestId('fermentation-transfer');
  async function choose(name){await page.getByRole('navigation',{name:'Select case study'}).getByRole('button',{name}).click();}
  async function calculate(){
    const pending=page.waitForResponse(r=>r.url().endsWith('/evaluate')&&r.request().method()==='POST');
    await panel.getByRole('button',{name:'Run deterministic assessment',exact:true}).click();
    const response=await pending;assert.equal(response.status(),200,await response.text());return response.json();
  }
  try {
    await page.goto(base+'/case-studies/');
    await story.getByRole('heading',{name:'Where the source-only model falls short'}).waitFor();
    assert.equal(await story.locator('pre:visible').count(),0);
    assert.equal(await story.getByRole('textbox').count(),0,'No second chat composer.');
    assert.match(await story.innerText(),/25.4/);assert.match(await story.innerText(),/41.1/);
    await page.screenshot({path:path.join(out,'sulfolobus-desktop.png')});
    checks.push('The default case shows a scientific question, actual held-out comparison, interpretation and next step without opening raw diagnostics.');
    await story.getByRole('button',{name:'Explore scenarios',exact:true}).click();
    const result=await calculate();assert.deepEqual(result.validation.rows.map(r=>r.measured),[40.5,41.1]);
    await story.getByRole('button',{name:'Prime assessment',exact:true}).click();
    await panel.getByRole('button',{name:'Draft engineering review',exact:true}).waitFor();
    assert.equal(await panel.getByRole('button',{name:'Draft engineering review',exact:true}).isEnabled(),true,'Changing workbench section retains the calculated review basis.');
    checks.push('Scenario exploration invokes the existing deterministic API; switching to review retains the current result.');
    await story.getByRole('button',{name:'Close workbench',exact:true}).click();
    await choose('Pichia pastoris Pressure · operating cost');
    await story.getByRole('heading',{name:'Production outcomes across scales'}).waitFor();
    assert.match(await story.innerText(),/40.89/);assert.match(await story.innerText(),/Not measured savings/);
    assert.equal(new URL(page.url()).hash,'#pichia');
    await page.screenshot({path:path.join(out,'pichia-desktop.png')});
    await story.getByRole('button',{name:'Explore scenarios',exact:true}).click();
    const first=await calculate();
    await panel.getByLabel('Oxygen ($/Nm³)',{exact:true}).fill('0.01');
    const second=await calculate();
    assert(first.prediction.economics.oxygen_delivery_savings_usd_h>0);
    assert(second.prediction.economics.oxygen_delivery_savings_usd_h<0);
    checks.push('Pichia shows measured endpoints separately from modeled economics; the real utility sensitivity can reverse the advantage.');
    await story.getByRole('button',{name:'Close workbench',exact:true}).click();
    await story.getByRole('button',{name:'Discuss this case',exact:true}).click();
    await page.getByTestId('selected-context').waitFor();
    await page.getByTestId('work-companion').getByRole('button',{name:'Minimize companion',exact:true}).click();
    checks.push('Discussion attaches retrospective case context to the existing persistent companion.');
    await choose('Factory investigation Evidence · reconstruction');
    assert.match(await story.innerText(),/Fictional operational records/);
    await story.getByText('Explore executed results and source evidence',{exact:true}).click();
    await story.getByRole('heading',{name:'Benchmark results',exact:true}).waitFor();
    await choose('IndPenSim Disturbances · process behavior');
    assert.match(await story.innerText(),/Simulation-derived/);
    await story.getByText('Explore executed results and source evidence',{exact:true}).click();
    await story.getByRole('heading',{name:'Compare historical batches',exact:true}).waitFor();
    checks.push('Legacy factory evidence and IndPenSim results remain inspectable with explicit evidence boundaries.');
    await choose('Sulfolobus Scale-up · oxygen transfer');
    await page.setViewportSize({width:390,height:844});
    await page.locator('#main').evaluate(el=>el.scrollTop=0);
    assert(await story.evaluate(el=>el.scrollWidth<=el.clientWidth+1));
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth));
    await page.screenshot({path:path.join(out,'sulfolobus-mobile.png')});
    checks.push('Case selector, schematic, comparison and next actions fit a 390px viewport.');
    await page.goto(base+'/case-studies/#pichia');
    await story.getByRole('heading',{name:'Production outcomes across scales'}).waitFor();
    assert.deepEqual(errors,[]);
    assert(!writes.some(url=>/dispatch|execute-intent|release_batch/.test(url)));
    fs.writeFileSync(path.join(out,'checks.json'),JSON.stringify({checks,errors,real_api:true,production_writes:false},null,2)+'\n');
    console.log(JSON.stringify({checks,errors,artifacts:out},null,2));
  } finally {await browser.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
