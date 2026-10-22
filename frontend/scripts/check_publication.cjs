const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async()=>{
 const url=process.argv[2]||'http://127.0.0.1:5182/';const baseline=process.argv.includes('--baseline');
 const browser=await chromium.launch({headless:true,channel:'chrome'});
 const page=await browser.newPage({viewport:{width:1363,height:936},reducedMotion:'reduce'});
 const errors=[];page.on('pageerror',error=>errors.push(error.message));
 const assert=(ok,message)=>{if(!ok)throw Error(message)};
 await page.goto(url,{waitUntil:'networkidle'});
 const snapshot=await page.evaluate(()=>fetch('/benchmarks/summary.json').then(response=>response.json()));
 const old=[/released while open/ig,/feed delivery stopped/ig,/toxic event killed/ig,/after (?:its t=)?73\.5/ig,/SEM over timepoints/ig,/\bL[123]\b/g,/timestamp write-order artifacts/ig,/export\/logger stops/ig];
 const scans=[];
 const scan=async name=>{const text=await page.locator('body').innerText();const hits=[];for(const pattern of old){pattern.lastIndex=0;for(const match of text.matchAll(pattern))hits.push({phrase:match[0],context:text.slice(Math.max(0,match.index-85),match.index+100)})}scans.push({name,hits});};
 for(const run of snapshot.runs){
  await page.getByLabel('Recorded benchmark case').selectOption(run.run_id);
  await page.locator(`[data-testid="case-panel"][data-run-id="${run.run_id}"]`).waitFor();
  const experiment=page.getByLabel('Investigation experiment');
  const choices=await experiment.count()?await experiment.locator('option').allTextContents():[''];
  for(const id of choices){
   if(id)await experiment.selectOption(id);
   await page.evaluate(()=>document.querySelectorAll('details').forEach(detail=>detail.open=true));
   await scan(run.case_id+(id?':'+id:''));
   if(!baseline){
    assert(await page.getByTestId('case-panel').getByTestId('publication-review').count()===1,'review visible '+run.case_id);
    const body=await page.locator('body').innerText();
    assert(!body.includes('No publication review is bound'),'hash binding '+run.case_id);
    if(run.case_id==='FRE-04'){
      assert(body.includes('Partial result — scientific and source review pending'),'partial retained');
      assert(!await page.getByRole('heading',{name:'Hypothesis · unverified',exact:true}).count(),'partial hypotheses quarantined');
    }
    if(run.case_id==='CHO-04'&&id==='EXP011'){
      assert(body.includes('90.78% at 51 h to 38.47% at 67 h'),'early decline');
      assert(body.includes('pump/controller records and a feed material balance'),'next checks');
    }
    if(run.case_id==='FRE-06')assert(body.includes('Separate synthetic product/line: Electrolyte Injection, LINE-C'),'negative control scope');
   }
  }
 }
 await page.getByRole('tab',{name:'Synthetic workflow replay',exact:true}).click();
 await page.evaluate(()=>document.querySelectorAll('details').forEach(detail=>detail.open=true));
 if(!baseline)await page.getByTestId('investigation-depth').getByText('Publication review · editorial interpretation',{exact:true}).waitFor();
 await scan('replay:baseline-events');
 await page.getByRole('tab',{name:'Projected assistance',exact:true}).click();
 await scan('replay:projected-events');
 if(!baseline){
  const body=await page.locator('body').innerText();
  assert(!body.includes('Planning sandbox'),'cost model removed');
  assert(!body.includes('Simulated shipped lots awaiting'),'exposure plot removed');
  assert(!body.includes('Synthetic batches since October'),'held strip removed');
  assert(/Illustrative, assumed outcome/i.test(body),'headline outcomes qualified');
  for(const tab of ['Synthetic workflow replay','Measured benchmarks']){
   await page.getByRole('tab',{name:tab,exact:true}).click();await page.setViewportSize({width:390,height:844});
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'mobile overflow '+tab);
  }
  const positives=scans.flatMap(scan=>scan.hits.filter(hit=>!hit.context.includes('do not establish whether physical feed delivery stopped')).map(hit=>({name:scan.name,...hit})));
  assert(positives.length===0,'unqualified old phrases: '+JSON.stringify(positives));
  assert(errors.length===0,'browser errors: '+errors.join(';'));
 }
 console.log(JSON.stringify({url,cases:snapshot.runs.length,rendered_views:scans.length,phrase_matches:scans.filter(scan=>scan.hits.length),browser_errors:errors,baseline},null,2));
 await browser.close();
})().catch(error=>{console.error(error);process.exit(1)});

