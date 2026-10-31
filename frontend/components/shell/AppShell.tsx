'use client';

import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { usePathname } from 'next/navigation';
import { TopHeader } from './TopHeader';
import { QuickFind } from './QuickFind';
import { Inspector } from './Inspector';
import { useAppContext } from '@/lib/app-context';
import { useAgent } from '@/lib/agent/agent-context';
import { AgentComposerModal } from '../agent/AgentComposerModal';
import { Companion } from '../agent/Companion';
import { CompanionProvider, useCompanion } from '@/lib/companion-context';
import { WorkspaceTutorial } from './WorkspaceTutorial';
import { Sidebar } from './Sidebar';
import { WorkspaceProvider } from '@/lib/workspace-context';
import { TutorialProvider, useTutorial } from '@/lib/tutorial-context';

export function AppShell({ children }: { children: ReactNode }) {
  return <WorkspaceProvider><TutorialProvider><CompanionProvider><WorkspaceShell>{children}</WorkspaceShell></CompanionProvider></TutorialProvider></WorkspaceProvider>;
}

function WorkspaceShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { closeInspector, sidePaneTab, isInspectorOpen } = useAppContext();
  const { pinned } = useAgent();
  const { open, show, close } = useCompanion();
  const guide = useTutorial();
  const [finding, setFinding] = useState(false);
  const home = pathname.replace(/\/$/, '') === '/home';
  const askAssistant = useCallback(() => {
    if (home) { document.querySelector<HTMLTextAreaElement>('[data-testid="engineering-chat"] textarea')?.focus(); return; }
    closeInspector(); show();
  }, [home, closeInspector, show]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setFinding(value => !value);
      }
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'j') {
        e.preventDefault();
        if (open && !home) close();
        else askAssistant();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, close, home, askAssistant]);

  // A route change closes transient panels so the new screen starts clean.
  useEffect(() => {
    if (!(isInspectorOpen && sidePaneTab === 'AGENT' && pinned)) closeInspector();
    if (!window.location.hash) document.getElementById('main')?.scrollTo(0, 0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname]);

  return (
    <div className="workspace-app">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:z-[100] focus:top-2 focus:left-2 focus:bg-surface focus:px-3 focus:py-2 focus:rounded">Skip to content</a>
      <Sidebar />
      <div className="workspace-main-column">
        <TopHeader onSearch={() => setFinding(true)} />
        <div className="workspace-content-row">
        <main id="main" className={`workspace-main ${home ? 'assistant-page' : ''}`}>
          {children}
          <Companion home={home} />
        </main>
        <Inspector />
        </div>
      </div>
      <WorkspaceTutorial />
      <QuickFind open={finding} onClose={() => setFinding(false)} onGuide={() => guide.open()} onAssistant={askAssistant} />
      <AgentComposerModal />
    </div>
  );
}
