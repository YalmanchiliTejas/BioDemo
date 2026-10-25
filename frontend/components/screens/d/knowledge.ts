// Synthetic index entries for the KNOW-01 search screen. Every entry resolves to a CITATIONS record.

export type GxpClass = 'GMP-critical' | 'GMP' | 'Non-GxP reference';

export type KnowledgeDoc = {
  citationId: string;
  system: 'Documentum' | 'Maximo CMMS' | 'Veeva Vault QMS' | 'DeltaV eBR' | 'LabWare LIMS';
  gxp: GxpClass;
  equipment: string[];
  title: string;
  recordId: string;
  keywords: string;
  updated: string;
  href?: string;
};

export const KNOWLEDGE_DOCS: KnowledgeDoc[] = [
  {
    citationId: 'sop-up-014', system: 'Documentum', gxp: 'GMP-critical', equipment: ['PM-204', 'PM-201'],
    title: 'SOP-UP-014 Rev 7 §7.2 · Tubing seating and occlusion', recordId: 'SOP-UP-014 Rev 7',
    keywords: 'sop procedure calibration occlusion slip verification feed pump feed-rate deviation', updated: 'Effective 2026-03-02',
  },
  {
    citationId: 'd-qms-dev-019', system: 'Veeva Vault QMS', gxp: 'GMP', equipment: ['PM-201', 'BR-UP-02'],
    title: 'Q-DEV-019 · Feed flow below setpoint after calibration (closed)', recordId: 'Q-DEV-019',
    keywords: 'deviation feed-rate feed flow calibration capa root cause', updated: 'Closed 2025-11-21',
  },
  {
    citationId: 'd-cmms-cal-3310', system: 'Maximo CMMS', gxp: 'GMP', equipment: ['PM-204'],
    title: 'CAL-3310 · PM-204 gravimetric flow calibration', recordId: 'CAL-3310',
    keywords: 'calibration pm feed-rate flow gravimetric slip deferred', updated: '2026-10-17', href: '/equipment/PM-204',
  },
  {
    citationId: 'cmms-wo-8819', system: 'Maximo CMMS', gxp: 'GMP', equipment: ['PM-204'],
    title: 'WO-8819 · PM-204 occlusion clamp torque adjustment', recordId: 'WO-8819',
    keywords: 'work order maintenance occlusion torque slip verification', updated: '2026-10-17', href: '/equipment/PM-204',
  },
  {
    citationId: 'ebr-mes-26073', system: 'DeltaV eBR', gxp: 'GMP-critical', equipment: ['BR-UP-01', 'PM-204'],
    title: 'eBR MES-26073 · Step 05.4 Bolus nutrient addition', recordId: 'MES-26073',
    keywords: 'batch record feed-rate deviation feed flow setpoint', updated: '2026-10-19', href: '/batches/MES-26073',
  },
  {
    citationId: 'qms-q-dev-031', system: 'Veeva Vault QMS', gxp: 'GMP', equipment: ['BR-UP-01', 'PM-204'],
    title: 'Q-DEV-031 · Feed flow below setpoint, QA hold (open)', recordId: 'Q-DEV-031',
    keywords: 'deviation feed-rate feed flow head pressure hold', updated: '2026-10-19', href: '/quality/Q-DEV-031',
  },
  {
    citationId: 'd-ebr-mes-26068', system: 'DeltaV eBR', gxp: 'GMP', equipment: ['BR-UP-01', 'PM-204'],
    title: 'eBR MES-26068 · Step 05.4 exception E-2 (prior campaign)', recordId: 'MES-26068',
    keywords: 'batch record exception feed-rate deviation tubing reseated', updated: '2026-05-08',
  },
  {
    citationId: 'd-lims-qc-917', system: 'LabWare LIMS', gxp: 'GMP', equipment: ['BR-UP-01'],
    title: 'QC-917 · Harvest titer MES-26068 (OOT, approved)', recordId: 'QC-917',
    keywords: 'titer hplc result oot lab', updated: '2026-05-12',
  },
  {
    citationId: 'lims-qc-948', system: 'LabWare LIMS', gxp: 'GMP', equipment: ['BR-UP-01'],
    title: 'QC-948 · Harvest titer MES-26073 (OOT, review pending)', recordId: 'QC-948',
    keywords: 'titer hplc result oot lab', updated: '2026-10-19', href: '/laboratory/QC-948',
  },
  {
    citationId: 'oem-masterflex', system: 'Documentum', gxp: 'Non-GxP reference', equipment: ['PM-204', 'PM-201'],
    title: 'Masterflex L/S pump head manual · Table 4 tubing service life', recordId: 'OEM-MF-LS Rev C',
    keywords: 'oem manual tubing service life occlusion pressure feed pump', updated: 'Rev C · 2024',
  },
];

/** Each statement lists the sources it rests on; a statement is only shown when all its sources are in the visible results. */
export const ANSWER_STATEMENTS: Array<{ text: string; sources: string[] }> = [
  { text: 'A prior feed-rate deviation, Q-DEV-019 on PM-201, followed a scheduled calibration in which the occlusion bed was reseated and slip verification was omitted; it was closed with a procedural root cause.', sources: ['d-qms-dev-019'] },
  { text: 'In the prior campaign, MES-26068 recorded feed flow 6.8% below setpoint for 52 min at Step 05.4 after tubing was reseated.', sources: ['d-ebr-mes-26068'] },
  { text: 'PM-204 was calibrated on 2026-10-17 (CAL-3310, static test PASS); the dynamic slip test was deferred because the fixture was out for repair.', sources: ['d-cmms-cal-3310'] },
  { text: 'SOP-UP-014 Rev 7 §7.2 requires a dynamic slip verification at operating RPM after any occlusion adjustment before return to GMP service.', sources: ['sop-up-014'] },
];

export const SEARCH_GAPS = [
  'No Maximo record of a completed dynamic slip test for PM-204 after CAL-3310 was found.',
  'No source states whether the omitted slip test caused the MES-26073 droop. That is a hypothesis under INV-104, not an answer.',
  'Historian data for T+182.0–182.7h (42 min) is missing and is not searchable.',
];

const STOP = new Set(['after', 'the', 'of', 'for', 'and', 'in', 'on', 'to', 'a', 'an', 'with', 'by', 'from', 'is', 'are']);

export function tokenize(q: string) {
  return q.toLowerCase().split(/\s+/).map((t) => t.replace(/[^a-z0-9.\-§]/g, '')).filter((t) => t.length > 1 && !STOP.has(t));
}

export function scoreDoc(doc: KnowledgeDoc, tokens: string[], excerpt: string) {
  const hay = `${doc.title} ${doc.recordId} ${doc.keywords} ${doc.system} ${doc.equipment.join(' ')} ${excerpt}`.toLowerCase();
  return tokens.reduce((s, t) => {
    const stem = t.endsWith('s') ? t.slice(0, -1) : t;
    return s + (hay.includes(t) || hay.includes(stem) || hay.includes(stem.replace(/-/g, ' ')) ? 1 : 0);
  }, 0);
}
