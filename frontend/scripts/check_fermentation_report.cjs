/* Replay actual recorded hosted responses to check presentation; no inference or uplift score. */
const { chromium }=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');

async function main(){
  const root=path.resolve('docs/research/fermentation/results/modal-live-20261027-02');
  const record=JSON.parse(fs.readFileSync(path.join(root,'results.json'),'utf8'));
  const browser=await chromium.launch({headless:true});
  const page=await browser.newPage({viewport:{width:1440,height:1080}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const checked=[];
  try{
    await page.route('**/fermentation/projects/*/agent-assessment',route=>{
      const id=route.request().url().split('/projects/')[1].split('/')[0];
      const row=record.cases.find(c=>c.case_id===id);
      return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(row.agent_plus_same_physics)});
    });
    await page.goto((process.argv[2]||'http://127.0.0.1:5181')+'/tech-transfer/');
    const panel=page.getByTestId('fermentation-transfer');
    await panel.getByRole('heading',{name:'Sulfolobus · 2 L to 20 L and 200 L',exact:true}).waitFor();
    for(const row of record.cases){
      await panel.getByLabel('Fermentation transfer project',{exact:true}).selectOption(row.case_id);
      await panel.getByRole('radio',{name:'Review',exact:true}).click();
      await panel.getByRole('button',{name:'Ask existing Prime agent',exact:true}).click();
      const report=row.agent_plus_same_physics.output.analysis;
      const expected=report.report_type==='partial_investigation'?'partial investigation':'completed';
      await panel.getByText('Prime assessment: '+expected,{exact:true}).waitFor();
      assert.match(await panel.innerText(),/Run execution: completed/);
      if(expected==='partial investigation')assert.match(await panel.innerText(),/scientific verification remains incomplete/);
      assert((await panel.innerText()).includes(report.assessment));
      await panel.screenshot({path:path.join(root,row.case_id+'-report-ui.png')});
      checked.push({case_id:row.case_id,execution:'completed',displayed_assessment:expected});
    }
    assert.deepEqual(errors,[]);
    const result={recorded_response_replay:true,live_inference:false,checked,errors};
    fs.writeFileSync(path.join(root,'report-ui-check.json'),JSON.stringify(result,null,2)+'\n');
    console.log(JSON.stringify(result,null,2));
  }finally{await browser.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
