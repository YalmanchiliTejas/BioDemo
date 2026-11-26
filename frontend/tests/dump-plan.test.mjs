import assert from 'node:assert/strict';
import test from 'node:test';
import { monthOf, planDump } from '../lib/dump-plan.ts';

test('months come from ISO dates, month names, and abbreviations only beside a year', () => {
  assert.equal(monthOf('LIMS_2026-10-19.csv'), '2026-10');
  assert.equal(monthOf('Northfield_September_process_trends.xlsx'), '09');
  assert.equal(monthOf('Oct 2026'), '2026-10');
  assert.equal(monthOf('mar_results.csv'), null); // "mar" alone is not trusted
  assert.equal(monthOf('CoA_CHO-007-R01.pdf'), null);
  assert.equal(monthOf('batch_20261105.csv'), '2026-11');
});

test('a dump splits by known CMO and month; folders win over file dates; undated files join the only month', () => {
  const plan = planDump([
    'dump/Alder Biologics/2026-10 October/LIMS_2026-09-30.csv', // folder month wins over the file date
    'dump/Alder Biologics/2026-10 October/CoA_A-105.pdf',
    'dump/Alder Biologics/November 2026/trends.xlsx',
    'dump/Birchwood CDMO/september/lims.csv',
    'dump/Birchwood CDMO/cover-letter.eml',                     // undated, joins Birchwood's only month
    'dump/CoAs/CoA_X-1.pdf',                                     // unknown folder: not a CMO, no month
  ], ['Alder Biologics', 'Birchwood CDMO'], 'Typed CMO');
  assert.deepEqual(plan.map(g => [g.label, g.paths.length]), [
    ['Alder Biologics · October 2026', 2], ['Alder Biologics · November 2026', 1],
    ['Birchwood CDMO · September', 2], ['Typed CMO · no month found', 1],
  ]);
});

test('one CMO and one month stays one delivery', () => {
  assert.equal(planDump(['a/LIMS_October.csv', 'a/CoA.pdf', 'README.md'], [], 'Alder').length, 1);
});

test('a group of only non-data files joins a delivery instead of standing alone', () => {
  const plan = planDump(['d/A/2026-10/lims.csv', 'd/A/2026-11/lims.csv', 'd/README.md'], ['A'], 'A');
  assert.deepEqual(plan.map(g => [g.label, g.paths.length]), [['A · October 2026', 2], ['A · November 2026', 1]]);
});
