'use client';

import { useState } from 'react';
import Link from 'next/link';
import { ArrowRight, Check, FileText, FlaskConical, GitBranch, GitCompareArrows, History } from 'lucide-react';
import { Callout, Card, CardBody, CardHeader, ClaimTag, DemoBoundary, EvidenceChip, Hash, KeyValue, LinkButton, PageHeader, Pill, SectionLabel, Stat, Tabs, table, type ClaimKind, type Tone } from '@/components/ui';
import { PlotLegend, ScientificPlot } from '@/components/ScientificPlot';
import { ANOMALY_HOUR, BATCH_COLORS, BATCH_MANIFEST_HASH, GAP_INTERVAL, MOCK_DATASET } from '@/fixtures/biomanufacturingData';
import { feedRateSeries, headPressureSeries, yieldSeries } from '@/fixtures/timeseries';
import { useAppContext } from '@/lib/app-context';
import { cn } from '@/lib/cn';

const PHASES = [
  { n: '01', name: 'Media charge', window: 'Oct 7' },
  { n: '02', name: 'Inoculation', window: 'T+0h' },
  { n: '03', name: 'Batch growth', window: '0–72h' },
  { n: '04', name: 'Fed-batch growth', window: '72–120h' },
  { n: '05', name: 'Fed-batch stationary', window: '120–336h' },
  { n: '06', name: 'Harvest', window: 'Oct 22' },
  { n: '07', name: 'Transfer & CIP', window: 'Oct 22–23' },
];
const CURRENT = 4;

type Step = { step: string; desc: string; start: string; dur: string; status: { label: string; tone: Tone }; kind: ClaimKind; cite?: string };
const STEPS: Step[] = [
  { step: '01.2', desc: 'Basal media BM-1184-03 charged, 1,620 L; equilibrated 36.8 °C', start: 'Oct 7 14:10', dur: '17.8 h', status: { label: 'Complete', tone: 'success' }, kind: 'observation', cite: 'b-ebr-material-lots' },
  { step: '02.1', desc: 'Inoculation from N-1 SUB-200-02 · VCD 0.47 ×10⁶/mL', start: 'T+0.0h', dur: '0.6 h', status: { label: 'Complete', tone: 'success' }, kind: 'observation', cite: 'b-mes-genealogy-26073' },
  { step: '04.1', desc: 'Feed start · PM-204 setpoint 16.90 mL/min (FM-2207)', start: 'T+72.0h', dur: '—', status: { label: 'Complete', tone: 'success' }, kind: 'observation', cite: 'b-ebr-material-lots' },
  { step: '05.1', desc: 'Temperature shift 36.8 → 34.0 °C', start: 'T+120.0h', dur: '1.4 h', status: { label: 'Complete', tone: 'success' }, kind: 'observation', cite: 'b-ebr-recipe-v4' },
  { step: '—', desc: 'Historian gap: no PI records for 42 min (PI buffer overflow)', start: 'T+182.0h', dur: '0.7 h', status: { label: 'Data gap', tone: 'warning' }, kind: 'imputed', cite: 'historian-gap' },
  { step: '05.3', desc: 'Daily glucose bolus · day 9', start: 'T+216.0h', dur: '0.3 h', status: { label: 'Complete', tone: 'success' }, kind: 'observation', cite: 'ebr-mes-26073' },
  { step: '05.4', desc: 'Bolus nutrient addition · feed PV 14.48 vs SP 16.90 mL/min (−14.3%)', start: 'T+264.0h', dur: 'Running', status: { label: 'Deviation', tone: 'critical' }, kind: 'observation', cite: 'ebr-mes-26073' },
  { step: '05.5', desc: 'Day 11 in-process sample QC-948 pulled', start: 'T+262.0h', dur: '—', status: { label: 'Result OOT', tone: 'critical' }, kind: 'observation', cite: 'lims-qc-948' },
];

