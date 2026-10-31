'use client';

import { useMemo, useState } from 'react';
import { Bot, Check, Download, FileDown, History, MessageSquare, PenLine, Send, UserRound } from 'lucide-react';
import { Button, Callout, Card, CardBody, CardHeader, ClaimTag, DemoBoundary, EvidenceChip, LinkButton, Modal, PageHeader, Pill, SectionLabel, type ClaimKind } from '@/components/ui';
import { downloadText } from '@/components/screens/c/shared';
import { CITATIONS } from '@/fixtures/biomanufacturingData';
import { ROLE_PEOPLE, useAppContext } from '@/lib/app-context';
import { cn } from '@/lib/cn';
import { AgentCanvasSlot } from '@/components/agent/AgentCanvasSlot';

type Origin = 'agent' | 'human' | 'agent-edited';
type Cite = { id: string; label?: string };
type Para = { id: string; origin: Origin; text: string; cites: Cite[]; kind?: ClaimKind };
type Section = { id: string; title: string; paras: Para[] };

const TARGET_WORDS = 1842;

const INITIAL: Section[] = [
  {
    id: 's1',
    title: '1. Purpose and scope',
    paras: [
      { id: 'p1', origin: 'human', text: 'This summary documents the investigation of deviation Q-DEV-031 on Skid BR-UP-01, batch MES-26073 (AB-mAb-014, campaign CMP-26-10). It covers the feed-flow droop and PM-204 head-pressure exceedance, the evidence reviewed, the most-likely cause and proposed CAPAs. It does not constitute a batch disposition decision.', cites: [{ id: 'qms-q-dev-031', label: 'QMS Q-DEV-031' }] },
    ],
  },
  {
    id: 's2',
    title: '2. Event description',
    paras: [
      { id: 'p2', origin: 'agent', kind: 'observation', text: 'At T+264.4 h PM-204 discharge head pressure rose to 1.48 bar against a 1.20 bar ceiling, and delivered feed flow fell from 16.88 to 14.48 mL/min (−14.2%) within two minutes.', cites: [{ id: 'historian-up01' }] },
      { id: 'p3', origin: 'agent', kind: 'observation', text: 'The operator acknowledged the deviation at eBR step 05.4 with FEED_SP 16.90 mL/min and FEED_PV 14.48 mL/min.', cites: [{ id: 'ebr-mes-26073', label: 'eBR MES-26073 step 05.4' }] },
      { id: 'p4', origin: 'agent-edited', kind: 'unknown', text: 'A 42-minute historian gap exists at T+182.0–182.7 h caused by a PI buffer overflow. No values from this window are used in any calculation in this report.', cites: [{ id: 'historian-gap', label: 'Historian gap §4.2' }] },
    ],
  },
  {
    id: 's3',
    title: '3. Investigation and evidence',
    paras: [
      { id: 'p5', origin: 'agent', kind: 'observation', text: 'Work order WO-8819, performed 48 h before the event, records an increase of the PM-204 occlusion clamp torque from 0.42 to 0.55 N·m. Dynamic slip verification was not performed because the fixture was unavailable.', cites: [{ id: 'cmms-wo-8819', label: 'CMMS WO-8819' }] },
      { id: 'p6', origin: 'human', kind: 'observation', text: 'SOP-UP-014 Rev 7 §7.2 requires a dynamic slip verification at operating RPM after any occlusion adjustment, with gravimetric acceptance of ±3% of setpoint.', cites: [{ id: 'sop-up-014', label: 'SOP-UP-014 §7.2' }] },
      { id: 'p7', origin: 'agent', kind: 'observation', text: 'The pump-head OEM manual states that increased occlusion shortens tubing service life (400–500 h nominal) and raises discharge pressure.', cites: [{ id: 'oem-masterflex' }] },
      { id: 'p8', origin: 'agent-edited', kind: 'observation', text: 'Harvest sample QC-948 returned an HPLC titer of 3.42 g/L, below the 3.80 g/L alert limit. System suitability passed. Second-person review is pending.', cites: [{ id: 'lims-qc-948', label: 'LIMS QC-948' }, { id: 'c-hplc-arc-run', label: 'Arc HPLC run' }] },
    ],
  },
  {
    id: 's4',
    title: '4. Most-likely root cause (pending QA)',
    paras: [
      { id: 'p9', origin: 'agent-edited', kind: 'hypothesis', text: 'The most-likely cause is over-occlusion of PM-204 tubing following WO-8819, without the required slip verification, leading to accelerated tubing fatigue, elevated discharge pressure and reduced delivered feed. This has not been confirmed by physical inspection of the removed tubing.', cites: [{ id: 'cmms-wo-8819', label: 'CMMS WO-8819' }, { id: 'sop-up-014', label: 'SOP-UP-014 §7.2' }] },
      { id: 'p10', origin: 'agent', kind: 'contradicted', text: 'Alternative causes reviewed and not supported by evidence: feed media lot FM-2207 out of specification (all attributes within specification); DO probe drift (redundant probes agree within 0.6%).', cites: [{ id: 'lims-media-lot' }, { id: 'pi-do-probe' }] },
    ],
  },
  {
    id: 's5',
    title: '5. Product impact',
    paras: [
      { id: 'p11', origin: 'human', kind: 'unknown', text: 'Titer is below the alert limit; other in-process results are within specification except osmolality, which is near its upper limit. SEC monomer has not been tested, so aggregation impact is unknown. Lot MES-26073 remains on QA hold.', cites: [{ id: 'c-lims-qc-948-panel', label: 'LIMS RS-77120 panel' }] },
    ],
  },
  {
    id: 's6',
    title: '6. Proposed CAPA',
    paras: [
      { id: 'p12', origin: 'agent', kind: 'recommendation', text: 'CAPA-01: exchange the PM-204 tubing spool and perform dynamic slip verification before return to service (owner R. Chen, due 2026-11-07). CAPA-02: amend SOP-UP-014 §7.2 so occlusion work orders cannot be closed without a slip-verification record (owner A. Rivera, due 2026-11-28). Both are proposals and have not been entered into QMS.', cites: [] },
    ],
  },
];

