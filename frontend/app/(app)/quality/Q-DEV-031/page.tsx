'use client';

import { useState } from 'react';
import Link from 'next/link';
import { ArrowRight, ChevronDown, ChevronRight, ClipboardCheck, FileText, Lock, Send } from 'lucide-react';
import { Button, Callout, Card, CardBody, CardHeader, ClaimTag, DemoBoundary, EvidenceChip, KeyValue, LinkButton, PageHeader, Pill, SectionLabel, type ClaimKind } from '@/components/ui';
import { StageTracker } from '@/components/screens/c/shared';
import { MOCK_DATASET } from '@/fixtures/biomanufacturingData';
import { cn } from '@/lib/cn';
import { AgentCanvasSlot } from '@/components/agent/AgentCanvasSlot';

const STAGES = ['Initiated', 'Triage & containment', 'Root-cause investigation', 'CAPA plan', 'QA approval', 'Closure'];
const CURRENT_STAGE = 2; // ROOT_CAUSE_INVESTIGATION

type Event = { rel: string; abs: string; title: string; detail: string; kind: ClaimKind; citation?: string; tone: 'critical' | 'warning' | 'neutral' | 'muted' };

const EVENTS: Event[] = [
  { rel: 'Event −48 h', abs: '2026-10-17 07:12', title: 'WO-8819 · PM-204 occlusion clamp torque 0.42 → 0.55 N·m', detail: 'Returned to service without the dynamic slip verification required by SOP-UP-014 §7.2 (fixture unavailable).', kind: 'observation', citation: 'cmms-wo-8819', tone: 'warning' },
  { rel: 'T+182.0–182.7 h', abs: '2026-10-15 14:00', title: 'Historian gap · 42 min (PI buffer overflow)', detail: 'No PM-204 flow or pressure data for this window. Not used in any calculation.', kind: 'unknown', citation: 'historian-gap', tone: 'muted' },
  { rel: 'T+200–264 h', abs: '2026-10-16 → 10-19', title: 'Gradual feed-flow decline on MES-26073', detail: 'Mean delivered flow falls ~0.4 mL/min below MES-26071 over this window.', kind: 'calculated', citation: 'historian-up01', tone: 'neutral' },
  { rel: 'T+264.4 h', abs: '2026-10-19 08:26', title: 'Head-pressure spike to 1.48 bar (ceiling 1.20 bar)', detail: 'Feed flow drops to 14.48 mL/min (−14.2%) within two minutes.', kind: 'observation', citation: 'historian-up01', tone: 'critical' },
  { rel: 'T+264.5 h', abs: '2026-10-19 08:31', title: 'eBR step 05.4 · operator acknowledged feed deviation', detail: 'FEED_SP 16.90 vs FEED_PV 14.48 mL/min recorded by T. Reed.', kind: 'observation', citation: 'ebr-mes-26073', tone: 'warning' },
  { rel: 'T+265.1 h', abs: '2026-10-19 09:05', title: 'Q-DEV-031 opened · lot MES-26073 placed on QA hold', detail: 'Classified Major (Tier 2) by P. Natarajan.', kind: 'observation', citation: 'qms-q-dev-031', tone: 'critical' },
  { rel: 'T+267.6 h', abs: '2026-10-19 11:40', title: 'QC-948 harvest titer 3.42 g/L · OOT', detail: 'Below the 3.80 g/L alert limit. Second-person review pending.', kind: 'observation', citation: 'lims-qc-948', tone: 'warning' },
];

const CAPAS = [
  {
    id: 'CAPA-01',
    title: 'Exchange PM-204 tubing spool and perform dynamic slip verification',
    detail: 'Replace pump-head tubing with a fresh Pt-cured silicone size 24 spool; verify gravimetric delivery at operating RPM (±3% of setpoint) before return to GMP service.',
    owner: 'R. Chen · Engineering',
    due: '2026-11-07',
    effectiveness: 'Next 3 batches: feed delivery within ±3% of setpoint and head pressure < 1.20 bar for the full fed-batch phase (historian review).',
    citations: ['cmms-wo-8819', 'oem-masterflex'],
  },
  {
    id: 'CAPA-02',
    title: 'Amend SOP-UP-014 §7.2 to make slip verification a hard hold point',
    detail: 'Add a CMMS work-order closure check: occlusion adjustments cannot be closed without an attached slip-verification record; add a spare verification fixture to Suite 3B.',
    owner: 'Alex Rivera · MSAT',
    due: '2026-11-28',
    effectiveness: '90-day CMMS audit: zero occlusion adjustments returned to service without a slip-verification record.',
    citations: ['sop-up-014'],
  },
];

