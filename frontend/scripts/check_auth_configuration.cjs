/* Exercise the real auth module under production and development configuration. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const code = ts.transpileModule(fs.readFileSync(require.resolve('../lib/auth.ts'), 'utf8'), {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
function auth(env, session=null, updateUser=async()=>({error:null}), local=null) {
  const module={exports:{}};
  const storage=new Map([['sievance.organization:fixture','org_a']]);
  if(local) storage.set('sievance.local-session.v1',JSON.stringify(local));
  vm.runInNewContext(code,{
    exports:module.exports,module,process:{env},
    require:name=>name==='react'?{}:{createClient:()=>({auth:{getSession:async()=>({data:{session},error:null}),updateUser}})},
    window:{},
    localStorage:{getItem:key=>storage.get(key),setItem:(key,v)=>storage.set(key,v),removeItem:key=>storage.delete(key)},
  });
  return module.exports;
}
(async()=>{
  const production=auth({NODE_ENV:'production'});
  assert.equal(production.authMode(),'supabase');
  assert.equal(production.authConfigured(),false);
  await assert.rejects(production.authHeaders(),/not configured/);
  const configured=auth({NODE_ENV:'production',NEXT_PUBLIC_SUPABASE_URL:'https://fixture.supabase.co',NEXT_PUBLIC_SUPABASE_ANON_KEY:'public-fixture'},{access_token:'fixture-token',user:{id:'fixture'}});
  const h=await configured.authHeaders();
  assert.equal(h.Authorization,'Bearer fixture-token');
  assert.equal(h['X-Organization-Id'],'org_a');
  assert.equal(h['X-Tenant-Id'],undefined);
  assert.equal(h['X-Actor-Id'],undefined);
  const updates = [];
  const profile = auth({NODE_ENV:'production',NEXT_PUBLIC_SUPABASE_URL:'https://fixture.supabase.co',NEXT_PUBLIC_SUPABASE_ANON_KEY:'public-fixture'}, null, async value=>{updates.push(value);return {error:null};});
  await profile.updateDisplayName('  Fixture Name  ');
  assert.equal(JSON.stringify(updates), JSON.stringify([{data:{full_name:'Fixture Name'}}]));
  await assert.rejects(profile.updateDisplayName(' '), /between 1 and 80/);
  await assert.rejects(profile.updateDisplayName('a'.repeat(81)), /between 1 and 80/);
  assert.equal(updates.length, 1);
  const development=auth({NODE_ENV:'development'});
  assert.equal(development.authMode(),'development');
  assert.equal(JSON.stringify(await development.authHeaders()), '{}'); // no implicit developer identity
  const local=auth({NODE_ENV:'development',NEXT_PUBLIC_LOCAL_LOGIN:'1'}, null, undefined,
    {tenant_id:'local-test',actor_id:'demo-visitor-fixture',email:'',name:'Demo visitor'});
  const localHeaders=await local.authHeaders();
  assert.equal(localHeaders['X-Actor-Id'],'demo-visitor-fixture');
  assert.equal(localHeaders['X-Tenant-Id'],'local-test');
  assert.equal(localHeaders['X-Demo-Visitor'],'1');
  const productionWithLocalData=auth({NODE_ENV:'production',NEXT_PUBLIC_LOCAL_LOGIN:'1'}, null, undefined,
    {tenant_id:'local-test',actor_id:'demo-visitor-fixture'});
  assert.equal(productionWithLocalData.authMode(),'supabase');
  await assert.rejects(productionWithLocalData.authHeaders(), /not configured/);
  for(const next of ['//external.test','/\\external.test','/bad path','https://external.test']) assert.equal(production.safeNext(next),'/trends/');
  assert.equal(production.safeNext(null), '/trends/');
  assert.equal(production.safeNext('/cmo/?run=fixture'), '/cmo/?run=fixture');
  const orgModule = {exports:{}};
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(require.resolve('../lib/organizations-api.ts'), 'utf8'), {compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText, {
    exports:orgModule.exports, module:orgModule, require:()=>({}),
  });
  const destination = orgModule.exports.organizationDestination;
  const organization = {roles:['admin'], onboarding_complete:false};
  assert.equal(destination(organization), '/onboarding/start/');
  assert.equal(destination({...organization, onboarding_complete:true}), '/trends/');
  assert.equal(destination({...organization, onboarding_complete:true}, '/cmo/?run=fixture'), '/cmo/?run=fixture');
  assert.equal(destination({...organization, roles:['viewer']}), '/trends/');
  console.log('PASS production fails closed; authenticated headers select organization; development headers stay in development; return paths remain local');
})().catch(e=>{console.error(e);process.exitCode=1;});
