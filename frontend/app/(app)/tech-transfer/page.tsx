'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { ArrowRight, Ban, GitCompareArrows } from 'lucide-react';
import { Callout, Card, CardBody, CardHeader, ClaimTag, DemoBoundary, EvidenceChip, LinkButton, PageHeader, Pill, Stat, table, type ClaimKind, type Tone } from '@/components/ui';
import { GATE_NAMES, GateRoadmap, type GateState } from '@/components/screens/c/GateRoadmap';
import { MOCK_DATASET } from '@/fixtures/biomanufacturingData';
import { useAppContext } from '@/lib/app-context';
import { cn } from '@/lib/cn';
import { FermentationTransfer } from '@/components/process/FermentationTransfer';

type Project = {
  id: string;
  molecule: string;
  donor: string;
  recipient: string;
  gates: GateState[];
  current: string;
  lead: string;
  nextMilestone: string;
  status: { label: string; tone: Tone };
  href?: string;
};

const PROJECTS: Project[] = [
  { id: 'TT-006', molecule: 'AB-mAb-014', donor: 'Mesa 500L single-use', recipient: 'Durham 2000L stainless', gates: ['done', 'done', 'blocked', 'pending', 'pending'], current: 'Gate 2 · blocked', lead: 'Alex Rivera', nextMilestone: 'PID constants from Durham Automation · due 2026-11-06', status: { label: 'Gate 2 blocker', tone: 'critical' }, href: '/tech-transfer/TT-006' },
  { id: 'TT-004', molecule: 'AB-mAb-009', donor: 'Mesa 2000L stainless', recipient: 'Basel 2000L single-use', gates: ['done', 'done', 'done', 'active', 'pending'], current: 'Gate 3 · engineering run', lead: 'S. Hoffmann', nextMilestone: 'Engineering run ER-04 starts 2026-11-02', status: { label: 'On plan', tone: 'success' } },
  { id: 'TT-005', molecule: 'AB-bsAb-021', donor: 'Durham 200L single-use', recipient: 'Mesa 500L single-use', gates: ['done', 'active', 'pending', 'pending', 'pending'], current: 'Gate 1 · analytics transfer', lead: 'K. Osei', nextMilestone: 'Method transfer protocol MTP-021 approval', status: { label: 'At risk', tone: 'warning' } },
  { id: 'TT-003', molecule: 'AB-mAb-007', donor: 'Mesa downstream (UF-DF-02)', recipient: 'Durham downstream', gates: ['done', 'done', 'done', 'done', 'active'], current: 'Gate 4 · PPQ readiness', lead: 'D. Kim', nextMilestone: 'PPQ protocol QA review', status: { label: 'On plan', tone: 'success' } },
];

type EqRow = { aspect: string; mesa: string; durham: string; status: 'match' | 'scaled' | 'gap' | 'unknown'; kind: ClaimKind };
const EQUIV: EqRow[] = [
  { aspect: 'Aspect ratio (H/D)', mesa: '1.5 : 1', durham: '2.0 : 1', status: 'scaled', kind: 'observation' },
  { aspect: 'Impeller type', mesa: '1 × pitched-blade 45°, D/T 0.33', durham: 'Rushton (lower) + pitched-blade (upper), D/T 0.35', status: 'gap', kind: 'observation' },
  { aspect: 'Sparger', mesa: 'Drilled-hole 1 mm + open pipe', durham: 'Ring sparger 2 mm', status: 'gap', kind: 'observation' },
  { aspect: 'Power per volume (P/V)', mesa: '42.8 W/m³ (measured)', durham: 'Unknown · not characterised', status: 'unknown', kind: 'unknown' },
  { aspect: 'kLa (air, 0.05 vvm)', mesa: '8.4 h⁻¹', durham: 'Unknown · ENG-RPT-0447 not issued', status: 'unknown', kind: 'unknown' },
  { aspect: 'Control system', mesa: 'DeltaV v14 · gravimetric feed cascade', durham: 'DeltaV v13 · flow-only feed loop', status: 'gap', kind: 'observation' },
];

const EQ_TONE: Record<EqRow['status'], { tone: Tone; label: string }> = {
  match: { tone: 'success', label: 'Match' },
  scaled: { tone: 'info', label: 'Scaled' },
  gap: { tone: 'warning', label: 'Gap' },
  unknown: { tone: 'muted', label: 'Unknown' },
};

