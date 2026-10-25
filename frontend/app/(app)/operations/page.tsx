'use client';

import Link from 'next/link';
import { AlertTriangle, ArrowRight, CalendarClock, Clock, Thermometer, Wind } from 'lucide-react';
import { Callout, Card, CardBody, CardHeader, ClaimTag, DemoBoundary, EvidenceChip, LinkButton, PageHeader, Pill, ProgressBar, SectionLabel, StatusDot, table, type Tone } from '@/components/ui';
import { MOCK_DATASET } from '@/fixtures/biomanufacturingData';
import { useAppContext } from '@/lib/app-context';
import { cn } from '@/lib/cn';

/* Axis: days since 2026-09-26 00:00 UTC. "Now" is the demo time, 2026-10-19 16:40 UTC (T+272.7h on MES-26073). */
const AXIS: [number, number] = [0, 36];
const NOW = 23 + 16.67 / 24;
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const dayLabel = (d: number) => {
  const dt = new Date(Date.UTC(2026, 8, 26) + d * 86400000);
  return `${MONTHS[dt.getUTCMonth()]} ${dt.getUTCDate()}`;
};
const pct = (d: number) => ((Math.max(AXIS[0], Math.min(AXIS[1], d)) - AXIS[0]) / (AXIS[1] - AXIS[0])) * 100;

type BarKind = 'completed' | 'active' | 'alert' | 'planned' | 'maintenance';
type Bar = { id: string; label: string; start: number; end: number; kind: BarKind; href?: string; detail: string };
type Lane = { id: string; name: string; equipment: string; bars: Bar[] };

const LANES: Lane[] = [
  {
    id: 'ST-01', name: 'Seed train', equipment: 'Shake flasks · WB-07 · SUB-200-02',
    bars: [
      { id: 's73', label: 'MES-26073 inoculum', start: 2.26, end: 12.33, kind: 'completed', href: '/batches/MES-26073/timeline', detail: 'WCB vial thaw to N-1 transfer' },
      { id: 's74', label: 'MES-26074 inoculum · N-1', start: 16.25, end: 30.396, kind: 'active', detail: 'N-1 expansion in SUB-200-02' },
    ],
  },
  {
    id: 'BR-UP-01', name: 'Bioreactor', equipment: '2,000 L fed-batch · PM-204 feed',
    bars: [
      { id: 'b72', label: 'MES-26072', start: -4, end: 10.33, kind: 'completed', detail: 'Completed · released' },
      { id: 'c72', label: 'CIP', start: 10.33, end: 10.85, kind: 'maintenance', detail: 'CIP/SIP turnaround' },
      { id: 'b73', label: 'MES-26073 · Phase 05 · T+264.4h', start: 12.33, end: 26.33, kind: 'alert', href: '/batches/MES-26073', detail: 'Telemetry alert · PM-204 head pressure' },
      { id: 'c73t', label: 'CIP', start: 27.333, end: 27.833, kind: 'maintenance', detail: 'CIP/SIP turnaround Fri Oct 23' },
      { id: 'c73', label: 'CIP WO-8862', start: 30.25, end: 30.583, kind: 'maintenance', href: '/planning', detail: 'Scheduled PM-204 sanitization Mon Oct 26 06:00–14:00 · overlaps MES-26074 inoculation' },
      { id: 'b74', label: 'MES-26074 (planned)', start: 30.396, end: 44.396, kind: 'planned', detail: 'Planned inoculation Mon Oct 26 09:30 UTC' },
    ],
  },
  {
    id: 'CE-01', name: 'Centrifuge', equipment: 'Disc-stack harvest',
    bars: [
      { id: 'e72', label: '26072', start: 10.42, end: 10.92, kind: 'completed', detail: 'Harvest clarified' },
      { id: 'e73', label: '26073', start: 26.833, end: 27.167, kind: 'planned', detail: 'Reserved for MES-26073 harvest' },
    ],
  },
  {
    id: 'UF-DF-02', name: 'Ultrafiltration', equipment: 'TFF skid · 30 kDa',
    bars: [
      { id: 'u72', label: 'MES-26072', start: 12.0, end: 13.5, kind: 'completed', detail: 'Concentration and buffer exchange complete' },
      { id: 'u73', label: 'MES-26073', start: 27.417, end: 27.917, kind: 'planned', detail: 'Planned after Protein A capture' },
    ],
  },
];

