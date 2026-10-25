'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { ArrowRight, ChevronDown, ChevronUp, Clock, FileText, LineChart, Pin, Plus, Search, Signature } from 'lucide-react';
import { AgentPinnedArtifacts } from '@/components/agent/AgentCanvasSlot';
import { Button, Card, ClaimTag, EmptyNote, EvidenceChip, LinkButton, Modal, PageHeader, Pill, SectionLabel, Stat, useDisclosure, type ClaimKind, type Tone } from '@/components/ui';
import { Sparkline } from '@/components/screens/a/StandaloneEvidence';
import { feedRateSeries, headPressureSeries, yieldSeries, type Series } from '@/fixtures/timeseries';
import { ROLE_LABELS, ROLE_PEOPLE, useAppContext } from '@/lib/app-context';
import { cn } from '@/lib/cn';

type Status = 'ANALYSIS' | 'INVESTIGATING' | 'BLOCKED' | 'DECISION';
const STATUS_META: Record<Status, { label: string; tone: Tone }> = {
  ANALYSIS: { label: 'Analysis in progress', tone: 'info' },
  INVESTIGATING: { label: 'Investigating · QA hold', tone: 'critical' },
  BLOCKED: { label: 'Blocked', tone: 'warning' },
  DECISION: { label: 'Decision needed', tone: 'warning' },
};

type Clip = { label: string; tag: string; series: Series[]; batch: string; window: [number, number]; citation: string; kind: ClaimKind; note: string };
type Clause = { label: string; citation: string; note: string };

type Workspace = {
  id: string;
  title: string;
  objective: string;
  owner: string;
  site: string;
  product: string;
  status: Status;
  nextStep: string;
  lastActivity: string;
  pendingApprovals: number;
  linked: string;
  clips: Clip[];
  clauses: Clause[];
  cta: { label: string; href: string };
};

function slice(series: Series[], batch: string, [a, b]: [number, number]) {
  return series.find((s) => s.id === batch)!.dataPoints.filter((p) => p.elapsedHours >= a && p.elapsedHours <= b && !p.imputed).map((p) => p.value);
}

