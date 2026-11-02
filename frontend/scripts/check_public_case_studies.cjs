/* Rendered navigation, data provenance, interactions and responsive checks. */
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const browser = process.env.AGENT_BROWSER_BIN || '/Users/tejas/.npm/_npx/6de2aa2fded2970c/node_modules/agent-browser/bin/agent-browser-darwin-arm64';
const base = process.argv[2] || 'http://127.0.0.1:5184';
const session = 'sievance-public-study-check';
const output = '/private/tmp/sievance-public-study-check';
fs.mkdirSync(output, { recursive: true });
function run(...args) {
  const text = execFileSync(browser, ['--session', session, '--json', ...args], { encoding:'utf8', timeout:60000 });
  const response = JSON.parse(text);
  assert.equal(response.success, true, text);
  return response.data?.result ?? response.data;
}
const evaluate = code => run('eval', code);
const truth = JSON.parse(fs.readFileSync('docs/case_studies/decision-followup-20261101/analysis.json'));
const exported = JSON.parse(fs.readFileSync('frontend/public/case-study-results/decision-followup/summary.json'));
assert.deepEqual(exported.summaries, truth.summaries);
assert.deepEqual(exported.contrasts, truth.paired_contrasts);
assert.equal(exported.cases.length, 24);
for (const file of ['frontend/lib/navigation.ts','frontend/lib/routes.ts']) {
  assert(!fs.readFileSync(file,'utf8').includes("href: '/case-studies'"), 'workspace entry remains: '+file);
}
try {
  run('open', base+'/case-studies/');
  run('wait','--fn','!!document.querySelector("[data-testid=decision-study]")');
  run('snapshot','-i');
  const initial = evaluate(`({heading:document.querySelector('h1')?.textContent,figures:document.querySelectorAll('[data-testid=decision-study] figure').length,workspace:!!document.querySelector('#workspace-navigation'),archiveOpen:document.querySelector('#earlier-studies').open})`);
  assert.equal(initial.heading,'Case studies');assert.equal(initial.figures,5);assert.equal(initial.workspace,false);assert.equal(initial.archiveOpen,false);
  const downloads = evaluate(`(async()=>{const files=['summary.pdf','report.md','analysis.json','summary.json','decisions.csv','methodology.md'];return Promise.all(files.map(async file=>{const r=await fetch('/case-study-results/decision-followup/'+file);return {file,status:r.status,type:r.headers.get('content-type')}}))})()`);
  assert(downloads.every(r=>r.status===200&&!r.type?.includes('text/html')));
  // Check the actual served bytes; the browser CLI's JSON bridge rounds a few
  // floating-point values by one ULP, which is not a source-data discrepancy.
  const servedHash = evaluate(`(async()=>{const r=await fetch('/case-study-results/decision-followup/summary.json');const h=await crypto.subtle.digest('SHA-256',await r.arrayBuffer());return Array.from(new Uint8Array(h),v=>v.toString(16).padStart(2,'0')).join('')})()`);
  assert.equal(servedHash,crypto.createHash('sha256').update(fs.readFileSync('frontend/public/case-study-results/decision-followup/summary.json')).digest('hex'));
  evaluate(`document.querySelector('#study-evidence details summary').click()`);
  assert.equal(evaluate(`document.querySelectorAll('#study-evidence tbody tr').length`),24);
  evaluate(`Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='Model-assisted violations').click()`);
  assert.equal(evaluate(`document.querySelectorAll('#study-evidence tbody tr').length`),1);
  assert.equal(evaluate(`document.querySelector('#study-evidence tbody th').textContent`),'PF-51008');
  evaluate(`Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='All decisions').click()`);
  evaluate(`Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='All inventory').click()`);
  assert(evaluate(`Array.from(document.querySelectorAll('figure')).find(f=>f.textContent.includes('Inventory needs')).textContent`).includes(truth.summaries.A.mean_mass_kg.toFixed(1)));
  for (const width of [1440,390,320]) {
    run('set','viewport',String(width),'900');
    for (const id of ['study-results','study-actions','study-failure','study-evidence']) {
      evaluate(`document.getElementById('${id}').scrollIntoView()`);
      assert(evaluate(`document.documentElement.scrollWidth<=innerWidth`),'overflow at '+width+' '+id);
    }
    evaluate(`document.getElementById('study-results').scrollIntoView()`);
    run('screenshot',path.join(output,`results-${width}.png`));
  }
  run('open',base+'/case-studies/#pichia');
  run('wait','--fn',`!!document.querySelector('[data-testid=archived-case-study]')&&document.querySelector('[data-testid=archived-case-study]').textContent.includes('Can air pressure replace supplemental oxygen?')`);
  assert(evaluate(`document.querySelector('#earlier-studies').open`));
  run('open',base+'/studies/');
  run('wait','--fn',`!!document.querySelector('[data-testid=decision-study]')`);
  run('open',base+'/');
  run('wait','--fn',`!!document.querySelector('#case-studies')`);
  assert(evaluate(`!!Array.from(document.querySelectorAll('nav[aria-label=Primary] a')).find(a=>a.textContent==='Case studies'&&a.getAttribute('href')==='/case-studies/')`));
  assert(evaluate(`!!document.querySelector('#case-studies a[href="/case-studies/"]')`));
  evaluate(`document.querySelector('#case-studies').scrollIntoView()`);
  run('set','viewport','1440','1000');
  run('screenshot',path.join(output,'landing-entry.png'));
  const receipt = {passed:true,source_metrics_match:true,public_without_workspace_shell:true,downloads,case_filter:true,inventory_toggle:true,widths:[1440,390,320],no_horizontal_overflow:true,legacy_alias:true,published_case_deep_link:true,landing_direct_entry:true,workspace_nav_entries_removed:true};
  fs.writeFileSync(path.join(output,'checks.json'),JSON.stringify(receipt,null,2)+'\n');
  console.log(JSON.stringify(receipt,null,2));
} finally { try { run('close'); } catch (error) { console.error('Browser cleanup:',error.message); } }
