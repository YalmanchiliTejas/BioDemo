'use client';

import { useEffect, useRef, useState } from 'react';
import { A2uiSurface, createComponentImplementation, type ReactCatalogComponent } from '@a2ui/react';
import { Catalog, MessageProcessor, type SurfaceModel } from '@a2ui/web_core';
import { CommonSchemas } from '@a2ui/web_core/v1_0';
import { z } from 'zod';
import { DESTINATIONS, ICONS, OVERVIEW_CATALOG, dataMessage, overviewComponents, overviewMessages, surfaceId, type Icp, type OverviewModel } from '@/lib/overview-views';
import { NativeOverview, OverviewPageView, SummaryCardView, SummaryGroupView } from './SummaryViews';

// The catalog is the whole vocabulary a view has: three registered components, a fixed icon set and a fixed list of
// destinations. A view can arrange and bind them; it cannot bring markup, code, numbers or links of its own.
type Child = string | { id: string; basePath?: string };
const children = (list: unknown, build: (id: string, basePath?: string) => React.ReactNode) =>
  (Array.isArray(list) ? list as Child[] : []).map(child => typeof child === 'string' ? build(child) : build(child.id, child.basePath));

const OverviewPage = createComponentImplementation({
  name: 'OverviewPage', schema: z.object({ children: CommonSchemas.ChildList }),
}, ({ props, buildChild }) => <OverviewPageView>{children(props.children, buildChild)}</OverviewPageView>);

// A binding whose path has no data yet resolves to nothing; anything that is not a real string is left out.
const text = (value: unknown) => typeof value === 'string' && value ? value : undefined;

const SummaryGroup = createComponentImplementation({
  name: 'SummaryGroup', schema: z.object({ title: CommonSchemas.DynamicString, children: CommonSchemas.ChildList }),
}, ({ props, buildChild }) => <SummaryGroupView title={text(props.title) ?? ''}>{children(props.children, buildChild)}</SummaryGroupView>);

const SummaryCard = createComponentImplementation({
  name: 'SummaryCard',
  schema: z.object({
    icon: z.enum(ICONS), title: CommonSchemas.DynamicString, about: CommonSchemas.DynamicString, href: z.enum(DESTINATIONS),
    value: CommonSchemas.DynamicString.optional(), status: CommonSchemas.DynamicString.optional(), tone: CommonSchemas.DynamicString.optional(),
  }),
}, ({ props }) => <SummaryCardView icon={props.icon} title={text(props.title) ?? ''} about={text(props.about) ?? ''} href={props.href}
  value={text(props.value)} status={text(props.status)} tone={text(props.tone)} />);

export const overviewCatalog = new Catalog<ReactCatalogComponent>(OVERVIEW_CATALOG, '1.0', [OverviewPage, SummaryGroup, SummaryCard], []);

/** Renders one person's overview from A2UI messages and keeps its data model current. Mount with a key per view. */
export default function OverviewSurface({ icp, demo, model }: { icp: Icp; demo: boolean; model: OverviewModel }) {
  const processor = useRef<MessageProcessor<ReactCatalogComponent> | null>(null);
  const [surface, setSurface] = useState<SurfaceModel<ReactCatalogComponent> | null>(null);
  const [failed, setFailed] = useState(false);
  const latest = useRef(model);
  latest.current = model;
  useEffect(() => {
    const created = new MessageProcessor<ReactCatalogComponent>([overviewCatalog]);
    try {
      created.processMessages(overviewMessages(icp, demo, latest.current));
      const next = created.model.surfacesMap.get(surfaceId(icp));
      if (!next) throw new Error('Overview surface was not created');
      processor.current = created;
      setSurface(next);
    } catch (error) {
      console.warn('A2UI overview: showing the plain view', error);
      setFailed(true);
    }
    return () => { processor.current = null; created.dispose(); };
  }, [icp, demo]);
  useEffect(() => {
    try { processor.current?.processMessages([dataMessage(icp, model)]); } catch (error) { console.warn('A2UI overview: showing the plain view', error); setFailed(true); }
  }, [icp, model, surface]);

  if (failed || !surface) return <NativeOverview components={overviewComponents(icp, demo)} model={model} />;
  return <div data-a2ui-catalog={OVERVIEW_CATALOG} data-a2ui-view={icp}><A2uiSurface surface={surface} /></div>;
}
