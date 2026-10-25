// Synthetic demonstration data. None of these values come from a real facility, batch, or system of record.
import { CITATIONS_A } from './citations/a';
import { CITATIONS_B } from './citations/b';
import { CITATIONS_C } from './citations/c';
import { CITATIONS_D } from './citations/d';

export const MOCK_DATASET = {
  facility: {
    name: 'Aster Biologics · Mesa Manufacturing',
    suite: 'Cleanroom Suite 3B (Upstream)',
    grade: 'Grade B (ISO 7)',
  },
  activeCampaign: {
    id: 'CMP-26-10',
    molecule: 'AB-mAb-014 (IgG1 Monoclonal Antibody)',
    targetYieldIndex: 82.0,
    batches: [
      { id: 'MES-26071', normalizedYield: 81.2, feedDeliveryL: 342.1, status: 'COMPLETED', release: 'RELEASED' },
      { id: 'MES-26072', normalizedYield: 78.4, feedDeliveryL: 328.6, status: 'COMPLETED', release: 'RELEASED' },
      { id: 'MES-26073', normalizedYield: 75.9, feedDeliveryL: 254.2, status: 'IN_EXECUTION', release: 'HOLD_ACTIVE' },
    ],
  },
  equipmentIncident: {
    tag: 'PM-204',
    name: 'Masterflex Peristaltic Feed Pump',
    skid: 'BR-UP-01 (2,000L Fed-Batch Bioreactor)',
    criticalEvent: 'T+264.4h head pressure spike to 1.48 bar (ceiling: 1.20 bar), -14.2% feed flow droop',
    workOrder: 'WO-8819 (Clamp torque adjustment performed at T-48h without dynamic slip verification)',
    sopReference: 'SOP-UP-014 Rev 7 §7.2',
  },
  qualityHold: {
    deviationId: 'Q-DEV-031',
    tier: 'MAJOR_TIER_2',
    sampleId: 'QC-948',
    hplcHarvestTiter: '3.42 g/L (OOT Alert, spec: >3.80 g/L)',
    vcd: '14.8 x 10^6 cells/mL',
    sha256Proof: '8f2c39d91fa70b2401ee8e239...e901',
  },
  techTransferBlocker: {
    projectId: 'TT-006',
    donor: 'Mesa 500L Single-Use Bioreactor',
    recipient: 'Durham 2000L Stainless Steel Bioreactor',
    gate: 'Gate 2 Clearance (Engineering & CPP Dossier)',
    blockerReason: 'Bioreactor feed-rate control loop PID cascade constant mapping unmapped at Durham',
  },
};

export const BATCH_COLORS: Record<string, string> = {
  'MES-26071': '#94a3b8',
  'MES-26072': '#0284c7',
  'MES-26073': '#dc2626',
};

export const GAP_INTERVAL = { startHour: 182.0, endHour: 182.7, annotation: 'Historian gap · 42 min (PI buffer overflow)' };
export const ANOMALY_HOUR = 264.4;

export type SourceSystem =
  | 'DeltaV eBR'
  | 'OSIsoft PI'
  | 'LabWare LIMS'
  | 'Maximo CMMS'
  | 'Documentum'
  | 'Veeva Vault QMS'
  | 'SAP ERP'
  /** Values computed by this application from other sources; never a system of record. */
  | 'Manufacturing OS (derived)';

export interface Citation {
  id: string;
  sourceSystem: SourceSystem;
  documentName: string;
  sectionOrClause: string;
  rawExcerpt: string;
  sha256Hash: string;
  timestamp: string;
  provenanceConfidence: number;
  deepLinkUrl?: string;
  transformation?: string;
}

