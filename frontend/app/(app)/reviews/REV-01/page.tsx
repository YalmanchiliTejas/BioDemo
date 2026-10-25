'use client';

import { useState, type ReactNode } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { ArrowRight, Bot, ExternalLink, FlaskConical, History, Link2, UserRound } from 'lucide-react';
import { Callout, Card, CardBody, CardHeader, ClaimTag, DemoBoundary, EvidenceChip, KeyValue, LinkButton, PageHeader, Pill, SectionLabel, table, type Tone } from '@/components/ui';
import { ReviewDossier, type ReviewDossierProps } from '@/components/ReviewDossier';
import { ACTION_LIFECYCLE } from '@/components/screens/c/shared';
import { ROLE_LABELS, ROLE_PEOPLE, useAppContext, type UserRole } from '@/lib/app-context';
import { cn } from '@/lib/cn';

type Risk = ReviewDossierProps['riskTier'];
const RISK_TONE: Record<Risk, Tone> = { LOW: 'success', MEDIUM: 'warning', HIGH: 'critical', BLOCKER: 'critical' };

type AuditEntry = { at: string; actor: string; agent?: boolean; what: string };

type Item = {
  id: string;
  title: string;
  type: string;
  risk: Risk;
  requester: string;
  age: string;
  stage: number;
  signers: UserRole[];
  audit: AuditEntry[];
  linked: Array<{ id: string; href: string; label: string }>;
  dossier?: Omit<ReviewDossierProps, 'onAuthorizeSignature' | 'onRejectReview' | 'approversRequired' | 'children'> & { body: ReactNode; onApproved?: string; onRejected?: string };
  external?: { system: string; body: ReactNode; href: string; cta: string };
};

const RECIPE_BODY = (
  <div className="space-y-5">
    <div>
      <div className="flex items-center gap-2"><SectionLabel>Rationale</SectionLabel><ClaimTag kind="hypothesis" /></div>
      <p className="mt-1.5 text-[13px] leading-relaxed text-text-secondary">
        Under the current open-loop feed, PM-204 delivered 14.2% less than setpoint after the T+264.4h pressure event and the control system did not compensate <EvidenceChip id="historian-up01" />. The most-likely cause is tubing over-occlusion after WO-8819 <EvidenceChip id="cmms-wo-8819" />. A gravimetric mass-balance cascade would correct delivered mass regardless of tubing slip, and a lower interlock would stop the pump before tubing damage escalates <EvidenceChip id="oem-masterflex" />.
      </p>
    </div>
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
      <div className="rounded-control border border-border-hairline p-3">
        <div className="flex items-center gap-2"><SectionLabel>Expected result</SectionLabel><ClaimTag kind="calculated" /></div>
        <p className="mt-1.5 text-xl font-semibold tabular-nums">+5.1 <span className="text-xs font-normal text-text-tertiary">yield-index pts (illustrative)</span></p>
        <p className="text-[12px] text-text-secondary">Simulated range +2.8 to +6.4 pts across 200 OPT-104 runs. Model not validated against plant outcomes; not a probability of success.</p>
      </div>
      <div className="rounded-control border border-border-hairline p-3">
        <SectionLabel>Constraints & owner</SectionLabel>
        <ul className="mt-1.5 text-[12px] text-text-secondary space-y-0.5 list-disc pl-4">
          <li>Requires load cell on feed tote (installed on BR-UP-01).</li>
          <li>Applies from MES-26074 onward; not retroactive to MES-26073.</li>
          <li>Implementation owner: Alex Rivera via DeltaV recipe change control.</li>
        </ul>
      </div>
    </div>
    <div>
      <SectionLabel>Supporting evidence</SectionLabel>
      <div className="mt-1.5 flex flex-wrap gap-1.5">
        <EvidenceChip id="historian-up01" /><EvidenceChip id="ebr-mes-26073" /><EvidenceChip id="cmms-wo-8819" label="CMMS WO-8819" /><EvidenceChip id="sop-up-014" label="SOP-UP-014 §7.2" /><EvidenceChip id="oem-masterflex" /><EvidenceChip id="lims-qc-948" label="LIMS QC-948" />
      </div>
    </div>
    <div className="rounded-control border border-border-hairline bg-surface-secondary/60 p-3">
      <SectionLabel>What evidence would change this recommendation</SectionLabel>
      <ul className="mt-1.5 list-disc pl-5 text-[12.5px] text-text-secondary space-y-0.5">
        <li>Tubing teardown showing normal wear (would weaken the over-occlusion hypothesis behind the interlock change).</li>
        <li>Gravimetric slip data from PM-204 at 184 RPM within ±3% (open-loop may then be adequate with CAPA-01 alone).</li>
        <li>Loop-tuning trials showing the cascade oscillates at low feed rates.</li>
      </ul>
    </div>
    <Callout tone="info" title="Status is distinct from approval and execution">
      Signing approves the proposal for implementation planning only. Implementation happens in DeltaV under change control, and effectiveness is verified on later batches.
    </Callout>
  </div>
);

