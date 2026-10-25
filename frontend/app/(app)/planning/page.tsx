'use client';

import { useMemo, useState } from 'react';
import { AlertTriangle, ArrowRight, CalendarClock, Eye, Wrench } from 'lucide-react';
import { Callout, Card, CardBody, CardHeader, ClaimTag, DemoBoundary, EvidenceChip, LinkButton, PageHeader, Pill, Segmented, SectionLabel, table, type Tone } from '@/components/ui';
import { Gantt, type GanttBar } from '@/components/screens/c/Gantt';
import { useAppContext } from '@/lib/app-context';
import { cn } from '@/lib/cn';
import { AgentCanvasSlot } from '@/components/agent/AgentCanvasSlot';

// Hour 0 = Mon 2026-10-19 00:00 UTC. Window covers 9 days (through Tue 27 Oct).
const HOURS = 216;
const DAY_LABELS = ['Mon 19 Oct', 'Tue 20', 'Wed 21', 'Thu 22', 'Fri 23', 'Sat 24', 'Sun 25', 'Mon 26', 'Tue 27'];
const NOW = 16.67;
const SHIFT = 4.5;

const ROWS = [
  { id: 'BR-UP-01', sub: '2,000 L fed-batch bioreactor' },
  { id: 'PM-204', sub: 'Masterflex feed pump' },
  { id: 'PM-205', sub: 'Standby feed pump' },
  { id: 'CE-01', sub: 'Disc-stack centrifuge' },
  { id: 'UF-DF-02', sub: 'UF/DF skid' },
  { id: 'CIP', sub: 'CIP skid (shared)' },
].map((r) => ({ ...r, label: r.id }));

const BASE: GanttBar[] = [
  { id: 'b73', row: 'BR-UP-01', start: 0, end: 92, label: 'MES-26073 fed-batch end & harvest', kind: 'batch', note: 'QA hold active on lot' },
  { id: 'brcip', row: 'BR-UP-01', start: 104, end: 116, label: 'CIP/SIP BR-UP-01', kind: 'cip' },
  { id: 'media', row: 'BR-UP-01', start: 152, end: 177.5, label: 'Media fill & equilibration', kind: 'prep' },
  { id: 'b74', row: 'BR-UP-01', start: 177.5, end: 216, label: 'MES-26074 inoculation → culture', kind: 'batch' },
  { id: 'feed73', row: 'PM-204', start: 0, end: 80, label: 'Feed MES-26073', kind: 'batch' },
  { id: 'san204', row: 'PM-204', start: 174, end: 182, label: 'PM-SAN-204 sanitization', kind: 'cip', note: 'Maximo PM-SAN-204-W44' },
  { id: 'req74', row: 'PM-204', start: 177.5, end: 216, label: 'Required for MES-26074', kind: 'requirement' },
  { id: 'pm205', row: 'PM-205', start: 0, end: 216, label: 'Standby · OQ overdue · no tubing installed', kind: 'unavailable' },
  { id: 'ce73', row: 'CE-01', start: 92, end: 100, label: 'Clarify MES-26073', kind: 'batch' },
  { id: 'cecip', row: 'CE-01', start: 100, end: 104, label: 'CIP', kind: 'cip' },
  { id: 'uf73', row: 'UF-DF-02', start: 106, end: 118, label: 'UF/DF MES-26073', kind: 'batch' },
  { id: 'ufcip', row: 'UF-DF-02', start: 118, end: 122, label: 'CIP', kind: 'cip' },
  { id: 'cip1', row: 'CIP', start: 100, end: 104, label: 'CE-01', kind: 'cip' },
  { id: 'cip2', row: 'CIP', start: 104, end: 116, label: 'BR-UP-01', kind: 'cip' },
  { id: 'cip3', row: 'CIP', start: 118, end: 122, label: 'UF-DF-02', kind: 'cip' },
  { id: 'cip4', row: 'CIP', start: 174, end: 182, label: 'PM-204', kind: 'cip' },
];

type Scenario = 'none' | 'A' | 'B';

