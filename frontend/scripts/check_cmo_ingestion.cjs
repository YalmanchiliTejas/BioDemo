// Run against a fresh temporary CMO_INGESTION_ROOT. Requires playwright as a local dev tool.
const {chromium}=require(process.env.CMO_PLAYWRIGHT_MODULE || 'playwright');
(async()=>{
 require('fs').mkdirSync('results/cmo_ingestion/ui',{recursive:true});
 const browser=await chromium.launch({headless:true,channel:'chrome'});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 const errors=[];page.on('pageerror',e=>errors.push(String(e)));
 const assert=(x,m)=>{if(!x)throw new Error(m)};
 await page.goto(process.env.CMO_UI_URL || 'http://127.0.0.1:5180/?tab=ingestion');
 await page.getByRole('heading',{name:'From raw package to verified data'}).waitFor();
 await page.getByLabel('Dataset',{exact:true}).selectOption('sanofi');
 await page.getByLabel('Raw package',{exact:true}).selectOption('sanofi-calibration');
 await page.getByRole('button',{name:'Run ingestion',exact:true}).click();
 await page.getByRole('button',{name:'Run ingestion',exact:true}).waitFor({timeout:90000});
 await page.getByRole('heading',{name:'Layout mappings',exact:true}).waitFor({timeout:90000});
 assert((await page.getByText('0 model calls',{exact:true}).count())>0,'no fabricated model usage');
 await page.getByLabel('Reviewer name').fill('automated-browser-check');
 await page.getByLabel('Review reason').fill('Automated UI verification; not human study evidence');
 // Inspect a real native spreadsheet value and highlight its original cell.
 await page.getByLabel('Review only',{exact:true}).uncheck();
 await page.locator('tbody tr:visible').filter({hasText:'temperature'}).first().click();
 await page.locator('tr.bg-yellow-100').waitFor();
 assert((await page.locator('tr.bg-yellow-100').innerText()).includes('temperature'),'exact source field highlight');
 await page.getByRole('button',{name:'Accept source value',exact:true}).click();
 // Confirm every discovered layout through the actual UI.
 const labels=await page.getByRole('button').filter({hasText:' · draft'}).allTextContents();
 for(const label of labels){
  await page.getByRole('button',{name:label,exact:true}).click();
  await page.getByRole('button',{name:'Confirm mapping version',exact:true}).click();
  await page.getByText('Template version saved.',{exact:false}).waitFor();
 }
 await page.getByLabel('Raw package',{exact:true}).selectOption('sanofi-returning');
 await page.getByLabel('Extraction configuration',{exact:true}).selectOption('D');
 await page.getByRole('button',{name:'Run ingestion',exact:true}).click();
 await page.getByRole('button',{name:'Run ingestion',exact:true}).waitFor({timeout:90000});
 await page.getByRole('heading',{name:'Layout mappings',exact:true}).waitFor({timeout:90000});
 assert((await page.getByText('0 model calls',{exact:true}).count())>0,'template reuse zero model calls');
 const body=await page.locator('body').innerText();
 assert(body.includes('source')||body.includes('Source'),'source review available');
 assert(body.includes('Human minutes: not measured'),'automated UI work not logged as human work');
 await page.locator('tbody tr:visible').first().click();
 await page.getByAltText('Original PDF source page').waitFor();
 await page.waitForFunction(()=>{const i=document.querySelector('img[alt="Original PDF source page"]');return i&&i.complete&&i.naturalWidth>0;});
 assert((await page.getByAltText('Original PDF source page').getAttribute('src')).startsWith('blob:'),'original PDF rendered to a visible page image');
 await page.getByRole('button',{name:'Zoom source page',exact:true}).click();
 await page.screenshot({path:'results/cmo_ingestion/ui/desktop.png',fullPage:true});
 await page.setViewportSize({width:390,height:844});
 await page.screenshot({path:'results/cmo_ingestion/ui/mobile.png',fullPage:true});
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'mobile no horizontal page overflow');
 await page.getByLabel('Raw package',{exact:true}).selectOption('sanofi-changed');
 await page.getByRole('button',{name:'Run ingestion',exact:true}).click();
 await page.getByRole('button',{name:'Run ingestion',exact:true}).waitFor({timeout:90000});
 await page.getByRole('heading',{name:'Layout mappings',exact:true}).waitFor({timeout:90000});
 await page.getByText('DUPLICATE_CONFLICT',{exact:false}).first().waitFor();
 await page.getByText('MISSING_FIELD',{exact:false}).first().waitFor();
 await page.getByText('LAYOUT_CHANGED',{exact:false}).first().waitFor();
 const download=page.waitForEvent('download');
 await page.getByRole('button',{name:'CSV · long',exact:true}).click();
 assert((await download).suggestedFilename().endsWith('.csv'),'real verified-subset export');
 assert(errors.length===0,errors.join('\n'));
 console.log(JSON.stringify({passed:['live ingestion','cell source highlight','source value acceptance','template confirmation','returning zero model calls','original PDF viewer','changed-layout defects','CSV export','automated time exclusion','mobile layout'],javascriptErrors:errors}));
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
