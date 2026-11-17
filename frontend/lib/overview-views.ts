/**
 * The overview each kind of person lands on, written as A2UI messages.
 *
 * A view only chooses and orders registered summaries. Numbers, statuses and links to records stay in the host:
 * the surface binds to data paths ({"@path": "/deliveries/value"}) that the page fills from the person's own authorized API calls.
 * The same messages could later be sent by the server or the assistant without changing the page.
 */
export type Icp = 'everyone' | 'process_engineer' | 'msat' | 'qa' | 'executive';
/** A summary whose numbers come from one API call. `trends` is derived from deliveries. */
export type Source = 'deliveries' | 'signals' | 'quality' | 'workbench' | 'connections' | 'assistant';
export type Tone = 'loading' | 'attention' | 'problem' | 'good' | 'quiet' | 'unavailable';
export type Summary = { value?: string; status?: string; tone: Tone };
export type OverviewModel = { lead: string } & Partial<Record<Source | 'trends', Summary>>;

export const OVERVIEW_CATALOG = 'urn:biodemo:a2ui:overview:1';
export const ICONS = ['deliveries', 'signals', 'quality', 'trends', 'workbench', 'assistant', 'simulation', 'saved', 'export', 'connections'] as const;
/** The only places a summary may lead. A view cannot introduce a link of its own. */
export const DESTINATIONS = ['/cmo/', '/signals/', '/quality/', '/trends/', '/workbench/', '/home/', '/home/?scenarios=1', '/process-simulation/', '/workspaces/', '/export/', '/sources/'] as const;

export const ICP_LABEL: Record<Icp, string> = {
  everyone: 'Everything', process_engineer: 'Process engineering', msat: 'MSAT', qa: 'Quality', executive: 'Leadership',
};

type CardKey = (typeof ICONS)[number];
type Card = { title: string; about: string; href: (typeof DESTINATIONS)[number]; data?: Source | 'trends' };
// `about` says what the destination is for in plain words, so nobody has to open a page to learn its name.
const CARDS: Record<CardKey, Card> = {
  deliveries: { title: 'Deliveries', about: 'Check the files a CDMO sent against their original sources.', href: '/cmo/', data: 'deliveries' },
  signals: { title: 'Signals', about: 'Possible deviations found in your data. A person decides what becomes a case.', href: '/signals/', data: 'signals' },
  quality: { title: 'Quality events', about: 'Prepare a deviation, inspect its evidence and complete review.', href: '/quality/', data: 'quality' },
  trends: { title: 'Trends', about: 'Plot any accepted value across batches and over process time.', href: '/trends/', data: 'trends' },
  workbench: { title: 'Workbench', about: 'Put deliveries side by side, see what the data shows, and plan the next steps.', href: '/workbench/', data: 'workbench' },
  assistant: { title: 'Assistant', about: 'Ask a question about your data. Answers link to the records they used.', href: '/home/', data: 'assistant' },
  simulation: { title: 'Simulation', about: 'Compare process scenarios before a batch is run.', href: '/process-simulation/' },
  saved: { title: 'Saved work', about: 'Results, charts and review steps from earlier questions.', href: '/workspaces/' },
  export: { title: 'Export', about: 'Take batch values or signals to another tool, in the shape it needs.', href: '/export/' },
  connections: { title: 'Data connections', about: 'The systems this workspace reads from.', href: '/sources/', data: 'connections' },
};

type Group = { title: string; cards: CardKey[] };
const VIEWS: Record<Icp, Group[]> = {
  everyone: [
    { title: 'Where things stand', cards: ['deliveries', 'signals', 'quality'] },
    { title: 'Analyze', cards: ['trends', 'workbench', 'assistant'] },
    { title: 'Set up', cards: ['connections'] },
  ],
  process_engineer: [
    { title: 'Your process', cards: ['signals', 'trends', 'workbench'] },
    { title: 'Go further', cards: ['assistant', 'simulation', 'deliveries'] },
  ],
  msat: [
    { title: 'Transfer and investigation', cards: ['deliveries', 'workbench', 'trends'] },
    { title: 'Follow up', cards: ['signals', 'quality', 'simulation', 'assistant'] },
  ],
  qa: [
    { title: 'Waiting on quality', cards: ['quality', 'signals', 'deliveries'] },
    { title: 'Evidence and records', cards: ['saved', 'export', 'assistant'] },
  ],
  executive: [
    { title: 'Where things stand', cards: ['deliveries', 'signals', 'quality'] },
    { title: 'Look closer', cards: ['trends', 'assistant'] },
  ],
};

