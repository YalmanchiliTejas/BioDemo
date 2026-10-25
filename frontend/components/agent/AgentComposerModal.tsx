'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { usePathname } from 'next/navigation';
import { ArrowLeft, HelpCircle, Lock, Plus, Search, X, Zap } from 'lucide-react';
import { useAgent } from '@/lib/agent/agent-context';
import { ATTACHABLE_SCOPE, SCOPE_KIND_LABEL, frameForPath, screenContext } from '@/lib/agent/screens';
import { TEMPLATE_BY_ID, matchTemplate } from '@/lib/agent/templates';
import type { ComposerMode, ScopeChip } from '@/lib/agent/types';
import { Button, Callout, Pill } from '../ui';
import { FindPanel } from '../shell/CommandPalette';
import { cn } from '@/lib/cn';

const MODES: Array<{ key: ComposerMode; label: string; icon: typeof Search; hint: string }> = [
  { key: 'FIND', label: 'Find data', icon: Search, hint: '⌘K' },
  { key: 'ASK', label: 'Ask question', icon: HelpCircle, hint: '?' },
  { key: 'DELEGATE', label: 'Delegate task', icon: Zap, hint: '⚡' },
];

function Composer({ mode }: { mode: Exclude<ComposerMode, 'FIND'> }) {
  const pathname = usePathname();
  const { overlay, closeOverlay, launch } = useAgent();
  const preset = overlay.preset;
  const frame = preset?.frame ?? frameForPath(pathname) ?? 'HOME-01';
  const ctx = screenContext(frame);
  const presetTemplate = preset?.templateId ? TEMPLATE_BY_ID[preset.templateId] : undefined;

  const [prompt, setPrompt] = useState(preset?.prompt ?? (presetTemplate ? presetTemplate.summary : ''));
  const [scope, setScope] = useState<ScopeChip[]>(preset?.scope ?? presetTemplate?.defaultScope ?? ctx.scope);
  const [templateId, setTemplateId] = useState<string | undefined>(presetTemplate?.id);
  const [view, setView] = useState<'COMPOSE' | 'PREVIEW'>(presetTemplate ? 'PREVIEW' : 'COMPOSE');
  const [attachOpen, setAttachOpen] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => { if (view === 'COMPOSE') setTimeout(() => inputRef.current?.focus(), 0); }, [view]);

  const matched = useMemo(() => (templateId ? TEMPLATE_BY_ID[templateId] : prompt.trim() ? matchTemplate(prompt) : null), [templateId, prompt]);
  const fallback = TEMPLATE_BY_ID[ctx.suggestions[0]?.templateId ?? 'feed-cmms'];
  const plan = matched ?? fallback;
  const isFallback = !matched;

  const preview = (tid?: string, text?: string) => {
    if (tid) {
      setTemplateId(tid);
      const t = TEMPLATE_BY_ID[tid];
      // Merge the plan's own scope with anything the user attached (e.g. a selected span).
      // Keep what the user already chose; add plan chips only where that kind is not covered yet.
      setScope((s) => [...s, ...t.defaultScope.filter((c) => !s.some((x) => x.id === c.id || (c.kind !== 'RECORD' && x.kind === c.kind)))]);
    }
    if (text) setPrompt(text);
    setView('PREVIEW');
  };

  const start = () => launch(plan.id, { mode, prompt: prompt.trim() || plan.summary, scope, frame, href: pathname });

  if (view === 'PREVIEW') {
    return (
      <div className="flex flex-col max-h-[72vh]" onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) start(); }}>
        <div className="px-4 py-3 overflow-y-auto space-y-3">
          <div className="flex items-start justify-between gap-2">
            <div>
              <p className="text-[10.5px] font-semibold uppercase tracking-wider text-text-tertiary">Plan preview · confirm scope before anything runs</p>
              <p className="mt-0.5 text-[14px] font-semibold text-text-primary">{plan.title}</p>
              <p className="text-[12px] text-text-secondary">{plan.agent} · <code className="font-mono">{plan.taskId}</code></p>
            </div>
            <Pill tone="neutral">{mode === 'ASK' ? 'Question' : 'Delegated task'}</Pill>
          </div>
          {prompt.trim() && <p className="rounded-control bg-surface-secondary px-3 py-2 text-[12.5px] text-text-primary">“{prompt.trim()}”</p>}
          {isFallback && (
            <Callout tone="warning" title="No exact plan for this request in the demo">
              The closest available plan is shown. It will not answer anything outside the checkpoints listed below.
            </Callout>
          )}
          <ScopeEditor scope={scope} setScope={setScope} attachOpen={attachOpen} setAttachOpen={setAttachOpen} />
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wider text-text-tertiary">Checkpoints</p>
            <ol className="mt-1.5 space-y-1">
              {plan.checkpoints.map((c, i) => (
                <li key={c.id} className="flex gap-2 text-[12.5px]">
                  <span className="w-5 shrink-0 text-right font-mono text-text-muted">{i + 1}.</span>
                  <span className="min-w-0">
                    <span className="text-text-primary">{c.title}</span>
                    {c.subtask && <span className="ml-1 text-[11px] text-text-tertiary">· {c.subtask}</span>}
                    {plan.gates?.filter((g) => g.beforeStep === i).map((g) => <span key={g.id} className="block text-[11.5px] text-amber-700">May pause to ask: {g.kind === 'PERMISSION' ? 'source access' : 'a decision only you can make'}</span>)}
                  </span>
                </li>
              ))}
            </ol>
          </div>
          <div className="flex flex-wrap gap-1 items-center">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-text-tertiary mr-1">Reads</span>
            {plan.sources.map((s) => <Pill key={s} tone={plan.unavailableSources?.includes(s) ? 'muted' : 'neutral'}>{s}{plan.unavailableSources?.includes(s) ? ' · not connected' : ''}</Pill>)}
          </div>
          <p className="text-[12px] text-text-secondary">Returns: {plan.artifacts.map((a) => a.title).join(' · ')}.{plan.review ? ' Proposals stop at a Review Required gate.' : ''}</p>
        </div>
        <Footer>
          <Button size="sm" variant="ghost" onClick={() => setView('COMPOSE')}><ArrowLeft className="h-3 w-3" /> Edit request</Button>
          <Button size="sm" variant="primary" onClick={start}><Zap className="h-3 w-3" /> Start task <kbd className="ml-1 text-[10px] opacity-80">⌘↵</kbd></Button>
        </Footer>
      </div>
    );
  }

  return (
    <div className="flex flex-col max-h-[72vh]">
      <div className="px-4 py-3 overflow-y-auto space-y-3">
        <textarea
          ref={inputRef}
          value={prompt}
          onChange={(e) => { setPrompt(e.target.value); setTemplateId(undefined); }}
          onKeyDown={(e) => { if (e.key === 'Escape') closeOverlay(); if (e.key === 'Enter' && !e.shiftKey && prompt.trim()) { e.preventDefault(); preview(undefined); } }}
          rows={2}
          placeholder={mode === 'ASK' ? 'Ask about what you are looking at… e.g. “Why did MES-26073 feed drop after T+264h?”' : 'Describe the outcome you want… e.g. “Draft the Q-DEV-031 RCA with evidence”'}
          aria-label={mode === 'ASK' ? 'Question' : 'Task'}
          className="w-full resize-none rounded-control border border-border-strong px-3 py-2 text-[13px] focus:outline-none focus:ring-2 focus:ring-brand-teal"
        />
        <ScopeEditor scope={scope} setScope={setScope} attachOpen={attachOpen} setAttachOpen={setAttachOpen} />
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wider text-text-tertiary">Suggested for {ctx.frame}</p>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {ctx.suggestions.map((s) => (
              <button key={s.label} type="button" onClick={() => preview(s.templateId, s.label)} className="inline-flex items-center gap-1 h-7 px-2.5 rounded-pill border border-cyan-200 bg-brand-teal-light text-[12px] text-brand-teal-dark hover:bg-cyan-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-teal">
                <Zap className="h-3 w-3" aria-hidden />{s.label}
              </button>
            ))}
          </div>
        </div>
      </div>
      <Footer>
        <Button size="sm" variant="ghost" onClick={closeOverlay}>Cancel</Button>
        <Button size="sm" variant="primary" onClick={() => preview(undefined)} disabled={!prompt.trim()}>Preview plan</Button>
      </Footer>
    </div>
  );
}

