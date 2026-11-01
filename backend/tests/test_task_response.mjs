import test from 'node:test';
import assert from 'node:assert/strict';
import {parseTaskResponse,runTaskResponse} from '../src/prime_runtime/task_response.mjs';
const answer={task_answer:{affected_batch_ids:['batch-a']},evidence_ids:['visible-source-cell']};
const messages=[{role:'assistant',content:[{type:'text',text:JSON.stringify(answer)}]}];
test('returns final agent output after native tool and child execution',async()=>{
  const events=[];
  const session={messages,prompt:async()=>events.push('model_and_tools'),waitForRlmQuiescence:async()=>events.push('children_done')};
  assert.deepEqual(await runTaskResponse(session,{prompt:'task',timeoutSeconds:1}),answer);
  assert.deepEqual(events,['model_and_tools','children_done']);
});
test('does not substitute tool output or an earlier guess for the final answer',()=>{
  assert.throws(()=>parseTaskResponse([...messages,{role:'assistant',content:[{type:'toolCall',name:'ipython'}]}]));
  assert.throws(()=>parseTaskResponse([{role:'toolResult',content:[{type:'text',text:JSON.stringify(answer)}]}]));
  assert.throws(()=>parseTaskResponse([{role:'assistant',content:[{type:'text',text:'No JSON answer.'}]}]));
  assert.throws(()=>parseTaskResponse([{role:'assistant',content:[{type:'text',text:'{"task_answer":{},"evidence_ids":[]}'}]}]));
});
test('timeout is a failure and aborts the live agent',async()=>{
  let aborted=false;
  const session={prompt:()=>new Promise(()=>{}),abort:async()=>{aborted=true;},messages};
  await assert.rejects(runTaskResponse(session,{prompt:'task',timeoutSeconds:.01}),/deadline/);
  assert.equal(aborted,true);
});
test('scores a unique structured answer surrounded by prose without inventing or choosing an answer',()=>{
  const response=text=>[{role:'assistant',content:[{type:'text',text}]}];
  assert.deepEqual(parseTaskResponse(response(`Assessment complete.\n\`\`\`json\n${JSON.stringify(answer)}\n\`\`\`\nDraft requires review.`)),answer);
  assert.throws(()=>parseTaskResponse(response(`${JSON.stringify(answer)}\n${JSON.stringify(answer)}`)),/unambiguous/);
  assert.throws(()=>parseTaskResponse(response('The answer is probably batch-a.')),/unambiguous/);
});
