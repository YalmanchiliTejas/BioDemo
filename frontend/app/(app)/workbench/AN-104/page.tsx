'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Download, GitCompareArrows, Play, RotateCcw, Search } from 'lucide-react';
import { Button, Callout, Card, CardHeader, ClaimTag, EvidenceChip, Hash, LinkButton, PageHeader, Pill, Segmented, SectionLabel, table } from '@/components/ui';
import { PlotLegend, ScientificPlot } from '@/components/ScientificPlot';
import { VARIABLES } from '@/fixtures/timeseries';
import { ANOMALY_HOUR, BATCH_COLORS, CITATIONS, GAP_INTERVAL, MOCK_DATASET } from '@/fixtures/biomanufacturingData';
import { useAppContext } from '@/lib/app-context';
import { cn } from '@/lib/cn';

type VarKey = (typeof VARIABLES)[number]['key'];
const BATCHES = ['MES-26071', 'MES-26072', 'MES-26073'];

export default function WorkbenchPage() {
  const router = useRouter();
  const { startRun, agentRunningState, openInspector, notify } = useAppContext();
  const [selected, setSelected] = useState<VarKey[]>(['yield', 'feed']);
  const [batches, setBatches] = useState<string[]>(BATCHES);
  const [filter, setFilter] = useState('');
  const [hover, setHover] = useState<number | null>(null);
  const [kalman, setKalman] = useState(true);
  const [timeMode, setTimeMode] = useState<'elapsed' | 'wall'>('elapsed');
  const [range, setRange] = useState<[number, number] | undefined>([240, 280]);

  const groups = useMemo(() => {
    const term = filter.toLowerCase();
    const g: Record<string, typeof VARIABLES[number][]> = {};
    VARIABLES.filter((v) => !term || `${v.label} ${v.tag}`.toLowerCase().includes(term)).forEach((v) => { (g[v.group] ??= []).push(v); });
    return g;
  }, [filter]);

  const toggleVar = (k: VarKey) => setSelected((s) => (s.includes(k) ? s.filter((x) => x !== k) : s.length >= 4 ? s : [...s, k]));
  const toggleBatch = (b: string) => setBatches((s) => (s.includes(b) ? (s.length > 1 ? s.filter((x) => x !== b) : s) : [...s, b]));

  const windowStats = useMemo(() => {
    const feed = VARIABLES.find((v) => v.key === 'feed')!.series;
    const [a, b] = range ?? [0, 280];
    return BATCHES.map((id) => {
      const pts = feed.find((s) => s.id === id)!.dataPoints.filter((p) => p.elapsedHours >= a && p.elapsedHours <= b && !p.imputed && p.value > 0);
      const mean = pts.reduce((s, p) => s + p.value, 0) / Math.max(1, pts.length);
      const min = Math.min(...pts.map((p) => p.value));
      return { id, mean, min, n: pts.length };
    });
  }, [range]);

  const ds = MOCK_DATASET.activeCampaign.batches;

  return (
    <div className="max-w-[1480px] mx-auto">
      <PageHeader
        frameId="ANALYSIS-01"
        crumbs={[{ label: 'Improve' }, { label: 'Workbench', href: '/workbench/AN-104' }, { label: 'UP-01 yield consistency' }]}
        title="Feed-rate attenuation across CMP-26-10"
        objectId="AN-104"
        status={<Pill tone="warning" dot>Exploratory analysis</Pill>}
        description="Compare the three campaign batches on a shared elapsed-time axis. Drag across any plot to select a range; the comparison table below recalculates for that range."
        actions={
          <>
            <Button onClick={() => startRun('Re-aligning AN-104 with latest historian data', 8)} disabled={agentRunningState.isRunning}>
              <Play className="h-3.5 w-3.5" /> Refresh from sources
            </Button>
            <LinkButton href="/documents/DOC-UP01-03"><Download className="h-3.5 w-3.5" /> Export data package</LinkButton>
            <Button variant="primary" onClick={() => router.push('/investigations/INV-104')}>
              <GitCompareArrows className="h-3.5 w-3.5" /> Create causal investigation
            </Button>
          </>
        }
      />

      <div className="grid grid-cols-1 lg:grid-cols-[220px_minmax(0,1fr)] gap-4">
        {/* Variable tree */}
        <Card className="self-start lg:sticky lg:top-0">
          <div className="p-3 border-b border-border-hairline">
            <label className="relative block">
              <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-text-muted" aria-hidden />
              <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter variables or tags" aria-label="Filter variables" className="w-full h-8 pl-7 pr-2 rounded-control border border-border-hairline bg-surface-secondary/60 text-[12.5px] focus:outline-none focus:ring-2 focus:ring-brand-teal" />
            </label>
          </div>
          <div className="p-3 space-y-3">
            {Object.entries(groups).map(([g, vars]) => (
              <div key={g}>
                <SectionLabel>{g}</SectionLabel>
                <ul className="mt-1.5 space-y-0.5">
                  {vars.map((v) => (
                    <li key={v.key}>
                      <label className={cn('flex items-start gap-2 px-1.5 py-1 rounded cursor-pointer hover:bg-surface-secondary', selected.includes(v.key) && 'bg-brand-teal-light/60')}>
                        <input type="checkbox" checked={selected.includes(v.key)} onChange={() => toggleVar(v.key)} className="mt-0.5 accent-[#0e7490]" />
                        <span className="min-w-0">
                          <span className="block text-[12.5px] text-text-primary leading-tight">{v.label}</span>
                          <span className="block text-[10.5px] font-mono text-text-tertiary">{v.tag} · {v.unit}</span>
                        </span>
                      </label>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
            {Object.keys(groups).length === 0 && <p className="text-xs text-text-tertiary">No variables match “{filter}”.</p>}
            <p className="text-[10.5px] text-text-muted">Up to 4 plots stacked. {selected.length}/4 selected.</p>
          </div>
          <div className="p-3 border-t border-border-hairline">
            <SectionLabel>Batches</SectionLabel>
            <ul className="mt-1.5 space-y-1">
              {BATCHES.map((b) => (
                <li key={b}>
                  <label className="flex items-center gap-2 text-[12.5px] cursor-pointer">
                    <input type="checkbox" checked={batches.includes(b)} onChange={() => toggleBatch(b)} className="accent-[#0e7490]" />
                    <span className="h-0.5 w-3 rounded" style={{ background: BATCH_COLORS[b] }} />
                    <span className="font-mono">{b}</span>
                  </label>
                </li>
              ))}
            </ul>
          </div>
        </Card>

        <div className="min-w-0 space-y-4">
          <Card>
            <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-2.5 border-b border-border-hairline">
              <div className="flex flex-wrap items-center gap-3">
                <Segmented value={timeMode} onChange={setTimeMode} options={[{ value: 'elapsed', label: 'Elapsed (T+0)' }, { value: 'wall', label: 'Wall clock' }]} />
                <label className="flex items-center gap-1.5 text-[12px] text-text-secondary cursor-pointer">
                  <input type="checkbox" checked={kalman} onChange={(e) => setKalman(e.target.checked)} className="accent-[#0e7490]" />
                  Show Kalman estimate in gap
                </label>
                {range && (
                  <span className="flex items-center gap-1.5 text-[12px] text-text-secondary">
                    Window <code className="font-mono text-text-primary">T+{range[0].toFixed(1)}–{range[1].toFixed(1)}h</code>
                    <button onClick={() => setRange(undefined)} className="text-text-tertiary hover:text-text-primary" aria-label="Clear range"><RotateCcw className="h-3 w-3" /></button>
                  </span>
                )}
              </div>
              <PlotLegend batches={batches.map((id) => ({ id, color: BATCH_COLORS[id] }))} kalman={kalman} />
            </div>
            {timeMode === 'wall' && (
              <div className="px-4 pt-3">
                <Callout tone="info">Wall-clock alignment overlays batches by calendar date. Batches started on different days will not line up; elapsed time is recommended for comparison.</Callout>
              </div>
            )}
            <div className="px-3 py-3 space-y-2">
              {selected.length === 0 && <p className="px-2 py-10 text-center text-[13px] text-text-tertiary">Select a variable on the left to plot it.</p>}
              {selected.map((k, i) => {
                const v = VARIABLES.find((x) => x.key === k)!;
                return (
                  <ScientificPlot
                    key={k}
                    variableName={v.label}
                    unit={v.unit}
                    batches={v.series.filter((s) => batches.includes(s.id))}
                    referenceEnvelope={'envelope' in v ? v.envelope : undefined}
                    missingDataInterval={batches.includes('MES-26073') ? GAP_INTERVAL : undefined}
                    kalmanStateActive={kalman}
                    hoverHour={hover}
                    onHoverHour={setHover}
                    selectedWindow={range}
                    onWindowSelect={setRange}
                    markers={[{ hour: ANOMALY_HOUR, label: 'T+264.4h PM-204 pressure spike' }]}
                    height={selected.length > 2 ? 150 : 190}
                    showXAxis={i === selected.length - 1}
                    xLabel={timeMode === 'elapsed' ? 'Elapsed batch time (h)' : 'Hours since campaign start (wall clock offset)'}
                  />
                );
              })}
            </div>
            <div className="flex flex-wrap items-center gap-2 px-4 py-2.5 border-t border-border-hairline bg-surface-secondary/40 text-[11.5px] text-text-tertiary">
              Sources: <EvidenceChip id="historian-up01" /> <EvidenceChip id="historian-gap" label="Historian gap rows 10,921–10,962" /> <EvidenceChip id="ebr-mes-26073" />
            </div>
          </Card>

          <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
            <Card className="xl:col-span-2">
              <CardHeader
                title="Batch comparison"
                subtitle={range ? `Feed-rate statistics for T+${range[0].toFixed(0)}–${range[1].toFixed(0)}h · imputed points excluded` : 'Feed-rate statistics for full batch · imputed points excluded'}
                actions={<ClaimTag kind="calculated" />}
              />
              <div className={table.wrap}>
                <table className={table.root}>
                  <thead>
                    <tr>
                      <th className={table.th}>Batch</th>
                      <th className={cn(table.th, 'text-right')}>Final yield idx</th>
                      <th className={cn(table.th, 'text-right')}>Feed delivered (L)</th>
                      <th className={cn(table.th, 'text-right')}>Mean feed (mL/min)</th>
                      <th className={cn(table.th, 'text-right')}>Min feed</th>
                      <th className={cn(table.th, 'text-right')}>n</th>
                      <th className={table.th}>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {windowStats.map((s) => {
                      const b = ds.find((x) => x.id === s.id)!;
                      return (
                        <tr key={s.id} className={table.tr}>
                          <td className={table.td}><span className="flex items-center gap-2"><span className="h-2 w-2 rounded-full" style={{ background: BATCH_COLORS[s.id] }} /><span className="font-mono">{s.id}</span></span></td>
                          <td className={cn(table.td, 'text-right', s.id === 'MES-26073' && 'text-status-critical font-semibold')}>{b.normalizedYield.toFixed(1)}</td>
                          <td className={cn(table.td, 'text-right')}>{b.feedDeliveryL.toFixed(1)}</td>
                          <td className={cn(table.td, 'text-right')}>{s.mean.toFixed(2)}</td>
                          <td className={cn(table.td, 'text-right')}>{s.min.toFixed(2)}</td>
                          <td className={cn(table.td, 'text-right text-text-tertiary')}>{s.n}</td>
                          <td className={table.td}><Pill tone={b.status === 'COMPLETED' ? 'success' : 'info'}>{b.status === 'COMPLETED' ? 'Completed' : 'In execution'}</Pill></td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <p className="px-4 py-2.5 text-[11.5px] text-text-tertiary border-t border-border-hairline">
                Calculation: arithmetic mean of 1-minute resampled FLOW_PV, non-zero, non-imputed points. Reproducible from <span className="font-mono">Historian_UP01_Oct.csv</span>.
              </p>
            </Card>

            <Card>
              <CardHeader title="What this shows — and doesn’t" />
              <div className="p-4 space-y-3 text-[12.5px] leading-relaxed">
                <div>
                  <ClaimTag kind="observation" />
                  <p className="mt-1 text-text-secondary">MES-26073 feed flow drops ~14% within minutes of the T+264.4h pressure spike; earlier batches show no comparable drop.</p>
                </div>
                <div>
                  <ClaimTag kind="hypothesis" />
                  <p className="mt-1 text-text-secondary">Tubing fatigue or over-occlusion after WO-8819 could explain both the pressure rise and reduced delivery. <button className="text-brand-teal hover:underline" onClick={() => openInspector({ type: 'WORK_ORDER', id: 'WO-8819', title: 'Clamp torque adjustment', citations: ['cmms-wo-8819', 'sop-up-014'], metadata: { Equipment: 'PM-204', Performed: 'T-48h', 'Dynamic slip check': 'Not performed' }, href: '/equipment/PM-204' })}>See WO-8819</button></p>
                </div>
                <div>
                  <ClaimTag kind="unknown" />
                  <p className="mt-1 text-text-secondary">42 minutes of PI data are missing at T+182h. The dashed estimate is not used in any statistic above.</p>
                </div>
                <Button size="sm" variant="subtle" onClick={() => { notify('Selection pinned to workspace “UP-01 Yield Consistency”.'); }}>Pin this view to workspace</Button>
              </div>
            </Card>
          </div>

          <Card>
            <CardHeader title="Raw excerpt" subtitle="Rows behind the hovered or selected range" actions={<Hash value={CITATIONS['historian-up01'].sha256Hash} />} />
            <pre className="m-4 mt-3 whitespace-pre-wrap text-[11.5px] font-mono leading-relaxed bg-surface-secondary border border-border-hairline rounded-control p-3 text-text-primary">{CITATIONS['historian-up01'].rawExcerpt}</pre>
          </Card>
        </div>
      </div>
    </div>
  );
}
