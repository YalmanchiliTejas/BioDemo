"""Exercise the real JS host and Python bridge without provider inference."""
import json
import shutil
from pathlib import Path
import pytest
from tests.test_investigation_review import case, complete_report
from src.prime_runtime.harness import PrimeManufacturingHarness


def test_real_host_waits_for_child_then_resumes_and_submits(case,tmp_path,monkeypatch):
    node=shutil.which('node')
    if not node:pytest.skip('Node is required for the SDK host integration')
    bridge,_,prepared,_=case
    bundle=tmp_path/'sdk';dist=bundle/'packages/coding-agent/dist';dist.mkdir(parents=True)
    (bundle/'package.json').write_text('{"type":"module"}')
    skill=bundle/'packages/coding-agent/skills/agent-message/SKILL.md';skill.parent.mkdir(parents=True);skill.write_text('Test messaging skill')
    fixture=tmp_path/'final-report.json';fixture.write_text(json.dumps(complete_report(prepared)))
    monkeypatch.setenv('TEST_HANDOFF_REPORT',str(fixture))
    (dist/'index.js').write_text('''
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {join} from 'node:path';
export const getAgentDir=()=>'';
export const AuthStorage={create:()=>({})};
export const ModelRegistry={create:()=>({})};
export class DefaultResourceLoader {async reload(){}}
export const SettingsManager={};
export const SessionManager={create:(_cwd,dir)=>({dir})};
export async function createAgentSession(options){
  const dir=options.sessionManager.dir;mkdirSync(dir,{recursive:true});
  const sessionFile=join(dir,'synthetic-host-session.jsonl');writeFileSync(sessionFile,'{}\\n');
  let childDone=false;let childWait;let prompts=0;
  const config=JSON.parse(readFileSync(process.env.BIODEMO_PRIME_BRIDGE_CONFIG,'utf8'));
  async function post(path,body){
    const response=await fetch(config.url+path,{method:'POST',headers:{Authorization:`Bearer ${config.token}`,'Content-Type':'application/json'},body:JSON.stringify(body)});
    const data=await response.json();if(!response.ok)throw Error(JSON.stringify(data));return data;
  }
  const session={sessionId:'synthetic-host-session',sessionFile,model:{provider:'test',id:'no-inference'},agent:{state:{}},
    subscribe:()=>()=>{},
    getRlmChildSnapshots:()=>childDone?[]:[{id:'test-child',status:'running'}],
    waitForRlmQuiescence:async()=>{await childWait;},
    waitForHeadlessIdle:async()=>{},abort:async()=>{},
    async prompt(text){
      prompts++;
      if(prompts===1){
        childWait=new Promise((resolve,reject)=>setTimeout(async()=>{
          try{
            const status=await post('/execution-status',{});
            if(status.final_report_submitted)throw Error('Report was invented before child handoff');
            await post('/subreport',{subreport_id:'handoff-child',assessment:'Specialist checkpoint retained.'});
            childDone=true;resolve();
          }catch(error){reject(error);}
        },50));
        // Reproduce the original failure: the first root prompt ends while
        // admitted child work is still active.
        return;
      }
      if(!childDone)throw Error('Lead resumed before specialist settlement');
      if(!text.includes('Continue the existing investigation'))throw Error('Expected synthesis continuation');
      const result=await post('/report',JSON.parse(readFileSync(process.env.TEST_HANDOFF_REPORT,'utf8')));
      if(result.report_status!=='complete_for_available_evidence')throw Error('Final submission was not accepted');
    },
    dispose(){if(!childDone)throw Error('Disposed before child completed');writeFileSync(join(dir,'host-handoff.json'),JSON.stringify({prompts,childDone}));}
  };
  return {session};
}
''')
    # No project provider override may affect this synthetic SDK. The host,
    # lifecycle, bridge HTTP routes and report verifier are the real code.
    for key in ('BIODEMO_MODAL_PROXY_TOKEN','MODAL_PROXY_TOKEN','BIODEMO_MODAL_BASE_URL'):
        monkeypatch.delenv(key,raising=False)
    harness=PrimeManufacturingHarness(command=[node,str(Path(__file__).resolve().parents[1]/'src/prime_runtime/sdk_runner.mjs')],
        store=bridge.store,blackboards=bridge.blackboards,workflow=bridge.workflow,scope=bridge.scope,runtime_root=tmp_path/'host-runtime')
    harness.bundle=bundle;harness.message_skill_path=skill;harness.timeout_seconds=120
    # Match the failed frozen run's fixed policy. Adaptive stopping decisions
    # have their own regressions and are not manufactured by this SDK fixture.
    harness.max_tool_calls=48;harness.execution_policy={'mode':'fixed_v1'}
    result=harness.run(incident_id='handoff-test',problem='Investigate scoped sources',new_evidence_ids=[],as_of=bridge.as_of)
    assert result['report_status']=='complete_for_available_evidence'
    assert json.loads((tmp_path/'host-runtime/sessions/handoff-test/host-handoff.json').read_text())=={'prompts':2,'childDone':True}
    logs=list((tmp_path/'host-runtime/logs').glob('*.jsonl'))
    assert any('lead_resumed_for_submission' in log.read_text() for log in logs)
