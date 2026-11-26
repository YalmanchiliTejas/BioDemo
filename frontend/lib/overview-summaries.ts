/** Turns API responses into the short summaries the overview shows. Pure, so the wording and counts can be checked without a browser. */
import type { RunListing } from './cmo-api';
import type { Connector } from './connectors-api';
import type { QualityWorkspace } from './quality-workflow-api';
import type { Signal } from './signals-api';
import type { PlanSummary } from './workbench';
import type { Attention, OverviewModel, Source, Summary } from './overview-views';

export type Conversation = { id: string; title: string; updated_at?: string };
export type Loaded = {
  deliveries?: RunListing[]; signals?: Signal[]; quality?: QualityWorkspace[]; workbench?: PlanSummary[];
  connections?: Connector[]; assistant?: Conversation[];
};
/** Per source: not asked for (absent), still loading, failed with a message, or loaded. */
export type State = Partial<Record<Source, 'loading' | { error: string } | 'ready'>>;

const count = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;
const LOADING: Summary = { tone: 'loading', status: 'Checking…' };
const unavailable = (error: string): Summary => ({ tone: 'unavailable', status: `Unavailable: ${error}` });

const deliveries = (runs: RunListing[]): Summary => {
  const review = runs.filter(r => r.status === 'complete' && !r.summary?.verified_package);
  const checking = runs.filter(r => r.status === 'queued' || r.status === 'running');
  const verified = runs.filter(r => r.summary?.verified_package);
  if (review.length) return { value: String(review.length), status: `to review${verified.length ? ` · ${verified.length} verified` : ''}`, tone: 'attention' };
  if (checking.length) return { value: String(checking.length), status: 'being checked. Nothing needs you yet.', tone: 'quiet' };
  if (verified.length) return { value: String(verified.length), status: 'verified. Nothing to review.', tone: 'good' };
  return { status: 'No deliveries yet. Start with the files your CDMO sent.', tone: 'quiet' };
};

const signals = (items: Signal[]): Summary => {
  const open = items.filter(s => s.status === 'open');
  const urgent = open.filter(s => s.severity !== 'warning').length;
  if (!open.length) return { value: '0', status: 'open. Nothing detected needs a decision.', tone: 'good' };
  return { value: String(open.length), status: urgent ? `open · ${urgent} at action level or above` : 'open, all at warning level', tone: urgent ? 'problem' : 'attention' };
};

const quality = (items: QualityWorkspace[]): Summary => {
  const open = items.filter(w => w.workflow?.state !== 'handed_off');
  const review = open.filter(w => w.workflow?.state === 'qa_review').length;
  if (!open.length) return { value: '0', status: 'open events.', tone: 'good' };
  return { value: String(open.length), status: review ? `open · ${review} in QA review` : `open ${open.length === 1 ? 'event' : 'events'}`, tone: 'attention' };
};

const workbench = (plans: PlanSummary[]): Summary => {
  const open = plans.filter(p => p.status === 'open');
  const steps = open.reduce((sum, plan) => sum + plan.open_steps, 0);
  if (!open.length) return { status: 'No work plan yet. Choose deliveries to compare and one is started for you.', tone: 'quiet' };
  return { value: String(steps), status: `${steps === 1 ? 'open step' : 'open steps'} in ${count(open.length, 'plan', 'plans')}`, tone: steps ? 'attention' : 'good' };
};

const connections = (items: Connector[]): Summary => {
  const enabled = items.filter(c => c.enabled);
  const failing = enabled.filter(c => c.last_error).length;
  if (!enabled.length) return { status: 'Nothing connected yet. Start with a system you already use.', tone: 'quiet' };
  return { value: String(enabled.length), status: failing ? `connected · ${failing} with a sync error` : 'connected and syncing', tone: failing ? 'problem' : 'good' };
};

const assistant = (items: Conversation[], scenarios: number): Summary => {
  if (scenarios && !items.length) return { value: String(scenarios), status: 'guided scenarios ready for your role', tone: 'quiet' };
  if (!items.length) return { status: 'No conversations yet. Ask your first question.', tone: 'quiet' };
  return { value: String(items.length), status: `${items.length === 1 ? 'conversation' : 'conversations'} · latest: ${items[0].title}`, tone: 'quiet' };
};

const trends = (runs: RunListing[]): Summary => {
  const verified = runs.filter(r => r.summary?.verified_package).length;
  return verified ? { value: String(verified), status: `verified ${verified === 1 ? 'delivery' : 'deliveries'} ready to plot`, tone: 'quiet' }
    : { status: 'Accepted values appear here once a delivery is checked.', tone: 'quiet' };
};

const NEEDS: Record<Attention, (n: number) => string> = {
  deliveries: n => `${count(n, 'delivery needs', 'deliveries need')} review`,
  signals: n => count(n, 'signal is open', 'signals are open'),
  quality: n => count(n, 'quality event is open', 'quality events are open'),
};
const NAMES: Record<Attention, string> = { deliveries: 'deliveries', signals: 'signals', quality: 'quality events' };
const listed = (items: string[]) => {
  const text = items.length > 1 ? `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}` : items[0];
  return text[0].toUpperCase() + text.slice(1);
};

/**
 * One sentence about what needs the person, in the order their view shows it.
 * It claims only what loaded: anything that could not be checked is named, never reported as clear.
 */
export function lead(model: Omit<OverviewModel, 'lead'>, state: State, order: Attention[] = ['deliveries', 'signals', 'quality']): string {
  const asked = order.filter(key => state[key]);
  const needs = asked.flatMap(key => {
    const s = model[key];
    return !s?.value || s.value === '0' || (s.tone !== 'attention' && s.tone !== 'problem') ? [] : [NEEDS[key](Number(s.value))];
  });
  const unchecked = asked.filter(key => typeof state[key] === 'object').map(key => NAMES[key]);
  const gap = unchecked.length ? `${listed(unchecked)} could not be checked.` : '';
  if (needs.length) return `${needs.join(' · ')}.${gap && ` ${gap}`}`;
  if (!asked.length || asked.some(key => state[key] === 'loading')) return 'Checking what needs your attention…';
  return gap || 'Nothing needs your attention right now.';
}

export function summarize(loaded: Loaded, state: State, scenarios = 0, order?: Attention[]): OverviewModel {
  const of = <K extends Source>(key: K, build: (value: NonNullable<Loaded[K]>) => Summary): Summary | undefined => {
    const s = state[key];
    if (!s) return undefined;
    if (typeof s === 'object') return unavailable(s.error);
    return loaded[key] ? build(loaded[key] as NonNullable<Loaded[K]>) : LOADING;
  };
  const model: Omit<OverviewModel, 'lead'> = {
    deliveries: of('deliveries', deliveries), signals: of('signals', signals), quality: of('quality', quality),
    workbench: of('workbench', workbench), connections: of('connections', connections),
    assistant: of('assistant', items => assistant(items, scenarios)),
    trends: of('deliveries', trends),
  };
  for (const key of Object.keys(model) as (keyof typeof model)[]) if (!model[key]) delete model[key];
  return { ...model, lead: lead(model, state, order) };
}
