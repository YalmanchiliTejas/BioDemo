'use client';

import { useCallback, useEffect, useRef } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ArrowLeft, ArrowUpRight, Check, CheckCircle2 } from 'lucide-react';
import { GUIDE_TOPICS, useTutorial } from '@/lib/tutorial-context';
import { useDemo } from '@/lib/demo-api';
import { navGroups } from '@/lib/navigation';
import { PointingGuide } from './PointingGuide';

const demoDestinations = new Set(navGroups(true).flatMap(group => group.items.map(item => `${item.href}/`)));

export function WorkspaceTutorial() {
  const { opened, topic, close } = useTutorial();
  const onOverview = usePathname().replace(/\/$/, '') === '/dashboard';
  const wasOnOverview = useRef(onOverview);
  const dashboardTour = topic === 'dashboard' && (onOverview || wasOnOverview.current);
  useEffect(() => {
    const leftOverview = wasOnOverview.current && !onOverview;
    wasOnOverview.current = onOverview;
    if (leftOverview && topic === 'dashboard') close();
  }, [onOverview, topic, close]);
  return opened && !dashboardTour ? <OpenWorkspaceGuide /> : null;
}

function OpenWorkspaceGuide() {
  const guide = useTutorial();
  const pathname = usePathname();
  const { demo } = useDemo();
  const { close } = guide;
  const dismiss = useCallback(() => {
    close();
    document.querySelector<HTMLButtonElement>('[data-guide="help"]')?.focus({ preventScroll: true });
  }, [close]);
  const topics = demo ? GUIDE_TOPICS.filter(topic => demoDestinations.has(topic.href)) : GUIDE_TOPICS;
  const current = topics.find(topic => topic.id === guide.topic);
  const arrived = pathname.replace(/\/$/, '') === current?.href.replace(/\/$/, '');
  const anchor = current ? (arrived ? current.control : current.target) : 'help';
  return <PointingGuide label="Workspace guide" anchor={anchor} focusKey={current?.id ?? 'topics'} locate={arrived}
    narration={current ? `${current.title}. ${current.body}` : undefined} onClose={dismiss}>
    {current ? <>
      <button type="button" className="guide-back" onClick={() => guide.open()}><ArrowLeft size={14} /> All topics</button>
      <div aria-live="polite"><h2>{current.title}</h2><p>{current.body}</p></div>
      <div className="guide-actions">
        {!arrived && <Link className="chrome-button primary" href={current.href}>Open {current.id === 'dashboard' ? 'Overview' : current.id} <ArrowUpRight size={15} /></Link>}
        <button type="button" className={`chrome-button${arrived ? ' primary' : ''}`} onClick={() => { guide.markSeen(current.id); guide.open(); }}><Check size={15} /> Got it</button>
      </div>
    </> : <>
      <h2>What would you like to do?</h2>
      <p>Pick a task and follow the pointer to the relevant control.</p>
      <ul className="guide-topics">{topics.map(topic => <li key={topic.id}><button type="button" onClick={() => guide.open(topic.id)}><span className={guide.seen.includes(topic.id) ? 'guide-check seen' : 'guide-check'}><CheckCircle2 size={16} aria-hidden="true" /></span>{topic.label}<ArrowUpRight size={14} aria-hidden="true" /></button></li>)}</ul>
      <small>{topics.filter(topic => guide.seen.includes(topic.id)).length} of {topics.length} topics explored</small>
    </>}
  </PointingGuide>;
}
