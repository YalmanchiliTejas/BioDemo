import test from 'node:test';
import assert from 'node:assert/strict';
import { configureProjectProvider, validateModalAuthentication } from '../src/prime_runtime/provider_config.mjs';

function setup() {
  const calls = [];
  return { calls, auth: {setRuntimeApiKey: (...args) => calls.push(['auth',...args])},
    registry: {registerProvider: (...args) => calls.push(['provider',...args])} };
}

test('project token overrides saved auth and explicitly selects bearer authentication', () => {
  const {calls,auth,registry}=setup();
  configureProjectProvider(auth,registry,{BIODEMO_MODAL_PROXY_TOKEN:' Bearer wk-test.ws-test '});
  assert.deepEqual(calls,[['auth','modal','wk-test.ws-test'],['provider','modal',{authHeader:true}]]);
});

test('endpoint can be overridden without replacing credentials', () => {
  const {calls,auth,registry}=setup();
  configureProjectProvider(auth,registry,{BIODEMO_MODAL_BASE_URL:'https://example.modal.direct/v1'});
  assert.deepEqual(calls,[['provider','modal',{baseUrl:'https://example.modal.direct/v1'}]]);
});

test('absent project overrides preserve existing configuration', () => {
  const {calls,auth,registry}=setup();
  configureProjectProvider(auth,registry,{});
  assert.deepEqual(calls,[]);
});

test('supports the existing Modal credential variable', () => {
  const {calls,auth,registry}=setup();
  configureProjectProvider(auth,registry,{MODAL_PROXY_TOKEN:'wk-test.ws-test'});
  assert.deepEqual(calls,[['auth','modal','wk-test.ws-test'],['provider','modal',{authHeader:true}]]);
});

test('project credential takes precedence over the existing variable', () => {
  const {calls,auth,registry}=setup();
  configureProjectProvider(auth,registry,{MODAL_PROXY_TOKEN:'old',BIODEMO_MODAL_PROXY_TOKEN:'wk-test.ws-test'});
  assert.equal(calls[0][2],'wk-test.ws-test');
});

test('authentication preflight rejects missing or malformed resolved credentials', async () => {
  for (const resolved of [{ok:false},{ok:true,apiKey:'MODAL_PROXY_TOKEN'},{ok:true,apiKey:'wk-id.ws-secret',headers:{Authorization:'Bearer wrong'}}]) {
    await assert.rejects(validateModalAuthentication({provider:'modal'},{getApiKeyAndHeaders:async()=>resolved}),/wrong format/);
  }
  await validateModalAuthentication({provider:'modal'},{getApiKeyAndHeaders:async()=>({ok:true,apiKey:'wk-id.ws-secret'})});
  await validateModalAuthentication({provider:'other'},{});
});

test('reject invalid headers and credential-bearing endpoint URLs', () => {
  const {calls,auth,registry}=setup();
  assert.throws(() => configureProjectProvider(auth,registry,{BIODEMO_MODAL_PROXY_TOKEN:'a\nb'}));
  assert.throws(() => configureProjectProvider(auth,registry,{BIODEMO_MODAL_BASE_URL:'https://secret@example.com/v1'}));
  assert.throws(() => configureProjectProvider(auth,registry,{BIODEMO_MODAL_BASE_URL:'file:///tmp/model'}));
  assert.deepEqual(calls,[]);
});
