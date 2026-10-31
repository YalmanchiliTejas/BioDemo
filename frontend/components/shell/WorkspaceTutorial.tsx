'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { BookOpen, X } from 'lucide-react';
import { Button, LinkButton } from '@/components/ui';
import { selectedOrganization, useSession } from '@/lib/auth';

const steps = [
  { href: '/dashboard', title: 'Start from your dashboard', body: 'See connection status and deliveries that need attention. Open a recent delivery to continue your work, or choose a tool below.' },
  { href: '/cmo', title: 'Inspect a delivery and its sources', body: 'Use your own files or choose an available sample. Open a delivery to compare extracted values with the original file and review flagged items. Visiting this page does not upload or approve anything.' },
  { href: '/home', title: 'Ask a question with context', body: 'The assistant can work with authorized connected sources and verified deliveries you attach. Inspect the cited evidence and any gaps before acting on an answer.' },
  { href: '/process-simulation', title: 'Explore a process scenario', body: 'Compare assumptions and predicted outcomes in Simulation. Predictions support review; they do not authorize changes in your manufacturing systems.' },
];
type Progress = { step: number; visible: boolean; complete: boolean };
const initial: Progress = { step: 0, visible: true, complete: false };

/** Local, per-person and per-organization guidance; never changes business records. */
export function WorkspaceTutorial() {
  const pathname = usePathname().replace(/\/$/, '');
  const { user, mode } = useSession();
  const organization = user ? selectedOrganization(user.id) : 'development';
  const key = `sievance.tutorial.v1:${user?.id ?? mode}:${organization}`;
  const [saved, setSaved] = useState<{ key: string; progress: Progress } | null>(null);
  useEffect(() => {
    let progress = { ...initial, visible: window.location.pathname.replace(/\/$/, '') === '/dashboard' };
    try {
      const value = JSON.parse(localStorage.getItem(key) ?? 'null');
      if (value && Number.isInteger(value.step) && value.step >= 0 && value.step < steps.length && typeof value.visible === 'boolean' && typeof value.complete === 'boolean') progress = value;
    } catch { /* Guidance still works when browser storage is unavailable. */ }
    setSaved({ key, progress });
  }, [key]);
  if (!saved || saved.key !== key) return null;
  const { progress } = saved;
  const update = (next: Progress) => {
    setSaved({ key, progress: next });
    try { localStorage.setItem(key, JSON.stringify(next)); } catch { /* Keep this session usable. */ }
  };
  if (!progress.visible) return <div className="mx-auto mb-4 flex max-w-6xl justify-end"><Button variant="ghost" onClick={() => update(progress.complete ? initial : { ...progress, visible: true })}><BookOpen size={15} />{progress.complete ? 'Replay tutorial' : 'Resume tutorial'}</Button></div>;
  const step = steps[progress.step];
  const onPage = pathname === step.href;
  return <section aria-label="Interactive workspace tutorial" className="mx-auto mb-8 max-w-6xl rounded-xl border border-brand-teal/30 bg-white p-5 sm:p-6">
    <div className="flex items-start justify-between gap-4"><div><p className="text-xs font-medium text-brand-teal">Workspace tutorial · {progress.step + 1} of {steps.length}</p><h2 className="mt-2 text-lg font-medium" aria-live="polite">{step.title}</h2></div><Button variant="ghost" aria-label="Dismiss tutorial" onClick={() => update({ ...progress, visible: false })}><X size={17} /></Button></div>
    <p className="mt-2 max-w-3xl text-sm leading-6 text-text-secondary">{step.body}</p>
    <div className="mt-4 flex flex-wrap items-center gap-3">
      {progress.step > 0 && <Button onClick={() => update({ ...progress, step: progress.step - 1 })}>Back</Button>}
      {!onPage && <LinkButton href={`${step.href}/`} variant="primary">Open {progress.step === 2 ? 'Assistant' : progress.step === 3 ? 'Simulation' : progress.step === 1 ? 'Deliveries' : 'Dashboard'}</LinkButton>}
      <Button variant={onPage ? 'primary' : 'secondary'} disabled={!onPage} onClick={() => update(progress.step === steps.length - 1 ? { ...progress, visible: false, complete: true } : { ...progress, step: progress.step + 1 })}>{progress.step === steps.length - 1 ? 'Finish tutorial' : 'Next step'}</Button>
      <Link href="/dashboard/" className="text-sm text-brand-teal underline">Return to dashboard</Link>
    </div>
    {!onPage && <p className="mt-3 text-xs text-text-secondary">Open the page to continue. You can pause this tour at any time.</p>}
  </section>;
}
