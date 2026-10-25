'use client';

import { useState } from 'react';
import Link from 'next/link';
import { ArrowRight, Brain, Check, ChevronDown, ChevronRight, CornerDownRight, GitCompareArrows, Pencil, RotateCcw, ShieldAlert, Square, Trash2, X } from 'lucide-react';
import { Button, Callout, Card, CardBody, CardHeader, ClaimTag, EvidenceChip, KeyValue, LinkButton, Modal, PageHeader, Pill, SectionLabel, Stat, StatusDot, useDisclosure } from '@/components/ui';
import { CASE_MEMORY, TRACE_STEPS, type MemoryFact, type TraceStep } from '@/components/screens/d/runTrace';
import { useAppContext } from '@/lib/app-context';

type ExecStatus = 'AWAITING_HUMAN_AUTHORIZATION' | 'STOPPED';

export default function RunTracePage() {
  const { openInspector, startRun, stopRun, agentRunningState, notify } = useAppContext();
  const [status, setStatus] = useState<ExecStatus>('AWAITING_HUMAN_AUTHORIZATION');
  const [openLogs, setOpenLogs] = useState<number[]>([]);
  const [memory, setMemory] = useState<MemoryFact[]>(CASE_MEMORY);
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState('');
  const [instructions, setInstructions] = useState<string[]>([]);
  const [instr, setInstr] = useState('');
  const redirect = useDisclosure();
  const stopConfirm = useDisclosure();

  const retrying = agentRunningState.isRunning && agentRunningState.runId === 'RUN-2026-1043';
  const runId = 'RUN-2026-1042';
  const stepsCompleted = TRACE_STEPS.length;
  const telemetryPoints = 24190;

  const inspectStep = (s: TraceStep) =>
    openInspector({
      type: 'AGENT_STEP',
      id: `${runId} · step ${s.n}`,
      title: s.title,
      citations: s.citations,
      metadata: { Tool: s.tool, Duration: s.duration, Inputs: s.inputs.length, Outputs: s.outputs.length, Status: 'Completed' },
    });

  const doStop = () => {
    stopRun();
    setStatus('STOPPED');
    stopConfirm.onClose();
    notify(`${runId} stopped. The proposal is withdrawn from the review queue; this trace is kept for audit.`, 'warning');
  };

  const doRetry = () => {
    startRun(`Retrying ${runId} as RUN-2026-1043${instructions.length ? ' with redirect instructions' : ''}`, 5);
    notify(`Retry started as RUN-2026-1043. This trace stays unchanged; results appear as a new run.`, 'info');
  };

  const submitRedirect = () => {
    if (!instr.trim()) return;
    setInstructions((l) => [...l, instr.trim()]);
    setInstr('');
    redirect.onClose();
    notify('Instruction recorded. It applies on the next retry; this completed trace is not altered.', 'info');
  };

  const statusPill = retrying
    ? <Pill tone="info" dot>Retry in progress (RUN-2026-1043)</Pill>
    : status === 'STOPPED'
      ? <Pill tone="muted" dot>Stopped by you</Pill>
      : <Pill tone="warning" dot>Awaiting human authorization</Pill>;

  return (
    <div className="max-w-[1280px] mx-auto">
      <PageHeader
        frameId="AGENT-02"
        crumbs={[{ label: 'Platform' }, { label: 'Agents', href: '/agents' }, { label: 'Runs' }, { label: runId }]}
        title="MSAT yield investigation run"
        objectId={runId}
        status={statusPill}
        description="Deterministic trace of what the MSAT Yield Sentry read, computed and proposed for INV-104. Click a step to inspect it; expand the raw log to see exact tool calls."
        meta={<><span>Agent: MSAT Yield Sentry · policy v4</span><span>Owner: Alex Rivera</span><span>Triggered by ALM-UP-204 · 2026-10-19 08:26 UTC</span><span>Read-only · writeback LOCKED</span></>}
        actions={
          <>
            <Button onClick={redirect.onOpen}><CornerDownRight className="h-3.5 w-3.5" /> Redirect</Button>
            <Button onClick={doRetry} disabled={agentRunningState.isRunning}><RotateCcw className="h-3.5 w-3.5" /> Retry run</Button>
            <Button variant="danger" onClick={retrying ? () => { stopRun(); notify('Retry RUN-2026-1043 stopped. Partial results discarded.', 'warning'); } : stopConfirm.onOpen} disabled={!retrying && status === 'STOPPED'}>
              <Square className="h-3.5 w-3.5" /> {retrying ? 'Stop retry' : 'Stop run'}
            </Button>
          </>
        }
      />

      {status === 'AWAITING_HUMAN_AUTHORIZATION' ? (
        <Callout
          tone="warning"
          icon={<ShieldAlert className="h-4 w-4" />}
          title="Human gate: the agent has stopped and cannot proceed on its own"
          className="mb-4"
          action={<LinkButton href="/reviews/REV-01" variant="primary" size="sm">Review proposal in REV-01 <ArrowRight className="h-3 w-3" /></LinkButton>}
        >
          Proposal RCP-AB014-V4.patch.02 needs signatures from the MSAT Lead (Alex Rivera) and QA Reviewer (Priya Natarajan). Until both sign, nothing is applied to the recipe, equipment or batch record.
        </Callout>
      ) : (
        <Callout tone="neutral" title="Run stopped" className="mb-4" action={<Button size="sm" onClick={() => { setStatus('AWAITING_HUMAN_AUTHORIZATION'); notify('Proposal restored to the REV-01 queue.'); }}>Undo stop</Button>}>
          The proposal has been withdrawn from review. The trace below is retained unchanged for the audit trail.
        </Callout>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_340px] gap-4">
        <div className="min-w-0 space-y-4">
          <Card>
            <CardBody className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <Stat label="Steps completed" value={`${stepsCompleted}/5`} hint="Checkpoint after step 5" />
              <Stat label="Telemetry points" value={telemetryPoints.toLocaleString('en-US')} hint="42 imputed, excluded" kind="observation" />
              <Stat label="Total duration" value="6m 41s" hint="08:26:04–08:32:45 UTC" />
              <Stat label="Execution status" value={<span className="text-[12px] font-mono">{status}</span>} />
            </CardBody>
          </Card>

          {retrying && (
            <Callout tone="info" title={`Retry RUN-2026-1043 in progress · ${agentRunningState.resolvedSources ?? 0} of ${agentRunningState.totalSources ?? 5} steps`}>
              The retry re-reads all sources. Results will appear as a separate run and need review again.
            </Callout>
          )}

          <ol className="space-y-3">
            {TRACE_STEPS.map((s) => {
              const open = openLogs.includes(s.n);
              return (
                <li key={s.n}>
                  <Card>
                    <button type="button" onClick={() => inspectStep(s)} className="w-full text-left flex items-start gap-3 px-4 py-3 hover:bg-surface-secondary/60 rounded-t-card" aria-label={`Inspect step ${s.n}: ${s.title}`}>
                      <span className="mt-0.5 h-6 w-6 shrink-0 rounded-full bg-status-success-bg text-status-success border border-emerald-200 flex items-center justify-center text-[11px] font-semibold tabular-nums">{s.n}</span>
                      <span className="min-w-0 flex-1">
                        <span className="flex flex-wrap items-center gap-2">
                          <span className="text-[13.5px] font-semibold text-text-primary">{s.title}</span>
                          <Pill tone="success"><Check className="h-3 w-3" />Completed</Pill>
                          <span className="text-[11.5px] text-text-tertiary tabular-nums">{s.duration}</span>
                        </span>
                        <span className="mt-0.5 block text-[11.5px] font-mono text-text-tertiary truncate">{s.tool}</span>
                      </span>
                      <ChevronRight className="h-4 w-4 mt-1 text-text-muted shrink-0" aria-hidden />
                    </button>
                    <div className="grid grid-cols-1 md:grid-cols-[200px_minmax(0,1fr)] gap-x-4 gap-y-2 px-4 pb-3 border-t border-border-hairline pt-3">
                      <div>
                        <SectionLabel>Inputs</SectionLabel>
                        <ul className="mt-1 space-y-0.5 text-[12px] text-text-secondary">
                          {s.inputs.map((x) => <li key={x}>{x}</li>)}
                        </ul>
                      </div>
                      <div>
                        <SectionLabel>Outputs</SectionLabel>
                        <ul className="mt-1 space-y-1">
                          {s.outputs.map((o) => (
                            <li key={o.text} className="flex items-start gap-2 text-[12.5px] text-text-primary">
                              <ClaimTag kind={o.kind} className="mt-px shrink-0" />
                              <span>{o.text}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    </div>
                    <div className="flex flex-wrap items-center gap-1.5 px-4 py-2 border-t border-border-hairline bg-surface-secondary/40">
                      {s.citations.map((c) => <EvidenceChip key={c} id={c} />)}
                      <button
                        type="button"
                        onClick={() => setOpenLogs((l) => (open ? l.filter((x) => x !== s.n) : [...l, s.n]))}
                        aria-expanded={open}
                        className="ml-auto inline-flex items-center gap-1 text-[11.5px] font-medium text-text-secondary hover:text-text-primary"
                      >
                        {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />} Raw log
                      </button>
                    </div>
                    {open && (
                      <pre className="mx-4 mb-3 mt-1 whitespace-pre-wrap break-words text-[11px] leading-relaxed font-mono text-slate-100 bg-slate-900 rounded-control p-3">{s.log}</pre>
                    )}
                  </Card>
                </li>
              );
            })}
          </ol>

          <div className="flex flex-wrap items-center justify-end gap-2">
            <LinkButton href="/investigations/INV-104"><GitCompareArrows className="h-3.5 w-3.5" /> Open linked investigation</LinkButton>
            <LinkButton href="/reviews/REV-01" variant="primary">Review proposal in REV-01 <ArrowRight className="h-3.5 w-3.5" /></LinkButton>
          </div>
        </div>

        <aside className="space-y-4 min-w-0 xl:sticky xl:top-0 self-start">
          <Card>
            <CardHeader icon={<Brain className="h-4 w-4" />} title="Case memory · INV-104" subtitle="Facts this agent will reuse on later runs. Correct or forget anything wrong." />
            <ul className="divide-y divide-border-hairline">
              {memory.map((m) => (
                <li key={m.id} className="px-4 py-2.5">
                  {editing === m.id ? (
                    <div className="space-y-1.5">
                      <label className="sr-only" htmlFor={`mem-${m.id}`}>Correct fact</label>
                      <textarea id={`mem-${m.id}`} value={draft} onChange={(e) => setDraft(e.target.value)} rows={3} className="w-full rounded-control border border-border-strong p-2 text-[12.5px] focus:outline-none focus:ring-2 focus:ring-brand-teal" />
                      <div className="flex gap-1.5 justify-end">
                        <Button size="sm" variant="ghost" onClick={() => setEditing(null)}><X className="h-3 w-3" /> Cancel</Button>
                        <Button size="sm" variant="primary" onClick={() => {
                          setMemory((l) => l.map((x) => (x.id === m.id ? { ...x, text: draft.trim() || x.text, corrected: true, confirmedBy: 'Alex Rivera · now' } : x)));
                          setEditing(null);
                          notify('Memory corrected. The change is logged; earlier traces keep the original value.');
                        }}>Save correction</Button>
                      </div>
                    </div>
                  ) : (
                    <>
                      <p className="text-[12.5px] text-text-primary leading-snug">{m.text}</p>
                      <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-text-tertiary">
                        <EvidenceChip id={m.source} />
                        {m.confirmedBy ? (
                          <span className="flex items-center gap-1"><StatusDot tone="success" />{m.corrected ? 'Corrected' : 'Confirmed'} by {m.confirmedBy}</span>
                        ) : (
                          <span className="flex items-center gap-1"><StatusDot tone="warning" />Agent-inferred · unconfirmed</span>
                        )}
                      </div>
                      <div className="mt-1.5 flex gap-1">
                        {!m.confirmedBy && (
                          <Button size="sm" variant="subtle" onClick={() => { setMemory((l) => l.map((x) => (x.id === m.id ? { ...x, confirmedBy: 'Alex Rivera · now' } : x))); notify('Fact confirmed and attributed to you.'); }}>Confirm</Button>
                        )}
                        <Button size="sm" variant="ghost" onClick={() => { setEditing(m.id); setDraft(m.text); }}><Pencil className="h-3 w-3" /> Correct</Button>
                        <Button size="sm" variant="ghost" onClick={() => { setMemory((l) => l.filter((x) => x.id !== m.id)); notify('Fact forgotten for INV-104. Removal is recorded in the audit log.', 'info'); }}><Trash2 className="h-3 w-3" /> Forget</Button>
                      </div>
                    </>
                  )}
                </li>
              ))}
              {memory.length === 0 && <li className="px-4 py-3 text-[12px] text-text-tertiary">No remembered facts. The next run will start from sources only.</li>}
            </ul>
          </Card>

          <Card>
            <CardHeader title="Redirect instructions" subtitle="Applied on the next retry only" actions={<Button size="sm" onClick={redirect.onOpen}>Add</Button>} />
            <div className="px-4 py-3">
              {instructions.length === 0 ? (
                <p className="text-[12px] text-text-tertiary">None yet. Use Redirect to steer the next run, e.g. “also check PM-201 history”.</p>
              ) : (
                <ul className="space-y-1.5">
                  {instructions.map((t, i) => (
                    <li key={i} className="text-[12.5px] text-text-primary flex gap-2"><CornerDownRight className="h-3.5 w-3.5 mt-0.5 text-text-muted shrink-0" />{t}<Pill tone="muted" className="ml-auto shrink-0">Queued</Pill></li>
                  ))}
                </ul>
              )}
            </div>
          </Card>

          <Card>
            <CardHeader title="Run context" />
            <CardBody>
              <KeyValue cols={1} items={[
                ['Linked investigation', <Link key="i" href="/investigations/INV-104" className="text-brand-teal hover:underline font-mono">INV-104</Link>],
                ['Proposal', <span key="p" className="font-mono">RCP-AB014-V4.patch.02</span>],
                ['Required approvers', 'MSAT Lead + QA Reviewer'],
                ['Data scope', 'PI, DeltaV eBR, LabWare, Maximo (read-only)'],
                ['Not available', 'SAP ERP (not connected)'],
              ]} />
            </CardBody>
          </Card>
        </aside>
      </div>

      <Modal
        open={redirect.open}
        onClose={redirect.onClose}
        title={`Redirect ${runId}`}
        footer={<><Button onClick={redirect.onClose}>Cancel</Button><Button variant="primary" onClick={submitRedirect} disabled={!instr.trim()}>Add instruction</Button></>}
      >
        <div className="space-y-2 text-[13px] text-text-secondary">
          <p>Tell the agent what to do differently. The instruction is recorded with your name and applied when you retry; it does not change this completed trace or widen the agent’s data permissions.</p>
          <label htmlFor="redirect-instr" className="block text-[12px] font-medium text-text-primary">Instruction</label>
          <textarea id="redirect-instr" value={instr} onChange={(e) => setInstr(e.target.value)} rows={4} placeholder="e.g. Also evaluate PM-201 maintenance history and exclude MES-26071 as a reference batch." className="w-full rounded-control border border-border-strong p-2 text-[13px] focus:outline-none focus:ring-2 focus:ring-brand-teal" />
        </div>
      </Modal>

      <Modal
        open={stopConfirm.open}
        onClose={stopConfirm.onClose}
        title={`Stop ${runId}?`}
        footer={<><Button onClick={stopConfirm.onClose}>Keep run</Button><Button variant="danger" onClick={doStop}>Stop run</Button></>}
      >
        <p className="text-[13px] text-text-secondary">Stopping withdraws proposal RCP-AB014-V4.patch.02 from the REV-01 queue. The trace and evidence remain available for audit, and you can retry later.</p>
      </Modal>
    </div>
  );
}
