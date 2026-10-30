const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 const base=process.argv[2]||'http://127.0.0.1:5180';
 const out='/private/tmp/biodemo-combined-case-study';fs.mkdirSync(out,{recursive:true});
 try {
  await page.goto(base+'/case-studies/');
  const study=page.getByTestId('combined-physics-study');await study.waitFor();
  await study.getByRole('heading',{name:'Can physics help an agent respond when a process changes?',exact:true}).waitFor();
  assert.equal(await study.locator('figure').count(),21);
  const truth=JSON.parse(fs.readFileSync('docs/case_studies/interventions-pensim-20261029/analysis.json'));
  const summary=await(await page.request.get(base+'/case-study-results/combined-physics/summary.json')).json();
  for(const key of ['groups','paired_intervals','paired_case_differences','original_recipe_reference','outcomes_by_recoverability'])assert.deepEqual(summary.intervention[key],truth[key]);
  const cho=JSON.parse(fs.readFileSync('docs/case_studies/physics-improvements-20261028/analysis.json')).real_CHO;
  assert.deepEqual(summary.cho,cho.summary.filter(r=>r.metric==='absolute_error'));
  const upper=JSON.parse(fs.readFileSync('docs/case_studies/model-repair-continuous-20261028/analysis.json'));
  assert.deepEqual(summary.upper_bound,upper.primary);
  const text=await study.innerText();
  for(const value of ['326.2','358.3','38 / 72','27 / 72','+32.1','-1.0','Both agents missed all 26 necessary stops','Average prediction error increased','No new comparative intervention study','586 kg'])assert(text.includes(value),value);
  for(const id of ['intro','results','reference','physical','reading'])assert(await study.locator('#combined-'+id).count());
  for(const file of ['intervention-report.md','upper-bound-report.md','physical-report.md','cho-report.md','summary.json'])assert.equal((await page.request.get(base+'/case-study-results/combined-physics/'+file)).status(),200);
  await page.screenshot({path:out+'/desktop-intro.png'});
  await study.locator('#combined-results').scrollIntoViewIfNeeded();await page.screenshot({path:out+'/desktop-results.png'});
  await study.locator('#combined-physical').scrollIntoViewIfNeeded();await page.screenshot({path:out+'/desktop-physical.png'});
  await study.getByRole('button',{name:'Explore the complete earlier benchmark'}).click();
  const earlier=page.getByTestId('physics-benchmark-study');await earlier.waitFor();assert.equal(await earlier.locator('figure').count(),16);
  await earlier.getByRole('button',{name:'SMPL',exact:true}).click();assert.equal(await earlier.locator('figure').count(),8);
  await study.getByRole('button',{name:'Close the complete earlier benchmark'}).click();assert.equal(await earlier.count(),0);
  await page.setViewportSize({width:390,height:844});
  for(const id of ['intro','results','reference','physical','reading']) {
   await study.locator('#combined-'+id).scrollIntoViewIfNeeded();
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),'document overflow');
   assert(await study.evaluate(e=>e.scrollWidth<=e.clientWidth+1),'study overflow '+id);
   await page.screenshot({path:out+'/mobile-'+id+'.png'});
  }
  await page.goto(base+'/case-studies/#pichia');await page.getByRole('heading',{name:'Can air pressure replace supplemental oxygen?',exact:true}).waitFor(); assert.equal(await page.getByTestId('combined-physics-study').count(),0);
  await page.goto(base+'/case-studies/#physics-value');await page.getByTestId('combined-physics-study').waitFor();
  assert.deepEqual(errors,[]);
  fs.writeFileSync(out+'/checks.json',JSON.stringify({passed:true,figures:21,source_values_match:true,downloads:true,mobile_no_overflow:true,earlier_filters:true,hash_navigation:true,errors},null,2));
  console.log(out+'/checks.json');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