const ROLE_ICP: Record<string, Icp> = {
  qa: 'qa', qa_reviewer: 'qa', quality_systems: 'qa', msat: 'msat', supervisor: 'executive',
  engineering: 'process_engineer', maintenance: 'process_engineer', manufacturing_systems: 'process_engineer', operator: 'process_engineer',
};
export const isIcp = (value: unknown): value is Icp => typeof value === 'string' && value in VIEWS;
/** The view a person starts on: their demo persona, else their role. Administrators and unknown roles see everything. */
export function icpFor(roles: string[] = [], persona?: string | null): Icp {
  if (isIcp(persona) && persona !== 'everyone') return persona;
  if (roles.includes('admin')) return 'everyone';
  return roles.map(role => ROLE_ICP[role]).find(Boolean) ?? 'everyone';
}

export type OverviewComponent = { id: string; component: string; [prop: string]: unknown };
const groupsFor = (icp: Icp, demo: boolean) => VIEWS[icp]
  // Demo visitors have no systems to connect.
  .map(group => ({ ...group, cards: group.cards.filter(card => !(demo && card === 'connections')) }))
  .filter(group => group.cards.length);

export type Attention = 'deliveries' | 'signals' | 'quality';
const isAttention = (card: CardKey): card is Attention => card === 'deliveries' || card === 'signals' || card === 'quality';
/** The summaries that can need a person, in the order this view shows them, so the opening sentence follows the view. */
export const attentionOrder = (icp: Icp, demo: boolean): Attention[] => groupsFor(icp, demo).flatMap(group => group.cards).filter(isAttention);
/** The pages a view's summaries lead to, in order and without a trailing slash. The sidebar lists these first. */
export const viewPages = (icp: Icp, demo: boolean): string[] =>
  groupsFor(icp, demo).flatMap(group => group.cards.map(card => CARDS[card].href.split('?')[0].replace(/\/$/, '')));

/** The API calls a view needs. A view that omits a summary never asks for its data. */
export function sourcesFor(icp: Icp, demo: boolean): Source[] {
  const wanted = new Set(groupsFor(icp, demo).flatMap(group => group.cards.map(card => CARDS[card].data)));
  if (wanted.has('trends')) wanted.add('deliveries');
  return (['deliveries', 'signals', 'quality', 'workbench', 'connections', 'assistant'] as Source[]).filter(source => wanted.has(source));
}

export function overviewComponents(icp: Icp, demo: boolean): OverviewComponent[] {
  const groups = groupsFor(icp, demo);
  return [
    { id: 'root', component: 'OverviewPage', children: groups.map((_, i) => `group_${i}`) },
    ...groups.flatMap((group, i) => [
      { id: `group_${i}`, component: 'SummaryGroup', title: group.title, children: group.cards.map(card => `card_${card}`) },
      ...group.cards.map(card => {
        const spec = CARDS[card];
        const bound = spec.data ? { value: { '@path': `/${spec.data}/value` }, status: { '@path': `/${spec.data}/status` }, tone: { '@path': `/${spec.data}/tone` } } : {};
        // A demo visitor's assistant opens on the guided scenarios for their role.
        const href = demo && card === 'assistant' ? '/home/?scenarios=1' : spec.href;
        return { id: `card_${card}`, component: 'SummaryCard', icon: card, title: spec.title, about: spec.about, href, ...bound };
      }),
    ]),
  ];
}

export const surfaceId = (icp: Icp) => `overview-${icp}`;
export function overviewMessages(icp: Icp, demo: boolean, model: OverviewModel) {
  return [{ version: '1.0' as const, createSurface: { surfaceId: surfaceId(icp), catalogId: OVERVIEW_CATALOG, components: overviewComponents(icp, demo), dataModel: model } }];
}
export const dataMessage = (icp: Icp, model: OverviewModel) => ({ version: '1.0' as const, updateDataModel: { surfaceId: surfaceId(icp), path: '/', value: model } });
