'use client';

import { useState } from 'react';
import Link from 'next/link';
import { ArrowRight, BookOpen, ChevronRight, History, LineChart } from 'lucide-react';
import { Callout, Card, CardBody, CardHeader, ClaimTag, DemoBoundary, EvidenceChip, KeyValue, LinkButton, PageHeader, Pill, SectionLabel, table, type ClaimKind, type Tone } from '@/components/ui';
import { ArcGauge } from '@/components/screens/b/ArcGauge';
import { BATCH_COLORS } from '@/fixtures/biomanufacturingData';
import { cn } from '@/lib/cn';

type StageKey = 'seed' | 'bioreactor' | 'harvest' | 'depth' | 'proa';
type Stage = { key: StageKey; n: string; name: string; unit: string; state: string; tone: Tone; summary: string; params: Array<[string, string]>; note?: string };

const STAGES: Stage[] = [
  {
    key: 'seed', n: '1', name: 'Seed Train', unit: 'ST-01 · N-4 → N-1', state: 'Complete', tone: 'success',
    summary: 'Expansion from WCB vial through shake flasks, a 20 L rocking bag and a 200 L single-use bioreactor.',
    params: [['Transfer VCD (N-1)', '3.9 ×10⁶/mL · target ≥3.5'], ['Viability at transfer', '98.1% · target ≥95%'], ['Passage age at inoculation', '17 · limit ≤25'], ['Duration', '10.1 days']],
  },
  {
    key: 'bioreactor', n: '2', name: 'Bioreactor Fed-Batch', unit: 'BR-UP-01 · 2,000 L', state: 'Running · alert', tone: 'critical',
    summary: 'Fed-batch production with temperature shift at T+120h and continuous feed from PM-204.',
    params: [],
  },
  {
    key: 'harvest', n: '3', name: 'Harvest / Centrifugation', unit: 'CE-01 · disc-stack', state: 'Planned Oct 22', tone: 'neutral',
    summary: 'Primary clarification of harvested cell culture fluid.',
    params: [['Feed rate (MES-26072)', '420 L/h · range 380–460'], ['Bowl speed', '9,800 rpm'], ['Centrate turbidity', '62 NTU · limit ≤100'], ['Temperature', '8 °C']],
    note: 'Not yet executed for MES-26073. Values shown are from MES-26072.',
  },
  {
    key: 'depth', n: '4', name: 'Depth Filtration', unit: 'DF-02 · 2-stage', state: 'Planned', tone: 'neutral',
    summary: 'Secondary clarification ahead of capture chromatography.',
    params: [['Flux (MES-26072)', '110 LMH'], ['Terminal ΔP', '0.9 bar · limit ≤1.5'], ['Filtrate turbidity', '4.1 NTU · limit ≤10'], ['Throughput', '182 L/m²']],
    note: 'Not yet executed for MES-26073. Values shown are from MES-26072.',
  },
  {
    key: 'proa', n: '5', name: 'Protein A Capture', unit: 'PA-01 · MabSelect column', state: 'Planned', tone: 'neutral',
    summary: 'Affinity capture of IgG1 from clarified harvest.',
    params: [['Load density (MES-26072)', '38 g/L resin · limit ≤42'], ['Residence time', '4.0 min'], ['Step yield', '94.6%'], ['Eluate HMW', '2.1%']],
    note: 'Not yet executed for MES-26073. Values shown are from MES-26072.',
  },
];

