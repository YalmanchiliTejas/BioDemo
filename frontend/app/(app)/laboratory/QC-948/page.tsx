'use client';

import { useMemo, useState } from 'react';
import { AlertTriangle, ArrowRight, Boxes, CheckCircle2, ClipboardCheck, Clock, FlaskConical, PenLine } from 'lucide-react';
import { Card, CardBody, CardHeader, ClaimTag, DemoBoundary, EvidenceChip, Hash, KeyValue, LinkButton, PageHeader, Pill, Segmented, SectionLabel, Stat, table, type Tone } from '@/components/ui';
import { Chromatogram, peakArea } from '@/components/screens/c/Chromatogram';
import { CITATIONS, MOCK_DATASET } from '@/fixtures/biomanufacturingData';
import { useAppContext } from '@/lib/app-context';
import { cn } from '@/lib/cn';

type Result = { test: string; method: string; result: string; unit: string; spec: string; status: { label: string; tone: Tone }; citation: string; note?: string };

const RESULTS: Result[] = [
  { test: 'Harvest titer (Protein A HPLC)', method: 'HPLC-PROA-01', result: '3.42', unit: 'g/L', spec: '> 3.80 (alert)', status: { label: 'OOT', tone: 'critical' }, citation: 'lims-qc-948' },
  { test: 'Viable cell density', method: 'VICELL-VCD-02', result: '14.8', unit: '×10⁶ cells/mL', spec: 'Report (trend 12–20)', status: { label: 'Within trend', tone: 'success' }, citation: 'c-lims-qc-948-panel' },
  { test: 'Viability', method: 'VICELL-VIAB-02', result: '86.1', unit: '%', spec: '≥ 80.0', status: { label: 'Pass', tone: 'success' }, citation: 'c-lims-qc-948-panel' },
  { test: 'Glucose', method: 'CEDEX-GLU-04', result: '1.9', unit: 'g/L', spec: '1.0 – 6.0', status: { label: 'Pass', tone: 'success' }, citation: 'c-lims-qc-948-panel', note: 'Lower third of range' },
  { test: 'Lactate', method: 'CEDEX-LAC-04', result: '2.6', unit: 'g/L', spec: '≤ 3.0', status: { label: 'Pass', tone: 'success' }, citation: 'c-lims-qc-948-panel' },
  { test: 'Ammonium', method: 'CEDEX-NH4-04', result: '6.9', unit: 'mmol/L', spec: '≤ 8.0', status: { label: 'Pass', tone: 'success' }, citation: 'c-lims-qc-948-panel' },
  { test: 'Osmolality', method: 'OSMO-03', result: '371', unit: 'mOsm/kg', spec: '280 – 380', status: { label: 'Alert', tone: 'warning' }, citation: 'c-lims-qc-948-panel', note: 'Within spec, near upper limit' },
  { test: 'SEC monomer', method: 'SEC-UPLC-05', result: '—', unit: '%', spec: '≥ 95.0', status: { label: 'Not started', tone: 'muted' }, citation: 'c-lims-qc-948-panel', note: 'Aggregation impact unknown' },
];

const PEAKS = [
  { t: 1.1, label: 'Flow-through' },
  { t: 3.62, label: 'Pre-peak' },
  { t: 4.25, label: 'IgG1 monomer', primary: true },
  { t: 5.05, label: 'Post-peak' },
];

const CUSTODY = [
  { at: '2026-10-19 06:12', who: 'T. Reed', what: 'Drawn at BR-UP-01 sample port SP-2', where: 'Suite 3B' },
  { at: '2026-10-19 06:31', who: 'J. Alvarez', what: 'Received at QC Lab 2 · 4.1 °C', where: 'QC Lab 2' },
  { at: '2026-10-19 07:05', who: 'J. Alvarez', what: 'Aliquoted ×4 (QC-948-A…D)', where: 'QC Lab 2' },
  { at: '2026-10-19 10:20', who: 'M. Okafor', what: 'Injected on ARC-HPLC-02', where: 'QC Lab 2' },
  { at: '2026-10-19 11:40', who: 'M. Okafor', what: 'Result entered · primary signature', where: 'LabWare LIMS' },
];