function ScopeEditor({ scope, setScope, attachOpen, setAttachOpen }: { scope: ScopeChip[]; setScope: (fn: (s: ScopeChip[]) => ScopeChip[]) => void; attachOpen: boolean; setAttachOpen: (o: boolean) => void }) {
  const available = ATTACHABLE_SCOPE.filter((c) => !scope.some((s) => s.id === c.id));
  return (
    <div>
      <p className="text-[11px] font-semibold uppercase tracking-wider text-text-tertiary">Scope</p>
      <ul className="mt-1.5 flex flex-wrap gap-1.5">
        {scope.map((c) => (
          <li key={c.id} className="inline-flex items-center gap-1 max-w-full pl-2 pr-1 h-7 rounded-control border border-border-hairline bg-surface-secondary text-[11.5px]">
            <span className="text-text-tertiary whitespace-nowrap">{SCOPE_KIND_LABEL[c.kind]}:</span>
            <span className="font-mono text-text-primary truncate">{c.value}</span>
            <button type="button" onClick={() => setScope((s) => s.filter((x) => x.id !== c.id))} className="p-0.5 rounded text-text-tertiary hover:bg-surface-hover hover:text-text-primary" aria-label={`Remove ${c.value}`}><X className="h-3 w-3" /></button>
          </li>
        ))}
        <li className="relative">
          <button type="button" onClick={() => setAttachOpen(!attachOpen)} disabled={!available.length} className="inline-flex items-center gap-1 h-7 px-2 rounded-control border border-dashed border-border-strong text-[11.5px] text-text-secondary hover:bg-surface-secondary disabled:opacity-50" aria-expanded={attachOpen}>
            <Plus className="h-3 w-3" aria-hidden /> Attach
          </button>
          {attachOpen && (
            <div className="absolute left-0 top-8 z-10 w-80 bg-surface border border-border-hairline rounded-card shadow-lg py-1">
              {available.map((c) => (
                <button key={c.id} type="button" onClick={() => { setScope((s) => [...s, c]); setAttachOpen(false); }} className="w-full px-3 py-1.5 text-left text-[12px] hover:bg-surface-secondary">
                  <span className="text-text-tertiary">{SCOPE_KIND_LABEL[c.kind]}:</span> <span className="font-mono">{c.value}</span>
                </button>
              ))}
            </div>
          )}
        </li>
      </ul>
      {scope.length === 0 && <p className="mt-1 text-[11.5px] text-amber-700">No scope attached. The agent will use the whole campaign, which takes longer.</p>}
    </div>
  );
}