const SAMPLES = [
  { id: 'QC-940', day: 'Day 3 · T+72h', test: 'VCD / viability', result: '5.6 ×10⁶/mL · 98.4%', spec: 'Trend only', status: { l: 'Reviewed', t: 'success' as Tone } },
  { id: 'QC-944', day: 'Day 7 · T+168h', test: 'Titer · SEC · CEX', result: '1.96 g/L · HMW 1.8% · acidic 24.1%', spec: 'HMW ≤3.0% · acidic 18–30%', status: { l: 'Reviewed', t: 'success' as Tone } },
  { id: 'QC-946', day: 'Day 9 · T+216h', test: 'Metabolites', result: 'Glc 4.1 g/L · Lac 1.2 g/L', spec: 'Trend only', status: { l: 'Reviewed', t: 'success' as Tone } },
  { id: 'QC-948', day: 'Day 11 · T+262h', test: 'HPLC Protein A titer', result: '3.42 g/L', spec: '>3.80 g/L', status: { l: 'OOT · review pending', t: 'critical' as Tone } },
  { id: 'QC-952', day: 'Harvest · planned', test: 'Titer · glycan · HCP', result: '—', spec: 'Release panel', status: { l: 'Not pulled', t: 'muted' as Tone } },
];

const DOCS = [
  { id: 'eBR MES-26073', type: 'Electronic batch record', sys: 'DeltaV eBR', state: 'In execution', cite: 'ebr-mes-26073' },
  { id: 'RCP-AB014-V4', type: 'Master recipe', sys: 'DeltaV eBR', state: 'Effective', cite: 'b-ebr-recipe-v4' },
  { id: 'SOP-UP-014 Rev 7', type: 'Standard operating procedure', sys: 'Documentum', state: 'Effective', cite: 'sop-up-014' },
  { id: 'Q-DEV-031', type: 'Deviation · Major Tier 2', sys: 'Veeva Vault QMS', state: 'Open', cite: 'qms-q-dev-031', href: '/quality/Q-DEV-031' },
  { id: 'WO-8819', type: 'Work order', sys: 'Maximo CMMS', state: 'Closed', cite: 'cmms-wo-8819', href: '/equipment/PM-204' },
  { id: 'DOC-UP01-03', type: 'Investigation summary (draft)', sys: 'Sievance', state: 'Draft · unsigned', href: '/documents/DOC-UP01-03' },
];

const ACTIVITY = [
  { t: 'Oct 19 12:20', who: 'MSAT Yield Sentry (agent)', what: 'Computed feed loss vs head pressure correlation for AN-104', kind: 'calculated' as ClaimKind },
  { t: 'Oct 19 11:40', who: 'M. Okafor', what: 'Entered QC-948 titer 3.42 g/L; flagged OOT; second-person review pending', kind: 'observation' as ClaimKind },
  { t: 'Oct 19 09:05', who: 'Priya Natarajan', what: 'Opened deviation Q-DEV-031 and placed batch on QA hold', kind: 'approved' as ClaimKind },
  { t: 'Oct 19 08:37', who: 'T. Reed', what: 'Acknowledged ALM-UP-204 HEAD_P HI; paged MSAT on-call', kind: 'observation' as ClaimKind },
  { t: 'Oct 17 07:12', who: 'K. Daniels (maintenance)', what: 'Closed WO-8819 clamp torque adjustment without dynamic slip check', kind: 'observation' as ClaimKind },
  { t: 'Oct 15 14:42', who: 'PI interface', what: 'Collection resumed after 42-min buffer overflow', kind: 'observation' as ClaimKind },
];

