'use client';

import { useRef, useState, type DragEvent } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { ArrowRight, Check, FileUp, Lock, PlayCircle, PlugZap, X } from 'lucide-react';
import { Button, Callout, LinkButton, Modal, Pill, SectionLabel, useDisclosure } from '@/components/ui';
import { cn } from '@/lib/cn';
import { GOAL_STORAGE_KEY, writeSession } from '@/components/screens/a/onboarding';

type IngestMode = 'FILE' | 'CONNECTOR' | 'DEMO';
const ACCEPTED_FILE_TYPES = ['.csv', '.xlsx', '.pdf', '.parquet'];
const SYSTEMS = [
  { name: 'Emerson DeltaV', kind: 'MES / eBR' },
  { name: 'OSIsoft PI', kind: 'Historian' },
  { name: 'LabWare', kind: 'LIMS' },
  { name: 'Veeva Vault', kind: 'QMS' },
  { name: 'IBM Maximo', kind: 'CMMS' },
];
const GOAL_EXAMPLES = ['Why is UP-01 yield declining?', 'Summarize what happened on MES-26073', 'Is BR-UP-01 ready for the next batch?'];

type PickedFile = { name: string; size: number; ok: boolean };

function ext(name: string) {
  const i = name.lastIndexOf('.');
  return i >= 0 ? name.slice(i).toLowerCase() : '';
}