export default function TechTransferPortfolio() {
  const router = useRouter();
  const { openInspector } = useAppContext();
  const [selected, setSelected] = useState('TT-006');
  const tb = MOCK_DATASET.techTransferBlocker;

  return (
    <div className="max-w-[1280px] mx-auto">
      <PageHeader
        frameId="TRANSFER-01"
        crumbs={[{ label: 'Improve' }, { label: 'Tech transfer' }]}
        title="Tech transfer portfolio"
        status={<Pill tone="info">4 active projects</Pill>}
        description="Projects moving processes between Mesa, Durham and Basel. Gate status reflects the transfer team’s stage-gate records; this view assembles them and flags blockers."
        meta={<><span>Gate records from Documentum</span><DemoBoundary compact /></>}
        actions={<LinkButton href="/tech-transfer/TT-006" variant="primary"><GitCompareArrows className="h-3.5 w-3.5" /> Open comparative workspace</LinkButton>}
      />

      <FermentationTransfer />

      <Callout
        tone="critical"
        icon={<Ban className="h-4 w-4" />}
        title={<span>TT-006 · Gate 2 blocker — bioreactor feed control loop</span>}
        action={<LinkButton href="/tech-transfer/TT-006" size="sm">Open TT-006 <ArrowRight className="h-3 w-3" /></LinkButton>}
        className="mb-4"
      >
        {tb.blockerReason}. Durham’s feed loop runs flow-only; Mesa relies on a gravimetric cascade. Gate 2 ({tb.gate}) cannot clear until the constants are supplied and reviewed by MSAT. <EvidenceChip id="c-tt-006-gate2" />
      </Callout>

      <Card className="mb-4">
        <CardBody className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Stat label="Active projects" value={PROJECTS.length} />
          <Stat label="Blocked gates" value={1} hint="TT-006 Gate 2" deltaTone="critical" />
          <Stat label="At risk" value={1} hint="TT-005 method transfer" />
          <Stat label="Gate reviews next 14 d" value={2} hint="TT-004 G3 · TT-003 G4" />
        </CardBody>
      </Card>

      <Card className="mb-4">
        <CardHeader title="Project ledger" subtitle={`Gates: ${GATE_NAMES.join(' → ')}`} />
        <div className={table.wrap}>
          <table className={table.root}>
            <thead>
              <tr>
                <th className={table.th}>Project</th>
                <th className={table.th}>Route</th>
                <th className={table.th}>Gates 0–4</th>
                <th className={table.th}>Current</th>
                <th className={table.th}>Next milestone</th>
                <th className={table.th}>Lead</th>
                <th className={table.th}>Status</th>
              </tr>
            </thead>
            <tbody>
              {PROJECTS.map((p) => (
                <tr
                  key={p.id}
                  className={cn(table.tr, 'cursor-pointer', selected === p.id && 'bg-brand-teal-light/40')}
                  onClick={() => {
                    setSelected(p.id);
                    if (p.href) router.push(p.href);
                    else openInspector({ type: 'PROJECT', id: p.id, title: `${p.molecule} · ${p.donor} → ${p.recipient}`, metadata: { Current: p.current, Lead: p.lead, 'Next milestone': p.nextMilestone, Status: p.status.label, Workspace: 'Not available in demo' } });
                  }}
                >
                  <td className={table.td}>
                    {p.href ? <Link href={p.href} onClick={(e) => e.stopPropagation()} className="font-mono text-[12px] text-brand-teal hover:underline">{p.id}</Link> : <span className="font-mono text-[12px]">{p.id}</span>}
                    <span className="block text-[11.5px] text-text-tertiary">{p.molecule}</span>
                  </td>
                  <td className={cn(table.td, 'text-[12px]')}>
                    <span className="text-text-secondary">{p.donor}</span>
                    <span className="block text-text-primary">→ {p.recipient}</span>
                  </td>
                  <td className={table.td}><GateRoadmap gates={p.gates} /></td>
                  <td className={cn(table.td, 'text-[12px] whitespace-nowrap')}>{p.current}</td>
                  <td className={cn(table.td, 'text-[12px] text-text-secondary max-w-[240px]')}>{p.nextMilestone}</td>
                  <td className={cn(table.td, 'text-[12px] whitespace-nowrap')}>{p.lead}</td>
                  <td className={table.td}><Pill tone={p.status.tone} dot>{p.status.label}</Pill></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="px-4 py-2.5 text-[11.5px] text-text-tertiary border-t border-border-hairline">
          No readiness percentages are shown: gate clearance is a QA/MSAT decision recorded in the stage-gate system. Only TT-006 has a comparative workspace in this demo.
        </p>
      </Card>

      <Card>
        <CardHeader
          title="Cross-site equipment equivalency · TT-006"
          subtitle="Mesa 500L single-use vs Durham 2000L stainless. Values from equipment specifications; blanks are shown as unknown, not estimated."
          actions={<LinkButton href="/tech-transfer/TT-006" size="sm">Full comparison <ArrowRight className="h-3 w-3" /></LinkButton>}
        />
        <div className={table.wrap}>
          <table className={table.root}>
            <thead>
              <tr>
                <th className={table.th}>Aspect</th>
                <th className={table.th}>Mesa 500L SUB (donor)</th>
                <th className={table.th}>Durham 2000L stainless (recipient)</th>
                <th className={table.th}>Comparability</th>
                <th className={table.th}>Claim</th>
              </tr>
            </thead>
            <tbody>
              {EQUIV.map((r) => (
                <tr key={r.aspect} className={table.tr}>
                  <td className={cn(table.td, 'font-medium')}>{r.aspect}</td>
                  <td className={cn(table.td, 'text-[12.5px]')}>{r.mesa}</td>
                  <td className={cn(table.td, 'text-[12.5px]', r.status === 'unknown' && 'text-text-tertiary italic')}>{r.durham}</td>
                  <td className={table.td}><Pill tone={EQ_TONE[r.status].tone} dot>{EQ_TONE[r.status].label}</Pill></td>
                  <td className={table.td}><ClaimTag kind={r.kind} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="flex flex-wrap items-center gap-2 px-4 py-2.5 border-t border-border-hairline bg-surface-secondary/40 text-[11.5px] text-text-tertiary">
          Sources: <EvidenceChip id="c-mesa-sub-spec" /> <EvidenceChip id="c-durham-ss-spec" />
          <span>Durham spec is Rev 1 (2023) and may be stale.</span>
        </div>
      </Card>
    </div>
  );
}