function Footer({ children }: { children: React.ReactNode }) {
  return (
    <div className="border-t border-border-hairline bg-surface-secondary/50 px-4 py-2.5 flex items-center gap-3">
      <p className="flex-1 min-w-0 flex items-start gap-1 text-[11px] text-text-tertiary leading-snug"><Lock className="h-3 w-3 mt-px shrink-0" aria-hidden /> Access: read-only historian, LIMS, CMMS, QMS · Writes: none (read-only sandbox staging)</p>
      <div className="flex items-center gap-2 shrink-0">{children}</div>
    </div>
  );
}

/** Global command overlay (⌘K): Find data · Ask question · Delegate task. */
export function AgentComposerModal() {
  const { overlay, closeOverlay, setOverlayMode, openOverlay } = useAgent();
  const [key, setKey] = useState(0);
  useEffect(() => { if (overlay.open) setKey((k) => k + 1); }, [overlay.open, overlay.preset]);
  useEffect(() => {
    if (!overlay.open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') closeOverlay(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [overlay.open, closeOverlay]);
  if (!overlay.open) return null;

  return (
    <div className="fixed inset-0 z-[90] flex items-start justify-center pt-[10vh] px-4">
      <div className="absolute inset-0 bg-slate-900/40" onClick={closeOverlay} aria-hidden />
      <div role="dialog" aria-modal="true" aria-label="Command and agent composer" className="relative w-full max-w-[640px] bg-surface rounded-xl border border-border-hairline shadow-2xl overflow-hidden">
        <div role="tablist" className="flex items-center gap-1 px-2 pt-2 border-b border-border-hairline">
          {MODES.map((m) => (
            <button key={m.key} role="tab" aria-selected={overlay.mode === m.key} onClick={() => setOverlayMode(m.key)} className={cn('flex items-center gap-1.5 h-8 px-3 -mb-px border-b-2 text-[12.5px] font-medium', overlay.mode === m.key ? 'border-brand-teal text-text-primary' : 'border-transparent text-text-tertiary hover:text-text-primary')}>
              <m.icon className="h-3.5 w-3.5" aria-hidden />{m.label}
            </button>
          ))}
          <button type="button" onClick={closeOverlay} className="ml-auto p-1 mb-1 rounded text-text-tertiary hover:bg-surface-secondary" aria-label="Close"><X className="h-4 w-4" /></button>
        </div>
        {overlay.mode === 'FIND'
          ? <FindPanel onClose={closeOverlay} onAsk={(text) => openOverlay('ASK', { ...overlay.preset, prompt: text })} />
          : <Composer key={key} mode={overlay.mode} />}
      </div>
    </div>
  );
}
