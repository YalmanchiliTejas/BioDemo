import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import {createHash} from 'node:crypto';
import {reviewedCase, supportingIds} from '../src/publicReviews.mjs';
const root=new URL('../',import.meta.url);
const snapshot=JSON.parse(readFileSync(new URL('src/data/benchmarks.json',root)));
test('Every public case review binds to the retained original output hash and fails closed on change',()=>{
  assert.equal(snapshot.runs.length,11);
  for(const run of snapshot.runs){
    assert.ok(reviewedCase(run.case_id,run.output_sha256),run.case_id);
    assert.equal(reviewedCase(run.case_id,'changed'),null);
    if(run.output_sha256){
      const bytes=readFileSync(new URL('../results/evaluation/'+run.run_id+'/output.json',root));
      assert.equal(createHash('sha256').update(bytes).digest('hex'),run.output_sha256);
    }
  }
});
test('Editorial observations point to existing evidence IDs and original coordinates',()=>{
  for(const run of snapshot.runs){
    const report=JSON.parse(readFileSync(new URL('public/benchmarks/'+run.run_id+'.json',root)));
    for(const section of reviewedCase(run.case_id,run.output_sha256).sections){
      for(const observation of section.observations){
        const ids=supportingIds(report,observation);
        assert.ok(ids.length,run.case_id+': '+observation.match);
        for(const id of ids){
          const check=report.source_checks.find(check=>check.observation_id===id);
          assert.ok(check?.source_ref,run.case_id+': '+id);
          assert.ok(check.source_ref.path);
        }
      }
    }
  }
});
test('Partial report is quarantined and high-risk corrections remain explicit',()=>{
  const review=id=>{const run=snapshot.runs.find(run=>run.case_id===id);return reviewedCase(id,run.output_sha256)};
  assert.ok(review('FRE-04').quarantine);
  assert.ok(review('FRE-04').sections.every(section=>section.hypotheses.length===0));
  assert.match(JSON.stringify(review('CHO-04')),/do not establish whether physical feed delivery stopped/);
  assert.match(JSON.stringify(review('CHO-04')),/initiating cause is unknown/);
  assert.match(JSON.stringify(review('CHO-05')),/SEM definition, underlying replicates, and replicate count are unavailable/);
  assert.match(review('FRE-06').summary,/Separate synthetic product\/line/);
  assert.match(review('FRE-01').summary,/closure status.*not established/);
  assert.match(JSON.stringify(review('FRE-05')),/do not share a category/);
});
