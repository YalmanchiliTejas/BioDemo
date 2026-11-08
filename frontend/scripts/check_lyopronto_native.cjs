/* Independently recompute reference quantities and published denominators. */
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'../..'),dir=path.join(root,'frontend/public/research-results/lyopronto-native');
const read=name=>JSON.parse(fs.readFileSync(path.join(dir,name),'utf8'));
const data=read('results.json'),refs=read('native-reference.json'),inputs=read('public-inputs.json'),manifest=read('manifest.json'),budget=read('usage-receipts.json');
for(const [name,hash] of Object.entries(manifest))assert.equal(crypto.createHash('sha256').update(fs.readFileSync(path.join(dir,name))).digest('hex'),hash,name);
assert.equal(data.total,24);assert.equal(data.recorded,24);assert.equal(data.rows.length,24);assert.equal(new Set(data.rows.map(r=>r.id)).size,24);
assert.equal(data.passed,data.rows.filter(r=>r.passed).length);
for(const f of data.families){const rows=data.rows.filter(r=>r.family===f.id);assert.equal(f.total,rows.length);assert.equal(f.passed,rows.filter(r=>r.passed).length);}
const near=(a,b)=>assert(Math.abs(a-b)<1e-9*Math.max(1,Math.abs(b)),`${a} != ${b}`);
function metrics(raw,source,m){
 const a=raw.rows,flux=a.map(r=>r[5]*source.native_inputs.vial.Ap*1e-4*(source.nVial??1));
 near(m.maximum_bottom_temperature_c,Math.max(...a.map(r=>r[2])));
 near(m.peak_batch_sublimation_kg_h,Math.max(...flux));
 assert.equal(m.drying_completed,a[a.length-1][6]>=99.99999);
 if(m.drying_completed)near(m.completion_h,a[a.length-1][0]);else assert.equal(m.completion_h,null);
 const t=source.native_inputs.product.T_pr_crit;
 if(t!==undefined)near(m.thermal_margin_c,Math.min(...a.map(r=>t-r[2])));
 if(source.eq_cap)near(m.capacity_margin_kg_h,Math.min(...a.map((r,i)=>source.eq_cap.a+source.eq_cap.b*r[4]/1000-flux[i])));
 assert.equal(m.feasible,m.drying_completed&&m.thermal_margin_c!==null&&m.capacity_margin_kg_h!==null&&m.thermal_margin_c>=0&&m.capacity_margin_kg_h>=0);
}
for(const row of data.rows){
 const ref=refs[row.id],source=inputs[row.id].source;
 assert.equal(row.expected_status,ref.required_status);
 assert.equal(row.passed,Object.values(row.checks).every(Boolean));
 assert.equal(row.assessment?.answer_status??null,row.answer_status);
 assert.equal('reference_spec' in source,false);
 if(ref.metrics)metrics(ref.native_trajectory,source,ref.metrics);
 if(ref.candidates){
   assert.equal(ref.candidates.length,source.recipe_candidates.length);
   for(const c of ref.candidates)metrics(c.native_trajectory,source,c.metrics);
   const feasible=ref.candidates.filter(c=>c.metrics.feasible);
   if(feasible.length)near(ref.best_time_h,Math.min(...feasible.map(c=>c.metrics.completion_h)));else assert.equal(ref.best_time_h,null);
 }
}
near(budget.accounted_usd,budget.records.reduce((a,r)=>a+r.accounted_usd,0));
assert(budget.accounted_usd<=budget.estimated_budget_usd);assert.equal(budget.requests,budget.records.length);
console.log(JSON.stringify({cases:data.total,passed:data.passed,downloads:Object.keys(manifest).length,checks:'native columns, units, drying events, batch constraints, finite-grid references, denominators, receipts and SHA-256'}));
