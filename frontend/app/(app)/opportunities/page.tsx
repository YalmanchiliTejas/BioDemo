'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { ArrowRight, ChevronDown, ChevronUp, Video, VideoOff } from 'lucide-react';
import { Button, Card, CardBody, CardHeader, ClaimTag, DemoBoundary, EvidenceChip, LinkButton, PageHeader, Pill, ProgressBar, Segmented, SectionLabel, type ClaimKind, type Tone } from '@/components/ui';
import { useAppContext } from '@/lib/app-context';
import { cn } from '@/lib/cn';

type Maturity = 'mechanism' | 'correlational' | 'fact' | 'contradicted';
type Signal = {
  id: string;
  rank: number;
  title: string;
  scope: string;
  kind: ClaimKind;
  maturity: Maturity;
  maturityLabel: string;
  summary: string;
  valueAtRisk: number;
  valueNote: string;
  sources: { verified: number; total: number };
  counterChecked: string;
  unknown: string;
  citations: string[];
  detected: string;
  ctas: Array<{ label: string; href: string; primary?: boolean }>;
};

const MATURITY_META: Record<Maturity, { tone: Tone; label: string }> = {
  mechanism: { tone: 'warning', label: 'Correlation + plausible mechanism (untested)' },
  correlational: { tone: 'neutral', label: 'Correlational only' },
  fact: { tone: 'info', label: 'Recorded fact' },
  contradicted: { tone: 'critical', label: 'Contradicted by evidence' },
};

const SIGNALS: Signal[] = [
  {
    id: 'SIG-0412', rank: 1,
    title: 'Late-Phase Feed-Rate Attenuation in UP-01',
    scope: 'BR-UP-01 · PM-204 · MES-26071/72/73',
    kind: 'observation', maturity: 'mechanism', maturityLabel: '',
    summary: 'Delivered feed fell 14.2% after a head-pressure spike at T+264.4h on MES-26073; yield has declined across three consecutive batches (81.2 → 78.4 → 75.9). Feed loss and head pressure correlate (R² = 0.941, 3 batches). Tubing fatigue/over-occlusion after WO-8819 is the leading hypothesis — not yet tested.',
    valueAtRisk: 1.86, valueNote: '6.1 yield-index pts below target × $305k per pt (planning value)',
    sources: { verified: 4, total: 4 }, counterChecked: '2 alternatives contradicted (media lot, DO drift)',
    unknown: 'Whether feed loss accounts for the full yield gap; why MES-26072 also declined slightly.',
    citations: ['historian-up01', 'ebr-mes-26073', 'cmms-wo-8819', 'lims-qc-948'],
    detected: 'Oct 19 08:52 · MSAT Yield Sentry',
    ctas: [{ label: 'Open investigation', href: '/investigations/INV-104', primary: true }, { label: 'Analyze in Workbench', href: '/workbench/AN-104' }],
  },
  {
    id: 'SIG-0398', rank: 2,
    title: 'Durham transfer blocked: feed-loop PID constants unmapped',
    scope: 'TT-006 · Mesa 500 L SUB → Durham 2,000 L SS',
    kind: 'observation', maturity: 'fact', maturityLabel: '',
    summary: 'Gate 2 checklist item 2.7 is open: the recipient feed-rate cascade (FIC-2210) has no mapped PID constants. Any feed-control change made at Mesa (see OPT-104) would also need mapping at Durham.',
    valueAtRisk: 0.92, valueNote: '~3-week Gate 2 slip × $307k/week holding cost (planning value)',
    sources: { verified: 3, total: 3 }, counterChecked: 'Not applicable — status read directly from checklist',
    unknown: 'Durham automation team has not given a completion date.',
    citations: ['b-tt006-gate2'],
    detected: 'Oct 16 17:45 · Transfer Readiness agent',
    ctas: [{ label: 'Inspect Durham transfer blocker', href: '/tech-transfer/TT-006', primary: true }],
  },
  {
    id: 'SIG-0405', rank: 3,
    title: 'CIP window overlaps MES-26074 inoculation by 4.5 h',
    scope: 'BR-UP-01 · WO-8862 · Mon Oct 26',
    kind: 'observation', maturity: 'fact', maturityLabel: '',
    summary: 'Scheduled CIP/SIP (06:00–14:00) overlaps the planned 09:30 inoculation. If unresolved, inoculation slips by at least one suite-day.',
    valueAtRisk: 0.46, valueNote: '1 suite-day opportunity cost (planning value)',
    sources: { verified: 2, total: 2 }, counterChecked: 'Not applicable — schedule records',
    unknown: 'Whether WO-8848 (tubing changeout) can run inside the same CIP window.',
    citations: ['b-cmms-wo-8862', 'b-cmms-wo-8848'],
    detected: 'Oct 18 15:31 · Schedule Conflict Checker',
    ctas: [{ label: 'Open planning', href: '/planning', primary: true }],
  },
  {
    id: 'SIG-0409', rank: 4,
    title: 'Feed media lot FM-2207 variation',
    scope: 'Raw materials · MES-26072/73',
    kind: 'contradicted', maturity: 'contradicted', maturityLabel: '',
    summary: 'Raised as a candidate explanation for the yield decline. CoA is within specification for osmolality and glucose, and the same lot fed MES-26072, which did not show the T+264h feed drop.',
    valueAtRisk: 0, valueNote: 'No value attributed while contradicted',
    sources: { verified: 2, total: 2 }, counterChecked: 'CoA in spec · same lot in prior batch',
    unknown: 'Trace-element composition is not on the CoA.',
    citations: ['lims-media-lot', 'b-ebr-media-26072'],
    detected: 'Oct 19 09:40 · MSAT Yield Sentry',
    ctas: [{ label: 'See in INV-104', href: '/investigations/INV-104' }],
  },
  {
    id: 'SIG-0410', rank: 5,
    title: 'DO probe drift on BR-UP-01',
    scope: 'BR.DO_A / BR.DO_B · T+200–280h',
    kind: 'contradicted', maturity: 'contradicted', maturityLabel: '',
    summary: 'Raised because DO trended slightly lower on MES-26073. Redundant probes A and B agree within 0.6% over the window, which argues against sensor drift.',
    valueAtRisk: 0, valueNote: 'No value attributed while contradicted',
    sources: { verified: 1, total: 1 }, counterChecked: 'Redundant probe agreement',
    unknown: 'Last off-line DO calibration check is not in the connected sources.',
    citations: ['pi-do-probe'],
    detected: 'Oct 19 09:41 · MSAT Yield Sentry',
    ctas: [{ label: 'See in INV-104', href: '/investigations/INV-104' }],
  },
];

