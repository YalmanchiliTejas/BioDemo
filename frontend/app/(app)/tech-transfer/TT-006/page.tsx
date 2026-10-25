'use client';

import { useState } from 'react';
import { Bot, ChevronDown, ChevronRight, FileText, Gauge, MessageSquareWarning } from 'lucide-react';
import { Button, Callout, Card, CardBody, CardHeader, ClaimTag, DemoBoundary, EvidenceChip, LinkButton, PageHeader, Pill, SectionLabel, Stat, table, type ClaimKind, type Tone } from '@/components/ui';
import { BioreactorSchematic } from '@/components/screens/c/BioreactorSchematic';
import { GateRoadmap } from '@/components/screens/c/GateRoadmap';
import { MOCK_DATASET } from '@/fixtures/biomanufacturingData';
import { useAppContext } from '@/lib/app-context';
import { cn } from '@/lib/cn';
import { AgentCanvasSlot } from '@/components/agent/AgentCanvasSlot';

type Comp = 'match' | 'scaled' | 'gap' | 'unknown';
const COMP: Record<Comp, { tone: Tone; label: string }> = {
  match: { tone: 'success', label: 'Match' },
  scaled: { tone: 'info', label: 'Scaled' },
  gap: { tone: 'warning', label: 'Gap' },
  unknown: { tone: 'muted', label: 'Unknown' },
};

const PARAMS: Array<{ p: string; mesa: string; durham: string; status: Comp; kind: ClaimKind; note: string; cite?: string }> = [
  { p: 'Working volume', mesa: '500 L', durham: '2000 L', status: 'scaled', kind: 'calculated', note: 'Scale factor 1:4.00', cite: 'c-durham-ss-spec' },
  { p: 'Aspect ratio H/D', mesa: '1.5', durham: '2.0', status: 'gap', kind: 'observation', note: 'Taller vessel: longer mixing time and higher hydrostatic head at sparger', cite: 'c-durham-ss-spec' },
  { p: 'Impeller', mesa: '1 × PBT 45°, D/T 0.33', durham: 'Rushton + PBT, D/T 0.35', status: 'gap', kind: 'observation', note: 'Different power number; Rushton adds radial shear', cite: 'c-mesa-sub-spec' },
  { p: 'Tip speed', mesa: '1.38 m/s @ 160 rpm', durham: 'Not set', status: 'unknown', kind: 'unknown', note: 'Depends on Durham agitation setpoint, not yet chosen' },
  { p: 'Power per volume P/V', mesa: '42.8 W/m³ (measured)', durham: '42.8 W/m³ (design basis)', status: 'scaled', kind: 'calculated', note: 'Constant-P/V basis is a target; Durham value not measured', cite: 'c-mesa-sub-spec' },
  { p: 'kLa (air)', mesa: '8.4 h⁻¹', durham: 'Unknown', status: 'unknown', kind: 'unknown', note: 'Characterisation report ENG-RPT-0447 not issued', cite: 'c-durham-ss-spec' },
  { p: 'Aeration (VVM)', mesa: '0.05 vvm', durham: '0.05 vvm (planned)', status: 'match', kind: 'observation', note: 'Same VVM; different sparger bubble size' },
  { p: 'Feed control loop', mesa: 'Gravimetric cascade (DeltaV v14)', durham: 'Flow-only FIC-2201 (DeltaV v13) · PID constants unmapped', status: 'gap', kind: 'observation', note: 'Gate 2 blocker', cite: 'c-tt-006-gate2' },
];

type Check = { item: string; owner: string; status: 'Done' | 'In progress' | 'Blocked' | 'Not started'; cite?: string };
const CHECKLIST: Check[] = [
  { item: 'Process description & CPP list transferred', owner: 'Alex Rivera · MSAT', status: 'Done' },
  { item: 'Analytical methods transferred (titer, VCD)', owner: 'K. Osei · QC Durham', status: 'Done' },
  { item: 'Equipment equivalency assessment', owner: 'R. Chen · Engineering', status: 'In progress', cite: 'c-durham-ss-spec' },
  { item: 'Feed-loop PID cascade constants mapped (FIC-2201)', owner: 'K. Osei · Durham Automation', status: 'Blocked', cite: 'c-tt-006-gate2' },
  { item: 'kLa characterisation at 2000 L (ENG-RPT-0447)', owner: 'Durham Engineering', status: 'Not started' },
  { item: 'Recipe translation RCP-AB014 → Durham DeltaV v13', owner: 'Alex Rivera · MSAT', status: 'Not started' },
  { item: 'Transfer risk assessment (FMEA)', owner: 'D. Kim · QA', status: 'In progress' },
  { item: 'Gate 2 dossier QA review', owner: 'Priya Natarajan · QA', status: 'Not started' },
];
const CHECK_TONE: Record<Check['status'], Tone> = { Done: 'success', 'In progress': 'info', Blocked: 'critical', 'Not started': 'muted' };

