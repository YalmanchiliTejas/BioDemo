'use client';

import dynamic from 'next/dynamic';
import { Component, type ReactNode } from 'react';
import { BatchComparisonChart, BatchProfileChart } from './TrendCharts';
import type { ComponentProps } from 'react';

export type TrendChartProps =
  | { kind: 'comparison'; chart: ComponentProps<typeof BatchComparisonChart> }
  | { kind: 'profile'; chart: ComponentProps<typeof BatchProfileChart> };

const Surface = dynamic(() => import('./A2uiTrendSurface'), {
  ssr: false,
  loading: () => <p role="status" className="flex h-[280px] items-center justify-center text-xs text-text-secondary">Loading chart…</p>,
});

export function NativeTrendChart(props: TrendChartProps) {
  return props.kind === 'comparison'
    ? <BatchComparisonChart {...props.chart} />
    : <BatchProfileChart {...props.chart} />;
}

// A renderer failure must leave the accepted values and chart interactions available.
class ChartBoundary extends Component<{ children: ReactNode; fallback: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    return this.state.failed ? <><p role="status" className="px-2 text-xs text-text-secondary">The interactive layout could not load. Showing the standard chart.</p>{this.props.fallback}</> : this.props.children;
  }
}

export function A2uiTrendChart(props: TrendChartProps) {
  return <ChartBoundary fallback={<NativeTrendChart {...props} />}>
    <Surface {...props} />
  </ChartBoundary>;
}
