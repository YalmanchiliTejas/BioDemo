/* Workbench UI contract: every API request is intercepted with fixtures in the shape of the backend's own samples
 * (workspace-task templates, delivery profiles, work plans). No live backend, no inference, no writes.
 * PLAYWRIGHT_MODULE=/path/to/playwright node scripts/check_workbench.cjs [scenario] [--screenshots=/dir]
 */
const assert = require('node:assert/strict');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.WORKBENCH_PREVIEW || 'http://127.0.0.1:5186';
const shots = (process.argv.find(arg => arg.startsWith('--screenshots=')) || '').split('=')[1];
const clone = value => JSON.parse(JSON.stringify(value));
const SITE = 'NF1';
// Colleagues who can be asked at this site, by the name they are known by.
const PEOPLE = [{ id: 'colleague', label: 'Carla Reyes' }, { id: 'm.okafor', label: 'M. Okafor' }];

// Made-up records. Elapsed hours and values per delivery, parameter and batch.
const DELIVERIES = [
  { id: 'ds-nov', run_id: 'run-nov', revision: 1, site_id: SITE, status: 'current', cmo: 'Fixture CDMO', delivery_name: 'November runs', measurements: 6, batches: ['B-210', 'B-211'], parameters: ['glucose'],
    verification: 'provisional', review: { pending_values: 6, rejected_values: 1, open_issues: 3 }, published_at: '2026-11-12T09:00:00Z' },
  { id: 'ds-oct', run_id: 'run-oct', revision: 2, site_id: SITE, status: 'current', cmo: 'Fixture CDMO', delivery_name: 'October runs', measurements: 23, batches: ['B-201', 'B-203', 'B-204'], parameters: ['glucose', 'pH'],
    verification: 'verified', published_at: '2026-11-02T09:00:00Z' },
  { id: 'ds-sep', run_id: 'run-sep', revision: 1, site_id: SITE, status: 'current', cmo: 'Fixture CDMO', delivery_name: 'September runs', measurements: 6, batches: ['B-190', 'B-191'], parameters: ['glucose'],
    verification: 'verified', published_at: '2026-10-03T09:00:00Z' },
];
const VALUES = {
  'ds-oct': { file: 'LIMS_October.csv', glucose: { unit: 'g/L', batches: {
    'B-201': [[0, 10], [12, 9.4], [24, 8.8], [36, 8.2], [48, 7.6], [72, 7], [96, 6.4]], 'B-203': [[0, 9.8], [24, 8.9], [48, 7.9], [96, 6.6]],
    'B-204': [[0, 9.2], [12, 8.6], [36, 7.4], [48, 6.8], [72, 6.2], [96, 5.6]] } },
    pH: { unit: 'pH', batches: { 'B-201': [[0, 7.1], [24, 6.9], [48, 6.8]], 'B-204': [[0, 7], [24, 6.7], [48, 6.5]] } } },
  'ds-sep': { file: 'LIMS_September.csv', glucose: { unit: 'g/L', batches: { 'B-190': [[0, 10.1], [24, 9], [48, 7.7]], 'B-191': [[0, 9.9], [24, 8.8], [48, 7.5]] } } },
  'ds-nov': { file: 'LIMS_November.csv', glucose: { unit: 'g/L', batches: { 'B-210': [[0, 9.9], [24, 8.1], [48, 6.9]], 'B-211': [[0, 9.7], [24, 8], [48, 6.6]] } } },
};
const CONTEXT = { 'B-201': ['mAb-1', 'v3', 'BR-01', '200 L'], 'B-203': ['mAb-1', 'v3', 'BR-01', '200 L'], 'B-204': ['mAb-1', 'v3', 'BR-07', null] };
const timing = (seconds = 0.033) => ({ seconds, target_seconds: 10, within_target: seconds <= 10 });
const ref = id => ({ kind: 'evidence', id, revision: DELIVERIES.find(d => d.id === id).revision, site_id: SITE });

function profile(id) {
  const dataset = DELIVERIES.find(d => d.id === id), held = VALUES[id];
  const series = dataset.parameters.flatMap(parameter => Object.entries(held[parameter].batches).map(([batch, points]) => ({ batch, parameter, unit: held[parameter].unit, mixed_units: false, n: points.length,
    first_time_h: points[0][0], last_time_h: points.at(-1)[0], min: Math.min(...points.map(p => p[1])), max: Math.max(...points.map(p => p[1])), mean: points.reduce((a, p) => a + p[1], 0) / points.length, values_in_review: 0 })));
  const times = series.flatMap(s => [s.first_time_h, s.last_time_h]);
  return { id: `prep_${id}`, profile_version: 'delivery-profile-1', values: series.reduce((n, s) => n + s.n, 0), rows: dataset.measurements, rows_not_usable: 0, batches: dataset.batches,
    parameters: dataset.parameters.map(parameter => ({ parameter, units: [held[parameter].unit], batches: Object.keys(held[parameter].batches).length, values: series.filter(s => s.parameter === parameter).reduce((n, s) => n + s.n, 0) })),
    series, time_range_h: [Math.min(...times), Math.max(...times)], values_in_review: dataset.review?.pending_values ?? 0, repeated_sample_times: 1, conflicting_sample_times: id === 'ds-oct' ? 1 : 0,
    site_id: SITE, delivery_id: id, delivery_revision: dataset.revision, delivery_name: dataset.delivery_name, verification: dataset.verification, review: dataset.review ?? null, status: 'current' };
}

/** The three results the batch_picture template calculates for a selection. Rows after 48 h are left off the page of
 *  measurements, as a long selection would leave them: their source then needs the single-value call. */