const ITEMS: Item[] = [
  {
    id: 'ACT-2026-0891',
    title: 'Recipe patch RCP-AB014-V4.patch.02 · closed-loop feed cascade',
    type: 'Recipe change',
    risk: 'HIGH',
    requester: 'Process Optimization agent · edited by Alex Rivera',
    age: '3 h',
    stage: 1,
    signers: ['MSAT_LEAD', 'QA_REVIEWER'],
    audit: [
      { at: '2026-10-19 08:32', actor: 'Process Optimization agent · RUN-2026-1042', agent: true, what: 'Created ACT-2026-0891 from OPT-104 scenario S-3 (model opt-sim v0.9.2, 6 sources).' },
      { at: '2026-10-19 13:36', actor: 'Alex Rivera · MSAT Lead', what: 'Edited: head-pressure interlock 1.30 → 1.25 bar; added dynamic slip verification requirement.' },
      { at: '2026-10-19 13:40', actor: 'Alex Rivera · MSAT Lead', what: 'Submitted for review. Signatures requested: MSAT_LEAD, QA_REVIEWER.' },
      { at: '2026-10-19 15:10', actor: 'Priya Natarajan · QA Reviewer', what: 'Opened evidence package (6 sources viewed).' },
      { at: '2026-10-19 16:30', actor: 'System', what: 'Re-checked source hashes: 6 of 6 unchanged. Historian gap at T+182h still unresolved.' },
    ],
    linked: [
      { id: 'INV-104', href: '/investigations/INV-104', label: 'Causal investigation' },
      { id: 'OPT-104', href: '/optimization/OPT-104', label: 'Optimization sandbox' },
      { id: 'RUN-2026-1042', href: '/runs/RUN-2026-1042', label: 'Agent run trace' },
      { id: 'Q-DEV-031', href: '/quality/Q-DEV-031', label: 'Deviation' },
    ],
    dossier: {
      actionId: 'ACT-2026-0891',
      title: 'Recipe patch RCP-AB014-V4.patch.02 · closed-loop mass-balance feed cascade',
      entityScope: 'Recipe RCP-AB014-V4 · Skid BR-UP-01 · PM-204 · from MES-26074',
      riskTier: 'HIGH',
      author: 'Process Optimization agent (RUN-2026-1042), edited by Alex Rivera',
      proposedChanges: [
        { parameter: 'Feed control mode', baseline: 'Open-loop', proposed: 'Closed-loop mass-balance cascade', unit: '—' },
        { parameter: 'Feed setpoint', baseline: '16.90', proposed: '16.90 (gravimetric trim ±0.8)', unit: 'mL/min' },
        { parameter: 'Head-pressure interlock', baseline: '1.50', proposed: '1.25', unit: 'bar' },
        { parameter: 'Tubing replacement interval', baseline: '500', proposed: '400', unit: 'h' },
        { parameter: 'Dynamic slip verification after occlusion change', baseline: 'Not required', proposed: 'Required', unit: '—' },
      ],
      body: RECIPE_BODY,
      onApproved: '/workspaces',
      onRejected: '/documents/DOC-UP01-03',
    },
  },
  {
    id: 'QC-948-SO',
    title: 'Second-person review · HPLC titer QC-948',
    type: 'Lab record',
    risk: 'MEDIUM',
    requester: 'M. Okafor · QC',
    age: '5 h',
    stage: 1,
    signers: ['QA_REVIEWER'],
    audit: [
      { at: '2026-10-19 11:40', actor: 'M. Okafor · Analyst', what: 'Primary signature in LabWare LIMS (RS-77120).' },
      { at: '2026-10-19 11:41', actor: 'System', what: 'Second-person review requested from QA.' },
      { at: '2026-10-19 12:35', actor: 'Data Intake agent · RUN-2026-1042', agent: true, what: 'Attached Arc HPLC raw run and chain of custody to the review package.' },
    ],
    linked: [
      { id: 'QC-948', href: '/laboratory/QC-948', label: 'Laboratory sample' },
      { id: 'MES-26073', href: '/batches/MES-26073', label: 'Batch 360' },
    ],
    external: {
      system: 'LabWare LIMS',
      href: '/laboratory/QC-948',
      cta: 'Open sample dossier',
      body: (
        <div className="space-y-3 text-[13px] text-text-secondary">
          <p>The second-person review signature for QC-948 is applied in LabWare LIMS, which remains the system of record. This center collects the evidence package so the reviewer can check it in one place.</p>
          <KeyValue cols={3} items={[['Result', '3.42 g/L (OOT)'], ['Spec', '> 3.80 g/L'], ['Sign-off', '1 of 2']]} />
          <div className="flex flex-wrap gap-1.5"><EvidenceChip id="lims-qc-948" label="LIMS QC-948" /><EvidenceChip id="c-hplc-arc-run" /><EvidenceChip id="c-lims-coc-qc-948" /></div>
        </div>
      ),
    },
  },
  {
    id: 'PLAN-SP-06',
    title: 'Planning shift proposal · MES-26074 inoculation +4.5 h',
    type: 'Schedule change',
    risk: 'MEDIUM',
    requester: 'Marcus Bell · Supervisor',
    age: '1 d',
    stage: 1,
    signers: ['CLEANROOM_SUPERVISOR', 'QA_REVIEWER'],
    audit: [
      { at: '2026-10-19 11:40', actor: 'Schedule Conflict Checker · RUN-2026-1039', agent: true, what: 'Drafted Scenarios A and B for the PM-204 sanitization overlap detected Oct 18.' },
      { at: '2026-10-19 12:30', actor: 'Marcus Bell · Supervisor', what: 'Selected Scenario A and submitted for review.' },
    ],
    linked: [
      { id: 'PLAN-01', href: '/planning', label: 'Planning & constraints' },
      { id: 'PM-204', href: '/equipment/PM-204', label: 'Equipment' },
    ],
    dossier: {
      actionId: 'PLAN-SP-06',
      title: 'Shift MES-26074 inoculation +4.5 h to clear PM-204 sanitization',
      entityScope: 'Suite 3B schedule · BR-UP-01 · PM-204 · MES-26074',
      riskTier: 'MEDIUM',
      author: 'Schedule Conflict Checker (RUN-2026-1039), submitted by Marcus Bell',
      proposedChanges: [
        { parameter: 'MES-26074 inoculation', baseline: 'Mon 26 Oct 09:30', proposed: 'Mon 26 Oct 14:00', unit: 'UTC' },
        { parameter: 'Media hold in vessel', baseline: '25.5', proposed: '30.0', unit: 'h' },
      ],
      body: (
        <div className="space-y-2 text-[13px] text-text-secondary">
          <p className="flex items-start gap-2"><ClaimTag kind="unknown" /><span>Validated media hold limit was not found in connected sources; confirm before approving.</span></p>
          <p className="flex flex-wrap items-center gap-1.5">Evidence: <EvidenceChip id="c-maximo-cip-sched" /></p>
        </div>
      ),
    },
  },
  {
    id: 'CAPA-01',
    title: 'CAPA-01 · PM-204 tubing spool exchange + dynamic slip verification',
    type: 'CAPA proposal',
    risk: 'MEDIUM',
    requester: 'Alex Rivera · MSAT',
    age: '2 d',
    stage: 0,
    signers: ['QA_REVIEWER'],
    audit: [
      { at: '2026-10-19 12:50', actor: 'Root Cause agent · RUN-2026-1042', agent: true, what: 'Drafted CAPA-01 in Q-DEV-031 dossier.' },
      { at: '2026-10-19 13:55', actor: 'Alex Rivera · MSAT Lead', what: 'Set owner R. Chen and due date 2026-11-07.' },
    ],
    linked: [
      { id: 'Q-DEV-031', href: '/quality/Q-DEV-031', label: 'Deviation' },
      { id: 'DOC-UP01-03', href: '/documents/DOC-UP01-03', label: 'Investigation draft' },
    ],
    dossier: {
      actionId: 'CAPA-01',
      title: 'Exchange PM-204 tubing spool and verify dynamic slip before return to service',
      entityScope: 'PM-204 · Q-DEV-031 · Veeva QMS entry pending',
      riskTier: 'MEDIUM',
      author: 'Root Cause agent (RUN-2026-1042), edited by Alex Rivera',
      proposedChanges: [
        { parameter: 'PM-204 tubing', baseline: 'Spool in service', proposed: 'New Pt-cured silicone size 24', unit: '—' },
        { parameter: 'Return-to-service check', baseline: 'Visual', proposed: 'Gravimetric slip ±3%', unit: '—' },
      ],
      body: (
        <div className="space-y-2 text-[13px] text-text-secondary">
          <p>Effectiveness check: next 3 batches with feed delivery within ±3% and head pressure below 1.20 bar.</p>
          <p className="flex flex-wrap items-center gap-1.5">Evidence: <EvidenceChip id="cmms-wo-8819" label="CMMS WO-8819" /><EvidenceChip id="sop-up-014" label="SOP-UP-014 §7.2" /></p>
          <p className="text-[12px] text-text-tertiary">Status: Proposed. After approval here, the CAPA record is entered in Veeva QMS by its owner.</p>
        </div>
      ),
    },
  },
  {
    id: 'TT-006-RQ-04',
    title: 'Request Durham PID cascade constants for FIC-2201',
    type: 'Data request',
    risk: 'LOW',
    requester: 'Alex Rivera · MSAT',
    age: '4 d',
    stage: 1,
    signers: ['MSAT_LEAD'],
    audit: [
      { at: '2026-10-17 11:00', actor: 'Tech Transfer Link · RUN-2026-1031', agent: true, what: 'Drafted request from Gate 2 action item AI-4.' },
      { at: '2026-10-17 11:25', actor: 'Alex Rivera · MSAT Lead', what: 'Edited recipient list (K. Osei, Durham Automation).' },
    ],
    linked: [
      { id: 'TT-006', href: '/tech-transfer/TT-006', label: 'Transfer workspace' },
    ],
    dossier: {
      actionId: 'TT-006-RQ-04',
      title: 'Send formal request for FIC-2201 PID constants (Kc, Ti, Td) to Durham Automation',
      entityScope: 'TT-006 · Gate 2 · Durham BR-D-2000',
      riskTier: 'LOW',
      author: 'Tech Transfer Link (RUN-2026-1031), edited by Alex Rivera',
      proposedChanges: [
        { parameter: 'Request', baseline: 'Not sent', proposed: 'Send to K. Osei · due 2026-11-06', unit: '—' },
      ],
      body: <p className="flex flex-wrap items-center gap-1.5 text-[13px] text-text-secondary">Evidence: <EvidenceChip id="c-tt-006-gate2" /></p>,
    },
  },
];

