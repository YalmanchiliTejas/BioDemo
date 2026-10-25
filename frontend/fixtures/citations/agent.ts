import type { Citation } from '../biomanufacturingData';

/** Synthetic citations used by agent task outputs. Keys must be unique across all citation files. */
export const CITATIONS_AGENT: Record<string, Citation> = {
  'ag-mesa-feed-loop': {
    id: 'ag-mesa-feed-loop',
    sourceSystem: 'DeltaV eBR',
    documentName: 'DeltaV module export · Mesa BR-UP-01 feed loop',
    sectionOrClause: 'WIC-1105 / FIC-1105 cascade',
    rawExcerpt:
      'MODULE=WIC-1105 MODE=CAS OUTER=WEIGHT KC=1.85 TI=240s TD=0\nMODULE=FIC-1105 MODE=CAS INNER=FLOW KC=0.62 TI=18s TD=0 OUT=PM-204.SPEED\nEXPORTED=2026-10-18T09:12Z VERSION=DeltaV v14.3',
    sha256Hash: '5563a988329c097c077af0506da82f36e99d97815333f078e517c6c2b84f3201',
    timestamp: '2026-10-18 09:12 UTC',
    provenanceConfidence: 99.1,
    transformation: 'Read-only configuration export; values copied verbatim.',
  },
  'ag-param-map': {
    id: 'ag-param-map',
    sourceSystem: 'Manufacturing OS (derived)',
    documentName: 'TT-006 parameter map · RCP-AB014-V4 → BR-D-2000',
    sectionOrClause: 'Mapping summary',
    rawExcerpt:
      'parameters_in_scope=86 (UP01 PH01–PH07)\nmapped_direct=79 scaled_by_volume=4 (factor 4.00) unmapped=3\nunmapped: FEED_OUTER_KC, FEED_OUTER_TI, FEED_CTRL_STRUCTURE (reason: recipient loop FIC-2201 flow-only)',
    sha256Hash: '2500a8597de8a573467c12abd8d6d9d833694f2b28f293ea51f60ff0aac3fdda',
    timestamp: 'Computed by agent task TASK-2026-1051',
    provenanceConfidence: 97.5,
    transformation: 'Rule-based mapping (param-mapper v0.9.1) over RCP-AB014-V4 and EQ-SPEC-DUR-SS2000 Rev 1. Recipient spec may be stale.',
  },
  'ag-calc-imc': {
    id: 'ag-calc-imc',
    sourceSystem: 'Manufacturing OS (derived)',
    documentName: 'Candidate FIC-2201 tuning · IMC rules',
    sectionOrClause: 'Derivation',
    rawExcerpt:
      'inputs: FIC-1105 KC=0.62 TI=18s; pump dead time ratio Durham/Mesa=1.22 (from line length, spec §5)\nIMC lambda=2.0*theta -> KC=0.71 TI=22s\nouter weight loop unavailable -> mass-balance trim every 15 min (dosing totaliser vs load cell)',
    sha256Hash: '4e1e6da62ebc2660c56dc2dc2fe7b40621cab41ced95b7cea502d9d57c35eb4a',
    timestamp: 'Computed by agent task TASK-2026-1051',
    provenanceConfidence: 95.0,
    transformation: 'Engineering estimate. Not tested on Durham hardware; requires a bump test before use.',
  },
  'ag-lims-qc948-signoff': {
    id: 'ag-lims-qc948-signoff',
    sourceSystem: 'LabWare LIMS',
    documentName: 'Sample QC-948 · HPLC-PROA-01 signature block',
    sectionOrClause: 'Result review',
    rawExcerpt:
      'SAMPLE=QC-948 TEST=HPLC-PROA-01 RESULT=3.42 g/L\nREVIEW_1=M.Okafor SIGNED 2026-10-19T10:02Z\nREVIEW_2=PENDING (QA reviewer)',
    sha256Hash: 'b2a3620d44f92dd40e815522c42c3eb71242a9d8eed37ea6845d79ca47441af1',
    timestamp: '2026-10-19 10:02 UTC',
    provenanceConfidence: 99.4,
  },
  'ag-calc-schedule': {
    id: 'ag-calc-schedule',
    sourceSystem: 'Manufacturing OS (derived)',
    documentName: 'Suite 3B schedule solve · 26 Oct',
    sectionOrClause: 'Constraint solver output',
    rawExcerpt:
      'conflict: PM-SAN-204 06:00–14:00 vs MES-26074 PH02 09:30 (overlap 4.5h)\nA: shift MES-26074 PH02 +4.5h -> harvest D14 slack 18h, vialing slot unchanged\nB: assign PM-205 -> requires CIP 3.0h, PM-205 OQ overdue 17d\nseed-train hold limit: NOT FOUND in connected sources',
    sha256Hash: '181bf4dc46995dae8cb485a9123780459fcf83b06d8a84e22996e4ffb7e13f5e',
    timestamp: 'Computed by agent task TASK-2026-1053',
    provenanceConfidence: 96.0,
    transformation: 'constraint-solver v0.8.3 over the Maximo PM schedule and MES planning extract. Labor and cost excluded (SAP ERP not connected).',
  },
  'ag-calc-compensation': {
    id: 'ag-calc-compensation',
    sourceSystem: 'Manufacturing OS (derived)',
    documentName: 'Modelled feed compensation · MES-26073',
    sectionOrClause: 'T+240–280h',
    rawExcerpt:
      'model: compensated = observed + 0.9 * droop_est(h)\ndroop_est = 2.4 mL/min * logistic((h - 264.4) * 1.4)\nassumption: mass-balance trim recovers 90% of post-spike shortfall',
    sha256Hash: 'be93d2b7417355a880155abd746347d9dd4fded6173a2652a712c523cb9bf947',
    timestamp: 'Computed by agent task TASK-2026-1042',
    provenanceConfidence: 94.0,
    transformation: 'Simulation only. Not an observed value and not a validated control change.',
  },
};
