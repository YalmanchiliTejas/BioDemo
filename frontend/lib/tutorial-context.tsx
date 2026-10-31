'use client';

import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { useWorkspace } from './workspace-context';

export const GUIDE_TOPICS = [
  { id: 'dashboard', label: 'Find your bearings', href: '/dashboard/', target: 'dashboard', title: 'Your work, in one place', body: 'The dashboard shows real connection status, deliveries that need attention, and recent work. Choose the next step that fits your goal.' },
  { id: 'connections', label: 'Connect your data', href: '/sources/', target: 'connections', title: 'Start with a source you already use', body: 'Choose an authorized source, configure its access, and test the mapping. You control when collection starts and can pause it later.' },
  { id: 'deliveries', label: 'Check a delivery', href: '/cmo/', target: 'deliveries', title: 'Follow a value back to its source', body: 'Bring in a delivery or choose an available sample. Open the original beside the extracted values, then review mappings and flagged items before accepting them.' },
  { id: 'assistant', label: 'Ask with context', href: '/home/', target: 'assistant', title: 'Bring a question and the relevant evidence', body: 'Attach verified deliveries or use your authorized connected sources. Inspect cited evidence, assumptions and gaps before acting on an answer.' },
  { id: 'simulation', label: 'Explore a scenario', href: '/process-simulation/', target: 'simulation', title: 'Compare possibilities before taking action', body: 'Simulation lets you explore assumptions and predicted outcomes. It does not change your manufacturing systems or approve an action.' },
  { id: 'organization', label: 'Set up your team', href: '/settings/organization/', target: 'organization', title: 'Keep access clear', body: 'See your organization and scope here. Organization administrators can grant specific roles and site access. Your personal details live separately under My profile.' },
] as const;
export type GuideTopic = typeof GUIDE_TOPICS[number]['id'];
type Progress = { seen: GuideTopic[] };
type Guide = { opened: boolean; topic: GuideTopic | null; seen: GuideTopic[]; open: (topic?: GuideTopic) => void; close: () => void; markSeen: (topic: GuideTopic) => void };
const Context = createContext<Guide | null>(null);

export function TutorialProvider({ children }: { children: ReactNode }) {
  const { user, organization, mode, loadingAccount } = useWorkspace();
  const key = `sievance.guide.v2:${user?.id ?? mode}:${organization?.id ?? 'local'}`;
  const [stored, setStored] = useState<{ key: string; progress: Progress } | null>(null);
  const [opened, setOpened] = useState(false);
  const [topic, setTopic] = useState<GuideTopic | null>(null);
  useEffect(() => {
    setOpened(false); setTopic(null);
    if (loadingAccount) return;
    let seen: GuideTopic[] = [];
    try { const value = JSON.parse(localStorage.getItem(key) ?? 'null'); if (Array.isArray(value?.seen)) seen = GUIDE_TOPICS.map(t => t.id).filter(id => value.seen.includes(id)); } catch { /* Optional guidance. */ }
    setStored({ key, progress: { seen } });
  }, [key, loadingAccount]);
  const seen = stored?.key === key ? stored.progress.seen : [];
  const markSeen = (id: GuideTopic) => {
    const progress = { seen: Array.from(new Set([...seen, id])) };
    setStored({ key, progress });
    try { localStorage.setItem(key, JSON.stringify(progress)); } catch { /* Keep progress for this session. */ }
  };
  return <Context.Provider value={{ opened, topic, seen, open: id => { setTopic(id ?? null); setOpened(true); }, close: () => setOpened(false), markSeen }}>{children}</Context.Provider>;
}
export function useTutorial() {
  const value = useContext(Context);
  if (!value) throw new Error('TutorialProvider is required');
  return value;
}
