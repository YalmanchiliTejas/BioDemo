'use client';

import Link from 'next/link';
import { Bot, FileSearch, PanelRightClose } from 'lucide-react';
import { useAppContext, type InspectorEntity } from '@/lib/app-context';
import { useAgent } from '@/lib/agent/agent-context';
import { AgentDock } from '../agent/AgentDock';
import { cn } from '@/lib/cn';
import { CITATIONS } from '@/fixtures/biomanufacturingData';
import { EvidenceDrawer } from '../EvidenceDrawer';
import { EvidenceChip, Hash, SectionLabel, buttonClass } from '../ui';

const TYPE_LABEL = { EVIDENCE: 'Evidence', SAMPLE: 'Sample', WORK_ORDER: 'Work order', HYPOTHESIS: 'Hypothesis', AGENT_STEP: 'Agent step', RECORD: 'Record', PROJECT: 'Project', SCHEDULE_ITEM: 'Schedule item' } as const;

/**
 * The single right-hand slot. When an agent task exists it hosts two tabs —
 * Agent Copilot (440px dock) and Evidence & Provenance — so opening a citation from the
 * agent never stacks a second sidebar and never loses task state.
 */
export function Inspector() {
  const { isInspectorOpen, activeInspectorEntity: e, closeInspector, sidePaneTab, setSidePaneTab } = useAppContext();
  const { tasks } = useAgent();
  if (!isInspectorOpen) return null;
  const shared = tasks.length > 0 || sidePaneTab === 'AGENT';
  const tab = shared ? sidePaneTab : 'EVIDENCE';

  return (
    <aside
      aria-label={tab === 'AGENT' ? 'Agent dock' : 'Inspector'}
      className={cn(
        'fixed inset-y-0 right-0 z-[60] w-full bg-surface border-l border-border-hairline shadow-xl xl:shadow-none xl:static xl:z-auto xl:max-w-none shrink-0 flex flex-col',
        shared ? 'max-w-[440px] xl:w-[440px]' : 'max-w-[360px] xl:w-[360px]',
      )}
    >
      {shared && (
        <div className="flex items-center gap-1 px-2 h-10 shrink-0 border-b border-border-hairline bg-surface-secondary/60" role="tablist" aria-label="Side panel">
          {([['AGENT', 'Agent Copilot', Bot], ['EVIDENCE', 'Evidence & Provenance', FileSearch]] as const).map(([k, label, Icon]) => (
            <button key={k} role="tab" aria-selected={tab === k} onClick={() => setSidePaneTab(k)} className={cn('flex items-center gap-1.5 h-7 px-2.5 rounded-control text-[12.5px] font-medium', tab === k ? 'bg-surface text-text-primary shadow-sm border border-border-hairline' : 'text-text-tertiary hover:text-text-primary')}>
              <Icon className="h-3.5 w-3.5" aria-hidden />{label}
            </button>
          ))}
          <button onClick={closeInspector} className="ml-auto p-1 rounded text-text-tertiary hover:bg-surface hover:text-text-primary" aria-label="Close side panel"><PanelRightClose className="h-4 w-4" /></button>
        </div>
      )}
      <div className="flex-1 min-h-0">
        {tab === 'AGENT' ? <AgentDock /> : e ? <EntityPanel e={e} onClose={closeInspector} /> : (
          <p className="p-4 text-[12.5px] text-text-tertiary">Select any citation chip to see its raw excerpt, transformation, timestamp and content hash here. Your agent task keeps running in the other tab.</p>
        )}
      </div>
    </aside>
  );
}

function EntityPanel({ e, onClose }: { e: InspectorEntity; onClose: () => void }) {
  const closeInspector = onClose;
  const citation = e.type === 'EVIDENCE' ? CITATIONS[e.id] : undefined;

  return (
    <>
      {citation ? (
        <EvidenceDrawer inline isOpen onClose={closeInspector} citation={citation} />
      ) : (
        <div className="flex flex-col h-full">
          <div className="flex items-start justify-between gap-2 px-4 py-3 border-b border-border-hairline">
            <div className="min-w-0">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-text-tertiary">{TYPE_LABEL[e.type]}</p>
              <h2 className="mt-1 text-sm font-semibold text-text-primary">{e.title ?? e.id}</h2>
              <code className="text-xs font-mono text-text-secondary">{e.id}</code>
            </div>
            <button onClick={closeInspector} className="p-1 rounded text-text-tertiary hover:bg-surface-secondary" aria-label="Close inspector">
              <PanelRightClose className="h-4 w-4" />
            </button>
          </div>
          <div className="flex-1 overflow-y-auto px-4 py-4 space-y-5">
            {e.metadata && (
              <div>
                <SectionLabel>Details</SectionLabel>
                <dl className="mt-2 space-y-2 text-[12.5px]">
                  {Object.entries(e.metadata).map(([k, v]) => (
                    <div key={k} className="flex justify-between gap-3">
                      <dt className="text-text-tertiary shrink-0">{k}</dt>
                      <dd className="text-text-primary text-right tabular-nums">{v}</dd>
                    </div>
                  ))}
                </dl>
              </div>
            )}
            {e.citations && e.citations.length > 0 && (
              <div>
                <SectionLabel>Supporting sources</SectionLabel>
                <div className="mt-2 flex flex-col items-start gap-1.5">
                  {e.citations.map((c) => <EvidenceChip key={c} id={c} />)}
                </div>
              </div>
            )}
            {e.sha256 && (
              <div>
                <SectionLabel>Content hash</SectionLabel>
                <Hash value={e.sha256} full className="mt-2 block break-all" />
              </div>
            )}
            {e.sourceFile && <p className="text-xs text-text-tertiary">Source file: <span className="font-mono">{e.sourceFile}</span></p>}
          </div>
          {e.href && (
            <div className="px-4 py-3 border-t border-border-hairline">
              <Link href={e.href} onClick={closeInspector} className={buttonClass('secondary', 'md', 'w-full')}>{e.hrefLabel ?? 'Open full record'}</Link>
            </div>
          )}
        </div>
      )}
    </>
  );
}
