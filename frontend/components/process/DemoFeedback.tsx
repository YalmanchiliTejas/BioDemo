'use client';

import { useState, type ReactNode } from 'react';
import { MessageSquareText, Play, ThumbsDown, ThumbsUp, X } from 'lucide-react';
import { sendFeedback, type Feedback, type Scenario } from '@/lib/demo-api';

function useSend() {
  const [state, setState] = useState<'idle' | 'busy' | 'sent'>('idle');
  const [error, setError] = useState('');
  async function submit(feedback: Feedback) {
    setState('busy'); setError('');
    try { await sendFeedback(feedback); setState('sent'); }
    catch (e) { setError((e as Error).message); setState('idle'); }
  }
  return { state, error, submit };
}

function Scale({ label, value, onChange }: { label: string; value: number; onChange: (v: number) => void }) {
  return <fieldset className="flex flex-wrap items-center gap-2"><legend className="mb-1 w-full text-text-secondary">{label}</legend>
    {[1, 2, 3, 4, 5].map(n => <button key={n} type="button" aria-pressed={value === n} onClick={() => onChange(n)}
      className={`h-7 w-7 rounded-control border text-xs ${value === n ? 'border-brand-teal bg-brand-teal text-white' : 'border-border-hairline bg-surface hover:border-brand-teal'}`}>{n}</button>)}
    <span className="text-[11px] text-text-tertiary">1 = not at all · 5 = very</span></fieldset>;
}

/** 👍/👎 under an assistant answer in a demo workspace; a comment is offered on 👎. */
export function AnswerFeedback({ turnId }: { turnId: string }) {
  const { state, error, submit } = useSend();
  const [down, setDown] = useState(false);
  const [comment, setComment] = useState('');
  if (state === 'sent') return <p role="status" className="mt-2 text-xs text-status-success">Thanks, that helps us improve.</p>;
  return <div className="mt-2 text-xs text-text-tertiary">
    <span className="mr-2">Was this useful?</span>
    <button type="button" aria-label="Useful" disabled={state === 'busy'} onClick={() => void submit({ kind: 'answer', turn_id: turnId, rating: 'up' })}
      className="mr-1 inline-flex h-7 w-7 items-center justify-center rounded-control hover:bg-surface-secondary hover:text-text-primary"><ThumbsUp size={14} /></button>
    <button type="button" aria-label="Not useful" aria-expanded={down} onClick={() => setDown(true)}
      className="inline-flex h-7 w-7 items-center justify-center rounded-control hover:bg-surface-secondary hover:text-text-primary"><ThumbsDown size={14} /></button>
    {down && <form className="mt-2 flex flex-wrap gap-2" onSubmit={e => { e.preventDefault(); void submit({ kind: 'answer', turn_id: turnId, rating: 'down', comment: comment.trim() || undefined }); }}>
      <input autoFocus value={comment} onChange={e => setComment(e.target.value)} maxLength={1000} placeholder="What was wrong or missing? (optional)"
        className="h-8 min-w-[240px] flex-1 rounded-control border border-border-hairline bg-surface px-2 text-xs text-text-primary outline-none focus:border-brand-teal" />
      <button type="submit" disabled={state === 'busy'} className="rounded-control bg-brand-teal px-3 text-xs font-medium text-white disabled:opacity-50">Send</button>
    </form>}
    {error && <p role="alert" className="mt-1 text-status-critical">{error}</p>}
  </div>;
}

/** The persona's scenarios: situation, Try it, what a good answer should do, and a short rating form. */
export function ScenarioCards({ scenarios, onTry, disabled }: { scenarios: Scenario[]; onTry: (prompt: string) => void; disabled?: boolean }) {
  return <div className="space-y-3">{scenarios.map(s => <ScenarioCard key={s.scenario_id} scenario={s} onTry={onTry} disabled={disabled} />)}</div>;
}

