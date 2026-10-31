/* Exercise the real auth module under production and development configuration. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const code = ts.transpileModule(fs.readFileSync(require.resolve('../lib/auth.ts'), 'utf8'), {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
function auth(env, session=null) {
  const module={exports:{}};
  const storage=new Map([['sievance.organization:fixture','org_a']]);
  vm.runInNewContext(code,{
    exports:module.exports,module,process:{env},
    require:name=>name==='react'?{}:{createClient:()=>({auth:{getSession:async()=>({data:{session},error:null})}})},
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
  const development=auth({NODE_ENV:'development'});
  assert.equal(development.authMode(),'development');
  assert.equal((await development.authHeaders())['X-Actor-Id'],'priya');
  for(const next of ['//external.test','/\\external.test','/bad path','https://external.test']) assert.equal(production.safeNext(next),'/cmo');
  console.log('PASS production fails closed; authenticated headers select organization; development headers stay in development; return paths remain local');
})().catch(e=>{console.error(e);process.exitCode=1;});
