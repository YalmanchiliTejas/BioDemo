'use client';

import { useEffect, type ReactNode } from 'react';
import { usePathname } from 'next/navigation';
import { TopHeader } from './TopHeader';
import { Inspector } from './Inspector';
import { useAppContext } from '@/lib/app-context';
import { useAgent } from '@/lib/agent/agent-context';
import { AgentComposerModal } from '../agent/AgentComposerModal';
import { Companion } from '../agent/Companion';
import { CompanionProvider, useCompanion } from '@/lib/companion-context';

export function AppShell({ children }: { children: ReactNode }) {
  return <CompanionProvider><WorkspaceShell>{children}</WorkspaceShell></CompanionProvider>;
}

function WorkspaceShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { closeInspector, sidePaneTab, isInspectorOpen } = useAppContext();
  const { overlay, openOverlay, closeOverlay, pinned } = useAgent();
  const overlayOpen = overlay.open;
  const { open, show, close } = useCompanion();
  const home = pathname.replace(/\/$/, '') === '/home';

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        if (overlayOpen) closeOverlay();
        else openOverlay('FIND');
      }
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'j') {
        e.preventDefault();
        if (home) { document.querySelector<HTMLTextAreaElement>('[data-testid="engineering-chat"] textarea')?.focus(); return; }
        if (open) close();
        else { closeInspector(); show(); }
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [overlayOpen, openOverlay, closeOverlay, open, show, close, closeInspector, home]);

  // A route change closes transient panels so the new screen starts clean.
  useEffect(() => {
    if (!(isInspectorOpen && sidePaneTab === 'AGENT' && pinned)) closeInspector();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname]);

  return (
    <div className="h-[100dvh] flex flex-col bg-canvas text-text-primary">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:z-[100] focus:top-2 focus:left-2 focus:bg-surface focus:px-3 focus:py-2 focus:rounded">Skip to content</a>
      <TopHeader />
      <div className="flex flex-1 min-h-0">
        <main id="main" className={`flex-1 min-w-0 overflow-y-auto px-4 md:px-8 pt-8 ${home ? '' : 'pb-24'}`}>
          {children}
          <Companion home={home} />
        </main>
        <Inspector />
      </div>
      <AgentComposerModal />
    </div>
  );
}