export default function DeviationPage() {
  const [showAlternatives, setShowAlternatives] = useState(true);

  return (
    <div className="max-w-[1280px] mx-auto">
      <PageHeader
        frameId="QUAL-02"
        agent={{ label: 'Draft RCA dossier', templateId: 'dossier' }}
        crumbs={[{ label: 'Assure' }, { label: 'Quality', href: '/quality' }, { label: 'Q-DEV-031' }]}
        title="Feed droop & head-pressure exceedance on BR-UP-01"
        objectId="Q-DEV-031"
        status={<><Pill tone="critical" dot>Major · Tier 2</Pill><Pill tone="warning">Root-cause investigation</Pill></>}
        description={`${MOCK_DATASET.equipmentIncident.skid} · ${MOCK_DATASET.equipmentIncident.name} (PM-204) · lot MES-26073. This dossier assembles evidence for the investigation; the deviation record itself lives in Veeva Vault QMS.`}
        meta={<><span className="flex items-center gap-1"><Lock className="h-3 w-3" aria-hidden /> QMS mode: <code className="font-mono">READ_ONLY_SANDBOX</code></span><span>Owner Priya Natarajan (QA)</span><span>Due 2026-11-18 (30-day)</span><DemoBoundary compact /></>}
        actions={
          <>
            <LinkButton href="/documents/DOC-UP01-03"><FileText className="h-3.5 w-3.5" /> Draft CAPA summary in workspace</LinkButton>
            <LinkButton href="/reviews/REV-01" variant="primary"><ClipboardCheck className="h-3.5 w-3.5" /> Request QA sign-off</LinkButton>
          </>
        }
      />

      <Card className="mb-4">
        <CardBody className="overflow-x-auto">
          <StageTracker stages={STAGES} current={CURRENT_STAGE} label="Deviation lifecycle" />
          <p className="mt-2 text-[11.5px] text-text-tertiary">Stage mirrors Veeva QMS. Advancing a stage happens in QMS by the record owner, not here.</p>
        </CardBody>
      </Card>

      <AgentCanvasSlot frame="QUAL-02" className="space-y-3 mb-4" />

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <div className="xl:col-span-2 space-y-4 min-w-0">
          <Card>
            <CardHeader title="Event sequence" subtitle="Chronological. “Event −48 h” is relative to the pressure spike; “T+” is elapsed batch time. Times UTC." />
            <ol className="px-4 py-3">
              {EVENTS.map((e, i) => (
                <li key={i} className="relative flex gap-3 pb-4 last:pb-0">
                  {i < EVENTS.length - 1 && <span className="absolute left-[5px] top-4 bottom-0 w-px bg-border-hairline" aria-hidden />}
                  <span className={cn('relative mt-1.5 h-[11px] w-[11px] shrink-0 rounded-full border-2 bg-surface', e.tone === 'critical' ? 'border-status-critical' : e.tone === 'warning' ? 'border-status-warning' : e.tone === 'muted' ? 'border-dashed border-text-muted' : 'border-text-tertiary')} />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                      <code className="text-[11.5px] font-mono font-semibold text-text-primary">{e.rel}</code>
                      <span className="text-[11px] text-text-tertiary tabular-nums">{e.abs}</span>
                      <ClaimTag kind={e.kind} />
                    </div>
                    <p className="mt-0.5 text-[13px] font-medium text-text-primary">{e.title}</p>
                    <p className="text-[12.5px] text-text-secondary">{e.detail}</p>
                    {e.citation && <div className="mt-1"><EvidenceChip id={e.citation} /></div>}
                  </div>
                </li>
              ))}
            </ol>
          </Card>

          <Card>
            <CardHeader
              title="Root-cause narrative"
              subtitle="Draft by Root Cause agent (RUN-2026-1042), edited by Alex Rivera. Pending QA review."
              actions={<><Pill tone="warning">Draft</Pill><ClaimTag kind="hypothesis" /></>}
            />
            <CardBody className="space-y-4 text-[13px] leading-relaxed">
              <Callout tone="warning" title="Most-likely hypothesis, not an established cause">
                QA has not accepted this explanation. The physical tubing from PM-204 has not yet been inspected, which is the most direct test.
              </Callout>
              <div>
                <SectionLabel>Most-likely mechanism</SectionLabel>
                <p className="mt-1.5 text-text-secondary">
                  Raising the occlusion clamp torque during WO-8819 <EvidenceChip id="cmms-wo-8819" /> without the required dynamic slip verification <EvidenceChip id="sop-up-014" /> likely over-compressed the tubing. The OEM notes that increased occlusion shortens tubing life and raises discharge pressure <EvidenceChip id="oem-masterflex" />. That is consistent with both the progressive flow decline and the T+264.4h pressure spike with −14.2% feed droop <EvidenceChip id="historian-up01" />.
                </p>
              </div>
              <div>
                <SectionLabel>Contributing factor</SectionLabel>
                <p className="mt-1.5 text-text-secondary">The SOP requirement exists but is not enforced at work-order closure; the verification fixture was unavailable and the pump was returned to service anyway <EvidenceChip id="cmms-wo-8819" />.</p>
              </div>
              <div>
                <button type="button" onClick={() => setShowAlternatives((s) => !s)} className="flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wider text-text-tertiary hover:text-text-primary" aria-expanded={showAlternatives}>
                  {showAlternatives ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />} Alternatives considered & unknowns
                </button>
                {showAlternatives && (
                  <ul className="mt-2 space-y-2">
                    <li className="flex flex-wrap items-start gap-2"><ClaimTag kind="contradicted" /><span className="flex-1 min-w-0 text-text-secondary">Feed media lot quality: FM-2207 osmolality and glucose are within specification. <EvidenceChip id="lims-media-lot" /></span></li>
                    <li className="flex flex-wrap items-start gap-2"><ClaimTag kind="contradicted" /><span className="flex-1 min-w-0 text-text-secondary">DO probe drift driving a control response: redundant probes A/B agree within 0.6%. <EvidenceChip id="pi-do-probe" /></span></li>
                    <li className="flex flex-wrap items-start gap-2"><ClaimTag kind="unknown" /><span className="flex-1 min-w-0 text-text-secondary">Tubing run-hours at the time of the spike are not recorded in CMMS, so the OEM 400–500 h service-life window cannot be checked directly.</span></li>
                    <li className="flex flex-wrap items-start gap-2"><ClaimTag kind="unknown" /><span className="flex-1 min-w-0 text-text-secondary">42 minutes of historian data are missing at T+182h. <EvidenceChip id="historian-gap" /></span></li>
                  </ul>
                )}
              </div>
              <div className="rounded-control border border-border-hairline bg-surface-secondary/60 p-3">
                <SectionLabel>What would change this conclusion</SectionLabel>
                <ul className="mt-1.5 list-disc pl-5 text-[12.5px] text-text-secondary space-y-0.5">
                  <li>Tubing teardown showing no wear or spallation beyond normal.</li>
                  <li>A gravimetric slip test on the removed spool within ±3% at operating RPM.</li>
                  <li>A comparable pressure/flow event on PM-204 before WO-8819.</li>
                </ul>
              </div>
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Proposed CAPAs" subtitle="Proposals only. CAPA records are created and approved in Veeva QMS by their owners." />
            <ul className="divide-y divide-border-hairline">
              {CAPAS.map((c) => (
                <li key={c.id} className="px-4 py-3.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <code className="text-[11.5px] font-mono text-text-secondary">{c.id}</code>
                    <ClaimTag kind="recommendation" />
                    <Pill tone="brand" dot>Status: Proposed</Pill>
                  </div>
                  <p className="mt-1 text-[13.5px] font-semibold text-text-primary">{c.title}</p>
                  <p className="mt-0.5 text-[12.5px] text-text-secondary">{c.detail}</p>
                  <KeyValue className="mt-3" cols={3} items={[['Owner', c.owner], ['Due', c.due], ['Approval', 'Not yet requested']]} />
                  <div className="mt-2.5">
                    <p className="text-[11px] text-text-tertiary">Effectiveness check</p>
                    <p className="text-[12.5px] text-text-primary">{c.effectiveness}</p>
                  </div>
                  <div className="mt-2 flex flex-wrap items-center gap-1.5">
                    {c.citations.map((id) => <EvidenceChip key={id} id={id} />)}
                  </div>
                  <ol className="mt-3 flex flex-wrap items-center gap-1 text-[11px]" aria-label={`${c.id} lifecycle`}>
                    {['Proposed', 'Approved in QMS', 'Implemented', 'Effectiveness verified'].map((s, i) => (
                      <li key={s} className="flex items-center gap-1">
                        <span className={cn('px-1.5 py-0.5 rounded border', i === 0 ? 'border-cyan-200 bg-brand-teal-light text-brand-teal-dark font-medium' : 'border-border-hairline text-text-muted')}>{s}</span>
                        {i < 3 && <ChevronRight className="h-3 w-3 text-text-muted" aria-hidden />}
                      </li>
                    ))}
                  </ol>
                </li>
              ))}
            </ul>
          </Card>
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader title="QMS handoff" icon={<Lock className="h-4 w-4" />} />
            <CardBody className="space-y-3">
              <span title="Disabled in demo sandbox. Veeva Vault QMS remains the system of record; no writeback connector is authorized." className="block">
                <Button className="w-full" disabled aria-describedby="qms-note"><Send className="h-3.5 w-3.5" /> Send to Veeva QMS</Button>
              </span>
              <p id="qms-note" className="text-[12px] text-text-secondary">
                Disabled: this workspace runs in <code className="font-mono text-[11px]">READ_ONLY_SANDBOX</code> mode. Veeva Vault QMS remains the system of record. In a configured deployment, an authorized QMS user would review and enter the CAPA there.
              </p>
              <LinkButton href="/documents/DOC-UP01-03" className="w-full justify-between">Draft CAPA summary <ArrowRight className="h-3.5 w-3.5" /></LinkButton>
              <LinkButton href="/reviews/REV-01" variant="primary" className="w-full justify-between">Request QA sign-off <ArrowRight className="h-3.5 w-3.5" /></LinkButton>
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Record" />
            <CardBody>
              <KeyValue cols={2} items={[
                ['Classification', 'Major · Tier 2'],
                ['Opened', '2026-10-19 09:05'],
                ['Lot', <span key="l" className="font-mono">MES-26073</span>],
                ['Equipment', <span key="e" className="font-mono">PM-204</span>],
                ['SOP', <span key="s" className="font-mono">SOP-UP-014 §7.2</span>],
                ['Linked CC', <span key="c" className="font-mono">CC-017</span>],
              ]} />
              <div className="mt-3"><EvidenceChip id="qms-q-dev-031" /></div>
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Impact assessment" subtitle="Preliminary" />
            <CardBody className="space-y-2.5 text-[12.5px]">
              <div className="flex items-start gap-2"><ClaimTag kind="observation" /><span className="text-text-secondary">Harvest titer QC-948 is OOT. <EvidenceChip id="lims-qc-948" /></span></div>
              <div className="flex items-start gap-2"><ClaimTag kind="calculated" /><span className="text-text-secondary">Yield index 75.9 vs target 82.0.</span></div>
              <div className="flex items-start gap-2"><ClaimTag kind="unknown" /><span className="text-text-secondary">Product quality impact (SEC monomer, glycan) not yet tested.</span></div>
              <div className="flex items-start gap-2"><ClaimTag kind="unknown" /><span className="text-text-secondary">Whether MES-26071/26072 used the same tubing lot is not recorded.</span></div>
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Linked work" />
            <ul className="divide-y divide-border-hairline text-[12.5px]">
              {[
                { id: 'INV-104', label: 'Causal investigation', href: '/investigations/INV-104' },
                { id: 'PM-204', label: 'Equipment record', href: '/equipment/PM-204' },
                { id: 'QC-948', label: 'Laboratory sample', href: '/laboratory/QC-948' },
                { id: 'MES-26073', label: 'Batch 360', href: '/batches/MES-26073' },
              ].map((l) => (
                <li key={l.id}>
                  <Link href={l.href} className="w-full flex items-center justify-between px-4 py-2 hover:bg-surface-secondary/60">
                    <span><code className="font-mono text-[11.5px] text-text-primary">{l.id}</code> <span className="text-text-tertiary">· {l.label}</span></span>
                    <ChevronRight className="h-3.5 w-3.5 text-text-muted" aria-hidden />
                  </Link>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </div>
    </div>
  );
}
