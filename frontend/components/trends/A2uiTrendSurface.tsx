'use client';

import { createContext, useContext, useEffect, useState } from 'react';
import { A2uiSurface, createComponentImplementation, type ReactCatalogComponent } from '@a2ui/react';
import { Catalog, MessageProcessor, type SurfaceModel } from '@a2ui/web_core';
import { z } from 'zod';
import { NativeTrendChart, type TrendChartProps } from './A2uiTrendChart';

// Values, source identifiers, limits, and callbacks stay in the authorized host.
// The declarative layout can choose a registered chart, never supply executable code
// or replace accepted measurements with generated numbers.
const ChartContext = createContext<TrendChartProps | null>(null);
const TrendChart = createComponentImplementation({
  name: 'TrendChart',
  schema: z.object({ kind: z.enum(['comparison', 'profile']) }),
}, ({ props }) => {
  const chart = useContext(ChartContext);
  if (!chart || chart.kind !== props.kind) throw new Error('Trend chart context does not match the surface');
  return <NativeTrendChart {...chart} />;
});

export const trendCatalog = new Catalog<ReactCatalogComponent>(
  'urn:biodemo:a2ui:trends:1', '1.0', [TrendChart], [],
);

export default function A2uiTrendSurface(props: TrendChartProps) {
  const [surface, setSurface] = useState<SurfaceModel<ReactCatalogComponent> | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    const processor = new MessageProcessor<ReactCatalogComponent>([trendCatalog]);
    try {
      processor.processMessages([{
        version: '1.0',
        createSurface: {
          surfaceId: `trend-${props.kind}`, catalogId: trendCatalog.id,
          components: [{ id: 'root', component: 'TrendChart', kind: props.kind }],
        },
      }]);
      const created = processor.model.surfacesMap.get(`trend-${props.kind}`);
      if (!created) throw new Error('Trend surface was not created');
      setSurface(created);
    } catch {
      setFailed(true);
    }
    return () => processor.dispose();
  }, [props.kind]);

  if (failed) return <><p role="status" className="px-2 text-xs text-text-secondary">The interactive layout could not load. Showing the standard chart.</p><NativeTrendChart {...props} /></>;
  if (!surface) return <NativeTrendChart {...props} />;
  return <ChartContext.Provider value={props}>
    <div data-a2ui-catalog={trendCatalog.id} data-a2ui-chart={props.kind}>
      <A2uiSurface surface={surface} />
    </div>
  </ChartContext.Provider>;
}