type Filter = 'all' | 'open' | 'contradicted';
type Sort = 'value' | 'maturity' | 'recent';

export default function OpportunitiesPage() {
  const { notify } = useAppContext();
  const [filter, setFilter] = useState<Filter>('all');
  const [sort, setSort] = useState<Sort>('value');
  const [showAssumptions, setShowAssumptions] = useState(false);

  const total = SIGNALS.reduce((s, x) => s + x.valueAtRisk, 0);
  const list = useMemo(() => {
    const f = SIGNALS.filter((s) => (filter === 'all' ? true : filter === 'contradicted' ? s.maturity === 'contradicted' : s.maturity !== 'contradicted'));
    const order: Record<Maturity, number> = { fact: 0, mechanism: 1, correlational: 2, contradicted: 3 };
    return [...f].sort((a, b) =>
      sort === 'value' ? b.valueAtRisk - a.valueAtRisk || a.rank - b.rank
        : sort === 'maturity' ? order[a.maturity] - order[b.maturity] || b.sources.verified / b.sources.total - a.sources.verified / a.sources.total
          : b.detected.localeCompare(a.detected),
    );
  }, [filter, sort]);

  return (
    <div className="max-w-[1280px] mx-auto">
      <PageHeader
        frameId="INTEL-01"
        crumbs={[{ label: 'Improve' }, { label: 'Opportunities' }]}
        title="Process intelligence inbox"
        status={<Pill tone="warning" dot>3 open · 2 contradicted</Pill>}
        description="Signals raised by monitoring agents and analysts, ranked by estimated impact and how well the evidence holds up. Ranking is a triage aid, not a decision."
        meta={<><span>Primary signal: Late-Phase Feed-Rate Attenuation in UP-01</span><span>Last scan 08:52 UTC</span><DemoBoundary compact /></>}
      />

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <div className="xl:col-span-2 space-y-4">
          <Card>
            <CardBody className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <div className="flex items-center gap-2">
                  <p className="text-[11px] font-medium uppercase tracking-wide text-text-tertiary">Estimated value at risk</p>
                  <Pill tone="warning" className="uppercase text-[10px] tracking-wide">Estimate</Pill>
                </div>
                <p className="mt-1 text-2xl font-semibold tabular-nums text-text-primary">${total.toFixed(2)}M</p>
                <p className="text-[11.5px] text-text-tertiary">Planning-value estimate across open signals · plausible range ±40% · not reviewed by Finance</p>
              </div>
              <Button size="sm" variant="ghost" onClick={() => setShowAssumptions((v) => !v)} aria-expanded={showAssumptions}>
                {showAssumptions ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />} {showAssumptions ? 'Hide' : 'Show'} assumptions
              </Button>
              {showAssumptions && (
                <div className="w-full rounded-control border border-border-hairline bg-surface-secondary/60 p-3 text-[12px] text-text-secondary">
                  <SectionLabel>How this number is built</SectionLabel>
                  <ul className="mt-1.5 space-y-1 list-disc pl-4">
                    {SIGNALS.filter((s) => s.valueAtRisk > 0).map((s) => (
                      <li key={s.id}><span className="font-mono text-text-primary">${s.valueAtRisk.toFixed(2)}M</span> · {s.title} — {s.valueNote}</li>
                    ))}
                    <li>Contradicted signals contribute $0.</li>
                    <li>Per-point and per-day values are FY26 planning figures, not actual batch economics. Signals may overlap; the total may double-count.</li>
                  </ul>
                  <div className="mt-2"><EvidenceChip id="b-sap-standard-cost" /></div>
                </div>
              )}
            </CardBody>
          </Card>

          <div className="flex flex-wrap items-center justify-between gap-2">
            <Segmented<Filter> value={filter} onChange={setFilter} options={[{ value: 'all', label: `All (${SIGNALS.length})` }, { value: 'open', label: 'Open' }, { value: 'contradicted', label: 'Contradicted' }]} />
            <label className="flex items-center gap-2 text-[12px] text-text-secondary">
              Sort by
              <select value={sort} onChange={(e) => setSort(e.target.value as Sort)} className="h-7 rounded-control border border-border-hairline bg-surface px-2 text-[12px] focus:outline-none focus:ring-2 focus:ring-brand-teal">
                <option value="value">Estimated value at risk</option>
                <option value="maturity">Evidence maturity</option>
                <option value="recent">Most recent</option>
              </select>
            </label>
          </div>

          <ul className="space-y-3">
            {list.map((s) => {
              const m = MATURITY_META[s.maturity];
              const contradicted = s.maturity === 'contradicted';
              return (
                <li key={s.id}>
                  <Card className={cn(s.rank === 1 && 'border-amber-300', contradicted && 'bg-surface-secondary/40')}>
                    <div className="p-4">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <code className="text-[11px] font-mono text-text-tertiary">{s.id}</code>
                            <ClaimTag kind={s.kind} />
                            <Pill tone={m.tone}>{m.label}</Pill>
                          </div>
                          <h2 className={cn('mt-1.5 text-[14px] font-semibold', contradicted ? 'text-text-secondary' : 'text-text-primary')}>{s.title}</h2>
                          <p className="text-[11.5px] font-mono text-text-tertiary">{s.scope}</p>
                        </div>
                        <div className="text-right">
                          <p className="text-[10.5px] uppercase tracking-wide text-text-tertiary">Est. value at risk</p>
                          <p className={cn('text-[16px] font-semibold tabular-nums', s.valueAtRisk > 0 ? 'text-text-primary' : 'text-text-muted')}>{s.valueAtRisk > 0 ? `$${s.valueAtRisk.toFixed(2)}M` : '—'}</p>
                        </div>
                      </div>
                      <p className="mt-2 text-[12.5px] text-text-secondary leading-relaxed">{s.summary}</p>

                      <div className="mt-3 grid grid-cols-1 md:grid-cols-3 gap-3 rounded-control border border-border-hairline p-3">
                        <div>
                          <p className="text-[10.5px] uppercase tracking-wide text-text-tertiary">Sources verified</p>
                          <p className="text-[13px] font-semibold tabular-nums">{s.sources.verified}/{s.sources.total} sources verified</p>
                          <ProgressBar className="mt-1" value={s.sources.verified} max={s.sources.total} tone={s.sources.verified === s.sources.total ? 'success' : 'warning'} label="Sources verified" />
                        </div>
                        <div>
                          <p className="text-[10.5px] uppercase tracking-wide text-text-tertiary">Counter-evidence checked</p>
                          <p className="text-[12px] text-text-secondary">{s.counterChecked}</p>
                        </div>
                        <div>
                          <p className="text-[10.5px] uppercase tracking-wide text-text-tertiary flex items-center gap-1">Still unknown</p>
                          <p className="text-[12px] text-text-secondary">{s.unknown}</p>
                        </div>
                      </div>

                      <div className="mt-3 flex flex-wrap items-center gap-2">
                        {s.citations.map((c) => <EvidenceChip key={c} id={c} />)}
                        <span className="ml-auto flex flex-wrap gap-2">
                          {s.ctas.map((c) => (
                            <LinkButton key={c.href + c.label} href={c.href} size="sm" variant={c.primary ? 'primary' : 'secondary'}>{c.label} <ArrowRight className="h-3 w-3" /></LinkButton>
                          ))}
                        </span>
                      </div>
                      <p className="mt-2 text-[11px] text-text-muted">Detected {s.detected}{contradicted && ' · kept for audit; not dismissed by a reviewer yet'}</p>
                    </div>
                  </Card>
                </li>
              );
            })}
          </ul>
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader title="Skid camera · BR-UP-01 / PM-204" icon={<Video className="h-4 w-4" />} actions={<Pill tone="muted">Not connected</Pill>} />
            <CardBody>
              <div className="aspect-video rounded-control border border-dashed border-border-strong bg-surface-secondary flex flex-col items-center justify-center text-center px-6">
                <VideoOff className="h-6 w-6 text-text-muted" aria-hidden />
                <p className="mt-2 text-[12.5px] font-medium text-text-secondary">No camera feed connected in demo</p>
                <p className="mt-0.5 text-[11.5px] text-text-tertiary">Video evidence would let reviewers see pump-head seating and tubing wear without entering the suite.</p>
              </div>
              <div className="mt-3 flex items-center justify-between gap-2">
                <Link href="/sources" className="text-[12px] text-brand-teal hover:underline">Connect a video source</Link>
                <Button size="sm" variant="ghost" onClick={() => notify('Camera request logged locally. Connecting a feed needs site IT and QA approval; nothing was changed.', 'info')}>Request access</Button>
              </div>
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="How signals are ranked" />
            <CardBody className="space-y-2 text-[12px] text-text-secondary">
              <p><span className="font-medium text-text-primary">Impact</span> — planning-value estimate of yield, schedule or program cost. Shown with assumptions; not a forecast.</p>
              <p><span className="font-medium text-text-primary">Evidence maturity</span> — how many cited sources are retrieved and hash-verified, whether alternatives were checked, and whether a mechanism has been tested.</p>
              <p><span className="font-medium text-text-primary">No signal is a confirmed root cause.</span> Mechanisms become verified only after a planned test and a named reviewer sign-off.</p>
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Evidence maturity legend" />
            <CardBody className="space-y-2">
              {(Object.keys(MATURITY_META) as Maturity[]).map((k) => (
                <div key={k} className="flex items-center gap-2 text-[12px]"><Pill tone={MATURITY_META[k].tone}>{MATURITY_META[k].label}</Pill></div>
              ))}
              <p className="text-[11.5px] text-text-tertiary pt-1">“Verified mechanism” is not shown because no signal has reached it.</p>
            </CardBody>
          </Card>
        </div>
      </div>
    </div>
  );
}
