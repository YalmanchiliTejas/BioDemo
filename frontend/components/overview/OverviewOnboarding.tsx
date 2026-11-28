'use client';

import { useCallback, useState } from 'react';
import { ArrowLeft, ArrowRight, Check, MousePointer2, X } from 'lucide-react';
import { PointingGuide } from '@/components/shell/PointingGuide';
import { useTutorial } from '@/lib/tutorial-context';

type Step = { anchor: string; title: string; body: string };
type WorklistState = 'loading' | 'ready' | 'failed';

const worklistSteps: Record<WorklistState, Step> = {
  loading: { anchor: 'overview-worklist-loading', title: 'Read what needs your attention', body: 'When the worklist loads, start with items waiting on you. In-progress work and recent completions appear below it.' },
  ready: { anchor: 'overview-needs-you', title: 'Start with Needs you', body: 'Look here for work waiting for your review or reply. Open a row to see the details. In-progress work and recent completions appear below.' },
  failed: { anchor: 'overview-status', title: 'Check what’s available', body: 'Read the status on each summary below. Open an available area to inspect its records and follow up there.' },
};

const viewStep: Step = {
  anchor: 'overview-view',
  title: 'Choose a view for your work',
  body: 'Use View to bring the summaries you need into focus. Change it whenever you switch tasks.',
};

const summaryStep: Step = {
  anchor: 'overview-summary',
  title: 'Open a summary to see the details',
  body: 'Each card opens the corresponding area. Read its status, then select it to see the records or tools behind it.',
};

function focusOverviewGuide() {
  document.querySelector<HTMLButtonElement>('[data-guide="overview-guide-launch"]')?.focus({ preventScroll: true });
}

export function OverviewGuideButton() {
  const guide = useTutorial();
  const active = guide.opened && guide.topic === 'dashboard';
  return <button type="button" data-guide="overview-guide-launch" className="chrome-button" aria-expanded={active}
    onClick={() => active ? guide.close() : guide.open('dashboard')}><MousePointer2 size={15} />Overview guide</button>;
}

export function OverviewOnboarding({ worklist }: { worklist: WorklistState }) {
  const guide = useTutorial();
  return <>
    {guide.showOverviewIntro && <aside className="overview-intro" aria-labelledby="overview-intro-title">
      <span className="overview-intro-icon" aria-hidden="true"><MousePointer2 size={20} /></span>
      <div className="overview-intro-copy">
        <h2 id="overview-intro-title">Start with what needs your attention</h2>
        <p>See what’s waiting on you, track work in progress, and open the details behind each summary.</p>
      </div>
      <button type="button" className="chrome-button primary" onClick={() => guide.open('dashboard')}>Show me around <ArrowRight size={15} /></button>
      <button type="button" className="chrome-icon overview-intro-dismiss" aria-label="Dismiss overview introduction"
        onClick={() => { guide.dismissOverviewIntro(); focusOverviewGuide(); }}><X size={17} /></button>
    </aside>}
    {guide.opened && guide.topic === 'dashboard' && <OverviewTour worklist={worklist} />}
  </>;
}

function OverviewTour({ worklist }: { worklist: WorklistState }) {
  const { close, markSeen } = useTutorial();
  const [step, setStep] = useState(0);
  const steps = [worklistSteps[worklist], viewStep, summaryStep];
  const current = steps[step];
  const last = step === steps.length - 1;
  const dismiss = useCallback(() => { close(); focusOverviewGuide(); }, [close]);
  const finish = () => {
    markSeen('dashboard');
    close();
    const firstSummary = document.querySelector<HTMLElement>('[data-guide="overview-summary"]');
    if (firstSummary) firstSummary.focus({ preventScroll: true });
    else focusOverviewGuide();
  };

  return <PointingGuide label="Overview guide" anchor={current.anchor} reveal locate focusKey={String(step)}
    narration={`${current.title}. ${current.body}`} onClose={dismiss}>
    <div aria-live="polite">
      <small className="overview-tour-progress">Step {step + 1} of {steps.length}</small>
      <h2>{current.title}</h2>
      <p>{current.body}</p>
    </div>
    <div className="guide-actions">
      {step > 0 && <button type="button" className="chrome-button" onClick={() => setStep(step - 1)}><ArrowLeft size={15} /> Back</button>}
      {last ? <button type="button" className="chrome-button primary" onClick={finish}><Check size={15} /> Finish guide</button>
        : <button type="button" className="chrome-button primary" onClick={() => setStep(step + 1)}>Next <ArrowRight size={15} /></button>}
    </div>
  </PointingGuide>;
}