const ORIGIN_META: Record<Origin, { label: string; className: string; icon: typeof Bot }> = {
  agent: { label: 'Agent-drafted', className: 'border-l-2 border-dashed border-brand-teal pl-3', icon: Bot },
  'agent-edited': { label: 'Agent-drafted · human-edited', className: 'border-l-2 border-brand-teal pl-3', icon: PenLine },
  human: { label: 'Human-written', className: 'border-l-2 border-slate-400 pl-3', icon: UserRound },
};

type Comment = { id: number; author: string; section: string; text: string; time: string; resolved?: boolean };
const INITIAL_COMMENTS: Comment[] = [
  { id: 1, author: 'Priya Natarajan · QA', section: 's4', text: 'Keep this framed as most-likely until the tubing teardown is done. Please add the teardown as an open action.', time: 'Oct 19 14:35' },
  { id: 2, author: 'R. Chen · Engineering', section: 's3', text: 'Confirmed the slip fixture was out for calibration that week. I can add the calibration record reference.', time: 'Oct 19 15:05' },
  { id: 3, author: 'Alex Rivera · MSAT', section: 's2', text: 'Reworded the gap paragraph so it is explicit that imputed values are excluded.', time: 'Oct 19 15:52', resolved: true },
];

const VERSIONS = [
  { v: 'v0.3', who: 'Alex Rivera', when: '2026-10-19 15:58', note: 'Edited §2, §4 wording; addressed 1 QA comment', current: true },
  { v: 'v0.2', who: 'Alex Rivera', when: '2026-10-19 14:20', note: 'Added §1 and §5; human-edited 3 agent paragraphs' },
  { v: 'v0.1', who: 'Root Cause agent · RUN-2026-1042', when: '2026-10-19 12:45', note: 'Initial agent draft from 9 sources' },
];

const words = (s: string) => s.trim().split(/\s+/).filter(Boolean).length;

