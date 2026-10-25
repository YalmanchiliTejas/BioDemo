// Synthetic trace for RUN-2026-1042 (MSAT Yield Sentry). Durations sum to the 6m 41s shown in the execution ledger.
import type { ClaimKind } from '@/components/ui';

export type TraceStep = {
  n: number;
  title: string;
  tool: string;
  duration: string;
  inputs: string[];
  outputs: Array<{ text: string; kind: ClaimKind }>;
  citations: string[];
  log: string;
};

export const TRACE_STEPS: TraceStep[] = [
  {
    n: 1,
    title: 'Gather data',
    tool: 'connector-hub v2.3.1 (PI Web API, DeltaV eBR export, LabWare REST, Maximo OSLC)',
    duration: '1m 52s',
    inputs: ['Workspace INV-104 scope: BR-UP-01, PM-204', 'Batches MES-26071, MES-26072, MES-26073', 'Window T+0–280h'],
    outputs: [
      { text: '24,190 telemetry points across 7 tags (read-only)', kind: 'observation' },
      { text: '3 eBR phase records, 2 LIMS result sets, 4 Maximo records', kind: 'observation' },
      { text: 'SAP ERP not connected — material cost context unavailable', kind: 'unknown' },
    ],
    citations: ['historian-up01', 'ebr-mes-26073', 'lims-qc-948'],
    log: `08:26:04Z run.start RUN-2026-1042 agent=msat-yield-sentry policy=v4 trigger=ALM-UP-204
08:26:05Z pi.query tags=7 batches=3 window=0-280h -> 24190 rows (quality GOOD 99.7%)
08:26:41Z ebr.fetch MES-26071..26073 phase=05 -> 3 records
08:27:12Z lims.fetch batch in (26071,26072,26073) -> RS-77120, RS-76881
08:27:40Z cmms.fetch asset=PM-204 since=-30d -> WO-8819, WO-8790, CAL-3310, PM-204-RUNHRS
08:27:55Z erp.fetch SKIPPED connector=not_configured
08:27:56Z step.done 1 elapsed=1m52s`,
  },
  {
    n: 2,
    title: 'Align timelines & impute gaps',
    tool: 'align-ts v1.8.0 · kalman-rts v0.9.2',
    duration: '0m 47s',
    inputs: ['24,190 raw points', 'Inoculation timestamps from eBR (T+0)'],
    outputs: [
      { text: 'All batches aligned on elapsed time from inoculation; timezone UTC confirmed', kind: 'calculated' },
      { text: '42-min historian gap at T+182.0–182.7h backfilled with Kalman (RTS) estimate — 42 points flagged', kind: 'imputed' },
      { text: 'Imputed points excluded from every downstream statistic', kind: 'calculated' },
    ],
    citations: ['historian-gap'],
    log: `08:27:57Z align.elapsed ref=eBR.INOC_TS batches=3 offset_hrs=[0.0,0.0,0.0]
08:28:02Z resample 1min mean tags=7
08:28:03Z gap.detect MES-26073 PM204.FLOW_PV 2026-10-15T14:00Z..14:42Z n_missing=42
08:28:04Z kalman.rts q=0.002 r=0.015 -> 42 imputed points flag=IMPUTED
08:28:05Z stats.policy exclude_flags=[IMPUTED,BAD]
08:28:43Z step.done 2 elapsed=0m47s`,
  },
  {
    n: 3,
    title: 'Cross-reference CMMS (WO-8819)',
    tool: 'cmms-correlate v1.2.4',
    duration: '1m 10s',
    inputs: ['Alarm ALM-UP-204 at T+264.4h', 'PM-204 maintenance history (30 days)'],
    outputs: [
      { text: 'WO-8819 raised occlusion clamp torque 0.42 → 0.55 N·m at T-48h; dynamic slip verification not performed', kind: 'observation' },
      { text: 'CAL-3310 static flow calibration passed; dynamic slip test deferred', kind: 'observation' },
      { text: 'SOP-UP-014 Rev 7 §7.2 requires dynamic slip verification after occlusion adjustment', kind: 'observation' },
    ],
    citations: ['cmms-wo-8819', 'd-cmms-cal-3310', 'sop-up-014'],
    log: `08:28:44Z cmms.window asset=PM-204 around=T+264.4h lookback=72h
08:28:45Z match WO-8819 closed=2026-10-17T07:12Z field=labor_notes "torque adjusted ... slip verification not performed"
08:28:46Z match CAL-3310 result=PASS note="dynamic slip test deferred"
08:29:20Z doc.lookup SOP-UP-014 rev=7 effective=2026-03-02 section=7.2
08:29:53Z step.done 3 elapsed=1m10s`,
  },
  {
    n: 4,
    title: 'Evaluate hypotheses',
    tool: 'hypothesis-eval v0.6.1 (deterministic checks; model-assisted ranking, model id logged)',
    duration: '2m 28s',
    inputs: ['Aligned telemetry (non-imputed)', 'CMMS correlation notes', 'Feed media CoA FM-2207', 'DO probes A/B'],
    outputs: [
      { text: 'A · Over-occlusion / tubing fatigue after WO-8819 — supported by pressure rise and droop timing; not established', kind: 'hypothesis' },
      { text: 'B · Feed media lot FM-2207 out of spec — contradicted: osmolality and glucose within spec', kind: 'contradicted' },
      { text: 'C · DO probe drift — contradicted: probes A/B agree within 0.6%', kind: 'contradicted' },
    ],
    citations: ['cmms-wo-8819', 'oem-masterflex', 'lims-media-lot', 'pi-do-probe'],
    log: `08:29:54Z hyp.A checks: head_p_rise(T+264.4)=PASS flow_droop_lag<10min=PASS tubing_hours=412 (OEM 400-500)=CONSISTENT
08:30:40Z hyp.B checks: FM-2207 osmo=312 in [290,330]=PASS glucose=198 in [190,210]=PASS -> CONTRADICTED
08:31:22Z hyp.C checks: |DO_A-DO_B| max=0.6% < 2.0% -> CONTRADICTED
08:32:05Z rank model=mos-reasoner-2026-09 temp=0 note="ranking is ordinal, not a probability"
08:32:21Z step.done 4 elapsed=2m28s`,
  },
  {
    n: 5,
    title: 'Compile patch proposal',
    tool: 'proposal-compiler v1.1.0',
    duration: '0m 24s',
    inputs: ['Hypothesis A (supported, not established)', 'SOP-UP-014 §7.2', 'Recipe RCP-AB014-V4'],
    outputs: [
      { text: 'Proposal RCP-AB014-V4.patch.02: closed-loop feed cascade on gravimetric delivery', kind: 'recommendation' },
      { text: 'Proposed maintenance: replace tubing TS-24-0931 and perform dynamic slip verification per §7.2', kind: 'recommendation' },
      { text: 'Routed to REV-01; requires MSAT Lead and QA Reviewer signatures. Not approved, not executed.', kind: 'unknown' },
    ],
    citations: ['sop-up-014', 'd-cmms-tubing-hours', 'qms-q-dev-031'],
    log: `08:32:22Z compile proposal=RCP-AB014-V4.patch.02 base=RCP-AB014-V4 diff_lines=14
08:32:30Z attach evidence n=11 manifest=sha256:f3a91c07…7c3d25 (synthetic)
08:32:41Z route REV-01 approvers=[MSAT_LEAD, QA_REVIEWER] writeback=LOCKED_READ_ONLY
08:32:45Z run.checkpoint state=AWAITING_HUMAN_AUTHORIZATION`,
  },
];

export type MemoryFact = { id: string; text: string; source: string; confirmedBy: string | null; corrected?: boolean };

export const CASE_MEMORY: MemoryFact[] = [
  { id: 'm1', text: 'PM-204 tubing set TS-24-0931 is at 412 run-hours.', source: 'd-cmms-tubing-hours', confirmedBy: 'Marcus Bell · 10-19' },
  { id: 'm2', text: 'The T+182.0–182.7h historian gap is a PI buffer overflow, not a process event.', source: 'historian-gap', confirmedBy: 'Alex Rivera · 10-19' },
  { id: 'm3', text: 'Feed media lot FM-2207 is ruled out as a cause for INV-104.', source: 'lims-media-lot', confirmedBy: 'Alex Rivera · 10-19' },
  { id: 'm4', text: 'Compare batches on elapsed time from inoculation (T+0), not wall clock.', source: 'ebr-mes-26073', confirmedBy: 'Alex Rivera · 10-18' },
  { id: 'm5', text: 'Dynamic slip fixture FX-12 is out for repair.', source: 'd-cmms-cal-3310', confirmedBy: null },
];