function picture(selection, { slow = false, noSpecs = false, noGaps = false } = {}) {
  const issues = [], used = [];
  for (const id of selection.dataset_ids) {
    const dataset = DELIVERIES.find(d => d.id === id);
    if (dataset.verification === 'provisional' && !selection.include_unverified) issues.push({ code: 'unverified_dataset', dataset_id: id, message: 'This delivery is still in review. Choose "Include values still in review" to include it.' });
    else used.push(id);
  }
  const inWindow = t => (selection.time_from_h == null || t >= selection.time_from_h) && (selection.time_to_h == null || t <= selection.time_to_h);
  const series = [], measurements = [];
  for (const id of used) {
    const held = VALUES[id][selection.parameter]; if (!held) continue; let row = 1;
    for (const [batch, all] of Object.entries(held.batches)) {
      const points = all.filter(p => inWindow(p[0])); row += all.length;
      if ((selection.batches.length && !selection.batches.includes(batch)) || !points.length) continue;
      series.push({ batch, parameter: selection.parameter, unit: held.unit, n: points.length, min: Math.min(...points.map(p => p[1])), max: Math.max(...points.map(p => p[1])), first_time_h: points[0][0], last_time_h: points.at(-1)[0], points });
      for (const [time_h, value] of points) if (time_h <= 48) measurements.push({ batch, parameter: selection.parameter, time_h, value, unit: held.unit, original_value: value, original_unit: held.unit,
        sources: [{ evidence_id: id, revision: ref(id).revision, measurement_id: `${batch}-${time_h}`, source: { path: VALUES[id].file, row: row - all.length + all.findIndex(p => p[0] === time_h) + 1, column: selection.parameter }, source_sha256: null }] });
    }
  }
  for (const batch of selection.batches) if (!series.some(s => s.batch === batch)) issues.push({ code: 'missing_requested_batch', batch, message: 'No usable measurements for this requested batch in the selected data.' });
  const conflict = used.includes('ds-oct') && selection.parameter === 'glucose' && series.some(s => s.batch === 'B-204') && inWindow(24);
  if (conflict) issues.push({ code: 'conflicting_measurements', message: 'Conflicting duplicates require source review.', batch: 'B-204', parameter: 'glucose', time_h: 24, conflicting_row_count: 2,
    values: [8, 8.4].map((value, i) => ({ batch: 'B-204', parameter: 'glucose', time_h: 24, value, unit: 'g/L', original_value: value, original_unit: 'g/L',
      sources: [{ evidence_id: 'ds-oct', revision: 2, measurement_id: `B-204-24-${i}`, source: { path: 'LIMS_October.csv', row: 26 + i, column: 'glucose' } }] })) });
  const deliveries = Object.fromEntries(used.map(id => [id, DELIVERIES.find(d => d.id === id).delivery_name]));
  const verification = used.filter(id => DELIVERIES.find(d => d.id === id).verification === 'provisional').map(id => ({ dataset_id: id, state: 'provisional', values_still_in_review_used: 6, open_checks: 3, rejected_values_excluded: 1,
    meaning: 'Nothing here was accepted on a reviewer\'s behalf. Verify the delivery before relying on these values.' }));
  const evidence_state = verification.length ? 'provisional' : 'verified';
  const measured = { measurements, measurement_count: series.reduce((n, s) => n + s.n, 0), measurements_offset: 0, next_offset: null, series, series_complete: true, truncated: false, deliveries, verification: verification.length ? verification : null,
    time_basis: 'elapsed hours as supplied in the delivery; no clock or phase alignment inferred' };
  const result = (operation, summary, data, extra = []) => ({ operation, site_id: SITE, owner_id: 'fixture-user', task_status: issues.length + extra.length ? 'needs_information' : 'completed', summary, data: { ...measured, ...data },
    issues: [...issues, ...extra], source_refs: used.map(ref), evidence_state, elapsed_seconds: 0.01, timing: { ...timing(0.01), phases: { authorize: 0.001, retrieve: 0.004, calculate: 0.005 } }, model_calls: 0, decisions: [] });
  const summary = [], unmatched_counts = {};
  for (let i = 0; i < series.length; i++) for (let j = i + 1; j < series.length; j++) {
    const left = series[i], right = series[j], pairs = left.points.filter(p => right.points.some(q => q[0] === p[0])).map(p => ({ time_h: p[0], left_value: p[1], right_value: right.points.find(q => q[0] === p[0])[1] }));
    if (!pairs.length) continue;
    const diffs = pairs.map(p => p.right_value - p.left_value), mean = diffs.reduce((a, b) => a + b, 0) / diffs.length, big = pairs.reduce((a, b) => Math.abs(b.right_value - b.left_value) > Math.abs(a.right_value - a.left_value) ? b : a);
    summary.push({ parameter: selection.parameter, unit: left.unit, left_batch: left.batch, right_batch: right.batch, matched_times: pairs.length, first_time_h: pairs[0].time_h, last_time_h: pairs.at(-1).time_h, mean_difference: mean,
      largest_difference: { ...big, difference: big.right_value - big.left_value }, share_of_samples_matched: pairs.length / Math.max(left.n, right.n), difference_definition: 'right batch minus left batch, at the same measured elapsed time',
      statistics: { n: diffs.length, mean, median: [...diffs].sort((a, b) => a - b)[Math.floor(diffs.length / 2)], standard_deviation: Math.sqrt(diffs.reduce((a, d) => a + (d - mean) ** 2, 0) / Math.max(1, diffs.length - 1)),
        min: Math.min(...diffs), max: Math.max(...diffs), root_mean_square: Math.sqrt(diffs.reduce((a, d) => a + d * d, 0) / diffs.length), share_positive: diffs.filter(d => d > 0).length / diffs.length,
        note: 'Descriptive only. Successive samples of one run are not independent, so no significance test is reported.' } });
    unmatched_counts[left.batch] = Math.max(unmatched_counts[left.batch] ?? 0, left.n - pairs.length); unmatched_counts[right.batch] = Math.max(unmatched_counts[right.batch] ?? 0, right.n - pairs.length);
  }
  const known = series.map(s => s.batch).filter(batch => CONTEXT[batch]);
  const attribute = (key, label, at) => { const values = Object.fromEntries(known.map(batch => [batch, CONTEXT[batch][at]])), seen = Object.values(values);
    return { attribute: key, label, values, verdict: seen.some(v => v == null) ? 'not_recorded' : new Set(seen).size > 1 ? 'differs' : 'same' }; };
  const attributes = known.length > 1 ? [attribute('product', 'Product', 0), attribute('process_version', 'Process version', 1), attribute('equipment_id', 'Equipment', 2), attribute('scale', 'Scale', 3)] : [];
  const differs = attributes.filter(a => a.verdict === 'differs').map(a => a.label), not_recorded = attributes.filter(a => a.verdict === 'not_recorded').map(a => a.label);
  const cohort = attributes.length ? { attributes, batch_records_found: known.length, batches: series.length, verdict: differs.length ? 'differs' : not_recorded.length ? 'not_established' : 'same_context', differs, not_recorded,
    meaning: 'A difference between batches made under different conditions may come from those conditions. Context that is not recorded is not assumed equal.' } : null;
  const compareIssues = [...(differs.length ? [{ code: 'cohort_differs', attributes: differs, message: `The batches differ in ${differs.join(', ').toLowerCase()}; the difference in values may come from that.` }] : []),
    ...(series.length > 1 && !summary.length ? [{ code: 'no_comparable_samples', message: 'Select at least two batches with matching measured times and compatible units.' }] : [])];
  const gaps = noSpecs || noGaps || !series.length ? [] : [
    { parameter: 'lactate', required_by: 'approved specification manual', status: 'unavailable', meaning: 'Not recorded in any selected delivery; it may be held in a system that is not connected here.' },
    ...(series.some(s => s.batch === 'B-204') ? [{ batch: 'B-204', parameter: 'osmolality', required_by: 'approved specification manual', status: 'required_missing', meaning: 'Required by an approved specification and absent for this batch.' }] : [])];
  const seconds = slow ? 14.2 : 0.033;
  return { template: { id: 'batch_picture', version: 'v1' }, saved: false, model_calls: 0, timing: timing(seconds), results: {
    reconcile: result('reconcile', `Reconciled ${measured.measurement_count} measurements.`, {}),
    compare: result('compare', `Compared ${summary.reduce((n, s) => n + s.matched_times, 0)} measured pairs.`, { comparison_summary: summary, comparison_count: summary.length, unmatched_counts, alignment: { tolerance_h: selection.align_tolerance_h ?? 0,
      method: selection.align_tolerance_h ? 'nearest sample within tolerance' : 'exact sample times' }, cohort, causal_claim_supported: false, limitations: ['Descriptive comparison only.'] }, compareIssues),
    gaps: result('check_gaps', `Found ${gaps.length} gaps against approved requirements.`, { gaps, gap_count: gaps.length, gaps_truncated: false, expectation_basis: noSpecs ? 'none' : 'approved_specifications', requirements_checked: noSpecs ? 0 : 2,
      gap_status_counts: Object.fromEntries(gaps.map(g => [g.status, 1])), coverage: 'Selected datasets and records only; not a finding of absence in other systems or SME knowledge.',
      ...(gaps.length ? { draft_request: { status: 'draft_not_sent', title: `Missing evidence: ${gaps.length} items`, sending: 'Choose who to ask and send it; the request is theirs to answer and stays attributed to them.',
        description: `These expected values were not found in the deliveries selected. For each, is it recorded somewhere else, was it not measured, or is it still to come?\n${gaps.map(g => `- ${g.parameter} (${g.required_by})`).join('\n')}`,
        questions: ['Is each item recorded in a system that is not connected here?', 'If an item was not measured, was that planned or a deviation?'] } } : {}) },
      [...(noSpecs ? [{ code: 'expectations_required', message: 'Specify expected parameters or document kinds; absence cannot be inferred without a requirement.' }] : []),
        ...(gaps.length ? [{ code: 'missing_expected_evidence', message: 'Expected evidence is absent from the selected inputs; it may exist elsewhere.' }] : [])]) } };
}
const ACTIONS = { operations: [['approve_capa', 'high', ['qa']], ['change_recipe_parameter', 'high', ['qa', 'msat']], ['close_deviation', 'high', ['qa']], ['place_hold', 'medium', ['supervisor']], ['release_batch', 'critical', ['qa', 'qa_reviewer']], ['request_retest', 'medium', ['supervisor']]]
  .map(([operation, risk, approved_by]) => ({ operation, label: (operation[0].toUpperCase() + operation.slice(1)).replaceAll('_', ' '), risk, approved_by })), other: { risk: 'medium', approved_by: ['supervisor'] },
  note: 'A proposal is a draft for review. It is carried out only after approval, and is complete only with a receipt.' };
const saved = (id, operation, data, summary) => ({ id, revision: 1, operation, site_id: SITE, owner_id: 'fixture-user', task_status: 'completed', status: 'current', summary, data, issues: [], source_refs: [], elapsed_seconds: 0.002, model_calls: 0,
  decision_model_calls: 0, decisions: [], timing: { ...timing(0.002), phases: { authorize: 0.0003, retrieve: 0.0012, calculate: 0.0005 } }, proposals: [], work_status: 'complete' });
const TRACE = record_id => saved('work-trace-1', 'trace_impact', { affected_batches: ['B-204'], causal_claim_supported: false, exposure_confirmed: false,
  genealogy: { batches_without_usage_records: 1, complete: false, examples: ['B-201'], status: 'recorded_usage_found', note: 'Usage comes from executed procedure steps recorded here. 1 batches at this site have no recorded steps, so their exposure cannot be ruled out from these records.' },
  limitation: 'Recorded usage shows what was used in which batch. Whether a batch was affected is a quality assessment. Records that only mention the identifier are candidates to confirm.',
  recorded_usage: [{ basis: 'recorded_usage', batch_id: 'B-204', identifier: record_id, performed_at: '2026-11-01T09:00:00Z', record: { id: 'inst-1', kind: 'procedure_instance', revision: 1, site_id: SITE }, step_id: 'feed', used_as: 'material lot' }],
  recorded_usage_count: 1, records: [{ kind: 'case', id: 'case-9', label: 'Deviation NC-9 mentions the feed lot', time: '2026-11-03T10:00:00Z', shared_identifiers: [{ identifier: record_id, status: 'candidate' }] }],
  records_searched: 7, results_depending_on_these_records: [], target: null, target_missing: `There is no record ${record_id} in this workspace; these are records that name ${record_id}.` }, 'Prepared 1 records.');
const CAUSES = saved('work-causes-1', 'suggest_causes', { causal_status: 'hypotheses_only', causal_claim_supported: false, establishing_a_cause: 'A cause is established only by the case review that closes the investigation.',
  subject: { record_id: 'B-204', kind: 'batch', label: 'Batch B-204', time: '2026-11-01T08:00:00Z', time_basis: 'event_time' },
  chronology: [{ id: 'F1', record: { kind: 'evidence', id: 'ev-1', revision: 1 }, label: 'Feed lot LOT-7781', time: '2026-10-31T08:00:00Z', time_basis: 'event_time', link: 'identifier in an ID field of both records', shared_identifiers: ['LOT-7781'], screening: 'not_ruled_out' }],
  hypotheses: [{ id: 'H1', kind: 'hypothesis', factor_id: 'F1', statement: 'Feed lot LOT-7781 may have contributed.', supported_by: ['Shares LOT-7781 with the subject.'], not_established: ['That the lot was physically involved.'], next_check: 'Confirm the usage window of feed lot LOT-7781.' }],
  contrary_evidence: [], precedents: [], unknowns: ['Whether records you cannot access hold other candidates.'], coverage: 'Linked records at this site only.', next_step: 'No hypothesis here is a finding.' },
  'Screened 1 linked record: 1 hypothesis to check. No cause is established.');
const EXPLAINED = { result_id: 'x', run_id: 'run_x', model: 'fixture-model', model_calls: 1, cached: false, cost_usd: 0.002, timing: { ...timing(3.1), model_seconds: 2.9 }, requires_human_review: true, status: 'completed',
  explanation: 'B-204 runs about 0.8 g/L below B-201 at every shared sample time.', observations: ['The difference is steady from 0 h to 96 h.'],
  hypotheses: [{ statement: 'The lower starting glucose in B-204 may come from the different bioreactor.', check: 'Compare the media preparation records for BR-01 and BR-07.', kind: 'hypothesis' }],
  unknowns: ['Whether the feed schedule was the same.'], grounding: 'Every number in this explanation appears in the calculated result. The wording is the model\'s; the figures are the host\'s.' };
