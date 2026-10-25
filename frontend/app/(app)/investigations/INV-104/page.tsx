'use client';

import { useState } from 'react';
import Link from 'next/link';
import { ArrowRight, CheckCircle2, ClipboardList, FileText, FlaskConical, HelpCircle, MessageSquareWarning, Plus, XCircle } from 'lucide-react';
import { Button, Callout, Card, CardBody, CardHeader, ClaimTag, DemoBoundary, EvidenceChip, LinkButton, Modal, PageHeader, Pill, SectionLabel, Stat, type ClaimKind, type Tone } from '@/components/ui';
import { ROLE_PEOPLE, useAppContext } from '@/lib/app-context';
import { cn } from '@/lib/cn';

type Evidence = { id: string; text: string; cite?: string; kind: ClaimKind; supports: boolean };
type Hypothesis = {
  key: 'A' | 'B' | 'C';
  title: string;
  verdict: { label: string; tone: Tone; kind: ClaimKind };
  summary: string;
  evidence: Evidence[];
  changeMind: string[];
};

const HYPOTHESES: Hypothesis[] = [
  {
    key: 'A',
    title: 'Mechanical tubing fatigue / slip on PM-204',
    verdict: { label: 'Supported · not established', tone: 'warning', kind: 'hypothesis' },
    summary: 'Over-occlusion after the WO-8819 clamp adjustment, on tubing near the end of its rated life, raised discharge pressure and reduced delivered volume per revolution.',
    evidence: [
      { id: 'A1', text: 'R² = 0.941 between feed loss and head pressure across 3 batches (n = 237 hourly points, imputed excluded). Correlation, not causal proof.', cite: 'b-calc-feed-pressure', kind: 'calculated', supports: true },
      { id: 'A2', text: 'WO-8819 raised clamp torque 0.42 → 0.55 N·m ~48 h before the spike; dynamic slip check not performed.', cite: 'cmms-wo-8819', kind: 'observation', supports: true },
      { id: 'A3', text: 'SOP-UP-014 §7.2 requires a slip verification after any occlusion adjustment.', cite: 'sop-up-014', kind: 'observation', supports: true },
      { id: 'A4', text: 'Tubing at 412 h of a 400–500 h OEM service life; OEM notes higher occlusion shortens life and raises pressure.', cite: 'oem-masterflex', kind: 'observation', supports: true },
      { id: 'A5', text: 'PT-204 pressure transmitter calibrated Oct 3, as-found +0.3% FS — the pressure reading itself is credible.', cite: 'b-cmms-wo-8790', kind: 'observation', supports: true },
      { id: 'A6', text: 'MES-26072 declined 2.8 pts with no clamp adjustment and normal pressure — tubing slip does not explain that batch.', cite: 'historian-up01', kind: 'observation', supports: false },
    ],
    changeMind: [
      'Gravimetric slip test on the removed tubing at 0.55 N·m shows delivery within ±3% of setpoint.',
      'Fresh tubing at 0.42 N·m reproduces the same pressure rise at the same RPM.',
      'Feed-loss-adjusted yield model leaves most of the 6.1-pt gap unexplained.',
    ],
  },
  {
    key: 'B',
    title: 'Raw feed media lot variation (FM-2207)',
    verdict: { label: 'Contradicted', tone: 'critical', kind: 'contradicted' },
    summary: 'A nutrient-composition difference in the feed lot reduced productivity.',
    evidence: [
      { id: 'B1', text: 'CoA within specification: osmolality 312 mOsm/kg (290–330), glucose 198 g/L (190–210).', cite: 'lims-media-lot', kind: 'observation', supports: false },
      { id: 'B2', text: 'Same lot FM-2207 fed MES-26072, which showed no T+264h feed drop.', cite: 'b-ebr-media-26072', kind: 'observation', supports: false },
      { id: 'B3', text: 'Titer trend diverges only after the feed-flow drop, not from feed start.', cite: 'lims-qc-948', kind: 'observation', supports: false },
    ],
    changeMind: ['Trace-element or hydrolysate assay shows FM-2207 outside historical range (not on CoA today).', 'An alternate-lot batch reproduces the decline with normal feed delivery.'],
  },
  {
    key: 'C',
    title: 'Dissolved-oxygen sensor drift',
    verdict: { label: 'Contradicted', tone: 'critical', kind: 'contradicted' },
    summary: 'A drifting DO probe caused control to under-aerate, limiting cell productivity.',
    evidence: [
      { id: 'C1', text: 'Redundant probes DO_A and DO_B agree within 0.6% over T+200–280h.', cite: 'pi-do-probe', kind: 'observation', supports: false },
      { id: 'C2', text: 'DO stays inside the 35–45% band on all three batches.', cite: 'pi-do-probe', kind: 'observation', supports: false },
    ],
    changeMind: ['Off-line DO calibration check shows both probes biased in the same direction (common-mode drift).'],
  },
];

