'use client';

import { useState } from 'react';
import { LineChart, Search } from 'lucide-react';
import { PlotLegend, ScientificPlot } from '@/components/ScientificPlot';
import { ClaimTag, EvidenceChip, Pill } from '@/components/ui';
import { ANOMALY_HOUR, GAP_INTERVAL } from '@/fixtures/biomanufacturingData';
import { feedRateSeries, yieldSeries } from '@/fixtures/timeseries';

/** Lightweight, interactive rendering of the ANALYSIS-01 workbench for the landing page. */
export function WorkbenchPreview() {
  const [hover, setHover] = useState<number | null>(252);
  const markers = [{ hour: ANOMALY_HOUR, label: 'T+264.4h pressure spike', tone: 'critical' as const }];
  const at = (h: number | null) => {
    if (h === null) return null;
    const s = feedRateSeries[2].dataPoints;
    return s.reduce((best, p) => (Math.abs(p.elapsedHours - h) < Math.abs(best.elapsedHours - h) ? p : best), s[0]);
  };
  const p = at(hover);

  return (
    <div className="rounded-[10px] border border-slate-200 bg-white shadow-[0_1px_2px_rgba(15,23,42,0.04),0_12px_32px_-12px_rgba(15,23,42,0.18)] overflow-hidden" aria-label="Interactive preview of the scientific workbench (synthetic data)">
      <div className="flex items-center gap-2 h-9 px-3 border-b border-slate-200 bg-slate-50">
        <span className="flex gap-1.5" aria-hidden><span className="h-2.5 w-2.5 rounded-full bg-slate-300" /><span className="h-2.5 w-2.5 rounded-full bg-slate-300" /><span className="h-2.5 w-2.5 rounded-full bg-slate-300" /></span>
        <span className="mx-auto flex items-center gap-1.5 h-6 px-3 rounded-control bg-white border border-slate-200 text-[11px] text-slate-500 font-mono">
          <Search className="h-3 w-3" aria-hidden />workbench / AN-104
        </span>
      </div>
      <div className="flex">
        <div className="hidden md:flex flex-col gap-1 w-40 shrink-0 border-r border-slate-200 bg-slate-50/60 p-2.5 text-[11px]">
          <p className="px-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-400">Variables</p>
          {['Normalized yield index', 'Feed rate (PM-204)', 'Head pressure', 'Dissolved oxygen', 'pH'].map((v, i) => (
            <span key={v} className={i < 2 ? 'px-1.5 py-1 rounded bg-cyan-50 text-cyan-800 font-medium' : 'px-1.5 py-1 text-slate-500'}>{v}</span>
          ))}
        </div>
        <div className="flex-1 min-w-0 p-3 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <LineChart className="h-3.5 w-3.5 text-slate-400" aria-hidden />
            <p className="text-[12.5px] font-semibold text-slate-900">Feed-rate attenuation across CMP-26-10</p>
            <Pill tone="warning" dot>Exploratory</Pill>
            <span className="ml-auto text-[11px] font-mono tabular-nums text-slate-500">
              {p ? `T+${p.elapsedHours.toFixed(1)}h · MES-26073 feed ${p.value.toFixed(2)} mL/min` : 'Hover a plot'}
            </span>
          </div>
          <ScientificPlot batches={yieldSeries} variableName="Normalized yield index" unit="idx" height={120} hoverHour={hover} onHoverHour={setHover} markers={markers} missingDataInterval={GAP_INTERVAL} showXAxis={false} />
          <ScientificPlot batches={feedRateSeries} variableName="Feed rate (PM-204)" unit="mL/min" height={140} hoverHour={hover} onHoverHour={setHover} markers={markers} missingDataInterval={GAP_INTERVAL} referenceEnvelope={{ min: 15.8, max: 17.6 }} xDomain={[0, 280]} />
          <PlotLegend batches={yieldSeries} />
          <div className="flex flex-wrap items-center gap-2 rounded-control border border-slate-200 bg-slate-50 px-2.5 py-2 text-[11.5px] text-slate-600">
            <ClaimTag kind="observation" />
            <span>Feed flow on MES-26073 fell 14.2% after the T+264.4h head-pressure spike.</span>
            <EvidenceChip id="historian-up01" />
          </div>
        </div>
      </div>
    </div>
  );
}
