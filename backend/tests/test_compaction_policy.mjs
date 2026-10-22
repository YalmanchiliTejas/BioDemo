import test from 'node:test';
import assert from 'node:assert/strict';
import { COMPACTION_RESERVE_TOKENS, compactionWindow } from '../src/prime_runtime/compaction_policy.mjs';

test('large native windows summarize at the target size', () => {
  const policy = compactionWindow({ contextWindow: 1048576 }, 128000);
  assert.deepEqual(policy, { target_tokens: 128000, context_window: 128000 + COMPACTION_RESERVE_TOKENS,
    native_context_window: 1048576 });
});

test('unset target or a window already near the target leaves the model unchanged', () => {
  assert.equal(compactionWindow({ contextWindow: 1048576 }, null), null);
  assert.equal(compactionWindow({ contextWindow: 128000 }, 128000), null);
  assert.equal(compactionWindow(undefined, 128000), null);
});

test('rejects targets too small to hold a working context', () => {
  assert.throws(() => compactionWindow({ contextWindow: 1048576 }, 1000), /at least 32000/);
  assert.throws(() => compactionWindow({ contextWindow: 1048576 }, 'lots'), /integer/);
});
