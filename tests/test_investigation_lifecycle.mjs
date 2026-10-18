import test from 'node:test';
import assert from 'node:assert/strict';
import {runInvestigation, RESUME_PROMPT, FINALIZE_PROMPT} from '../src/prime_runtime/investigation_lifecycle.mjs';

function deferred() {
  let resolve, reject;
  const promise = new Promise((yes,no) => { resolve=yes; reject=no; });
  return {promise,resolve,reject};
}
const tick = () => new Promise(resolve => setImmediate(resolve));
function setup() {
  const state={submitted:false, prompts:[], events:[], cancelled:[], aborts:0, reads:0};
  const session={agent:{state:{}},
    prompt:async text => {state.prompts.push(text);},
    waitForRlmQuiescence:async()=>{}, waitForHeadlessIdle:async()=>{},
    getRlmChildSnapshots:()=>[],cancelRlmChildRun:id=>state.cancelled.push(id),
    abort:async()=>{state.aborts++;}};
  const options={prompt:'Investigate existing evidence',timeoutSeconds:2,finalizationReserveSeconds:0.5,
    emit:e=>state.events.push(e),readStatus:async()=>{state.reads++;return {final_report_submitted:state.submitted,report_status:'complete_for_available_evidence'};}};
  return {state,session,options};
}

test('lead turn may end while specialists run; resume only after SDK fan-in',async()=>{
  const {state,session,options}=setup();const children=deferred();let finished=false;
  session.getRlmChildSnapshots=()=>[{id:'child',status:'running'}];
  session.waitForRlmQuiescence=()=>children.promise;
  session.prompt=async text=>{state.prompts.push(text);if(text===RESUME_PROMPT)state.submitted=true;};
  const run=runInvestigation(session,options).then(result=>{finished=true;return result;});
  await tick();assert.equal(finished,false);assert.equal(state.reads,1);assert.equal(state.prompts.length,1);
  children.resolve();const result=await run;
  assert.equal(result.final_report_submitted,true);assert.deepEqual(state.prompts,[options.prompt,RESUME_PROMPT]);
  assert.equal(state.aborts,0);
});

test('native parent follow-up submits report during recursive fan-in, without duplicate prompt',async()=>{
  const {state,session,options}=setup();
  session.waitForRlmQuiescence=async()=>{state.submitted=true;};
  const result=await runInvestigation(session,options);
  assert.equal(result.final_report_submitted,true);assert.equal(state.prompts.length,1);
});

test('descendant barrier remains owned while nested work and parent replies drain',async()=>{
  const {state,session,options}=setup();const direct=deferred(),nested=deferred();
  session.waitForRlmQuiescence=async()=>{await direct.promise;await nested.promise;state.submitted=true;};
  let finished=false;const run=runInvestigation(session,options).then(()=>finished=true);
  await tick();direct.resolve();await tick();assert.equal(finished,false);assert.equal(state.reads,1);
  nested.resolve();await run;assert.equal(finished,true);
});

test('saved partial submission is accepted without promoting it to complete',async()=>{
  const {state,session,options}=setup();state.submitted=true;
  options.readStatus=async()=>({final_report_submitted:true,report_status:'incomplete'});
  const result=await runInvestigation(session,options);assert.equal(result.report_status,'incomplete');
});

test('a persisted report stops work without waiting for unnecessary outstanding specialists',async()=>{
  const {state,session,options}=setup();state.submitted=true;
  session.waitForRlmQuiescence=()=>{throw Error('Should not wait after actual submission');};
  assert.equal((await runInvestigation(session,options)).final_report_submitted,true);
});

test('idle progress messages and checkpoints alone never count as report submission',async()=>{
  const {state,session,options}=setup();
  session.prompt=async text=>{state.prompts.push(text);if(state.prompts.length===3)state.submitted=true;};
  await runInvestigation(session,options);
  assert.equal(state.prompts.length,3);assert.equal(state.events.filter(e=>e.type==='lead_resumed_for_submission').length,2);
});

test('finalization reserve cancels unfinished children and synthesizes their saved findings',async()=>{
  const {state,session,options}=setup();options.timeoutSeconds=0.5;options.finalizationReserveSeconds=0.45;
  session.getRlmChildSnapshots=()=>[{id:'running-child',status:'running'},{id:'done-child',status:'done'}];
  session.waitForRlmQuiescence=signal=>new Promise((_,reject)=>signal.addEventListener('abort',()=>reject(Error('wait cancelled')),{once:true}));
  session.prompt=async text=>{state.prompts.push(text);if(text===FINALIZE_PROMPT)state.submitted=true;};
  await runInvestigation(session,options);
  assert.deepEqual(state.cancelled,['running-child']);assert.ok(state.prompts.includes(FINALIZE_PROMPT));assert.equal(state.aborts,1);
});

test('reserve cancellation of an in-flight lead prompt still enters synthesis',async()=>{
  const {state,session,options}=setup();options.timeoutSeconds=0.5;options.finalizationReserveSeconds=0.45;
  const inFlight=deferred();session.abort=async()=>{state.aborts++;inFlight.reject(Error('prompt aborted'));};
  session.prompt=async text=>{state.prompts.push(text);if(text===options.prompt)return inFlight.promise;state.submitted=true;};
  await runInvestigation(session,options);assert.deepEqual(state.prompts,[options.prompt,FINALIZE_PROMPT]);
});

test('hard deadline bounds a stuck final synthesis and preserves failure',async()=>{
  const {session,options}=setup();options.timeoutSeconds=0.1;options.finalizationReserveSeconds=0.05;
  session.waitForRlmQuiescence=signal=>new Promise((_,reject)=>signal.addEventListener('abort',()=>reject(Error('cancelled')),{once:true}));
  session.prompt=async text=>text===FINALIZE_PROMPT?new Promise(()=>{}):undefined;
  await assert.rejects(runInvestigation(session,options),/wall-clock deadline/);
});

test('a completed synthesis turn without a report fails explicitly',async()=>{
  const {session,options}=setup();options.timeoutSeconds=0.5;options.finalizationReserveSeconds=0.45;
  session.waitForRlmQuiescence=signal=>new Promise((_,reject)=>signal.addEventListener('abort',()=>reject(Error('cancelled')),{once:true}));
  await assert.rejects(runInvestigation(session,options),/Final synthesis ended without submitting/);
});

test('provider errors remain terminal; more lead prompts cannot conceal them',async()=>{
  const {state,session,options}=setup();options.getFatalError=()=> 'provider_payment_required';
  await assert.rejects(runInvestigation(session,options),/provider_payment_required/);
  assert.equal(state.prompts.length,1);
});

test('bridge failures and SDK fan-in failures produce errors rather than inferred completion',async()=>{
  const one=setup();one.options.readStatus=async()=>{throw Error('bridge unavailable');};
  await assert.rejects(runInvestigation(one.session,one.options),/bridge unavailable/);
  const two=setup();two.session.waitForRlmQuiescence=async()=>{throw Error('child barrier failed');};
  await assert.rejects(runInvestigation(two.session,two.options),/child barrier failed/);
});

test('unsupported SDK and absent deadlines fail with actionable diagnostics',async()=>{
  const {session,options}=setup();delete session.waitForRlmQuiescence;
  await assert.rejects(runInvestigation(session,options),/SDK lacks waitForRlmQuiescence/);
  const other=setup();other.options.timeoutSeconds=null;
  await assert.rejects(runInvestigation(other.session,other.options),/positive finite/);
});