const BAR_CLASS: Record<BarKind, string> = {
  completed: 'bg-slate-200 text-slate-600 border border-slate-300',
  active: 'bg-brand-teal-light text-brand-teal-dark border border-cyan-300',
  alert: 'bg-status-critical-bg text-red-700 border border-red-300',
  planned: 'bg-surface text-text-tertiary border border-dashed border-border-strong',
  maintenance: 'text-amber-800 border border-amber-300',
};
const HATCH = { backgroundImage: 'repeating-linear-gradient(45deg,#fef3c7 0 4px,#fde68a 4px 6px)' };

const LEDGER = [
  { station: 'ST-01', batch: 'MES-26074', phase: 'N-1 expansion (SUB-200-02)', elapsed: 'Day 7.4 / 14.1', progress: 53, tone: 'brand' as Tone, status: { label: 'On plan', tone: 'success' as Tone }, reading: 'VCD 4.1 ×10⁶/mL · 97.8% viable', href: null as string | null },
  { station: 'BR-UP-01', batch: 'MES-26073', phase: 'Phase 05 · Fed-batch stationary', elapsed: 'T+272.7h / 336h', progress: 81.2, tone: 'critical' as Tone, status: { label: 'TELEMETRY_ALERT', tone: 'critical' as Tone }, reading: 'Head P 1.48 bar (ceiling 1.20)', href: '/batches/MES-26073' },
  { station: 'CE-01', batch: '—', phase: 'Idle · clean hold', elapsed: 'Clean hold 12.8 d of 21 d', progress: 61, tone: 'neutral' as Tone, status: { label: 'Ready', tone: 'neutral' as Tone }, reading: 'Reserved for MES-26073 harvest Oct 22', href: null },
  { station: 'UF-DF-02', batch: 'MES-26072', phase: 'Complete · released', elapsed: '100%', progress: 100, tone: 'success' as Tone, status: { label: 'Complete', tone: 'success' as Tone }, reading: 'Last run Oct 8–9', href: null },
];

const ENV = [
  { label: 'Temperature', value: '20.4', unit: '°C', limit: '18.0–22.0 °C', frac: 0.6, tone: 'success' as Tone },
  { label: 'Relative humidity', value: '42', unit: '%', limit: '30–60 %', frac: 0.4, tone: 'success' as Tone },
  { label: 'Diff. pressure to corridor', value: '+14.2', unit: 'Pa', limit: '≥ +10 Pa', frac: 0.71, tone: 'success' as Tone },
  { label: 'Particles ≥0.5 µm', value: '1,820', unit: '/m³', limit: 'In-operation limit 352,000', frac: 0.005, tone: 'success' as Tone },
  { label: 'Particles ≥5.0 µm', value: '12', unit: '/m³', limit: 'In-operation limit 2,930', frac: 0.004, tone: 'success' as Tone },
];