export default function LabSamplePage() {
  const { openInspector } = useAppContext();
  const [zoom, setZoom] = useState<'full' | 'main'>('full');
  const domain: [number, number] = zoom === 'full' ? [0, 8.4] : [3.4, 5.4];

  const peakTable = useMemo(() => {
    const rows = PEAKS.map((p) => ({ ...p, area: peakArea(p.t, p.primary ? 0.35 : 0.25) }));
    const total = rows.reduce((s, r) => s + r.area, 0);
    return rows.map((r) => ({ ...r, pct: (r.area / total) * 100 }));
  }, []);

  return (
    <div className="max-w-[1280px] mx-auto">
      <PageHeader
        frameId="LAB-01"
        crumbs={[{ label: 'Assure' }, { label: 'Laboratory' }, { label: 'QC-948' }]}
        title="Harvest sample · MES-26073 day 11"
        objectId="QC-948"
        status={<><Pill tone="critical" dot>OOT alert</Pill><Pill tone="warning">Sign-off 1 of 2</Pill></>}
        description="Sample-centric view of the LabWare LIMS result set RS-77120 and its Waters Arc HPLC raw data. Results and signatures remain in LIMS; nothing here changes them."
        meta={<><span>Result set RS-77120</span><span>Method HPLC-PROA-01 v4</span><DemoBoundary compact /></>}
        actions={
          <>
            <LinkButton href="/batches/MES-26073"><Boxes className="h-3.5 w-3.5" /> Inspect linked batch record</LinkButton>
            <LinkButton href="/quality/Q-DEV-031" variant="danger"><AlertTriangle className="h-3.5 w-3.5" /> Flag for OOT investigation</LinkButton>
            <LinkButton href="/reviews/REV-01" variant="primary"><ClipboardCheck className="h-3.5 w-3.5" /> Review assay record in approvals</LinkButton>
          </>
        }
      />

      <Card className="mb-4">
        <CardBody className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Stat label="Harvest titer" value="3.42" unit="g/L" delta="spec > 3.80" deltaTone="critical" kind="observation" hint={<EvidenceChip id="lims-qc-948" label="LIMS RS-77120" />} />
          <Stat label="Viable cell density" value="14.8" unit="×10⁶ cells/mL" kind="observation" hint="Within campaign trend" />
          <Stat label="Dual sign-off" value="1 of 2" hint="QA reviewer pending" />
          <Stat label="Titer gap to alert limit" value="−0.38" unit="g/L" deltaTone="critical" delta="−10.0%" kind="calculated" hint="(3.42 − 3.80) / 3.80" />
        </CardBody>
      </Card>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <div className="xl:col-span-2 space-y-4 min-w-0">
          <Card>
            <CardHeader
              title="Waters Arc HPLC · chromatogram"
              subtitle="Run ARC-2-26-1019-04 · injection 3 of 3 · 280 nm · no baseline correction"
              actions={<Segmented value={zoom} onChange={setZoom} options={[{ value: 'full', label: 'Full run' }, { value: 'main', label: 'Zoom main peak' }]} />}
            />
            <div className="px-3 pt-3"><Chromatogram domain={domain} peaks={PEAKS} /></div>
            <div className={cn(table.wrap, 'border-t border-border-hairline')}>
              <table className={table.root}>
                <thead>
                  <tr>
                    <th className={table.th}>Peak</th>
                    <th className={cn(table.th, 'text-right')}>RT (min)</th>
                    <th className={cn(table.th, 'text-right')}>Area (mAU·min)</th>
                    <th className={cn(table.th, 'text-right')}>% area</th>
                  </tr>
                </thead>
                <tbody>
                  {peakTable.map((p) => (
                    <tr key={p.t} className={table.tr}>
                      <td className={cn(table.td, p.primary && 'font-semibold')}>{p.label}</td>
                      <td className={cn(table.td, 'text-right font-mono')}>{p.t.toFixed(2)}</td>
                      <td className={cn(table.td, 'text-right')}>{p.area.toFixed(2)}</td>
                      <td className={cn(table.td, 'text-right')}>{p.pct.toFixed(1)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="flex flex-wrap items-center gap-2 px-4 py-2.5 border-t border-border-hairline bg-surface-secondary/40 text-[11.5px] text-text-tertiary">
              <ClaimTag kind="calculated" /> Areas re-integrated here (trapezoid, flat baseline 2 mAU) for orientation only; the reportable value is the LIMS result.
              <EvidenceChip id="c-hplc-arc-run" />
            </div>
          </Card>

          <Card>
            <CardHeader title="Test battery" subtitle="All tests on QC-948 from LIMS result set RS-77120" actions={<ClaimTag kind="observation" />} />
            <div className={table.wrap}>
              <table className={table.root}>
                <thead>
                  <tr>
                    <th className={table.th}>Test</th>
                    <th className={table.th}>Method</th>
                    <th className={cn(table.th, 'text-right')}>Result</th>
                    <th className={table.th}>Unit</th>
                    <th className={table.th}>Specification</th>
                    <th className={table.th}>Status</th>
                    <th className={table.th}>Source</th>
                  </tr>
                </thead>
                <tbody>
                  {RESULTS.map((r) => (
                    <tr key={r.method} className={table.tr}>
                      <td className={table.td}>
                        <span className="font-medium">{r.test}</span>
                        {r.note && <span className="block text-[11px] text-text-tertiary">{r.note}</span>}
                      </td>
                      <td className={cn(table.td, 'font-mono text-[11.5px] text-text-secondary')}>{r.method}</td>
                      <td className={cn(table.td, 'text-right font-semibold', r.status.tone === 'critical' && 'text-status-critical')}>{r.result}</td>
                      <td className={cn(table.td, 'text-text-tertiary text-[12px]')}>{r.unit}</td>
                      <td className={cn(table.td, 'text-[12px] text-text-secondary whitespace-nowrap')}>{r.spec}</td>
                      <td className={table.td}><Pill tone={r.status.tone} dot>{r.status.label}</Pill></td>
                      <td className={table.td}><EvidenceChip id={r.citation} label="LIMS" /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="px-4 py-2.5 text-[11.5px] text-text-tertiary border-t border-border-hairline">
              SEC monomer has not been run, so aggregate formation cannot be ruled in or out. Titer OOT is an alert-limit excursion pending review, not a confirmed failure.
            </p>
          </Card>
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader title="Dual-analyst sign-off" subtitle="1 of 2 complete · signatures held in LabWare LIMS" icon={<PenLine className="h-4 w-4" />} />
            <ul className="divide-y divide-border-hairline">
              <li className="px-4 py-3 flex items-start gap-2.5">
                <CheckCircle2 className="h-4 w-4 mt-0.5 text-status-success shrink-0" aria-hidden />
                <div className="min-w-0 flex-1">
                  <p className="text-[13px] font-medium">Primary analyst · M. Okafor</p>
                  <p className="text-[11.5px] text-text-tertiary">Signed 2026-10-19 11:40 UTC · meaning: “Performed”</p>
                </div>
                <Pill tone="success">Signed</Pill>
              </li>
              <li className="px-4 py-3 flex items-start gap-2.5">
                <Clock className="h-4 w-4 mt-0.5 text-status-warning shrink-0" aria-hidden />
                <div className="min-w-0 flex-1">
                  <p className="text-[13px] font-medium">QA reviewer · Priya Natarajan</p>
                  <p className="text-[11.5px] text-text-tertiary">Second-person review · waiting 5 d</p>
                </div>
                <Pill tone="warning">Pending</Pill>
              </li>
            </ul>
            <CardBody className="border-t border-border-hairline space-y-2">
              <LinkButton href="/reviews/REV-01" variant="primary" className="w-full justify-between">Review assay record in approvals <ArrowRight className="h-3.5 w-3.5" /></LinkButton>
              <p className="text-[11.5px] text-text-tertiary">The second signature is applied in LIMS. The review center prepares the evidence package only.</p>
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Sample" icon={<FlaskConical className="h-4 w-4" />} />
            <CardBody>
              <KeyValue cols={2} items={[
                ['Batch', <span key="b" className="font-mono">MES-26073</span>],
                ['Skid', 'BR-UP-01'],
                ['Sample point', 'SP-2 · day 11'],
                ['Molecule', 'AB-mAb-014'],
                ['Instrument', <span key="i" className="font-mono">ARC-HPLC-02</span>],
                ['Column lot', <span key="c" className="font-mono">CA-2231</span>],
              ]} />
              <div className="mt-3 space-y-1">
                <p className="text-[11px] text-text-tertiary">LIMS record hash</p>
                <Hash value={CITATIONS['lims-qc-948'].sha256Hash} />
              </div>
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="System suitability" actions={<ClaimTag kind="observation" />} />
            <CardBody className="space-y-1.5 text-[12.5px]">
              {[
                ['RT RSD', '0.21%', '≤ 1.0%'],
                ['Area RSD', '0.64%', '≤ 2.0%'],
                ['Ref std RS-IGG1-09 recovery', '99.1%', '95–105%'],
              ].map(([k, v, s]) => (
                <div key={k} className="flex items-center justify-between gap-2">
                  <span className="text-text-secondary">{k}</span>
                  <span className="flex items-center gap-2 tabular-nums"><span className="font-medium">{v}</span><span className="text-[11px] text-text-tertiary">{s}</span><Pill tone="success">Pass</Pill></span>
                </div>
              ))}
              <p className="pt-1 text-[11.5px] text-text-tertiary">Suitability passed, so an assay error is less likely, but it is not excluded until QA review.</p>
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Chain of custody" actions={<EvidenceChip id="c-lims-coc-qc-948" label="LIMS custody" />} />
            <ol className="px-4 py-3 space-y-2.5">
              {CUSTODY.map((c, i) => (
                <li key={i} className="flex gap-2.5 text-[12.5px]">
                  <span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-text-tertiary" aria-hidden />
                  <div className="min-w-0">
                    <p className="text-text-primary">{c.what}</p>
                    <p className="text-[11px] text-text-tertiary tabular-nums">{c.at} UTC · {c.who} · {c.where}</p>
                  </div>
                </li>
              ))}
            </ol>
            <div className="px-4 pb-3">
              <button type="button" className="text-[12px] text-brand-teal hover:underline" onClick={() => openInspector({ type: 'SAMPLE', id: 'QC-948', title: 'Harvest sample QC-948', citations: ['lims-qc-948', 'c-lims-coc-qc-948', 'c-hplc-arc-run'], metadata: { Batch: 'MES-26073', 'Hold time before injection': '4 h 08 min', 'Storage temp': '4.1 °C', Aliquots: 4 }, href: '/batches/MES-26073' })}>
                Open sample in inspector
              </button>
            </div>
          </Card>

          <Card>
            <CardHeader title="Context" />
            <CardBody className="space-y-2 text-[12.5px] text-text-secondary">
              <p><ClaimTag kind="observation" /> <span className="ml-1">Linked deviation Q-DEV-031 covers the PM-204 feed droop on the same batch.</span></p>
              <p className="text-[11.5px] text-text-tertiary">Campaign: {MOCK_DATASET.activeCampaign.id} · {MOCK_DATASET.activeCampaign.molecule}</p>
              <SectionLabel className="pt-1">Next steps</SectionLabel>
              <LinkButton href="/quality/Q-DEV-031" size="sm" className="w-full justify-between">Flag for OOT investigation <ArrowRight className="h-3 w-3" /></LinkButton>
              <LinkButton href="/batches/MES-26073" size="sm" className="w-full justify-between">Inspect linked batch record <ArrowRight className="h-3 w-3" /></LinkButton>
            </CardBody>
          </Card>
        </div>
      </div>
    </div>
  );
}
