import type { Citation } from '../biomanufacturingData';

/** Extra synthetic citations used by batch C screens. Keys must be unique across all citation files. */
export const CITATIONS_C: Record<string, Citation> = {
  'c-lims-qc-948-panel': {
    id: 'c-lims-qc-948-panel',
    sourceSystem: 'LabWare LIMS',
    documentName: 'Sample QC-948 · Result set RS-77120',
    sectionOrClause: 'Full test battery · harvest day 11',
    rawExcerpt:
      'SAMPLE=QC-948 TEST=VICELL-VCD-02 RESULT=14.8 UNIT=E6 cells/mL STATUS=PASS\nSAMPLE=QC-948 TEST=VICELL-VIAB-02 RESULT=86.1 UNIT=% SPEC=>=80 STATUS=PASS\nSAMPLE=QC-948 TEST=CEDEX-GLU-04 RESULT=1.9 UNIT=g/L SPEC=1.0-6.0 STATUS=PASS\nSAMPLE=QC-948 TEST=CEDEX-LAC-04 RESULT=2.6 UNIT=g/L SPEC=<=3.0 STATUS=PASS\nSAMPLE=QC-948 TEST=CEDEX-NH4-04 RESULT=6.9 UNIT=mmol/L SPEC=<=8.0 STATUS=PASS\nSAMPLE=QC-948 TEST=OSMO-03 RESULT=371 UNIT=mOsm/kg SPEC=280-380 STATUS=ALERT\nSAMPLE=QC-948 TEST=SEC-UPLC-05 RESULT=NOT_STARTED',
    sha256Hash: '1f17f34b67bb1f14d64dabb7388985053bb53fbd29ec22708e357a763d2ada13',
    timestamp: '2026-10-19 11:40 UTC',
    provenanceConfidence: 99.8,
  },
  'c-hplc-arc-run': {
    id: 'c-hplc-arc-run',
    sourceSystem: 'LabWare LIMS',
    documentName: 'Waters Arc HPLC · run ARC-2-26-1019-04 (attached raw data)',
    sectionOrClause: 'Injection 3 of 3 · Protein A affinity · 280 nm',
    rawExcerpt:
      'INSTRUMENT=ARC-HPLC-02 METHOD=HPLC-PROA-01 v4 COLUMN=POROS-A-20um LOT=CA-2231\nINJ=3 RT_MAIN=4.25 min AREA=6184.2 mAU*s HEIGHT=312.4 mAU\nSST: RT RSD=0.21% (<=1.0%) AREA RSD=0.64% (<=2.0%) PASS\nREF STD RS-IGG1-09 recovery 99.1% PASS',
    sha256Hash: '2cf8f1680a152c933e67e68339aaf9389fa16e5e8872416739fee0b171db0066',
    timestamp: '2026-10-19 10:58 UTC',
    provenanceConfidence: 99.6,
    transformation: 'Trace re-plotted from exported CDF at 0.035 min sampling; no baseline correction applied.',
  },
  'c-lims-coc-qc-948': {
    id: 'c-lims-coc-qc-948',
    sourceSystem: 'LabWare LIMS',
    documentName: 'Sample QC-948 · chain of custody',
    sectionOrClause: 'Custody log',
    rawExcerpt:
      '2026-10-19 06:12Z DRAWN BR-UP-01 sample port SP-2 by T.Reed\n2026-10-19 06:31Z RECEIVED QC Lab 2 by J.Alvarez temp=4.1C\n2026-10-19 07:05Z ALIQUOTED x4 (QC-948-A..D)\n2026-10-19 10:20Z INJECTED ARC-HPLC-02 by M.Okafor\n2026-10-19 11:40Z RESULT ENTERED, PRIMARY SIGN M.Okafor',
    sha256Hash: '65fa3c15fde65a0526a2d676036ab5378effbcb0b8ea0f49c1ebb320f7d96e4d',
    timestamp: '2026-10-19 11:40 UTC',
    provenanceConfidence: 99.9,
  },
  'c-qms-cc-017': {
    id: 'c-qms-cc-017',
    sourceSystem: 'Veeva Vault QMS',
    documentName: 'Change Control CC-017',
    sectionOrClause: 'Scope & impact assessment',
    rawExcerpt:
      'CC-017: Replace PM-204 pump head tubing supplier part (PharMed BPT -> Pt-cured silicone size 24) for CMP-26-10 onward. Impact: SOP-UP-014, BOM-UP-01-07. Status: IMPACT_ASSESSMENT. Owner: R. Chen (Engineering).',
    sha256Hash: 'df90fb5ff4f48fefcf84de084aa93020819d5643ed25ce087c8006bfc1b5ac42',
    timestamp: '2026-10-08 13:22 UTC',
    provenanceConfidence: 99.4,
  },
  'c-qms-hold-26073': {
    id: 'c-qms-hold-26073',
    sourceSystem: 'Veeva Vault QMS',
    documentName: 'Batch disposition hold · MES-26073',
    sectionOrClause: 'Hold reasons',
    rawExcerpt:
      'LOT=MES-26073 HOLD=ACTIVE PLACED=2026-10-19 09:05Z BY=P.Natarajan\nREASON_1=Deviation Q-DEV-031 open (Tier 2)\nREASON_2=OOT titer QC-948 pending second-person review\nRELEASE_CONDITION=Deviation closure + QA disposition',
    sha256Hash: '7ee1e366357481b0f5402c5ea049b0db0cccb2075a39b22e66d122db06adcfe3',
    timestamp: '2026-10-19 09:05 UTC',
    provenanceConfidence: 99.7,
  },
  'c-tt-006-gate2': {
    id: 'c-tt-006-gate2',
    sourceSystem: 'Documentum',
    documentName: 'TT-006 Gate 2 review minutes',
    sectionOrClause: 'Action item 4 · feed control loop',
    rawExcerpt:
      'AI-4: Durham Automation to supply PID cascade constants (Kc, Ti, Td) for FIC-2201 feed loop on BR-D-2000. Current DeltaV module at Durham uses flow-only control; no gravimetric outer loop configured. Gate 2 cannot close until mapping is reviewed by MSAT. Owner: K. Osei. Due: 2026-11-06.',
    sha256Hash: '8ab42e380a862eb2f6e3d68d97eeb033088a9ce4de853bb10b09e89b61d3b270',
    timestamp: '2026-10-14 15:30 UTC',
    provenanceConfidence: 98.9,
  },
  'c-mesa-sub-spec': {
    id: 'c-mesa-sub-spec',
    sourceSystem: 'Documentum',
    documentName: 'EQ-SPEC-MESA-SUB500 · 500L single-use bioreactor',
    sectionOrClause: '§3 Geometry & agitation',
    rawExcerpt:
      'Working volume 500 L. H/D 1.5:1. Impeller: single 3-blade pitched (45°) down-pumping, D/T 0.33. Sparger: drilled-hole 1 mm + open pipe. Tip speed at 160 rpm: 1.38 m/s. P/V measured 42.8 W/m³. kLa (air, 0.05 vvm) 8.4 h⁻¹. Control: DeltaV v14, gravimetric feed cascade.',
    sha256Hash: 'b7bb2339758179672a904d483eab4788c1e9cc4b91bb5c86abd8422160862b00',
    timestamp: 'Rev 3 · 2025-06-11',
    provenanceConfidence: 99.1,
  },
  'c-durham-ss-spec': {
    id: 'c-durham-ss-spec',
    sourceSystem: 'Documentum',
    documentName: 'EQ-SPEC-DUR-SS2000 · 2000L stainless bioreactor',
    sectionOrClause: '§3 Geometry & agitation',
    rawExcerpt:
      'Working volume 2000 L. H/D 2.0:1. Impellers: dual — lower Rushton 6-blade, upper pitched-blade 45°, D/T 0.35. Sparger: ring sparger 2 mm. Tip speed: [not stated]. kLa: characterisation study pending (ENG-RPT-0447 not issued). Control: DeltaV v13, flow-only feed loop.',
    sha256Hash: '8dc90830701ade4af470aec16526599bf3fd7ea5787f137c75a9453953eff647',
    timestamp: 'Rev 1 · 2023-02-27',
    provenanceConfidence: 97.8,
  },
  'c-maximo-pm205-qual': {
    id: 'c-maximo-pm205-qual',
    sourceSystem: 'Maximo CMMS',
    documentName: 'Asset PM-205 · qualification & PM status',
    sectionOrClause: 'Asset record',
    rawExcerpt:
      'ASSET=PM-205 STATUS=STANDBY LAST_OQ=2026-04-02 OQ_DUE=2026-10-02 (OVERDUE 17 d) TUBING=NOT_INSTALLED CAL_FLOW=2026-08-14 PASS',
    sha256Hash: '4fb96d54488ff4674bb905f55e539bbb414e8feb92a114e3ff186311cb2b6076',
    timestamp: '2026-10-19 07:00 UTC',
    provenanceConfidence: 99.3,
  },
  'c-maximo-cip-sched': {
    id: 'c-maximo-cip-sched',
    sourceSystem: 'Maximo CMMS',
    documentName: 'PM schedule · Suite 3B · week 44',
    sectionOrClause: 'PM-204 sanitization PM-SAN-204',
    rawExcerpt:
      'WO=PM-SAN-204-W44 ASSET=PM-204 TASK=CIP/SIP sanitization of feed path START=2026-10-26 06:00 DUR=8.0h\nLINKED BATCH (planned) MES-26074 INOC=2026-10-26 09:30 (from MES planning extract)',
    sha256Hash: 'f32b4d419405acc48bea44542ae0ea2362fe9d0f0aabbb9d3c07cca00c9b8e12',
    timestamp: '2026-10-19 06:45 UTC',
    provenanceConfidence: 98.4,
  },
};