export default function DocumentPage() {
  const { notify, userRole } = useAppContext();
  const [sections, setSections] = useState(INITIAL);
  const [editing, setEditing] = useState<string | null>(null);
  const [showAuthorship, setShowAuthorship] = useState(true);
  const [comments, setComments] = useState(INITIAL_COMMENTS);
  const [draft, setDraft] = useState('');
  const [draftSection, setDraftSection] = useState('s4');
  const [exportOpen, setExportOpen] = useState(false);

  const initialVisibleWords = useMemo(() => INITIAL.flatMap((s) => s.paras).reduce((n, p) => n + words(p.text), 0), []);
  const visibleWords = sections.flatMap((s) => s.paras).reduce((n, p) => n + words(p.text), 0);
  const appendixWords = TARGET_WORDS - initialVisibleWords;
  const wordCount = visibleWords + appendixWords;
  const boundCitations = sections.flatMap((s) => s.paras).reduce((n, p) => n + p.cites.length, 0);
  const originCounts = sections.flatMap((s) => s.paras).reduce<Record<Origin, number>>((a, p) => ({ ...a, [p.origin]: a[p.origin] + 1 }), { agent: 0, 'agent-edited': 0, human: 0 });

  const updatePara = (pid: string, text: string) =>
    setSections((ss) => ss.map((s) => ({ ...s, paras: s.paras.map((p) => (p.id === pid ? { ...p, text, origin: p.origin === 'agent' ? 'agent-edited' : p.origin } : p)) })));

  const scrollTo = (id: string) => document.getElementById(`doc-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });

  const addComment = () => {
    if (!draft.trim()) return;
    setComments((c) => [...c, { id: Date.now(), author: `${ROLE_PEOPLE[userRole]} · you`, section: draftSection, text: draft.trim(), time: 'just now' }]);
    setDraft('');
  };

  const exportDraft = () => {
    const lines = [
      '# CONTROLLED DRAFT — NOT AN APPROVED RECORD',
      '',
      '> Demo export from Sievance. Synthetic data. This file is not a controlled document and has not been reviewed or approved.',
      '> Approved investigation reports are issued from Documentum / Veeva QMS, not from this tool.',
      '',
      '## DOC-UP01-03 v0.3 · Investigation summary · Q-DEV-031',
      `Status: DRAFT_IN_PROGRESS · Exported ${new Date().toISOString()}`,
      '',
      ...sections.flatMap((s) => [
        `### ${s.title}`,
        '',
        ...s.paras.flatMap((p) => [
          `${p.text}${p.cites.length ? ' ' + p.cites.map((c) => `[${c.label ?? CITATIONS[c.id]?.documentName ?? c.id}]`).join(' ') : ''}`,
          `<!-- authorship: ${ORIGIN_META[p.origin].label}${p.kind ? ` · claim: ${p.kind}` : ''} -->`,
          '',
        ]),
      ]),
      '### Bound citations',
      ...Array.from(new Set(sections.flatMap((s) => s.paras.flatMap((p) => p.cites.map((c) => c.id))))).map((id) => `- ${id}: ${CITATIONS[id]?.documentName ?? id} · sha256:${CITATIONS[id]?.sha256Hash ?? 'n/a'}`),
      '',
      '_Appendix A (data tables) omitted from demo export._',
      '',
      'CONTROLLED DRAFT — NOT AN APPROVED RECORD',
    ];
    downloadText('DOC-UP01-03_v0.3_DRAFT_demo.md', lines.join('\n'));
    setExportOpen(false);
    notify('Draft downloaded as Markdown (demo). It carries the draft watermark text.', 'info');
  };

  return (
    <div className="max-w-[1440px] mx-auto">
      <PageHeader
        frameId="DOC-01"
        crumbs={[{ label: 'Assure' }, { label: 'Documents' }, { label: 'DOC-UP01-03' }]}
        title="Investigation summary · Q-DEV-031"
        objectId="DOC-UP01-03 v0.3"
        status={<Pill tone="warning" dot>Draft in progress</Pill>}
        description="Working draft assembled from cited sources. Paragraphs show whether they were drafted by an agent or written by a person."
        meta={<><span className="tabular-nums">{wordCount.toLocaleString()} words</span><span className="tabular-nums">{boundCitations} bound citations</span><span>Owner Alex Rivera</span><DemoBoundary compact /></>}
        actions={
          <>
            <Button onClick={() => setExportOpen(true)}><FileDown className="h-3.5 w-3.5" /> Export PDF / Word</Button>
            <LinkButton href="/reviews/REV-01" variant="primary"><Send className="h-3.5 w-3.5" /> Route for multi-party review</LinkButton>
          </>
        }
      />

      <div role="note" className="mb-4 flex items-center justify-center gap-2 rounded-card border border-red-200 bg-status-critical-bg px-3 py-2 text-[12.5px] font-semibold tracking-wide text-red-700 uppercase">
        Controlled draft — not an approved record
      </div>

      <AgentCanvasSlot frame="DOC-01" className="space-y-3 mb-4" />

      <div className="grid grid-cols-1 lg:grid-cols-[200px_minmax(0,1fr)] xl:grid-cols-[200px_minmax(0,1fr)_300px] gap-4">
        <nav aria-label="Document outline" className="lg:sticky lg:top-0 self-start">
          <Card>
            <div className="px-3 py-2.5 border-b border-border-hairline"><SectionLabel>Outline</SectionLabel></div>
            <ul className="p-1.5">
              {sections.map((s) => (
                <li key={s.id}>
                  <button type="button" onClick={() => scrollTo(s.id)} className="w-full text-left px-2 py-1.5 rounded text-[12.5px] text-text-secondary hover:bg-surface-secondary hover:text-text-primary flex items-center justify-between gap-2">
                    <span className="truncate">{s.title}</span>
                    {comments.some((c) => c.section === s.id && !c.resolved) && <MessageSquare className="h-3 w-3 text-status-warning shrink-0" aria-label="Open comments" />}
                  </button>
                </li>
              ))}
              <li><span className="block px-2 py-1.5 text-[12.5px] text-text-muted">Appendix A · data tables</span></li>
            </ul>
            <div className="px-3 py-2.5 border-t border-border-hairline space-y-1.5">
              <label className="flex items-center gap-2 text-[12px] text-text-secondary cursor-pointer">
                <input type="checkbox" checked={showAuthorship} onChange={(e) => setShowAuthorship(e.target.checked)} className="accent-[#0e7490]" />
                Show authorship
              </label>
              {showAuthorship && (
                <ul className="space-y-1 text-[11px] text-text-tertiary">
                  {(Object.keys(ORIGIN_META) as Origin[]).map((o) => (
                    <li key={o} className={cn('py-0.5', ORIGIN_META[o].className)}>{ORIGIN_META[o].label} · {originCounts[o]}</li>
                  ))}
                </ul>
              )}
            </div>
          </Card>
        </nav>

        <article className="min-w-0 bg-surface border border-border-hairline rounded-card watermark-draft">
          <header className="px-8 pt-7 pb-4 border-b border-border-hairline">
            <p className="text-[11px] font-mono text-text-tertiary">DOC-UP01-03 · v0.3 · Aster Biologics · Mesa UP-01</p>
            <h2 className="mt-1 text-xl font-semibold text-text-primary">Investigation Summary: Feed Droop and Head-Pressure Exceedance, BR-UP-01</h2>
            <p className="mt-1 text-[12px] text-text-tertiary">Deviation Q-DEV-031 · Batch MES-26073 · Prepared by Alex Rivera (MSAT) with Root Cause agent assistance</p>
          </header>
          <div className="px-8 py-6 space-y-7">
            {sections.map((s) => (
              <section key={s.id} id={`doc-${s.id}`} className="scroll-mt-4">
                <h3 className="text-[15px] font-semibold text-text-primary">{s.title}</h3>
                <div className="mt-2.5 space-y-3">
                  {s.paras.map((p) => {
                    const meta = ORIGIN_META[p.origin];
                    const Icon = meta.icon;
                    const isEditing = editing === p.id;
                    return (
                      <div key={p.id} className={cn('group', showAuthorship && meta.className)}>
                        {(showAuthorship || p.kind) && (
                          <div className="mb-1 flex flex-wrap items-center gap-1.5">
                            {showAuthorship && <span className="inline-flex items-center gap-1 text-[10.5px] text-text-tertiary"><Icon className="h-3 w-3" aria-hidden />{meta.label}</span>}
                            {p.kind && <ClaimTag kind={p.kind} className="!h-4 !px-1.5 !text-[9px]" />}
                          </div>
                        )}
                        {isEditing ? (
                          <div>
                            <textarea
                              value={p.text}
                              onChange={(e) => updatePara(p.id, e.target.value)}
                              rows={Math.max(3, Math.ceil(p.text.length / 90))}
                              aria-label={`Edit paragraph in ${s.title}`}
                              className="w-full rounded-control border border-border-strong bg-surface px-3 py-2 text-[13.5px] leading-relaxed focus:outline-none focus:ring-2 focus:ring-brand-teal"
                              autoFocus
                            />
                            <div className="mt-1 flex items-center justify-between gap-2">
                              <p className="text-[11px] text-text-tertiary">Citations stay bound to this paragraph. Editing an agent paragraph marks it human-edited.</p>
                              <Button size="sm" onClick={() => setEditing(null)}><Check className="h-3 w-3" /> Done</Button>
                            </div>
                          </div>
                        ) : (
                          <p className="text-[13.5px] leading-relaxed text-text-primary">
                            {p.text}{' '}
                            {p.cites.map((c) => <EvidenceChip key={c.id} id={c.id} label={c.label} className="mr-1" />)}
                            <button type="button" onClick={() => setEditing(p.id)} className="ml-1 inline-flex items-center gap-0.5 text-[11px] text-text-tertiary hover:text-brand-teal opacity-60 group-hover:opacity-100 focus:opacity-100" aria-label="Edit paragraph">
                              <PenLine className="h-3 w-3" /> Edit
                            </button>
                          </p>
                        )}
                      </div>
                    );
                  })}
                </div>
              </section>
            ))}
            <section className="rounded-control border border-dashed border-border-strong px-4 py-3">
              <h3 className="text-[13px] font-semibold text-text-secondary">Appendix A · Data tables</h3>
              <p className="text-[12px] text-text-tertiary">{appendixWords.toLocaleString()} words of tabulated historian and LIMS data. Collapsed in this demo.</p>
            </section>
          </div>
        </article>

        <aside className="space-y-4 lg:col-span-2 xl:col-span-1">
          <Card>
            <CardHeader title="Comments" subtitle={`${comments.filter((c) => !c.resolved).length} open`} icon={<MessageSquare className="h-4 w-4" />} />
            <ul className="divide-y divide-border-hairline">
              {comments.map((c) => (
                <li key={c.id} className={cn('px-4 py-2.5', c.resolved && 'opacity-60')}>
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-[12px] font-medium text-text-primary">{c.author}</p>
                    <span className="text-[10.5px] text-text-tertiary">{c.time}</span>
                  </div>
                  <button type="button" onClick={() => scrollTo(c.section)} className="text-[10.5px] text-brand-teal hover:underline">{sections.find((s) => s.id === c.section)?.title}</button>
                  <p className="mt-0.5 text-[12.5px] text-text-secondary">{c.text}</p>
                  <button type="button" onClick={() => setComments((cs) => cs.map((x) => (x.id === c.id ? { ...x, resolved: !x.resolved } : x)))} className="mt-1 text-[11px] text-text-tertiary hover:text-text-primary">
                    {c.resolved ? 'Reopen' : 'Resolve'}
                  </button>
                </li>
              ))}
            </ul>
            <CardBody className="border-t border-border-hairline space-y-2">
              <label className="block">
                <span className="text-[11px] text-text-tertiary">Section</span>
                <select value={draftSection} onChange={(e) => setDraftSection(e.target.value)} className="mt-0.5 w-full h-8 rounded-control border border-border-strong bg-surface px-2 text-[12.5px]">
                  {sections.map((s) => <option key={s.id} value={s.id}>{s.title}</option>)}
                </select>
              </label>
              <textarea value={draft} onChange={(e) => setDraft(e.target.value)} rows={2} placeholder="Add a comment" aria-label="New comment" className="w-full rounded-control border border-border-strong px-2.5 py-1.5 text-[12.5px] focus:outline-none focus:ring-2 focus:ring-brand-teal" />
              <div className="flex items-center justify-between gap-2">
                <span className="text-[10.5px] text-text-tertiary">Kept in this session only (demo)</span>
                <Button size="sm" variant="primary" disabled={!draft.trim()} onClick={addComment}>Comment</Button>
              </div>
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Version history" icon={<History className="h-4 w-4" />} />
            <ol className="divide-y divide-border-hairline">
              {VERSIONS.map((v) => (
                <li key={v.v} className="px-4 py-2.5">
                  <div className="flex items-center gap-2">
                    <code className="text-[12px] font-mono font-semibold">{v.v}</code>
                    {v.current && <Pill tone="brand">Current</Pill>}
                    <span className="ml-auto text-[10.5px] text-text-tertiary tabular-nums">{v.when}</span>
                  </div>
                  <p className="text-[11.5px] text-text-tertiary">{v.who}</p>
                  <p className="text-[12px] text-text-secondary">{v.note}</p>
                </li>
              ))}
            </ol>
          </Card>

          <Callout tone="neutral">
            When approved, the final report is issued from Documentum under document control. This workspace prepares the draft and its evidence links.
          </Callout>
        </aside>
      </div>

      <Modal
        open={exportOpen}
        onClose={() => setExportOpen(false)}
        title="Export draft"
        footer={
          <>
            <Button onClick={() => setExportOpen(false)}>Cancel</Button>
            <Button variant="primary" onClick={exportDraft}><Download className="h-3.5 w-3.5" /> Download draft (.md)</Button>
          </>
        }
      >
        <div className="space-y-3 text-[13px] text-text-secondary">
          <Callout tone="warning" title="Demo export">PDF and Word rendering is staged in this demo. You will get a Markdown file with the same content, the draft watermark text and the list of bound citations with hashes.</Callout>
          <p>The export is a working copy. It is not a controlled document and must not be used as an approved investigation report.</p>
        </div>
      </Modal>
    </div>
  );
}