const WITHHELD = { result_id: 'x', run_id: 'run_y', model: null, model_calls: 0, cached: false, cost_usd: 0, timing: { ...timing(0.002), model_seconds: 0 }, requires_human_review: true, status: 'unavailable',
  reason: 'no qualified, available model for comparison_explanation', next_step: 'The calculated result is unchanged. Ask the assistant for a longer investigation.' };
const trendSeries = ['B-201', 'B-204'].map(batch => ({ key: `run-oct:${batch}`, batch, run_id: 'run-oct', cmo: 'Fixture CDMO', delivery_name: 'October runs', completed_at: '2026-11-02T09:00:00Z', delivery_verified: true, time_basis: 'recorded_hours', unit: 'g/L',
  points: [[0, 10, `${batch}-0`], [12, 9.4, `${batch}-12`]], points_total: 2, points_without_time: 0, sampled_every: 1,
  summary: { n: 2, mean: 9.7, min: { time_h: 12, value: 9.4, id: `${batch}-12` }, max: { time_h: 0, value: 10, id: `${batch}-0` }, first: { time_h: 0, value: 10, id: `${batch}-0` }, last: { time_h: 12, value: 9.4, id: `${batch}-12` } } }));
const TRENDS = { parameters: [{ id: 'glucose', units: ['g/L'], batches: 2, values: 4 }], batches: trendSeries, deliveries: 1, parameter: 'glucose', series: trendSeries, standouts: { from_sampled_profiles: false } };

