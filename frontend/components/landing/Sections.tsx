'use client';

import { useRef, useState, type ReactNode } from 'react';
import Link from 'next/link';
import { ArrowRight, Atom, Check, CircleDashed, ClipboardCheck, Database, GitCompareArrows, PenLine, TriangleAlert, X } from 'lucide-react';
import { CountUp, Reveal, useReducedMotion, useScrollFrame } from './motion';
import { cn } from '@/lib/cn';

const Eyebrow = ({ children, className }: { children: ReactNode; className?: string }) => <p className={cn('lp-eyebrow', className)}>{children}</p>;

/* ---------- Rolling list of what the platform covers ---------- */

const USES = ['CMO deliveries', 'Batch monitoring', 'Deviation investigations', 'Root-cause evidence', 'Physics-based forecasts', 'Freeze-drying design', 'Yield optimization', 'Tech transfer', 'Quality reviews', 'Lab results', 'Knowledge search', 'Operator shifts', 'Tech transfer data'];

export function UsesRoll() {
  const reduced = useReducedMotion();
  const section = useRef<HTMLElement>(null);
  const list = useRef<HTMLUListElement>(null);
  const [active, setActive] = useState(0);
  const activeRef = useRef(0);
  useScrollFrame(section, p => {
    const pos = p * (USES.length - 1);
    list.current?.style.setProperty('--pos', pos.toFixed(3));
    const i = Math.round(pos);
    if (i !== activeRef.current) { activeRef.current = i; setActive(i); }
  }, { pinned: true, enabled: !reduced });

  if (reduced) {
    return (
      <section className="border-b border-border-hairline bg-white px-6 py-24">
        <div className="mx-auto max-w-6xl">
          <Eyebrow className="text-ink">One platform for</Eyebrow>
          <ul className="mt-8 flex flex-wrap gap-x-8 gap-y-3 font-display text-[26px] font-light text-ink">{USES.map(u => <li key={u}>{u}</li>)}</ul>
        </div>
      </section>
    );
  }
  return (
    <section ref={section} className="lp-uses" aria-label="What the platform covers">
      <div className="lp-uses-sticky">
        <div className="mx-auto grid h-full w-full max-w-6xl grid-cols-1 content-center items-center gap-6 pt-14 md:grid-cols-[220px_1fr_auto] md:pt-0">
          <p className="lp-eyebrow text-ink">Manufacturing teams<br className="hidden md:block" /> use it for</p>
          <div className="lp-uses-window">
            <ul ref={list} className="lp-uses-list">
              {USES.map((u, i) => <li key={u} data-distance={Math.min(3, Math.abs(i - active))}>{u}</li>)}
            </ul>
          </div>
          <div className="hidden md:block"><Link href="/home/" className="lp-btn lp-btn-outline">Explore</Link></div>
        </div>
      </div>
    </section>
  );
}

/* ---------- Problem ---------- */

function ParallaxImage({ src, alt }: { src: string; alt: string }) {
  const box = useRef<HTMLDivElement>(null);
  const reduced = useReducedMotion();
  useScrollFrame(box, p => box.current?.style.setProperty('--shift', `${((p - 0.5) * -14).toFixed(2)}%`), { enabled: !reduced });
  return (
    <div ref={box} className="lp-photo">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={src} alt={alt} width={800} height={800} loading="lazy" decoding="async" />
    </div>
  );
}

const PROBLEMS = [
  { img: '/os/assets/btec-bioreactors.jpg', alt: 'Bioreactor control panels in a process development lab', title: 'The answer is spread across systems', body: 'Batch records, historian tags, lab results and work orders each hold part of the story. Every investigation starts with exports and spreadsheets.' },
  { img: '/os/assets/bioreactor-akureyri.jpg', alt: 'Sample vials with syringes', title: 'Investigations start from scratch', body: 'Each deviation means rebuilding the same timeline by hand, and the reasoning ends up in slide decks that are hard to trace back to the data.' },
  { img: '/os/assets/bioreactor-in-operation.jpg', alt: 'A stainless steel bioreactor skid in operation', title: 'Changes get tested on real batches', body: 'Without a model that follows the process physics, a new site, scale or recipe is checked on the plant itself, one batch at a time.' },
];

