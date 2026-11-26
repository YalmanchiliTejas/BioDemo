/* Real mounted API/browser acceptance. No request fulfillment or runtime fixtures. */
const fs = require('fs'), path = require('path'), assert = require('assert/strict'), crypto = require('crypto');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || '/Users/tejas/.npm/_npx/e41f203b7505f1fb/node_modules/playwright');
const output = process.argv[2], manifest = JSON.parse(fs.readFileSync(process.argv[3]));
assert(!fs.existsSync(output), 'Choose a fresh output directory; preserve earlier attempts.');
fs.mkdirSync(output, {recursive:true});
const base = 'http://127.0.0.1:5198', api = manifest.api;
const resuming = process.argv.includes('--resume');
const complete = process.argv.includes('--complete');
if(process.argv.includes('--inspect-chart-corrections'))manifest.signal_id=manifest.correction_signal_id;
const batch = manifest.batch || 'SYN-001', equipment = manifest.equipment || 'SYN-V1';
(async()=>{
 const browser=await chromium.launch(), context=await browser.newContext({viewport:{width:1440,height:1000},serviceWorkers:'block'}), page=await context.newPage();
 await context.tracing.start({screenshots:true,snapshots:true,sources:true});
 page.setDefaultTimeout(15000);
 const started=Date.now();
 const evidence={started_at:new Date(started).toISOString(),mode:resuming?'resume_persisted_case':'new_case',requests:[],checks:[],errors:[],external_requests:[]};
 page.on('pageerror',e=>evidence.errors.push(String(e)));
 page.on('response',r=>{if(r.url().startsWith(api)) evidence.requests.push({path:new URL(r.url()).pathname,status:r.status(),method:r.request().method()});});
 page.on('request',r=>{if(/^https?:/.test(r.url())&&!r.url().startsWith(api)&&!r.url().startsWith(base))evidence.external_requests.push(r.url());});
 const check=(name,value)=>{assert(value,name);evidence.checks.push(name);};
 async function login(email,next){await page.goto(`${base}/sign-in/?next=${encodeURIComponent(next)}`);await page.getByLabel('Work email').fill(email);await page.getByLabel('Password',{exact:true}).fill('sievance-local');await page.getByRole('button',{name:'Sign in',exact:true}).click();}
 const button=name=>page.getByRole('button',{name,exact:true});
 try{
 const headers={'X-Tenant-Id':'demo-northfield','X-Actor-Id':'dev-msat'};
 const apiGet=async path=>{const r=await context.request.get(`${api}${path}`,{headers});assert.equal(r.status(),200);return r.json();};
 if(process.argv.includes('--final-review')){
   page.setDefaultTimeout(8000);
   const probe=process.argv.find(v=>v.startsWith('--probe='))?.split('=')[1]||'all';
   const selected=name=>probe==='all'||probe===name;
   const key=path.basename(output);
   const post=async(url,data)=>{const r=await context.request.post(`${api}${url}`,{headers:{...headers,'Idempotency-Key':crypto.randomUUID()},data});assert.equal(r.status(),200,await r.text());return r.json();};
   const created=await post('/v1/quality/workspaces',{site_id:'NF1',title:'Synthetic final review '+key,owner_id:'dev-msat',qa_reviewer_id:'dev-qa',associations:{batch_id:batch}});
   const id=created.case.case_id, url=`/v1/quality/workspaces/${id}`;
   evidence.case_id=id;
   let failures=[];const attempt=async(name,fn)=>{try{await fn();}catch(e){failures.push({name,error:String(e)});}};
   await login('msat@sievance.local',`/quality/?case=${id}`);await page.getByTestId('quality-workspace').waitFor();
   if(selected('catalog'))await attempt('catalog',async()=>{
     await page.getByText('Scientific work and hypotheses',{exact:true}).click();
     await page.getByRole('alert').filter({hasText:'at least one evidence'}).waitFor();
     check('manual workspace initially discloses empty scientific basis',true);
     const response=page.waitForResponse(r=>r.url()===api+url+'/prepare');await button('Prepare evidence').click();await response;
     await page.getByText('Supplied configurations: synthetic-oxygen',{exact:true}).waitFor();
     check('catalog refreshes after source preparation and clears old error',await page.getByRole('alert').filter({hasText:'at least one evidence'}).count()===0);
   });
   if(selected('impact'))await attempt('impact',async()=>{
     const before=await apiGet(url);
     await page.getByText('Assessment and impact',{exact:true}).click();
     for(const [label,value] of [['Event description','Synthetic event'],['Investigation scope',batch],['Technical summary','Cause unresolved'],['Impact assessment','Saved impact '+key]])await page.getByLabel(label,{exact:true}).fill(value);
     const saved=page.waitForResponse(r=>r.url()===api+url+'/assessment');await button('Save assessment').click();await saved;await page.getByTestId('quality-workspace').getAttribute('aria-busy');
     await page.waitForFunction(value=>document.querySelector('[aria-label="Impact assessment"]').value===value&&document.querySelector('[data-testid="quality-workspace"]').getAttribute('aria-busy')==='false','Saved impact '+key,{timeout:15000});
     check('impact survives successful save remount',await page.getByLabel('Impact assessment',{exact:true}).inputValue()==='Saved impact '+key);
     await button('Refresh workspace').click();await page.getByTestId('quality-workspace').waitFor();
     check('impact survives explicit refresh',await page.getByLabel('Impact assessment',{exact:true}).inputValue()==='Saved impact '+key);
     const after=await apiGet(url);check('impact save preserves source-derived candidates',JSON.stringify(after.impact.candidates)===JSON.stringify(before.impact.candidates));
     await page.reload();await page.getByTestId('quality-workspace').waitFor();await page.getByText('Assessment and impact',{exact:true}).click();check('impact survives browser reload',await page.getByLabel('Impact assessment',{exact:true}).inputValue()==='Saved impact '+key);
     await page.getByLabel('Decision reason').fill('Synthetic assignment');await button('Assign investigation').click();await page.getByTestId('workflow-state').getByText('investigation_assigned',{exact:true}).waitFor();
     check('impact survives unrelated triage mutation',await page.getByLabel('Impact assessment',{exact:true}).inputValue()==='Saved impact '+key);
     let review=await apiGet(url);review=await post(url+'/transition',{expected_revision:review.revision,transition:'submit_technical',reason:'Impact review'});await post(url+'/transition',{expected_revision:review.revision,transition:'submit_qa',reason:'Technical assessment for QA'});
     await context.clearCookies();await page.evaluate(()=>localStorage.clear());await login('qa@sievance.local',`/quality/?case=${id}`);await page.getByTestId('quality-workspace').waitFor();await page.getByText('Assessment and impact',{exact:true}).click();
     check('QA read-only impact remains visible',await page.getByLabel('Impact assessment',{exact:true}).isDisabled()&&await page.getByLabel('Impact assessment',{exact:true}).inputValue()==='Saved impact '+key);
     await context.clearCookies();await page.evaluate(()=>localStorage.clear());await login('msat@sievance.local',`/quality/?case=${id}`);await page.getByTestId('quality-workspace').waitFor();
   });
   if(selected('submission'))await attempt('submission',async()=>{
     let w=await post('/v1/quality/workspaces',{site_id:'NF1',title:'Synthetic submission '+key,owner_id:'dev-msat',qa_reviewer_id:'dev-qa'});const submissionUrl='/v1/quality/workspaces/'+w.case.case_id;w=await post(submissionUrl+'/transition',{expected_revision:w.revision,transition:'assign',reason:'Synthetic assignment'});
     w=await post(submissionUrl+'/transition',{expected_revision:w.revision,transition:'submit_technical',reason:'Synthetic submission summary'});
     const review=w.reviews.find(r=>r.decision==='submitted');await page.goto(`${base}/quality/?case=${w.case.case_id}`);await page.getByTestId('quality-workspace').waitFor();await page.getByText('Reviews and activity',{exact:true}).click();
     const row=page.locator('article > p').filter({hasText:'Synthetic submission summary'});await row.waitFor();
     check('compact submission shows submitting person and timestamp',(await row.innerText()).includes(review.submitted_by)&&(await row.innerText()).includes(review.submitted_at));
   });
   if(selected('recurrence'))await attempt('recurrence',async()=>{
     const f=manifest.followup;assert(f,'fresh final review fixture required');
     await page.goto(`${base}/quality/?case=${f.case_id}`);await page.getByTestId('quality-workspace').waitFor();await button('Refresh workspace').click();await page.getByText('Actions and evidence requests',{exact:true}).click();
     const concerns=page.getByTestId('effectiveness-concern');await concerns.first().waitFor();const body=await concerns.allTextContents();const combined=body.join(' ');
     check('adverse post-action evidence reaches follow-up with human assessment next step',combined.includes(f.action_id)&&combined.includes(f.refs.adverse.id)&&combined.includes('Human assessment required'));
     check('uncertain event timing is explicit',combined.includes(f.refs.uncertain.id)&&combined.includes('Timing uncertain'));
     check('normal and known pre-action events excluded from recurrence',!combined.includes(f.refs.normal.id)&&!combined.includes(f.refs.preaction.id));
     const ref=f.refs.adverse;await concerns.getByRole('button',{name:`Inspect ${ref.kind}:${ref.id}@${ref.revision}`,exact:true}).click();await page.getByTestId('source-original').waitFor();check('concern opens exact evidence revision',(await page.getByTestId('source-original').innerText()).includes('OOS'));await button('Close source').click();
     const w=await apiGet(`/v1/quality/workspaces/${f.case_id}`);check('advisory concern does not change effectiveness conclusion',w.actions[0].effectiveness_status==='not_assessed');
   });
   if(selected('people'))await attempt('people',async()=>{
     const fresh=await post('/v1/quality/workspaces',{site_id:'NF1',title:'Synthetic owner recovery '+key,owner_id:'dev-msat',qa_reviewer_id:'dev-qa'});
     // Abort a real lookup to exercise network failure; never fulfill a fabricated response.
     const matcher='**/v1/quality/workspaces/assignees?*';await page.route(matcher,route=>route.abort('failed'));
     await page.goto(`${base}/quality/?case=${fresh.case.case_id}`);await page.getByTestId('quality-workspace').waitFor();await page.getByText('Actions and evidence requests',{exact:true}).click();
     await page.getByRole('alert').filter({hasText:'Could not load follow-up owners'}).waitFor();check('follow-up lookup failure has understandable recovery',await button('Retry follow-up owners').isVisible());
     await page.unroute(matcher);await button('Retry follow-up owners').click();await page.getByLabel('Follow-up owner',{exact:true}).locator('option[value="dev-msat"]').waitFor({state:'attached'});
     check('follow-up retry loads actual authorized owners',await page.getByLabel('Follow-up owner',{exact:true}).isEnabled()&&await page.getByRole('alert').filter({hasText:'Could not load follow-up owners'}).count()===0);
     // Hold genuine requests, navigate with the app, then reject old work after cleanup.
     let hold=true;const held=[];let seenOwners=false,seenCatalog=false;
     const delayed=async route=>{if(hold){held.push(route);if(route.request().url().includes('/assignees'))seenOwners=true;else seenCatalog=true;}else await route.continue();};
     const oldCatalog=`**/v1/quality/workspaces/${fresh.case.case_id}/science/catalog`;
     await page.route(matcher,delayed);await page.route(oldCatalog,delayed);
     await page.reload();await page.getByTestId('quality-workspace').waitFor();
     for(let n=0;n<80&&!(seenOwners&&seenCatalog);n++)await page.waitForTimeout(50);
     check('obsolete request check holds real catalog and owner requests',seenOwners&&seenCatalog);
     hold=false;await page.getByRole('link',{name:'New event',exact:true}).click();await page.getByRole('form',{name:'New Quality workspace'}).waitFor();
     await Promise.all(held.map(route=>route.abort('failed').catch(()=>{})));await page.unroute(matcher,delayed);await page.unroute(oldCatalog,delayed);
     await page.getByLabel('Site',{exact:true}).fill('NF1');await page.getByLabel('Investigation owner',{exact:true}).locator('option[value="dev-msat"]').waitFor({state:'attached'});
     check('late rejected catalog and owner lookups do not contaminate new route',await page.getByRole('form',{name:'New Quality workspace'}).getByRole('alert').count()===0&&await page.getByRole('form',{name:'New Quality workspace'}).isVisible());

   });
   await page.screenshot({path:path.join(output,'final-review.png'),fullPage:true});
   evidence.failures=failures;check('no page exceptions',evidence.errors.length===0);check('no external browser requests',evidence.external_requests.length===0);
   assert.deepEqual(failures,[]);evidence.status='passed';return;
 }
 if(process.argv.includes('--inspect-real-citation')){
   await login('msat@sievance.local',`/investigations/?run=${manifest.run_id}`);await page.getByRole('region',{name:'Report',exact:true}).waitFor();
   check('persisted deterministic executor disclosure is visible',(await page.getByRole('region',{name:'Report',exact:true}).innerText()).includes('No LLM inference ran'));
   const response=page.waitForResponse(r=>r.url().includes(`/investigation-runs/${manifest.run_id}/citations/`));await button(`Source ${manifest.citation_id}`).click();const raw=await response;check('actual run citation route succeeds',raw.status()===200);const source=await raw.json();
   await page.getByTestId('source-original').waitFor();check('citation resolves actual pinned source and coordinate',source.ref.id===manifest.source_ref.id&&source.ref.revision===manifest.source_ref.revision&&source.source_coordinate.json_pointer==='/scientific_models/0/observations/0');
   check('inspector contains actual original observation',JSON.parse(source.content_text).scientific_models[0].observations[0].value===95&&(await page.getByTestId('source-original').innerText()).includes('scientific_models'));
   const downloadPromise=page.waitForEvent('download');await page.getByRole('button',{name:/Download original revision/}).click();await(await downloadPromise).saveAs(path.join(output,'prime-cited-original.json'));
   check('Prime citation downloads exact frozen original bytes',crypto.createHash('sha256').update(fs.readFileSync(path.join(output,'prime-cited-original.json'))).digest('hex')===manifest.source_sha256);
   evidence.run_id=manifest.run_id;evidence.execution_mode=manifest.metrics.execution_mode;check('no page exceptions',evidence.errors.length===0);check('no external browser requests',evidence.external_requests.length===0);evidence.status='passed';await page.screenshot({path:path.join(output,'persisted-run-citation.png'),fullPage:true});return;
 }
 if(process.argv.includes('--regress-create-rejection')){
   await login('msat@sievance.local','/quality/?new=1');await page.getByRole('form',{name:'New Quality workspace'}).waitFor();
   await page.getByLabel('Site',{exact:true}).fill('NF1');await page.getByLabel('Investigation owner',{exact:true}).selectOption('dev-msat');await page.getByLabel('QA reviewer',{exact:true}).selectOption('dev-qa');await page.getByLabel('Event title',{exact:true}).fill('   ');
   const failed=page.waitForResponse(r=>r.url()===`${api}/v1/quality/workspaces`&&r.request().method()==='POST');await button('Create workspace').click();const rejected=await failed;check('blank submitted title receives actual domain rejection',rejected.status()===400);await page.getByRole('form',{name:'New Quality workspace'}).getByRole('alert').waitFor();
   check('definitive rejection keeps text and allows correction',await page.getByLabel('Event title',{exact:true}).inputValue()==='   '&&await button('Create workspace').isVisible()&&await page.getByTestId('create-pending-notice').count()===0);
   const title=`Corrected validation submission ${path.basename(output)}`;await page.getByLabel('Event title',{exact:true}).fill(title);const success=page.waitForResponse(r=>r.url()===`${api}/v1/quality/workspaces`&&r.request().method()==='POST');await button('Create workspace').click();const accepted=await success;check('corrected submission succeeds with a new reviewed intent',accepted.status()===200&&accepted.request().headers()['idempotency-key']!==rejected.request().headers()['idempotency-key']);await page.getByTestId('quality-workspace').waitFor();await page.waitForURL(/\/quality\/\?case=/);
   const caseId=new URL(page.url()).searchParams.get('case'),w=await apiGet(`/v1/quality/workspaces/${caseId}`);check('only corrected content is committed once',w.case.title===title&&w.activity.filter(a=>a.operation==='create').length===1);evidence.case_id=caseId;check('no page exceptions',evidence.errors.length===0);check('no external browser requests',evidence.external_requests.length===0);evidence.status='passed';await page.screenshot({path:path.join(output,'corrected-rejected-title.png'),fullPage:true});return;
 }
 if(process.argv.includes('--regress-create-response-loss')){
   const index=Number((process.argv.find(arg=>arg.startsWith('--loss-index='))||'--loss-index=0').split('=')[1]);const id=manifest.response_loss_signals[index].signal_id;
   const initial=await apiGet(`/v1/signals/${id}`);assert.equal(initial.case_id,null,'Use an unlinked synthetic signal for this attempt');
   await login('msat@sievance.local',`/quality/?signal=${id}`);await page.getByRole('form',{name:'New Quality workspace'}).waitFor();
   await page.getByLabel('Investigation owner',{exact:true}).selectOption('dev-msat');await page.getByLabel('QA reviewer',{exact:true}).selectOption('dev-qa');
   const title=`Original response-loss submission ${index}`;await page.getByLabel('Event title',{exact:true}).fill(title);
   const transmissions=[];page.on('request',request=>{if(request.url()===`${api}/v1/quality/workspaces`&&request.method()==='POST')transmissions.push({body:request.postDataJSON(),key:request.headers()['idempotency-key']});});
   const cdp=await context.newCDPSession(page);await cdp.send('Fetch.enable',{patterns:[{urlPattern:`${api}/v1/quality/workspaces`,requestStage:'Response'}]});
   const lost=new Promise((resolve,reject)=>cdp.on('Fetch.requestPaused',async event=>{
     try{
       if(event.request.method!=='POST'){await cdp.send('Fetch.continueRequest',{requestId:event.requestId});return;}
       assert.equal(event.responseStatusCode,200);const body=JSON.parse(event.request.postData),before=await apiGet(`/v1/quality/workspaces/${body.case_id}`);
       check('real backend committed original case before response loss',before.case.title===title&&before.workflow.activity.filter(a=>a.operation==='create').length===1);
       const key=Object.entries(event.request.headers).find(([name])=>name.toLowerCase()==='idempotency-key')[1];
       evidence.controlled_loss={upstream_status:event.responseStatusCode,case_id:body.case_id,request:body,idempotency_key:key,before_revision:before.revision,before_activity:before.activity};
       await cdp.send('Fetch.failRequest',{requestId:event.requestId,errorReason:'Failed'});await cdp.send('Fetch.disable');resolve({body,key,before});
     }catch(error){reject(error);}
   }));
   await button('Create workspace').click();const {body,key,before}=await lost;await page.getByRole('form',{name:'New Quality workspace'}).getByRole('alert').waitFor();
   check('lost response keeps initiation form and original fields',await page.getByRole('form',{name:'New Quality workspace'}).isVisible()&&await page.getByLabel('Event title',{exact:true}).inputValue()===title);
   const edited=process.argv.includes('--clear-pending-title')?'':`Later unsaved title ${index}`;await page.getByLabel('Event title',{exact:true}).fill(edited);
   const notice=await page.getByTestId('create-pending-notice').innerText();check('pending original and later unsaved edits are explicitly distinguished',notice.includes(title)&&notice.includes('Later form edits are unsaved')&&await page.getByLabel('Event title',{exact:true}).inputValue()===edited);await page.screenshot({path:path.join(output,'original-pending-later-edits.png'),fullPage:true});
   // The RED version has only Create workspace; the fixed UI explicitly labels original-intent retry.
   const retry=page.getByRole('button',{name:/^(Create workspace|Retry original submission)$/});await retry.click();await page.getByTestId('quality-workspace').waitFor();await page.waitForURL(new RegExp(`case=${body.case_id}$`));
   const creates=evidence.requests.filter(r=>r.path==='/v1/quality/workspaces'&&r.method==='POST');const after=await apiGet(`/v1/quality/workspaces/${body.case_id}`);
   check('retry opens same authorized case after lost response',new URL(page.url()).searchParams.get('case')===body.case_id);
   check('retry replays exact original submitted payload and key',transmissions.length===2&&JSON.stringify(transmissions[0].body)===JSON.stringify(transmissions[1].body)&&transmissions[0].key===transmissions[1].key&&transmissions[1].key===key);
   check('typed later edit did not alter committed original intent',after.case.title===title&&after.case.title!==edited);
   check('retry does not repeat workflow creation or activity',after.revision===before.revision&&JSON.stringify(after.activity)===JSON.stringify(before.activity));
   evidence.create_requests=creates;evidence.create_transmissions=transmissions;evidence.case_id=body.case_id;check('no page exceptions',evidence.errors.length===0);check('no external browser requests',evidence.external_requests.length===0);evidence.status='passed';await page.screenshot({path:path.join(output,'recovered-original-case.png'),fullPage:true});return;
 }
 if(process.argv.includes('--regress-navigation')){
   await login('msat@sievance.local',`/quality/?signal=${manifest.signal_id}`);await page.getByTestId('quality-workspace').waitFor();
   const oldCase=new URL(page.url()).searchParams.get('case');await page.getByRole('link',{name:'New event',exact:true}).click();await page.getByLabel('Event title',{exact:true}).waitFor();
   check('new event clears prior signal title and identifiers',await page.getByLabel('Event title',{exact:true}).inputValue()===''&&await page.getByLabel('Batch identifier',{exact:true}).inputValue()===''&&await page.getByLabel('Equipment identifier',{exact:true}).inputValue()==='');
   const cdp=await context.newCDPSession(page);await cdp.send('Network.enable');await cdp.send('Network.emulateNetworkConditions',{offline:false,latency:1000,downloadThroughput:-1,uploadThroughput:-1});
   const delayed=page.waitForRequest(r=>r.url()===`${api}/v1/signals/${manifest.signal_id}`);await page.goto(`${base}/quality/?signal=${manifest.signal_id}`,{waitUntil:'domcontentloaded'});const request=await delayed;await page.getByRole('link',{name:'New event',exact:true}).click();await request.response();await page.waitForLoadState('networkidle');
   check('late real signal response cannot restore old route context',new URL(page.url()).searchParams.get('new')==='1'&&await page.getByLabel('Event title',{exact:true}).inputValue()==='');
   await cdp.send('Network.emulateNetworkConditions',{offline:false,latency:0,downloadThroughput:-1,uploadThroughput:-1});
   await page.getByLabel('Site',{exact:true}).fill('NF1');await page.getByLabel('Event title',{exact:true}).fill(`Manual route regression ${path.basename(output)}`);await page.getByLabel('Investigation owner',{exact:true}).selectOption('dev-msat');await page.getByLabel('QA reviewer',{exact:true}).selectOption('dev-qa');await button('Create workspace').click();await page.getByTestId('quality-workspace').waitFor();await page.waitForURL(/\/quality\/\?case=/);
   const newId=new URL(page.url()).searchParams.get('case'),w=await apiGet(`/v1/quality/workspaces/${newId}`);check('manual event creates independent case without old discovery source',newId!==oldCase&&w.workflow.discovery_refs.length===0&&Object.keys(w.case.associations).length===0);
   evidence.case_id=newId;await page.screenshot({path:path.join(output,'manual-new-case.png'),fullPage:true});
   await page.getByText('Scientific work and hypotheses',{exact:true}).click();await page.getByLabel('Hypothesis or follow-up',{exact:true}).fill('Late mutation stays with its original manual case');
   await cdp.send('Network.emulateNetworkConditions',{offline:false,latency:1000,downloadThroughput:-1,uploadThroughput:-1});
   const mutationRequest=page.waitForRequest(r=>r.url().endsWith(`/${newId}/hypotheses`)&&r.method()==='POST');await button('Record hypothesis').click();const pendingMutation=await mutationRequest;await page.getByRole('link',{name:'New event',exact:true}).click();const mutationResult=await pendingMutation.response();assert.equal(mutationResult.status(),200);await page.waitForLoadState('networkidle');
   check('late mutation completion cannot overwrite new manual route',new URL(page.url()).searchParams.get('new')==='1'&&await page.getByLabel('Event title',{exact:true}).inputValue()==='');
   await page.getByLabel('Site',{exact:true}).fill('NF1');await page.getByLabel('Event title',{exact:true}).fill(`Late creation ${path.basename(output)}`);await page.getByLabel('Investigation owner',{exact:true}).selectOption('dev-msat');await page.getByLabel('QA reviewer',{exact:true}).selectOption('dev-qa');
   const createRequest=page.waitForRequest(r=>r.url()===`${api}/v1/quality/workspaces`&&r.method()==='POST');await button('Create workspace').click();const pendingCreate=await createRequest;await page.getByRole('link',{name:'Quality',exact:true}).click();const createResult=await pendingCreate.response();assert.equal(createResult.status(),200);const created=await createResult.json();await page.getByRole('heading',{name:'Event queue',exact:true}).waitFor();
   check('late creation does not redirect a newly selected queue',!new URL(page.url()).searchParams.has('case')&&!new URL(page.url()).searchParams.has('new')&&await page.getByRole('heading',{name:'Event queue',exact:true}).isVisible());
   check('authorized in-flight creation persists under its own identity',created.case.case_id!==oldCase&&created.case.case_id!==newId&&(await apiGet(`/v1/quality/workspaces/${created.case.case_id}`)).case.title===`Late creation ${path.basename(output)}`);
   await cdp.send('Network.emulateNetworkConditions',{offline:false,latency:0,downloadThroughput:-1,uploadThroughput:-1});check('no page exceptions',evidence.errors.length===0);check('no external browser requests',evidence.external_requests.length===0);evidence.status='passed';return;
 }
 if(process.argv.includes('--regress-retention')){
   const signal=await apiGet(`/v1/signals/${manifest.signal_id}`),caseId=signal.case_id;await login('msat@sievance.local',`/quality/?case=${caseId}`);await page.getByTestId('quality-workspace').waitFor();
   await page.getByText('Scientific work and hypotheses',{exact:true}).click();await page.getByText('Actions and evidence requests',{exact:true}).click();
   for(const spec of [{op:'hypotheses',label:'Hypothesis or follow-up',button:'Record hypothesis',array:'hypotheses',field:'text'},{op:'evidence-requests',label:'Evidence needed',button:'Request evidence',array:'requests',field:'description'},{op:'actions',label:'Action description',button:'Add action',array:'actions',field:'description'}]){
     const value=`Retained ${spec.op} ${path.basename(output)}`;await page.getByLabel(spec.label,{exact:true}).fill(value);if(spec.op==='actions')await page.getByLabel('Action deadline',{exact:true}).fill('2026-12-01');
     const before=await apiGet(`/v1/quality/workspaces/${caseId}`);const changed=await context.request.post(`${api}/v1/quality/workspaces/${caseId}/assessment`,{headers:{...headers,'Idempotency-Key':crypto.randomUUID()},data:{expected_revision:before.revision,assessment:{concurrent_edit:`${spec.op} conflict probe`}}});assert.equal(changed.status(),200);
     const conflict=page.waitForResponse(r=>r.url().endsWith(`/${caseId}/${spec.op}`)&&r.request().method()==='POST');await button(spec.button).click();const rejected=await conflict;check(`${spec.op} received actual backend revision conflict`,rejected.status()===409);
     const rejectedBody=rejected.request().postDataJSON(),rejectedKey=rejected.request().headers()['idempotency-key'];const retainedKey=await page.evaluate(({path,body})=>sessionStorage.getItem(`quality-intent:${JSON.stringify([path,body])}`),{path:new URL(rejected.url()).pathname,body:rejectedBody});check(`${spec.op} failed payload retains original idempotency key`,Boolean(rejectedKey)&&retainedKey===rejectedKey);
     check(`${spec.op} failed save retains exact typed text`,await page.getByLabel(spec.label,{exact:true}).inputValue()===value);
     await page.getByRole('alert').filter({hasText:'Unsaved text is kept'}).waitFor();const refreshed=page.waitForResponse(r=>r.url().endsWith(`/v1/quality/workspaces/${caseId}`)&&r.request().method()==='GET');await button('Refresh workspace').click();await refreshed;await button(spec.button).waitFor();check(`${spec.op} explicit refresh retains typed text`,await page.getByLabel(spec.label,{exact:true}).inputValue()===value);const saved=page.waitForResponse(r=>r.url().endsWith(`/${caseId}/${spec.op}`)&&r.request().method()==='POST');await button(spec.button).click();const retried=await saved;check(`${spec.op} explicit retry succeeds`,retried.status()===200);const retryBody=retried.request().postDataJSON();delete rejectedBody.expected_revision;delete retryBody.expected_revision;check(`${spec.op} explicit retry preserves saved content`,JSON.stringify(rejectedBody)===JSON.stringify(retryBody));
     const after=await apiGet(`/v1/quality/workspaces/${caseId}`);check(`${spec.op} retry stores exactly one entry`,after[spec.array].filter(item=>item[spec.field]===value).length===1);
   }
   evidence.case_id=caseId;evidence.status='passed';await page.screenshot({path:path.join(output,'retained-and-saved.png'),fullPage:true});return;
 }
 if(process.argv.includes('--regress-adoption')){
   assert.equal(manifest.adoption_cases.length,2);const actorHeaders={'X-Tenant-Id':'demo-northfield','X-Actor-Id':'dev-adoption'};
   await login('adoption@sievance.local',`/quality/?case=${manifest.adoption_cases[0].case_id}`);
   const account=await context.request.get(`${api}/v1/account`,{headers:actorHeaders});const membership=await account.json();check('adoption actor first site is NF1',membership.organizations[0].site_ids[0]==='NF1');
   for(const [index,legacy] of manifest.adoption_cases.entries()){
     if(index)await page.goto(`${base}/quality/?case=${legacy.case_id}`);
     await page.getByRole('form',{name:'New Quality workspace'}).waitFor();
     check(`${legacy.case_id} prefills actual case site and people`,await page.getByLabel('Site',{exact:true}).inputValue()===legacy.site_id&&await page.getByLabel('Investigation owner',{exact:true}).inputValue()==='dev-adoption'&&await page.getByLabel('QA reviewer',{exact:true}).inputValue()==='dev-qa');
     check(`${legacy.case_id} classification comes from structured context`,await page.getByLabel('Category',{exact:true}).inputValue()===legacy.category);
     check(`${legacy.case_id} preserves risk priority deadline`,await page.getByLabel('Initial risk',{exact:true}).inputValue()==='Awaiting qualified assessment'&&await page.getByLabel('Priority',{exact:true}).inputValue()==='high'&&await page.getByLabel('Investigation deadline',{exact:true}).inputValue()==='2026-12-01');
     const known=await page.getByTestId('initiation-context').innerText();check(`${legacy.case_id} shows linked material product supplier context`,['SYN-P','SYN-M','SYN-SUP','0007'].every(value=>known.includes(value)));
     await button('Create workspace').click();await page.getByTestId('quality-workspace').waitFor();await page.waitForURL(new RegExp(`case=${legacy.case_id}$`));
     const response=await context.request.get(`${api}/v1/quality/workspaces/${legacy.case_id}`,{headers:actorHeaders});assert.equal(response.status(),200);const w=await response.json();
     check(`${legacy.case_id} adopts same identity and associations`,w.case.case_id===legacy.case_id&&w.case.associations.product_id==='SYN-P'&&w.case.associations.material_id==='SYN-M'&&w.case.associations.supplier_id==='SYN-SUP'&&w.case.associations.lot_id==='0007');
     check(`${legacy.case_id} retains pinned original and exact deadline`,w.sources.some(s=>s.ref.id===legacy.source_ref.id&&s.ref.revision===1&&s.current_revision===2)&&w.case.deadline==='2026-12-01T09:30:00+00:00');
     await page.getByText('Assessment and impact',{exact:true}).click();check(`${legacy.case_id} OOS lab controls follow actual classification`,await page.getByLabel('Initial laboratory conclusion',{exact:true}).count()===(legacy.category==='oos'?1:0));
     await page.getByText('Sources and timeline',{exact:true}).click();await page.getByRole('button',{name:`Inspect evidence · ${legacy.source_ref.id}`,exact:true}).click();await page.getByTestId('source-original').getByText(legacy.original_text,{exact:true}).waitFor();check(`${legacy.case_id} inspects old original bytes through real endpoint`,true);await button('Close source').click();
     await page.screenshot({path:path.join(output,`${legacy.case_id}.png`),fullPage:true});
   }
   check('no page exceptions',evidence.errors.length===0);check('no external browser requests',evidence.external_requests.length===0);evidence.status='passed';return;
 }
 await login('msat@sievance.local',`/signals/?id=${manifest.signal_id}`);
 const expectedSignal=await apiGet(`/v1/signals/${manifest.signal_id}`);
 await page.getByRole('heading',{name:expectedSignal.rule,exact:true}).waitFor({timeout:60000});
 await page.getByTestId('signal-observation-point').first().waitFor();
 const signalResponse=await context.request.get(`${api}/v1/signals/${manifest.signal_id}`,{headers:{'X-Tenant-Id':'demo-northfield','X-Actor-Id':'dev-msat'}});const persistedSignal=await signalResponse.json();evidence.source_observations=persistedSignal.observations;
 const actualPoints=persistedSignal.observations.filter(p=>typeof(p.original_value??p.value)==='number'&&p.event_time);
 check('all real historian points without a delivery, retaining source revisions',actualPoints.length>=3&&await page.getByTestId('signal-observation-point').count()===actualPoints.length);
 const pointLabels=await page.getByTestId('signal-observation-point').evaluateAll(nodes=>nodes.map(n=>n.getAttribute('aria-label')));
 check('source times values units and revisions match persisted observations',actualPoints.every(p=>pointLabels.some(label=>label.includes(`${p.event_time}: ${p.original_value??p.value} ${p.original_unit??p.unit}`)&&label.includes(`revision ${p.evidence_ref.revision}`))));
 if(process.argv.includes('--inspect-chart-corrections')){
   const charts=page.getByTestId('signal-observations').locator('svg');check('original units stay on separate axes',await charts.count()===2);check('mixed source revisions retain explicit correction notice',await page.getByText(/^Multiple revisions of/).count()===1);check('conflicting source versions are not connected into one trajectory',await charts.locator('polyline').count()===1);check('all corrected originals remain individually selectable',await charts.getByTestId('signal-observation-point').count()===3);evidence.status='passed';await page.screenshot({path:path.join(output,'source-corrections-and-units.png'),fullPage:true});return;
 }
 if(process.argv.includes('--inspect-multipoint')){
   const series=await page.getByTestId('signal-observations').locator('svg').evaluateAll(nodes=>nodes.map(n=>n.querySelectorAll('[data-testid=signal-observation-point]').length));
   check('same-unit same-batch observations from distinct originals form a multi-point trend',series.length===1&&series[0]===actualPoints.length);
   for(const p of actualPoints){const label=`${p.batch_id??persistedSignal.subject.id} ${p.event_time}: ${p.original_value??p.value} ${p.original_unit??p.unit} ${p.evidence_ref.id} revision ${p.evidence_ref.revision}`;await page.getByRole('button',{name:label,exact:true}).click();await page.getByText(`Selected ${label} · ${persistedSignal.subject.id}`,{exact:true}).waitFor();}
   check('every selected trend point preserves its own exact source revision',true);evidence.status='passed';await page.screenshot({path:path.join(output,'multipoint-source-trend.png'),fullPage:true});return;
 }
 await page.getByTestId('signal-observation-point').last().click();
 await page.getByRole('link',{name:'Prepare Quality workspace',exact:true}).click();
 if(!resuming){
 check('batch and equipment context carried into initiation',await page.getByLabel('Batch identifier',{exact:true}).inputValue()===batch&&await page.getByLabel('Equipment identifier',{exact:true}).inputValue()===equipment);
 await page.getByLabel('Investigation owner',{exact:true}).selectOption('dev-msat');
 await page.getByLabel('QA reviewer',{exact:true}).selectOption('dev-qa');
 await button('Create workspace').click();
 }else check('resume explicitly requires existing signal case',Boolean(persistedSignal.case_id));
 await page.getByTestId('quality-workspace').waitFor();
 await page.waitForURL(/\/quality\/\?case=/);
 const caseId=new URL(page.url()).searchParams.get('case');check('same case link',Boolean(caseId));evidence.case_id=caseId;
 if(resuming)check('resume preserves original case identity',caseId===persistedSignal.case_id);
 if(process.argv.includes('--inspect-blockers')){check('blocker names evidence and responsible owner',/Evidence needed: Calibration certificate · owner dev-msat/.test(await page.getByTestId('quality-gaps').innerText()));await page.screenshot({path:path.join(output,'blocker-readable.png'),fullPage:true});check('no browser exceptions',evidence.errors.length===0);check('no external browser requests',evidence.external_requests.length===0);evidence.status='passed';return;}
 await page.screenshot({path:path.join(output,'workspace-compact.png'),fullPage:true});
 await page.goto(`${base}/signals/?id=${manifest.signal_id}`);const sameCase=page.getByRole('link',{name:'Continue this case in Quality',exact:true});await sameCase.waitFor();check('signal reopens same case',new URL(await sameCase.getAttribute('href'),base).searchParams.get('case')===caseId);await sameCase.click();await page.getByTestId('quality-workspace').waitFor();
 if(!resuming){await page.getByLabel('Decision reason').fill('Prepare local deviation based on observed excursion');await button('Assign investigation').click();await button('Prepare evidence').click();}
 await page.getByText('Sources and timeline',{exact:true}).click();await page.getByTestId('source-row').first().waitFor();await page.getByRole('button',{name:`Inspect evidence · ${manifest.source_ref.id}`,exact:true}).click();
 await page.getByTestId('source-original').getByText(/Synthetic acceptance inputs/).waitFor();
 check('pinned actual original', (await page.getByTestId('source-original').innerText()).includes('scientific_models'));
 const downloadPromise=page.waitForEvent('download');await page.getByRole('button',{name:/Download original revision/}).click();const originalDownload=await downloadPromise;await originalDownload.saveAs(path.join(output,'original-pinned-source'));
 check('download exact original bytes',crypto.createHash('sha256').update(fs.readFileSync(path.join(output,'original-pinned-source'))).digest('hex')===manifest.source_sha256);
 check('untrusted source script escaped',await page.evaluate(()=>window.__sourceExecuted===undefined));
 await button('Close source').click();
 await page.getByText('Assessment and impact',{exact:true}).click();
 if(!resuming){
 await page.getByLabel('Event description',{exact:true}).fill(`Oxygen fell to 2 mg/L in synthetic batch ${batch}.`);
 await page.getByLabel('Investigation scope',{exact:true}).fill(`${batch}, vessel ${equipment}, 10:00–12:00 source time.`);
 await page.getByLabel('Technical summary',{exact:true}).fill('Observed decline; cause remains unresolved.');
 await page.getByLabel('Limitations',{exact:true}).fill('Synthetic data; calibration not supplied.');
 await page.getByLabel('Impact assessment',{exact:true}).fill(`${batch} reviewed; distribution unknown, external QA disposition pending.`);
 await button('Save assessment').click();
 }else check('resume retains saved event description',await page.getByLabel('Event description',{exact:true}).inputValue()===`Oxygen fell to 2 mg/L in synthetic batch ${batch}.`);
 await page.getByText('Scientific work and hypotheses',{exact:true}).click();if(!resuming)await button('Run supplied scientific configurations').click();
 await page.getByTestId('science-run').first().waitFor();check('real source-complete science completed', /completed/.test(await page.getByTestId('science-run').first().innerText()));
 await page.getByRole('cell',{name:'100',exact:true}).first().waitFor();
 if(!resuming){await page.getByLabel('Hypothesis or follow-up').fill('Transfer limitation remains unconfirmed.');await button('Record hypothesis').click();}await page.getByText('Transfer limitation remains unconfirmed. · hypothesis',{exact:true}).waitFor();
 await page.getByText('Actions and evidence requests',{exact:true}).click();
 if(!resuming){await page.getByLabel('Evidence needed').fill('Calibration certificate');await button('Request evidence').click();}
 await page.getByText('Calibration certificate',{exact:true}).waitFor();
 if(!resuming){await page.getByLabel('Action description').fill('Review vessel calibration before disposition');await page.getByLabel('Action deadline').fill('2026-12-01');await button('Add action').click();}else await page.getByText('Review vessel calibration before disposition',{exact:true}).waitFor();
 await page.reload();await page.getByTestId('quality-workspace').waitFor();
 await page.getByText('Assessment and impact',{exact:true}).click();check('scope survives reload',await page.getByLabel('Investigation scope',{exact:true}).inputValue()===`${batch}, vessel ${equipment}, 10:00–12:00 source time.`);
 await page.getByLabel('Decision reason').fill('Ready for inspection with open evidence request');await button('Submit technical review').click();
 await page.getByLabel('Decision reason').fill('Technical review completed for QA inspection');await button('Submit QA review').click();
 await page.screenshot({path:path.join(output,'owner-review.png'),fullPage:true});
 await context.clearCookies();await page.evaluate(()=>localStorage.clear());
 await login('qa@sievance.local',`/quality/?case=${caseId}`);await page.getByTestId('quality-workspace').waitFor();
 await page.getByLabel('Decision reason').fill('Review incomplete material evidence');
 check('QA approval blocked by unresolved evidence with reason supplied',await button('Approve local preparation').isDisabled());
 await page.getByLabel('Decision reason').fill('Obtain calibration certificate before local approval');await button('Return for more evidence').click();await page.getByTestId('workflow-state').getByText('returned',{exact:true}).waitFor();
 await page.getByText('Reviews and activity',{exact:true}).click();await page.getByText('Obtain calibration certificate before local approval',{exact:false}).first().waitFor();
 const exportResponsePromise=page.waitForResponse(r=>r.url().endsWith(`/v1/quality/workspaces/${caseId}/export`));const packageDownloadPromise=page.waitForEvent('download');
 await button('Export local package').click();await page.getByTestId('export-label').waitFor();const exportedPackage=await(await exportResponsePromise).json();const packageDownload=await packageDownloadPromise;await packageDownload.saveAs(path.join(output,'local-pending-package.json'));
 check('local pending handoff label',/pending_external_approval/.test(await page.getByTestId('export-label').innerText()));
 check('scope and description retained in export',exportedPackage.workspace.assessment.scope===`${batch}, vessel ${equipment}, 10:00–12:00 source time.`&&exportedPackage.workspace.assessment.event_description===`Oxygen fell to 2 mg/L in synthetic batch ${batch}.`);
 check('export retains review history and no external receipt',exportedPackage.workspace.reviews.length>=2&&exportedPackage.external_receipt===null);
 let r=await context.request.get(`${api}/v1/quality/workspaces/${caseId}`,{headers});let w=await r.json();
 check('persisted request/action/review',w.requests.length===1 && w.actions.length===1 && w.reviews.length>=2);
 check('source revision preserved',w.sources.some(s=>s.ref.id===manifest.source_ref.id&&s.ref.revision===manifest.source_ref.revision));
 check('hypothesis retained separately from science',w.hypotheses.some(h=>h.text==='Transfer limitation remains unconfirmed.'));
 check('owner lacks QA approval action',!w.allowed_actions.includes('approve_local'));
 r=await context.request.post(`${api}/v1/quality/workspaces/${caseId}/transition`,{headers:{...headers,'Idempotency-Key':'unauthorized-browser-proof'},data:{expected_revision:w.revision,transition:'approve_local',reason:'Forbidden'}});check('real backend denies owner QA approval',r.status()===403);
 check('no browser exceptions',evidence.errors.length===0);
 check('no external browser requests',evidence.external_requests.length===0);
 await page.screenshot({path:path.join(output,'qa-return.png'),fullPage:true});
 if(complete){
   await context.clearCookies();await page.evaluate(()=>localStorage.clear());await login('msat@sievance.local',`/quality/?case=${caseId}`);await page.getByTestId('quality-workspace').waitFor();
   await page.getByText('Actions and evidence requests',{exact:true}).click();const followup=page.locator('details').filter({has:page.locator('summary').filter({hasText:'Actions and evidence requests'})});
   await followup.getByRole('checkbox',{name:`evidence:${manifest.calibration_ref.id}@${manifest.calibration_ref.revision}`,exact:true}).check();await button('Resolve request with selected evidence').click();await button('Record completion with selected evidence').click();
   await page.getByText('Assessment and impact',{exact:true}).click();await page.getByLabel('Limitations',{exact:true}).fill('Calibration original reviewed; conditional calculation remains synthetic and unqualified. Root cause unresolved.');await button('Save assessment').click();
   await page.getByLabel('Decision reason').fill('Resubmit with reviewed calibration and completion evidence');await button('Submit technical review').click();await page.getByLabel('Decision reason').fill('Current evidence technically assessed');await button('Submit QA review').click();
   await context.clearCookies();await page.evaluate(()=>localStorage.clear());await login('qa@sievance.local',`/quality/?case=${caseId}`);await page.getByTestId('quality-workspace').waitFor();await page.getByLabel('Decision reason').fill('Complete current submission accepted locally only');await button('Approve local preparation').click();await page.getByTestId('workflow-state').getByText('handoff_pending',{exact:true}).waitFor();
   const response=page.waitForResponse(r=>r.url().endsWith(`/v1/quality/workspaces/${caseId}/export`));const download=page.waitForEvent('download');await button('Export local package').click();const final=await(await response).json();await(await download).saveAs(path.join(output,'complete-local-pending-package.json'));
   check('fresh workflow reaches complete local pending handoff',final.workspace.completeness.complete&&final.workspace.workflow.state==='handoff_pending'&&final.external_receipt===null);
   check('returned snapshot survives complete new review',final.workspace.reviews.filter(r=>r.decision==='submitted').length===2&&final.workspace.reviews.some(r=>r.decision==='return'));
   check('action completion is source-backed without effectiveness conclusion',final.workspace.actions[0].status==='completed'&&final.workspace.actions[0].completion_refs[0].id===manifest.calibration_ref.id&&final.workspace.actions[0].effectiveness_status==='not_assessed');
   check('completed export contains pinned originals for every manifested source',final.source_records.length===final.source_manifest.length&&final.source_records.some(s=>s.ref.id===manifest.calibration_ref.id&&s.content_text));
   await page.screenshot({path:path.join(output,'complete-local-handoff.png'),fullPage:true});
 }
 evidence.status='passed';
 }catch(e){evidence.status='failed';evidence.error=String(e);evidence.url=page.url();evidence.body=await page.locator('body').innerText();await page.screenshot({path:path.join(output,'failure.png'),fullPage:true});process.exitCode=1;}
 finally{evidence.completed_at=new Date().toISOString();evidence.elapsed_seconds=(Date.now()-started)/1000;await context.tracing.stop({path:path.join(output,'trace.zip')});fs.writeFileSync(path.join(output,'result.json'),JSON.stringify(evidence,null,2));await browser.close();console.log(JSON.stringify(evidence));}
})().catch(error=>{fs.writeFileSync(path.join(output,'startup-error.json'),JSON.stringify({error:String(error),stack:error.stack},null,2));console.error(error);process.exitCode=1;});
