'use client';

import { useState } from 'react';
import { Modal } from '@/components/ui';
import { kindLabel, type DocumentInfo, type Run } from '@/lib/cmo-api';
import { plural } from './shared';
import { FilePreview, Thumbnail } from './SourceContext';

const FIRST = 8;

/** Every file that was read, with a look at its contents: a filename alone rarely says what a file is. */
export function DeliveryFiles({ run }: { run: Run }) {
  const documents = run.documents ?? [];
  const [all, setAll] = useState(false);
  const [open, setOpen] = useState<DocumentInfo | null>(null);
  if (!documents.length) return null;
  const shown = all ? documents : documents.slice(0, FIRST);
  return (
    <section className="rounded-2xl border border-border-hairline bg-white" data-testid="delivery-files">
      <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-border-hairline px-6 py-4">
        <h2 className="font-display text-[20px] font-light text-ink">Files <span className="text-text-tertiary">· {documents.length}</span></h2>
        <p className="text-xs text-text-tertiary">Click a file to look inside it.</p>
      </div>
      <ul className="grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-4">
        {shown.map(d => {
          const c = run.coverage?.by_document[d.path];
          const name = d.path.split('/').pop() ?? d.path;
          return <li key={d.source_id}>
            <button type="button" onClick={() => setOpen(d)} className="block w-full rounded-card p-1.5 text-left hover:bg-surface-secondary focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-teal">
              <Thumbnail runId={run.id} sourceId={d.source_id} path={d.path} />
              <p className="mt-1.5 truncate text-[12.5px] font-medium text-ink" title={d.path}>{name}</p>
              <p className="truncate text-[11px] text-text-tertiary">{kindLabel(d.doc_type)}{c ? ` · ${plural(c.measurement, 'value')}${c.flagged ? ` · ${c.flagged} to check` : ''}` : ''}</p>
            </button>
          </li>;
        })}
      </ul>
      {documents.length > shown.length && <button type="button" onClick={() => setAll(true)} className="mx-6 mb-4 text-[12.5px] text-brand-teal hover:underline">Show all {documents.length} files</button>}
      {open && <Modal open onClose={() => setOpen(null)} title={<span className="font-mono text-[13px]">{open.path}</span>} width="max-w-4xl">
        <p className="mb-2 text-xs text-text-tertiary">Read as {kindLabel(open.doc_type).toLowerCase()}. Shown from the stored original, which matches the hash recorded when it was delivered.</p>
        <FilePreview runId={run.id} sourceId={open.source_id} path={open.path} />
      </Modal>}
    </section>
  );
}