export default function OnboardingStartPage() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const connector = useDisclosure();
  const [mode, setMode] = useState<IngestMode | null>(null);
  const [goal, setGoal] = useState('');
  const [dragOver, setDragOver] = useState(false);
  const [files, setFiles] = useState<PickedFile[]>([]);

  const saveGoal = () => writeSession(GOAL_STORAGE_KEY, goal.trim() || null);

  const go = (href: string, m: IngestMode) => {
    setMode(m);
    saveGoal();
    router.push(href);
  };

  const accept = (list: FileList | null) => {
    if (!list || list.length === 0) return;
    const picked = Array.from(list).map((f) => ({ name: f.name, size: f.size, ok: ACCEPTED_FILE_TYPES.includes(ext(f.name)) || ext(f.name) === '.zip' }));
    setFiles(picked);
    setMode('FILE');
    if (picked.some((f) => f.ok)) {
      saveGoal();
      setTimeout(() => router.push('/onboarding/mapping'), 1400);
    }
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    accept(e.dataTransfer.files);
  };

  const okCount = files.filter((f) => f.ok).length;

  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wider text-text-tertiary">Step 1 of 3 · ONB-01</p>
          <h1 className="mt-1 text-xl font-semibold tracking-tight text-text-primary">Start from the data you already have</h1>
          <p className="mt-1 text-[13px] text-text-secondary max-w-2xl">Choose any starting point. Nothing needs to be reformatted first, and you can add more sources later without repeating this step.</p>
        </div>
        <Pill tone="muted" className="mt-1" title="The product reads from systems of record. It never writes to MES, DCS/PLC, LIMS, QMS or ERP.">
          <Lock className="h-3 w-3" aria-hidden /> Read-only architecture · no writeback
        </Pill>
      </div>

      <div className="mt-6 bg-surface border border-border-hairline rounded-card p-4">
        <label htmlFor="goal" className="text-[13px] font-semibold text-text-primary">What do you want to find out? <span className="font-normal text-text-tertiary">(optional)</span></label>
        <p className="text-[12px] text-text-tertiary mt-0.5">A question focuses the first result. Skip it and you’ll get a general data-health and trend summary.</p>
        <input
          id="goal"
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          placeholder="e.g. Why is UP-01 yield declining across the last three batches?"
          className="mt-2 w-full h-9 px-3 rounded-control border border-border-strong bg-surface text-[13px] placeholder:text-text-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-teal"
        />
        <div className="mt-2 flex flex-wrap gap-1.5">
          {GOAL_EXAMPLES.map((g) => (
            <button key={g} type="button" onClick={() => setGoal(g)} className="h-6 px-2 rounded-pill border border-border-hairline bg-surface-secondary text-[11.5px] text-text-secondary hover:text-text-primary hover:border-border-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-teal">
              {g}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-4 grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Upload */}
        <section aria-labelledby="card-file" className={cn('bg-surface border rounded-card flex flex-col', mode === 'FILE' ? 'border-brand-teal' : 'border-border-hairline')}>
          <div className="p-4 flex-1 flex flex-col">
            <div className="flex items-center gap-2">
              <span className="h-8 w-8 rounded-control bg-surface-secondary text-text-secondary flex items-center justify-center"><FileUp className="h-4 w-4" aria-hidden /></span>
              <h2 id="card-file" className="text-[14px] font-semibold text-text-primary">Upload files or ZIP</h2>
            </div>
            <p className="mt-2 text-[12.5px] text-text-secondary">Historian exports, eBR reports, LIMS results, SOP PDFs. Mixed formats are fine.</p>

            <div
              onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={onDrop}
              className={cn('mt-3 flex-1 min-h-[132px] rounded-card border-2 border-dashed flex flex-col items-center justify-center text-center px-3 py-4 transition-colors', dragOver ? 'border-brand-teal bg-brand-teal-light' : 'border-border-strong bg-surface-secondary/50')}
            >
              {files.length === 0 ? (
                <>
                  <p className="text-[12.5px] text-text-secondary">Drop files here, or</p>
                  <Button variant="secondary" size="sm" className="mt-2" onClick={() => inputRef.current?.click()}>Choose files</Button>
                  <p className="mt-2 text-[11px] text-text-tertiary font-mono">{ACCEPTED_FILE_TYPES.join(' ')} .zip</p>
                </>
              ) : (
                <div className="w-full text-left" aria-live="polite">
                  <ul className="space-y-1 max-h-28 overflow-y-auto">
                    {files.map((f) => (
                      <li key={f.name} className="flex items-center gap-1.5 text-[12px]">
                        {f.ok ? <Check className="h-3.5 w-3.5 text-status-success shrink-0" aria-hidden /> : <X className="h-3.5 w-3.5 text-status-critical shrink-0" aria-hidden />}
                        <span className="font-mono truncate">{f.name}</span>
                        <span className="ml-auto text-[11px] text-text-tertiary tabular-nums shrink-0">{f.ok ? `${Math.max(1, Math.round(f.size / 1024))} KB` : 'unsupported type'}</span>
                      </li>
                    ))}
                  </ul>
                  <p className="mt-2 text-[11.5px] text-text-secondary">
                    {okCount > 0 ? `${okCount} file${okCount > 1 ? 's' : ''} accepted · opening mapping…` : 'No supported files. Try .csv, .xlsx, .pdf, .parquet or .zip.'}
                  </p>
                  <p className="mt-1 text-[10.5px] text-text-muted">Demo: file contents are not parsed; the mapping step uses the sample campaign.</p>
                </div>
              )}
              <input
                ref={inputRef}
                type="file"
                multiple
                accept={[...ACCEPTED_FILE_TYPES, '.zip'].join(',')}
                className="sr-only"
                aria-label="Choose files to upload"
                onChange={(e) => accept(e.target.files)}
              />
            </div>
          </div>
          <div className="px-4 py-3 border-t border-border-hairline">
            <Button variant="secondary" className="w-full" onClick={() => go('/onboarding/mapping', 'FILE')}>Upload Files <ArrowRight className="h-3.5 w-3.5" aria-hidden /></Button>
          </div>
        </section>

        {/* Connector */}
        <section aria-labelledby="card-conn" className={cn('bg-surface border rounded-card flex flex-col', mode === 'CONNECTOR' ? 'border-brand-teal' : 'border-border-hairline')}>
          <div className="p-4 flex-1">
            <div className="flex items-center gap-2">
              <span className="h-8 w-8 rounded-control bg-surface-secondary text-text-secondary flex items-center justify-center"><PlugZap className="h-4 w-4" aria-hidden /></span>
              <h2 id="card-conn" className="text-[14px] font-semibold text-text-primary">Connect historian / LIMS API</h2>
            </div>
            <p className="mt-2 text-[12.5px] text-text-secondary">Pull records directly from systems of record with a read-only service account. No exports to maintain.</p>
            <SectionLabel className="mt-4">Supported systems</SectionLabel>
            <ul className="mt-2 divide-y divide-border-hairline border border-border-hairline rounded-control">
              {SYSTEMS.map((s) => (
                <li key={s.name} className="flex items-center justify-between px-2.5 py-1.5 text-[12.5px]">
                  <span className="text-text-primary">{s.name}</span>
                  <span className="text-[11px] text-text-tertiary">{s.kind}</span>
                </li>
              ))}
            </ul>
          </div>
          <div className="px-4 py-3 border-t border-border-hairline">
            <Button variant="secondary" className="w-full" onClick={() => { setMode('CONNECTOR'); connector.onOpen(); }}>Connect a system <ArrowRight className="h-3.5 w-3.5" aria-hidden /></Button>
          </div>
        </section>

        {/* Demo */}
        <section aria-labelledby="card-demo" className={cn('bg-surface border rounded-card flex flex-col', mode === 'DEMO' ? 'border-brand-teal' : 'border-border-hairline')}>
          <div className="p-4 flex-1">
            <div className="flex items-center gap-2">
              <span className="h-8 w-8 rounded-control bg-brand-teal-light text-brand-teal flex items-center justify-center"><PlayCircle className="h-4 w-4" aria-hidden /></span>
              <h2 id="card-demo" className="text-[14px] font-semibold text-text-primary">Explore demo sandbox</h2>
              <Pill tone="brand" className="ml-auto">Fastest</Pill>
            </div>
            <p className="mt-2 text-[12.5px] text-text-secondary">A pre-indexed synthetic campaign: three fed-batch runs of AB-mAb-014 on BR-UP-01, with a known historian gap and a yield decline to examine.</p>
            <dl className="mt-4 grid grid-cols-2 gap-2 text-[12px]">
              {[['Batches', '3'], ['Files', '8'], ['Records', '24,190'], ['Assays', '4']].map(([k, v]) => (
                <div key={k} className="rounded-control bg-surface-secondary px-2.5 py-1.5">
                  <dt className="text-[11px] text-text-tertiary">{k}</dt>
                  <dd className="font-semibold tabular-nums text-text-primary">{v}</dd>
                </div>
              ))}
            </dl>
            <p className="mt-3 text-[11px] text-text-tertiary">All values are synthetic. Mapping is already confirmed, so this skips straight to the first result.</p>
          </div>
          <div className="px-4 py-3 border-t border-border-hairline">
            <Button variant="primary" className="w-full" onClick={() => go('/onboarding/results', 'DEMO')}>Explore Demo Data <ArrowRight className="h-3.5 w-3.5" aria-hidden /></Button>
          </div>
        </section>
      </div>

      <p className="mt-6 text-[12px] text-text-tertiary">
        Already set up? <Link href="/home" className="text-brand-teal hover:underline">Go to the daily briefing</Link> or <Link href="/sources" className="text-brand-teal hover:underline">review connected sources</Link>.
      </p>

      <Modal
        open={connector.open}
        onClose={connector.onClose}
        title="Connect a system of record"
        footer={
          <>
            <LinkButton href="/sources" variant="secondary" onClick={saveGoal}>View connector gallery</LinkButton>
            <Button variant="primary" onClick={() => go('/onboarding/mapping', 'CONNECTOR')}>Continue with demo connectors <ArrowRight className="h-3.5 w-3.5" aria-hidden /></Button>
          </>
        }
      >
        <div className="space-y-3 text-[13px] text-text-secondary">
          <p>Each connector needs a <span className="font-medium text-text-primary">read-only service account</span> issued by your system owner. The product requests only the scopes listed below and cannot write, acknowledge alarms, or change recipes.</p>
          <ul className="space-y-1.5 text-[12.5px]">
            <li className="flex gap-2"><Check className="h-4 w-4 text-status-success shrink-0" aria-hidden />PI Web API: read tags and archive values for named assets</li>
            <li className="flex gap-2"><Check className="h-4 w-4 text-status-success shrink-0" aria-hidden />LIMS: read sample, test and result records (no review actions)</li>
            <li className="flex gap-2"><Check className="h-4 w-4 text-status-success shrink-0" aria-hidden />MES/eBR: read batch records and phase events</li>
          </ul>
          <Callout tone="warning" title="In this demo, connectors are simulated">
            No credentials are requested and no network connection is made. Continuing uses pre-loaded synthetic records that behave like connected sources.
          </Callout>
        </div>
      </Modal>
    </div>
  );
}
