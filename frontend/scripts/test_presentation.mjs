import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { elapsedDays, unaddressedCount, lotDays } from '../src/presentation.mjs';
const data = JSON.parse(readFileSync(new URL('../src/data/fresenius.json', import.meta.url)));
const view = data.plant_view;
test('Exposure ends at escalation without implying physical product recovery', () => {
  assert.equal(unaddressedCount(view.lots, '2025-10-15T00:00:00Z', view.recognized.time, false), 3);
  assert.equal(unaddressedCount(view.lots, view.recognized.time, view.recognized.time, false), 0);
  assert.equal(unaddressedCount(view.lots, '2025-11-15T00:00:00Z', view.recognized.time, false), 0);
  assert.equal(unaddressedCount(view.lots, '2025-01-03T00:00:00Z', view.escalation.time, true), 1);
  assert.equal(unaddressedCount(view.lots, view.escalation.time, view.escalation.time, true), 0);
});
test('Lead and lot days use exact elapsed times before display rounding', () => {
  assert.equal(Math.round(elapsedDays(view.escalation.time, view.recognized.time)), 289);
  assert.ok(lotDays(view.lots, view.escalation.time, true) > 2);
  assert.ok(lotDays(view.lots, view.escalation.time, true) < 3);
  const baseline = lotDays(view.lots, view.recognized.time, false);
  const assisted = lotDays(view.lots, view.escalation.time, true);
  assert.equal(baseline.toFixed(1), '738.1');
  assert.equal(assisted.toFixed(1), '2.5');
  assert.equal((baseline - assisted).toFixed(1), '735.6');
});
test('Synthetic population has multiple lines and one unavailable measurement', () => {
  assert.equal(data.batches.length, 100);
  assert.equal(data.batches.filter(b => b.bioburden != null).length, 99);
  assert.equal(new Set(data.batches.map(b => b.line)).size, 3);
});
test('Public release narrative does not infer administrative closure status', () => {
  assert.equal(data.presentation_version, 'v2-investigation-adequacy');
  assert.ok(data.legacy_record_notice.includes('not rerun'));
  const releases = data.recorded_events.filter(event => event.kind === 'disposition_decision');
  assert.equal(releases.length, 3);
  for (const event of releases) {
    assert.ok(event.title.includes('simulated QA decision'));
    assert.ok(event.detail.includes('did not adequately assess broader risk'));
    assert.ok(event.detail.includes('does not establish the deviation closure date'));
    assert.ok(!event.detail.includes('remained in batch-local open deviations'));
  }
});
