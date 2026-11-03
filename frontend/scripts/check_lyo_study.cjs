/* Verify published numbers against archives, then exercise the rendered page. */
const {execFileSync}=require('node:child_process');
const fs=require('node:fs');
const path=require('node:path');
const crypto=require('node:crypto');
const assert=require('node:assert/strict');
const data=JSON.parse(fs.readFileSync('frontend/data/lyo-study.json'));
const root='docs/case_studies/lyo-study-20261102/';
const hash=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
for(const [file,expected] of Object.entries(data.source_hashes))assert.equal(hash(fs.readFileSync(file)),expected,file);
for(const [cohort,prefix] of [['primary',''],['sensitivity','sensitivity/']]){
  const source=JSON.parse(fs.readFileSync(root+prefix+'summary.json'));
  for(const arm of ['A','C'])for(const task of ['forecast','pretransfer']){
    const truth=source.groups.find(g=>g.source==='agent'&&g.arm===arm&&g.task===task);
    const displayed=data.cohorts[cohort].groups[arm][task];
    for(const key of ['planned','completed','feasible_selections','unsafe_selections','characterize','completion_predictions','completion_eligible'])assert.equal(displayed[key],truth[key],`${cohort}/${arm}/${task}/${key}`);
    assert.equal(displayed.failed,truth.planned-truth.completed);
  }
}
// Independently join archived CSV rows; do not use exporter helpers for this check.
const common=JSON.parse(execFileSync('python3',['-c',`
import csv,json
from pathlib import Path
out={}
for cohort,prefix in [('primary',''),('sensitivity','sensitivity/')]:
 rows=list(csv.DictReader((Path('${root}')/(prefix+'per-case.csv')).open()))
 out[cohort]={}
 for task in ['forecast','pretransfer']:
  by={a:{r['case_id']:float(r['completion_absolute_error_h']) for r in rows if r['source']=='agent' and r['arm']==a and r['task']==task and r['completion_absolute_error_h']!=''} for a in ['A','C']}
  cases=sorted(by['A'].keys() & by['C'].keys())
  out[cohort][task]={'points':[{'case_id':c,'A':by['A'][c],'C':by['C'][c]} for c in cases],'common_predictions':len(cases),'mean':{a:sum(by[a][c] for c in cases)/len(cases) if cases else None for a in ['A','C']}}
print(json.dumps(out))
`],{encoding:'utf8'}));
for(const cohort of ['primary','sensitivity'])assert.deepEqual(data.cohorts[cohort].errors,common[cohort]);
assert.deepEqual(data.budget,{A:{primary:3,sensitivity:8},C:{primary:12,sensitivity:12}});
const publicDir='frontend/public/case-study-results/freeze-drying/';
const manifest=JSON.parse(fs.readFileSync(publicDir+'manifest.json'));
for(const [file,expected] of Object.entries(manifest))assert.equal(hash(fs.readFileSync(publicDir+file)),expected,file);
for(const file of ['primary-report.md','sensitivity-report.md']){
  for(const match of fs.readFileSync(publicDir+file,'utf8').matchAll(/!\[[^\]]*\]\(([^)]+)\)/g))assert(fs.existsSync(path.join(publicDir,match[1])),`${file}: missing ${match[1]}`);
}
assert.equal(hash(fs.readFileSync(publicDir+'illustrative-case.json')),data.source_hashes[root+'illustrative-case.json']);
assert.equal(fs.readFileSync(publicDir+'comparison.json','utf8'),fs.readFileSync('frontend/data/lyo-study.json','utf8'));
if(process.argv.includes('--data-only')){console.log('Archived numbers, common-case joins, source hashes and download checksums passed.');process.exit(0);}

