/* Real local demo UI/API flow. No intercepted responses or injected sign-in state. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.argv[2] || 'http://127.0.0.1:5189';
const out = process.argv[3] || '/private/tmp/demo-persona-browser';
const personas = [
 ['process_engineer','Run a pharmaceutical process model','chemical.parallel_batch'],
 ['msat','Screen oxygen transfer before a site transfer','fermentation.oxygen_transfer'],
 ['qa','Review the evidence behind a model prediction','chemical.parallel_batch'],
 ['executive','Turn a process prediction into a next decision','chemical.parallel_batch'],
];
(async()=>{
 fs.mkdirSync(out,{recursive:true});
 const browser = await chromium.launch();
 const results=[];
 try {
  for(const [persona,title,mid] of personas){
   const context=await browser.newContext({viewport:{width:1360,height:950}});
   const page=await context.newPage();page.setDefaultTimeout(45000);
   const errors=[]; page.on('pageerror',e=>errors.push(e.message));
   try{
    await page.goto(base+'/demo/');
    await page.locator(`input[type=radio][value="${persona}"]`).check({force:true});
    await page.locator('input[type=checkbox]').check();
    await page.getByRole('button',{name:'Start the demo',exact:true}).click();
    await page.waitForURL('**/home/?scenarios=1');
    await page.getByRole('article',{name:title,exact:true}).waitFor();
    await page.getByRole('link',{name:'Try the model library',exact:true}).click();
    await page.getByTestId('pharmaceutical-model-library').waitFor();
    await page.getByLabel('Model',{exact:true}).selectOption(mid);
    await page.getByRole('button',{name:'Prepare and run analysis',exact:true}).click();
    await page.getByText(/1 solver calls/).waitFor();
    await page.getByRole('link',{name:'Try your own delivery',exact:true}).click();
    await page.getByRole('combobox',{name:'CDMO name',exact:true}).fill('Readiness '+persona);
    await page.locator('input[aria-label="Delivery files"]').setInputFiles({name:'readiness.csv',mimeType:'text/csv',buffer:Buffer.from('batch_id,elapsed_h,pH [pH]\nB,0,7\nB,1,7.1\n')});
    await page.getByRole('button',{name:'Looks right, apply',exact:true}).click();
    await page.getByRole('heading',{name:'Verified. 2 values ready.',exact:true}).waitFor();
    await page.getByRole('button',{name:'Ask the assistant',exact:true}).click();
    await page.getByText(/Verified delivery · Readiness/).waitFor();
    await page.screenshot({path:path.join(out,persona+'.png'),fullPage:true});
    assert.deepEqual(errors,[]);
    await page.reload();
    await page.getByRole('heading',{name:'Verified. 2 values ready.',exact:true}).waitFor();
    await page.setViewportSize({width:390,height:844});
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),'mobile page overflows horizontally');
    await page.screenshot({path:path.join(out,persona+'-mobile.png'),fullPage:true});
    results.push({persona,pass:true,flow:'start -> scenario -> simulation -> upload -> review -> attach -> reload',mobile_width:390});
   }catch(error){results.push({persona,pass:false,error:String(error)});await page.screenshot({path:path.join(out,persona+'-failure.png'),fullPage:true}).catch(()=>{});}
   finally{await context.close();}
   console.log(JSON.stringify(results.at(-1)));
  }
 }finally{await browser.close();fs.writeFileSync(path.join(out,'summary.json'),JSON.stringify(results,null,2));}
 if(results.some(r=>!r.pass))process.exitCode=1;
})().catch(e=>{console.error(e.message);process.exitCode=1;});