const UNKNOWNS = [
  { text: 'Whether feed loss alone explains the full 6.1-pt yield gap on MES-26073.', kind: 'unknown' as ClaimKind },
  { text: 'Why MES-26072 declined 2.8 pts without a pressure event.', kind: 'unknown' as ClaimKind },
  { text: 'Telemetry for 42 minutes at T+182.0h (PI buffer overflow). Imputed values are excluded from every statistic.', kind: 'imputed' as ClaimKind, cite: 'historian-gap' },
  { text: 'Physical condition of the removed tubing — not yet inspected; no camera or photo evidence connected.', kind: 'unknown' as ClaimKind },
];

type TestPlan = { id: string; hyp: string; test: string; criterion: string; owner: string; status: string };
const INITIAL_PLANS: TestPlan[] = [
  { id: 'TP-01', hyp: 'A', test: 'Gravimetric slip test of removed tubing TS24-PT-5521 at 0.42 and 0.55 N·m, 184 RPM, 5 min each', criterion: 'Delivery within ±3% of setpoint at 0.42 N·m; >5% shortfall at 0.55 N·m supports A', owner: 'K. Daniels (Maintenance)', status: 'Planned · not executed' },
  { id: 'TP-02', hyp: 'B', test: 'Retain-sample trace-element panel on FM-2207 vs two prior lots', criterion: 'All elements within ±2 SD of historical lots keeps B contradicted', owner: 'M. Okafor (QC)', status: 'Planned · not executed' },
];

type Dispute = { note: string; by: string };