const WORKSPACES: Workspace[] = [
  {
    id: 'WS-UP01-YIELD',
    title: 'UP-01 Yield Consistency',
    objective: 'Explain batch-to-batch yield variation on UP-01 (81.2 → 78.4 → 75.9) and propose controls to restore the 82.0 target.',
    owner: 'Alex Rivera (MSAT Lead)',
    site: 'Mesa',
    product: 'AB-mAb-014',
    status: 'ANALYSIS',
    nextStep: 'Compare T+240–280 h feed delivery of MES-26073 against the 26071/72 baseline.',
    lastActivity: '38 min ago · analysis window saved in AN-104',
    pendingApprovals: 0,
    linked: 'AN-104',
    clips: [
      { label: 'Feed rate droop after pressure event', tag: 'PM204.FLOW_PV', series: feedRateSeries, batch: 'MES-26073', window: [240, 280], citation: 'historian-up01', kind: 'observation', note: '−14.2% vs setpoint after T+264.4 h' },
      { label: 'Head pressure spike', tag: 'PM204.HEAD_P', series: headPressureSeries, batch: 'MES-26073', window: [244, 280], citation: 'historian-up01', kind: 'observation', note: 'Peak 1.48 bar; ceiling 1.20 bar' },
      { label: 'Yield index trajectory', tag: 'CALC.YIELD_IDX', series: yieldSeries, batch: 'MES-26073', window: [120, 280], citation: 'ebr-mes-26073', kind: 'calculated', note: 'Ends at 75.9' },
    ],
    clauses: [
      { label: 'SOP-UP-014 §7.2 · dynamic slip verification after occlusion change', citation: 'sop-up-014', note: 'Requirement to compare with WO-8819 labor notes' },
      { label: 'Historian gap Hour 182.0–182.7', citation: 'historian-gap', note: 'Imputed span excluded from statistics' },
    ],
    cta: { label: 'Open Case UP-01 Yield', href: '/workbench/AN-104' },
  },
  {
    id: 'WS-INV-104',
    title: 'MES-26073 Investigation',
    objective: 'Establish the cause of deviation Q-DEV-031 (feed flow >10% below setpoint for 47 min) and assess product impact before disposition.',
    owner: 'Alex Rivera (MSAT Lead)',
    site: 'Mesa',
    product: 'AB-mAb-014',
    status: 'INVESTIGATING',
    nextStep: 'QA review of the tubing over-occlusion hypothesis; investigation due 2026-11-18 per SOP-QA-021.',
    lastActivity: '2 h ago · QC-948 result linked',
    pendingApprovals: 2,
    linked: 'INV-104',
    clips: [
      { label: 'Feed rate during deviation window', tag: 'PM204.FLOW_PV', series: feedRateSeries, batch: 'MES-26073', window: [256, 280], citation: 'ebr-mes-26073', kind: 'observation', note: 'eBR step 05.4 · DEV −14.3%' },
    ],
    clauses: [
      { label: 'Q-DEV-031 initial description', citation: 'qms-q-dev-031', note: 'Major, Tier 2' },
      { label: 'WO-8819 · clamp torque adjusted without slip verification', citation: 'cmms-wo-8819', note: 'T−48 h' },
      { label: 'SOP-QA-021 §6.4 · 30-day investigation timeline', citation: 'a-veeva-sop-qa-021', note: 'Due 2026-11-18' },
    ],
    cta: { label: 'Open MES-26073 investigation', href: '/investigations/INV-104' },
  },
  {
    id: 'WS-TT-006',
    title: 'TT-006 Scale-Up',
    objective: 'Transfer AB-mAb-014 from the Mesa 500 L single-use bioreactor to the Durham 2000 L stainless steel bioreactor.',
    owner: 'Alex Rivera (MSAT Lead)',
    site: 'Durham',
    product: 'AB-mAb-014',
    status: 'BLOCKED',
    nextStep: 'Durham engineering to supply feed-loop PID cascade constants so Gate 2 can be reviewed.',
    lastActivity: 'Yesterday · gap list sent to Durham',
    pendingApprovals: 1,
    linked: 'TT-006',
    clips: [
      { label: 'Donor feed profile (reference batch)', tag: 'PM204.FLOW_PV', series: feedRateSeries, batch: 'MES-26071', window: [72, 280], citation: 'historian-up01', kind: 'observation', note: 'Mesa reference, MES-26071' },
    ],
    clauses: [
      { label: 'SOP-TT-003 §5.3 · every critical loop must be mapped before Gate 2', citation: 'a-sop-tt-003', note: 'Current blocker' },
      { label: 'OEM tubing service life (feed pump)', citation: 'oem-masterflex', note: 'Relevant to recipient pump selection' },
    ],
    cta: { label: 'Open TT-006 workspace', href: '/tech-transfer/TT-006' },
  },
  {
    id: 'WS-SCHED-UP01',
    title: 'Cleanroom Schedule Conflict',
    objective: 'Resolve a 4.5 h overlap between BR-UP-01 CIP/SIP (incl. PM-204 line) and MES-26074 inoculation on Mon 26 Oct.',
    owner: 'Marcus Bell (Cleanroom Supervisor)',
    site: 'Mesa',
    product: 'AB-mAb-014',
    status: 'DECISION',
    nextStep: 'Choose one of two drafted scenarios; needs supervisor and MSAT sign-off. Neither is applied.',
    lastActivity: '5 h ago · scenarios drafted',
    pendingApprovals: 1,
    linked: 'PLAN-01',
    clips: [],
    clauses: [
      { label: 'Maximo PM-BRUP01-CIP-Q4 · 06:00–14:00 UTC', citation: 'a-maximo-pm-cip', note: 'Approved PM job' },
      { label: 'MES-26074 inoculation scheduled 09:30 UTC', citation: 'a-ebr-schedule-26074', note: 'Overlaps CIP by 4.5 h' },
    ],
    cta: { label: 'Resolve in planning', href: '/planning' },
  },
];

