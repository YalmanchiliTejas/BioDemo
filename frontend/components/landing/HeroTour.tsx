'use client';

import { useRef, useState, type ReactNode } from 'react';
import Link from 'next/link';
import { Activity, ArrowDown, ArrowRight, Atom, Check, CircleDashed, ClipboardCheck, Database, GitCompareArrows, PackageCheck, TriangleAlert } from 'lucide-react';
import type { STATIONS } from './PlantScene';
import { LabStage, type StageHandle, type View } from './LabStage';
import { clamp, easeInOut, useReducedMotion, useScrollFrame } from './motion';
import { cn } from '@/lib/cn';

type Station = keyof typeof STATIONS;
type Chapter = { station: Station; zoom: number; title: string; body: string; note: string; status: 'available' | 'preview'; callout: ReactNode; place: string };

function Callout({ icon, title, children }: { icon: ReactNode; title: string; children: ReactNode }) {
  return (
    <div className="w-[min(320px,82vw)] overflow-hidden rounded-[6px] border border-black/10 bg-white text-[12px] shadow-[0_18px_40px_-18px_rgba(11,30,34,0.35)]">
      <div className="flex items-center gap-2 bg-ink px-3.5 py-2.5 text-[13px] font-medium text-white">{icon}{title}</div>
      <div className="divide-y divide-border-hairline px-3.5">{children}</div>
    </div>
  );
}
const Row = ({ label, value, tone = 'ok' }: { label: string; value?: string; tone?: 'ok' | 'open' | 'alert' | 'none' }) => (
  <div className="flex items-center justify-between gap-3 py-2 text-text-secondary">
    <span className="min-w-0 truncate">{label}</span>
    <span className={cn('flex shrink-0 items-center gap-1.5', tone === 'alert' ? 'text-red-600' : tone === 'open' ? 'text-amber-700' : 'text-text-tertiary')}>
      {value}
      {tone === 'ok' && <Check className="h-3.5 w-3.5 text-brand-teal" />}
      {tone === 'open' && <CircleDashed className="h-3.5 w-3.5" />}
      {tone === 'alert' && <TriangleAlert className="h-3.5 w-3.5" />}
    </span>
  </div>
);

const SYNTHETIC = 'Example from the synthetic demo campaign CMP-26-10.';

function StatusPill({ status }: { status: Chapter['status'] }) {
  return status === 'available'
    ? <span className="rounded-[3px] bg-brand-teal-light px-1.5 py-0.5 text-[10.5px] font-medium uppercase tracking-[0.08em] text-brand-teal-dark">Working now</span>
    : <span className="rounded-[3px] bg-surface-secondary px-1.5 py-0.5 text-[10.5px] font-medium uppercase tracking-[0.08em] text-text-tertiary">Preview · synthetic data</span>;
}