export default function InvestigationPage() {
  const { notify, userRole } = useAppContext();
  const [plans, setPlans] = useState<TestPlan[]>(INITIAL_PLANS);
  const [planOpen, setPlanOpen] = useState(false);
  const [form, setForm] = useState({ hyp: 'A', test: '', criterion: '', owner: 'Alex Rivera (MSAT)' });
  const [disputes, setDisputes] = useState<Record<string, Dispute>>({});
  const [challenge, setChallenge] = useState<Evidence | null>(null);
  const [challengeNote, setChallengeNote] = useState('');

  const savePlan = () => {
    if (!form.test.trim() || !form.criterion.trim()) return;
    const id = `TP-${String(plans.length + 1).padStart(2, '0')}`;
    setPlans((p) => [...p, { id, hyp: form.hyp, test: form.test.trim(), criterion: form.criterion.trim(), owner: form.owner, status: 'Draft · not executed' }]);
    setPlanOpen(false);
    setForm({ hyp: 'A', test: '', criterion: '', owner: 'Alex Rivera (MSAT)' });
    notify(`${id} added to INV-104 (local draft). It is not scheduled in any system until the owner accepts it.`);
  };

  const saveDispute = () => {
    if (!challenge || challengeNote.trim().length < 5) return;
    setDisputes((d) => ({ ...d, [challenge.id]: { note: challengeNote.trim(), by: ROLE_PEOPLE[userRole] } }));
    notify(`Evidence ${challenge.id} marked disputed. The hypothesis status will be re-reviewed; source records are unchanged.`, 'info');
    setChallenge(null);
    setChallengeNote('');
  };

  const inputCls = 'w-full rounded-control border border-border-strong bg-surface px-2.5 py-1.5 text-[13px] focus:outline-none focus:ring-2 focus:ring-brand-teal';

  return (
    <div className="max-w-[1280px] mx-auto">
      <PageHeader
        frameId="INV-01"
        crumbs={[{ label: 'Improve' }, { label: 'Investigations' }, { label: 'INV-104' }]}
        title="Yield decline on BR-UP-01 · MES-26073"
        objectId="INV-104"
        status={<Pill tone="warning" dot>HYPOTHESES_UNDER_REVIEW</Pill>}
        description="Three candidate explanations, each with the evidence that supports or contradicts it. Nothing here is an approved root cause; the deviation Q-DEV-031 remains the system of record."
        meta={<><span>Lead: Alex Rivera (MSAT)</span><span>Linked: Q-DEV-031 · AN-104 · MES-26073</span><span>Opened Oct 19 10:15 UTC</span><DemoBoundary compact /></>}
        actions={
          <>
            <Button onClick={() => setPlanOpen(true)}><Plus className="h-3.5 w-3.5" /> Create test plan</Button>
            <LinkButton href="/documents/DOC-UP01-03"><FileText className="h-3.5 w-3.5" /> Draft investigation summary</LinkButton>
            <LinkButton href="/optimization/OPT-104" variant="primary"><FlaskConical className="h-3.5 w-3.5" /> Propose controlled experiment</LinkButton>
          </>
        }
      />

      <Card className="mb-4">
        <CardBody className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Stat label="Yield trend" value="81.2 → 75.9" hint="MES-26071 → 26073" kind="calculated" />
          <Stat label="Feed droop" value="−14.2" unit="%" hint="after T+264.4h" kind="observation" />
          <Stat label="Head pressure peak" value="1.48" unit="bar" hint="ceiling 1.20 bar" kind="observation" />
          <Stat label="Hypotheses" value="1 / 3" hint="supported · 2 contradicted" />
        </CardBody>
        <div className="flex flex-wrap items-center gap-2 px-4 py-2.5 border-t border-border-hairline text-[11.5px] text-text-tertiary">
          Problem evidence: <EvidenceChip id="historian-up01" /> <EvidenceChip id="ebr-mes-26073" /> <EvidenceChip id="qms-q-dev-031" />
          <Link href="/workbench/AN-104" className="ml-auto text-brand-teal hover:underline">Open analysis AN-104</Link>
        </div>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-4">
        {HYPOTHESES.map((h) => {
          const supports = h.evidence.filter((e) => e.supports);
          const against = h.evidence.filter((e) => !e.supports);
          return (
            <Card key={h.key} className={cn('flex flex-col', h.key === 'A' && 'border-amber-300')}>
              <div className="px-4 py-3 border-b border-border-hairline">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[11px] font-mono text-text-tertiary">Hypothesis {h.key}</span>
                  <ClaimTag kind={h.verdict.kind} />
                </div>
                <h2 className="mt-1 text-[14px] font-semibold text-text-primary leading-snug">{h.title}</h2>
                <Pill tone={h.verdict.tone} className="mt-1.5">{h.verdict.label}</Pill>
                <p className="mt-2 text-[12px] text-text-secondary leading-relaxed">{h.summary}</p>
              </div>
              <div className="px-4 py-3 space-y-3 flex-1">
                {supports.length > 0 && (
                  <div>
                    <SectionLabel className="text-emerald-700">Supporting · {supports.length}</SectionLabel>
                    <ul className="mt-1.5 space-y-2">{supports.map((e) => <EvidenceRow key={e.id} e={e} dispute={disputes[e.id]} onChallenge={() => setChallenge(e)} />)}</ul>
                  </div>
                )}
                {against.length > 0 && (
                  <div>
                    <SectionLabel className="text-red-700">Contradicting · {against.length}</SectionLabel>
                    <ul className="mt-1.5 space-y-2">{against.map((e) => <EvidenceRow key={e.id} e={e} dispute={disputes[e.id]} onChallenge={() => setChallenge(e)} />)}</ul>
                  </div>
                )}
              </div>
              <div className="px-4 py-3 border-t border-border-hairline bg-surface-secondary/40 rounded-b-card">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-text-tertiary flex items-center gap-1"><HelpCircle className="h-3 w-3" />What would change our mind</p>
                <ul className="mt-1.5 space-y-1 text-[12px] text-text-secondary list-disc pl-4">
                  {h.changeMind.map((c) => <li key={c}>{c}</li>)}
                </ul>
              </div>
            </Card>
          );
        })}
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <Card className="xl:col-span-2">
          <CardHeader
            title="Test plans"
            subtitle="Counter-evidence tests designed to confirm or rule out each hypothesis"
            icon={<ClipboardList className="h-4 w-4" />}
            actions={<Button size="sm" onClick={() => setPlanOpen(true)}><Plus className="h-3 w-3" /> Add test</Button>}
          />
          <ul className="divide-y divide-border-hairline">
            {plans.map((p) => (
              <li key={p.id} className="px-4 py-3">
                <div className="flex flex-wrap items-center gap-2">
                  <code className="text-[11px] font-mono text-text-tertiary">{p.id}</code>
                  <Pill tone="neutral">Hypothesis {p.hyp}</Pill>
                  <Pill tone={p.status.startsWith('Draft') ? 'warning' : 'muted'}>{p.status}</Pill>
                  <span className="ml-auto text-[11.5px] text-text-tertiary">Owner: {p.owner}</span>
                </div>
                <p className="mt-1.5 text-[12.5px] text-text-primary">{p.test}</p>
                <p className="mt-0.5 text-[12px] text-text-secondary"><span className="text-text-tertiary">Acceptance criterion:</span> {p.criterion}</p>
              </li>
            ))}
          </ul>
          <div className="px-4 py-2.5 border-t border-border-hairline text-[11.5px] text-text-tertiary flex flex-wrap items-center gap-2">
            Tests that change equipment or process settings need a controlled experiment proposal and review.
            <LinkButton href="/optimization/OPT-104" size="sm" variant="ghost" className="ml-auto">Propose controlled experiment <ArrowRight className="h-3 w-3" /></LinkButton>
          </div>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader title="What remains unknown" />
            <ul className="divide-y divide-border-hairline">
              {UNKNOWNS.map((u) => (
                <li key={u.text} className="px-4 py-2.5 text-[12.5px] text-text-secondary">
                  <ClaimTag kind={u.kind} className="mr-1.5" />{u.text} {u.cite && <EvidenceChip id={u.cite} />}
                </li>
              ))}
            </ul>
          </Card>
          <Callout tone="info" title="Status is separate from approval">
            “Supported” means the evidence so far is consistent with hypothesis A. A root cause is assigned only in Q-DEV-031 by QA after tests complete.
          </Callout>
        </div>
      </div>

      <Modal
        open={planOpen}
        onClose={() => setPlanOpen(false)}
        title="Create test plan"
        footer={<><Button onClick={() => setPlanOpen(false)}>Cancel</Button><Button variant="primary" onClick={savePlan} disabled={!form.test.trim() || !form.criterion.trim()}>Save draft</Button></>}
      >
        <div className="space-y-3">
          <label className="block">
            <span className="text-[12px] font-medium text-text-secondary">Hypothesis</span>
            <select className={cn(inputCls, 'mt-1')} value={form.hyp} onChange={(e) => setForm({ ...form, hyp: e.target.value })}>
              {HYPOTHESES.map((h) => <option key={h.key} value={h.key}>{h.key} · {h.title}</option>)}
            </select>
          </label>
          <label className="block">
            <span className="text-[12px] font-medium text-text-secondary">Test</span>
            <textarea className={cn(inputCls, 'mt-1 min-h-[70px]')} value={form.test} onChange={(e) => setForm({ ...form, test: e.target.value })} placeholder="What will be done, on what material or equipment, under which conditions" />
          </label>
          <label className="block">
            <span className="text-[12px] font-medium text-text-secondary">Acceptance criterion</span>
            <textarea className={cn(inputCls, 'mt-1 min-h-[56px]')} value={form.criterion} onChange={(e) => setForm({ ...form, criterion: e.target.value })} placeholder="Which result supports or rules out the hypothesis" />
          </label>
          <label className="block">
            <span className="text-[12px] font-medium text-text-secondary">Owner</span>
            <select className={cn(inputCls, 'mt-1')} value={form.owner} onChange={(e) => setForm({ ...form, owner: e.target.value })}>
              {['Alex Rivera (MSAT)', 'K. Daniels (Maintenance)', 'M. Okafor (QC)', 'Marcus Bell (Cleanroom)', 'Priya Natarajan (QA)'].map((o) => <option key={o}>{o}</option>)}
            </select>
          </label>
          <p className="text-[11.5px] text-text-tertiary">Saved as a local draft on this investigation. It is not sent to CMMS or LIMS.</p>
        </div>
      </Modal>

      <Modal
        open={!!challenge}
        onClose={() => setChallenge(null)}
        title={`Challenge evidence ${challenge?.id ?? ''}`}
        footer={<><Button onClick={() => setChallenge(null)}>Cancel</Button><Button variant="danger" onClick={saveDispute} disabled={challengeNote.trim().length < 5}>Mark as disputed</Button></>}
      >
        {challenge && (
          <div className="space-y-3">
            <p className="text-[12.5px] text-text-secondary rounded-control bg-surface-secondary p-2.5">{challenge.text}</p>
            <label className="block">
              <span className="text-[12px] font-medium text-text-secondary">Why is this evidence wrong, incomplete or misapplied?</span>
              <textarea className={cn(inputCls, 'mt-1 min-h-[80px]')} value={challengeNote} onChange={(e) => setChallengeNote(e.target.value)} placeholder="e.g. the window includes the post-alarm period and inflates the fit" />
            </label>
            <p className="text-[11.5px] text-text-tertiary">Recorded as {ROLE_PEOPLE[userRole]}. The source record is not changed; the dispute is attached to this investigation for review.</p>
          </div>
        )}
      </Modal>
    </div>
  );
}

