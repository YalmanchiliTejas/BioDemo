'use client';

import { useState } from 'react';
import { Check, Copy, ExternalLink, FileSearch, X } from 'lucide-react';
import type { SourceSystem } from '@/fixtures/biomanufacturingData';
import { Hash, Pill, SectionLabel } from './ui';
import { cn } from '@/lib/cn';

export interface EvidenceDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  citation: {
    sourceSystem: SourceSystem;
    documentName: string;
    sectionOrClause: string;
    rawExcerpt: string;
    sha256Hash: string;
    timestamp: string;
    provenanceConfidence: number;
    deepLinkUrl?: string;
    transformation?: string;
  };
  /** Render as an in-flow panel (inspector) instead of a fixed overlay. */
  inline?: boolean;
}

export function EvidenceDrawer({ isOpen, onClose, citation, inline }: EvidenceDrawerProps) {
  const [copied, setCopied] = useState(false);
  if (!isOpen) return null;

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(citation.sha256Hash);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable */
    }
  };

  const body = (
    <div className="flex flex-col h-full">
      <div className="flex items-start justify-between gap-2 px-4 py-3 border-b border-border-hairline">
        <div className="min-w-0">
          <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-text-tertiary">
            <FileSearch className="h-3.5 w-3.5" aria-hidden /> Source evidence
          </p>
          <h2 className="mt-1 text-sm font-semibold text-text-primary leading-snug">{citation.documentName}</h2>
          <p className="text-xs text-text-secondary">{citation.sectionOrClause}</p>
        </div>
        <button onClick={onClose} className="p-1 rounded text-text-tertiary hover:bg-surface-secondary" aria-label="Close evidence">
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-5">
        <div className="flex flex-wrap gap-1.5">
          <Pill tone="info">{citation.sourceSystem}</Pill>
          <Pill tone="muted">System of record · read-only</Pill>
        </div>

        <div>
          <SectionLabel>Raw excerpt</SectionLabel>
          <pre className="mt-2 whitespace-pre-wrap break-words text-[11.5px] leading-relaxed font-mono text-text-primary bg-surface-secondary border border-border-hairline rounded-control p-3">
            {citation.rawExcerpt}
          </pre>
          <p className="mt-1.5 text-[11px] text-text-tertiary">Shown exactly as retrieved. No summarization applied.</p>
        </div>

        {citation.transformation && (
          <div>
            <SectionLabel>Transformation applied</SectionLabel>
            <p className="mt-1.5 text-[12.5px] text-text-secondary">{citation.transformation}</p>
          </div>
        )}

        <div>
          <SectionLabel>Provenance</SectionLabel>
          <dl className="mt-2 space-y-2 text-[12.5px]">
            <Row k="Record timestamp" v={citation.timestamp} />
            <Row k="Retrieved by" v="Data Intake agent · RUN-2026-1042 · connector v2.3.1" />
            <Row
              k="Excerpt match"
              v={<span>{citation.provenanceConfidence.toFixed(1)}% <span className="text-text-tertiary">string match to source</span></span>}
            />
          </dl>
          <p className="mt-2 text-[11px] text-text-tertiary">
            The match score compares this excerpt with the stored source text. It is not a probability that any conclusion is correct.
          </p>
        </div>

        <div>
          <SectionLabel>Content hash</SectionLabel>
          <div className="mt-2 flex items-start gap-2 rounded-control border border-border-hairline bg-surface p-2.5">
            <Hash value={citation.sha256Hash} full className="break-all leading-relaxed" />
            <button onClick={copy} className="shrink-0 p-1 rounded text-text-tertiary hover:bg-surface-secondary" aria-label="Copy hash">
              {copied ? <Check className="h-3.5 w-3.5 text-status-success" /> : <Copy className="h-3.5 w-3.5" />}
            </button>
          </div>
          <p className="mt-1.5 text-[11px] text-text-tertiary">Synthetic demo hash. In production this identifies the exact source bytes that were read.</p>
        </div>
      </div>

      <div className="px-4 py-3 border-t border-border-hairline">
        <button
          disabled={!citation.deepLinkUrl}
          title={citation.deepLinkUrl ? undefined : 'Deep links open the system of record when a live connector is configured. Not available in the demo.'}
          className="w-full inline-flex items-center justify-center gap-1.5 h-8 rounded-control border border-border-strong text-[13px] font-medium text-text-primary hover:bg-surface-secondary disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <ExternalLink className="h-3.5 w-3.5" /> Open in {citation.sourceSystem}
        </button>
      </div>
    </div>
  );

  if (inline) return body;
  return (
    <div className="fixed inset-0 z-[70] flex justify-end">
      <div className="absolute inset-0 bg-slate-900/30" onClick={onClose} aria-hidden />
      <aside className={cn('relative w-full max-w-[380px] h-full bg-surface border-l border-border-hairline shadow-xl')} role="dialog" aria-label="Source evidence">
        {body}
      </aside>
    </div>
  );
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-text-tertiary shrink-0">{k}</dt>
      <dd className="text-text-primary text-right">{v}</dd>
    </div>
  );
}
