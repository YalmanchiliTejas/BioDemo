'use client';

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';
import { useWorkspace } from './workspace-context';

export const GUIDE_TOPICS = [
  { id: 'dashboard', label: 'Find your bearings', href: '/dashboard/', target: 'dashboard', control: 'overview-view', title: 'Find the work that needs you', body: 'Use View to see the summaries for your role. Open a summary to go straight to the work.' },
  { id: 'connections', label: 'Connect your data', href: '/sources/', target: 'connections', control: 'setup-source-search', title: 'Start with a source you already use', body: 'Find an authorized system and check a sample against its source. You choose when collection starts.' },
  { id: 'deliveries', label: 'Check a delivery', href: '/cmo/', target: 'deliveries', control: 'delivery-files', title: 'Follow a value back to its source', body: 'Choose a delivery or upload approved files. Compare the extracted values with their originals before accepting them.' },
  { id: 'assistant', label: 'Ask with context', href: '/home/', target: 'assistant', control: 'assistant-question', title: 'Bring a question and the relevant evidence', body: 'Describe what you want to check and attach the relevant records. Inspect cited evidence and gaps before acting on an answer.' },
  { id: 'simulation', label: 'Explore a scenario', href: '/process-simulation/', target: 'simulation', control: 'simulation-examples', title: 'Explore a process change', body: 'Use an example to see a forecast and its assumptions. Keep it as evidence for engineering review.' },
  { id: 'organization', label: 'Set up your team', href: '/settings/organization/', target: 'organization', control: 'team-access', title: 'Check your team’s access', body: 'Review the roles and site scopes. Organization administrators can grant access to people with an account.' },
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
  const close = useCallback(() => setOpened(false), []);
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
  return <Context.Provider value={{ opened, topic, seen, open: id => { setTopic(id ?? null); setOpened(true); }, close, markSeen }}>{children}</Context.Provider>;
}
export function useTutorial() {
  const value = useContext(Context);
  if (!value) throw new Error('TutorialProvider is required');
  return value;
}
