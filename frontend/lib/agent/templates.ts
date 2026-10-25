// Synthetic agent task plans for the five prototype journeys (MOS-AGENT-DELTA §4).
// Every output carries a claim type and citations from the shared CITATIONS registry.
import { ANOMALY_HOUR } from '@/fixtures/biomanufacturingData';
import { feedRateSeries } from '@/fixtures/timeseries';
import type { Answers, ScopeChip, TaskTemplate } from './types';

const sigmoid = (x: number) => 1 / (1 + Math.exp(-x));
const seriesIn = (id: string, [a, b]: [number, number]) =>
  feedRateSeries.find((s) => s.id === id)!.dataPoints.filter((p) => p.elapsedHours >= a && p.elapsedHours <= b && !p.imputed).map((p) => [p.elapsedHours, p.value] as [number, number]);

const FEED_WINDOW: [number, number] = [240, 280];
const observed73 = seriesIn('MES-26073', FEED_WINDOW);
const reference71 = seriesIn('MES-26071', FEED_WINDOW);
// Modelled delivery if a mass-balance setpoint trim recovered 90% of the post-spike droop.
const compensated73 = observed73.map(([h, v]) => [h, +(v + 0.9 * 2.4 * sigmoid((h - ANOMALY_HOUR) * 1.4)).toFixed(3)] as [number, number]);

const MESA_FACILITY: ScopeChip = { id: 'fac-mesa', kind: 'FACILITY', value: 'Mesa Site · Cleanroom Suite 3B · Skid BR-UP-01' };
const CAMPAIGN_3: ScopeChip = { id: 'batches-3', kind: 'BATCHES', value: 'CMP-26-10 · MES-26071, MES-26072, MES-26073' };

