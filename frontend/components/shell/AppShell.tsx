'use client';

import { useEffect, useState, type ReactNode } from 'react';
import { usePathname } from 'next/navigation';
import { TopHeader } from './TopHeader';
import { Sidebar } from './Sidebar';
import { Inspector } from './Inspector';
import { RunStrip } from './RunStrip';
import { useAppContext } from '@/lib/app-context';
import { useAgent } from '@/lib/agent/agent-context';
import { AgentComposerModal } from '../agent/AgentComposerModal';
import { AgentBottomRunStrip } from '../agent/AgentBottomRunStrip';

export function AppShell({ children }: { children: ReactNode }) {
  const [navOpen, setNavOpen] = useState(false);
  const pathname = usePathname();
  const { closeInspector, sidePaneTab, isInspectorOpen } = useAppContext();
  const { overlay, openOverlay, closeOverlay, pinned } = useAgent();
  const overlayOpen = overlay.open;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        if (overlayOpen) closeOverlay();
        else openOverlay('FIND');
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [overlayOpen, openOverlay, closeOverlay]);

  // A route change closes transient panels so the new screen starts clean. The agent dock
  // stays open only when pinned; otherwise it collapses to the run strip and the task keeps running.
  useEffect(() => {
    setNavOpen(false);
    if (!(isInspectorOpen && sidePaneTab === 'AGENT' && pinned)) closeInspector();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname]);

  return (
    <div className="h-screen flex flex-col bg-canvas text-text-primary">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:z-[100] focus:top-2 focus:left-2 focus:bg-surface focus:px-3 focus:py-2 focus:rounded">Skip to content</a>
      <TopHeader onToggleNav={() => setNavOpen((o) => !o)} />
      <div className="flex flex-1 min-h-0">
        <aside className="hidden lg:block w-[228px] shrink-0 bg-surface border-r border-border-hairline">
          <Sidebar />
        </aside>
        {navOpen && (
          <div className="lg:hidden fixed inset-0 z-[65]">
            <div className="absolute inset-0 bg-slate-900/30" onClick={() => setNavOpen(false)} aria-hidden />
            <aside className="relative w-[260px] h-full bg-surface border-r border-border-hairline shadow-xl">
              <Sidebar onNavigate={() => setNavOpen(false)} />
            </aside>
          </div>
        )}
        <main id="main" className="flex-1 min-w-0 overflow-y-auto px-4 md:px-6 py-4">
          {children}
        </main>
        <Inspector />
      </div>
      <RunStrip />
      <AgentBottomRunStrip />
      <AgentComposerModal />
    </div>
  );
}