const IMPACTS: Record<'A' | 'B', Array<{ area: string; effect: string; tone: Tone; kind: 'calculated' | 'unknown' | 'observation' }>> = {
  A: [
    { area: 'Conflict', effect: 'Removed · inoculation starts after PM-SAN-204 ends (Mon 26 Oct 14:00)', tone: 'success', kind: 'calculated' },
    { area: 'MES-26074 timeline', effect: 'All downstream steps +4.5 h; harvest moves to Mon 9 Nov 14:00', tone: 'warning', kind: 'calculated' },
    { area: 'Media hold in vessel', effect: '25.5 h → 30.0 h. Validated hold limit not found in connected sources', tone: 'neutral', kind: 'unknown' },
    { area: 'Staffing', effect: 'Inoculation lands at shift handover (14:00); supervisor confirmation needed', tone: 'warning', kind: 'observation' },
    { area: 'Qualification', effect: 'No equipment substitution; no qualification impact', tone: 'success', kind: 'observation' },
  ],
  B: [
    { area: 'Conflict', effect: 'Removed · MES-26074 uses PM-205; inoculation time unchanged', tone: 'success', kind: 'calculated' },
    { area: 'Qualification', effect: 'PM-205 OQ overdue by 17 d · requires OQ re-execution or QA-approved justification', tone: 'critical', kind: 'observation' },
    { area: 'Preparation', effect: 'Tubing install + dynamic slip verification (SOP-UP-014 §7.2) ≈ 6 h before inoculation', tone: 'warning', kind: 'calculated' },
    { area: 'Batch record', effect: 'Equipment substitution in eBR needs QA approval before execution', tone: 'warning', kind: 'observation' },
    { area: 'Pump history', effect: 'PM-205 has no feed-delivery history on this process', tone: 'neutral', kind: 'unknown' },
  ],
};