const TOTAL_PINNED = WORKSPACES.reduce((s, w) => s + w.clips.length + w.clauses.length, 0); // 14

export default function WorkspacesPage() {
  const { userRole, notify } = useAppContext();
  const create = useDisclosure();
  const [query, setQuery] = useState('');
  const [site, setSite] = useState('ALL');
  const [product, setProduct] = useState('ALL');
  const [status, setStatus] = useState<'ALL' | Status>('ALL');
  const [mine, setMine] = useState(false);
  const [expanded, setExpanded] = useState<string | null>('WS-UP01-YIELD');
  const [newObjective, setNewObjective] = useState('');

  const me = ROLE_PEOPLE[userRole];
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return WORKSPACES.filter((w) =>
      (!q || [w.title, w.objective, w.owner, w.linked, w.nextStep, ...w.clauses.map((c) => c.label)].join(' ').toLowerCase().includes(q)) &&
      (site === 'ALL' || w.site === site) &&
      (product === 'ALL' || w.product === product) &&
      (status === 'ALL' || w.status === status) &&
      (!mine || w.owner.startsWith(me)),
    );
  }, [query, site, product, status, mine, me]);

  const reset = () => { setQuery(''); setSite('ALL'); setProduct('ALL'); setStatus('ALL'); setMine(false); };
  const selectCls = 'h-8 px-2 rounded-control border border-border-strong bg-surface text-[12.5px] text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-teal';

  return (
    <div className="max-w-[1280px] mx-auto">
      <PageHeader
        frameId="WORK-01"
        crumbs={[{ label: 'Aster Biologics' }, { label: 'Work' }, { label: 'Workspaces' }]}
        title="Workspaces"
        description="Persistent cases that keep an objective, its evidence, open decisions and next steps together across shifts and roles."
        meta={<><span>Active case owner: Alex Rivera (MSAT Lead)</span><span>Viewing as {me} · {ROLE_LABELS[userRole]}</span></>}
        actions={<Button variant="secondary" onClick={create.onOpen}><Plus className="h-3.5 w-3.5" aria-hidden />New workspace</Button>}
      />

      <AgentPinnedArtifacts />

      <Card className="mb-4">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 px-4 py-3">
          <Stat label="Pinned workspaces" value={WORKSPACES.length} />
          <Stat label="Pinned evidence" value={TOTAL_PINNED} hint="Telemetry clips and source clauses" />
          <Stat label="Pending approvals" value={WORKSPACES.reduce((s, w) => s + w.pendingApprovals, 0)} hint="Need a named signature" />
          <Stat label="Blocked / decision" value={WORKSPACES.filter((w) => w.status === 'BLOCKED' || w.status === 'DECISION').length} />
        </div>
      </Card>

      <div className="flex flex-wrap items-end gap-2 mb-4" role="search">
        <div className="relative flex-1 min-w-[220px]">
          <label htmlFor="ws-search" className="sr-only">Search workspaces</label>
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-text-muted" aria-hidden />
          <input
            id="ws-search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search objective, owner, ID, SOP clause…"
            className="w-full h-8 pl-8 pr-3 rounded-control border border-border-strong bg-surface text-[13px] placeholder:text-text-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-teal"
          />
        </div>
        <label className="flex flex-col gap-0.5 text-[11px] text-text-tertiary">Site
          <select value={site} onChange={(e) => setSite(e.target.value)} className={selectCls}>
            <option value="ALL">All sites</option><option value="Mesa">Mesa</option><option value="Durham">Durham</option>
          </select>
        </label>
        <label className="flex flex-col gap-0.5 text-[11px] text-text-tertiary">Product
          <select value={product} onChange={(e) => setProduct(e.target.value)} className={selectCls}>
            <option value="ALL">All products</option><option value="AB-mAb-014">AB-mAb-014</option>
          </select>
        </label>
        <label className="flex flex-col gap-0.5 text-[11px] text-text-tertiary">Status
          <select value={status} onChange={(e) => setStatus(e.target.value as 'ALL' | Status)} className={selectCls}>
            <option value="ALL">All statuses</option>
            {(Object.keys(STATUS_META) as Status[]).map((s) => <option key={s} value={s}>{STATUS_META[s].label}</option>)}
          </select>
        </label>
        <label className="flex items-center gap-1.5 h-8 px-2 text-[12.5px] text-text-secondary">
          <input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} className="accent-[#0e7490]" />Owned by me
        </label>
      </div>

      <p className="sr-only" aria-live="polite">{filtered.length} workspaces shown</p>

      {filtered.length === 0 ? (
        <Card className="px-4 py-10 text-center">
          <EmptyNote>No workspaces match these filters.</EmptyNote>
          <Button size="sm" variant="ghost" className="mt-2" onClick={reset}>Clear filters</Button>
        </Card>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {filtered.map((w) => {
            const open = expanded === w.id;
            const sm = STATUS_META[w.status];
            const pins = w.clips.length + w.clauses.length;
            return (
              <Card key={w.id} className={cn('flex flex-col', open && 'lg:col-span-2')}>
                <div className="px-4 pt-3.5 pb-3 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <Pin className="h-3.5 w-3.5 text-brand-teal" aria-label="Pinned" />
                    <h2 className="text-[14px] font-semibold text-text-primary">{w.title}</h2>
                    <Pill tone={sm.tone} dot>{sm.label}</Pill>
                    <code className="ml-auto text-[11px] font-mono text-text-tertiary">{w.linked}</code>
                  </div>
                  <p className="mt-1.5 text-[12.5px] text-text-secondary leading-relaxed">{w.objective}</p>
                  <dl className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-2 text-[12px]">
                    <div className="sm:col-span-2 rounded-control bg-surface-secondary px-2.5 py-1.5">
                      <dt className="text-[11px] text-text-tertiary">Next step</dt>
                      <dd className="text-text-primary">{w.nextStep}</dd>
                    </div>
                    <div><dt className="text-[11px] text-text-tertiary">Owner</dt><dd className="text-text-primary">{w.owner}</dd></div>
                    <div><dt className="text-[11px] text-text-tertiary">Site · product</dt><dd className="text-text-primary">{w.site} · <span className="font-mono">{w.product}</span></dd></div>
                    <div><dt className="text-[11px] text-text-tertiary">Last activity</dt><dd className="text-text-primary flex items-center gap-1"><Clock className="h-3 w-3 text-text-muted" aria-hidden />{w.lastActivity}</dd></div>
                    <div><dt className="text-[11px] text-text-tertiary">Pending approvals</dt>
                      <dd className={cn('flex items-center gap-1', w.pendingApprovals ? 'text-status-warning font-medium' : 'text-text-tertiary')}>
                        <Signature className="h-3 w-3" aria-hidden />{w.pendingApprovals ? `${w.pendingApprovals} awaiting signature` : 'None'}
                      </dd>
                    </div>
                  </dl>
                </div>

                {open && (
                  <div id={`${w.id}-pins`} className="border-t border-border-hairline bg-canvas/60 px-4 py-3 grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <SectionLabel className="flex items-center gap-1.5"><LineChart className="h-3 w-3" aria-hidden />Pinned telemetry clips</SectionLabel>
                      {w.clips.length === 0 ? (
                        <p className="mt-2 text-[12px] text-text-tertiary">No telemetry pinned. This case relies on schedule records.</p>
                      ) : (
                        <ul className="mt-2 space-y-2">
                          {w.clips.map((c) => (
                            <li key={c.label} className="flex items-center gap-3 rounded-control border border-border-hairline bg-surface px-3 py-2">
                              <Sparkline values={slice(c.series, c.batch, c.window)} width={110} height={34} color={c.batch === 'MES-26073' ? '#dc2626' : '#0284c7'} label={`${c.tag} ${c.batch} T+${c.window[0]}–${c.window[1]} h`} />
                              <div className="min-w-0 flex-1">
                                <p className="text-[12.5px] font-medium text-text-primary flex flex-wrap items-center gap-1.5">{c.label} <ClaimTag kind={c.kind} /></p>
                                <p className="text-[11px] text-text-tertiary font-mono">{c.batch} · {c.tag} · T+{c.window[0]}–{c.window[1]} h</p>
                                <p className="text-[11px] text-text-secondary">{c.note}</p>
                                <EvidenceChip id={c.citation} className="mt-1" />
                              </div>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                    <div>
                      <SectionLabel className="flex items-center gap-1.5"><FileText className="h-3 w-3" aria-hidden />Linked SOP clauses &amp; records</SectionLabel>
                      <ul className="mt-2 space-y-2">
                        {w.clauses.map((c) => (
                          <li key={c.label} className="rounded-control border border-border-hairline bg-surface px-3 py-2">
                            <p className="text-[12.5px] text-text-primary">{c.label}</p>
                            <p className="text-[11px] text-text-tertiary">{c.note}</p>
                            <EvidenceChip id={c.citation} className="mt-1" />
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                )}

                <div className="flex flex-wrap items-center gap-2 px-4 py-2.5 border-t border-border-hairline">
                  <Button size="sm" variant="ghost" onClick={() => setExpanded(open ? null : w.id)} aria-expanded={open} aria-controls={`${w.id}-pins`}>
                    {open ? <ChevronUp className="h-3.5 w-3.5" aria-hidden /> : <ChevronDown className="h-3.5 w-3.5" aria-hidden />}
                    {open ? 'Hide' : 'Show'} pinned evidence ({pins})
                  </Button>
                  <LinkButton href={w.cta.href} size="sm" variant={w.id === 'WS-UP01-YIELD' ? 'primary' : 'secondary'} className="ml-auto">
                    {w.cta.label} <ArrowRight className="h-3 w-3" aria-hidden />
                  </LinkButton>
                </div>
              </Card>
            );
          })}
        </div>
      )}

      <p className="mt-4 text-[11.5px] text-text-tertiary">
        Workspaces reference records in their systems of record; pinning never copies or edits the source. Approvals are tracked in the <Link href="/reviews/REV-01" className="text-brand-teal hover:underline">approval center</Link>.
      </p>

      <Modal
        open={create.open}
        onClose={create.onClose}
        title="New workspace"
        footer={
          <>
            <Button variant="ghost" onClick={create.onClose}>Cancel</Button>
            <Button
              variant="primary"
              disabled={!newObjective.trim()}
              onClick={() => { notify('Demo only: workspace not saved. In production it would be created in your team’s space.', 'info'); setNewObjective(''); create.onClose(); }}
            >
              Create workspace
            </Button>
          </>
        }
      >
        <label htmlFor="ws-objective" className="text-[12.5px] font-medium text-text-primary">Objective</label>
        <p className="text-[11.5px] text-text-tertiary">Start from a question or event; evidence can be pinned later from any screen.</p>
        <textarea
          id="ws-objective"
          value={newObjective}
          onChange={(e) => setNewObjective(e.target.value)}
          rows={3}
          placeholder="e.g. Understand why MES-26074 seed train VCD is trending low"
          className="mt-2 w-full px-3 py-2 rounded-control border border-border-strong text-[13px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-teal"
        />
      </Modal>
    </div>
  );
}
