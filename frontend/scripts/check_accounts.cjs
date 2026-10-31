/* UI contract with isolated auth/API fixtures. No real signup emails or production data writes.
 * PLAYWRIGHT_MODULE=/path/to/playwright node frontend/scripts/check_accounts.cjs http://localhost:5182
 * Backend JWT, RLS and authorization tests separately exercise the real security boundaries. */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const base = process.argv[2] || 'http://localhost:5182';
const out = process.env.ACCOUNT_CHECK_ARTIFACTS || '/private/tmp/sievance-account-checks';
const envFile = path.join(__dirname, '../.env.local');
const env = fs.existsSync(envFile) ? fs.readFileSync(envFile, 'utf8') : '';
const project = process.env.NEXT_PUBLIC_SUPABASE_URL || env.match(/^NEXT_PUBLIC_SUPABASE_URL=["']?([^\s"']+)/m)?.[1];
assert(project, 'The test build needs a public Supabase project URL configured');
const user = {id:'11111111-1111-4111-8111-111111111111', email:'fixture@example.test',aud:'authenticated',role:'authenticated',app_metadata:{},user_metadata:{},created_at:new Date().toISOString()};
const token = ['eyJhbGciOiJIUzI1NiJ9',Buffer.from(JSON.stringify({sub:user.id,exp:Math.floor(Date.now()/1000)+3600})).toString('base64url'),'fixture'].join('.');
const organizations = [];
let members = [{actor_id:user.id,role:'admin',site_id:null}];
const posts = [], apiRequests = [], errors = [];
(async()=>{
  fs.mkdirSync(out,{recursive:true});
  const browser = await chromium.launch({headless:true});
  try {
    const context = await browser.newContext({viewport:{width:1440,height:1000}});
    await context.route('**/*', async route=>{
      const req=route.request(), url=new URL(req.url());
      const json=body=>route.fulfill({status:200,contentType:'application/json',headers:{'access-control-allow-origin':'*','access-control-allow-headers':'*'},body:JSON.stringify(body)});
      if(req.method()==='OPTIONS') return json({});
      if(url.pathname.startsWith('/auth/v1/')) {
        if(url.pathname.endsWith('/signup')) {posts.push({path:'signup'});return json({user,session:null});}
        return json({user});
      }
      if(url.pathname.startsWith('/v1/') || url.pathname.startsWith('/api/cmo-ingestion/')) {
        apiRequests.push({path:url.pathname,headers:req.headers()});
        const body=req.method()==='POST'?req.postDataJSON():null;
        if(body) posts.push({path:url.pathname,body});
        if(url.pathname==='/v1/account') return json({actor_id:user.id,organizations,can_create_organization:true});
        if(url.pathname==='/v1/account/organizations') {
          const org={id:'org_fixture',name:body.name,roles:['admin'],site_ids:[],onboarding_complete:false};organizations.push(org);return json(org);
        }
        if(url.pathname==='/v1/me') return json({tenant_id:'org_fixture',actor_id:user.id,roles:['admin'],site_ids:[],auth_mode:'supabase'});
        if(url.pathname==='/v1/connectors/catalog') return json({families:[],transports:[]});
        if(url.pathname==='/v1/connectors') return json({items:[]});
        if(url.pathname==='/v1/organization/onboarding/complete') {organizations[0].onboarding_complete=true;return json({status:'complete'});}
        if(url.pathname==='/v1/organization/members') {
          if(body?.operation==='revoke') members=members.filter(m=>m.actor_id!==body.actor_id);
          else if(body) members.push({actor_id:'22222222-2222-4222-8222-222222222222',role:body.role,site_id:body.site_id});
          return json(body?{status:'updated'}:{items:members});
        }
        if(url.pathname.endsWith('/catalog')) return json({packages:[],upload:{mode:'direct',max_bytes:64000000}});
        if(url.pathname.endsWith('/runs')) return json({runs:[],items:[]});
        return json({items:[]});
      }
      if(url.origin===new URL(base).origin) return route.continue();
      return route.abort(); // Never call a real identity provider or API.
    });
    const page=await context.newPage();
    page.on('pageerror',e=>errors.push(e.message));
    await page.goto(base+'/sign-in/');
    await page.getByRole('link',{name:'Create an account',exact:true}).click();
    await page.getByLabel('Work email').fill(user.email);
    await page.getByLabel('Password',{exact:true}).fill('fixture-password-only-123');
    await page.getByRole('button',{name:'Create account',exact:true}).click();
    await page.getByRole('heading',{name:'Check your email'}).waitFor();
    assert.equal(apiRequests.length,0,'Public signup must not load a workspace or demo identity');
    await page.screenshot({path:path.join(out,'signup-confirmation.png')});
    console.log('PASS login → signup → confirmation, with no workspace API calls');
    await context.addInitScript(({key,user,token})=>localStorage.setItem(key,JSON.stringify({access_token:token,refresh_token:'fixture-refresh',token_type:'bearer',expires_at:Math.floor(Date.now()/1000)+3600,expires_in:3600,user})),{key:`sb-${new URL(project).hostname.split('.')[0]}-auth-token`,user,token});
    await page.goto(base+'/account/');
    await page.getByLabel('Organization name').fill('Fixture organization');
    await page.getByRole('button',{name:'Create organization & continue'}).click();
    await page.waitForURL('**/onboarding/start/');
    await page.getByRole('button',{name:'Continue without adding a source'}).waitFor({state:'visible'});
    await page.getByRole('button',{name:'Continue without adding a source'}).click();
    await page.waitForURL('**/cmo/');
    assert(organizations[0].onboarding_complete);
    assert(posts.some(p=>p.path==='/v1/organization/onboarding/complete'));
    console.log('PASS new account → organization → onboarding → workspace');
    await page.goto(base+'/account/');
    await page.waitForURL('**/cmo/');
    console.log('PASS returning account bypasses completed onboarding');
    await page.goto(base+'/settings/organization/');
    await page.getByRole('heading',{name:'Grant team access'}).waitFor();
    await page.getByLabel('Account email').fill('member@example.test');
    await page.getByRole('button',{name:'Grant access',exact:true}).click();
    await page.getByText('Access granted.',{exact:false}).waitFor();
    await page.getByRole('button',{name:'Revoke role'}).last().click();
    await page.getByText('Role revoked.',{exact:false}).waitFor();
    assert(posts.some(p=>p.body?.operation==='revoke'));
    await page.screenshot({path:path.join(out,'organization-access.png')});
    organizations.push({id:'org_second',name:'Second organization',roles:['operator'],site_ids:[],onboarding_complete:true});
    await page.goto(base+'/account/?manage=1');
    await page.getByRole('button',{name:/Second organization/}).click();
    await page.waitForURL('**/cmo/');
    await page.waitForFunction(()=>document.body.innerText.includes('Organization'));
    assert(apiRequests.some(r=>r.headers['x-organization-id']==='org_second'));
    assert(!apiRequests.some(r=>r.headers['x-actor-id'] || r.headers['x-tenant-id']));
    assert.equal(errors.length,0,errors.join('\n'));
    console.log('PASS team grant/revoke and organization switch; bearer identity only');
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