export default function TransferWorkspace() {
  const { notify } = useAppContext();
  const [drawer, setDrawer] = useState(false);
  const tb = MOCK_DATASET.techTransferBlocker;
  const counts = CHECKLIST.reduce<Record<string, number>>((a, c) => ({ ...a, [c.status]: (a[c.status] ?? 0) + 1 }), {});

  return (
    <div className="max-w-[1360px] mx-auto">
      <PageHeader
        frameId="TRANSFER-02"
        agent={{ label: 'Delegate parameter gap resolution', templateId: 'tt-gap' }}
        crumbs={[{ label: 'Improve' }, { label: 'Tech transfer', href: '/tech-transfer' }, { label: 'TT-006' }]}
        title="Mesa 500L single-use → Durham 2000L stainless"
        objectId="TT-006"
        status={<Pill tone="critical" dot>Gate 2 blocker</Pill>}
        description={`AB-mAb-014 upstream transfer. ${tb.gate}. Side-by-side comparison of donor and recipient equipment, with gaps and unknowns shown explicitly.`}
        meta={<><span className="flex items-center gap-2">Gates <GateRoadmap gates={['done', 'done', 'blocked', 'pending', 'pending']} /></span><span>Lead Alex Rivera</span><DemoBoundary compact /></>}
        actions={
          <>
            <LinkButton href="/documents/DOC-UP01-03"><FileText className="h-3.5 w-3.5" /> Draft transfer plan</LinkButton>
            <LinkButton href="/optimization/OPT-104" variant="primary"><Gauge className="h-3.5 w-3.5" /> Propose recipe delta</LinkButton>
          </>
        }
      />

      <Card className="mb-4">
        <CardBody className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Stat label="Scale factor" value="1:4.00" kind="calculated" hint="2000 L / 500 L working volume" />
          <Stat label="Volumetric power (donor)" value="42.8" unit="W/m³" kind="observation" hint="Recipient not measured" />
          <div className="col-span-2 min-w-0">
            <p className="text-[11px] font-medium uppercase tracking-wide text-text-tertiary">Unresolved blocker</p>
            <p className="mt-1 text-[14px] font-semibold text-status-critical">Durham PID cascade tuning constants unmapped</p>
            <p className="mt-0.5 text-[11.5px] text-text-tertiary">Owner K. Osei · due 2026-11-06 <EvidenceChip id="c-tt-006-gate2" className="ml-1" /></p>
          </div>
        </CardBody>
      </Card>

      <AgentCanvasSlot frame="TRANSFER-02" className="space-y-3 mb-4" />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
        <Card>
          <CardHeader title="Donor · Mesa 500L single-use" subtitle="EQ-SPEC-MESA-SUB500 Rev 3" actions={<EvidenceChip id="c-mesa-sub-spec" label="Spec" />} />
          <div className="p-3"><BioreactorSchematic variant="mesa" /></div>
        </Card>
        <Card>
          <CardHeader title="Recipient · Durham 2000L stainless" subtitle="EQ-SPEC-DUR-SS2000 Rev 1 (2023 · may be stale)" actions={<EvidenceChip id="c-durham-ss-spec" label="Spec" />} />
          <div className="p-3"><BioreactorSchematic variant="durham" /></div>
        </Card>
      </div>
      <p className="-mt-2 mb-4 text-[11.5px] text-text-tertiary">Schematics are simplified and drawn to relative vessel scale only. Orange line = feed path; dashed red controller = unmapped loop.</p>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <Card className="xl:col-span-2 min-w-0">
          <CardHeader title="Parameter comparability" subtitle="Status per parameter. Unknowns stay unknown until a source supplies them." />
          <div className={table.wrap}>
            <table className={table.root}>
              <thead>
                <tr>
                  <th className={table.th}>Parameter</th>
                  <th className={table.th}>Mesa 500L</th>
                  <th className={table.th}>Durham 2000L</th>
                  <th className={table.th}>Status</th>
                  <th className={table.th}>Note</th>
                </tr>
              </thead>
              <tbody>
                {PARAMS.map((r) => (
                  <tr key={r.p} className={cn(table.tr, r.p === 'Feed control loop' && 'bg-status-critical-bg/50')}>
                    <td className={cn(table.td, 'font-medium whitespace-nowrap')}>{r.p}</td>
                    <td className={cn(table.td, 'text-[12.5px]')}>{r.mesa}</td>
                    <td className={cn(table.td, 'text-[12.5px]', r.status === 'unknown' && 'italic text-text-tertiary')}>{r.durham}</td>
                    <td className={table.td}>
                      <span className="flex flex-col items-start gap-1">
                        <Pill tone={COMP[r.status].tone} dot>{COMP[r.status].label}</Pill>
                        <ClaimTag kind={r.kind} />
                      </span>
                    </td>
                    <td className={cn(table.td, 'text-[12px] text-text-secondary')}>
                      {r.note}
                      {r.cite && <span className="block mt-1"><EvidenceChip id={r.cite} /></span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <Card className="self-start">
          <CardHeader title="Gate 2 readiness checklist" subtitle={`${counts['Done'] ?? 0} done · ${counts['In progress'] ?? 0} in progress · ${counts['Blocked'] ?? 0} blocked · ${counts['Not started'] ?? 0} not started`} />
          <ul className="divide-y divide-border-hairline">
            {CHECKLIST.map((c) => (
              <li key={c.item} className="px-4 py-2.5">
                <div className="flex items-start justify-between gap-2">
                  <p className="text-[12.5px] text-text-primary">{c.item}</p>
                  <Pill tone={CHECK_TONE[c.status]} dot className="shrink-0">{c.status}</Pill>
                </div>
                <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[11px] text-text-tertiary">{c.owner}{c.cite && <EvidenceChip id={c.cite} />}</p>
              </li>
            ))}
          </ul>
          <p className="px-4 py-2.5 text-[11.5px] text-text-tertiary border-t border-border-hairline">No readiness score is computed. Gate clearance is decided by the Gate 2 review board.</p>
        </Card>
      </div>

      <Card className="mt-4">
        <button
          type="button"
          onClick={() => setDrawer((d) => !d)}
          aria-expanded={drawer}
          className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left hover:bg-surface-secondary/50"
        >
          <span className="flex items-center gap-2">
            {drawer ? <ChevronDown className="h-4 w-4 text-text-tertiary" /> : <ChevronRight className="h-4 w-4 text-text-tertiary" />}
            <Bot className="h-4 w-4 text-brand-teal" aria-hidden />
            <span className="text-[13px] font-semibold">Transfer gap summary</span>
            <Pill tone="warning">Agent draft · not reviewed</Pill>
          </span>
          <span className="text-[11.5px] text-text-tertiary">Tech Transfer Link · RUN-2026-1031 · 3 gaps</span>
        </button>
        {drawer && (
          <div className="border-t border-border-hairline px-4 py-4 space-y-4 text-[13px] leading-relaxed">
            <Callout tone="neutral">Generated from the documents cited below. It has not been reviewed by MSAT or QA and should not be used as a gate decision.</Callout>
            <div>
              <div className="flex items-center gap-2"><SectionLabel>1 · Feed control loop</SectionLabel><ClaimTag kind="observation" /></div>
              <p className="mt-1 text-text-secondary">Mesa delivers feed through a gravimetric cascade; Durham’s FIC-2201 runs flow-only and has no mapped PID constants. <EvidenceChip id="c-tt-006-gate2" /> <EvidenceChip id="c-durham-ss-spec" /></p>
              <div className="mt-2 flex items-start gap-2"><ClaimTag kind="hypothesis" /><p className="text-text-secondary">Given the Mesa PM-204 feed droop under Q-DEV-031, a flow-only loop may not detect tubing slip, so delivered feed could fall below setpoint unnoticed. <EvidenceChip id="historian-up01" /> <EvidenceChip id="sop-up-014" /></p></div>
            </div>
            <div>
              <div className="flex items-center gap-2"><SectionLabel>2 · Oxygen transfer</SectionLabel><ClaimTag kind="unknown" /></div>
              <p className="mt-1 text-text-secondary">Durham kLa is not characterised, so oxygen-transfer parity at constant P/V cannot be confirmed. Ring sparger and H/D 2.0 differ from Mesa. <EvidenceChip id="c-mesa-sub-spec" /></p>
            </div>
            <div>
              <div className="flex items-center gap-2"><SectionLabel>3 · Mixing & shear</SectionLabel><ClaimTag kind="hypothesis" /></div>
              <p className="mt-1 text-text-secondary">The Rushton lower impeller may raise local shear relative to the Mesa pitched-blade at matched P/V. No Durham tip-speed setpoint exists to test this.</p>
            </div>
            <div className="rounded-control border border-border-hairline bg-surface-secondary/60 p-3">
              <div className="flex items-center gap-2"><SectionLabel>Suggested next steps</SectionLabel><ClaimTag kind="recommendation" /></div>
              <ul className="mt-1.5 list-disc pl-5 text-[12.5px] text-text-secondary space-y-0.5">
                <li>Request FIC-2201 constants and add a gravimetric trim to the Durham recipe delta (OPT-104).</li>
                <li>Schedule kLa characterisation before engineering run planning.</li>
              </ul>
            </div>
            <div className="flex flex-wrap gap-2">
              <LinkButton href="/optimization/OPT-104" size="sm" variant="primary">Propose recipe delta</LinkButton>
              <Button size="sm" onClick={() => notify('Marked for MSAT review. The draft stays labeled “not reviewed” until someone signs it off.', 'info')}><MessageSquareWarning className="h-3.5 w-3.5" /> Flag for MSAT review</Button>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