const CHAPTERS: Chapter[] = [
  {
    station: 'partners', status: 'available', zoom: 1.75, place: 'lg:left-auto lg:right-[8%] lg:top-[16%]',
    title: 'Verifies every delivery from your CMOs',
    body: 'Spreadsheets, LIMS exports and certificates become one dataset. Each value links to its source cell, and nothing is accepted or dropped without a record.',
    note: 'Measured on real CHO cell-culture data, repackaged as deliveries from a fictional CMO.',
    callout: (
      <Callout icon={<PackageCheck className="h-4 w-4" />} title="October delivery · 8 files">
        <Row label="Values verified automatically" value="1,843 / 1,843" />
        <Row label="Wrong values accepted" value="0" />
        <Row label="Source cells unaccounted for" value="0" />
        <Row label="Sent to the assistant as evidence" tone="ok" />
      </Callout>
    ),
  },
  {
    station: 'connect', status: 'preview', zoom: 1.8, place: 'lg:left-auto lg:right-[8%] lg:top-[18%]',
    title: 'Connects to the systems you already run',
    body: 'Reads batch records, historian data, lab results, deviations and work orders without changing them. Each source stays the system of record.',
    note: 'Connections in the public demo use synthetic records.',
    callout: (
      <Callout icon={<Database className="h-4 w-4" />} title="Read-only sources">
        <Row label="DeltaV eBR · batch records" value="read" />
        <Row label="OSIsoft PI · historian" value="read" />
        <Row label="LabWare LIMS · lab results" value="read" />
        <Row label="Veeva Vault QMS · deviations" value="read" />
        <Row label="Maximo CMMS · work orders" value="read" />
      </Callout>
    ),
  },
  {
    station: 'monitor', status: 'preview', zoom: 1.85, place: 'lg:left-[7%] lg:top-[16%]',
    title: 'Watches every batch on one timeline',
    body: 'Process data, lab results, maintenance and quality events line up on one time axis. Gaps in the data are shown, never filled in silently.',
    note: SYNTHETIC,
    callout: (
      <Callout icon={<Activity className="h-4 w-4" />} title="BR-UP-01 · batch MES-26073">
        <Row label="Pump head pressure (limit 1.20)" value="1.48 bar" tone="alert" />
        <Row label="Feed flow against setpoint" value="−14.2%" tone="alert" />
        <Row label="Historian gap, shown and excluded" value="42 min" tone="open" />
      </Callout>
    ),
  },
  {
    station: 'investigate', status: 'preview', zoom: 1.95, place: 'lg:left-[7%] lg:top-[14%]',
    title: 'Investigates with the evidence for and against',
    body: 'Each candidate cause lists what supports it, what contradicts it and what is still unknown. Nothing is called a root cause until people decide.',
    note: SYNTHETIC,
    callout: (
      <Callout icon={<GitCompareArrows className="h-4 w-4" />} title="Deviation Q-DEV-031">
        <Row label="Tubing fatigue or slip on PM-204" value="supported" tone="open" />
        <Row label="Feed media lot FM-2207" value="contradicted" tone="none" />
        <Row label="Dissolved-oxygen sensor drift" value="contradicted" tone="none" />
      </Callout>
    ),
  },
  {
    station: 'predict', status: 'available', zoom: 1.6, place: 'lg:left-[7%] lg:top-[18%]',
    title: 'Forecasts outcomes with physics-based models',
    body: 'Mechanistic models built on heat and mass balances predict what a change will do before anyone tries it on a batch, and state where their assumptions stop.',
    note: 'Reconstructed freeze-drying demonstration; the receiving-dryer vapor limit is synthetic.',
    callout: (
      <Callout icon={<Atom className="h-4 w-4" />} title="Primary drying · receiving dryer">
        <Row label="Source recipe, full loading" value="over limit" tone="alert" />
        <Row label="Lower shelf temp and loading" value="within" />
        <Row label="Heat and mass balances, ice vapor pressure" tone="none" />
      </Callout>
    ),
  },
  {
    station: 'act', status: 'preview', zoom: 1.75, place: 'lg:left-auto lg:right-[7%] lg:top-[38%]',
    title: 'Turns findings into proposals people sign',
    body: 'A proposal states its rationale, expected effect and required approvals. Nothing reaches the MES or control system from here.',
    note: SYNTHETIC,
    callout: (
      <Callout icon={<ClipboardCheck className="h-4 w-4" />} title="Proposal · mass-balance feed control">
        <Row label="Predicted yield effect (range)" value="+5.1 pts (3.2–6.8)" tone="none" />
        <Row label="MSAT review" value="signed" />
        <Row label="QA review" value="pending" tone="open" />
        <Row label="Changes sent to MES or DCS" value="none" tone="none" />
      </Callout>
    ),
  },
];

const INTRO = 0.08;
const END = 0.93;
const SEG = (END - INTRO) / CHAPTERS.length;
const OVERVIEW: View = { station: 'overview', zoom: 0.92 };
const keyOf = (i: number): View => (i < 0 || i >= CHAPTERS.length ? OVERVIEW : { station: CHAPTERS[i].station, zoom: CHAPTERS[i].zoom });

function Copy({ className }: { className?: string }) {
  return (
    <div className={className}>
      <h1 className="font-display text-[36px] font-light leading-[1.06] tracking-[-0.03em] text-ink sm:text-[56px] xl:text-[62px]">
        The AI operating system for <span className="text-brand-teal">pharmaceutical manufacturing.</span>
      </h1>
      <p className="mt-5 max-w-[31rem] text-[15.5px] leading-relaxed text-text-secondary sm:mt-6 sm:text-[17px]">
        Verify what your contract manufacturers send, investigate deviations with the evidence in view, and forecast process outcomes with physics-based models. Every proposed change waits for a named person to sign.
      </p>
      <div className="mt-8 flex flex-wrap gap-3">
        <Link href="/demo/" className="lp-btn lp-btn-primary">Explore the platform<ArrowRight className="h-4 w-4" /></Link>
        <a href="#platform" className="lp-btn lp-btn-outline">See how it works</a>
      </div>
      <p className="mt-5 max-w-[31rem] text-[12.5px] leading-relaxed text-text-tertiary">Working now: CMO delivery verification on real CHO data, the assistant and freeze-drying forecasts. Monitoring and investigation screens preview a synthetic campaign.</p>
    </div>
  );
}

const FORMATS = ['CMO deliveries', 'Excel trend exports', 'LIMS results', 'Certificates of analysis', 'Batch records', 'Historian tags', 'Deviations and CAPAs', 'Work orders', 'SOPs', 'Freeze drying', 'Tech transfer'];

function Marquee() {
  return (
    <div className="lp-marquee" aria-label="Areas the platform covers">
      <div className="lp-marquee-track">
        {[...FORMATS, ...FORMATS].map((f, i) => <span key={i} aria-hidden={i >= FORMATS.length}>{f}</span>)}
      </div>
    </div>
  );
}