export default function BatchPage() {
  const { openInspector } = useAppContext();
  const [tab, setTab] = useState('overview');
  const [hover, setHover] = useState<number | null>(null);
  const b73 = MOCK_DATASET.activeCampaign.batches[2];
  const target = MOCK_DATASET.activeCampaign.targetYieldIndex;
  const only73 = <T extends { id: string }>(s: T[]) => s.filter((x) => x.id === 'MES-26073');

  const openSample = (id: string) =>
    openInspector({ type: 'SAMPLE', id, title: `Sample ${id}`, metadata: Object.fromEntries(Object.entries(SAMPLES.find((s) => s.id === id) ?? {}).filter(([, v]) => typeof v === 'string')) as Record<string, string>, citations: id === 'QC-944' ? ['b-lims-cqa-panel'] : undefined });

  return (
    <div className="max-w-[1280px] mx-auto">
      <PageHeader
        frameId="BATCH-01"
        crumbs={[{ label: 'Operate' }, { label: 'Batches' }, { label: 'CMP-26-10' }, { label: 'MES-26073' }]}
        title="Batch 360"
        objectId="MES-26073"
        status={<><Pill tone="info" dot>In execution</Pill><Pill tone="critical">QA hold · Q-DEV-031</Pill></>}
        description={`${MOCK_DATASET.activeCampaign.molecule} · BR-UP-01 2,000 L · Stage: Fed-Batch Stationary (Day 11/14)`}
        meta={<><span>ISA-88 procedure UP-01 · recipe RCP-AB014-V4</span><span>Inoculated Oct 8 08:00 UTC</span><span className="flex items-center gap-1">Manifest <Hash value={BATCH_MANIFEST_HASH} /></span><DemoBoundary compact /></>}
        actions={
          <>
            <LinkButton href="/batches/MES-26073/timeline"><GitBranch className="h-3.5 w-3.5" /> View events & genealogy</LinkButton>
            <LinkButton href="/investigations/INV-104"><GitCompareArrows className="h-3.5 w-3.5" /> Inspect investigation INV-104</LinkButton>
            <LinkButton href="/workbench/AN-104" variant="primary">Compare batches in Workbench <ArrowRight className="h-3.5 w-3.5" /></LinkButton>
          </>
        }
      />

      <Card className="mb-4">
        <div className="px-4 pt-3 flex items-center justify-between">
          <SectionLabel>Recipe phases · RCP-AB014-V4</SectionLabel>
          <EvidenceChip id="b-ebr-recipe-v4" label="Master recipe V4" />
        </div>
        <ol className="flex flex-wrap md:flex-nowrap gap-1 p-4 pt-2.5" aria-label="Recipe phase progress">
          {PHASES.map((p, i) => {
            const done = i < CURRENT;
            const cur = i === CURRENT;
            return (
              <li
                key={p.n}
                aria-current={cur ? 'step' : undefined}
                className={cn(
                  'flex-1 min-w-[120px] rounded-control border px-2.5 py-2',
                  done && 'bg-surface-secondary border-border-hairline',
                  cur && 'bg-status-critical-bg border-red-300 ring-1 ring-red-200',
                  !done && !cur && 'bg-surface border-dashed border-border-strong',
                )}
              >
                <div className="flex items-center gap-1.5">
                  <span className={cn('h-4 w-4 rounded-full flex items-center justify-center text-[9px] font-mono', done ? 'bg-status-success text-white' : cur ? 'bg-status-critical text-white' : 'border border-border-strong text-text-tertiary')}>
                    {done ? <Check className="h-2.5 w-2.5" /> : p.n}
                  </span>
                  <span className="text-[10.5px] font-mono text-text-tertiary">{p.window}</span>
                </div>
                <p className={cn('mt-1 text-[12px] font-medium leading-tight', cur ? 'text-red-800' : done ? 'text-text-secondary' : 'text-text-tertiary')}>{p.name}</p>
                {cur && <p className="mt-0.5 text-[10.5px] text-red-700">Running · step 05.4 deviation</p>}
              </li>
            );
          })}
        </ol>
      </Card>

      <Tabs
        className="mb-4"
        active={tab}
        onChange={setTab}
        tabs={[
          { key: 'overview', label: 'Overview' },
          { key: 'timeline', label: 'Timeline' },
          { key: 'trends', label: 'Process trends' },
          { key: 'quality', label: 'Quality & samples', count: SAMPLES.length },
          { key: 'genealogy', label: 'Genealogy' },
          { key: 'documents', label: 'Documents', count: DOCS.length },
          { key: 'activity', label: 'Activity' },
        ]}
      />

      {tab === 'overview' && (
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
          <div className="xl:col-span-2 space-y-4">
            <Card>
              <CardHeader title="Yield position" subtitle="Normalized yield index to date vs campaign target and prior batches" actions={<EvidenceChip id="historian-up01" />} />
              <CardBody className="grid grid-cols-2 md:grid-cols-4 gap-4 border-b border-border-hairline">
                <Stat label="Yield index" value={b73.normalizedYield.toFixed(1)} delta={`−${(target - b73.normalizedYield).toFixed(1)} vs ${target.toFixed(1)}`} deltaTone="critical" kind="calculated" />
                <Stat label="vs MES-26071" value="−5.3" unit="pts" hint="81.2 → 78.4 → 75.9" kind="calculated" />
                <Stat label="Feed droop" value="−14.2" unit="%" delta="after T+264.4h" deltaTone="warning" kind="observation" />
                <Stat label="Feed delivered" value={b73.feedDeliveryL.toFixed(1)} unit="L" hint="to date · Day 11 of 14" kind="observation" />
              </CardBody>
              <div className="px-3 pt-3 pb-2">
                <ScientificPlot
                  batches={yieldSeries}
                  variableName="Normalized yield index"
                  unit="idx"
                  missingDataInterval={GAP_INTERVAL}
                  markers={[{ hour: ANOMALY_HOUR, label: 'T+264.4h pressure spike' }]}
                  height={180}
                />
                <div className="px-1 pt-1"><PlotLegend batches={Object.entries(BATCH_COLORS).map(([id, color]) => ({ id, color }))} /></div>
              </div>
            </Card>

            <Callout
              tone="warning"
              title={<span className="flex flex-wrap items-center gap-2">42-minute historian gap at T+182.0–182.7h <ClaimTag kind="imputed" /></span>}
            >
              PI buffer overflow on Oct 15, 14:00–14:42 UTC. A Kalman-smoothed estimate is drawn dashed for visual continuity only; it is excluded from all yield and feed statistics on this page. The local HMI trend showed no alarms during the gap (operator note). <EvidenceChip id="historian-gap" /> <EvidenceChip id="b-ebr-oplog-26073" label="Operator note T+182.8h" />
            </Callout>

            <Card>
              <CardHeader title="Step record" subtitle="Chronological, from eBR, historian and LIMS · selected steps" actions={<button className="text-xs text-brand-teal hover:underline" onClick={() => setTab('timeline')}>Full timeline</button>} />
              <div className={table.wrap}>
                <table className={table.root}>
                  <thead>
                    <tr>
                      <th className={table.th}>Step</th>
                      <th className={table.th}>Description</th>
                      <th className={table.th}>Start</th>
                      <th className={cn(table.th, 'text-right')}>Duration</th>
                      <th className={table.th}>Status</th>
                      <th className={table.th}>Source</th>
                    </tr>
                  </thead>
                  <tbody>
                    {STEPS.map((s, i) => (
                      <tr key={i} className={cn(table.tr, s.status.tone === 'critical' && 'bg-status-critical-bg/40')}>
                        <td className={cn(table.td, 'font-mono text-[12px]')}>{s.step}</td>
                        <td className={cn(table.td, 'text-text-secondary text-[12.5px]')}>{s.desc}</td>
                        <td className={cn(table.td, 'font-mono text-[11.5px] whitespace-nowrap')}>{s.start}</td>
                        <td className={cn(table.td, 'text-right text-text-tertiary text-[12px]')}>{s.dur}</td>
                        <td className={table.td}><Pill tone={s.status.tone}>{s.status.label}</Pill></td>
                        <td className={table.td}>{s.cite && <EvidenceChip id={s.cite} />}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          </div>

          <div className="space-y-4">
            <Card>
              <CardHeader title={<span className="flex items-center gap-2">Linked sample <code className="font-mono text-xs">QC-948</code></span>} icon={<FlaskConical className="h-4 w-4" />} actions={<Pill tone="critical">OOT</Pill>} />
              <CardBody className="space-y-3">
                <KeyValue items={[
                  ['HPLC Protein A titer', <span key="t" className="text-status-critical">3.42 g/L</span>],
                  ['Specification', '> 3.80 g/L'],
                  ['VCD', MOCK_DATASET.qualityHold.vcd],
                  ['Pulled', 'T+262.0h · Day 11'],
                  ['Analyst', 'M. Okafor · signed'],
                  ['Second review', <span key="r" className="text-status-warning">Pending</span>],
                ]} />
                <p className="text-[11.5px] text-text-tertiary">In-process result. Release decisions use the harvest panel (QC-952), not yet pulled.</p>
                <div className="flex flex-wrap items-center gap-2">
                  <EvidenceChip id="lims-qc-948" />
                  <LinkButton href="/laboratory/QC-948" size="sm" variant="secondary" className="ml-auto">Open QC-948 <ArrowRight className="h-3 w-3" /></LinkButton>
                </div>
              </CardBody>
            </Card>

            <Card>
              <CardHeader title="Investigation" icon={<GitCompareArrows className="h-4 w-4" />} actions={<Pill tone="warning">Hypotheses under review</Pill>} />
              <CardBody className="space-y-2.5 text-[12.5px]">
                <p className="text-text-secondary">INV-104 is evaluating three candidate explanations for the yield decline. One is supported by correlated evidence; two are contradicted. No root cause has been approved.</p>
                <ul className="space-y-1.5">
                  <li className="flex items-center gap-2"><ClaimTag kind="hypothesis" /><span>A · Tubing fatigue / slip</span></li>
                  <li className="flex items-center gap-2"><ClaimTag kind="contradicted" /><span>B · Media lot variation</span></li>
                  <li className="flex items-center gap-2"><ClaimTag kind="contradicted" /><span>C · DO sensor drift</span></li>
                </ul>
                <div className="flex flex-wrap items-center gap-2 pt-1">
                  <EvidenceChip id="qms-q-dev-031" />
                  <LinkButton href="/investigations/INV-104" size="sm" className="ml-auto">Inspect INV-104 <ArrowRight className="h-3 w-3" /></LinkButton>
                </div>
              </CardBody>
            </Card>

            <Card>
              <CardHeader title="Batch identity" />
              <CardBody>
                <KeyValue cols={2} items={[
                  ['Batch', <span key="b" className="font-mono">MES-26073</span>],
                  ['Campaign', <span key="c" className="font-mono">CMP-26-10</span>],
                  ['Unit', 'BR-UP-01'],
                  ['Feed pump', <Link key="p" href="/equipment/PM-204" className="text-brand-teal hover:underline">PM-204</Link>],
                  ['Elapsed', 'T+272.7h'],
                  ['Planned end', 'T+336h · Oct 22'],
                  ['Release', <span key="r" className="text-status-critical">Hold active</span>],
                  ['Process', <Link key="u" href="/processes/UP-01" className="text-brand-teal hover:underline">UP-01</Link>],
                ]} />
              </CardBody>
            </Card>
          </div>
        </div>
      )}

      {tab === 'timeline' && (
        <Card>
          <CardHeader title="Key events" subtitle="Compact list · the full synchronized 5-track trace is on its own page" actions={<LinkButton href="/batches/MES-26073/timeline" size="sm" variant="primary">Open full timeline <ArrowRight className="h-3 w-3" /></LinkButton>} />
          <ol className="relative m-4 border-l border-border-strong pl-5 space-y-3">
            {[
              ['T+0.0h', 'Inoculation from SUB-200-02', 'b-mes-genealogy-26073', 'neutral'],
              ['T+72.0h', 'Feed start · 16.90 mL/min', 'b-ebr-material-lots', 'neutral'],
              ['T+120.0h', 'Temperature shift to 34.0 °C', 'b-ebr-recipe-v4', 'neutral'],
              ['T+182.0h', 'Historian gap · 42 min', 'historian-gap', 'warning'],
              ['T+215.2h', 'WO-8819 clamp torque adjusted (no slip check)', 'cmms-wo-8819', 'warning'],
              ['T+262.0h', 'QC-948 pulled · titer 3.42 g/L OOT', 'lims-qc-948', 'critical'],
              ['T+264.4h', 'PM-204 head pressure 1.48 bar · feed −14.2%', 'historian-up01', 'critical'],
            ].map(([t, label, cite, tone]) => (
              <li key={t} className="relative">
                <span className={cn('absolute -left-[25px] top-1.5 h-2.5 w-2.5 rounded-full border-2 border-white', tone === 'critical' ? 'bg-status-critical' : tone === 'warning' ? 'bg-status-warning' : 'bg-status-neutral')} />
                <p className="text-[12.5px]"><span className="font-mono text-text-tertiary mr-2">{t}</span><span className="text-text-primary">{label}</span> <EvidenceChip id={cite} className="ml-1" /></p>
              </li>
            ))}
          </ol>
        </Card>
      )}

      {tab === 'trends' && (
        <Card>
          <CardHeader title="Process trends · MES-26073" subtitle="Synchronized crosshair · reference envelopes from recipe limits" actions={<LinkButton href="/workbench/AN-104" size="sm">Compare with 26071/26072 in Workbench</LinkButton>} />
          <div className="p-3 space-y-2">
            <ScientificPlot batches={only73(feedRateSeries)} variableName="Feed rate (PM-204)" unit="mL/min" referenceEnvelope={{ min: 15.8, max: 17.6 }} missingDataInterval={GAP_INTERVAL} markers={[{ hour: ANOMALY_HOUR, label: 'T+264.4h' }]} hoverHour={hover} onHoverHour={setHover} height={160} showXAxis={false} />
            <ScientificPlot batches={only73(headPressureSeries)} variableName="Head pressure (PM-204)" unit="bar" referenceEnvelope={{ min: 0.6, max: 1.2 }} missingDataInterval={GAP_INTERVAL} markers={[{ hour: ANOMALY_HOUR, label: 'T+264.4h' }]} hoverHour={hover} onHoverHour={setHover} height={160} />
          </div>
          <div className="flex flex-wrap items-center gap-2 px-4 py-2.5 border-t border-border-hairline text-[11.5px] text-text-tertiary">Sources: <EvidenceChip id="historian-up01" /> <EvidenceChip id="historian-gap" /></div>
        </Card>
      )}

      {tab === 'quality' && (
        <Card>
          <CardHeader title="In-process samples" subtitle="LabWare LIMS · read-only" />
          <div className={table.wrap}>
            <table className={table.root}>
              <thead><tr><th className={table.th}>Sample</th><th className={table.th}>Pulled</th><th className={table.th}>Test</th><th className={table.th}>Result</th><th className={table.th}>Spec</th><th className={table.th}>Status</th></tr></thead>
              <tbody>
                {SAMPLES.map((s) => (
                  <tr key={s.id} className={table.tr}>
                    <td className={table.td}>
                      {s.id === 'QC-948' ? <Link href="/laboratory/QC-948" className="font-mono text-brand-teal hover:underline">{s.id}</Link> : <button className="font-mono text-text-primary hover:text-brand-teal" onClick={() => openSample(s.id)}>{s.id}</button>}
                    </td>
                    <td className={cn(table.td, 'text-[12px] text-text-secondary')}>{s.day}</td>
                    <td className={cn(table.td, 'text-[12px]')}>{s.test}</td>
                    <td className={cn(table.td, s.id === 'QC-948' && 'text-status-critical font-semibold')}>{s.result}</td>
                    <td className={cn(table.td, 'text-[12px] text-text-tertiary')}>{s.spec}</td>
                    <td className={table.td}><Pill tone={s.status.t}>{s.status.l}</Pill></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="px-4 py-2.5 text-[11.5px] text-text-tertiary border-t border-border-hairline flex flex-wrap items-center gap-2">Sources: <EvidenceChip id="lims-qc-948" /> <EvidenceChip id="b-lims-cqa-panel" /></p>
        </Card>
      )}

      {tab === 'genealogy' && (
        <Card>
          <CardHeader title="Inoculum lineage" subtitle="Upstream genealogy from the MES genealogy report" actions={<LinkButton href="/batches/MES-26073/timeline" size="sm" variant="primary">Lineage tree & material lots <ArrowRight className="h-3 w-3" /></LinkButton>} />
          <CardBody>
            <ol className="flex flex-wrap items-center gap-2 text-[12px]">
              {['WCB-AB014-0217 · vial 112', 'SF-0928-A/B · N-4', 'SF-1001-C · N-3', 'WB-07 · N-2 20 L', 'SUB-200-02 · N-1 200 L', 'BR-UP-01 · 2,000 L'].map((n, i, a) => (
                <li key={n} className="flex items-center gap-2">
                  <span className={cn('rounded-control border px-2 py-1 font-mono', i === a.length - 1 ? 'border-cyan-300 bg-brand-teal-light text-brand-teal-dark' : 'border-border-hairline bg-surface-secondary')}>{n}</span>
                  {i < a.length - 1 && <ArrowRight className="h-3 w-3 text-text-muted" aria-hidden />}
                </li>
              ))}
            </ol>
            <div className="mt-3 flex flex-wrap items-center gap-2 text-[11.5px] text-text-tertiary">
              <EvidenceChip id="b-mes-genealogy-26073" /> <EvidenceChip id="b-ebr-material-lots" />
              <span>Tubing lot TS24-PT-5521 on PM-204 was installed during MES-26072 and carried into this batch.</span>
            </div>
          </CardBody>
        </Card>
      )}

      {tab === 'documents' && (
        <Card>
          <CardHeader title="Linked records" subtitle="Systems of record remain authoritative; links open read-only views" icon={<FileText className="h-4 w-4" />} />
          <div className={table.wrap}>
            <table className={table.root}>
              <thead><tr><th className={table.th}>Record</th><th className={table.th}>Type</th><th className={table.th}>System</th><th className={table.th}>State</th><th className={table.th}>Source</th></tr></thead>
              <tbody>
                {DOCS.map((d) => (
                  <tr key={d.id} className={table.tr}>
                    <td className={cn(table.td, 'font-mono text-[12px]')}>{d.href ? <Link href={d.href} className="text-brand-teal hover:underline">{d.id}</Link> : d.id}</td>
                    <td className={cn(table.td, 'text-text-secondary')}>{d.type}</td>
                    <td className={cn(table.td, 'text-[12px]')}>{d.sys}</td>
                    <td className={table.td}><Pill tone={d.state.startsWith('Draft') ? 'warning' : d.state === 'Open' ? 'critical' : 'neutral'}>{d.state}</Pill></td>
                    <td className={table.td}>{d.cite ? <EvidenceChip id={d.cite} /> : <span className="text-[11.5px] text-text-tertiary">Generated draft</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {tab === 'activity' && (
        <Card>
          <CardHeader title="Activity" subtitle="People, systems and agents that touched this batch record" icon={<History className="h-4 w-4" />} />
          <ul className="divide-y divide-border-hairline">
            {ACTIVITY.map((a, i) => (
              <li key={i} className="px-4 py-2.5 flex flex-wrap items-start gap-x-3 gap-y-1 text-[12.5px]">
                <span className="w-[96px] shrink-0 font-mono text-[11.5px] text-text-tertiary">{a.t}</span>
                <span className="flex-1 min-w-[200px]"><span className="font-medium text-text-primary">{a.who}</span> <span className="text-text-secondary">· {a.what}</span></span>
                <ClaimTag kind={a.kind} />
              </li>
            ))}
          </ul>
          <p className="px-4 py-2.5 text-[11.5px] text-text-tertiary border-t border-border-hairline">Agent entries are interpretations or calculations; they never change the batch record.</p>
        </Card>
      )}
    </div>
  );
}