const browser=process.env.AGENT_BROWSER_BIN||'/Users/tejas/.npm/_npx/6de2aa2fded2970c/node_modules/agent-browser/bin/agent-browser-darwin-arm64';
const base=process.argv[2]||'http://127.0.0.1:5186';
const output='/private/tmp/sievance-lyo-study-check';
fs.mkdirSync(output,{recursive:true});
function run(...args){const result=JSON.parse(execFileSync(browser,['--session','sievance-lyo-study-check','--json',...args],{encoding:'utf8',timeout:60000}));assert.equal(result.success,true,JSON.stringify(result));return result.data?.result??result.data;}
const evaluate=code=>run('eval',code);
const clickText=text=>evaluate(`Array.from(document.querySelectorAll('button')).find(b=>b.textContent===${JSON.stringify(text)}).click()`);
try{
  run('open',base+'/case-studies/freeze-drying/');
  run('wait','--fn',`!!document.querySelector('[data-testid=freeze-drying-study]')`);
  assert(evaluate(`document.querySelector('h1').textContent.includes('More usable decisions')`));
  assert(evaluate(`document.querySelector('[data-testid=lyo-headline]').textContent.includes('11/12')`));
  assert.equal(evaluate(`document.querySelectorAll('figure').length`),5);
  assert.equal(evaluate(`!!document.querySelector('#workspace-navigation')`),false);
  assert(evaluate(`document.querySelector('#results').textContent.includes('6 cases × 2 tasks = 12 sessions per arm')`));
  assert(evaluate(`document.querySelector('[data-testid=lyo-error-chart]').textContent.includes('4 shared cases')`));
  clickText('Original · 24 cases');
  run('wait','--fn',`document.querySelector('#results').textContent.includes('24 cases × 2 tasks = 48 sessions per arm')`);
  assert(evaluate(`document.querySelector('#results').textContent.includes('44/48 feasible')`));
  assert(evaluate(`document.querySelector('[data-testid=lyo-error-chart]').textContent.includes('1 shared cases')`));
  clickText('Before transfer');
  run('wait','--fn',`document.querySelector('[data-testid=lyo-error-chart]').textContent.includes('3 shared cases')`);
  clickText('Follow-up · 6 cases');
  run('wait','--fn',`document.querySelector('#results').textContent.includes('6 cases × 2 tasks = 12 sessions per arm')`);
  assert(evaluate(`document.querySelector('[data-testid=lyo-error-chart]').textContent.includes('4 shared cases')`));
  clickText('After 6 h of observations');
  const downloads=evaluate(`(async()=>Promise.all(${JSON.stringify(Object.keys(manifest))}.map(async file=>{const r=await fetch('/case-study-results/freeze-drying/'+file);const bytes=await r.arrayBuffer();const h=await crypto.subtle.digest('SHA-256',bytes);return {file,status:r.status,type:r.headers.get('content-type'),hash:Array.from(new Uint8Array(h),v=>v.toString(16).padStart(2,'0')).join('')}})))()`);
  for(const file of downloads){assert.equal(file.status,200);assert(!file.type?.includes('text/html'));assert.equal(file.hash,manifest[file.file]);}
  evaluate(`document.querySelectorAll('details').forEach(d=>d.open=true)`);
  for(const width of [1440,390,320]){
    run('set','viewport',String(width),'1000');
    for(const id of ['results','budget','decision-example','model-math','evidence']){
      evaluate(`document.getElementById('${id}').scrollIntoView()`);
      assert(evaluate(`document.documentElement.scrollWidth<=innerWidth`),`overflow ${width} ${id}`);
    }
    evaluate(`document.querySelectorAll('details').forEach(d=>d.open=false);window.scrollTo(0,0)`);
    run('screenshot',path.join(output,`top-${width}.png`));
    evaluate(`document.getElementById('model-math').scrollIntoView();document.querySelector('#model-math details').open=true`);
    run('screenshot',path.join(output,`math-${width}.png`));
    evaluate(`document.querySelectorAll('details').forEach(d=>d.open=true)`);
  }
  // Native buttons/details remain reachable and operable from the keyboard.
  evaluate(`document.querySelector('#model-math details').open=false;document.querySelector('#model-math summary').focus()`);
  run('press','Enter');
  assert(evaluate(`document.querySelector('#model-math details').open`));
  run('open',base+'/case-studies/');
  run('wait','--fn',`!!document.querySelector('a[href="/case-studies/freeze-drying/"]')`);
  run('open',base+'/');
  run('wait','--fn',`!!document.querySelector('#case-studies a[href="/case-studies/freeze-drying/"]')`);
  const receipt={passed:true,source_metrics_match:true,common_case_errors_match:true,protocol_and_task_controls:true,downloads:downloads.map(({file,status})=>({file,status})),widths:[1440,390,320],no_page_overflow_with_math_expanded:true,keyboard_details:true,index_and_landing_links:true,public_without_workspace_shell:true};
  fs.writeFileSync(path.join(output,'checks.json'),JSON.stringify(receipt,null,2)+'\n');
  console.log(JSON.stringify(receipt,null,2));
}finally{try{run('close');}catch(error){console.error('Browser cleanup:',error.message);}}