const CQAS: Array<{ name: string; method: string; value: string; spec: string; status: string; tone: Tone; kind: ClaimKind; sample: string }> = [
  { name: 'Titer', method: 'HPLC Protein A', value: '3.42 g/L', spec: '> 3.80 g/L (Day 11 in-process)', status: 'Out of trend', tone: 'critical', kind: 'observation', sample: 'QC-948' },
  { name: 'Aggregates (HMW)', method: 'SEC-HPLC', value: '1.8 %', spec: '≤ 3.0 %', status: 'Within spec', tone: 'success', kind: 'observation', sample: 'QC-944' },
  { name: 'Charge variants (acidic)', method: 'CEX-HPLC', value: '24.1 %', spec: '18–30 %', status: 'Within spec', tone: 'success', kind: 'observation', sample: 'QC-944' },
  { name: 'Glycan (G0F)', method: 'HILIC-FLD', value: '—', spec: '35–55 %', status: 'Not tested until harvest', tone: 'muted', kind: 'unknown', sample: 'QC-952 (planned)' },
];

const VARIANCE: Array<{ p: string; unit: string; v: [number, number, number]; range: string; flag?: boolean; prec?: number }> = [
  { p: 'Mean DO, Phase 05', unit: '%', v: [40.1, 39.8, 39.4], range: '35–45' },
  { p: 'Mean pH, Phase 05', unit: '', v: [7.05, 7.04, 7.04], range: '6.90–7.20', prec: 2 },
  { p: 'Agitation', unit: 'rpm', v: [85.0, 85.1, 85.0], range: '80–90' },
  { p: 'Mean feed flow T+240–280h', unit: 'mL/min', v: [16.88, 16.41, 14.48], range: '15.8–17.6', flag: true, prec: 2 },
  { p: 'Peak PM-204 head pressure', unit: 'bar', v: [0.98, 1.06, 1.48], range: '≤ 1.20', flag: true, prec: 2 },
  { p: 'Feed delivered (to T+264h)', unit: 'L', v: [291.4, 284.9, 254.2], range: 'Trend only', flag: true },
  { p: 'Day 11 titer', unit: 'g/L', v: [3.98, 3.81, 3.42], range: '> 3.80', flag: true, prec: 2 },
  { p: 'Final normalized yield index', unit: 'idx', v: [81.2, 78.4, 75.9], range: 'Target 82.0', flag: true },
];

