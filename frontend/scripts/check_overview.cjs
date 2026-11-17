/* The overview's views and summaries, exercised without a browser: node scripts/check_overview.cjs */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
function load(file, modules = {}) {
  const code = ts.transpileModule(fs.readFileSync(require.resolve(file), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText;
  const module = { exports: {} };
  vm.runInNewContext(code, { exports: module.exports, module, require: name => modules[name] ?? {} });
  return module.exports;
}
const views = load('../lib/overview-views.ts');
const plain = value => JSON.parse(JSON.stringify(value));   // values from the vm context have another realm's prototypes
const { summarize } = load('../lib/overview-summaries.ts');

// Who lands where.
assert.equal(views.icpFor(['engineering'], 'qa'), 'qa');           // a demo persona wins
assert.equal(views.icpFor(['qa_reviewer']), 'qa');
assert.equal(views.icpFor(['supervisor']), 'executive');
assert.equal(views.icpFor(['msat', 'admin']), 'everyone');          // administrators see everything
assert.equal(views.icpFor(['unknown_role']), 'everyone');
assert.equal(views.icpFor(undefined, 'not-a-persona'), 'everyone');

// Every view is well formed: ids resolve, links are registered destinations, and it asks only for data it shows.
for (const icp of Object.keys(views.ICP_LABEL)) for (const demo of [false, true]) {
  const components = views.overviewComponents(icp, demo);
  const ids = new Set(components.map(c => c.id));
  assert.equal(ids.size, components.length, `${icp}: duplicate ids`);
  for (const c of components) for (const child of c.children ?? []) assert(ids.has(child), `${icp}: missing ${child}`);
  const cards = components.filter(c => c.component === 'SummaryCard');
  assert(cards.length >= 4, `${icp}: too few summaries`);
  for (const card of cards) assert(views.DESTINATIONS.includes(card.href), `${icp}: ${card.href} is not a destination`);
  const bound = new Set(cards.flatMap(c => c.value ? [c.value['@path'].split('/')[1]] : []));
  for (const source of views.sourcesFor(icp, demo)) assert(bound.has(source) || (source === 'deliveries' && bound.has('trends')), `${icp}: loads ${source} without showing it`);
  if (demo) assert(!cards.some(c => c.href === '/sources/'), `${icp}: demo shows connections`);
}
assert(!views.sourcesFor('executive', false).includes('workbench'));
assert.equal(views.overviewComponents('qa', true).find(c => c.id === 'card_assistant').href, '/home/?scenarios=1');

// Summaries say what needs the person, and only claim what loaded.
const run = (status, verified) => ({ id: status + verified, cmo: 'Partner', status, documents: 1, summary: { verified_package: verified } });
const ready = { deliveries: 'ready', signals: 'ready', quality: 'ready' };
let m = summarize({
  deliveries: [run('complete', false), run('complete', false), run('complete', true)],
  signals: [{ status: 'open', severity: 'critical' }, { status: 'open', severity: 'warning' }],
  quality: [{ workflow: { state: 'qa_review' } }, { workflow: { state: 'handed_off' } }],
}, ready);
assert.deepEqual({ ...m.deliveries }, { value: '2', status: 'to review · 1 verified', tone: 'attention' });
assert.deepEqual({ ...m.signals }, { value: '2', status: 'open · 1 at action level or above', tone: 'problem' });
assert.deepEqual({ ...m.quality }, { value: '1', status: 'open · 1 in QA review', tone: 'attention' });
assert.equal(m.trends.value, '1');
assert.equal(m.lead, '2 deliveries need review · 2 signals are open · 1 quality event is open.');
// The opening sentence follows the order of the person's own view.
assert.deepEqual(plain(views.attentionOrder('qa', false)), ['quality', 'signals', 'deliveries']);
assert.equal(summarize({ deliveries: [run('complete', false)], signals: [{ status: 'open', severity: 'warning' }], quality: [{ workflow: { state: 'qa_review' } }] },
  ready, 0, views.attentionOrder('qa', false)).lead, '1 quality event is open · 1 signal is open · 1 delivery needs review.');
assert.equal(summarize({ signals: [{ status: 'open', severity: 'warning' }] }, { signals: 'ready' }, 0, views.attentionOrder('process_engineer', true)).lead, '1 signal is open.');
assert.equal(m.workbench, undefined);                                // not part of this view, so not invented

m = summarize({ deliveries: [], signals: [], quality: [] }, ready);
assert.equal(m.lead, 'Nothing needs your attention right now.');
assert.equal(m.deliveries.value, undefined);
assert.equal(m.signals.tone, 'good');

m = summarize({}, { deliveries: 'loading', signals: { error: 'offline' } });
assert.equal(m.lead, 'Checking what needs your attention…');
assert.equal(m.deliveries.tone, 'loading');
assert.deepEqual({ ...m.signals }, { tone: 'unavailable', status: 'Unavailable: offline' });
// Something that could not be checked is named; it is never reported as clear.
assert.equal(summarize({}, { deliveries: { error: 'offline' } }).lead, 'Deliveries could not be checked.');
const offline = { error: 'offline' };
assert.equal(summarize({ connections: [{ enabled: true }] }, { deliveries: offline, signals: offline, quality: offline, connections: 'ready' }).lead,
  'Deliveries, signals and quality events could not be checked.');
assert.equal(summarize({ signals: [{ status: 'open', severity: 'critical' }, { status: 'open', severity: 'critical' }], quality: [] }, { deliveries: offline, signals: 'ready', quality: 'ready' }).lead,
  '2 signals are open. Deliveries could not be checked.');
assert.equal(summarize({ signals: [], quality: [] }, { deliveries: offline, signals: 'ready', quality: 'ready' }).lead, 'Deliveries could not be checked.');
assert.equal(summarize({}, {}).lead, 'Checking what needs your attention…');   // nothing asked for yet

m = summarize({ assistant: [], workbench: [{ status: 'open', open_steps: 3 }, { status: 'closed', open_steps: 9 }], connections: [{ enabled: true, last_error: 'x' }, { enabled: false }] },
  { assistant: 'ready', workbench: 'ready', connections: 'ready' }, 4);
assert.deepEqual({ ...m.assistant }, { value: '4', status: 'guided scenarios ready for your role', tone: 'quiet' });
assert.deepEqual({ ...m.workbench }, { value: '3', status: 'open steps in 1 plan', tone: 'attention' });
assert.equal(m.connections.tone, 'problem');

// The sidebar follows the view: its pages first and in the same order, the rest folded under More, nothing lost.
const nav = load('../lib/navigation.ts', { './overview-views': views });
const labels = group => plain(group.items.map(item => item.label));
const hrefs = groups => plain(groups.flatMap(g => g.items.map(item => item.href))).sort();
assert.equal(nav.navFor('everyone', false), nav.navGroups(false));
let groups = nav.navFor('qa', false);
assert.deepEqual(plain(groups.map(g => g.id)), ['start', 'yours', 'more', 'settings']);
assert.deepEqual(labels(groups[1]), ['Quality', 'Signals', 'Deliveries', 'Saved work', 'Export']);
assert.deepEqual(labels(groups[2]), ['Trends', 'Workbench', 'Simulation']);
assert.equal(groups[2].folded, true);
assert.deepEqual(labels(nav.navFor('executive', true)[1]), ['Deliveries', 'Signals', 'Quality', 'Trends']);
for (const icp of Object.keys(views.ICP_LABEL)) for (const demo of [false, true]) {
  assert.deepEqual(hrefs(nav.navFor(icp, demo)), hrefs(nav.navGroups(demo)), `${icp}: the sidebar lost or repeated a page`);
}
console.log('PASS overview views, summaries and sidebar');
