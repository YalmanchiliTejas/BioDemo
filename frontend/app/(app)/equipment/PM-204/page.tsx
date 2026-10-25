'use client';

import { useState } from 'react';
import Link from 'next/link';
import { CalendarClock, LineChart, Package, Wrench } from 'lucide-react';
import { Button, Callout, Card, CardBody, CardHeader, ClaimTag, DemoBoundary, EvidenceChip, KeyValue, LinkButton, PageHeader, Pill, Segmented, table, type Tone } from '@/components/ui';
import { PlotLegend, ScientificPlot } from '@/components/ScientificPlot';
import { ArcGauge } from '@/components/screens/b/ArcGauge';
import { ProposalFields } from '@/components/screens/b/ProposalFields';
import { ANOMALY_HOUR, BATCH_COLORS, GAP_INTERVAL, MOCK_DATASET } from '@/fixtures/biomanufacturingData';
import { feedRateSeries, headPressureSeries } from '@/fixtures/timeseries';
import { useAppContext } from '@/lib/app-context';
import { cn } from '@/lib/cn';

const WORK_ORDERS: Array<{ id: string; date: string; type: string; desc: string; status: { l: string; t: Tone }; cite: string; flag?: string; href?: string }> = [
  { id: 'WO-8862', date: 'Oct 26 06:00 (sched.)', type: 'CIP/SIP', desc: 'BR-UP-01 feed skid CIP/SIP incl. PM-204 line, 06:00–14:00', status: { l: 'Scheduled', t: 'info' }, cite: 'b-cmms-wo-8862', flag: 'Overlaps MES-26074 inoculation by 4.5 h', href: '/planning' },
  { id: 'WO-8848', date: 'Oct 23 (planned)', type: 'Corrective', desc: 'Tubing changeout + dynamic slip verification per SOP-UP-014 §7.2', status: { l: 'Awaiting approval', t: 'warning' }, cite: 'b-cmms-wo-8848' },
  { id: 'WO-8819', date: 'Oct 17 07:12', type: 'Corrective', desc: 'Occlusion clamp torque 0.42 → 0.55 N·m after audible chatter. Returned to service.', status: { l: 'Closed', t: 'neutral' }, cite: 'cmms-wo-8819', flag: 'Dynamic slip verification not performed (fixture unavailable)' },
  { id: 'WO-8790', date: 'Oct 3 13:20', type: 'Calibration', desc: 'PT-204 discharge pressure transmitter · as-found +0.3% FS (tol. ±0.5%)', status: { l: 'Closed · pass', t: 'success' }, cite: 'b-cmms-wo-8790' },
  { id: 'WO-8726', date: 'Sep 26 20:05', type: 'Preventive', desc: 'Scheduled tubing changeout · lot TS24-PT-5521 · gravimetric check −0.1%', status: { l: 'Closed · pass', t: 'success' }, cite: 'b-cmms-wo-8726' },
];

const SPARES: Array<{ item: string; part: string; loc: string; qty: number; note: string; tone: Tone }> = [
  { item: 'Tubing · size 24 platinum silicone', part: '96440-24', loc: 'Suite 3B airlock cabinet SB-3B-02', qty: 6, note: 'Gamma-irradiated · lot TS24-PT-5604 · exp. Apr 2027 · cleanroom-ready', tone: 'success' },
  { item: 'Tubing · size 24 platinum silicone', part: '96440-24', loc: 'Central warehouse WH-C-14', qty: 14, note: 'Needs transfer and wipe-down into Grade B', tone: 'neutral' },
  { item: 'L/S Easy-Load II pump head', part: '77200-62', loc: 'Maintenance crib MC-01', qty: 1, note: 'Not cleanroom-ready; transfer takes ~2 h', tone: 'warning' },
  { item: 'Pressure transmitter PT-204 spare', part: 'PT-204-SP', loc: '—', qty: 0, note: 'None in stock · lead time 10 days', tone: 'critical' },
];