export const TEMPLATES: TaskTemplate[] = [
  /* ----------------------------------------------------------- Journey 1 */
  {
    id: 'feed-cmms',
    taskId: 'TASK-2026-1042',
    title: 'Late-phase feed rate attenuation',
    agent: 'MSAT Yield Sentry',
    originFrame: 'ANALYSIS-01',
    summary: 'Correlate the MES-26073 feed droop with recent CMMS maintenance and PM-204 pump telemetry.',
    keywords: ['feed', 'droop', 'cmms', 'pump', 'maintenance', 'correlate', 'attenuation', 'wo-8819', 'pressure'],
    defaultScope: [
      MESA_FACILITY,
      { id: 'batch-73', kind: 'BATCHES', value: 'CMP-26-10 · MES-26073 (vs MES-26071, MES-26072)' },
      { id: 'span-260', kind: 'SPAN', value: 'T+260.0h – T+272.0h (12.0h window · feed droop)' },
      { id: 'rec-hist', kind: 'RECORD', value: 'Historian_UP01_Oct.csv §4.2' },
      { id: 'rec-wo', kind: 'RECORD', value: 'CMMS WO-8819' },
    ],
    sources: ['OSIsoft PI', 'DeltaV eBR', 'Maximo CMMS', 'LabWare LIMS'],
    checkpoints: [
      {
        id: 'q', short: 'Query historian & eBR', title: 'Query DeltaV eBR and historian continuous logs', tool: 'connector-hub v2.3.1 (PI Web API, DeltaV eBR export)', durationSec: 4, resolvesSource: 'OSIsoft PI',
        outputs: [
          { text: '24,190 telemetry points across 7 tags for 3 batches (read-only service account).', kind: 'observation', citations: ['historian-up01'] },
          { text: '3 eBR phase records; inoculation timestamps used as T+0.', kind: 'observation', citations: ['ebr-mes-26073'] },
        ],
      },
      {
        id: 'gap', short: 'Impute historian gap', title: 'Impute 42-minute historian gap at T+182h', tool: 'align-ts v1.8.0 · kalman-rts v0.9.2', durationSec: 4, resolvesSource: 'DeltaV eBR',
        outputs: [
          { text: '42 points at T+182.0–182.7h filled with a Kalman (RTS) estimate and flagged imputed.', kind: 'imputed', citations: ['historian-gap'] },
          { text: 'Imputed points are excluded from every statistic below.', kind: 'calculated' },
        ],
      },
      {
        id: 'cmms', short: 'CMMS cross-ref', title: 'Cross-reference Maximo CMMS work order WO-8819', tool: 'cmms-correlate v1.2.4', durationSec: 6, resolvesSource: 'Maximo CMMS',
        outputs: [
          { text: 'WO-8819 raised PM-204 clamp torque 0.42 → 0.55 N·m about 48 h before the T+264.4h spike; no dynamic slip check recorded.', kind: 'observation', citations: ['cmms-wo-8819'] },
          { text: 'SOP-UP-014 §7.2 requires a slip verification after any occlusion adjustment.', kind: 'observation', citations: ['sop-up-014'] },
        ],
      },
      {
        id: 'hyp', short: 'Evaluate hypotheses', title: 'Evaluate 3 competing hypotheses', tool: 'hypothesis-eval v0.6.0 (OLS + evidence ledger)', durationSec: 6, resolvesSource: 'LabWare LIMS',
        outputs: [
          { text: 'Feed loss vs head pressure: R² = 0.941 across 3 batches (n = 237 hourly points). Correlation, not causal proof.', kind: 'calculated', citations: ['b-calc-feed-pressure'] },
          { text: 'Tubing slip after WO-8819 remains the leading explanation; not yet tested.', kind: 'hypothesis', citations: ['oem-masterflex'] },
          { text: 'Media lot FM-2207 and DO probe drift are contradicted by CoA and redundant-probe data.', kind: 'contradicted', citations: ['lims-media-lot', 'pi-do-probe'] },
        ],
      },
      {
        id: 'out', short: 'Draft outputs', title: 'Draft compensation curve and hypothesis matrix', tool: 'artifact-builder v1.0.0', durationSec: 4,
        outputs: [
          { text: 'Modelled compensation curve and hypothesis matrix ready for your review. Nothing has been inserted or shared yet.', kind: 'recommendation' },
          { text: 'MES-26072 declined 2.8 pts without a pressure event — not explained by this analysis.', kind: 'unknown', citations: ['historian-up01'] },
        ],
      },
    ],
    artifacts: [
      {
        id: 'matrix', title: 'Hypothesis evaluation matrix', kind: 'calculated', availableAfter: 4, insertTarget: 'ANALYSIS-01',
        summary: '3 explanations scored against the evidence ledger. Fit statistics are not probabilities of being correct.',
        build: () => ({
          type: 'HYPOTHESIS_MATRIX',
          note: 'Statistics describe fit to the observed data only. A hypothesis is not established until the TP-01 slip test is run.',
          rows: [
            { hypothesis: 'Tubing fatigue / slip on PM-204 after WO-8819', statistic: 'R² = 0.941 (feed loss vs head pressure)', for: 'Torque raised 48 h before spike; tubing at 412 h of 400–500 h life', against: 'Does not explain MES-26072 decline', kind: 'hypothesis', citations: ['b-calc-feed-pressure', 'cmms-wo-8819', 'oem-masterflex'] },
            { hypothesis: 'Feed media lot FM-2207 variation', statistic: 'CoA within spec on all attributes', for: '—', against: 'Same lot fed MES-26072 with no T+264h drop', kind: 'contradicted', citations: ['lims-media-lot', 'b-ebr-media-26072'] },
            { hypothesis: 'Dissolved-oxygen probe drift', statistic: 'DO_A vs DO_B agree within 0.6%', for: '—', against: 'DO inside 35–45% band on all batches', kind: 'contradicted', citations: ['pi-do-probe'] },
          ],
        }),
      },
      {
        id: 'curve', title: 'Synthetic feed compensation curve', kind: 'hypothesis', availableAfter: 5, insertTarget: 'ANALYSIS-01',
        summary: 'Observed MES-26073 delivery vs a modelled mass-balance setpoint trim, with MES-26071 as reference.',
        build: () => ({
          type: 'CHART_DIFF', xLabel: 'Elapsed batch time (h)', unit: 'mL/min', window: FEED_WINDOW,
          observed: observed73, reference: reference71, compensated: compensated73,
          note: 'The compensated line is a model output (90% droop recovery assumed), not an observed value and not a validated control change.',
          citations: ['ag-calc-compensation', 'historian-up01'],
        }),
      },
    ],
    runTraceHref: '/runs/RUN-2026-1042',
  },

  /* ----------------------------------------------------------- Journey 2 */
  {
    id: 'tt-gap',
    taskId: 'TASK-2026-1051',
    title: 'TT-006 feed-loop parameter gap resolution',
    agent: 'Tech Transfer Mapper',
    originFrame: 'TRANSFER-02',
    summary: 'Map Mesa 500L recipe parameters onto Durham 2000L and resolve the unmapped feed-loop PID constants.',
    keywords: ['transfer', 'durham', 'pid', 'gap', 'scale', 'parameter', 'geometry', 'tt-006', 'recipe', 'map'],
    defaultScope: [
      { id: 'proj-tt', kind: 'PROJECT', value: 'TT-006 · Gate 2 (Engineering & CPP dossier)' },
      { id: 'fac-pair', kind: 'FACILITY', value: 'Mesa 500L single-use → Durham 2000L stainless' },
      { id: 'rec-recipe', kind: 'RECORD', value: 'Recipe AB-mAb-014 UP-01 v4' },
      { id: 'rec-gate', kind: 'RECORD', value: 'Gate 2 checklist item 2.7' },
    ],
    sources: ['DeltaV eBR', 'Documentum', 'Veeva Vault QMS'],
    checkpoints: [
      {
        id: 'donor', short: 'Read donor recipe', title: 'Read donor recipe and equipment specification', tool: 'connector-hub v2.3.1 (DeltaV recipe export, Documentum)', durationSec: 3, resolvesSource: 'DeltaV eBR',
        outputs: [
          { text: '86 recipe parameters extracted from UP-01 v4 for the production phases.', kind: 'observation', citations: ['b-ebr-recipe-v4'] },
          { text: 'Mesa feed uses a gravimetric cascade: outer weight loop Kc = 1.85, Ti = 240 s over an inner flow loop (Kc 0.62, Ti 18 s).', kind: 'observation', citations: ['c-mesa-sub-spec', 'ag-mesa-feed-loop'] },
        ],
      },
      {
        id: 'recipient', short: 'Read recipient spec', title: 'Read recipient equipment specification', tool: 'connector-hub v2.3.1 (Documentum)', durationSec: 3, resolvesSource: 'Documentum',
        outputs: [
          { text: 'Durham FIC-2201 runs flow-only control (DeltaV v13); no gravimetric outer loop configured.', kind: 'observation', citations: ['c-durham-ss-spec', 'c-tt-006-gate2'] },
          { text: 'Recipient spec is Rev 1 (2023) and may be stale.', kind: 'unknown', citations: ['c-durham-ss-spec'] },
        ],
      },
      {
        id: 'map', short: 'Map parameters', title: 'Map 86 parameters across sites', tool: 'param-mapper v0.9.1 (geometric + volumetric scaling rules)', durationSec: 4, resolvesSource: 'Veeva Vault QMS',
        outputs: [
          { text: '79 mapped directly, 4 scaled by volume (1:4.00), 3 unmapped — all three in the feed control loop.', kind: 'calculated', citations: ['ag-param-map', 'b-tt006-gate2'] },
        ],
      },
      {
        id: 'derive', short: 'Derive tuning', title: 'Derive candidate feed-loop tuning for Durham', tool: 'loop-tuning-calc v0.4.2 (IMC rules)', durationSec: 4,
        outputs: (a: Answers) => a['loop-map'] === 'direct'
          ? [
              { text: 'Mesa inner flow-loop constants copied to FIC-2201 unchanged (Kc 0.62, Ti 18 s).', kind: 'calculated', citations: ['ag-mesa-feed-loop'] },
              { text: 'Without the gravimetric outer loop, delivered-mass drift is uncorrected — the gap the PM-204 incident exposed.', kind: 'unknown' },
            ]
          : [
              { text: 'Candidate single-loop tuning for FIC-2201 with a mass-balance trim: Kc 0.71, Ti 22 s, trim every 15 min (derived by IMC rules; not tested on Durham hardware).', kind: 'calculated', citations: ['ag-calc-imc', 'c-durham-ss-spec'] },
              { text: 'Requires a loop bump test at Durham before any use.', kind: 'recommendation' },
            ],
      },
      {
        id: 'memo', short: 'Draft memo', title: 'Draft gap assessment memo and recipe patch proposal', tool: 'artifact-builder v1.0.0', durationSec: 3,
        outputs: [{ text: 'Gap memo DOC-UP01-03 v0.3 section and recipe patch proposal drafted. Both need engineering and QA review.', kind: 'recommendation' }],
      },
    ],
    gates: [
      {
        id: 'loop-map', kind: 'INPUT', beforeStep: 3,
        question: 'Durham FIC-2201 is flow-only; Mesa delivers feed through a gravimetric cascade (outer loop Kc = 1.85). How should the feed loop be mapped?',
        context: 'This changes the derived constants and the risk statement in the memo. The agent cannot decide this from the records alone.',
        citations: ['c-tt-006-gate2', 'ag-mesa-feed-loop'],
        options: [
          { label: 'Derive equivalent single-loop tuning with mass-balance trim', value: 'derive', recommended: true, note: 'Compensates for the missing outer loop; needs a bump test.' },
          { label: 'Map Mesa inner-loop constants directly', value: 'direct', note: 'Fastest; leaves delivered-mass drift uncorrected.' },
        ],
      },
    ],
    artifacts: [
      {
        id: 'param-diff', title: 'Feed-loop parameter diff · Mesa → Durham', kind: 'calculated', availableAfter: 4, insertTarget: 'TRANSFER-02',
        summary: 'The 3 unmapped feed-loop parameters with the candidate Durham values.',
        build: (a) => ({
          type: 'TABLE_DIFF', columns: ['Parameter', 'Mesa 500L (donor)', 'Durham FIC-2201 (candidate)'],
          note: a['loop-map'] === 'direct' ? 'Direct mapping selected. Delivered-mass control is lost at Durham.' : 'Derived values follow IMC tuning rules and have not been tested on Durham hardware.',
          rows: a['loop-map'] === 'direct'
            ? [
                { parameter: 'Feed control structure', current: 'Gravimetric cascade', proposed: 'Flow-only', kind: 'observation', citation: 'c-durham-ss-spec' },
                { parameter: 'Flow loop Kc / Ti', current: '0.62 / 18 s', proposed: '0.62 / 18 s', kind: 'calculated', citation: 'ag-mesa-feed-loop' },
                { parameter: 'Outer loop Kc / Ti', current: '1.85 / 240 s', proposed: 'Not available', kind: 'unknown', citation: 'ag-mesa-feed-loop' },
              ]
            : [
                { parameter: 'Feed control structure', current: 'Gravimetric cascade', proposed: 'Flow loop + mass-balance trim', kind: 'recommendation', citation: 'c-tt-006-gate2' },
                { parameter: 'Flow loop Kc / Ti', current: '0.62 / 18 s', proposed: '0.71 / 22 s', kind: 'calculated', citation: 'ag-calc-imc' },
                { parameter: 'Mass-balance trim interval', current: 'Continuous (outer loop 1.85 / 240 s)', proposed: '15 min', kind: 'calculated', citation: 'ag-calc-imc' },
              ],
        }),
      },
      {
        id: 'memo', title: 'Transfer gap assessment · DOC-UP01-03 v0.3 section', kind: 'recommendation', availableAfter: 5, insertTarget: 'DOC-01',
        summary: 'Draft memo section with citations to both sites. Remains a draft until reviewed.',
        build: (a) => ({
          type: 'DOC_DRAFT', docId: 'DOC-UP01-03', version: 'v0.3 (draft)',
          sections: [
            { heading: '4.3 Feed-loop control gap', body: 'The donor process controls feed by delivered mass (gravimetric cascade). The recipient loop FIC-2201 controls volumetric flow only, so pump slip of the kind observed on PM-204 would not be corrected at Durham.', kind: 'observation', citations: ['c-mesa-sub-spec', 'c-durham-ss-spec'] },
            { heading: '4.4 Proposed mapping', body: a['loop-map'] === 'direct' ? 'Inner-loop constants are mapped unchanged. Residual risk: uncorrected delivered-mass drift. Recommend Gate 2 records this as an accepted risk only with QA concurrence.' : 'Candidate flow-loop tuning Kc 0.71 / Ti 22 s with a 15-minute mass-balance trim, derived by IMC rules. To be confirmed by a bump test on BR-D-2000 before Gate 2 review.', kind: 'recommendation', citations: ['ag-calc-imc', 'c-tt-006-gate2'] },
            { heading: '4.5 Open items', body: 'Durham equipment specification is Rev 1 (2023); confirm current DeltaV module configuration with K. Osei (Durham Automation).', kind: 'unknown', citations: ['c-durham-ss-spec'] },
          ],
        }),
      },
      { id: 'gate', title: 'Recipe patch proposal · REV-TT006-07', kind: 'recommendation', availableAfter: 5, summary: 'Engineering sign-off required before handoff to Durham.', build: () => ({ type: 'REVIEW_GATE' }) },
    ],
    review: {
      proposalId: 'REV-TT006-07',
      title: 'Recipe patch: Durham FIC-2201 feed-loop mapping',
      signOffRoles: ['QA_REVIEWER'],
      riskTier: 'High',
      systemOfRecord: 'DeltaV recipe management (Durham)',
      rationale: 'Closes Gate 2 checklist item 2.7 with an explicit mapping for the only unmapped parameters.',
      expectedResult: 'Delivered feed at Durham within ±3% of setpoint across a 280 h batch.',
      constraints: 'Bump test on BR-D-2000 before first use; no change to Mesa recipe.',
      owner: 'K. Osei · Durham Automation',
      changeMind: ['Bump test shows oscillation or >5% delivery error at the candidate tuning.', 'Durham confirms a gravimetric outer loop can be configured on DeltaV v13.'],
      monitor: 'Track FIC-2201 delivered vs setpoint for the first Durham engineering run.',
      diff: (a) => a['loop-map'] === 'direct'
        ? [{ parameter: 'FIC-2201 Kc / Ti', current: 'Unmapped', proposed: '0.62 / 18 s', kind: 'recommendation', citation: 'ag-mesa-feed-loop' }]
        : [
            { parameter: 'FIC-2201 Kc / Ti', current: 'Unmapped', proposed: '0.71 / 22 s', kind: 'recommendation', citation: 'ag-calc-imc' },
            { parameter: 'Mass-balance trim', current: 'None', proposed: 'Every 15 min', kind: 'recommendation', citation: 'c-tt-006-gate2' },
          ],
    },
  },

  /* ----------------------------------------------------------- Journey 3 */
  {
    id: 'dossier',
    taskId: 'TASK-2026-1052',
    title: 'Upstream yield decline investigation dossier',
    agent: 'Investigation Orchestrator',
    originFrame: 'HOME-01',
    summary: 'Assemble process, deviation and laboratory evidence for the MES-26073 yield decline and draft Q-DEV-031 narrative and CAPA.',
    keywords: ['dossier', 'deviation', 'q-dev-031', 'rca', 'capa', 'investigation', 'hplc', 'qc-948', 'yield', 'outlier', 'quality'],
    defaultScope: [
      MESA_FACILITY,
      CAMPAIGN_3,
      { id: 'rec-dev', kind: 'RECORD', value: 'Veeva QMS Q-DEV-031' },
      { id: 'rec-qc', kind: 'RECORD', value: 'LabWare QC-948' },
    ],
    sources: ['OSIsoft PI', 'Maximo CMMS', 'Veeva Vault QMS', 'LabWare LIMS'],
    subtasks: ['A · Process engineering correlation', 'B · Deviation timeline (QMS)', 'C · Laboratory confirmation'],
    checkpoints: [
      {
        id: 'a1', subtask: 'A · Process engineering correlation', short: 'Process correlation', title: 'Correlate feed droop with PM-204 telemetry and maintenance', tool: 'msat-yield-sentry v4 (reuses TASK-2026-1042 results when present)', durationSec: 3, resolvesSource: 'OSIsoft PI',
        outputs: [
          { text: 'Yield index 81.2 → 78.4 → 75.9 across three batches; MES-26073 feed −14.2% after T+264.4h.', kind: 'observation', citations: ['historian-up01'] },
          { text: 'Feed loss vs head pressure R² = 0.941; tubing slip after WO-8819 is the leading hypothesis.', kind: 'hypothesis', citations: ['b-calc-feed-pressure', 'cmms-wo-8819'] },
        ],
      },
      {
        id: 'b1', subtask: 'B · Deviation timeline (QMS)', short: 'QMS timeline', title: 'Extract Q-DEV-031 timeline from Veeva QMS', tool: 'connector-hub v2.3.1 (Veeva Vault read-only)', durationSec: 3, resolvesSource: 'Veeva Vault QMS',
        outputs: [{ text: 'Q-DEV-031 opened as Major Tier 2; root-cause stage; 30-day due date 2026-11-18.', kind: 'observation', citations: ['qms-q-dev-031'] }],
      },
      {
        id: 'c1', subtask: 'C · Laboratory confirmation', short: 'LIMS titer', title: 'Retrieve QC-948 HPLC titer and sign-off status', tool: 'connector-hub v2.3.1 (LabWare REST)', durationSec: 3, resolvesSource: 'LabWare LIMS',
        outputs: [
          { text: 'QC-948 HPLC titer 3.42 g/L (spec > 3.80 g/L), out of trend.', kind: 'observation', citations: ['lims-qc-948'] },
          { text: '1 of 2 analyst signatures recorded; second sign-off pending in LIMS.', kind: 'unknown', citations: ['ag-lims-qc948-signoff'] },
        ],
      },
      {
        id: 'c2', subtask: 'C · Laboratory confirmation', short: 'Compare to spec', title: 'Compare titer with spec and campaign trend', tool: 'stats-core v2.0.1', durationSec: 3, resolvesSource: 'Maximo CMMS',
        outputs: (a: Answers) => [
          { text: 'Titer is 0.38 g/L below the lower specification and below the two prior batches.', kind: 'calculated', citations: ['lims-qc-948'] },
          ...(a['qc-pending'] === 'proceed' ? [{ text: 'Uses preliminary (single-analyst) data — annotated throughout the dossier.', kind: 'unknown' as const }] : []),
        ],
      },
      {
        id: 'draft', short: 'Draft narrative & CAPA', title: 'Assemble deviation narrative and CAPA items', tool: 'artifact-builder v1.0.0', durationSec: 4,
        outputs: [{ text: 'Draft deviation narrative and 2 CAPA items staged as a Review Required proposal. Nothing written to Veeva QMS.', kind: 'recommendation', citations: ['sop-up-014'] }],
      },
    ],
    gates: [
      {
        id: 'qc-pending', kind: 'INPUT', beforeStep: 3,
        question: "QC-948 harvest titer is 'Awaiting 2nd analyst sign-off'. How should the analysis proceed?",
        context: 'Proceeding labels every titer-based statement as preliminary. Pausing keeps the task here until LIMS shows concurrence.',
        citations: ['ag-lims-qc948-signoff'],
        options: [
          { label: 'Proceed with preliminary data (annotated)', value: 'proceed', recommended: true },
          { label: 'Pause until QC concurrence', value: 'pause', holds: true, note: 'In this demo, concurrence never arrives; choose Proceed to continue.' },
        ],
      },
    ],
    artifacts: [
      {
        id: 'narrative', title: 'Q-DEV-031 deviation narrative (draft)', kind: 'recommendation', availableAfter: 5, insertTarget: 'QUAL-02',
        summary: 'Structured narrative with event, impact, evidence and the leading hypothesis.',
        build: (a) => ({
          type: 'DOC_DRAFT', docId: 'Q-DEV-031', version: 'Narrative draft 1',
          sections: [
            { heading: 'Event', body: 'At T+264.4h on MES-26073, PM-204 head pressure peaked at 1.48 bar (ceiling 1.20 bar) and delivered feed dropped 14.2%.', kind: 'observation', citations: ['historian-up01', 'qms-q-dev-031'] },
            { heading: 'Impact', body: `Harvest titer 3.42 g/L against a > 3.80 g/L specification${a['qc-pending'] === 'proceed' ? ' (preliminary: 1 of 2 analyst signatures)' : ''}. Lot on QA hold.`, kind: 'observation', citations: ['lims-qc-948', 'c-qms-hold-26073'] },
            { heading: 'Probable cause (not established)', body: 'Tubing over-occlusion after WO-8819 without the SOP-UP-014 §7.2 slip verification. Media lot and DO drift contradicted.', kind: 'hypothesis', citations: ['cmms-wo-8819', 'sop-up-014'] },
          ],
        }),
      },
      {
        id: 'capa', title: 'Proposed CAPA items', kind: 'recommendation', availableAfter: 5, insertTarget: 'QUAL-02',
        summary: '2 corrective/preventive actions with owners and verification criteria.',
        build: () => ({
          type: 'TABLE_DIFF', columns: ['CAPA item', 'Current state', 'Proposed'],
          note: 'Proposals only. CAPA records are created by the QMS owner in Veeva Vault after approval.',
          rows: [
            { parameter: 'PM-204 tubing spool', current: '412 h in service (400–500 h rated)', proposed: 'Exchange spool; verify slip ±3% gravimetrically', kind: 'recommendation', citation: 'oem-masterflex' },
            { parameter: 'SOP-UP-014 §7.2', current: 'Slip check required, not enforced in eBR', proposed: 'Add eBR hard-stop after any occlusion change', kind: 'recommendation', citation: 'sop-up-014' },
          ],
        }),
      },
      { id: 'gate', title: 'Deviation & CAPA proposal · REV-QDEV031-04', kind: 'recommendation', availableAfter: 5, summary: 'QA authorization required.', build: () => ({ type: 'REVIEW_GATE' }) },
    ],
    review: {
      proposalId: 'REV-QDEV031-04',
      title: 'Q-DEV-031 narrative and CAPA proposal',
      signOffRoles: ['QA_REVIEWER'],
      riskTier: 'High',
      systemOfRecord: 'Veeva Vault QMS',
      rationale: 'Gives the QMS owner a cited starting narrative and two CAPA candidates tied to the leading hypothesis.',
      expectedResult: 'No feed-delivery shortfall > 3% on the next three batches after spool exchange and SOP change.',
      constraints: 'QMS record edits are made by the record owner in Veeva; this proposal does not change the record.',
      owner: 'Priya Natarajan · QA',
      changeMind: ['TP-01 slip test shows delivery within ±3% at 0.55 N·m.', 'Second analyst revises the QC-948 titer above 3.80 g/L.'],
      monitor: 'Watch PM-204 delivered-vs-setpoint and head pressure on MES-26074–26076.',
      diff: () => [
        { parameter: 'CAPA-1 Spool exchange', current: 'Not planned', proposed: 'Before MES-26074 inoculation', kind: 'recommendation', citation: 'oem-masterflex' },
        { parameter: 'CAPA-2 SOP-UP-014 §7.2', current: 'Rev 7', proposed: 'Rev 8 draft with eBR hard-stop', kind: 'recommendation', citation: 'sop-up-014' },
      ],
    },
  },

  /* ----------------------------------------------------------- Journey 4 */
  {
    id: 'schedule',
    taskId: 'TASK-2026-1053',
    title: 'PM-204 sanitization vs MES-26074 inoculation conflict',
    agent: 'Schedule Resolver',
    originFrame: 'PLAN-01',
    summary: 'Resolve the 4.5 h overlap between PM-SAN-204 and MES-26074 inoculation.',
    keywords: ['schedule', 'conflict', 'collision', 'sanitization', 'inoculation', 'shift', 'plan', 'pm-205', 'mes-26074', 'cip'],
    defaultScope: [
      { id: 'fac-3b', kind: 'FACILITY', value: 'Mesa Site · Cleanroom Suite 3B' },
      { id: 'batch-74', kind: 'BATCHES', value: 'MES-26074 (planned inoculation Mon 26 Oct 09:30)' },
      { id: 'rec-pm', kind: 'RECORD', value: 'Maximo PM-SAN-204' },
    ],
    sources: ['Maximo CMMS', 'DeltaV eBR', 'SAP ERP'],
    unavailableSources: ['SAP ERP'],
    checkpoints: [
      {
        id: 'pm', short: 'Read PM schedule', title: 'Read Maximo PM and CIP/SIP schedule', tool: 'connector-hub v2.3.1 (Maximo OSLC)', durationSec: 3, resolvesSource: 'Maximo CMMS',
        outputs: [{ text: 'PM-SAN-204 runs Mon 26 Oct 06:00–14:00 and holds PM-204.', kind: 'observation', citations: ['c-maximo-cip-sched'] }],
      },
      {
        id: 'mes', short: 'Read MES plan', title: 'Read MES planning extract', tool: 'connector-hub v2.3.1 (DeltaV eBR)', durationSec: 3, resolvesSource: 'DeltaV eBR',
        outputs: [{ text: 'MES-26074 inoculation planned 09:30; needs PM-204 from that point. Overlap 4.5 h.', kind: 'calculated', citations: ['a-ebr-schedule-26074'] }],
      },
      {
        id: 'erp', short: 'ERP labor & cost', title: 'Check labor and material cost impact (SAP ERP)', tool: 'connector-hub v2.3.1 (SAP)', durationSec: 2,
        outputs: (a: Answers) => [{ text: a['erp-access'] === 'continue' ? 'SAP ERP not connected — labor and cost impact left as Unknown.' : 'SAP ERP access pending.', kind: 'unknown', citations: ['a-sap-not-connected'] }],
      },
      {
        id: 'eval', short: 'Evaluate options', title: 'Evaluate schedule heuristics', tool: 'constraint-solver v0.8.3', durationSec: 4,
        outputs: [
          { text: 'Option A: delay MES-26074 inoculation +4.5 h; harvest slack absorbs it, no change to vialing slot.', kind: 'calculated', citations: ['ag-calc-schedule', 'a-ebr-schedule-26074'] },
          { text: 'Option B: divert feed to standby pump PM-205; needs 3.0 h CIP and QA sign-off; PM-205 OQ is overdue by 17 days.', kind: 'calculated', citations: ['ag-calc-schedule', 'c-maximo-pm205-qual'] },
          { text: 'Seed-train hold limit for this cell line was not found in connected sources.', kind: 'unknown', citations: ['ag-calc-schedule'] },
        ],
      },
      {
        id: 'prep', short: 'Prepare diff', title: 'Prepare schedule diff matrix', tool: 'artifact-builder v1.0.0', durationSec: 2,
        outputs: [{ text: 'Schedule diff ready. Select an option to prepare an adjustment proposal.', kind: 'recommendation' }],
      },
    ],
    gates: [
      {
        id: 'erp-access', kind: 'PERMISSION', beforeStep: 2,
        question: 'SAP ERP is not connected for this workspace, so labor and material cost impact cannot be read.',
        context: 'An administrator would need to authorize a read-only SAP connector. The schedule analysis itself does not depend on it.',
        citations: ['a-sap-not-connected'],
        options: [
          { label: 'Continue without ERP (cost shown as Unknown)', value: 'continue', recommended: true },
          { label: 'Request read-only connector from admin', value: 'request', holds: true, note: 'Logged as a request (demo). The task waits until access is granted or you continue without it.' },
        ],
      },
    ],
    artifacts: [
      {
        id: 'sched-diff', title: 'Schedule diff matrix', kind: 'calculated', availableAfter: 5, insertTarget: 'PLAN-01',
        summary: 'Side-by-side comparison of two heuristics. Choose one to prepare a proposal.',
        build: () => ({
          type: 'SCHEDULE_DIFF',
          options: [
            { key: 'A', title: 'Delay MES-26074 inoculation +4.5 h', recommended: true, rows: [['Inoculation', '09:30 → 14:00 Mon 26 Oct'], ['Harvest (Day 14)', 'Absorbed by 18 h slack'], ['Vialing slot', 'No change'], ['Extra sanitization', 'None'], ['Labor / cost', 'Unknown (ERP not connected)']], risks: ['Seed train held 4.5 h longer at N-1; hold limit not found in connected sources — confirm with MSAT.'], citations: ['ag-calc-schedule', 'a-ebr-schedule-26074', 'c-maximo-cip-sched'] },
            { key: 'B', title: 'Divert feed to standby pump PM-205', rows: [['Inoculation', 'On time (09:30)'], ['Harvest (Day 14)', 'On time'], ['Vialing slot', 'No change'], ['Extra sanitization', '3.0 h emergency CIP on PM-205'], ['Labor / cost', 'Unknown (ERP not connected)']], risks: ['Needs QA sign-off for an unplanned equipment substitution.', 'PM-205 OQ overdue by 17 days; tubing not installed.'], citations: ['ag-calc-schedule', 'c-maximo-pm205-qual'] },
          ],
        }),
      },
      { id: 'gate', title: 'Schedule adjustment proposal · REV-PLAN-12', kind: 'recommendation', availableAfter: 5, summary: 'Supervisor signature required.', build: () => ({ type: 'REVIEW_GATE' }) },
    ],
    review: {
      proposalId: 'REV-PLAN-12',
      title: 'Suite 3B schedule adjustment for Mon 26 Oct',
      signOffRoles: ['CLEANROOM_SUPERVISOR'],
      riskTier: 'Medium',
      systemOfRecord: 'Maximo CMMS / MES planning',
      rationale: 'Removes the 4.5 h PM-204 overlap without moving the vialing date.',
      expectedResult: 'PM-SAN-204 completes before MES-26074 needs PM-204; no schedule conflicts remain on 26 Oct.',
      constraints: 'Planner applies the change in MES/Maximo; labor and cost impact unknown without ERP; seed-train hold limit to be confirmed.',
      owner: 'Marcus Bell · Cleanroom Supervisor',
      changeMind: ['PM-SAN-204 is shortened or moved by Maintenance.', 'MSAT confirms the seed-train hold limit is shorter than 4.5 h.'],
      monitor: 'Confirm actual inoculation and PM-SAN-204 completion times on 26 Oct.',
      diff: (_a, s) => s['heuristic'] === 'B'
        ? [{ parameter: 'MES-26074 feed pump', current: 'PM-204', proposed: 'PM-205 (after 3.0 h CIP)', kind: 'recommendation', citation: 'c-maximo-pm205-qual' }]
        : [{ parameter: 'MES-26074 inoculation', current: 'Mon 26 Oct 09:30', proposed: 'Mon 26 Oct 14:00 (+4.5 h)', kind: 'recommendation', citation: 'a-ebr-schedule-26074' }],
    },
  },
];

export const TEMPLATE_BY_ID: Record<string, TaskTemplate> = Object.fromEntries(TEMPLATES.map((t) => [t.id, t]));

export function resolveOutputs(t: TaskTemplate, i: number, answers: Answers) {
  const o = t.checkpoints[i].outputs;
  return typeof o === 'function' ? o(answers) : o;
}

/** Best keyword match for free text; null when nothing matches. */
export function matchTemplate(text: string): TaskTemplate | null {
  const q = text.toLowerCase();
  let best: { t: TaskTemplate; score: number } | null = null;
  for (const t of TEMPLATES) {
    const score = t.keywords.filter((k) => q.includes(k)).length;
    if (score > 0 && (!best || score > best.score)) best = { t, score };
  }
  return best?.t ?? null;
}
