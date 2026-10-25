import type { Citation } from '../biomanufacturingData';

/** Extra synthetic citations used by batch A screens. Keys must be unique across all citation files. */
export const CITATIONS_A: Record<string, Citation> = {
  'a-pi-interface-log': {
    id: 'a-pi-interface-log',
    sourceSystem: 'OSIsoft PI',
    documentName: 'PI Interface log · PI-UFL-MESA-02',
    sectionOrClause: 'Buffer subsystem · 2026-10-15',
    rawExcerpt:
      '2026-10-15 14:00:07Z [W] PIBufSS: buffer queue full (max 32 MB), new events discarded\n2026-10-15 14:41:52Z [I] PIBufSS: connection to PI-DA-MESA restored, flushing 0 queued events\n2026-10-15 14:42:00Z [I] Interface resumed normal collection (147 tags)',
    sha256Hash: '10ca328db4648608596f768fd2c9132a547840c634f08698a855dd13374aa95d',
    timestamp: '2026-10-15 14:00–14:42 UTC',
    provenanceConfidence: 99.2,
    transformation: 'Log lines retrieved verbatim through the read-only PI Web API service account.',
  },
  'a-lims-assay-panel': {
    id: 'a-lims-assay-panel',
    sourceSystem: 'LabWare LIMS',
    documentName: 'Campaign CMP-26-10 · test panel export',
    sectionOrClause: 'Tests indexed at intake',
    rawExcerpt:
      'TEST=HPLC-PROA-01 (titer) SAMPLES=9\nTEST=VICELL-VCD-02 (viable cell density) SAMPLES=42\nTEST=OSMO-03 (osmolality) SAMPLES=18\nTEST=CEDEX-GLU-04 (glucose/lactate) SAMPLES=42',
    sha256Hash: '854b096669fcd7b7488eb02253925c69c141f679c0a32e3055d369917fac6497',
    timestamp: '2026-10-19 12:10 UTC',
    provenanceConfidence: 99.7,
  },
  'a-maximo-pm-cip': {
    id: 'a-maximo-pm-cip',
    sourceSystem: 'Maximo CMMS',
    documentName: 'PM schedule PM-BRUP01-CIP-Q4',
    sectionOrClause: 'Planned job · Mon 2026-10-26',
    rawExcerpt:
      'ASSET=BR-UP-01 JOB=CIP/SIP sanitization incl. PM-204 feed line PLANNED_START=2026-10-26T06:00Z DURATION=8.0h CREW=UPS-B STATUS=APPR',
    sha256Hash: '54ab307a9925d7c533094db3ae8ba5daef1ede060cdec68d5110666b316b4489',
    timestamp: '2026-10-18 15:30 UTC',
    provenanceConfidence: 98.9,
  },
  'a-ebr-schedule-26074': {
    id: 'a-ebr-schedule-26074',
    sourceSystem: 'DeltaV eBR',
    documentName: 'Batch schedule · MES-26074',
    sectionOrClause: 'Phase 01 Inoculation',
    rawExcerpt:
      'BATCH=MES-26074 UNIT=BR-UP-01 PHASE=01 INOCULATION SCHED_START=2026-10-26T09:30Z STATE=SCHEDULED RECIPE=AB014-UP-V4',
    sha256Hash: '9fffec3696ee5685f93a225b45382a308efe8b54e4c6da9db7863bd6191d0211',
    timestamp: '2026-10-18 09:12 UTC',
    provenanceConfidence: 99.0,
  },
  'a-sop-tt-003': {
    id: 'a-sop-tt-003',
    sourceSystem: 'Documentum',
    documentName: 'SOP-TT-003 Rev 4 · Process Transfer Gate Review',
    sectionOrClause: '§5.3 Gate 2 engineering dossier',
    rawExcerpt:
      '5.3 Gate 2 SHALL NOT be cleared until every critical control loop in the donor process has a documented, mapped equivalent at the recipient site, including controller tuning constants and their scale-up rationale.',
    sha256Hash: '595717b530256a790acb511b130b0b93e077278a13dbef9294fcbce3f2b5f704',
    timestamp: 'Effective 2025-11-14',
    provenanceConfidence: 99.6,
  },
  'a-veeva-sop-qa-021': {
    id: 'a-veeva-sop-qa-021',
    sourceSystem: 'Veeva Vault QMS',
    documentName: 'SOP-QA-021 Rev 9 · Deviation Management',
    sectionOrClause: '§6.4 Major deviation investigation timeline',
    rawExcerpt:
      '6.4 Major (Tier 2) deviations SHALL have a root-cause investigation completed and approved by QA within 30 calendar days of discovery. Product impact assessment is required before batch disposition.',
    sha256Hash: '68c6aa4e54b629cdbf32e35b5d814368c651ef55e090b4502beb9d87a6eedee4',
    timestamp: 'Effective 2026-01-20',
    provenanceConfidence: 99.8,
  },
  'a-sap-not-connected': {
    id: 'a-sap-not-connected',
    sourceSystem: 'SAP ERP',
    documentName: 'Connector status · SAP S/4HANA (ERP)',
    sectionOrClause: 'No authorized service account',
    rawExcerpt:
      'CONNECTOR=sap-s4-erp STATE=NOT_CONNECTED REASON=No read-only RFC/OData service account provisioned. Material, lot and order data are absent from all analyses in this workspace.',
    sha256Hash: 'c82d8d1b52cd534e19409964b9f6dd29280d594a6b9e6d9143d199588de1b9a2',
    timestamp: '2026-10-19 16:40 UTC',
    provenanceConfidence: 100,
  },
};
