import type { Citation } from '../biomanufacturingData';

/** Extra synthetic citations used by batch D screens. Keys must be unique across all citation files. */
export const CITATIONS_D: Record<string, Citation> = {
  'd-qms-dev-019': {
    id: 'd-qms-dev-019',
    sourceSystem: 'Veeva Vault QMS',
    documentName: 'Deviation Q-DEV-019 (closed)',
    sectionOrClause: 'Root cause summary · §4',
    rawExcerpt:
      'Feed flow on BR-UP-02 PM-201 ran 9.6% below setpoint for 3.1 h after scheduled calibration CAL-2981. Occlusion bed reseated during calibration; slip verification omitted. Root cause: procedural (verification step not performed). CAPA-0412: add slip verification sign-off to SOP-UP-014 (implemented as Rev 7 §7.2).',
    sha256Hash: '93526c13acd2be6c07906871749e4eed2eed207cee48996f2a46326d4041e3a4',
    timestamp: 'Closed 2025-11-21',
    provenanceConfidence: 99.3,
  },
  'd-cmms-cal-3310': {
    id: 'd-cmms-cal-3310',
    sourceSystem: 'Maximo CMMS',
    documentName: 'Calibration record CAL-3310 · PM-204',
    sectionOrClause: 'Gravimetric flow calibration · result block',
    rawExcerpt:
      'ASSET=PM-204 PROC=CAL-FLOW-GRAV-02 DATE=2026-10-17T06:40Z AS_FOUND=16.21 mL/min AS_LEFT=16.92 mL/min SP=16.90 TOL=±3% RESULT=PASS TECH=D.Huang NOTE=static test only; dynamic slip test deferred (fixture FX-12 out for repair)',
    sha256Hash: '42b493a2ee6e3b0a4a46e01e6f56f1ce066990a41475f3cce07b5320d43e8881',
    timestamp: '2026-10-17 06:40 UTC (T-49h)',
    provenanceConfidence: 98.9,
  },
  'd-ebr-mes-26068': {
    id: 'd-ebr-mes-26068',
    sourceSystem: 'DeltaV eBR',
    documentName: 'eBR MES-26068 · Phase 05 Fed-Batch',
    sectionOrClause: 'Step 05.4 · exception E-2 (prior campaign)',
    rawExcerpt:
      'PHASE=05 STEP=05.4 EXCEPTION=E-2 FEED_PV below SP by 6.8% for 52 min; operator comment: "tubing reseated per SOP-UP-014 Rev 6 §7.2, flow recovered". QA_REVIEW=ACCEPTED',
    sha256Hash: '846e1b14df760c86cb07cc5bca6a1ea9ee2bfd0d5382d6d1bfacc90b1915aea3',
    timestamp: '2026-05-08 22:14 UTC',
    provenanceConfidence: 98.4,
  },
  'd-lims-qc-917': {
    id: 'd-lims-qc-917',
    sourceSystem: 'LabWare LIMS',
    documentName: 'Sample QC-917 · Result set RS-75502',
    sectionOrClause: 'Test HPLC-PROA-01 · titer',
    rawExcerpt: 'SAMPLE=QC-917 BATCH=MES-26068 TEST=HPLC-PROA-01 RESULT=3.71 UNIT=g/L SPEC=>3.80 STATUS=OOT REVIEW=APPROVED (L.Moreau)',
    sha256Hash: 'fd18131cfaf02ecbb330a05674f958c22818d052857c749a41d570e27dbabd35',
    timestamp: '2026-05-12 10:02 UTC',
    provenanceConfidence: 99.8,
  },
  'd-cmms-tubing-hours': {
    id: 'd-cmms-tubing-hours',
    sourceSystem: 'Maximo CMMS',
    documentName: 'Asset meter reading · PM-204 tubing set TS-24-0931',
    sectionOrClause: 'Meter RUNHRS',
    rawExcerpt: 'ASSET=PM-204 COMPONENT=TS-24-0931 (Pt-cured silicone, size 24) INSTALLED=2026-10-02 METER=RUNHRS READING=412 h LAST_READ=2026-10-19T08:00Z',
    sha256Hash: '9d1d7103f919738c8fb4936c9585d947888c5f5d318960960b698a307aeb4fb1',
    timestamp: '2026-10-19 08:00 UTC',
    provenanceConfidence: 99.0,
  },
  'd-mes-cip-schedule': {
    id: 'd-mes-cip-schedule',
    sourceSystem: 'DeltaV eBR',
    documentName: 'MES schedule export · Suite 3B',
    sectionOrClause: 'Monday 2026-10-26 · BR-UP-01',
    rawExcerpt:
      'ORDER=CIP-UP01-118 EQUIP=BR-UP-01/PM-204 START=06:00 END=14:00\nORDER=MES-26074 OP=INOCULATION EQUIP=BR-UP-01 START=09:30 END=11:30\nCONFLICT=OVERLAP 4.5 h (soft)',
    sha256Hash: '72c1fae67efbe69fe0f69c2c4685b8ae22edc2c7d43a6d5db90d012a8249a103',
    timestamp: 'Exported 2026-10-19 07:55 UTC',
    provenanceConfidence: 99.5,
  },
  'd-kafka-event-log': {
    id: 'd-kafka-event-log',
    sourceSystem: 'OSIsoft PI',
    documentName: 'Agent event stream · topic mos.events.up01',
    sectionOrClause: 'Offsets 1,882,410–1,882,416',
    rawExcerpt:
      '08:26:03Z alarm.raised ALM-UP-204 PM204.HEAD_P=1.48 bar\n08:26:04Z agent.triggered msat-yield-sentry RUN-2026-1042\n08:31:12Z ebr.exception MES-26073 step 05.4 DEV=-14.3%\n11:40:20Z lims.result QC-948 STATUS=OOT',
    sha256Hash: '24ae6eed34ca1b106ddf3f34683dcaedcca49bd40485cbc83befa1b714349d7d',
    timestamp: '2026-10-19 08:26–11:40 UTC',
    provenanceConfidence: 100,
    transformation: 'Events are references to source records; payloads are not modified by the event stream.',
  },
};
