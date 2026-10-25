'use client';

import { useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { ArrowRight, Crosshair } from 'lucide-react';
import { Card, CardBody, CardHeader, ClaimTag, DemoBoundary, EvidenceChip, LinkButton, PageHeader, Pill, table, type Tone } from '@/components/ui';
import { ANOMALY_HOUR, GAP_INTERVAL } from '@/fixtures/biomanufacturingData';
import { feedRateSeries, headPressureSeries } from '@/fixtures/timeseries';
import { useAppContext, type InspectorEntity } from '@/lib/app-context';
import { cn } from '@/lib/cn';

const X: [number, number] = [0, 280];
const pct = (h: number) => ((Math.max(X[0], Math.min(X[1], h)) - X[0]) / (X[1] - X[0])) * 100;

type TrackKey = 'ebr' | 'pi' | 'cmms' | 'lims' | 'oplog';
type Ev = {
  id: string;
  track: TrackKey;
  hour: number;
  label: string;
  detail: string;
  tone: Tone;
  type: InspectorEntity['type'];
  cite?: string;
  href?: string;
  edge?: 'before' | 'after';
};

const EVENTS: Ev[] = [
  { id: 'WO-8726', track: 'cmms', hour: 0, edge: 'before', label: 'WO-8726', detail: 'Tubing changeout on PM-204 during MES-26072 (Sep 26). Lot TS24-PT-5521 carried into this batch.', tone: 'neutral', type: 'WORK_ORDER', cite: 'b-cmms-wo-8726', href: '/equipment/PM-204' },
  { id: 'WO-8819', track: 'cmms', hour: 215.2, label: 'WO-8819', detail: 'Occlusion clamp torque 0.42 → 0.55 N·m. Dynamic slip verification not performed (SOP-UP-014 §7.2 requires it).', tone: 'warning', type: 'WORK_ORDER', cite: 'cmms-wo-8819', href: '/equipment/PM-204' },
  { id: 'WO-8848', track: 'cmms', hour: 280, edge: 'after', label: 'WO-8848 (planned)', detail: 'Planned tubing changeout + slip verification during CIP turnaround Oct 23. Awaiting approval.', tone: 'neutral', type: 'WORK_ORDER', cite: 'b-cmms-wo-8848', href: '/equipment/PM-204' },
  { id: 'QC-940', track: 'lims', hour: 72, label: 'QC-940', detail: 'VCD 5.6 ×10⁶/mL · viability 98.4%', tone: 'success', type: 'SAMPLE' },
  { id: 'QC-944', track: 'lims', hour: 168, label: 'QC-944', detail: 'Titer 1.96 g/L · HMW 1.8% · acidic variants 24.1%', tone: 'success', type: 'SAMPLE', cite: 'b-lims-cqa-panel' },
  { id: 'QC-946', track: 'lims', hour: 216, label: 'QC-946', detail: 'Glucose 4.1 g/L · lactate 1.2 g/L', tone: 'success', type: 'SAMPLE' },
  { id: 'QC-948', track: 'lims', hour: 262, label: 'QC-948 OOT', detail: 'HPLC Protein A titer 3.42 g/L (spec >3.80 g/L). Second-person review pending.', tone: 'critical', type: 'SAMPLE', cite: 'lims-qc-948', href: '/laboratory/QC-948' },
  { id: 'LOG-14', track: 'oplog', hour: 0.2, label: 'Inoc. confirmed', detail: 'Inoculation transfer confirmed by T. Reed; VCD 0.47 ×10⁶/mL.', tone: 'neutral', type: 'AGENT_STEP', cite: 'b-mes-genealogy-26073' },
  { id: 'LOG-17', track: 'oplog', hour: 120.4, label: 'Temp shift ack', detail: 'Temperature shift to 34.0 °C acknowledged.', tone: 'neutral', type: 'AGENT_STEP', cite: 'b-ebr-recipe-v4' },
  { id: 'LOG-19', track: 'oplog', hour: 182.8, label: 'PI frozen', detail: 'PI trend frozen ~40 min; local HMI normal, no alarms. Automation notified.', tone: 'warning', type: 'AGENT_STEP', cite: 'b-ebr-oplog-26073' },
  { id: 'LOG-20', track: 'oplog', hour: 212.1, label: 'Pump chatter', detail: 'Audible chatter at PM-204 head; flow PV within band. Preceded WO-8819.', tone: 'warning', type: 'AGENT_STEP', cite: 'b-ebr-oplog-26073' },
  { id: 'LOG-22', track: 'oplog', hour: 264.6, label: 'ALM-UP-204 ack', detail: 'HEAD_P HI acknowledged. Feed PV 14.5 vs SP 16.9. MSAT on-call paged.', tone: 'critical', type: 'AGENT_STEP', cite: 'b-ebr-oplog-26073' },
];

const PHASE_BARS = [
  { n: '03', name: 'Batch growth', start: 0, end: 72 },
  { n: '04', name: 'Fed-batch growth', start: 72, end: 120 },
  { n: '05', name: 'Fed-batch stationary (running)', start: 120, end: 336 },
];

const TRACKS: Array<{ key: TrackKey; name: string; system: string; h: string }> = [
  { key: 'ebr', name: 'Recipe phases', system: 'DeltaV eBR', h: 'h-11' },
  { key: 'pi', name: 'Telemetry', system: 'OSIsoft PI · feed & head P', h: 'h-20' },
  { key: 'cmms', name: 'Maintenance', system: 'Maximo CMMS', h: 'h-11' },
  { key: 'lims', name: 'QC pulls', system: 'LabWare LIMS', h: 'h-11' },
  { key: 'oplog', name: 'Operator log', system: 'eBR comments', h: 'h-11' },
];

const CHIP_TONE: Record<Tone, string> = {
  neutral: 'bg-surface border-border-strong text-text-secondary',
  success: 'bg-status-success-bg border-emerald-200 text-emerald-800',
  warning: 'bg-status-warning-bg border-amber-300 text-amber-800',
  critical: 'bg-status-critical-bg border-red-300 text-red-700',
  info: 'bg-sky-50 border-sky-200 text-sky-700',
  brand: 'bg-brand-teal-light border-cyan-200 text-brand-teal-dark',
  muted: 'bg-surface border-border-hairline text-text-tertiary',
};

const LOTS = [
  { mat: 'Tubing · size 24 platinum silicone (PM-204)', part: 'Masterflex 96440-24', lot: 'TS24-PT-5521', supplier: 'Avantor', used: 'Installed Sep 26 (MES-26072)', coa: 'Released', note: 'Carried across 2 batches' },
  { mat: 'Feed media', part: 'FM-AB014', lot: 'FM-2207', supplier: 'In-house', used: 'T+72h onward', coa: 'Released', note: 'Same lot used in MES-26072' },
  { mat: 'Basal media', part: 'BM-AB014', lot: 'BM-1184-03', supplier: 'In-house', used: 'Phase 01', coa: 'Released', note: '' },
  { mat: 'Single-use bag 2,000 L', part: 'TB-2K-STD', lot: 'TB2K-26-0419', supplier: 'Thermo Fisher', used: 'Phase 01', coa: 'Released', note: '' },
  { mat: 'Vent filter 0.2 µm', part: 'FV-0.2-10', lot: 'FV-88213', supplier: 'Sartorius', used: 'Phase 01', coa: 'Released', note: 'Integrity test pass' },
];

function nearest(series: typeof feedRateSeries, h: number) {
  const pts = series.find((s) => s.id === 'MES-26073')!.dataPoints;
  return pts.reduce((best, p) => (Math.abs(p.elapsedHours - h) < Math.abs(best.elapsedHours - h) ? p : best), pts[0]);
}

export default function BatchTimelinePage() {
  const router = useRouter();
  const { openInspector } = useAppContext();
  const [hover, setHover] = useState<number | null>(null);
  const [selected, setSelected] = useState<string | null>('WO-8819');
  const axisRef = useRef<HTMLDivElement>(null);

  const feed73 = feedRateSeries.find((s) => s.id === 'MES-26073')!.dataPoints;
  const hp73 = headPressureSeries.find((s) => s.id === 'MES-26073')!.dataPoints;
  const line = (pts: typeof feed73, lo: number, hi: number, from = 0) => {
    let d = '';
    let prevImputed = true;
    for (const p of pts) {
      if (p.elapsedHours < from || p.imputed) { prevImputed = true; continue; }
      const y = 100 - ((Math.max(lo, Math.min(hi, p.value)) - lo) / (hi - lo)) * 100;
      d += `${prevImputed ? 'M' : 'L'}${p.elapsedHours},${y.toFixed(1)}`;
      prevImputed = false;
    }
    return d;
  };
  const feedPath = useMemo(() => line(feed73, 13, 18, 72), [feed73]);
  const hpPath = useMemo(() => line(hp73, 0.7, 1.6), [hp73]);

  const onMove = (e: React.MouseEvent) => {
    const r = axisRef.current?.getBoundingClientRect();
    if (!r) return;
    const h = ((e.clientX - r.left) / r.width) * (X[1] - X[0]) + X[0];
    setHover(h >= X[0] && h <= X[1] ? h : null);
  };

  const inspect = (ev: Ev) => {
    setSelected(ev.id);
    openInspector({
      type: ev.type,
      id: ev.id,
      title: `${ev.label} · T+${ev.hour.toFixed(1)}h`,
      citations: ev.cite ? [ev.cite] : undefined,
      href: ev.href,
      metadata: { Track: TRACKS.find((t) => t.key === ev.track)!.system, 'Elapsed hour': ev.edge === 'before' ? 'Before inoculation' : ev.edge === 'after' ? 'Planned, after window' : `T+${ev.hour.toFixed(1)}h`, Detail: ev.detail },
    });
  };

  const phaseAt = (h: number) => PHASE_BARS.find((p) => h >= p.start && h < p.end);
  const sel = EVENTS.find((e) => e.id === selected);
  const ticks = [0, 40, 80, 120, 160, 200, 240, 280];

  return (
    <div className="max-w-[1480px] mx-auto">
      <PageHeader
        frameId="BATCH-02"
        crumbs={[{ label: 'Operate' }, { label: 'Batches' }, { label: 'MES-26073', href: '/batches/MES-26073' }, { label: 'Events & genealogy' }]}
        title="Batch events & genealogy"
        objectId="MES-26073"
        status={<Pill tone="critical">QA hold</Pill>}
        description="Five source systems aligned on one elapsed-time axis. Hover anywhere to move a single crosshair across all tracks; click an event to inspect its source record."
        meta={<><span>Time window <span className="font-mono text-text-secondary">0.0h to 280.0h</span></span><span>Active gap <span className="font-mono text-text-secondary">[182.0, 182.7]</span></span><span>T+0 = Oct 8 08:00 UTC</span><DemoBoundary compact /></>}
        actions={
          <>
            <LinkButton href="/processes/UP-01">Unit procedure UP-01</LinkButton>
            <LinkButton href="/batches/MES-26073" variant="primary">Back to Batch 360</LinkButton>
          </>
        }
      />

      <Card className="mb-4">
        <CardHeader
          title="Synchronized execution trace"
          subtitle="eBR · PI · CMMS · LIMS · operator log"
          actions={
            <span className="flex items-center gap-1.5 text-[11.5px] font-mono text-text-tertiary tabular-nums min-w-[90px] justify-end">
              <Crosshair className="h-3.5 w-3.5" aria-hidden /> {hover !== null ? `T+${hover.toFixed(1)}h` : '—'}
            </span>
          }
        />
        <div className="px-4 py-3 overflow-x-auto">
          <div className="min-w-[820px] relative pb-5" onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
            <div className="grid grid-cols-[180px_minmax(0,1fr)]">
              <div />
              <div className="relative h-5">
                {ticks.map((t) => (
                  <span key={t} className={cn('absolute text-[10px] font-mono text-text-tertiary', t === 0 ? '' : t === 280 ? '-translate-x-full' : '-translate-x-1/2')} style={{ left: `${pct(t)}%` }}>{t}h</span>
                ))}
              </div>
            </div>

            {TRACKS.map((tr) => (
              <div key={tr.key} className="grid grid-cols-[180px_minmax(0,1fr)] border-t border-border-hairline">
                <div className="py-1.5 pr-3 flex flex-col justify-center">
                  <p className="text-[12.5px] font-semibold text-text-primary">{tr.name}</p>
                  <p className="text-[10.5px] text-text-tertiary">{tr.system}</p>
                </div>
                <div className={cn('relative', tr.h)}>
                  {ticks.map((t) => <span key={t} className="absolute inset-y-0 w-px bg-surface-secondary" style={{ left: `${pct(t)}%` }} aria-hidden />)}

                  {tr.key === 'ebr' && PHASE_BARS.map((p) => (
                    <button
                      key={p.n}
                      type="button"
                      onClick={() => openInspector({ type: 'AGENT_STEP', id: `PH${p.n}`, title: `Phase ${p.n} · ${p.name}`, citations: ['b-ebr-recipe-v4'], href: '/processes/UP-01', metadata: { Window: `T+${p.start}h – T+${p.end}h`, Unit: 'BR-UP-01', Procedure: 'UP-01' } })}
                      className={cn('absolute top-2 h-7 rounded-[4px] border px-1.5 text-left text-[11px] font-medium truncate', p.n === '05' ? 'bg-status-critical-bg border-red-300 text-red-700' : 'bg-slate-100 border-slate-300 text-slate-600')}
                      style={{ left: `${pct(p.start)}%`, width: `${pct(p.end) - pct(p.start)}%` }}
                    >
                      {p.n} · {p.name}
                    </button>
                  ))}

                  {tr.key === 'pi' && (
                    <svg viewBox="0 0 280 100" preserveAspectRatio="none" className="absolute inset-0 h-full w-full" role="img" aria-label="Feed rate and head pressure for MES-26073">
                      <path d={hpPath} fill="none" stroke="#7c3aed" strokeWidth="1.2" vectorEffect="non-scaling-stroke" strokeDasharray="3 2" />
                      <path d={feedPath} fill="none" stroke="#dc2626" strokeWidth="1.6" vectorEffect="non-scaling-stroke" />
                    </svg>
                  )}

                  {EVENTS.filter((e) => e.track === tr.key).map((ev) => {
                    const p = pct(ev.hour);
                    const anchor = p > 88 ? '-translate-x-full' : p < 6 ? '' : '-translate-x-1/2';
                    return (
                      <button
                        key={ev.id}
                        type="button"
                        onClick={() => inspect(ev)}
                        title={ev.detail}
                        className={cn('absolute top-2 h-7 inline-flex items-center gap-1 rounded-pill border px-2 text-[11px] font-mono whitespace-nowrap shadow-sm hover:ring-2 hover:ring-brand-teal/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-teal', CHIP_TONE[ev.tone], anchor, selected === ev.id && 'ring-2 ring-brand-teal')}
                        style={{ left: `${p}%` }}
                      >
                        {ev.edge === 'before' && '◂ '}{ev.label}{ev.edge === 'after' && ' ▸'}
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}

            <div className="pointer-events-none absolute inset-0 grid grid-cols-[180px_minmax(0,1fr)]">
              <div />
              <div ref={axisRef} className="relative">
                <span
                  className="absolute top-5 bottom-5"
                  style={{ left: `calc(${pct(GAP_INTERVAL.startHour)}% - 3px)`, width: `calc(${pct(GAP_INTERVAL.endHour) - pct(GAP_INTERVAL.startHour)}% + 6px)`, backgroundImage: 'repeating-linear-gradient(45deg,rgba(254,243,199,.85) 0 3px,rgba(245,158,11,.55) 3px 4px)' }}
                  title={GAP_INTERVAL.annotation}
                />
                <span className="absolute top-5 bottom-5 w-[2px] bg-status-critical" style={{ left: `${pct(ANOMALY_HOUR)}%` }} />
                <span className="absolute bottom-0 -translate-x-1/2 text-[10px] font-semibold text-red-700 whitespace-nowrap" style={{ left: `${pct(ANOMALY_HOUR)}%` }}>T+264.4h spike</span>
                {hover !== null && <span className="absolute top-5 bottom-5 w-px bg-slate-900/40" style={{ left: `${pct(hover)}%` }} />}
              </div>
            </div>
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3 px-4 py-2.5 border-t border-border-hairline bg-surface-secondary/40 text-[12px]">
          {hover !== null ? (
            <>
              <p><span className="text-text-tertiary">Phase </span><span className="font-medium">{phaseAt(hover) ? `${phaseAt(hover)!.n} · ${phaseAt(hover)!.name}` : '—'}</span></p>
              <p className="tabular-nums"><span className="text-text-tertiary">Feed </span><span className="font-medium" style={{ color: '#dc2626' }}>{hover >= 72 ? `${nearest(feedRateSeries, hover).value.toFixed(2)} mL/min` : 'not started'}</span>{hover >= GAP_INTERVAL.startHour && hover <= GAP_INTERVAL.endHour && <span className="ml-1 text-amber-700">imputed</span>}</p>
              <p className="tabular-nums"><span className="text-text-tertiary">Head P </span><span className="font-medium" style={{ color: '#7c3aed' }}>{nearest(headPressureSeries, hover).value.toFixed(2)} bar</span></p>
              <p className="text-text-tertiary">Events ±4h: <span className="text-text-primary">{EVENTS.filter((e) => !e.edge && Math.abs(e.hour - hover) <= 4).map((e) => e.label).join(', ') || 'none'}</span></p>
            </>
          ) : (
            <p className="md:col-span-4 text-text-tertiary flex flex-wrap items-center gap-3">
              <span className="flex items-center gap-1.5"><span className="h-0.5 w-4 bg-[#dc2626]" />Feed rate (13–18 mL/min scale)</span>
              <span className="flex items-center gap-1.5"><span className="h-0.5 w-4 border-t border-dashed border-[#7c3aed]" />Head pressure (0.7–1.6 bar scale)</span>
              <span className="flex items-center gap-1.5"><span className="h-2.5 w-4 rounded-sm" style={{ background: 'repeating-linear-gradient(45deg,#fef3c7 0 3px,#f59e0b 3px 4px)' }} />No telemetry (gap not drawn, not imputed here)</span>
              <span>Hover to read values</span>
            </p>
          )}
        </div>
      </Card>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4 mb-4">
        <Card className="xl:col-span-2">
          <CardHeader title="Event ledger" subtitle={`${EVENTS.length} events · click a row to inspect, or open the owning record`} />
          <div className={table.wrap}>
            <table className={table.root}>
              <thead><tr><th className={table.th}>When</th><th className={table.th}>Event</th><th className={table.th}>System</th><th className={table.th}>Detail</th><th className={table.th}>Source</th><th className={table.th}><span className="sr-only">Open</span></th></tr></thead>
              <tbody>
                {[...EVENTS].sort((a, b) => (a.edge === 'before' ? -1 : b.edge === 'before' ? 1 : a.hour - b.hour)).map((ev) => (
                  <tr key={ev.id} className={cn(table.tr, 'cursor-pointer', selected === ev.id && 'bg-brand-teal-light/50')} onClick={() => setSelected(ev.id)}>
                    <td className={cn(table.td, 'font-mono text-[11.5px] whitespace-nowrap')}>{ev.edge === 'before' ? 'Sep 26' : ev.edge === 'after' ? 'Oct 23 (plan)' : `T+${ev.hour.toFixed(1)}h`}</td>
                    <td className={table.td}><Pill tone={ev.tone}>{ev.label}</Pill></td>
                    <td className={cn(table.td, 'text-[12px] text-text-secondary whitespace-nowrap')}>{TRACKS.find((t) => t.key === ev.track)!.system}</td>
                    <td className={cn(table.td, 'text-[12px] text-text-secondary min-w-[240px]')}>{ev.detail}</td>
                    <td className={table.td} onClick={(e) => e.stopPropagation()}>{ev.cite ? <EvidenceChip id={ev.cite} /> : <span className="text-[11px] text-text-muted">LIMS summary only</span>}</td>
                    <td className={cn(table.td, 'text-right')} onClick={(e) => e.stopPropagation()}>
                      {ev.href ? <Link href={ev.href} className="text-[12px] text-brand-teal hover:underline whitespace-nowrap">Open {ev.href.split('/').pop()}</Link> : <button className="text-[12px] text-brand-teal hover:underline" onClick={() => inspect(ev)}>Inspect</button>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <Card>
          <CardHeader title="Selected event" />
          <CardBody>
            {sel ? (
              <div className="space-y-2.5 text-[12.5px]">
                <div className="flex flex-wrap items-center gap-2"><Pill tone={sel.tone}>{sel.label}</Pill><ClaimTag kind="observation" /></div>
                <p className="text-text-secondary leading-relaxed">{sel.detail}</p>
                {sel.id === 'WO-8819' && (
                  <p className="text-[12px] text-text-secondary"><ClaimTag kind="hypothesis" className="mr-1" />Over-occlusion after this adjustment is one candidate explanation for the later pressure rise; it is under review in INV-104, not established.</p>
                )}
                <div className="flex flex-wrap gap-2">
                  {sel.cite && <EvidenceChip id={sel.cite} />}
                  {sel.href && <LinkButton href={sel.href} size="sm" variant="primary">Open {sel.href.split('/').pop()} <ArrowRight className="h-3 w-3" /></LinkButton>}
                </div>
              </div>
            ) : (
              <p className="text-xs text-text-tertiary">Select an event in the trace or ledger.</p>
            )}
          </CardBody>
        </Card>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-5 gap-4">
        <Card className="xl:col-span-3">
          <CardHeader title="Inoculum lineage" subtitle="Working cell bank vial to production bioreactor" actions={<EvidenceChip id="b-mes-genealogy-26073" label="Genealogy report" />} />
          <div className="p-3 overflow-x-auto">
            <svg viewBox="0 0 860 150" className="w-full min-w-[640px]" role="group" aria-label="Inoculum lineage tree">
              {(() => {
                const nodes = [
                  { id: 'wcb', x: 0, y: 53, t1: 'WCB-AB014-0217', t2: 'Vial 112 · thaw Sep 28' },
                  { id: 'n4a', x: 145, y: 15, t1: 'SF-0928-A', t2: 'N-4 · 250 mL' },
                  { id: 'n4b', x: 145, y: 91, t1: 'SF-0928-B', t2: 'N-4 · 250 mL' },
                  { id: 'n3', x: 290, y: 53, t1: 'SF-1001-C', t2: 'N-3 · 3 L flask' },
                  { id: 'n2', x: 435, y: 53, t1: 'WB-07', t2: 'N-2 · 20 L rocking' },
                  { id: 'n1', x: 580, y: 53, t1: 'SUB-200-02', t2: 'N-1 · 200 L SUB' },
                  { id: 'br', x: 725, y: 53, t1: 'BR-UP-01', t2: 'Production 2,000 L' },
                ];
                const W = 130, Hn = 44;
                const n = Object.fromEntries(nodes.map((d) => [d.id, d]));
                const edges = [['wcb', 'n4a'], ['wcb', 'n4b'], ['n4a', 'n3'], ['n4b', 'n3'], ['n3', 'n2'], ['n2', 'n1'], ['n1', 'br']];
                return (
                  <>
                    {edges.map(([a, b]) => {
                      const s = n[a], e = n[b];
                      const x1 = s.x + W, y1 = s.y + Hn / 2, x2 = e.x, y2 = e.y + Hn / 2, mx = (x1 + x2) / 2;
                      return <path key={a + b} d={`M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`} fill="none" stroke="#cbd5e1" strokeWidth="1.5" />;
                    })}
                    {nodes.map((d) => {
                      const isBr = d.id === 'br';
                      return (
                        <g
                          key={d.id}
                          role={isBr ? 'link' : undefined}
                          tabIndex={isBr ? 0 : undefined}
                          aria-label={isBr ? 'BR-UP-01 production unit operation, open process UP-01' : undefined}
                          className={isBr ? 'cursor-pointer focus:outline-none' : undefined}
                          onClick={isBr ? () => router.push('/processes/UP-01') : () => openInspector({ type: 'SAMPLE', id: d.t1, title: `${d.t1} · ${d.t2}`, citations: ['b-mes-genealogy-26073'], metadata: { Stage: d.t2 } })}
                          onKeyDown={isBr ? (e) => { if (e.key === 'Enter') router.push('/processes/UP-01'); } : undefined}
                          style={{ cursor: 'pointer' }}
                        >
                          <rect x={d.x} y={d.y} width={W} height={Hn} rx="6" fill={isBr ? '#ecfeff' : '#ffffff'} stroke={isBr ? '#0e7490' : '#cbd5e1'} strokeWidth={isBr ? 1.5 : 1} />
                          <text x={d.x + 8} y={d.y + 18} fontSize="11" fontWeight="600" fill="#0f172a" fontFamily="JetBrains Mono, monospace">{d.t1}</text>
                          <text x={d.x + 8} y={d.y + 33} fontSize="10" fill="#64748b">{d.t2}</text>
                        </g>
                      );
                    })}
                  </>
                );
              })()}
            </svg>
            <p className="px-1 pt-1 text-[11.5px] text-text-tertiary">Select <span className="font-mono">BR-UP-01</span> to open the unit procedure. Other nodes open their genealogy record in the inspector.</p>
          </div>
        </Card>

        <Card className="xl:col-span-2">
          <CardHeader title="Single-use & raw material lots" subtitle="Scanned into eBR at point of use" actions={<EvidenceChip id="b-ebr-material-lots" label="Material scans" />} />
          <div className={table.wrap}>
            <table className={table.root}>
              <thead><tr><th className={table.th}>Material</th><th className={table.th}>Lot</th><th className={table.th}>CoA</th></tr></thead>
              <tbody>
                {LOTS.map((l) => (
                  <tr key={l.lot} className={table.tr}>
                    <td className={cn(table.td, 'text-[12px]')}>
                      <p className="text-text-primary">{l.mat}</p>
                      <p className="text-[10.5px] text-text-tertiary">{l.part} · {l.supplier} · {l.used}</p>
                      {l.note && <p className="text-[10.5px] text-amber-700">{l.note}</p>}
                    </td>
                    <td className={cn(table.td, 'font-mono text-[11.5px]')}>{l.lot === 'FM-2207' ? <EvidenceChip id="lims-media-lot" label="FM-2207" /> : l.lot}</td>
                    <td className={table.td}><Pill tone="success">{l.coa}</Pill></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </div>
  );
}