/** Every evidence chip in the UI resolves to one of these records, so the inspector can always show the source. */
const CORE_CITATIONS: Record<string, Citation> = {
  'historian-up01': {
    id: 'historian-up01',
    sourceSystem: 'OSIsoft PI',
    documentName: 'Historian_UP01_Oct.csv',
    sectionOrClause: '§4.2 · tag BR-UP-01.PM204.FLOW_PV',
    rawExcerpt:
      'TS_UTC,TAG,VALUE,UNIT,QUALITY\n2026-10-19T08:24:00Z,BR-UP-01.PM204.FLOW_PV,16.88,mL/min,GOOD\n2026-10-19T08:25:00Z,BR-UP-01.PM204.FLOW_PV,15.12,mL/min,GOOD\n2026-10-19T08:26:00Z,BR-UP-01.PM204.FLOW_PV,14.48,mL/min,GOOD\n2026-10-19T08:26:00Z,BR-UP-01.PM204.HEAD_P,1.48,bar,GOOD',
    sha256Hash: 'a41f0c9e7b3d2285f6c1e09d4ab7731c2e8f5d60b9a4e17c3d02f8b65e1c94d7',
    timestamp: '2026-10-19 08:26 UTC',
    provenanceConfidence: 99.4,
    transformation: 'Resampled to 1-min mean; units unchanged; timezone confirmed UTC at intake.',
  },
  'historian-gap': {
    id: 'historian-gap',
    sourceSystem: 'OSIsoft PI',
    documentName: 'Historian_UP01_Oct.csv',
    sectionOrClause: '§4.2 · rows 10,921–10,962 (no data)',
    rawExcerpt:
      '2026-10-15T14:00:00Z,BR-UP-01.PM204.FLOW_PV,17.02,mL/min,GOOD\n-- 42 minutes with no records (QUALITY=NO_DATA) --\n2026-10-15T14:42:00Z,BR-UP-01.PM204.FLOW_PV,16.97,mL/min,GOOD',
    sha256Hash: 'c7e2b19a04d58f3e61a2097bd4c5e8f13a0b6d27e94c18f50a3d6b2e7f91c048',
    timestamp: '2026-10-15 14:00–14:42 UTC (Hour 182.0–182.7)',
    provenanceConfidence: 100,
    transformation: 'Kalman-smoothed estimate shown dashed. Imputed values are excluded from yield statistics.',
  },
  'cmms-wo-8819': {
    id: 'cmms-wo-8819',
    sourceSystem: 'Maximo CMMS',
    documentName: 'Work Order WO-8819',
    sectionOrClause: 'Labor notes · line 3',
    rawExcerpt:
      'PM-204 occlusion clamp torque adjusted from 0.42 N·m to 0.55 N·m per tech judgement after audible chatter. Dynamic slip verification not performed (fixture unavailable). Returned to service.',
    sha256Hash: '3b9d71e0c42af8865d10e7c39b2a4f6e8d05c71b93ae2f4d6081c7b5e39a2f60',
    timestamp: '2026-10-17 07:12 UTC (T-48h)',
    provenanceConfidence: 98.7,
  },
  'lims-qc-948': {
    id: 'lims-qc-948',
    sourceSystem: 'LabWare LIMS',
    documentName: 'Sample QC-948 · Result set RS-77120',
    sectionOrClause: 'Test HPLC-PROA-01 · titer',
    rawExcerpt:
      'SAMPLE=QC-948 TEST=HPLC-PROA-01 RESULT=3.42 UNIT=g/L SPEC=>3.80 STATUS=OOT ANALYST=M.Okafor REVIEW=PENDING',
    sha256Hash: '8f2c39d91fa70b2401ee8e239c4d6a1b07f5e38c29d1a64b0e7f3c58a92de901',
    timestamp: '2026-10-19 11:40 UTC',
    provenanceConfidence: 99.9,
  },
  'sop-up-014': {
    id: 'sop-up-014',
    sourceSystem: 'Documentum',
    documentName: 'SOP-UP-014 Rev 7 · Fed-Batch Feed Pump Operation',
    sectionOrClause: '§7.2 Tubing seating and occlusion',
    rawExcerpt:
      '7.2 After any occlusion adjustment, the operator SHALL perform a dynamic slip verification at the operating RPM before returning the pump to GMP service. Record the gravimetric delivery over 5 minutes; acceptance ±3% of setpoint.',
    sha256Hash: 'e05a8c3f2d71b946a0c8e1f37d29b54a6c0e8f13d7a29b5c4e60f1a83d7c2b19',
    timestamp: 'Effective 2026-03-02',
    provenanceConfidence: 99.8,
  },
  'ebr-mes-26073': {
    id: 'ebr-mes-26073',
    sourceSystem: 'DeltaV eBR',
    documentName: 'eBR MES-26073 · Phase 05 Fed-Batch',
    sectionOrClause: 'Step 05.4 Bolus nutrient addition',
    rawExcerpt:
      'PHASE=05 STEP=05.4 STATE=RUNNING FEED_SP=16.90 mL/min FEED_PV=14.48 mL/min DEV=-14.3% OPERATOR=T.Reed ACK=YES',
    sha256Hash: '5d17e4a90c3b28f6e1d07a49c3b85f20e6a1d94c7b03f58e2a16d90c4b7e3a85',
    timestamp: '2026-10-19 08:31 UTC (T+264.5h)',
    provenanceConfidence: 99.1,
  },
  'qms-q-dev-031': {
    id: 'qms-q-dev-031',
    sourceSystem: 'Veeva Vault QMS',
    documentName: 'Deviation Q-DEV-031',
    sectionOrClause: 'Initial description',
    rawExcerpt:
      'Feed flow on BR-UP-01 fell below setpoint by >10% for 47 min during Phase 05. PM-204 head pressure exceeded 1.20 bar ceiling. Batch MES-26073 placed on QA hold pending investigation.',
    sha256Hash: '91c4e0b7a2f3d58e6c09b1a47d3e2f8c5a06b9d14e7c3a2f80d5b6e19c4a7d03',
    timestamp: '2026-10-19 09:05 UTC',
    provenanceConfidence: 99.6,
  },
  'oem-masterflex': {
    id: 'oem-masterflex',
    sourceSystem: 'Documentum',
    documentName: 'Masterflex L/S Pump Head Manual (OEM)',
    sectionOrClause: 'Table 4 · Tubing service life',
    rawExcerpt:
      'Platinum-cured silicone, size 24: expected service life 400–500 h at ≤200 RPM. Increased occlusion shortens life and raises discharge pressure.',
    sha256Hash: '0e7b3c19d5a24f86b1e09c7d3a5f28e46b0c1d97a3e5f2b8c40d6e1a97b3c25f',
    timestamp: 'Rev C · 2024',
    provenanceConfidence: 97.2,
  },
  'lims-media-lot': {
    id: 'lims-media-lot',
    sourceSystem: 'LabWare LIMS',
    documentName: 'Raw material CoA · Feed Media Lot FM-2207',
    sectionOrClause: 'Osmolality, glucose',
    rawExcerpt: 'LOT=FM-2207 OSMO=312 mOsm/kg (spec 290–330) GLUCOSE=198 g/L (spec 190–210) STATUS=RELEASED',
    sha256Hash: '6a2d8f1c09e3b47a5d10c8e29f3b6a4d7e05c1b92f8a3d6e40c7b1a95e2d3f08',
    timestamp: '2026-09-28 16:02 UTC',
    provenanceConfidence: 99.5,
  },
  'pi-do-probe': {
    id: 'pi-do-probe',
    sourceSystem: 'OSIsoft PI',
    documentName: 'Historian_UP01_Oct.csv',
    sectionOrClause: '§4.5 · DO redundant probes A/B',
    rawExcerpt: 'BR-UP-01.DO_A mean 39.4% · BR-UP-01.DO_B mean 39.2% · max |A-B| 0.6% over T+200–280h',
    sha256Hash: 'b48e1d07c3a95f2e6d10b7c48a3f2e95d06c1a7b39e4f2d8c05a1b6e73d9c4f12',
    timestamp: '2026-10-19 12:00 UTC',
    provenanceConfidence: 99.0,
  },
};

export const CITATIONS: Record<string, Citation> = { ...CORE_CITATIONS, ...CITATIONS_A, ...CITATIONS_B, ...CITATIONS_C, ...CITATIONS_D };

export const BATCH_MANIFEST_HASH = 'f3a91c07e5d28b46a1c09e7d3b5f2a8e64c0d19b7a3e5f2c80d6b1e49a7c3d25';