function ScenarioCard({ scenario, onTry, disabled }: { scenario: Scenario; onTry: (prompt: string) => void; disabled?: boolean }) {
  const { state, error, submit } = useSend();
  const [rating, setRating] = useState(false);
  const [realistic, setRealistic] = useState(0);
  const [useful, setUseful] = useState(0);
  const [comment, setComment] = useState('');
  return <article className="rounded-card border border-border-hairline bg-surface p-4 text-sm" aria-label={scenario.title}>
    <p className="font-medium text-text-primary">{scenario.title}</p>
    <p className="mt-1 leading-6 text-text-secondary">{scenario.situation}</p>
    {!!scenario.look_for?.length && <details className="mt-2 text-xs text-text-secondary"><summary className="cursor-pointer">What a good answer should do</summary>
      <ul className="mt-1.5 list-disc space-y-1 pl-4">{scenario.look_for.map(item => <li key={item}>{item}</li>)}</ul></details>}
    <div className="mt-3 flex flex-wrap items-center gap-3">
      <button type="button" disabled={disabled} onClick={() => onTry(scenario.prompt)}
        className="inline-flex items-center gap-1.5 rounded-control bg-brand-teal px-3 py-1.5 text-xs font-medium text-white hover:bg-brand-teal-dark disabled:opacity-50"><Play size={12} />Try it</button>
      {state !== 'sent' && <button type="button" onClick={() => setRating(r => !r)} aria-expanded={rating} className="text-xs text-text-tertiary underline-offset-2 hover:text-text-secondary hover:underline">Rate this scenario</button>}
      {state === 'sent' && <span role="status" className="text-xs text-status-success">Thanks for rating this scenario.</span>}
    </div>
    {rating && state !== 'sent' && <form className="mt-3 space-y-3 rounded-control bg-surface-secondary/60 p-3 text-xs" onSubmit={e => {
      e.preventDefault(); void submit({ kind: 'scenario', scenario_id: scenario.scenario_id, realistic: realistic || undefined, useful: useful || undefined, comment: comment.trim() || undefined });
    }}>
      <Scale label="How realistic is this situation?" value={realistic} onChange={setRealistic} />
      <Scale label="How useful would the assistant’s help be here, in your work?" value={useful} onChange={setUseful} />
      <textarea value={comment} onChange={e => setComment(e.target.value)} rows={2} maxLength={2000} placeholder="Anything about it that rings true, or doesn’t? (optional)"
        className="block w-full rounded-control border border-border-hairline bg-surface p-2 text-xs outline-none focus:border-brand-teal" />
      {error && <p role="alert" className="text-status-critical">{error}</p>}
      <button type="submit" disabled={state === 'busy' || (!realistic && !useful && !comment.trim())} className="rounded-control bg-brand-teal px-3 py-1.5 font-medium text-white disabled:opacity-40">Send rating</button>
    </form>}
  </article>;
}

/** Header "Feedback" button and form for demo workspaces. */
export function OverallFeedbackButton() {
  const [open, setOpen] = useState(false);
  return <>
    <button type="button" onClick={() => setOpen(true)} className="chrome-button" aria-haspopup="dialog"><MessageSquareText size={15} />Feedback</button>
    {open && <Modal title="How is the demo working for you?" onClose={() => setOpen(false)}><OverallForm onDone={() => setOpen(false)} /></Modal>}
  </>;
}

function OverallForm({ onDone }: { onDone: () => void }) {
  const { state, error, submit } = useSend();
  const [useful, setUseful] = useState(0);
  const [use, setUse] = useState<'yes' | 'maybe' | 'no' | ''>('');
  const [missing, setMissing] = useState('');
  const [email, setEmail] = useState('');
  if (state === 'sent') return <div className="space-y-4 text-sm"><p role="status">Thank you. We read every response.</p>
    <button type="button" onClick={onDone} className="rounded-control bg-brand-teal px-3 py-2 text-xs font-medium text-white">Close</button></div>;
  return <form className="space-y-4 text-xs" onSubmit={e => {
    e.preventDefault(); void submit({ kind: 'overall', useful: useful || undefined, would_use: use || undefined, comment: missing.trim() || undefined, email: email.trim() || undefined });
  }}>
    <Scale label="Overall, how useful was it?" value={useful} onChange={setUseful} />
    <fieldset><legend className="mb-1 text-text-secondary">Would you use this in your work?</legend>
      <div className="flex gap-2">{(['yes', 'maybe', 'no'] as const).map(v => <button key={v} type="button" aria-pressed={use === v} onClick={() => setUse(v)}
        className={`rounded-control border px-3 py-1.5 capitalize ${use === v ? 'border-brand-teal bg-brand-teal text-white' : 'border-border-hairline bg-surface hover:border-brand-teal'}`}>{v}</button>)}</div></fieldset>
    <label className="block text-text-secondary">What’s missing, or what would make it worth using?
      <textarea value={missing} onChange={e => setMissing(e.target.value)} rows={3} maxLength={4000} className="mt-1 block w-full rounded-control border border-border-hairline bg-surface p-2 text-text-primary outline-none focus:border-brand-teal" /></label>
    <label className="block text-text-secondary">Email, if you’d like us to follow up (optional)
      <input type="email" value={email} onChange={e => setEmail(e.target.value)} maxLength={200} placeholder="you@company.com" className="mt-1 block h-9 w-full rounded-control border border-border-hairline bg-surface px-2 text-text-primary outline-none focus:border-brand-teal" /></label>
    {error && <p role="alert" className="text-status-critical">{error}</p>}
    <button type="submit" disabled={state === 'busy' || (!useful && !use && !missing.trim())} className="rounded-control bg-brand-teal px-3 py-2 font-medium text-white disabled:opacity-40">Send feedback</button>
  </form>;
}

export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  return <div className="fixed inset-0 z-[90] flex items-center justify-center bg-ink/30 p-4" onKeyDown={e => { if (e.key === 'Escape') onClose(); }}>
    <button type="button" aria-label="Close" className="absolute inset-0 cursor-default" onClick={onClose} />
    <section role="dialog" aria-modal="true" aria-label={title} className="relative w-full max-w-md rounded-card border border-border-hairline bg-surface p-5 shadow-2xl">
      <div className="mb-4 flex items-start justify-between gap-3"><h2 className="text-sm font-medium text-text-primary">{title}</h2>
        <button type="button" onClick={onClose} aria-label="Close feedback" className="rounded p-1 text-text-tertiary hover:bg-surface-secondary"><X size={16} /></button></div>
      {children}
    </section>
  </div>;
}