export default function ProcessPage() {
  const [selected, setSelected] = useState<StageKey>('bioreactor');
  const stage = STAGES.find((s) => s.key === selected)!;

  return (
    <div className="max-w-[1280px] mx-auto">
      <PageHeader
        frameId="PROC-01"
        crumbs={[{ label: 'Operate' }, { label: 'Processes' }, { label: 'AB-mAb-014' }, { label: 'UP-01' }]}
        title="Process context"
        objectId="UP-01"
        status={<Pill tone="critical" dot>1 CPP outside range</Pill>}
        description="The upstream-to-capture lifecycle for AB-mAb-014. Select a stage to see its critical process parameters, quality attributes and how recent batches compare."
        meta={<><span>Recipe RCP-AB014-V4</span><span>Active batch MES-26073 · T+264.4h</span><span>CPP snapshot 08:26 UTC</span><DemoBoundary compact /></>}
        actions={
          <>
            <LinkButton href="/knowledge"><BookOpen className="h-3.5 w-3.5" /> View SOP-UP-014 revisions</LinkButton>
            <LinkButton href="/batches/MES-26073"><History className="h-3.5 w-3.5" /> Historical batches</LinkButton>
            <LinkButton href="/workbench/AN-104" variant="primary"><LineChart className="h-3.5 w-3.5" /> Open selected unit in Workbench</LinkButton>
          </>
        }
      />

      <Card className="mb-4">
        <CardHeader title="Lifecycle map" subtitle="Seed train through capture · select a stage" />
        <div className="p-4">
          <ol className="flex flex-col md:flex-row md:items-stretch gap-2" role="tablist" aria-label="Process stages">
            {STAGES.map((s, i) => {
              const active = s.key === selected;
              return (
                <li key={s.key} className="flex md:flex-1 items-center gap-2">
                  <button
                    type="button"
                    role="tab"
                    aria-selected={active}
                    onClick={() => setSelected(s.key)}
                    className={cn(
                      'flex-1 h-full text-left rounded-card border px-3 py-2.5 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-teal',
                      active ? 'border-brand-teal bg-brand-teal-light ring-1 ring-brand-teal/40' : 'border-border-hairline bg-surface hover:bg-surface-secondary',
                    )}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[10.5px] font-mono text-text-tertiary">Stage {s.n}</span>
                      <span className={cn('h-2 w-2 rounded-full', s.tone === 'critical' ? 'bg-status-critical' : s.tone === 'success' ? 'bg-status-success' : 'bg-border-strong')} />
                    </div>
                    <p className={cn('mt-1 text-[13px] font-semibold leading-tight', active ? 'text-brand-teal-dark' : 'text-text-primary')}>{s.name}</p>
                    <p className="mt-0.5 text-[11px] text-text-tertiary truncate">{s.unit}</p>
                    <p className={cn('mt-1.5 text-[11px] font-medium', s.tone === 'critical' ? 'text-status-critical' : s.tone === 'success' ? 'text-status-success' : 'text-text-tertiary')}>{s.state}</p>
                  </button>
                  {i < STAGES.length - 1 && <ChevronRight className="hidden md:block h-4 w-4 shrink-0 text-text-muted" aria-hidden />}
                </li>
              );
            })}
          </ol>
        </div>
      </Card>

      {selected === 'bioreactor' ? (
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-4 mb-4">
          <Card className="xl:col-span-2">
            <CardHeader
              title="Critical process parameters · BR-UP-01"
              subtitle="Live snapshot at T+264.4h · green band = recipe range"
              actions={<><ClaimTag kind="observation" /><EvidenceChip id="b-pi-cpp-snapshot" label="CPP snapshot" /></>}
            />
            <CardBody className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <ArcGauge label="Dissolved O₂" value={39.4} unit="%" min={20} max={60} bandLo={35} bandHi={45} caption="Range 35–45" />
              <ArcGauge label="pH" value={7.04} unit="" min={6.7} max={7.4} bandLo={6.9} bandHi={7.2} precision={2} caption="Range 6.90–7.20" />
              <ArcGauge label="Agitation" value={85.0} unit="rpm" min={60} max={110} bandLo={80} bandHi={90} caption="Range 80–90" />
              <ArcGauge label="Feed flow" value={14.48} unit="mL/min" min={10} max={20} bandLo={15.8} bandHi={17.6} precision={2} caption="Range 15.8–17.6 · SP 16.90" />
            </CardBody>
            <div className="px-4 pb-4">
              <Callout tone="critical" title="Feed flow 14.48 mL/min is below the 15.8 mL/min lower limit">
                −14.3% against setpoint since T+264.4h, coincident with PM-204 head pressure at 1.48 bar. DO, pH and agitation remain in range. <EvidenceChip id="ebr-mes-26073" /> <Link href="/equipment/PM-204" className="underline">Open PM-204</Link>
              </Callout>
            </div>
          </Card>

          <Card>
            <CardHeader title="Stage summary" />
            <CardBody className="space-y-3 text-[12.5px]">
              <p className="text-text-secondary">{stage.summary}</p>
              <KeyValue items={[['Unit', 'BR-UP-01'], ['Phase', '05 · Stationary'], ['Elapsed', 'T+272.7h / 336h'], ['Feed pump', 'PM-204'], ['Temp SP', '34.0 °C'], ['Governing SOP', 'SOP-UP-014 Rev 7']]} />
              <div className="flex flex-wrap gap-2"><EvidenceChip id="b-ebr-recipe-v4" /><EvidenceChip id="sop-up-014" /></div>
            </CardBody>
          </Card>
        </div>
      ) : (
        <Card className="mb-4">
          <CardHeader title={`${stage.name} · ${stage.unit}`} subtitle={stage.summary} actions={<Pill tone={stage.tone}>{stage.state}</Pill>} />
          <CardBody>
            {stage.note && <Callout tone="info" className="mb-3">{stage.note}</Callout>}
            <KeyValue cols={4} items={stage.params} />
            <p className="mt-3 text-[11.5px] text-text-tertiary">Ranges from master recipe RCP-AB014-V4. <EvidenceChip id="b-ebr-recipe-v4" /></p>
          </CardBody>
        </Card>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-5 gap-4">
        <Card className="xl:col-span-2">
          <CardHeader title="Critical quality attributes" subtitle="Latest in-process results for MES-26073" actions={<EvidenceChip id="b-lims-cqa-panel" label="CQA panel" />} />
          <ul className="divide-y divide-border-hairline">
            {CQAS.map((c) => (
              <li key={c.name} className="px-4 py-2.5">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-[13px] font-medium text-text-primary">{c.name}</p>
                  <Pill tone={c.tone} dot>{c.status}</Pill>
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11.5px] text-text-tertiary">
                  <span className={cn('tabular-nums text-[13px] font-semibold', c.tone === 'critical' ? 'text-status-critical' : 'text-text-primary')}>{c.value}</span>
                  <span>Spec {c.spec}</span>
                  <span>{c.method}</span>
                  {c.sample === 'QC-948' ? <Link href="/laboratory/QC-948" className="font-mono text-brand-teal hover:underline">{c.sample}</Link> : <span className="font-mono">{c.sample}</span>}
                  <ClaimTag kind={c.kind} />
                </div>
              </li>
            ))}
          </ul>
        </Card>

        <Card className="xl:col-span-3">
          <CardHeader title="Unit-run variance audit · BR-UP-01" subtitle="Same unit, same recipe, three campaign batches" actions={<ClaimTag kind="calculated" />} />
          <div className={table.wrap}>
            <table className={table.root}>
              <thead>
                <tr>
                  <th className={table.th}>Parameter</th>
                  {(['MES-26071', 'MES-26072', 'MES-26073'] as const).map((b) => (
                    <th key={b} className={cn(table.th, 'text-right')}><span className="inline-flex items-center gap-1.5"><span className="h-2 w-2 rounded-full" style={{ background: BATCH_COLORS[b] }} />{b}</span></th>
                  ))}
                  <th className={table.th}>Range</th>
                </tr>
              </thead>
              <tbody>
                {VARIANCE.map((r) => (
                  <tr key={r.p} className={table.tr}>
                    <td className={cn(table.td, 'text-[12.5px]')}>{r.p} {r.unit && <span className="text-text-tertiary text-[11px]">({r.unit})</span>}</td>
                    {r.v.map((v, i) => (
                      <td key={i} className={cn(table.td, 'text-right', i === 2 && r.flag && 'text-status-critical font-semibold')}>{v.toFixed(r.prec ?? 1)}</td>
                    ))}
                    <td className={cn(table.td, 'text-[11.5px] text-text-tertiary whitespace-nowrap')}>{r.range}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="px-4 py-2.5 border-t border-border-hairline text-[11.5px] text-text-tertiary space-y-1">
            <p>Environmental CPPs (DO, pH, agitation) are near-identical across batches; differences concentrate in feed delivery and pump pressure. This narrows where to look but does not establish cause.</p>
            <p className="flex flex-wrap items-center gap-2">Sources: <EvidenceChip id="historian-up01" /> <EvidenceChip id="pi-do-probe" /> <EvidenceChip id="lims-qc-948" />
              <LinkButton href="/workbench/AN-104" size="sm" variant="ghost" className="ml-auto">Plot in Workbench <ArrowRight className="h-3 w-3" /></LinkButton>
            </p>
          </div>
        </Card>
      </div>

      <div className="mt-4 flex items-center gap-2 text-[11.5px] text-text-tertiary">
        <SectionLabel className="!text-[10.5px]">Note</SectionLabel>
        Earlier-batch feed delivered is computed to the same elapsed hour (T+264h) for a like-for-like comparison.
      </div>
    </div>
  );
}
