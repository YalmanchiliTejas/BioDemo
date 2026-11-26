'use client';

import { useEffect, useState } from 'react';
import { processRequest, ProcessApiError } from './process-api';
import { useWorkspace } from './workspace-context';

export type Persona = 'process_engineer' | 'msat' | 'qa' | 'executive';
export type Scenario = { scenario_id: string; persona?: string; title: string; situation: string; prompt: string; look_for?: string[] };
export type DemoWorkspace = {
  tenant_id?: string; organization_id?: string; persona: Persona | string; expires_at?: string | null;
  messages_used?: number; message_limit?: number; messages_left?: number; status?: 'active' | 'expired'; expired?: boolean; scenarios?: Scenario[];
};
export type Feedback = {
  kind: 'answer' | 'scenario' | 'overall'; turn_id?: string; scenario_id?: string; rating?: 'up' | 'down' | number;
  realistic?: number; useful?: number; would_use?: 'yes' | 'maybe' | 'no'; comment?: string; email?: string;
};

export const CONTACT_URL = process.env.NEXT_PUBLIC_CONTACT_URL ?? '';
export const PERSONA_LABEL: Record<string, string> = {
  process_engineer: 'Process Engineer', msat: 'MSAT', qa: 'Quality (QA)', executive: 'Executive',
};

export const startDemo = (persona: Persona) =>
  processRequest<DemoWorkspace>('/v1/demo/workspaces', { persona, accepted_notice: true });
export const sendFeedback = (feedback: Feedback) => processRequest<{ ok: boolean }>('/v1/demo/feedback', feedback);

export function hoursLeft(expires?: string | null, now = Date.now()) {
  if (!expires) return null;
  const ms = new Date(expires).getTime() - now;
  return Number.isNaN(ms) ? null : Math.max(0, Math.ceil(ms / 3600000));
}

const cache = new Map<string, DemoWorkspace | null>();
const listeners = new Set<() => void>();
/** Re-read the demo state (e.g. after a message, to update "messages left"). */
export function refreshDemo() { cache.clear(); listeners.forEach(l => l()); }

/** The current organization's demo workspace, or null when it is a real workspace (404). Fetched once per org. */
export function useDemo() {
  const { organization, user } = useWorkspace();
  const key = `${user?.id ?? ''}:${organization?.id ?? ''}`;
  const [state, setState] = useState<{ key: string; demo: DemoWorkspace | null; expired: boolean }>(() =>
    ({ key, demo: cache.get(key) ?? null, expired: false }));
  const [tick, setTick] = useState(0);
  useEffect(() => { const l = () => setTick(t => t + 1); listeners.add(l); return () => { listeners.delete(l); }; }, []);
  useEffect(() => {
    if (!organization) return;
    if (cache.has(key)) { setState({ key, demo: cache.get(key) ?? null, expired: false }); return; }
    let alive = true;
    processRequest<DemoWorkspace>('/v1/demo/workspace')
      .then(demo => { cache.set(key, demo); if (alive) setState({ key, demo, expired: !!demo.expired }); })
      .catch(e => {
        const expired = e instanceof ProcessApiError && e.status === 410;
        if (!expired) cache.set(key, null);
        if (alive) setState({ key, demo: null, expired });
      });
    return () => { alive = false; };
  }, [key, organization, tick]);
  return state.key === key ? { demo: state.demo, expired: state.expired } : { demo: null, expired: false };
}