function EvidenceRow({ e, dispute, onChallenge }: { e: Evidence; dispute?: Dispute; onChallenge: () => void }) {
  return (
    <li className={cn('rounded-control border p-2', e.supports ? 'border-emerald-200 bg-status-success-bg/60' : 'border-red-200 bg-status-critical-bg/60', dispute && 'opacity-80')}>
      <div className="flex items-start gap-1.5">
        {e.supports ? <CheckCircle2 className="h-3.5 w-3.5 mt-0.5 shrink-0 text-status-success" aria-label="Supports" /> : <XCircle className="h-3.5 w-3.5 mt-0.5 shrink-0 text-status-critical" aria-label="Contradicts" />}
        <p className={cn('text-[12px] leading-snug text-text-primary', dispute && 'line-through decoration-text-muted')}>{e.text}</p>
      </div>
      <div className="mt-1.5 flex flex-wrap items-center gap-1.5 pl-5">
        <ClaimTag kind={e.kind} className="!h-4 !text-[9px]" />
        {e.cite && <EvidenceChip id={e.cite} />}
        {dispute ? (
          <Pill tone="warning">Disputed</Pill>
        ) : (
          <button type="button" onClick={onChallenge} className="ml-auto inline-flex items-center gap-1 text-[11px] text-text-tertiary hover:text-status-critical" aria-label={`Challenge evidence ${e.id}`}>
            <MessageSquareWarning className="h-3 w-3" /> Challenge
          </button>
        )}
      </div>
      {dispute && <p className="mt-1 pl-5 text-[11px] text-amber-800">“{dispute.note}” — {dispute.by}</p>}
    </li>
  );
}