export default function EquipmentPage() {
  const { openInspector } = useAppContext();
  const [scope, setScope] = useState<'73' | 'all'>('73');
  const eq = MOCK_DATASET.equipmentIncident;
  const hp = scope === '73' ? headPressureSeries.filter((s) => s.id === 'MES-26073') : headPressureSeries;
  const feed73 = feedRateSeries.find((s) => s.id === 'MES-26073')!;

  return (
    <div className="max-w-[1280px] mx-auto">
      <PageHeader
        frameId="EQP-01"
        crumbs={[{ label: 'Operate' }, { label: 'Equipment' }, { label: 'Skid BR-UP-01' }, { label: 'PM-204' }]}
        title={eq.name}
        objectId="PM-204"
        status={<Pill tone="critical" dot>Head pressure above ceiling</Pill>}
        description={`Feed pump on Skid ${eq.skid}. Live readings from the historian, maintenance history from Maximo and spare stock from SAP — all read-only.`}
        meta={<><span>Asset class: peristaltic pump · GMP critical</span><span>Suite 3B (Grade B)</span><span>Snapshot 08:26 UTC · T+264.4h</span><DemoBoundary compact /></>}
        actions={
          <>
            <LinkButton href="/planning"><CalendarClock className="h-3.5 w-3.5" /> Resolve schedule conflict</LinkButton>
            <LinkButton href="/workbench/AN-104" variant="primary"><LineChart className="h-3.5 w-3.5" /> View related yield analysis</LinkButton>
          </>
        }
      />

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4 mb-4">
        <Card className="xl:col-span-2">
          <CardHeader title="Operating state" subtitle="Last 1-min average · red tick = hard limit" actions={<><ClaimTag kind="observation" /><EvidenceChip id="historian-up01" /></>} />
          <CardBody className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <ArcGauge label="Head pressure" value={1.48} unit="bar" min={0} max={2} bandLo={0.6} bandHi={1.2} ceiling={1.2} precision={2} caption="Ceiling 1.20 bar" />
            <ArcGauge label="Tubing life expended" value={412} unit="/ 500 h" min={0} max={500} bandLo={0} bandHi={400} precision={0} status="warning" caption="OEM life 400–500 h" />
            <ArcGauge label="Motor speed" value={184.2} unit="RPM" min={0} max={240} bandLo={0} bandHi={200} ceiling={200} caption="OEM tubing limit ≤ 200" />
          </CardBody>
          <div className="px-4 pb-4 space-y-2">
            <Callout tone="critical" title="1.48 bar vs 1.20 bar ceiling · delivered feed −14.2% at constant 184.2 RPM">
              Constant speed with falling delivery means less volume per revolution. That pattern fits tubing slip or over-occlusion, but is a <strong>hypothesis</strong> under INV-104, not a confirmed failure mode. <EvidenceChip id="oem-masterflex" /> <Link href="/investigations/INV-104" className="underline">INV-104</Link>
            </Callout>
            <p className="text-[11.5px] text-text-tertiary">Tubing hours come from the CMMS run-hour counter reset at WO-8726; the tube has run across MES-26072 and MES-26073. <EvidenceChip id="b-cmms-wo-8726" /></p>
          </div>
        </Card>

        <Card>
          <CardHeader title="Asset record" icon={<Wrench className="h-4 w-4" />} />
          <CardBody>
            <KeyValue cols={2} items={[
              ['Tag', <span key="t" className="font-mono">PM-204</span>],
              ['Model', 'Masterflex L/S'],
              ['Pump head', 'Easy-Load II'],
              ['Tubing', 'Size 24 Pt-silicone'],
              ['Tubing lot', <span key="l" className="font-mono text-[12px]">TS24-PT-5521</span>],
              ['Clamp torque', '0.55 N·m'],
              ['Pressure TX', 'PT-204 · cal. Oct 3'],
              ['Governing SOP', 'SOP-UP-014 Rev 7'],
            ]} />
            <div className="mt-3 flex flex-wrap gap-2"><EvidenceChip id="sop-up-014" /><EvidenceChip id="b-cmms-wo-8790" /></div>
          </CardBody>
        </Card>
      </div>

      <Card className="mb-4">
        <CardHeader
          title="Correlated anomaly timeline"
          subtitle="Head pressure (left axis) with MES-26073 delivered feed (right axis, dashed)"
          actions={<Segmented value={scope} onChange={setScope} options={[{ value: '73', label: 'MES-26073 only' }, { value: 'all', label: 'All 3 batches' }]} />}
        />
        <div className="px-3 pt-3">
          <ScientificPlot
            batches={hp}
            variableName="Head pressure (PM-204)"
            unit="bar"
            referenceEnvelope={{ min: 0.6, max: 1.2 }}
            missingDataInterval={GAP_INTERVAL}
            markers={[{ hour: 215.2, label: 'WO-8819 clamp adj.', tone: 'warning' }, { hour: ANOMALY_HOUR, label: 'T+264.4h spike' }]}
            secondary={{ label: 'Feed rate MES-26073', unit: 'mL/min', color: '#7c3aed', dataPoints: feed73.dataPoints.filter((p) => p.elapsedHours >= 72) }}
            xDomain={[72, 280]}
            height={230}
          />
        </div>
        <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-2.5 border-t border-border-hairline">
          <PlotLegend batches={hp.map((s) => ({ id: s.id, color: BATCH_COLORS[s.id] }))} />
          <p className="text-[11.5px] text-text-tertiary flex items-center gap-2">R² = 0.941 feed loss vs head pressure — correlation across 3 batches, not causal proof <EvidenceChip id="b-calc-feed-pressure" label="Calculation" /></p>
        </div>
      </Card>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4 mb-4">
        <Card className="xl:col-span-2">
          <CardHeader title="Maximo work order ledger" subtitle="PM-204 · last 30 days and scheduled" />
          <div className={table.wrap}>
            <table className={table.root}>
              <thead><tr><th className={table.th}>Work order</th><th className={table.th}>Date (UTC)</th><th className={table.th}>Type</th><th className={table.th}>Description</th><th className={table.th}>Status</th><th className={table.th}>Source</th></tr></thead>
              <tbody>
                {WORK_ORDERS.map((w) => (
                  <tr key={w.id} className={cn(table.tr, w.id === 'WO-8819' && 'bg-status-warning-bg/50')}>
                    <td className={table.td}>
                      <button
                        type="button"
                        className="font-mono text-[12px] text-brand-teal hover:underline"
                        onClick={() => openInspector({ type: 'WORK_ORDER', id: w.id, title: w.desc, citations: [w.cite], href: w.href, metadata: { Equipment: 'PM-204', Date: w.date, Type: w.type, Status: w.status.l } })}
                      >
                        {w.id}
                      </button>
                    </td>
                    <td className={cn(table.td, 'font-mono text-[11.5px] whitespace-nowrap')}>{w.date}</td>
                    <td className={cn(table.td, 'text-[12px]')}>{w.type}</td>
                    <td className={cn(table.td, 'text-[12px] text-text-secondary min-w-[240px]')}>
                      {w.desc}
                      {w.flag && <p className={cn('mt-0.5 text-[11px]', w.id === 'WO-8862' ? 'text-red-700' : 'text-amber-800')}>{w.flag}{w.href && <> · <Link href={w.href} className="underline">resolve</Link></>}</p>}
                    </td>
                    <td className={table.td}><Pill tone={w.status.t}>{w.status.l}</Pill></td>
                    <td className={table.td}><EvidenceChip id={w.cite} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <Card>
          <CardHeader title="Spare parts availability" subtitle="SAP stock · read-only extract" icon={<Package className="h-4 w-4" />} actions={<Pill tone="warning" title="ERP extract refreshes every 4 h">2 h old</Pill>} />
          <ul className="divide-y divide-border-hairline">
            {SPARES.map((s) => (
              <li key={s.loc + s.part} className="px-4 py-2.5">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-[12.5px] font-medium text-text-primary">{s.item}</p>
                    <p className="text-[11px] text-text-tertiary"><span className="font-mono">{s.part}</span> · {s.loc}</p>
                  </div>
                  <span className={cn('shrink-0 text-[16px] font-semibold tabular-nums', s.tone === 'critical' ? 'text-status-critical' : s.tone === 'success' ? 'text-status-success' : 'text-text-primary')}>{s.qty}</span>
                </div>
                <p className="mt-0.5 text-[11px] text-text-secondary">{s.note}</p>
              </li>
            ))}
          </ul>
          <div className="px-4 py-2.5 border-t border-border-hairline text-[11px] text-text-tertiary flex flex-wrap items-center gap-2">
            Physical counts are not verified by ERP. <EvidenceChip id="b-sap-spares-3b" />
          </div>
        </Card>
      </div>

      <Card>
        <CardHeader
          title="Proposed maintenance action"
          subtitle="Drafted from INV-104 evidence · requires maintenance and QA sign-off"
          actions={<Button size="sm" variant="subtle" onClick={() => openInspector({ type: 'WORK_ORDER', id: 'WO-8848', title: 'Planned tubing changeout + slip verification', citations: ['b-cmms-wo-8848', 'sop-up-014'], metadata: { Status: 'Awaiting approval in Maximo', Window: 'Oct 23 CIP turnaround' } })}>View WO-8848</Button>}
        />
        <CardBody>
          <ProposalFields
            rationale="Tubing is inside the OEM end-of-life window, the clamp was tightened without the SOP-required slip check, and delivery fell at constant RPM."
            expected="Head pressure back below 1.20 bar and delivered feed within ±3% of setpoint at 184 RPM after changeout and verification."
            constraints="Can only run when BR-UP-01 is not in a GMP batch. Planned for the Fri 23 Oct CIP turnaround; the Mon 26 Oct 06:00–14:00 sanitization window already conflicts with MES-26074 inoculation; 6 cleanroom-ready tubes are available in the Suite 3B airlock."
            owner="K. Daniels (Maintenance) · Marcus Bell (Cleanroom Supervisor)"
            approval="Maintenance planner approval of WO-8848 in Maximo and QA concurrence under Q-DEV-031."
            wouldChange="A slip test on the removed tube showing normal delivery (points away from tubing), or a PT-204 check showing the pressure reading is biased."
          />
        </CardBody>
      </Card>
    </div>
  );
}