export default function ReviewCenterPage() {
  const router = useRouter();
  const { notify, userRole } = useAppContext();
  const [activeId, setActiveId] = useState(ITEMS[0].id);
  const item = ITEMS.find((i) => i.id === activeId)!;
  const canSign = item.signers.includes(userRole);

  const approvers = item.signers.map((r) => ({ role: ROLE_LABELS[r], name: ROLE_PEOPLE[r], status: 'PENDING' as const }));

  return (
    <div className="max-w-[1360px] mx-auto">
      <PageHeader
        frameId="REV-01"
        crumbs={[{ label: 'Assure' }, { label: 'Reviews' }, { label: 'Approval & action center' }]}
        title="Approval & action center"
        objectId="REV-01"
        status={<Pill tone="warning" dot>{ITEMS.length} pending</Pill>}
        description="Proposals waiting for a named human decision. Nothing here takes effect until the required people sign, and implementation still happens in the source system."
        meta={<><span>Signing as {ROLE_PEOPLE[userRole]} · {ROLE_LABELS[userRole]}</span><span>Signatures designed to support Part 11 workflows; demo signatures are not Part 11 records</span><DemoBoundary compact /></>}
      />

      <Card className="mb-4">
        <CardHeader title="Triage ledger" subtitle="Select an item to open its dossier" />
        <div className={table.wrap}>
          <table className={table.root}>
            <thead>
              <tr>
                <th className={table.th}>Action</th>
                <th className={table.th}>Type</th>
                <th className={table.th}>Risk</th>
                <th className={table.th}>Requester</th>
                <th className={table.th}>Signers</th>
                <th className={cn(table.th, 'text-right')}>Age</th>
              </tr>
            </thead>
            <tbody>
              {ITEMS.map((i) => (
                <tr
                  key={i.id}
                  className={cn(table.tr, 'cursor-pointer', activeId === i.id && 'bg-brand-teal-light/50 hover:bg-brand-teal-light/50')}
                  onClick={() => setActiveId(i.id)}
                >
                  <td className={table.td}>
                    <button type="button" className="text-left" aria-pressed={activeId === i.id} onClick={(e) => { e.stopPropagation(); setActiveId(i.id); }}>
                      <code className="text-[11.5px] font-mono text-text-secondary">{i.id}</code>
                      <span className="block text-[12.5px] font-medium text-text-primary">{i.title}</span>
                    </button>
                  </td>
                  <td className={cn(table.td, 'text-[12px] whitespace-nowrap')}>{i.type}</td>
                  <td className={table.td}><Pill tone={RISK_TONE[i.risk]} dot>{i.risk}</Pill></td>
                  <td className={cn(table.td, 'text-[12px] text-text-secondary')}>{i.requester}</td>
                  <td className={cn(table.td, 'text-[11.5px] font-mono text-text-tertiary whitespace-nowrap')}>{i.signers.join(' + ')}</td>
                  <td className={cn(table.td, 'text-right text-text-secondary')}>{i.age}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <Card className="xl:col-span-2 min-w-0">
          <CardHeader title="Review dossier" subtitle={item.id} />
          <CardBody>
            {item.dossier ? (
              <div className="space-y-4">
                {!canSign && (
                  <Callout tone="warning" title={`${ROLE_LABELS[userRole]} is not a required signer for ${item.id}`}>
                    Required: {item.signers.map((r) => ROLE_LABELS[r]).join(' and ')}. You can review and comment, but a signature from your role would not count. Switch role in the header to try another perspective.
                  </Callout>
                )}
                <ReviewDossier
                  key={item.id}
                  actionId={item.dossier.actionId}
                  title={item.dossier.title}
                  entityScope={item.dossier.entityScope}
                  proposedChanges={item.dossier.proposedChanges}
                  riskTier={item.dossier.riskTier}
                  author={item.dossier.author}
                  approversRequired={approvers}
                  onAuthorizeSignature={async () => {
                    if (!canSign) throw new Error(`${ROLE_LABELS[userRole]} is not an authorized signer for this action.`);
                    notify(`${ROLE_PEOPLE[userRole]} signed ${item.id} (demo). Status: Under review until all required signatures are recorded; not implemented.`, 'success');
                    if (item.dossier?.onApproved) router.push(item.dossier.onApproved);
                  }}
                  onRejectReview={async () => {
                    notify(`${item.id} sent back to the author with your notes (demo).`, 'warning');
                    if (item.dossier?.onRejected) router.push(item.dossier.onRejected);
                  }}
                >
                  {item.dossier.body}
                </ReviewDossier>
              </div>
            ) : item.external ? (
              <div className="space-y-4">
                <div className="flex flex-wrap items-center gap-2">
                  <code className="text-xs font-mono text-text-secondary">{item.id}</code>
                  <Pill tone="info"><FlaskConical className="h-3 w-3" /> Signed in {item.external.system}</Pill>
                  <Pill tone={RISK_TONE[item.risk]} dot>Risk: {item.risk}</Pill>
                </div>
                <h2 className="text-base font-semibold text-text-primary">{item.title}</h2>
                {item.external.body}
                <div className="flex flex-wrap gap-2">
                  <LinkButton href={item.external.href} variant="primary">{item.external.cta} <ArrowRight className="h-3.5 w-3.5" /></LinkButton>
                  <span title={`Deep links into ${item.external.system} require a live connector. Not available in the demo.`}>
                    <button type="button" disabled className="inline-flex items-center gap-1.5 h-8 px-3 rounded-control border border-border-strong text-[13px] font-medium opacity-50 cursor-not-allowed"><ExternalLink className="h-3.5 w-3.5" /> Open in {item.external.system}</button>
                  </span>
                </div>
              </div>
            ) : null}
          </CardBody>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader title="Action lifecycle" subtitle="Proposal, approval, implementation and effectiveness are tracked separately" />
            <CardBody>
              <ol className="space-y-2">
                {ACTION_LIFECYCLE.map((s, i) => (
                  <li key={s} className="flex items-center gap-2.5 text-[12.5px]">
                    <span className={cn('h-5 w-5 rounded-full border flex items-center justify-center text-[10px] font-semibold tabular-nums', i < item.stage ? 'bg-brand-teal border-brand-teal text-white' : i === item.stage ? 'bg-brand-teal-light border-brand-teal text-brand-teal-dark' : 'border-border-strong text-text-muted')}>{i + 1}</span>
                    <span className={cn(i === item.stage ? 'font-semibold text-text-primary' : i < item.stage ? 'text-text-secondary' : 'text-text-tertiary')}>{s}</span>
                    {i === item.stage && <Pill tone="brand" className="ml-auto">Current</Pill>}
                  </li>
                ))}
              </ol>
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Audit trail" icon={<History className="h-4 w-4" />} subtitle="Append-only in production; local in demo" />
            <ol className="px-4 py-3 space-y-3">
              {item.audit.map((a, i) => (
                <li key={i} className="flex gap-2.5">
                  <span className={cn('mt-0.5 h-5 w-5 shrink-0 rounded-full flex items-center justify-center', a.agent ? 'bg-brand-teal-light text-brand-teal-dark' : 'bg-surface-secondary text-text-secondary')} aria-hidden>
                    {a.agent ? <Bot className="h-3 w-3" /> : <UserRound className="h-3 w-3" />}
                  </span>
                  <div className="min-w-0">
                    <p className="text-[11px] text-text-tertiary tabular-nums">{a.at} UTC</p>
                    <p className="text-[12px] font-medium text-text-primary">{a.actor}</p>
                    <p className="text-[12px] text-text-secondary">{a.what}</p>
                  </div>
                </li>
              ))}
            </ol>
          </Card>

          <Card>
            <CardHeader title="Linked records" icon={<Link2 className="h-4 w-4" />} />
            <ul className="divide-y divide-border-hairline">
              {item.linked.map((l) => (
                <li key={l.id}>
                  <Link href={l.href} className="flex items-center justify-between px-4 py-2 text-[12.5px] hover:bg-surface-secondary/60">
                    <span><code className="font-mono text-[11.5px]">{l.id}</code> <span className="text-text-tertiary">· {l.label}</span></span>
                    <ArrowRight className="h-3 w-3 text-text-muted" aria-hidden />
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