export function HeroTour() {
  const reduced = useReducedMotion();
  const section = useRef<HTMLElement>(null);
  const sticky = useRef<HTMLDivElement>(null);
  const stage = useRef<StageHandle>(null);
  const [active, setActive] = useState(-1);
  const activeRef = useRef(-1);

  useScrollFrame(section, p => {
    let from = -1, to = -1, t = 1, chapter = -1, outro = 0;
    if (p < INTRO) { from = to = -1; }
    else if (p < END) {
      chapter = Math.min(CHAPTERS.length - 1, Math.floor((p - INTRO) / SEG));
      const local = (p - INTRO - chapter * SEG) / SEG;
      from = chapter - 1; to = chapter; t = easeInOut(clamp(local / 0.42));
    } else { outro = clamp((p - END) / (1 - END - 0.02)); from = CHAPTERS.length - 1; to = CHAPTERS.length; t = easeInOut(outro); }
    stage.current?.setView(keyOf(from), keyOf(to), t);
    const intro = Math.max(1 - p / INTRO, outro);
    const el = sticky.current;
    if (el) {
      el.style.setProperty('--intro', intro.toFixed(4));
      el.style.setProperty('--tour', clamp((p - INTRO) / (END - INTRO)).toFixed(4));
      el.style.setProperty('--route', (1 - clamp((p - INTRO) / (END - INTRO - SEG * 0.5))).toFixed(4));
    }
    if (chapter !== activeRef.current) { activeRef.current = chapter; setActive(chapter); }
  }, { pinned: true, enabled: !reduced });

  const skip = () => {
    const el = section.current;
    if (el) window.scrollTo({ top: el.offsetTop + el.offsetHeight, behavior: 'smooth' });
  };

  if (reduced) {
    return (
      <section className="px-6 pb-16 pt-32">
        <div className="mx-auto grid max-w-6xl items-center gap-10 lg:grid-cols-[1fr_1.1fr]">
          <Copy />
          <div style={{ ['--route' as string]: 0 }}><StaticScene /></div>
        </div>
        <ol className="mx-auto mt-16 grid max-w-6xl gap-px overflow-hidden rounded-[6px] border border-border-hairline bg-border-hairline sm:grid-cols-2 lg:grid-cols-3">
          {CHAPTERS.map((c, i) => (
            <li key={c.title} className="bg-white p-6">
              <p className="flex items-center gap-3"><span className="lp-step-index">{String(i + 1).padStart(2, '0')} / {String(CHAPTERS.length).padStart(2, '0')}</span><StatusPill status={c.status} /></p>
              <h2 className="mt-2 font-display text-[19px] font-light text-ink">{c.title}</h2>
              <p className="mt-2 text-[14px] leading-relaxed text-text-secondary">{c.body}</p>
              <p className="mt-2 text-[12px] text-text-tertiary">{c.note}</p>
            </li>
          ))}
        </ol>
        <div className="mx-auto mt-14 max-w-6xl"><Marquee /></div>
      </section>
    );
  }

  const current = active >= 0 ? CHAPTERS[active] : null;
  return (
    <section ref={section} className="lp-tour" aria-label="A tour of the platform">
      <div ref={sticky} className="lp-tour-sticky" data-touring={active >= 0 || undefined}>
        <div className="lp-stage">
          <LabStage ref={stage} initial={OVERVIEW} className="h-full w-full" />
        </div>
        <div className="lp-grain" aria-hidden />

        <div className="lp-hero-copy">
          <div className="mx-auto w-full max-w-6xl"><Copy className="max-w-[36rem]" /></div>
        </div>
        <div className="lp-hero-marquee"><div className="mx-auto max-w-6xl"><Marquee /></div></div>

        {CHAPTERS.map((c, i) => (
          <div key={c.title} className={cn('absolute left-1/2 top-[124px] z-20 -translate-x-1/2 lg:translate-x-0', c.place)} aria-hidden={i !== active}>
            <div className="lp-callout" data-active={i === active || undefined}>{c.callout}</div>
          </div>
        ))}

        <button type="button" onClick={skip} className="lp-skip">Skip sequence<ArrowDown className="h-3.5 w-3.5" /></button>

        <div className="lp-caption" aria-live="polite">
          {current && (
            <div key={active} className="lp-caption-inner">
              <div className="min-w-0">
                <p className="flex items-center gap-3"><span className="lp-step-index">{String(active + 1).padStart(2, '0')} / {String(CHAPTERS.length).padStart(2, '0')}</span><StatusPill status={current.status} /></p>
                <h2 className="mt-1.5 font-display text-[21px] font-light tracking-[-0.01em] text-ink sm:text-[28px]">{current.title}</h2>
                <p className="mt-1.5 text-[13.5px] leading-relaxed text-text-secondary">{current.body}</p>
                <p className="mt-1.5 text-[11.5px] text-text-tertiary">{current.note}</p>
              </div>
              <div className="lp-caption-bar" aria-hidden><span /></div>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

function StaticScene() {
  return (
    <div className="relative aspect-[4/3]">
      <LabStage still initial={OVERVIEW} anchor={0.46} className="h-full w-full" />
      <div className="lp-grain" aria-hidden />
    </div>
  );
}