export default function PlanningPage() {
  const { openInspector } = useAppContext();
  const [scenario, setScenario] = useState<Scenario>('none');

  const { bars, conflicts } = useMemo(() => {
    if (scenario === 'A') {
      const bars = BASE.map((b) => {
        if (b.id === 'media') return { ...b, end: b.end + SHIFT, kind: 'moved' as const, label: 'Media fill & equilibration (extended)' };
        if (b.id === 'b74') return { ...b, start: b.start + SHIFT, kind: 'moved' as const, label: 'MES-26074 inoculation +4.5 h' };
        if (b.id === 'req74') return { ...b, start: b.start + SHIFT };
        return b;
      });
      return { bars, conflicts: [] };
    }
    if (scenario === 'B') {
      const bars: GanttBar[] = BASE.filter((b) => b.id !== 'req74' && b.id !== 'pm205').concat([
        { id: 'pm205a', row: 'PM-205', start: 0, end: 160, label: 'Standby · OQ overdue', kind: 'unavailable' },
        { id: 'pm205prep', row: 'PM-205', start: 160, end: 177.5, label: 'OQ check + tubing install + slip verification', kind: 'prep', note: 'Requires QA decision' },
        { id: 'pm205req', row: 'PM-205', start: 177.5, end: 216, label: 'Feed MES-26074 (substituted)', kind: 'moved' },
      ]);
      return { bars, conflicts: [] };
    }
    return { bars: BASE, conflicts: [{ row: 'PM-204', start: 177.5, end: 182, label: 'Overlap 4.5 h' }] };
  }, [scenario]);

  const onBar = (b: GanttBar) =>
    openInspector({
      type: 'SCHEDULE_ITEM',
      id: b.id.toUpperCase(),
      title: b.label,
      metadata: { Resource: b.row, Start: hourToLabel(b.start), End: hourToLabel(b.end), Duration: `${(b.end - b.start).toFixed(1)} h`, ...(b.note ? { Note: b.note } : {}) },
      citations: b.row === 'PM-205' ? ['c-maximo-pm205-qual'] : b.row === 'PM-204' || b.row === 'CIP' ? ['c-maximo-cip-sched'] : undefined,
    });

  return (
    <div className="max-w-[1360px] mx-auto">
      <PageHeader
        frameId="PLAN-01"
        agent={{ label: 'Solve constraint collision', templateId: 'schedule' }}
        crumbs={[{ label: 'Operate' }, { label: 'Planning' }, { label: 'CMP-26-10 · Suite 3B' }]}
        title="Suite 3B equipment schedule"
        objectId="CMP-26-10"
        status={<Pill tone="critical" dot>1 active conflict</Pill>}
        description="Batches, CIP/SIP windows and equipment availability across the upstream and harvest skids. Built from the Maximo PM schedule and the MES planning extract; SAP ERP is not connected."
        meta={<><span>Schedule as of 06:45 UTC</span><span>Times UTC</span><DemoBoundary compact /></>}
        actions={
          <>
            <LinkButton href="/equipment/PM-204"><Wrench className="h-3.5 w-3.5" /> Inspect affected pump PM-204</LinkButton>
            <LinkButton href="/reviews/REV-01" variant="primary">Submit shift proposal <ArrowRight className="h-3.5 w-3.5" /></LinkButton>
          </>
        }
      />

      <Callout tone="critical" icon={<CalendarClock className="h-4 w-4" />} title="PM-204 sanitization overlaps MES-26074 inoculation by 4.5 h" className="mb-4">
        PM-SAN-204 runs Mon 26 Oct 06:00–14:00; MES-26074 inoculation is planned for 09:30 and needs PM-204 from that point. <EvidenceChip id="c-maximo-cip-sched" />
      </Callout>

      <AgentCanvasSlot frame="PLAN-01" className="space-y-3 mb-4" />

      <Card className="mb-4">
        <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-2.5 border-b border-border-hairline">
          <div className="flex flex-wrap items-center gap-3 text-[11.5px] text-text-secondary">
            <Legend swatch="bg-blue-100 border-blue-600" label="Batch / process" />
            <Legend swatch="bg-cyan-50 border-cyan-700" label="CIP / SIP" />
            <Legend swatch="bg-amber-100 border-amber-600" label="Preparation" />
            <Legend swatch="bg-slate-50 border-slate-400 border-dashed" label="Equipment required" />
            <Legend swatch="bg-slate-100 border-slate-400" label="Unavailable" />
            <Legend swatch="bg-red-100 border-red-600" label="Collision" />
          </div>
          <span className="flex items-center gap-2">
            <span className="text-[11.5px] text-text-tertiary">Preview</span>
            <Segmented<Scenario> value={scenario} onChange={setScenario} options={[{ value: 'none', label: 'Current plan' }, { value: 'A', label: 'Scenario A' }, { value: 'B', label: 'Scenario B' }]} />
          </span>
        </div>
        {scenario !== 'none' && (
          <div className="px-4 pt-3">
            <Callout tone="warning" icon={<Eye className="h-4 w-4" />} title={`Preview of Scenario ${scenario} — not applied to schedule`}>
              Dashed teal bars show what would move. Nothing is written to MES or Maximo.{' '}
              <button type="button" className="underline" onClick={() => setScenario('none')}>Return to current plan</button>
            </Callout>
          </div>
        )}
        <div className={cn('overflow-x-auto px-2 py-2', scenario !== 'none' && 'ring-1 ring-inset ring-amber-200')}>
          <Gantt
            rows={ROWS}
            bars={bars}
            hours={HOURS}
            startLabelDay={(d) => DAY_LABELS[d]}
            conflicts={conflicts}
            nowHour={NOW}
            onBarClick={onBar}
          />
        </div>
        <p className="px-4 py-2.5 text-[11.5px] text-text-tertiary border-t border-border-hairline">
          Click any bar for details. Previews are local to this browser; the schedule of record in MES/Maximo is unchanged.
        </p>
      </Card>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <Card className="xl:col-span-2 min-w-0">
          <CardHeader
            title="Constraint resolver sandbox"
            subtitle="Two drafted options. Select one to preview it above. Neither is applied; a proposal needs supervisor and QA review."
            actions={<ClaimTag kind="recommendation" />}
          />
          <div className="grid grid-cols-1 md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-border-hairline">
            {(['A', 'B'] as const).map((s) => (
              <div key={s} className={cn('p-4', scenario === s && 'bg-brand-teal-light/30')}>
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <SectionLabel>Scenario {s}</SectionLabel>
                    <p className="mt-1 text-[13.5px] font-semibold text-text-primary">{s === 'A' ? 'Shift MES-26074 inoculation +4.5 h' : 'Divert MES-26074 feed to standby PM-205'}</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setScenario(scenario === s ? 'none' : s)}
                    aria-pressed={scenario === s}
                    className={cn('inline-flex items-center gap-1 h-7 px-2.5 rounded-control border text-xs font-medium shrink-0', scenario === s ? 'bg-brand-teal text-white border-brand-teal' : 'border-border-strong hover:bg-surface-secondary')}
                  >
                    <Eye className="h-3.5 w-3.5" /> {scenario === s ? 'Previewing' : 'Preview'}
                  </button>
                </div>
                <ul className="mt-3 space-y-2">
                  {IMPACTS[s].map((i) => (
                    <li key={i.area} className="text-[12.5px]">
                      <div className="flex items-center gap-1.5">
                        <span className={cn('h-1.5 w-1.5 rounded-full', i.tone === 'success' ? 'bg-status-success' : i.tone === 'critical' ? 'bg-status-critical' : i.tone === 'warning' ? 'bg-status-warning' : 'bg-text-muted')} />
                        <span className="font-medium text-text-primary">{i.area}</span>
                        <ClaimTag kind={i.kind} className="!h-4 !px-1.5 !text-[9px]" />
                      </div>
                      <p className="ml-3 text-text-secondary">{i.effect}</p>
                    </li>
                  ))}
                </ul>
                {s === 'B' && (
                  <div className="mt-3 flex flex-wrap items-center gap-1.5 text-[11.5px] text-text-tertiary">
                    <AlertTriangle className="h-3.5 w-3.5 text-status-warning" aria-hidden /> PM-205 qualification status: <EvidenceChip id="c-maximo-pm205-qual" />
                  </div>
                )}
              </div>
            ))}
          </div>
          <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 border-t border-border-hairline bg-surface-secondary/40">
            <p className="text-[11.5px] text-text-tertiary">Scenario A has fewer qualification dependencies; Scenario B keeps the timeline. The trade-off is a supervisor and QA decision.</p>
            <LinkButton href="/reviews/REV-01" variant="primary" size="sm">Submit shift proposal{scenario !== 'none' ? ` (Scenario ${scenario})` : ''} <ArrowRight className="h-3 w-3" /></LinkButton>
          </div>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader title="Equipment availability" subtitle="Next 7 days" />
            <div className={table.wrap}>
              <table className={table.root}>
                <tbody>
                  {[
                    ['BR-UP-01', 'Booked', 'info', 'MES-26073 → MES-26074'],
                    ['PM-204', 'Conflict', 'critical', 'Sanitization vs inoculation'],
                    ['PM-205', 'Not ready', 'warning', 'OQ overdue · no tubing'],
                    ['CE-01', 'Available', 'success', 'After Fri 23 08:00'],
                    ['UF-DF-02', 'Available', 'success', 'After Sat 24 02:00'],
                    ['CIP skid', 'Available', 'success', '4 bookings, no overlap'],
                  ].map(([id, s, t, d]) => (
                    <tr key={id} className={table.tr}>
                      <td className={cn(table.td, 'font-mono text-[12px]')}>{id}</td>
                      <td className={table.td}><Pill tone={t as Tone} dot>{s}</Pill></td>
                      <td className={cn(table.td, 'text-[11.5px] text-text-tertiary')}>{d}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
          <Card>
            <CardHeader title="Data coverage" />
            <CardBody className="space-y-2 text-[12.5px] text-text-secondary">
              <p className="flex items-start gap-2"><ClaimTag kind="observation" /><span>PM and CIP windows from Maximo. <EvidenceChip id="c-maximo-cip-sched" /></span></p>
              <p className="flex items-start gap-2"><ClaimTag kind="unknown" /><span>Operator rosters and SAP ERP material availability are not connected, so staffing and material constraints are not checked.</span></p>
              <LinkButton href="/equipment/PM-204" size="sm" className="w-full justify-between">Inspect affected pump PM-204 <ArrowRight className="h-3 w-3" /></LinkButton>
            </CardBody>
          </Card>
        </div>
      </div>
    </div>
  );
}

function Legend({ swatch, label }: { swatch: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className={cn('h-2.5 w-4 rounded-sm border', swatch)} aria-hidden />
      {label}
    </span>
  );
}

function hourToLabel(h: number) {
  const d = Math.floor(h / 24);
  const rem = h - d * 24;
  const hh = Math.floor(rem);
  const mm = Math.round((rem - hh) * 60);
  return `${DAY_LABELS[d] ?? ''} ${String(hh).padStart(2, '0')}:${String(mm).padStart(2, '0')}`;
}