async function fixture(browser, { deliveries = DELIVERIES, slow = false, noSpecs = false, noGaps = false, explanation = EXPLAINED, plans: seeded = [], viewport = { width: 1440, height: 900 }, start = '/workbench/', failDeliveries = 0, failPreview = 0, remembered = null } = {}) {
  const context = await browser.newContext({ viewport });
  const page = await context.newPage(); page.setDefaultTimeout(12000);
  const errors = [], unexpected = [], posts = [], gets = [], plans = new Map(), proposals = new Map(), requests = new Map();
  let ids = 0, runs = 0;
  const stands = step => { if (step.status !== 'open') return step.status; const p = step.proposal || {};
    if (p.status === 'proposed') return 'waiting for approval'; if (p.status === 'approved') return 'approved, not yet carried out'; if (step.request) return step.request.status === 'answered' ? 'reply received' : 'waiting for a reply'; return 'to do'; };
  const view = plan => { const steps = plan.steps.map(step => { const shown = { ...step };
    if (step.proposal_id) { const p = proposals.get(step.proposal_id); shown.proposal = { operation: p.operation, target_id: p.target_id, status: p.status, execution_status: p.execution_status, effectiveness: 'unknown', required_roles: p.required_roles, risk: p.risk }; }
    if (step.work_request_id) { const r = requests.get(step.work_request_id); shown.request = { title: r.title, owner_id: r.owner_id, owner_name: (PEOPLE.find(person => person.id === r.owner_id) || {}).label, status: r.status, reply: r.reply ?? null, answered_at: r.answered_at ?? null }; }
    shown.stands = stands(shown); return shown; });
    return { ...clone(plan), steps, results: plan.result_ids.map(id => ({ id, operation: 'compare', summary: 'Saved result', status: 'current', work_status: 'complete' })),
      progress: { open: steps.filter(s => s.status === 'open').length, done: steps.filter(s => s.status === 'done').length, waiting_for_approval: steps.filter(s => s.stands === 'waiting for approval').length, waiting_for_reply: steps.filter(s => s.stands === 'waiting for a reply').length } }; };
  const newStep = body => ({ step_id: `step-${++ids}`, kind: body.kind ?? 'check', text: body.text, result_id: body.result_id ?? null, basis: body.basis ?? null, proposal_id: body.proposal_id ?? null, work_request_id: body.work_request_id ?? null,
    status: 'open', added_by: 'fixture-user', created_at: '2026-11-15T07:00:00Z', done_at: null, outcome: null });
  for (const seed of seeded) plans.set(seed.id, { owner_id: 'fixture-user', site_id: SITE, status: 'open', result_ids: [], created_at: '2026-11-14T08:00:00Z', updated_at: '2026-11-14T09:30:00Z', revision: 3, ...seed, steps: (seed.steps ?? []).map(step => ({ ...newStep(step), ...step })) });
  page.on('pageerror', error => errors.push(error.message));
  await page.addInitScript(plan => {
    localStorage.setItem('sievance.local-session.v1', JSON.stringify({ tenant_id: 'workflow-fixture', actor_id: 'fixture-user', email: 'fixture@example.test', name: 'UI fixture' }));
    localStorage.setItem('sievance.organization:fixture-user', 'workflow-fixture');
    if (plan && !sessionStorage.getItem('seeded')) { localStorage.setItem('workbench.plan:NF1', plan); sessionStorage.setItem('seeded', '1'); }
  }, remembered);
  const headers = { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': '*', 'Access-Control-Allow-Methods': 'GET,POST,OPTIONS' };
  const respond = (route, data, status = 200) => route.fulfill({ status, headers, body: JSON.stringify(data) });
  await page.route('**/*', async route => {
    const req = route.request(), url = new URL(req.url()), at = decodeURIComponent(url.pathname);
    if (!at.startsWith('/v1/') && !at.startsWith('/api/')) return route.continue();
    if (req.method() === 'OPTIONS') return route.fulfill({ status: 204, headers, body: '' });
    const body = req.method() === 'POST' ? req.postDataJSON() : null;
    if (body) posts.push({ path: at, body }); else gets.push(at);
    if (at === '/v1/account') return respond(route, { actor_id: 'fixture-user', organizations: [{ id: 'workflow-fixture', name: 'Local UI fixture', roles: ['admin'], site_ids: [SITE], onboarding_complete: true }] });
    if (at === '/v1/me') return respond(route, { tenant_id: 'workflow-fixture', actor_id: 'fixture-user', roles: ['admin'], auth_mode: 'development' });
    if (at === '/v1/notifications') return respond(route, { items: [], unread: 0 });
    if (at === '/v1/demo/workspace') return respond(route, { detail: 'No demo workspace in this fixture' }, 404);
    if (at === '/v1/specifications') return respond(route, { specifications: [] });
    if (at === '/api/cmo-ingestion/trends') return respond(route, TRENDS);
    // The assistant, when a result is handed to it. Nothing is sent to a model here.
    if (at === '/v1/process-model/conversations') return body ? respond(route, { detail: 'No conversation is created in this fixture' }, 400) : respond(route, { conversations: [] });
    if (at === '/v1/workspace-tasks/catalog') return respond(route, { operations: [], template_version: 'fixture', decision_model: { enabled: false } });
    if (at === '/v1/cmo-datasets' && !body) { assert.equal(url.searchParams.get('site_id'), SITE); assert.equal(url.searchParams.get('include_provisional'), 'true');
      if (failDeliveries-- > 0) return respond(route, { detail: 'The evidence store is not reachable' }, 503); return respond(route, { datasets: deliveries }); }
    const profiled = at.match(/^\/v1\/workspace-tasks\/deliveries\/([^/]+)\/profile$/);
    if (profiled) return respond(route, profile(profiled[1]));
    if (at === '/v1/workspace-tasks/templates/batch_picture/preview') { if (failPreview-- > 0) return respond(route, { detail: 'The selected delivery was superseded; publish the current delivery again' }, 400); return respond(route, picture(body.selection, { slow, noSpecs, noGaps })); }
    if (at === '/v1/workspace-tasks/templates/batch_picture/run') { runs++; const live = picture(body.selection, { slow, noSpecs, noGaps }).results;
      return respond(route, { template: { id: 'batch_picture', version: 'v1', title: 'Consolidate and compare' }, flow_run_id: `flowrun-${runs}`, status: 'completed', problems: [], model_calls: 0, timing: { ...timing(0.017), tasks: 3 },
        results: Object.fromEntries(Object.entries(live).map(([name, result]) => [name, { ...result, id: `work-${name}-${runs}`, status: 'current', proposals: [], work_status: 'needs_evidence' }])) }); }
    if (at === '/v1/workspace-tasks/run' || at === '/v1/workspace-tasks/preview') {
      if (body.operation === 'trace_impact') return respond(route, TRACE(body.record_id));
      if (body.operation === 'suggest_causes') return respond(route, CAUSES);
      assert.equal(body.operation, 'reconcile'); const held = VALUES[body.dataset_ids.find(id => VALUES[id][body.parameter]?.batches[body.batches[0]])];
      const value = held[body.parameter].batches[body.batches[0]].find(p => p[0] === body.time_from_h)[1];
      return respond(route, saved('work-source-1', 'reconcile', { measurements: [{ batch: body.batches[0], parameter: body.parameter, time_h: body.time_from_h, value, unit: 'g/L', original_value: value * 1000, original_unit: 'mg/L',
        sources: [{ evidence_id: 'ds-oct', revision: 2, measurement_id: 'm-late', source: { path: 'LIMS_October_late.xlsx', sheet: 'Glucose', cell: 'C9' } }] }], measurement_count: 1, series: [] }, 'Reconciled 1 measurement.'));
    }
    if (at === '/v1/workspace-tasks/actions') return respond(route, ACTIONS);
    if (at === '/v1/worklist/people') return respond(route, { people: PEOPLE });
    const onResult = at.match(/^\/v1\/workspace-tasks\/results\/([^/]+)\/(propose|request-evidence|explain)$/);
    if (onResult && onResult[2] === 'propose') { const action = ACTIONS.operations.find(item => item.operation === body.operation);
      const proposal = { proposal_id: `prop-${++ids}`, target_system: 'quality-review', operation: body.operation, target_id: body.target_id, rationale: body.rationale, expected_result: body.expected_result, follow_up_measure: body.follow_up_measure ?? null,
        constraints: ['The result it rests on has open checks: Conflicting duplicates require source review.'], risk: action.risk, required_roles: action.approved_by, status: 'proposed', execution_status: 'not_started', effectiveness: 'unknown', site_id: SITE };
      proposals.set(proposal.proposal_id, proposal); return respond(route, proposal, 201); }
    if (onResult && onResult[2] === 'request-evidence') { const request = { id: `assistant_work_request:${++ids}`, title: body.title ?? 'Missing evidence', description: body.description ?? '', owner_id: body.owner_id, site_id: SITE, status: 'open', requested_by: 'fixture-user', revision: 1 };
      requests.set(request.id, request); return respond(route, request, 201); }
    if (onResult) return respond(route, { ...explanation, result_id: onResult[1] });
    if (at === '/v1/work-plans') {
      if (!body) return respond(route, { plans: [...plans.values()].map(plan => ({ id: plan.id, title: plan.title, status: plan.status, site_id: SITE, created_at: plan.created_at, updated_at: plan.updated_at, revision: plan.revision, results: plan.result_ids.length,
        open_steps: plan.steps.filter(s => s.status === 'open').length, steps: plan.steps.length })) });
      const plan = { id: `plan-${++ids}`, owner_id: 'fixture-user', site_id: body.site_id, title: body.title, selection: body.selection, status: 'open', result_ids: [], steps: [], created_at: '2026-11-15T07:00:00Z', updated_at: '2026-11-15T07:00:00Z', revision: 1 };
      plans.set(plan.id, plan); return respond(route, view(plan), 201);
    }
    const onPlan = at.match(/^\/v1\/work-plans\/([^/]+)(?:\/(update|steps)(?:\/([^/]+))?)?$/);
    if (onPlan) {
      const plan = plans.get(onPlan[1]); if (!plan) return respond(route, { detail: 'No such work plan' }, 404);
      if (!body) return respond(route, view(plan));
      if (body.expected_revision !== plan.revision) return respond(route, { detail: 'the plan changed; refresh before editing' }, 409);
      if (onPlan[2] === 'update') { for (const key of ['title', 'status', 'selection']) if (body[key] != null) plan[key] = body[key]; }
      else if (onPlan[3]) { const step = plan.steps.find(s => s.step_id === onPlan[3]); for (const key of ['text', 'outcome', 'status']) if (body[key] != null) step[key] = body[key]; }
      else { plan.steps.push(newStep(body)); if (body.result_id && !plan.result_ids.includes(body.result_id)) plan.result_ids.push(body.result_id); }
      plan.revision++; plan.updated_at = '2026-11-15T07:05:00Z'; return respond(route, view(plan), onPlan[2] === 'steps' && !onPlan[3] ? 201 : 200);
    }
    unexpected.push(`${req.method()} ${at}`); return respond(route, { detail: 'Unexpected fixture request' }, 404);
  });
  await page.goto(base + start, { waitUntil: 'domcontentloaded', timeout: 60000 });
  const posted = suffix => posts.filter(p => p.path.endsWith(suffix));
  /** Waits until a request ending in `suffix` satisfies `test`, and returns its body. */
  const until = async (suffix, test = () => true, message = `a request to ${suffix}`) => {
    for (let i = 0; i < 80; i++) { const hit = posted(suffix).find(p => test(p.body)); if (hit) return hit.body; await page.waitForTimeout(100); }
    assert.fail(`Timed out waiting for ${message}. Saw: ${JSON.stringify(posted(suffix).map(p => p.body)).slice(0, 900)}`);
  };
  const shot = async name => { if (!shots) return; const main = page.locator('#main');
    const height = await main.evaluate(node => node.scrollHeight + (window.innerHeight - node.clientHeight));
    await page.setViewportSize({ width: viewport.width, height: Math.max(viewport.height, Math.ceil(height)) }); await page.waitForTimeout(400); await page.screenshot({ path: path.join(shots, name) }); await page.setViewportSize(viewport); };
  return { context, page, posts, gets, posted, until, shot, plans, proposals,
    /** The colleague who was asked replies (from their own overview). */
    answer: reply => { for (const request of requests.values()) Object.assign(request, { status: 'answered', reply, answered_at: '2026-11-15T09:00:00Z' }); },
    ready: () => page.locator('[data-point="B-201@24"]').waitFor(),
    /** Someone else (another tab, a colleague's hand-off) changes the plan. */
    touch: id => { const plan = plans.get(id); plan.steps.push(newStep({ kind: 'note', text: 'Added from another window' })); plan.revision++; },
    verify: () => { assert.deepEqual(errors, []); assert.deepEqual(unexpected, []); } };
}
const FIRST = { dataset_ids: ['ds-oct'], batches: [], parameter: 'glucose', time_from_h: null, time_to_h: null, align_tolerance_h: 0, include_unverified: false, limit: 100, site_id: SITE };
const nothingSaved = f => { assert.equal(f.posted('/batch_picture/run').length, 0, 'Looking at the picture saves no result'); assert.equal(f.posts.filter(p => p.path.startsWith('/v1/work-plans')).length, 0, 'Looking at the picture creates no plan'); };
const steps = f => f.page.getByTestId('plan-step');
/** Points the mouse at a plotted value, as a person does. The chart takes the nearest value, whichever hit area lies on top. */
const aim = async (f, point, click = true) => { const mark = f.page.locator(`[data-point="${point}"]`); await mark.scrollIntoViewIfNeeded(); const box = await mark.boundingBox();
  await f.page.mouse.move(box.x + box.width / 2, box.y + box.height / 2); if (click) await f.page.mouse.click(box.x + box.width / 2, box.y + box.height / 2); };

const scenarios = {
  async first_visit(browser) {
    const f = await fixture(browser, { plans: [{ id: 'plan-old', title: 'pH drift in B-204', selection: { dataset_ids: ['ds-oct'], parameter: 'pH', batches: ['B-201', 'B-204'], site_id: SITE }, steps: [{ kind: 'check', text: 'Review the probe calibration' }] }] });
    try {
      await f.ready();
      assert.deepEqual((await f.until('/batch_picture/preview')).selection, FIRST, 'The first picture is the newest verified delivery, its first parameter, every batch');
      assert(await f.page.getByRole('checkbox', { name: 'Use delivery October runs', exact: true }).isChecked()); assert(!(await f.page.getByRole('checkbox', { name: 'Use delivery November runs', exact: true }).isChecked()), 'A newer delivery still in review is not preselected');
      assert.equal(await f.page.getByLabel('Parameter', { exact: true }).inputValue(), 'glucose');
      assert.equal(await f.page.getByRole('group', { name: 'Batches', exact: true }).getByRole('button', { name: 'All batches', exact: true }).getAttribute('aria-pressed'), 'true');
      await f.page.getByTestId('consolidation').getByText('23 values · 3 batches · 2 parameters · 0 open checks · 1 conflicting sample time', { exact: true }).waitFor();
      await f.page.getByTestId('picture-timing').getByText('Updated in 0.03 s', { exact: true }).waitFor();
      assert.equal(await f.page.getByTestId('largest-difference').count(), 1, 'The largest difference is marked on the chart');
      const table = f.page.getByTestId('comparison-table'); await table.getByRole('rowheader', { name: 'B-204 minus B-201' }).waitFor();
      const row = table.getByRole('row').filter({ hasText: 'B-204 minus B-201' });
      for (const text of ['-0.8 g/L', '0 to 96 h', '0 g/L', '85.7%', 'B-204 9.2 g/L · B-201 10 g/L']) assert((await row.innerText()).includes(text), `Comparison row shows ${text}: ${await row.innerText()}`);
      const fair = f.page.getByTestId('fair-comparison');
      assert.equal(await fair.locator('[data-verdict="differs"]').innerText().then(t => t.replace(/\s+/g, ' ')), 'Equipment Differs B-201 BR-01 B-203 BR-01 B-204 BR-07');
      assert((await fair.locator('[data-verdict="not_recorded"]').innerText()).includes('not recorded'), 'A missing context value is named as not recorded');
      const tone = verdict => fair.locator(`[data-verdict="${verdict}"] span.rounded-pill`).first().evaluate(node => getComputedStyle(node).borderStyle + getComputedStyle(node).backgroundColor);
      assert.notEqual(await tone('not_recorded'), await tone('same'), 'Not recorded must not look like Same');
      await f.page.getByTestId('finding-conflict').getByText('B-204 has 2 different glucose values at 24 h', { exact: true }).waitFor();
      assert.equal(await f.page.getByTestId('finding-conflict').getByRole('link', { name: 'Open the delivery to resolve' }).getAttribute('href'), '/cmo/?run=run-oct');
      await f.page.getByTestId('plan-status').getByText(/^Not saved yet\./).waitFor();
      const work = f.page.getByRole('navigation', { name: 'Primary', exact: true }).getByRole('link', { name: 'Workbench', exact: true });
      assert.equal(await work.getAttribute('aria-current'), 'page');
      const text = await f.page.getByTestId('workbench').innerText();
      for (const internal of ['ds-oct', 'run-oct', 'required_missing', 'not_recorded', 'cohort', 'needs_information', 'work-compare']) assert(!text.includes(internal), `No internal name on the page: ${internal}`);
      nothingSaved(f); f.verify();
    } finally { await f.context.close(); }
  },
  async selection_changes(browser) {
    const f = await fixture(browser);
    try {
      await f.ready(); const batches = f.page.getByRole('group', { name: 'Batches', exact: true });
      await f.page.getByLabel('Parameter', { exact: true }).selectOption('pH');
      assert.deepEqual((await f.until('/batch_picture/preview', b => b.selection.parameter === 'pH')).selection, { ...FIRST, parameter: 'pH' });
      await f.page.locator('[data-point="B-201@24"]').waitFor(); await f.page.locator('svg text').filter({ hasText: /^pH \(pH\)$/ }).waitFor();
      await batches.getByRole('button', { name: 'B-201', exact: true }).click(); await batches.getByRole('button', { name: 'B-204', exact: true }).click();
      assert.deepEqual((await f.until('/batch_picture/preview', b => b.selection.batches.length === 2)).selection, { ...FIRST, parameter: 'pH', batches: ['B-201', 'B-204'] });
      await f.page.getByLabel('Parameter', { exact: true }).selectOption('glucose');
      await f.page.getByRole('group', { name: 'Time window presets' }).getByRole('button', { name: 'First 24 h', exact: true }).click();
      assert.deepEqual((await f.until('/batch_picture/preview', b => b.selection.time_to_h === 24)).selection, { ...FIRST, batches: ['B-201', 'B-204'], time_from_h: 0, time_to_h: 24 });
      await f.page.locator('[data-point="B-201@24"]').waitFor(); assert.equal(await f.page.locator('[data-point="B-201@48"]').count(), 0, 'Samples outside the window are not drawn');
      await f.page.getByLabel('To (hours)', { exact: true }).fill('48');
      await f.until('/batch_picture/preview', b => b.selection.time_from_h === 0 && b.selection.time_to_h === 48); await f.page.locator('[data-point="B-204@48"]').waitFor();
      // Typing is debounced: the intermediate "4" is not requested once "48" follows straight away.
      assert.equal(f.posted('/batch_picture/preview').filter(p => p.body.selection.time_to_h === 4).length, 0, 'A keystroke that is immediately superseded is not requested');
      await f.page.getByLabel('From (hours)', { exact: true }).fill('60'); await f.page.getByRole('alert').filter({ hasText: '“From” is later than “To”' }).waitFor(); await f.page.waitForTimeout(600);
      assert.equal(f.posted('/batch_picture/preview').filter(p => p.body.selection.time_from_h === 60).length, 0, 'A window that ends before it starts is not requested');
      await f.page.getByRole('group', { name: 'Time window presets' }).getByRole('button', { name: 'All', exact: true }).click();
      await f.page.getByText('More options', { exact: true }).click(); await f.page.getByLabel('Pair samples up to this many hours apart').fill('2');
      assert.deepEqual((await f.until('/batch_picture/preview', b => b.selection.align_tolerance_h === 2)).selection, { ...FIRST, batches: ['B-201', 'B-204'], align_tolerance_h: 2 });
      await f.page.getByText('Samples up to 2 h apart are paired; nothing is interpolated.').waitFor();
      await f.page.getByRole('group', { name: 'Batches drawn' }).getByRole('button', { name: /^B-204/ }).click();
      assert.equal(await f.page.locator('[data-point^="B-204@"]').count(), 0, 'A legend chip hides its batch'); assert.equal(await f.page.getByTestId('largest-difference').count(), 0, 'The marked difference goes with a hidden batch');
      nothingSaved(f); f.verify();
    } finally { await f.context.close(); }
  },
  async point_source(browser) {
    const f = await fixture(browser);
    try {
      await f.ready(); const panel = f.page.getByTestId('source-panel');
      await panel.getByText('Click a point to see the file and the place its value was read from.').waitFor();
      await aim(f, 'B-201@24', false); await f.page.getByRole('tooltip').getByText('8.8 g/L', { exact: true }).waitFor();
      await aim(f, 'B-201@24');
      await panel.getByText('B-201 · 24 h', { exact: true }).waitFor(); await panel.getByText('8.8 g/L', { exact: true }).waitFor();
      await panel.getByText('LIMS_October.csv', { exact: true }).waitFor(); await panel.getByText('row 4, column glucose', { exact: true }).waitFor(); await panel.getByText('October runs · revision 2', { exact: true }).waitFor();
      assert.equal(await panel.getByRole('link', { name: 'Open this delivery' }).getAttribute('href'), '/cmo/?run=run-oct');
      assert.equal(f.posted('/v1/workspace-tasks/run').length, 0, 'A value already on the page shows its source without another request');
      await aim(f, 'B-201@72');
      const sent = await f.until('/v1/workspace-tasks/preview');
      assert.equal(f.posted('/v1/workspace-tasks/run').length, 0, 'Looking up a source saves no result');
      assert.deepEqual(sent, { ...FIRST, operation: 'reconcile', batches: ['B-201'], time_from_h: 72, time_to_h: 72, limit: 5 }, 'One value is looked up by narrowing the selection to its batch and time');
      await panel.getByText('LIMS_October_late.xlsx', { exact: true }).waitFor(); await panel.getByText('sheet Glucose, cell C9', { exact: true }).waitFor(); await panel.getByText('7000 mg/L', { exact: true }).waitFor();
      await f.page.locator('[data-point="B-204@0"]').focus(); await f.page.keyboard.press('Enter'); await panel.getByText('B-204 · 0 h', { exact: true }).waitFor();
      await f.page.getByText(/^Values as a table/).click(); await f.page.getByRole('row').filter({ hasText: 'B-203' }).filter({ hasText: '24 h' }).getByRole('button', { name: 'Source', exact: true }).click();
      await panel.getByText('B-203 · 24 h', { exact: true }).waitFor(); await panel.getByText('row 10, column glucose', { exact: true }).waitFor();
      await panel.getByRole('button', { name: 'Close source' }).click(); await panel.getByText('Click a point to see the file and the place its value was read from.').waitFor();
      nothingSaved(f); f.verify();
    } finally { await f.context.close(); }
  },
  async in_review(browser) {
    const f = await fixture(browser);
    try {
      await f.ready(); assert.equal(await f.page.getByRole('checkbox', { name: 'Include values still in review', exact: true }).count(), 0, 'The option appears only with a delivery still in review');
      await f.page.getByRole('checkbox', { name: 'Use delivery November runs', exact: true }).check();
      assert.deepEqual((await f.until('/batch_picture/preview', b => b.selection.dataset_ids.includes('ds-nov'))).selection, { ...FIRST, dataset_ids: ['ds-oct', 'ds-nov'] }, 'Values still in review are never included by default');
      const include = f.page.getByRole('checkbox', { name: 'Include values still in review', exact: true }); assert(!(await include.isChecked()));
      await f.page.getByText('November runs is not used: its values are still in review.', { exact: false }).waitFor();
      await f.page.getByTestId('consolidation').getByText('29 values · 5 batches · 2 parameters · 3 open checks · 1 conflicting sample time', { exact: true }).waitFor();
      await f.page.waitForTimeout(500); assert.equal(await f.page.locator('[data-point^="B-210@"]').count(), 0, 'A delivery in review is not drawn until it is included'); assert.equal(await f.page.getByTestId('finding-in-review').count(), 0);
      await include.check();
      assert.equal((await f.until('/batch_picture/preview', b => b.selection.include_unverified)).selection.include_unverified, true);
      await f.page.locator('[data-point="B-210@24"]').waitFor(); await f.page.getByTestId('finding-in-review').getByText('November runs: 6 values still in review used · 3 open checks · 1 rejected value left out', { exact: true }).waitFor();
      await f.page.getByRole('checkbox', { name: 'Use delivery October runs', exact: true }).uncheck(); await f.page.getByRole('checkbox', { name: 'Include values still in review', exact: true }).uncheck();
      await f.page.getByTestId('picture-empty').getByText('A selected delivery is still in review and is not used.', { exact: false }).waitFor();
      nothingSaved(f); f.verify();
    } finally { await f.context.close(); }
  },
  async ask_for_evidence(browser) {
    const f = await fixture(browser);
    try {
      await f.ready(); const missing = f.page.getByTestId('finding-missing');
      await missing.getByText('2 expected items missing from the selected deliveries', { exact: true }).waitFor();
      for (const text of ['Required and missing · 1', 'Not recorded in any selected delivery · 1', 'osmolality · batch B-204', 'It may be held in a system that is not connected here.']) await missing.getByText(text, { exact: false }).first().waitFor();
      await missing.getByRole('button', { name: 'Ask for this evidence', exact: true }).click();
      const form = f.page.getByRole('form', { name: 'Ask for this evidence' });
      assert((await form.getByLabel('Request', { exact: true }).inputValue()).includes('- lactate (approved specification manual)'), 'The drafted request is shown, ready to edit');
      assert(await form.getByRole('button', { name: 'Send request', exact: true }).isDisabled(), 'A request needs someone to ask'); nothingSaved(f);
      await form.getByLabel('Subject', { exact: true }).fill('Lactate and osmolality for October'); await form.locator('select[aria-label="Who to ask"]').selectOption({ label: 'Carla Reyes' });
      await form.getByRole('button', { name: 'Send request', exact: true }).click();
      await missing.getByRole('status').filter({ hasText: 'Request sent to Carla Reyes. It is in next steps, waiting for a reply.' }).waitFor();
      assert.deepEqual((await f.until('/batch_picture/run')).selection, FIRST, 'The results a request cites are saved from the selection in view');
      const sent = f.posts.find(p => p.path.endsWith('/request-evidence'));
      assert.equal(sent.path, '/v1/workspace-tasks/results/work-gaps-1/request-evidence'); assert.equal(sent.body.owner_id, 'colleague'); assert.equal(sent.body.title, 'Lactate and osmolality for October'); assert(sent.body.description.includes('Is each item recorded in a system that is not connected here?'));
      const created = f.posts.find(p => p.path === '/v1/work-plans').body; assert.deepEqual(created, { site_id: SITE, title: 'glucose · all batches', selection: FIRST }, 'The plan is created silently, named after what is in view');
      const step = f.posts.find(p => /^\/v1\/work-plans\/plan-\d+\/steps$/.test(p.path)).body;
      assert.equal(step.kind, 'request'); assert.equal(step.result_id, 'work-gaps-1'); assert.match(step.work_request_id, /^assistant_work_request:/); assert.equal(step.expected_revision, 1);
      await steps(f).filter({ hasText: 'Lactate and osmolality for October' }).getByTestId('step-stands').getByText('Waiting for a reply', { exact: true }).waitFor();
      await steps(f).getByText('Sent to Carla Reyes: Lactate and osmolality for October', { exact: true }).waitFor();
      await f.page.getByTestId('plan-status').getByText('1 step to do · 1 waiting for a reply', { exact: true }).waitFor();
      await f.page.getByTestId('finding-context').getByRole('button', { name: 'Add a check to next steps', exact: true }).click();
      await f.page.getByTestId('finding-context').getByRole('button', { name: 'Added to next steps', exact: true }).waitFor();
      const check = f.posts.filter(p => /\/steps$/.test(p.path)).at(-1).body; assert.equal(check.kind, 'check'); assert.equal(check.result_id, 'work-compare-1'); assert.equal(check.expected_revision, 2); assert.equal(check.basis, 'The batches differ in equipment.');
      assert.equal(f.posted('/batch_picture/run').length, 1, 'A second action on the same selection reuses the saved results');
      await steps(f).filter({ hasText: 'Check whether the difference in equipment' }).getByText('Prompted by: The batches differ in equipment.', { exact: true }).waitFor();
      // Changing what is in view updates the saved plan, and the next action saves results for the new selection.
      await f.page.getByRole('group', { name: 'Batches', exact: true }).getByRole('button', { name: 'B-204', exact: true }).click(); await f.page.getByRole('group', { name: 'Batches', exact: true }).getByRole('button', { name: 'B-201', exact: true }).click();
      const update = await f.until('/update', b => b.selection?.batches.length === 2); assert.deepEqual(update.selection, { ...FIRST, batches: ['B-204', 'B-201'] }); assert.equal(update.expected_revision, 3);
      await f.page.getByTestId('finding-context').getByRole('button', { name: 'Add a check to next steps', exact: true }).click(); await f.until('/batch_picture/run', b => b.selection.batches.length === 2);
      await f.page.getByTestId('finding-context').getByRole('button', { name: 'Added to next steps', exact: true }).waitFor(); assert.equal(f.posts.filter(p => /\/steps$/.test(p.path)).at(-1).body.result_id, 'work-compare-2');
      // Carla answers from her own overview. Back here the step reads as answered, shows her words, and can be closed.
      f.answer('Lactate was not sampled on B-204; see LIMS-4411.'); await f.page.reload(); await steps(f).first().waitFor();
      const answered = steps(f).filter({ hasText: 'Lactate and osmolality for October' });
      await answered.getByTestId('step-stands').getByText('Reply received', { exact: true }).waitFor();
      await answered.getByTestId('step-reply').getByText('Carla Reyes replied: Lactate was not sampled on B-204; see LIMS-4411.', { exact: false }).waitFor();
      await answered.getByTestId('step-reply').getByText('Their statement, not verified evidence.', { exact: false }).waitFor();
      await answered.getByRole('button', { name: 'Mark done', exact: true }).waitFor();
      f.verify();
    } finally { await f.context.close(); }
  },
  async propose_action(browser) {
    const f = await fixture(browser);
    try {
      await f.ready(); const region = f.page.getByTestId('region-next-steps');
      await region.getByText(ACTIONS.note, { exact: true }).waitFor();
      await region.getByRole('button', { name: 'Propose an action for review', exact: true }).click();
      const form = f.page.getByRole('form', { name: 'Propose an action for review' });
      assert.deepEqual(await form.getByLabel('Action', { exact: true }).locator('option').allInnerTexts(), ['Choose an action', 'Approve CAPA · approved by QA', 'Change recipe parameter · approved by QA and MSAT', 'Close deviation · approved by QA',
        'Place hold · approved by a supervisor', 'Release batch · approved by QA and a QA reviewer', 'Request retest · approved by a supervisor']);
      await form.getByLabel('Action', { exact: true }).selectOption('close_deviation'); await form.getByLabel('What it applies to', { exact: true }).fill('DEV-77');
      await form.getByLabel('Why', { exact: true }).fill('Glucose in B-204 tracks B-201 with a steady offset.'); await form.getByLabel('Expected result', { exact: true }).fill('Deviation closed with no product impact.');
      await form.getByLabel('How you will check it worked', { exact: false }).fill('Next three batches stay within 1 g/L.'); nothingSaved(f);
      await form.getByRole('button', { name: 'Propose for review', exact: true }).click();
      const sent = region.getByTestId('proposal-sent'); await sent.getByText('Waiting for approval from QA. Nothing has been carried out.', { exact: true }).waitFor(); await sent.getByText('The result it rests on has open checks', { exact: false }).waitFor();
      const proposed = f.posts.find(p => p.path.endsWith('/propose'));
      assert.equal(proposed.path, '/v1/workspace-tasks/results/work-compare-1/propose', 'The proposal rests on the saved comparison');
      assert.deepEqual(proposed.body, { operation: 'close_deviation', target_id: 'DEV-77', rationale: 'Glucose in B-204 tracks B-201 with a steady offset.', expected_result: 'Deviation closed with no product impact.', follow_up_measure: 'Next three batches stay within 1 g/L.' });
      const step = f.posts.find(p => /\/steps$/.test(p.path)).body; assert.equal(step.kind, 'action'); assert.match(step.proposal_id, /^prop-/); assert.equal(step.result_id, 'work-compare-1');
      const shown = steps(f).filter({ hasText: 'Close deviation: DEV-77' }); await shown.getByTestId('step-stands').getByText('Waiting for approval', { exact: true }).waitFor();
      await shown.getByText('Proposal: Close deviation · DEV-77 · approval by QA', { exact: true }).waitFor();
      assert.equal(await shown.getByRole('button', { name: 'Mark done' }).count(), 0, 'A proposal waiting for approval cannot be ticked off as done');
      await f.page.getByTestId('plan-status').getByText('1 step to do · 1 waiting for approval', { exact: true }).waitFor();
      // Approval happens elsewhere. The step then reports it as the backend does, and is still not done.
      f.proposals.get(step.proposal_id).status = 'approved'; await f.page.reload(); await f.ready();
      await steps(f).filter({ hasText: 'Close deviation: DEV-77' }).getByTestId('step-stands').getByText('Approved, not yet carried out', { exact: true }).waitFor();
      assert.equal(await steps(f).getByRole('button', { name: 'Mark done' }).count(), 0); f.verify();
    } finally { await f.context.close(); }
  },
  async step_done(browser) {
    const f = await fixture(browser);
    try {
      await f.ready(); const add = f.page.getByRole('form', { name: 'Add a step' });
      assert.deepEqual(await add.getByLabel('Kind of step').locator('option').allInnerTexts(), ['Check', 'Request', 'Action', 'Note']);
      await add.getByLabel('Step', { exact: true }).fill('Compare viable cell density for the same batches'); await add.getByRole('button', { name: 'Add', exact: true }).click();
      const step = steps(f).filter({ hasText: 'Compare viable cell density' }); await step.getByTestId('step-stands').getByText('To do', { exact: true }).waitFor();
      assert.deepEqual(f.posts.find(p => /\/steps$/.test(p.path)).body, { expected_revision: 1, kind: 'check', text: 'Compare viable cell density for the same batches' });
      assert.equal(f.posted('/batch_picture/run').length, 0, 'A step typed by hand cites no result, so none is saved');
      await step.getByRole('button', { name: 'Edit step' }).click(); await step.getByLabel('Step text').fill('Compare viable cell density for B-201 and B-204'); await step.getByRole('button', { name: 'Save', exact: true }).click();
      await steps(f).filter({ hasText: 'Compare viable cell density for B-201 and B-204' }).waitFor();
      const current = steps(f).filter({ hasText: 'B-201 and B-204' }); await current.getByRole('button', { name: 'Mark done' }).click();
      await current.getByLabel('Outcome').fill('Density matches within 3 %; not the cause.'); await current.getByRole('button', { name: 'Save as done', exact: true }).click();
      await f.page.getByRole('list', { name: 'Steps done' }).getByText('Density matches within 3 %; not the cause.', { exact: false }).waitFor();
      const done = f.posts.filter(p => /\/steps\/step-\d+$/.test(p.path)).at(-1).body; assert.deepEqual(done, { expected_revision: 3, status: 'done', outcome: 'Density matches within 3 %; not the cause.' });
      await f.page.getByTestId('plan-status').getByText('No steps to do · 1 done', { exact: true }).waitFor();
      await add.getByLabel('Kind of step').selectOption('note'); await add.getByLabel('Step', { exact: true }).fill('Ask whether BR-07 was requalified'); await add.getByRole('button', { name: 'Add', exact: true }).click();
      await steps(f).filter({ hasText: 'BR-07 was requalified' }).getByRole('button', { name: 'Drop step' }).click();
      await f.page.getByText('Dropped · 1', { exact: true }).waitFor(); assert.equal(f.posts.at(-1).body.status, 'dropped');
      // Rename, then come back: the work, its steps and its selection are restored.
      await f.page.getByRole('button', { name: /Rename$/ }).click(); await f.page.getByLabel('Name of this work').fill('Glucose offset in B-204'); await f.page.keyboard.press('Enter');
      await f.page.getByRole('heading', { level: 1 }).getByText('Glucose offset in B-204', { exact: true }).waitFor(); assert.equal(f.posted('/update').filter(p => p.body.title === 'Glucose offset in B-204').length, 1, 'One rename is one write');
      await f.page.reload(); await f.ready(); await f.page.getByRole('heading', { level: 1 }).getByText('Glucose offset in B-204', { exact: true }).waitFor();
      await f.page.getByRole('list', { name: 'Steps done' }).getByText('Density matches within 3 %; not the cause.', { exact: false }).waitFor(); assert.equal(f.posts.filter(p => p.path === '/v1/work-plans').length, 1, 'Returning reopens the saved work'); f.verify();
    } finally { await f.context.close(); }
  },
  async changed_elsewhere(browser) {
    const f = await fixture(browser);
    try {
      await f.ready(); const add = f.page.getByRole('form', { name: 'Add a step' });
      await add.getByLabel('Step', { exact: true }).fill('First step'); await add.getByRole('button', { name: 'Add', exact: true }).click(); await steps(f).filter({ hasText: 'First step' }).waitFor();
      f.touch([...f.plans.keys()][0]);
      await add.getByLabel('Step', { exact: true }).fill('Second step'); await add.getByRole('button', { name: 'Add', exact: true }).click();
      await f.page.getByTestId('workbench-notice').getByText('This work was changed somewhere else, so it has been reloaded', { exact: false }).waitFor();
      await steps(f).filter({ hasText: 'Added from another window' }).waitFor(); assert.equal(await steps(f).filter({ hasText: 'Second step' }).count(), 0, 'A refused change is not shown as saved');
      await add.getByRole('alert').filter({ hasText: 'Make the change again' }).waitFor(); assert.equal(await add.getByLabel('Step', { exact: true }).inputValue(), 'Second step', 'The text of a refused step is kept for another try');
      await add.getByRole('button', { name: 'Add', exact: true }).click(); await steps(f).filter({ hasText: 'Second step' }).waitFor();
      assert.equal(f.posts.filter(p => /\/steps$/.test(p.path)).at(-1).body.expected_revision, 3, 'The retry uses the reloaded revision');
      await f.page.getByTestId('workbench-notice').getByRole('button', { name: 'Dismiss' }).click(); assert.equal(await f.page.getByTestId('workbench-notice').count(), 0); f.verify();
    } finally { await f.context.close(); }
  },
  async explain_withheld(browser) {
    const f = await fixture(browser, { explanation: WITHHELD });
    try {
      await f.ready(); const tool = f.page.getByRole('region', { name: 'Explain this picture', exact: true }); nothingSaved(f);
      await tool.getByRole('button', { name: 'Explain this picture', exact: true }).click();
      const card = tool.getByTestId('explanation-withheld'); await card.getByText('No explanation is available right now', { exact: true }).waitFor();
      await card.getByText('Reason: no qualified, available model for comparison_explanation', { exact: true }).waitFor(); await card.getByText(WITHHELD.next_step, { exact: true }).waitFor();
      assert.equal(f.posts.find(p => p.path.endsWith('/explain')).path, '/v1/workspace-tasks/results/work-compare-1/explain'); assert.equal(await tool.getByTestId('explanation').count(), 0);
      await card.getByRole('button', { name: 'Continue in the assistant', exact: true }).click();
      const companion = f.page.getByTestId('work-companion'); await companion.getByTestId('selected-context').getByText(/Workbench · glucose · all batches/).waitFor();
      await companion.getByText('Inspect selection', { exact: true }).click(); await companion.getByText(/Review saved workspace task work-compare-1 \(compare\) at site NF1\./).waitFor();
      assert.equal(f.posts.filter(p => /\/messages$/.test(p.path)).length, 0, 'Handing over prepares the assistant; it sends nothing'); f.verify();
    } finally { await f.context.close(); }
  },
  async explain(browser) {
    const f = await fixture(browser);
    try {
      await f.ready(); const tool = f.page.getByRole('region', { name: 'Explain this picture', exact: true });
      await tool.getByRole('button', { name: 'Explain this picture', exact: true }).click();
      const card = tool.getByTestId('explanation'); await card.getByText(EXPLAINED.explanation, { exact: true }).waitFor();
      for (const text of ['What the figures show', 'Possible explanations · not established', 'What this cannot tell', 'Written by a model · review before relying on it']) await card.getByText(text, { exact: true }).waitFor();
      await card.getByText(/Every number in this explanation appears in the calculated result\..*Model fixture-model · 3\.1 s/).waitFor();
      await card.getByRole('button', { name: 'Add to next steps', exact: true }).click(); await steps(f).filter({ hasText: 'Compare the media preparation records for BR-01 and BR-07.' }).waitFor();
      const step = f.posts.find(p => /\/steps$/.test(p.path)).body; assert.equal(step.basis, EXPLAINED.hypotheses[0].statement); assert.equal(step.result_id, 'work-compare-1');
      await f.page.getByLabel('Parameter', { exact: true }).selectOption('pH'); await tool.getByText('The selection has changed since this was written. It describes the earlier picture.', { exact: true }).waitFor(); f.verify();
    } finally { await f.context.close(); }
  },
  async trace_and_causes(browser) {
    const f = await fixture(browser);
    try {
      await f.ready(); const trace = f.page.getByRole('region', { name: 'Trace a lot or equipment', exact: true });
      await trace.getByLabel('Lot or equipment number').fill('LOT-7781'); await trace.getByRole('button', { name: 'Trace', exact: true }).click();
      const found = trace.getByTestId('trace-result'); await found.getByText('Recorded as used · 1 batch', { exact: true }).waitFor(); await found.getByText('Only mentioned · 1 record', { exact: true }).waitFor();
      await found.getByText('B-204', { exact: true }).waitFor(); await found.getByText('Deviation NC-9 mentions the feed lot', { exact: false }).waitFor(); await found.getByText(/1 batches at this site have no recorded steps/).waitFor();
      const sent = f.posts.find(p => p.path === '/v1/workspace-tasks/run').body; assert.equal(sent.operation, 'trace_impact'); assert.equal(sent.record_id, 'LOT-7781'); assert.equal(sent.site_id, SITE);
      await found.getByRole('button', { name: 'Add affected batches to next steps', exact: true }).click(); await steps(f).filter({ hasText: 'Assess whether B-204 is affected by LOT-7781.' }).waitFor();
      assert.equal(f.posts.find(p => /\/steps$/.test(p.path)).body.result_id, 'work-trace-1');
      const causes = f.page.getByRole('region', { name: 'Suggest causes to check', exact: true });
      await causes.getByLabel('Signal, case or batch number').fill('B-204'); await causes.getByRole('button', { name: 'Suggest', exact: true }).click();
      await causes.getByText('Hypotheses to check. No cause is established.', { exact: true }).waitFor();
      await causes.getByRole('button', { name: 'Add to next steps', exact: true }).click(); await steps(f).filter({ hasText: 'Confirm the usage window of feed lot LOT-7781.' }).getByText('Prompted by: Feed lot LOT-7781 may have contributed.', { exact: true }).waitFor();
      const step = f.posts.filter(p => /\/steps$/.test(p.path)).at(-1).body; assert.equal(step.text, 'Confirm the usage window of feed lot LOT-7781.'); assert.equal(step.result_id, 'work-causes-1'); f.verify();
    } finally { await f.context.close(); }
  },
  async saved_work(browser) {
    const f = await fixture(browser, { remembered: 'plan-old', plans: [{ id: 'plan-old', title: 'pH drift in B-204', selection: { dataset_ids: ['ds-oct'], parameter: 'pH', batches: ['B-201', 'B-204'], site_id: SITE, time_from_h: 0, time_to_h: 48 }, steps: [{ kind: 'check', text: 'Review the probe calibration', basis: 'B-204 is lower from 24 h' }] },
      { id: 'plan-two', title: 'September glucose', selection: { dataset_ids: ['ds-sep'], parameter: 'glucose', batches: [], site_id: SITE }, steps: [] }] });
    try {
      await f.page.getByRole('heading', { level: 1 }).getByText('pH drift in B-204', { exact: true }).waitFor(); await f.ready();
      assert.deepEqual((await f.until('/batch_picture/preview')).selection, { ...FIRST, parameter: 'pH', batches: ['B-201', 'B-204'], time_from_h: 0, time_to_h: 48 }, 'Opening saved work restores its selection');
      assert.equal(f.posted('/batch_picture/preview').filter(p => p.body.selection.parameter === 'glucose').length, 0, 'The default picture is not requested when saved work is reopened');
      await steps(f).filter({ hasText: 'Review the probe calibration' }).getByText('Prompted by: B-204 is lower from 24 h', { exact: true }).waitFor();
      await f.page.waitForTimeout(1200); assert.equal(f.posted('/update').length, 0, 'Opening work does not write to it');
      await f.page.getByRole('button', { name: 'My work', exact: true }).click(); const menu = f.page.getByRole('menu', { name: 'My work' });
      await menu.getByRole('menuitem').filter({ hasText: 'pH drift in B-204' }).getByText(/1 step to do · updated/).waitFor();
      await menu.getByRole('menuitem').filter({ hasText: 'September glucose' }).click();
      await f.page.getByRole('heading', { level: 1 }).getByText('September glucose', { exact: true }).waitFor(); await f.page.locator('[data-point="B-190@24"]').waitFor();
      assert(await f.page.getByRole('checkbox', { name: 'Use delivery September runs', exact: true }).isChecked());
      await f.page.getByRole('group', { name: 'Batches', exact: true }).getByRole('button', { name: 'B-190', exact: true }).click();
      const update = f.posts.find(p => p.path === '/v1/work-plans/plan-two/update') ?? { body: await f.until('/v1/work-plans/plan-two/update') };
      assert.deepEqual(update.body, { expected_revision: 3, selection: { ...FIRST, dataset_ids: ['ds-sep'], batches: ['B-190'] } }, 'Changing the selection of saved work updates it');
      await f.page.getByRole('button', { name: 'My work', exact: true }).click(); await f.page.getByRole('menu', { name: 'My work' }).getByRole('menuitem', { name: 'New' }).click();
      await f.page.getByTestId('plan-status').getByText(/^Not saved yet\./).waitFor(); assert.equal(await steps(f).count(), 0); assert.equal(f.posts.filter(p => p.path === '/v1/work-plans').length, 0); f.verify();
    } finally { await f.context.close(); }
  },
  async from_trends(browser) {
    const f = await fixture(browser, { start: '/trends/' });
    try {
      const link = f.page.getByRole('link', { name: 'Open in workbench', exact: true }); await link.waitFor();
      assert.equal(await link.getAttribute('href'), '/workbench/?parameter=glucose&datasets=run-oct&batches=B-204', 'Trends hands over its parameter, deliveries and highlighted batch');
      await f.page.getByRole('button', { name: 'Compare selected', exact: true }).waitFor();
      await link.click(); await f.page.locator('[data-point="B-204@0"]').waitFor();
      assert.deepEqual((await f.until('/batch_picture/preview')).selection, { ...FIRST, batches: ['B-204'] }, 'The workbench opens on what Trends showed');
      assert.equal(f.posts.filter(p => p.path === '/v1/cmo-datasets').length, 0, 'Opening the workbench publishes nothing'); nothingSaved(f); f.verify();
    } finally { await f.context.close(); }
  },
  async link_names_unknown(browser) {
    const f = await fixture(browser, { start: '/workbench/?parameter=titer&datasets=run-missing' });
    try {
      await f.ready(); await f.page.getByTestId('region-data').getByRole('status').filter({ hasText: '1 delivery named in the link is not available here yet.' }).getByText('titer is not recorded in this delivery; glucose is shown.', { exact: false }).waitFor();
      assert.deepEqual((await f.until('/batch_picture/preview')).selection, FIRST); f.verify();
    } finally { await f.context.close(); }
  },
  async timing_and_requirements(browser) {
    const f = await fixture(browser, { slow: true, noSpecs: true });
    try {
      await f.ready(); const timing = f.page.getByTestId('picture-timing'); await timing.getByText('Took 14 s · over the 10 s target', { exact: true }).waitFor();
      assert.equal(await timing.evaluate(node => getComputedStyle(node).color), 'rgb(217, 119, 6)', 'A slow answer is shown in the warning colour');
      await f.page.getByTestId('no-requirements').getByText('No requirements are approved for this site yet, so gaps cannot be judged.', { exact: false }).waitFor();
      assert.equal(await f.page.getByTestId('finding-missing').count(), 0); assert.equal(await f.page.getByTestId('no-gaps').count(), 0); f.verify();
    } finally { await f.context.close(); }
  },
  async no_gaps(browser) {
    const f = await fixture(browser, { deliveries: DELIVERIES.filter(d => d.id === 'ds-sep'), noGaps: true });
    try {
      await f.page.locator('[data-point="B-190@24"]').waitFor();
      await f.page.getByTestId('no-gaps').getByText('No gaps against approved requirements for this selection (2 requirements checked).', { exact: true }).waitFor();
      assert.equal(await f.page.getByTestId('finding-missing').count() + await f.page.getByTestId('finding-conflict').count() + await f.page.getByTestId('finding-context').count(), 0, 'Nothing to report is one line, not empty cards');
      f.verify();
    } finally { await f.context.close(); }
  },
  async errors(browser) {
    const f = await fixture(browser, { failDeliveries: 2, failPreview: 1 });
    try {
      const data = f.page.getByTestId('region-data'); await data.getByRole('alert').filter({ hasText: 'The deliveries for this site could not be read. The evidence store is not reachable' }).waitFor();
      await f.page.getByTestId('region-picture').getByText('Available once the deliveries above can be read.', { exact: true }).waitFor(); await f.page.getByTestId('region-findings').getByText('Available once the deliveries above can be read.', { exact: true }).waitFor();
      await f.page.getByRole('form', { name: 'Add a step' }).waitFor();
      await data.getByRole('button', { name: 'Try again' }).click(); await data.getByRole('button', { name: 'Try again' }).click().catch(() => undefined);
      const picture = f.page.getByTestId('region-picture'); await picture.getByRole('alert').filter({ hasText: 'The picture could not be calculated. The selected delivery was superseded; publish the current delivery again' }).waitFor();
      await f.page.getByTestId('region-findings').getByText('Findings appear once the picture can be calculated.', { exact: true }).waitFor();
      assert(await f.page.getByRole('button', { name: 'Propose an action for review', exact: true }).isDisabled(), 'A proposal needs a calculated result to rest on');
      await picture.getByRole('button', { name: 'Try again' }).click(); await f.ready(); assert.equal(await picture.getByRole('alert').count(), 0); f.verify();
    } finally { await f.context.close(); }
  },
  async no_deliveries(browser) {
    const f = await fixture(browser, { deliveries: [] });
    try {
      const empty = f.page.getByTestId('no-deliveries'); await empty.getByText('No deliveries to work with yet', { exact: true }).waitFor();
      assert.equal(await empty.getByRole('link', { name: 'Go to deliveries' }).getAttribute('href'), '/cmo/');
      await f.page.getByTestId('region-picture').getByText('Appears here once a delivery is in view.', { exact: true }).waitFor(); await f.page.getByTestId('region-findings').getByText('Appears here once a delivery is in view.', { exact: true }).waitFor();
      await f.page.getByTestId('region-next-steps').getByText('Nothing planned yet.', { exact: false }).waitFor();
      assert(await f.page.getByRole('button', { name: 'Explain this picture', exact: true }).isDisabled());
      await f.page.waitForTimeout(500); assert.equal(f.posted('/batch_picture/preview').length, 0, 'Nothing is calculated without a delivery'); f.verify();
    } finally { await f.context.close(); }
  },
  async mobile(browser) {
    const f = await fixture(browser, { viewport: { width: 390, height: 844 }, remembered: 'plan-old', plans: [{ id: 'plan-old', title: 'Glucose offset in B-204', selection: FIRST, steps: [{ kind: 'check', text: 'Compare the media preparation records for BR-01 and BR-07', basis: 'The batches differ in equipment.' }] }] });
    try {
      await f.ready(); await f.page.getByTestId('comparison-cards').getByText('B-204 minus B-201', { exact: true }).waitFor(); assert(!(await f.page.getByTestId('comparison-table').isVisible()), 'A phone shows each pair as a short list, not a wide table'); await aim(f, 'B-201@24'); await f.page.getByTestId('source-panel').getByText('row 4, column glucose', { exact: true }).waitFor();
      const overflow = await f.page.evaluate(() => { const main = document.getElementById('main'); return { page: document.documentElement.scrollWidth - window.innerWidth, main: main.scrollWidth - main.clientWidth,
        wide: [...main.querySelectorAll('[data-testid="workbench"] *')].filter(node => node.getBoundingClientRect().right > window.innerWidth + 1 && !node.closest('.overflow-x-auto, .overflow-auto')).map(node => node.tagName + '.' + node.className).slice(0, 5) }; });
      assert.deepEqual(overflow, { page: 0, main: 0, wide: [] }, 'At 390 px nothing scrolls the page sideways');
      const order = await f.page.evaluate(() => ['data', 'picture', 'findings', 'next-steps'].map(id => Math.round(document.getElementById(id).getBoundingClientRect().left)));
      assert.equal(new Set(order).size, 1, 'The four regions stack in one column'); await f.shot('workbench-mobile.png'); f.verify();
    } finally { await f.context.close(); }
  },
  async desktop(browser) {
    const f = await fixture(browser);
    try {
      await f.ready(); const add = f.page.getByRole('form', { name: 'Add a step' });
      await f.page.getByRole('group', { name: 'Batches', exact: true }).getByRole('button', { name: 'B-201', exact: true }).click(); await f.page.getByRole('group', { name: 'Batches', exact: true }).getByRole('button', { name: 'B-204', exact: true }).click();
      await f.until('/batch_picture/preview', b => b.selection.batches.length === 2); await f.page.waitForTimeout(300);
      await f.page.getByTestId('finding-context').getByRole('button', { name: 'Add a check to next steps', exact: true }).click(); await steps(f).first().waitFor();
      await f.page.getByTestId('finding-missing').getByRole('button', { name: 'Ask for this evidence', exact: true }).click(); await f.page.getByRole('form', { name: 'Ask for this evidence' }).locator('select[aria-label="Who to ask"]').selectOption('m.okafor');
      await f.page.getByRole('form', { name: 'Ask for this evidence' }).getByRole('button', { name: 'Send request', exact: true }).click(); await steps(f).nth(1).waitFor();
      await f.page.getByRole('button', { name: 'Propose an action for review', exact: true }).click(); const form = f.page.getByRole('form', { name: 'Propose an action for review' });
      await form.getByLabel('Action', { exact: true }).selectOption('request_retest'); await form.getByLabel('What it applies to', { exact: true }).fill('B-204'); await form.getByLabel('Why', { exact: true }).fill('Two glucose values are recorded for B-204 at 24 h.');
      await form.getByLabel('Expected result', { exact: true }).fill('One confirmed value at 24 h.'); await form.getByRole('button', { name: 'Propose for review', exact: true }).click(); await steps(f).nth(2).waitFor();
      await add.getByLabel('Step', { exact: true }).fill('Compare viable cell density for B-201 and B-204'); await add.getByRole('button', { name: 'Add', exact: true }).click(); await steps(f).nth(3).waitFor();
      const last = steps(f).filter({ hasText: 'viable cell density' }); await last.getByRole('button', { name: 'Mark done' }).click(); await last.getByLabel('Outcome').fill('Density matches within 3 %.'); await last.getByRole('button', { name: 'Save as done', exact: true }).click();
      await f.page.getByRole('list', { name: 'Steps done' }).waitFor(); await aim(f, 'B-201@36'); await f.page.getByTestId('source-panel').getByText('row 5, column glucose', { exact: true }).waitFor();
      await f.page.getByTestId('plan-status').getByText('3 steps to do · 1 waiting for approval · 1 waiting for a reply · 1 done', { exact: true }).waitFor();
      const overflow = await f.page.evaluate(() => { const main = document.getElementById('main'); return main.scrollWidth - main.clientWidth; }); assert.equal(overflow, 0);
      await f.page.mouse.move(5, 5); await f.shot('workbench-desktop.png'); f.verify();
    } finally { await f.context.close(); }
  },
};
async function main() {
  const browser = await chromium.launch({ headless: true });
  const only = process.argv.slice(2).find(arg => !arg.startsWith('--'));
  let failed = 0;
  try { for (const [name, run] of Object.entries(scenarios)) { if (only && name !== only) continue;
    try { await run(browser); console.log(`PASS ${name}`); } catch (error) { failed++; console.log(`FAIL ${name}`); console.error(error); } } }
  finally { await browser.close(); }
  console.log(failed ? `${failed} scenario(s) failed` : 'All workbench scenarios passed'); if (failed) process.exitCode = 1;
}
main().catch(error => { console.error(error); process.exitCode = 1; });
