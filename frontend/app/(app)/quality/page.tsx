'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { ArrowRight, Lock, ShieldAlert } from 'lucide-react';
import { Card, CardBody, CardHeader, ClaimTag, DemoBoundary, EvidenceChip, LinkButton, PageHeader, Pill, ProgressBar, Segmented, SectionLabel, Stat, StatusDot, table, type Tone } from '@/components/ui';
import { MOCK_DATASET } from '@/fixtures/biomanufacturingData';
import { useAppContext } from '@/lib/app-context';
import { cn } from '@/lib/cn';

type ExType = 'Deviation' | 'OOT' | 'Change control' | 'Planning gap';
type Exception = {
  id: string;
  type: ExType;
  title: string;
  severity: { label: string; tone: Tone };
  owner: string;
  age: string;
  system: string;
  status: string;
  href?: string;
  citation?: string;
};

const EXCEPTIONS: Exception[] = [
  { id: 'Q-DEV-031', type: 'Deviation', title: 'BR-UP-01 feed droop −14.2% and PM-204 head-pressure exceedance (1.48 bar)', severity: { label: 'Major · Tier 2', tone: 'critical' }, owner: 'Priya Natarajan (QA)', age: '8 h', system: 'Veeva Vault QMS', status: 'Root-cause investigation', href: '/quality/Q-DEV-031', citation: 'qms-q-dev-031' },
  { id: 'QC-948', type: 'OOT', title: 'Harvest titer 3.42 g/L vs alert limit >3.80 g/L', severity: { label: 'OOT alert', tone: 'warning' }, owner: 'M. Okafor (QC)', age: '5 h', system: 'LabWare LIMS', status: 'Second-person review pending', href: '/laboratory/QC-948', citation: 'lims-qc-948' },
  { id: 'Q-DEV-030', type: 'Deviation', title: 'Label reconciliation discrepancy, harvest bags MES-26072 (2 of 48)', severity: { label: 'Minor · Tier 3', tone: 'neutral' }, owner: 'D. Kim (QA)', age: '4 d', system: 'Veeva Vault QMS', status: 'CAPA effectiveness check' },
  { id: 'Q-DEV-029', type: 'Deviation', title: 'CIP final-rinse conductivity alarm on UF-DF-02 (cleared on re-rinse)', severity: { label: 'Minor · Tier 3', tone: 'neutral' }, owner: 'D. Kim (QA)', age: '7 d', system: 'Veeva Vault QMS', status: 'Pending closure' },
  { id: 'CC-017', type: 'Change control', title: 'PM-204 pump-head tubing part change (PharMed BPT → Pt-cured silicone)', severity: { label: 'Moderate', tone: 'warning' }, owner: 'R. Chen (Engineering)', age: '11 d', system: 'Veeva Vault QMS', status: 'Impact assessment', citation: 'c-qms-cc-017' },
  { id: 'GAP-PLAN-06', type: 'Planning gap', title: 'PM-204 sanitization overlaps MES-26074 inoculation by 4.5 h', severity: { label: 'Schedule risk', tone: 'warning' }, owner: 'Marcus Bell (Supervisor)', age: '1 d', system: 'Maximo CMMS (PM) · MES plan', status: 'Two scenarios drafted, none applied', href: '/planning', citation: 'c-maximo-cip-sched' },
];

const FILTERS: Array<{ value: 'all' | ExType; label: string }> = [
  { value: 'all', label: 'All' },
  { value: 'Deviation', label: 'Deviations' },
  { value: 'OOT', label: 'OOT' },
  { value: 'Change control', label: 'Change control' },
  { value: 'Planning gap', label: 'Planning' },
];

const SYNC: Array<{ name: string; tone: Tone; detail: string }> = [
  { name: 'Veeva Vault QMS', tone: 'success', detail: 'Read-only · synced 11 min ago' },
  { name: 'LabWare LIMS', tone: 'success', detail: 'Read-only · synced 6 min ago' },
  { name: 'DeltaV eBR', tone: 'success', detail: 'Read-only · synced 2 min ago' },
  { name: 'SAP ERP (batch disposition)', tone: 'neutral', detail: 'Not connected · release status not verified against ERP' },
];

