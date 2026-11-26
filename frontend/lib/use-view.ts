'use client';

import { useEffect, useSyncExternalStore } from 'react';
import { icpFor, isIcp, type Icp } from './overview-views';
import { useWorkspace } from './workspace-context';

// One view per person and organization, shared by the overview and the sidebar. Browser storage is a convenience:
// the choice is also held in memory, so switching views still works when storage is blocked.
const memory = new Map<string, string>();
const listeners = new Set<() => void>();
const subscribe = (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; };
const read = (key: string) => { if (memory.has(key)) return memory.get(key)!; try { return localStorage.getItem(key); } catch { return null; } };
const write = (key: string, value: string) => { memory.set(key, value); try { localStorage.setItem(key, value); } catch { /* A convenience only. */ } };

/** The view in use: the person's own choice for this organization, else the one their demo persona or role starts on. */
export function useView(persona?: string | null): { icp: Icp; choose: (next: Icp) => void } {
  const { organization, user } = useWorkspace();
  const key = `sievance.overview.view:${organization?.id ?? ''}`;
  // While the organization is still loading, keep the view this person last saw so the sidebar does not rearrange itself.
  const last = `sievance.overview.view:last:${user?.id ?? ''}`;
  const saved = useSyncExternalStore(subscribe, () => read(organization ? key : last), () => null);
  const icp = isIcp(saved) ? saved : organization ? icpFor(organization.roles, persona) : 'everyone';
  useEffect(() => { if (organization) write(last, icp); }, [organization, last, icp]);
  return { icp, choose: next => { write(key, next); listeners.forEach(listener => listener()); } };
}