export default function OperationsPage() {
  const { openInspector } = useAppContext();
  const ticks = Array.from({ length: 9 }, (_, i) => i * 4);
  const inc = MOCK_DATASET.equipmentIncident;

  return (
    <div className="max-w-[1480px] mx-auto">
      <PageHeader
        frameId="OPS-01"
        crumbs={[{ label: 'Operate' }, { label: 'Operations' }, { label: 'Mesa · Suite 3B (UP-01)' }]}
        title="Operations control"
        objectId="UP-01 · Suite 3B"
        status={<Pill tone="critical" dot>BR-UP-01 · TELEMETRY_ALERT</Pill>}
        description="Where every upstream and downstream station stands right now, which batch it holds, and what needs attention. Read-only view of MES, historian and CMMS records."
        meta={<><span className="flex items-center gap-1"><Clock className="h-3 w-3" />Current step elapsed <span className="font-mono text-text-secondary">T+272.7h</span></span><span>Historian synced 16:39 UTC</span><span>MES synced 2 min ago</span><DemoBoundary compact /></>}
        actions={
          <>
            <LinkButton href="/equipment/PM-204"><AlertTriangle className="h-3.5 w-3.5 text-status-critical" /> Pump PM-204 alert</LinkButton>
            <LinkButton href="/batches/MES-26073" variant="primary">Open MES-26073 <ArrowRight className="h-3.5 w-3.5" /></LinkButton>
          </>
        }
      />

      <Callout
        tone="critical"
        className="mb-4"
        title={<span className="flex flex-wrap items-center gap-2">PM-204 head pressure 1.48 bar exceeds the 1.20 bar ceiling on BR-UP-01 <ClaimTag kind="observation" /></span>}
        action={<LinkButton href="/equipment/PM-204" size="sm" variant="danger">Inspect PM-204</LinkButton>}
      >
        Spike at T+264.4h, followed by a 14.2% drop in delivered feed flow. Alarm ALM-UP-204 acknowledged by operator; batch is on QA hold under Q-DEV-031. <EvidenceChip id="historian-up01" /> <EvidenceChip id="qms-q-dev-031" />
      </Callout>

      <Card className="mb-4">
        <CardHeader
          title="Station timeline"
          subtitle="Batch occupancy per station · Sep 26 – Nov 1, 2026 (UTC) · simplified train; Protein A and depth filtration omitted"
          actions={
            <div className="hidden md:flex items-center gap-3 text-[11px] text-text-tertiary">
              <span className="flex items-center gap-1"><span className="h-2.5 w-4 rounded-sm bg-slate-200 border border-slate-300" />Completed</span>
              <span className="flex items-center gap-1"><span className="h-2.5 w-4 rounded-sm bg-brand-teal-light border border-cyan-300" />Active</span>
              <span className="flex items-center gap-1"><span className="h-2.5 w-4 rounded-sm bg-status-critical-bg border border-red-300" />Alert</span>
              <span className="flex items-center gap-1"><span className="h-2.5 w-4 rounded-sm border border-dashed border-border-strong" />Planned</span>
              <span className="flex items-center gap-1"><span className="h-2.5 w-4 rounded-sm border border-amber-300" style={HATCH} />CIP / maintenance</span>
            </div>
          }
        />
        <div className="px-4 py-3 overflow-x-auto">
          <div className="min-w-[760px]">
            <div className="grid grid-cols-[170px_minmax(0,1fr)]">
              <div />
              <div className="relative h-5">
                {ticks.map((t) => (
                  <span key={t} className="absolute -translate-x-1/2 text-[10px] font-mono text-text-tertiary" style={{ left: `${pct(t)}%` }}>{dayLabel(t)}</span>
                ))}
              </div>
            </div>
            <div className="relative mb-5 border-b border-border-hairline">
              {LANES.map((lane) => (
                <div key={lane.id} className="grid grid-cols-[170px_minmax(0,1fr)] border-t border-border-hairline">
                  <div className="py-2 pr-3">
                    <p className="text-[12.5px] font-semibold text-text-primary flex items-center gap-1.5">
                      {lane.name}
                      {lane.id === 'BR-UP-01' && <StatusDot tone="critical" pulse />}
                    </p>
                    <p className="text-[10.5px] font-mono text-text-tertiary truncate">{lane.id} · {lane.equipment}</p>
                  </div>
                  <div className="relative h-[52px]">
                    {ticks.map((t) => <span key={t} className="absolute top-0 bottom-0 w-px bg-surface-secondary" style={{ left: `${pct(t)}%` }} aria-hidden />)}
                    {lane.bars.map((b) => {
                      const left = pct(b.start);
                      const width = Math.max(0.6, pct(b.end) - left);
                      const progress = b.kind === 'active' || b.kind === 'alert' ? Math.max(0, Math.min(100, ((NOW - b.start) / (b.end - b.start)) * 100)) : 0;
                      const body = (
                        <>
                          {progress > 0 && <span className={cn('absolute inset-y-0 left-0 rounded-l-[3px]', b.kind === 'alert' ? 'bg-red-200/70' : 'bg-cyan-200/70')} style={{ width: `${progress}%` }} aria-hidden />}
                          <span className="relative truncate px-1.5">{b.label}</span>
                        </>
                      );
                      const cls = cn('absolute top-3 h-7 rounded-[4px] flex items-center text-[11px] font-medium overflow-hidden text-left hover:ring-2 hover:ring-brand-teal/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-teal', BAR_CLASS[b.kind]);
                      const style = { left: `${left}%`, width: `${width}%`, ...(b.kind === 'maintenance' ? HATCH : {}) };
                      const title = `${b.label} · ${dayLabel(Math.max(b.start, AXIS[0]))}–${dayLabel(b.end)} · ${b.detail}`;
                      return b.href ? (
                        <Link key={b.id} href={b.href} className={cls} style={style} title={title}>{body}</Link>
                      ) : (
                        <button
                          key={b.id}
                          type="button"
                          className={cls}
                          style={style}
                          title={title}
                          onClick={() => openInspector({ type: 'AGENT_STEP', id: b.label, title: `${lane.id} · ${b.label}`, metadata: { Station: lane.id, Window: `${dayLabel(Math.max(b.start, AXIS[0]))} – ${dayLabel(b.end)}`, Status: b.kind, Note: b.detail, 'Batch record in demo': 'Not available' } })}
                        >
                          {body}
                        </button>
                      );
                    })}
                    {lane.id === 'BR-UP-01' && (
                      <Link
                        href="/planning"
                        className="absolute top-1 h-[44px] rounded-[4px] border-2 border-status-critical/70"
                        style={{ left: `${pct(30.396)}%`, width: `${Math.max(0.8, pct(30.583) - pct(30.396))}%` }}
                        title="Conflict: CIP WO-8862 overlaps MES-26074 inoculation by 4.5 h. Open planning."
                        aria-label="Schedule conflict: CIP overlaps MES-26074 inoculation by 4.5 hours. Open planning."
                      />
                    )}
                  </div>
                </div>
              ))}
              <div className="pointer-events-none absolute inset-y-0 grid grid-cols-[170px_minmax(0,1fr)] w-full">
                <div />
                <div className="relative">
                  <span className="absolute top-0 -bottom-1 w-px bg-brand-teal" style={{ left: `${pct(NOW)}%` }} />
                  <span className="absolute -bottom-5 -translate-x-1/2 rounded bg-brand-teal px-1 text-[10px] font-mono text-white whitespace-nowrap" style={{ left: `${pct(NOW)}%` }}>Now · Oct 19 16:40</span>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 px-4 py-2.5 border-t border-border-hairline bg-surface-secondary/40 text-[11.5px] text-text-tertiary">
          <CalendarClock className="h-3.5 w-3.5 text-status-critical" aria-hidden />
          <span>CIP window WO-8862 overlaps MES-26074 inoculation by <strong className="text-text-primary">4.5 h</strong> on Mon Oct 26.</span>
          <EvidenceChip id="b-cmms-wo-8862" />
          <Link href="/planning" className="text-brand-teal hover:underline">Resolve in planning</Link>
        </div>
      </Card>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <Card className="xl:col-span-2">
          <CardHeader title="Active batch & station ledger" subtitle="Each row opens the record that holds its detail" />
          <div className={table.wrap}>
            <table className={table.root}>
              <thead>
                <tr>
                  <th className={table.th}>Station</th>
                  <th className={table.th}>Batch</th>
                  <th className={table.th}>Phase / state</th>
                  <th className={cn(table.th, 'w-[180px]')}>Progress</th>
                  <th className={table.th}>Key reading</th>
                  <th className={table.th}>Status</th>
                  <th className={table.th}><span className="sr-only">Open</span></th>
                </tr>
              </thead>
              <tbody>
                {LEDGER.map((r) => (
                  <tr key={r.station} className={cn(table.tr, r.station === 'BR-UP-01' && 'bg-status-critical-bg/40')}>
                    <td className={cn(table.td, 'font-mono text-[12px]')}>{r.station}</td>
                    <td className={table.td}>
                      {r.href ? <Link href={r.href} className="font-mono text-brand-teal hover:underline">{r.batch}</Link> : <span className="font-mono text-text-secondary">{r.batch}</span>}
                    </td>
                    <td className={cn(table.td, 'text-text-secondary')}>{r.phase}</td>
                    <td className={table.td}>
                      <ProgressBar value={r.progress} tone={r.tone} label={`${r.station} progress`} />
                      <p className="mt-1 text-[10.5px] font-mono text-text-tertiary">{r.elapsed}</p>
                    </td>
                    <td className={cn(table.td, 'text-[12px]')}>
                      {r.station === 'BR-UP-01' ? (
                        <Link href="/equipment/PM-204"><Pill tone="warning" dot>PM-204 · {r.reading}</Pill></Link>
                      ) : (
                        <span className="text-text-secondary">{r.reading}</span>
                      )}
                    </td>
                    <td className={table.td}><Pill tone={r.status.tone}>{r.status.label}</Pill></td>
                    <td className={cn(table.td, 'text-right')}>
                      {r.href ? (
                        <LinkButton href={r.href} size="sm" variant="ghost" aria-label={`Open ${r.batch}`}><ArrowRight className="h-3.5 w-3.5" /></LinkButton>
                      ) : (
                        <button
                          type="button"
                          className="text-[11.5px] text-brand-teal hover:underline"
                          onClick={() => openInspector({ type: 'AGENT_STEP', id: r.station, title: `${r.station} · ${r.phase}`, metadata: { Batch: r.batch, Progress: r.elapsed, Reading: r.reading, 'Detailed record': 'Not modelled in this demo' } })}
                        >
                          Details
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 p-4 border-t border-border-hairline">
            <div>
              <SectionLabel>Open alerts</SectionLabel>
              <ul className="mt-2 space-y-2 text-[12.5px]">
                <li className="flex items-start gap-2">
                  <StatusDot tone="critical" />
                  <span className="flex-1 -mt-1"><Link href="/equipment/PM-204" className="font-medium text-text-primary hover:text-brand-teal">ALM-UP-204 · {inc.tag} head pressure high</Link><span className="block text-[11.5px] text-text-tertiary">Acknowledged T+264.6h by T. Reed · not cleared</span></span>
                </li>
                <li className="flex items-start gap-2">
                  <StatusDot tone="warning" />
                  <span className="flex-1 -mt-1"><Link href="/batches/MES-26073/timeline" className="font-medium text-text-primary hover:text-brand-teal">Historian gap · 42 min at T+182.0h</Link><span className="block text-[11.5px] text-text-tertiary">PI buffer overflow · imputed values excluded from statistics</span></span>
                </li>
                <li className="flex items-start gap-2">
                  <StatusDot tone="warning" />
                  <span className="flex-1 -mt-1"><Link href="/planning" className="font-medium text-text-primary hover:text-brand-teal">CIP / inoculation overlap · BR-UP-01</Link><span className="block text-[11.5px] text-text-tertiary">Two scenarios drafted in planning; none applied</span></span>
                </li>
              </ul>
            </div>
            <div>
              <SectionLabel>Shift</SectionLabel>
              <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-2 text-[12.5px]">
                <div><dt className="text-[11px] text-text-tertiary">Supervisor</dt><dd className="font-medium">Marcus Bell</dd></div>
                <div><dt className="text-[11px] text-text-tertiary">Operators on floor</dt><dd className="font-medium tabular-nums">4</dd></div>
                <div><dt className="text-[11px] text-text-tertiary">Next handoff</dt><dd className="font-medium">14:00 UTC</dd></div>
                <div><dt className="text-[11px] text-text-tertiary">Open eBR steps</dt><dd className="font-medium tabular-nums">2</dd></div>
              </dl>
              <Link href="/operator/handoff" className="mt-2 inline-block text-[12px] text-brand-teal hover:underline">Shift handoff notes</Link>
            </div>
          </div>
        </Card>

        <Card>
          <CardHeader
            title="Cleanroom environment"
            subtitle={`${MOCK_DATASET.facility.suite} · ${MOCK_DATASET.facility.grade}`}
            icon={<Wind className="h-4 w-4" />}
            actions={<ClaimTag kind="observation" />}
          />
          <CardBody className="space-y-3">
            {ENV.map((e) => (
              <div key={e.label}>
                <div className="flex items-baseline justify-between gap-2">
                  <p className="text-[12px] text-text-secondary">{e.label}</p>
                  <p className="tabular-nums"><span className="text-[14px] font-semibold text-text-primary">{e.value}</span> <span className="text-[11px] text-text-tertiary">{e.unit}</span></p>
                </div>
                <ProgressBar className="mt-1" value={e.frac * 100} tone={e.tone} label={`${e.label} relative to limit`} />
                <p className="mt-0.5 text-[10.5px] text-text-tertiary">{e.limit}</p>
              </div>
            ))}
            <div className="flex items-center gap-2 rounded-control border border-dashed border-border-strong px-2.5 py-2 text-[11.5px] text-text-tertiary">
              <Thermometer className="h-3.5 w-3.5 shrink-0" aria-hidden />
              Viable monitoring (settle and contact plates) is not connected; no microbial data is shown here.
            </div>
            <div className="flex flex-wrap items-center gap-2 text-[11px] text-text-tertiary">
              Last 1-min average · 08:37 UTC <EvidenceChip id="b-pi-ems-3b" />
            </div>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