export default function QualityPage() {
  const router = useRouter();
  const { openInspector } = useAppContext();
  const [filter, setFilter] = useState<'all' | ExType>('all');
  const rows = useMemo(() => EXCEPTIONS.filter((e) => filter === 'all' || e.type === filter), [filter]);
  const batches = MOCK_DATASET.activeCampaign.batches;
  const released = batches.filter((b) => b.release === 'RELEASED').length;
  const openDeviations = EXCEPTIONS.filter((e) => e.type === 'Deviation').length;

  const openRow = (e: Exception) => {
    if (e.href) router.push(e.href);
    else openInspector({ type: 'RECORD', id: e.id, title: e.title, metadata: { Type: e.type, Severity: e.severity.label, Owner: e.owner, Status: e.status, 'System of record': e.system }, citations: e.citation ? [e.citation] : undefined });
  };

  return (
    <div className="max-w-[1280px] mx-auto">
      <PageHeader
        frameId="QUAL-01"
        crumbs={[{ label: 'Assure' }, { label: 'Quality' }, { label: 'Exceptions & release' }]}
        title="Quality exceptions & release"
        objectId="CMP-26-10"
        status={<Pill tone="critical" dot>GxP hold active</Pill>}
        description="Deviations, out-of-trend results, change controls and planning gaps across the active campaign. Records stay in Veeva Vault QMS and LabWare LIMS; this view reads them and links back."
        meta={<><span>Data as of 16:40 UTC</span><DemoBoundary compact /></>}
        actions={
          <>
            <LinkButton href="/laboratory/QC-948">Review QC-948</LinkButton>
            <LinkButton href="/quality/Q-DEV-031" variant="primary">Open Q-DEV-031 <ArrowRight className="h-3.5 w-3.5" /></LinkButton>
          </>
        }
      />

      <Card className="mb-4">
        <CardBody className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Stat label="Open deviations" value={openDeviations} hint="1 major · 2 minor" kind="observation" />
          <div className="min-w-0">
            <p className="text-[11px] font-medium uppercase tracking-wide text-text-tertiary">GxP release hold</p>
            <p className="mt-1 flex flex-wrap items-center gap-1.5">
              <Pill tone="critical" dot>ACTIVE</Pill>
              <span className="text-[13px] font-medium">Lot <span className="font-mono">MES-26073</span></span>
            </p>
            <p className="mt-1"><EvidenceChip id="c-qms-hold-26073" label="QMS hold record" /></p>
          </div>
          <div className="min-w-0">
            <Stat label="Campaign batches released" value={`${released} of ${batches.length}`} hint={`${((released / batches.length) * 100).toFixed(1)}% · MES-26073 on hold`} kind="calculated" />
            <ProgressBar className="mt-1.5" value={released} max={batches.length} tone="warning" label="Batches released" />
          </div>
          <Stat label="Out-of-trend results" value={1} hint="QC-948 · review 1 of 2 complete" kind="observation" />
        </CardBody>
      </Card>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <div className="xl:col-span-2 space-y-4 min-w-0">
          <Card>
            <CardHeader
              title="Exception queue"
              subtitle={`${rows.length} of ${EXCEPTIONS.length} open items · sorted by severity, then age`}
              actions={<Segmented value={filter} onChange={setFilter} options={FILTERS} />}
            />
            <div className={table.wrap}>
              <table className={table.root}>
                <thead>
                  <tr>
                    <th className={table.th}>Record</th>
                    <th className={table.th}>Type</th>
                    <th className={table.th}>Severity</th>
                    <th className={table.th}>Owner</th>
                    <th className={cn(table.th, 'text-right')}>Age</th>
                    <th className={table.th}>System of record</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((e) => (
                    <tr key={e.id} className={cn(table.tr, 'cursor-pointer')} onClick={() => openRow(e)}>
                      <td className={cn(table.td, 'max-w-[340px]')}>
                        {e.href ? (
                          <Link href={e.href} onClick={(ev) => ev.stopPropagation()} className="font-mono text-[12px] text-brand-teal hover:underline">{e.id}</Link>
                        ) : (
                          <button type="button" className="font-mono text-[12px] text-text-primary hover:text-brand-teal" onClick={(ev) => { ev.stopPropagation(); openRow(e); }}>{e.id}</button>
                        )}
                        <p className="text-[12px] text-text-secondary leading-snug mt-0.5">{e.title}</p>
                        <p className="text-[11px] text-text-tertiary mt-0.5">{e.status}</p>
                      </td>
                      <td className={cn(table.td, 'whitespace-nowrap')}>{e.type}</td>
                      <td className={table.td}><Pill tone={e.severity.tone} dot>{e.severity.label}</Pill></td>
                      <td className={cn(table.td, 'text-[12px] whitespace-nowrap')}>{e.owner}</td>
                      <td className={cn(table.td, 'text-right text-text-secondary')}>{e.age}</td>
                      <td className={cn(table.td, 'text-[12px] text-text-secondary')}>
                        <span className="flex items-center gap-1.5 whitespace-nowrap"><Lock className="h-3 w-3 text-text-muted" aria-hidden />{e.system}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="px-4 py-2.5 text-[11.5px] text-text-tertiary border-t border-border-hairline">
              Severity and status are read from the system of record, not assigned by this app. Rows without a detail screen open a read-only summary in the inspector.
            </p>
          </Card>

          <Card>
            <CardHeader
              title={<span className="flex items-center gap-2"><ShieldAlert className="h-4 w-4 text-status-critical" aria-hidden /> Active GxP holds</span>}
              subtitle="Lot → hold reasons → linked records. Release requires deviation closure and QA disposition in Veeva."
              actions={<ClaimTag kind="observation" />}
            />
            <CardBody>
              <HoldTree />
            </CardBody>
          </Card>
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader title="Source sync" subtitle="Systems of record remain authoritative" />
            <ul className="divide-y divide-border-hairline">
              {SYNC.map((s) => (
                <li key={s.name} className="px-4 py-2.5 flex items-start gap-2.5">
                  <span className="mt-1.5"><StatusDot tone={s.tone} /></span>
                  <div className="min-w-0">
                    <p className="text-[13px] font-medium text-text-primary">{s.name}</p>
                    <p className="text-[11.5px] text-text-tertiary">{s.detail}</p>
                  </div>
                </li>
              ))}
            </ul>
            <p className="px-4 py-2.5 text-[11.5px] text-text-tertiary border-t border-border-hairline">No writeback is configured. Drafts created here are handed off to QMS owners for entry.</p>
          </Card>

          <Card>
            <CardHeader title="Campaign release status" subtitle={MOCK_DATASET.activeCampaign.molecule} />
            <ul className="divide-y divide-border-hairline">
              {batches.map((b) => (
                <li key={b.id} className="px-4 py-2.5 flex items-center justify-between gap-2">
                  <Link href={b.id === 'MES-26073' ? '/batches/MES-26073' : '/workbench/AN-104'} className="font-mono text-[12.5px] hover:text-brand-teal">{b.id}</Link>
                  <Pill tone={b.release === 'RELEASED' ? 'success' : 'critical'} dot>{b.release === 'RELEASED' ? 'Released' : 'Hold active'}</Pill>
                </li>
              ))}
            </ul>
            <p className="px-4 py-2.5 text-[11.5px] text-text-tertiary border-t border-border-hairline">Release status from Veeva QMS disposition. ERP not connected, so shipment status is unknown.</p>
          </Card>

          <Card>
            <CardHeader title="Next steps" />
            <CardBody className="space-y-2">
              <LinkButton href="/quality/Q-DEV-031" className="w-full justify-between">Continue Q-DEV-031 investigation <ArrowRight className="h-3.5 w-3.5" /></LinkButton>
              <LinkButton href="/laboratory/QC-948" className="w-full justify-between">Second-person review · QC-948 <ArrowRight className="h-3.5 w-3.5" /></LinkButton>
              <LinkButton href="/planning" className="w-full justify-between">Resolve GAP-PLAN-06 <ArrowRight className="h-3.5 w-3.5" /></LinkButton>
            </CardBody>
          </Card>
        </div>
      </div>
    </div>
  );
}

function HoldTree() {
  const { openInspector } = useAppContext();
  const reasons = [
    {
      id: 'Q-DEV-031',
      label: 'Deviation Q-DEV-031 open (Major · Tier 2)',
      href: '/quality/Q-DEV-031',
      linked: [
        { id: 'WO-8819', label: 'Work order WO-8819 · clamp torque change at T-48h', citation: 'cmms-wo-8819' },
        { id: 'SOP-UP-014', label: 'SOP-UP-014 Rev 7 §7.2 · slip verification', citation: 'sop-up-014' },
        { id: 'eBR-05.4', label: 'eBR MES-26073 step 05.4 · feed −14.3%', citation: 'ebr-mes-26073' },
      ],
    },
    {
      id: 'QC-948',
      label: 'OOT titer QC-948 · second-person review pending',
      href: '/laboratory/QC-948',
      linked: [
        { id: 'RS-77120', label: 'LIMS result set RS-77120 · titer 3.42 g/L', citation: 'lims-qc-948' },
        { id: 'ARC-2-26-1019-04', label: 'Waters Arc run ARC-2-26-1019-04', citation: 'c-hplc-arc-run' },
      ],
    },
  ];
  return (
    <div className="text-[12.5px]">
      <div className="inline-flex items-center gap-2 rounded-control border border-red-200 bg-status-critical-bg px-2.5 py-1.5">
        <SectionLabel className="!text-red-700">Lot</SectionLabel>
        <Link href="/batches/MES-26073" className="font-mono font-semibold text-red-800 hover:underline">MES-26073</Link>
        <span className="text-red-700">QA hold since 2026-10-19 09:05 UTC</span>
      </div>
      <ul className="mt-2 ml-4 border-l border-border-strong space-y-3 pt-1">
        {reasons.map((r) => (
          <li key={r.id} className="relative pl-5">
            <span className="absolute left-0 top-3 w-4 h-px bg-border-strong" aria-hidden />
            <div className="inline-flex flex-wrap items-center gap-2 rounded-control border border-amber-200 bg-status-warning-bg px-2.5 py-1">
              <span className="text-[10px] font-semibold uppercase tracking-wide text-amber-700">Hold reason</span>
              <Link href={r.href} className="font-medium text-amber-900 hover:underline">{r.label}</Link>
            </div>
            <ul className="mt-1.5 ml-4 border-l border-border-hairline space-y-1">
              {r.linked.map((l) => (
                <li key={l.id} className="relative pl-5 flex flex-wrap items-center gap-2">
                  <span className="absolute left-0 top-2.5 w-4 h-px bg-border-hairline" aria-hidden />
                  <button type="button" onClick={() => openInspector({ type: 'RECORD', id: l.id, title: l.label, citations: [l.citation] })} className="text-text-secondary hover:text-brand-teal text-left">{l.label}</button>
                  <EvidenceChip id={l.citation} />
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
    </div>
  );
}