export function Problem() {
  return (
    <section id="problem" className="scroll-mt-24 bg-canvas px-6 pb-28 pt-28 sm:pb-36 sm:pt-32">
      <div className="mx-auto max-w-6xl">
        <Reveal><Eyebrow>The problem</Eyebrow></Reveal>
        <Reveal delay={80}>
          <h2 className="lp-h2 mt-6 max-w-4xl">
            Manufacturing data lives in <span className="lp-underline">a dozen systems</span>. <span className="text-text-tertiary">Engineers still connect it by hand.</span>
          </h2>
        </Reveal>
        <Reveal delay={120}><p className="mt-20 font-display text-[22px] font-light text-text-tertiary">What that leaves you with —</p></Reveal>
        <div className="mt-10 grid gap-10 md:grid-cols-3 md:gap-8">
          {PROBLEMS.map((p, i) => (
            <Reveal key={p.title} delay={i * 120}>
              <ParallaxImage src={p.img} alt={p.alt} />
              <h3 className="mt-7 font-display text-[22px] font-light tracking-[-0.01em] text-ink">{p.title}</h3>
              <p className="mt-3 text-[15px] leading-relaxed text-text-secondary">{p.body}</p>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ---------- Platform ---------- */

const PILLARS = [
  { icon: Database, title: 'Connect', body: 'Verified CMO deliveries today; read-only access to MES, historian, LIMS and QMS records. Every value keeps its source and timestamp.' },
  { icon: GitCompareArrows, title: 'Investigate', body: 'Agents assemble timelines and candidate causes, with the evidence for and against each one labelled.' },
  { icon: Atom, title: 'Predict', body: 'Physics-based process models forecast what a change will do, with their inputs and assumptions on record.' },
  { icon: ClipboardCheck, title: 'Act', body: 'Findings become proposals with an owner, expected effect and required signatures. Nothing executes on its own.' },
];

/* Synthetic feed-flow traces for three batches, hours 200–300; batch 3 droops after the pump event at 264 h. */
const HOURS = Array.from({ length: 26 }, (_, i) => 200 + i * 4);
const flow = (seed: number, droop: boolean) => HOURS.map((h, i) => 16.9 + Math.sin(i * 1.7 + seed) * 0.18 - (droop && h >= 264 ? 2.1 + (h - 264) * 0.02 : 0));
const TRACES = [{ data: flow(0, false), color: '#94a3b8', id: 'MES-26071' }, { data: flow(2, false), color: '#0284c7', id: 'MES-26072' }, { data: flow(4, true), color: '#dc2626', id: 'MES-26073' }];

function PreviewTimeline() {
  const W = 400, H = 150, x = (h: number) => ((h - 200) / 100) * W, y = (v: number) => H - ((v - 13.5) / 4.5) * H;
  return (
    <div className="lp-preview-card">
      <div className="flex items-center justify-between"><p className="lp-mini-label">Feed flow · BR-UP-01 · mL/min</p><span className="text-[11px] text-text-tertiary">synthetic demo data</span></div>
      <svg viewBox={`-6 -6 ${W + 12} ${H + 30}`} className="mt-4 w-full" role="img" aria-label="Feed flow for three batches; batch MES-26073 drops after 264 hours, and a 42-minute historian gap is hatched.">
        <defs><pattern id="lp-hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="6" stroke="#cbd5e1" strokeWidth="2" /></pattern></defs>
        {[14, 15, 16, 17].map(v => <line key={v} x1={0} x2={W} y1={y(v)} y2={y(v)} stroke="#eef2f6" />)}
        <rect x={x(232)} y={0} width={x(236) - x(232)} height={H} fill="url(#lp-hatch)" />
        <line x1={x(264.4)} x2={x(264.4)} y1={0} y2={H} stroke="#dc2626" strokeDasharray="3 3" />
        {TRACES.map(t => <polyline key={t.id} fill="none" stroke={t.color} strokeWidth={t.id === 'MES-26073' ? 2 : 1.4} points={t.data.map((v, i) => `${x(HOURS[i]).toFixed(1)},${y(v).toFixed(1)}`).join(' ')} />)}
        {[200, 225, 250, 275, 300].map((h, i, all) => <text key={h} x={x(h)} y={H + 18} fontSize={10} fill="#94a3b8" textAnchor={i === 0 ? 'start' : i === all.length - 1 ? 'end' : 'middle'}>{h} h</text>)}
      </svg>
      <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-[12px] text-text-secondary">
        {TRACES.map(t => <span key={t.id} className="flex items-center gap-1.5"><span className="h-0.5 w-4" style={{ background: t.color }} />{t.id}</span>)}
        <span className="flex items-center gap-1.5"><span className="h-2.5 w-3 bg-[repeating-linear-gradient(45deg,#cbd5e1_0_2px,transparent_2px_4px)]" />gap, not filled</span>
      </div>
    </div>
  );
}

function PreviewDelivery() {
  const parts = [{ label: 'Measurements', n: 1843, cls: 'bg-brand-teal' }, { label: 'Identifiers', n: 596, cls: 'bg-[#67c4ce]' }, { label: 'Flagged for review', n: 116, cls: 'bg-amber-400' }];
  return (
    <div className="lp-preview-card">
      <div className="flex items-center justify-between"><p className="lp-mini-label">October delivery · 2,555 source elements</p><span className="text-[11px] text-brand-teal">real CHO data</span></div>
      <div className="mt-5 flex h-3 overflow-hidden rounded-full bg-surface-secondary">
        {parts.map(p => <span key={p.label} className={p.cls} style={{ flexGrow: p.n, flexBasis: 0 }} />)}
      </div>
      <div className="mt-4 divide-y divide-border-hairline text-[12.5px]">
        {parts.map(p => <p key={p.label} className="flex items-center justify-between py-2.5 text-text-secondary"><span className="flex items-center gap-2.5"><span className={cn('h-2.5 w-2.5 rounded-full', p.cls)} />{p.label}</span><span className="tabular-nums text-ink">{p.n.toLocaleString('en-US')}</span></p>)}
        <p className="flex items-center justify-between py-2.5 text-text-secondary"><span className="flex items-center gap-2.5"><Check className="h-3.5 w-3.5 text-brand-teal" />Unaccounted for</span><span className="tabular-nums text-ink">0</span></p>
        <p className="flex items-center justify-between py-2.5 text-text-secondary"><span>pH 7.033 · CHO-004-R01 · 0 h</span><span className="text-brand-teal">xlsx · Process data!C2</span></p>
      </div>
    </div>
  );
}

function PreviewInvestigation() {
  const items = [
    { h: 'Tubing fatigue or slip on PM-204', state: 'Supported · not established', tone: 'text-amber-700', evidence: [['for', 'WO-8819: clamp torque changed without slip check'], ['for', 'SOP-UP-014 §7.2 requires a slip check']] },
    { h: 'Feed media lot FM-2207', state: 'Contradicted', tone: 'text-text-tertiary', evidence: [['against', 'Lot CoA: osmolality 312 mOsm/kg, within spec']] },
    { h: 'Dissolved-oxygen sensor drift', state: 'Contradicted', tone: 'text-text-tertiary', evidence: [['against', 'Probes A and B agree within 0.6%']] },
  ];
  return (
    <div className="lp-preview-card">
      <div className="flex items-center justify-between"><p className="lp-mini-label">Q-DEV-031 · candidate causes</p><span className="text-[11px] text-text-tertiary">synthetic demo data</span></div>
      <div className="mt-3 divide-y divide-border-hairline">
        {items.map(it => (
          <div key={it.h} className="py-3">
            <div className="flex items-center justify-between gap-3 text-[13px]"><span className="text-ink">{it.h}</span><span className={cn('shrink-0 text-[11.5px]', it.tone)}>{it.state}</span></div>
            <div className="mt-2 space-y-1">
              {it.evidence.map(([kind, text]) => (
                <p key={text} className="flex items-center gap-2 text-[12px] text-text-secondary">
                  <span className={cn('rounded-[3px] px-1.5 py-0.5 text-[10.5px] font-medium', kind === 'for' ? 'bg-brand-teal-light text-brand-teal-dark' : 'bg-surface-secondary text-text-tertiary')}>{kind}</span>{text}
                </p>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function PreviewPhysics() {
  return (
    <div className="lp-preview-card">
      <div className="flex items-center justify-between"><p className="lp-mini-label">Primary drying · predicted vapor load</p><span className="text-[11px] text-text-tertiary">reconstructed demo</span></div>
      <svg viewBox="0 0 400 170" className="mt-4 w-full" role="img" aria-label="Predicted batch vapor load over time. The source recipe at full loading rises above the receiving dryer's vapor limit; the lower shelf temperature and loading option stays below it.">
        {[30, 70, 110, 150].map(v => <line key={v} x1={0} x2={400} y1={v} y2={v} stroke="#eef2f6" />)}
        <line x1={0} x2={400} y1={52} y2={52} stroke="#d9a441" strokeWidth={1.4} strokeDasharray="5 4" />
        <text x={396} y={45} fontSize={10} fill="#a16207" textAnchor="end">receiving vapor limit (synthetic)</text>
        <path d="M0,150 C60,20 120,18 200,46 S330,120 400,148" fill="none" stroke="#c2410c" strokeWidth={2} />
        <path d="M0,152 C70,74 140,64 220,82 S340,132 400,150" fill="none" stroke="#0e7490" strokeWidth={2.4} />
        <path d="M0,152 C70,64 140,54 220,72 S340,126 400,150 L400,152 C340,138 220,92 140,74 C70,84 0,152 0,152 Z" fill="#0e7490" opacity={0.1} />
      </svg>
      <div className="mt-2 space-y-2 text-[12.5px]">
        <p className="flex items-center justify-between text-text-secondary"><span className="flex items-center gap-2"><span className="h-0.5 w-4 bg-[#c2410c]" />Source recipe, full loading</span><span className="flex items-center gap-1 text-red-600"><TriangleAlert className="h-3.5 w-3.5" />exceeds limit</span></p>
        <p className="flex items-center justify-between text-text-secondary"><span className="flex items-center gap-2"><span className="h-0.5 w-4 bg-brand-teal" />Lower shelf temperature and loading</span><span className="flex items-center gap-1 text-brand-teal"><Check className="h-3.5 w-3.5" />within limit</span></p>
        <p className="border-t border-border-hairline pt-2 text-[12px] text-text-tertiary">Not modeled: residual moisture, energy use, final appearance.</p>
      </div>
    </div>
  );
}

function PreviewProposal() {
  return (
    <div className="lp-preview-card">
      <div className="flex items-center justify-between"><p className="lp-mini-label">Proposal · Candidate A</p><span className="text-[11px] text-text-tertiary">synthetic demo data</span></div>
      <p className="mt-4 font-display text-[19px] font-light text-ink">Switch feed control to a mass-balance cascade, with a head-pressure interlock at 1.20 bar.</p>
      <div className="mt-4 divide-y divide-border-hairline text-[12.5px]">
        <p className="flex justify-between py-2.5 text-text-secondary"><span>Expected effect</span><span className="text-ink">+5.1 pts normalized yield (3.2–6.8)</span></p>
        <p className="flex justify-between py-2.5 text-text-secondary"><span>Basis</span><span className="text-ink">regression on 3 batches</span></p>
        <p className="flex items-center justify-between py-2.5 text-text-secondary"><span className="flex items-center gap-2"><PenLine className="h-3.5 w-3.5" />MSAT</span><span className="flex items-center gap-1 text-brand-teal"><Check className="h-3.5 w-3.5" />signed</span></p>
        <p className="flex items-center justify-between py-2.5 text-text-secondary"><span className="flex items-center gap-2"><PenLine className="h-3.5 w-3.5" />QA</span><span className="flex items-center gap-1 text-amber-700"><CircleDashed className="h-3.5 w-3.5" />pending</span></p>
        <p className="flex items-center justify-between py-2.5 text-text-secondary"><span>Written to MES, DCS or LIMS</span><span className="flex items-center gap-1 text-text-tertiary"><X className="h-3.5 w-3.5" />never from here</span></p>
      </div>
    </div>
  );
}

const TOOLS = [
  { title: 'CMO deliveries, verified', body: 'Spreadsheets, LIMS exports and certificates become one dataset. Every value links to its source cell; a verified delivery can go straight to the assistant as evidence.', preview: <PreviewDelivery /> },
  { title: 'Operations on one timeline', body: 'Batches, equipment events and lab results on a shared time axis. Gaps and imputed values are marked and kept out of statistics.', preview: <PreviewTimeline /> },
  { title: 'Investigations that show their evidence', body: 'Every candidate cause carries the records that support or contradict it, each one linked to its source.', preview: <PreviewInvestigation /> },
  { title: 'Physics-based forecasts', body: 'Mechanistic models predict the process under conditions you have not run yet, and say what they leave out.', preview: <PreviewPhysics /> },
  { title: 'Proposals with signatures', body: 'A recommendation is not an action. Named reviewers sign, and implementation still happens in your systems.', preview: <PreviewProposal /> },
];

function ToolTabs() {
  const reduced = useReducedMotion();
  const section = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState(0);
  const activeRef = useRef(0);
  useScrollFrame(section, p => {
    const i = Math.min(TOOLS.length - 1, Math.floor(p * TOOLS.length));
    section.current?.style.setProperty('--tool', ((p * TOOLS.length) % 1).toFixed(3));
    if (i !== activeRef.current) { activeRef.current = i; setActive(i); }
  }, { pinned: true, enabled: !reduced });
  const select = (i: number) => {
    const el = section.current;
    if (!el || reduced) { setActive(i); return; }
    const top = el.getBoundingClientRect().top + window.scrollY;
    window.scrollTo({ top: top + ((i + 0.5) / TOOLS.length) * (el.offsetHeight - window.innerHeight), behavior: 'smooth' });
  };
  return (
    <div ref={section} className={cn(!reduced && 'lp-tools')}>
      <div className={cn(!reduced && 'lp-tools-sticky', reduced && 'px-6')}>
        <div className="mx-auto w-full max-w-6xl">
          <h3 className="lp-h3">From partner data to signed decision.</h3>
          <div className="mt-10 grid border-y border-border-hairline md:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)]">
            <ol className="md:border-r md:border-border-hairline">
              {TOOLS.map((t, i) => (
                <li key={t.title} className="lp-tool" data-active={i === active || undefined}>
                  <button type="button" onClick={() => select(i)} aria-pressed={i === active} className="flex w-full gap-5 py-6 pr-6 text-left">
                    <span className="mt-1.5 font-mono text-[11px] text-text-muted">{String(i + 1).padStart(2, '0')}</span>
                    <span>
                      <span className="lp-tool-title block font-display text-[20px] font-light">{t.title}</span>
                      <span className="lp-tool-body mt-2 block max-w-sm text-[14px] leading-relaxed">{t.body}</span>
                    </span>
                  </button>
                  <span className="lp-tool-progress" aria-hidden />
                </li>
              ))}
            </ol>
            <div className="relative hidden min-h-[520px] bg-[#f3f4f2] md:my-6 md:ml-7 md:block">
              {TOOLS.map((t, i) => <div key={t.title} className="lp-tool-preview" data-active={i === active || undefined} aria-hidden={i !== active}>{t.preview}</div>)}
            </div>
          </div>
          <div className="mt-8 md:hidden">{TOOLS[active].preview}</div>
        </div>
      </div>
    </div>
  );
}

export function Platform() {
  return (
    <section id="platform" className="scroll-mt-24 bg-white pt-28 sm:pt-36">
      <div className="mx-6"><div className="mx-auto max-w-6xl">
        <Reveal><Eyebrow>The platform</Eyebrow></Reveal>
        <Reveal delay={80}>
          <h2 className="lp-h2 mt-6">One operating system from the plant floor to the signature. <span className="text-text-tertiary">Every claim one click from its source.</span></h2>
        </Reveal>
        <div className="mt-16 grid border-y border-border-hairline sm:grid-cols-2 lg:grid-cols-4">
          {PILLARS.map((p, i) => {
            const I = p.icon;
            return (
              <Reveal key={p.title} delay={i * 90} className={cn('py-10 sm:pr-8', i > 0 && 'lg:border-l lg:border-border-hairline lg:pl-8', i % 2 === 1 && 'sm:border-l sm:border-border-hairline sm:pl-8 lg:pl-8')}>
                <I className="h-5 w-5 text-brand-teal" strokeWidth={1.5} />
                <h3 className="mt-6 font-display text-[24px] font-light tracking-[-0.01em] text-ink">{p.title}</h3>
                <p className="mt-3 text-[14.5px] leading-relaxed text-text-secondary">{p.body}</p>
              </Reveal>
            );
          })}
        </div>
      </div></div>
      <div className="pt-10"><ToolTabs /></div>
    </section>
  );
}

/* ---------- Physics-based models ---------- */

const MODELS = [
  { name: 'Freeze drying', detail: 'Primary drying: heat transfer to the vial, mass transfer through the dried layer, ice vapor pressure and condenser capacity.', status: 'Reconstructed demonstration · not qualified' },
  { name: 'Penicillin fed-batch', detail: 'Industrial-scale growth, production, oxygen transfer and substrate balances (IndPenSim / PenSimPy).', status: 'Scored on 96 h · full 230 h batch not qualified' },
  { name: 'Antibody upstream', detail: 'A 17-state reactor and separator model of a continuous monoclonal antibody process (SMPL).', status: 'Simulation benchmark' },
  { name: 'CHO batch culture', detail: 'Glucose-limited growth and death with a substrate balance, fitted to real CHO-K1 measurements.', status: 'Tested on real data' },
];

const AB: { label: string; note: string; a: number; b: number; ci: string }[] = [
  { label: 'Antibody upstream · recipe adaptation', note: 'decision score out of 100', a: 82.5, b: 95.5, ci: '+12.9 points, 95% interval 4.5 to 23.1' },
  { label: 'Penicillin process · recipe adaptation', note: 'decision score out of 100', a: 86.3, b: 96.6, ci: '+10.3 points, 95% interval 4.0 to 18.0' },
  { label: 'Penicillin process · operating decisions', note: 'decision score out of 100', a: 88.4, b: 96.6, ci: '+8.2 points, 95% interval 3.0 to 15.0' },
  { label: 'Antibody upstream · operating decisions', note: 'decision score out of 100', a: 94.2, b: 96.7, ci: '+2.5 points, 95% interval −1.8 to 8.0' },
];

export function Physics() {
  return (
    <section id="physics" className="scroll-mt-24 bg-ink px-6 py-28 text-white sm:py-36">
      <div className="mx-auto max-w-6xl">
        <Reveal><p className="lp-eyebrow text-cyan-300">Physics-based models</p></Reveal>
        <Reveal delay={80}>
          <h2 className="lp-h2 mt-6 max-w-4xl">Predictions that follow the physics, <span className="text-cyan-300">tested in the open.</span></h2>
        </Reveal>
        <Reveal delay={140}>
          <p className="mt-7 max-w-3xl text-[17px] leading-relaxed text-white/70">Statistical models learn from the batches you have already run. Physics-based models also obey mass and heat balances, so they can forecast conditions you have not tried: a new site, a new scale, a new recipe. Each forecast records its model version, inputs and assumptions, and the agents use these models as tools.</p>
        </Reveal>

        <div className="mt-14 grid gap-px overflow-hidden rounded-[6px] border border-white/10 bg-white/10 sm:grid-cols-2 lg:grid-cols-4">
          {MODELS.map((m, i) => (
            <Reveal key={m.name} delay={i * 90} className="bg-ink p-7">
              <Atom className="h-5 w-5 text-cyan-300" strokeWidth={1.5} />
              <h3 className="mt-5 font-display text-[21px] font-light">{m.name}</h3>
              <p className="mt-3 text-[14px] leading-relaxed text-white/65">{m.detail}</p>
              <p className="mt-5 text-[11.5px] uppercase tracking-[0.12em] text-white/40">{m.status}</p>
            </Reveal>
          ))}
        </div>

        <div className="mt-24 grid gap-10 lg:grid-cols-[0.8fr_1.2fr]">
          <Reveal>
            <h3 className="font-display text-[30px] font-light leading-[1.15] tracking-[-0.02em]">The same AI, with and without a physics model.</h3>
            <p className="mt-5 text-[15px] leading-relaxed text-white/65">48 simulated situations per process, two independent sessions per arm, 1,136 of 1,152 attempts scored. Both arms saw identical data and limits; only one could run the model.</p>
            <div className="mt-6 flex gap-6 text-[12.5px] text-white/55">
              <span className="flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-full bg-white/35" />AI alone</span>
              <span className="flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-full bg-cyan-300" />AI + physics model</span>
            </div>
          </Reveal>
          <div>
            {AB.map((r, i) => (
              <Reveal key={r.label} delay={i * 80} className="border-t border-white/10 py-6 last:border-b">
                <div className="flex items-end justify-between gap-6">
                  <div><p className="text-[16px] text-white/80">{r.label}</p><p className="mt-1 text-[12px] text-white/40">{r.ci}</p></div>
                  <p className="shrink-0 font-display font-light leading-none tabular-nums"><span className="text-[26px] text-white/40">{r.a.toFixed(1)}</span><span className="mx-3 text-[20px] text-white/30">→</span><span className="text-[44px] text-cyan-300"><CountUp value={r.b} from={r.a} decimals={1} /></span></p>
                </div>
                <div className="mt-4 space-y-1.5">
                  <div className="lp-ab-bar"><span className="bg-white/30" style={{ ['--w' as string]: r.a / 100 }} /></div>
                  <div className="lp-ab-bar"><span className="bg-cyan-300" style={{ ['--w' as string]: r.b / 100 }} /></div>
                </div>
              </Reveal>
            ))}
          </div>
        </div>

        <Reveal className="mt-14 grid gap-8 border-t border-white/10 pt-10 md:grid-cols-3">
          <div><p className="text-[12px] uppercase tracking-[0.14em] text-white/45">Forecasts</p><p className="mt-3 text-[14.5px] leading-relaxed text-white/70">Mixed. Forecast error fell 9.6% for the antibody process and rose 11% for penicillin. Neither met our pre-set bar of a 20% reduction.</p></div>
          <div><p className="text-[12px] uppercase tracking-[0.14em] text-white/45">Real CHO cultures</p><p className="mt-3 text-[14.5px] leading-relaxed text-white/70">The simple growth model made glucose forecasts less accurate (mean error 0.60 → 0.72 g/L). A model this simple leaves out nutrients and stress the cells respond to.</p></div>
          <div><p className="text-[12px] uppercase tracking-[0.14em] text-white/45">What this shows</p><p className="mt-3 text-[14.5px] leading-relaxed text-white/70">In simulation the tool and the scorer share equations, so gains show the value of a correct model, not plant accuracy. No interval cleared our pre-set threshold. Model corrections and a fresh run are under way.</p></div>
        </Reveal>
      </div>
    </section>
  );
}

/* ---------- Real data ---------- */

export function RealData() {
  return (
    <section id="results" className="scroll-mt-24 bg-white px-6 py-28 sm:py-36">
      <div className="mx-auto grid max-w-6xl gap-14 lg:grid-cols-[0.9fr_1.1fr]">
        <div>
          <Reveal><Eyebrow>Working now · CMO deliveries</Eyebrow></Reveal>
          <Reveal delay={80}><h2 className="lp-h3 mt-6">Verified data from your contract manufacturers, inside the same platform.</h2></Reveal>
          <Reveal delay={140}><p className="mt-6 text-[15.5px] leading-relaxed text-text-secondary">Drop in a delivery as it arrived. The platform reads each file, traces every value to its source cell and lists what it cannot account for. Once a delivery is verified, send it to the assistant: it answers with the batch, time and source file behind each value.</p></Reveal>
          <Reveal delay={170}><p className="mt-4 text-[13.5px] leading-relaxed text-text-tertiary">Measured on 24 real CHO bioreactor runs from a published dataset, repackaged as monthly deliveries from a fictional CMO.</p></Reveal>
          <Reveal delay={200} className="mt-8 flex flex-wrap gap-3"><Link href="/cmo/?demo=1" className="lp-btn lp-btn-primary">Try the live demo<ArrowRight className="h-4 w-4" /></Link><Link href="/cmo/" className="lp-btn lp-btn-outline">Use your own files</Link></Reveal>
        </div>
        <div className="grid gap-px self-start overflow-hidden rounded-[6px] border border-border-hairline bg-border-hairline sm:grid-cols-2">
          {[
            { v: 100, s: '%', d: 0, label: 'Values verified automatically on a repeat delivery', note: '1,843 of 1,843' },
            { v: 0, s: '', d: 0, label: 'Wrong values accepted without review', note: 'scored against independent answer keys' },
            { v: 99.7, s: '%', d: 1, label: 'Verified automatically after a layout change', note: 'after one confirmation' },
            { v: 0, s: '', d: 0, label: 'Source cells left unaccounted for', note: 'every condition tested' },
          ].map((r, i) => (
            <Reveal key={r.label} delay={i * 90} className="bg-white p-7">
              <p className="font-display text-[48px] font-light leading-none text-ink"><CountUp value={r.v} decimals={r.d} suffix={r.s} /></p>
              <p className="mt-4 text-[14.5px] text-text-secondary">{r.label}</p>
              <p className="mt-1 text-[12px] text-text-tertiary">{r.note}</p>
            </Reveal>
          ))}
          <p className="bg-white p-5 text-[12px] leading-relaxed text-text-tertiary sm:col-span-2">Deterministic local processing, no model calls. Defects in the changed delivery are injected and listed. Human time saved has not been measured.</p>
        </div>
      </div>
    </section>
  );
}

/* ---------- How it works ---------- */

const STEPS = [
  { title: 'Start with the data you receive', body: 'Drop in a CMO delivery today, or connect your MES, historian, LIMS and QMS read-only. Nothing is written back, and every value keeps its source, version and timestamp.' },
  { title: 'Start from a question or an event', body: 'A deviation, a yield drop, a transfer or a partner delivery. Agents gather the evidence and show each step they took.' },
  { title: 'Review, sign, then act', body: 'Proposals carry a rationale, expected effect and required approvals. Implementation stays in your systems, with an audit trail designed to support 21 CFR Part 11.' },
];

export function How() {
  return (
    <section id="how" className="scroll-mt-24 bg-canvas px-6 py-28 sm:py-36">
      <div className="mx-auto max-w-6xl">
        <Reveal><Eyebrow>How it works</Eyebrow></Reveal>
        <Reveal delay={80}><h2 className="lp-h2 mt-6">Starts from the systems you have, <span className="text-brand-teal">without replacing any of them.</span></h2></Reveal>
        <Reveal delay={140}><p className="mt-7 max-w-2xl text-[17px] leading-relaxed text-text-secondary">No migration and no rip-and-replace. The platform reads from the systems you have already validated, and they stay the record.</p></Reveal>
        <div className="mt-16 grid gap-10 md:grid-cols-3 md:gap-8">
          {STEPS.map((s, i) => (
            <Reveal key={s.title} delay={i * 160} className="lp-step">
              <span className="lp-step-line" aria-hidden />
              <p className="mt-6 font-mono text-[12px] text-brand-teal">{String(i + 1).padStart(2, '0')}</p>
              <h3 className="mt-3 font-display text-[24px] font-light tracking-[-0.01em] text-ink">{s.title}</h3>
              <p className="mt-3 text-[15px] leading-relaxed text-text-secondary">{s.body}</p>
            </Reveal>
          ))}
        </div>
        <Reveal className="mt-10"><p className="text-[12.5px] text-text-tertiary">Validation of any deployment remains the customer’s responsibility. The platform does not claim GxP validation.</p></Reveal>
      </div>
    </section>
  );
}

/* ---------- Systems ---------- */

export function Systems() {
  return (
    <section id="systems" className="scroll-mt-24 bg-white px-6 py-28 sm:py-36">
      <div className="mx-auto max-w-6xl">
        <Reveal><Eyebrow>Systems</Eyebrow></Reveal>
        <Reveal delay={80}><h2 className="lp-h2 mt-6">Built around the systems <span className="text-brand-teal">you already run.</span></h2></Reveal>
        <div className="mt-14 grid gap-5 lg:grid-cols-[1.45fr_1fr]">
          <Reveal className="rounded-[6px] border border-border-hairline bg-canvas p-8 sm:p-10">
            <h3 className="text-[19px] font-medium text-ink">Manufacturing and quality systems</h3>
            <p className="mt-3 max-w-lg text-[15px] leading-relaxed text-text-secondary">Read-only connections that index and link records without changing them. Each source stays authoritative.</p>
            <div className="mt-10 grid grid-cols-2 gap-4 sm:grid-cols-3">
              {[['DeltaV eBR', 'Batch records'], ['OSIsoft PI', 'Historian'], ['LabWare LIMS', 'Lab results'], ['Veeva Vault QMS', 'Deviations, CAPA'], ['Maximo CMMS', 'Work orders'], ['Documentum', 'SOPs']].map(([k, v]) => (
                <div key={k} className="rounded-[4px] border border-border-hairline bg-white px-4 py-4">
                  <p className="font-display text-[18px] font-light text-ink">{k}</p><p className="mt-1 text-[12.5px] text-text-tertiary">{v}</p>
                </div>
              ))}
            </div>
            <p className="mt-6 text-[12px] text-text-tertiary">The public demo shows these connections with synthetic records.</p>
          </Reveal>
          <div className="grid gap-5">
            <Reveal delay={120} className="rounded-[6px] bg-ink p-8 text-white sm:p-10">
              <Atom className="h-5 w-5 text-cyan-300" strokeWidth={1.5} />
              <h3 className="mt-5 text-[19px] font-medium">Process models</h3>
              <p className="mt-3 text-[15px] leading-relaxed text-white/70">Registered physics-based models run beside your data. Inputs, versions and assumptions are recorded with every forecast.</p>
            </Reveal>
            <Reveal delay={220} className="rounded-[6px] bg-brand-teal p-8 text-white sm:p-10">
              <Database className="h-5 w-5 text-white/80" strokeWidth={1.5} />
              <h3 className="mt-5 text-[19px] font-medium">CMO deliveries · working now</h3>
              <p className="mt-3 text-[15px] leading-relaxed text-white/80">Excel exports, LIMS CSVs, PDF certificates and ZIP packages are read, checked and traced to their source files, then shared with the assistant as evidence.</p>
            </Reveal>
          </div>
        </div>
      </div>
    </section>
  );
}

/* ---------- Call to action and footer ---------- */

export function Closing() {
  return (
    <section className="bg-brand-teal px-6 py-24 text-white sm:py-28">
      <div className="mx-auto flex max-w-6xl flex-col items-start justify-between gap-8 md:flex-row md:items-center">
        <Reveal><h2 className="lp-h2 max-w-2xl">See the platform on a real manufacturing problem.</h2></Reveal>
        <Reveal delay={120} className="flex flex-wrap gap-3">
          <Link href="/home/" className="lp-btn bg-white text-brand-teal-dark hover:bg-brand-teal-light">Explore the platform<ArrowRight className="h-4 w-4" /></Link>
          <Link href="/cmo/?demo=1" className="lp-btn border border-white/70 text-white hover:bg-white hover:text-brand-teal-dark">Try the live demo</Link>
        </Reveal>
      </div>
    </section>
  );
}

export function Footer() {
  return (
    <div className="lp-footer-reveal">
      <div className="lp-footer-track">
        <footer className="lp-footer">
          <div className="lp-footer-art" aria-hidden />
          <div className="relative mx-6 h-full"><div className="mx-auto flex h-full max-w-6xl flex-col justify-between py-14">
            <div className="flex flex-wrap items-start justify-between gap-10">
              <div>
                <p className="font-display text-[34px] font-light tracking-[-0.02em] text-white sm:text-[44px]">Manufacturing OS</p>
                <p className="mt-2 max-w-sm text-[14px] text-white/60">The AI operating system for pharmaceutical manufacturing.</p>
              </div>
              <nav className="grid grid-cols-2 gap-x-14 gap-y-2.5 text-[14px] text-white/70" aria-label="Footer">
                <a href="#platform" className="hover:text-white">Platform</a>
                <a href="#physics" className="hover:text-white">Physics models</a>
                <a href="#results" className="hover:text-white">Results</a>
                <a href="#how" className="hover:text-white">How it works</a>
                <Link href="/home/" className="hover:text-white">Open the app</Link>
                <Link href="/cmo/?demo=1" className="hover:text-white">Live demo</Link>
              </nav>
            </div>
            <div className="space-y-2 text-[12px] leading-relaxed text-white/45">
              <p>Workspace screens use a synthetic campaign (Aster Biologics, CMP-26-10); no values come from a real facility. Demo deliveries use the CHO cultivation dataset, Zenodo record 20829178 (DOI 10.5281/zenodo.20829178), CC BY 4.0. Physics results come from the operating-challenges and physics-improvements reports of 28 October 2026. Not a validated GxP system.</p>
              <p>Photos via Wikimedia Commons, shown in greyscale: “BTEC Bioreactors” by RickLawless, CC BY 3.0; “Bioreactor Akureyri” by Fribbi, public domain; “Bioreactor in operation” by Habin Zhang, CC BY-SA 4.0.</p>
            </div>
          </div></div>
        </footer>
      </div>
    </div>
  );
}
