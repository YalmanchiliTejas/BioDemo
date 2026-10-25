'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { ArrowRight, Bot, Cpu, Lock, Pause, Play, Rocket, ShieldCheck } from 'lucide-react';
import { Button, Card, CardBody, CardHeader, LinkButton, Modal, PageHeader, Pill, Segmented, SectionLabel, Stat, StatusDot, table, useDisclosure, type Tone } from '@/components/ui';
import { EventStream } from '@/components/screens/d/EventStream';
import { AGENT_ROLES, LEDGER, type AgentRole, type AgentStatus } from '@/components/screens/d/agents';
import { useAppContext } from '@/lib/app-context';
import { cn } from '@/lib/cn';

const STATUS_META: Record<AgentStatus, { label: string; tone: Tone }> = {
  idle: { label: 'Idle', tone: 'neutral' },
  running: { label: 'Running', tone: 'info' },
  awaiting_review: { label: 'Awaiting review', tone: 'warning' },
  paused: { label: 'Paused', tone: 'muted' },
};

type FilterKey = 'all' | AgentStatus;

export default function AgentsPage() {
  const router = useRouter();
  const { notify } = useAppContext();
  const [agents, setAgents] = useState<AgentRole[]>(AGENT_ROLES);
  const [prev, setPrev] = useState<Record<string, AgentStatus>>({});
  const [filter, setFilter] = useState<FilterKey>('all');
  const deploy = useDisclosure();

  const inFlightTasks = agents.filter((a) => a.status === 'running').length;
  const awaitingReviewCount = agents.reduce((s, a) => s + (a.status === 'awaiting_review' ? a.reviewCount ?? 0 : 0), 0);
  const dcsWritebackMode = 'LOCKED_READ_ONLY';

  const togglePause = (a: AgentRole) => {
    if (a.status === 'paused') {
      const back = prev[a.id] ?? 'idle';
      setAgents((list) => list.map((x) => (x.id === a.id ? { ...x, status: back } : x)));
      notify(`${a.name} resumed. It will act on its next trigger within its read-only scope.`);
    } else {
      setPrev((p) => ({ ...p, [a.id]: a.status }));
      setAgents((list) => list.map((x) => (x.id === a.id ? { ...x, status: 'paused' } : x)));
      notify(
        a.status === 'running'
          ? `${a.name} pausing at its next checkpoint. Partial results are kept and marked incomplete.`
          : `${a.name} paused. Triggers will be queued, not acted on.`,
        'info',
      );
    }
  };

  const shown = agents.filter((a) => filter === 'all' || a.status === filter);

  return (
    <div className="max-w-[1280px] mx-auto">
      <PageHeader
        frameId="AGENT-01"
        crumbs={[{ label: 'Platform' }, { label: 'Agents' }]}
        title="Background agents"
        status={<Pill tone="success" dot>Writeback locked · read-only</Pill>}
        description="Agents run in the background within explicit permissions. They read from systems of record and produce drafts or proposals; nothing they produce takes effect without a named person’s signature."
        meta={<><span>Mesa Site (UP-01)</span><span>Agent policy v4 · approved by P. Natarajan 2026-09-30</span></>}
        actions={
          <>
            <LinkButton href="/runs/RUN-2026-1042"><Cpu className="h-3.5 w-3.5" /> Inspect run RUN-2026-1042</LinkButton>
            <Button variant="primary" onClick={deploy.onOpen}><Rocket className="h-3.5 w-3.5" /> Deploy agent workflow</Button>
          </>
        }
      />

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4 mb-4">
        <Card className="xl:col-span-2">
          <CardBody className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <Stat label="Configured roles" value={agents.length} hint={`${agents.filter((a) => a.status !== 'paused').length} active · ${agents.filter((a) => a.status === 'paused').length} paused`} />
            <Stat label="In-flight tasks" value={inFlightTasks} hint="Running now" />
            <Stat label="Awaiting review" value={awaitingReviewCount} hint="Drafts and proposals" />
            <Stat label="DCS writeback" value={<span className="text-[13px] font-mono">{dcsWritebackMode}</span>} hint="Not configurable in UI" />
          </CardBody>
        </Card>
        <Card className="border-emerald-200">
          <CardHeader icon={<ShieldCheck className="h-4 w-4 text-status-success" />} title="Platform safety boundary" actions={<Lock className="h-3.5 w-3.5 text-text-tertiary" aria-label="Locked" />} />
          <ul className="px-4 py-3 space-y-1.5 text-[12.5px] text-text-secondary">
            <li>All connectors use read-only service accounts; no write paths to MES, DCS/PLC, LIMS, QMS or ERP.</li>
            <li>Agent outputs are drafts or proposals, stored separately from source records.</li>
            <li>Every proposal names its required human approvers; approval is recorded with e-signature meaning.</li>
            <li>Each run logs tool versions, inputs and outputs to the audit trail. <Link href="/settings/governance" className="text-brand-teal hover:underline">Governance settings</Link></li>
          </ul>
        </Card>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <div className="xl:col-span-2 min-w-0 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <SectionLabel>Agent roles</SectionLabel>
            <Segmented<FilterKey>
              value={filter}
              onChange={setFilter}
              options={[
                { value: 'all', label: `All ${agents.length}` },
                { value: 'running', label: 'Running' },
                { value: 'awaiting_review', label: 'Awaiting review' },
                { value: 'idle', label: 'Idle' },
                { value: 'paused', label: 'Paused' },
              ]}
            />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {shown.map((a) => {
              const m = STATUS_META[a.status];
              return (
                <Card key={a.id} className={cn('flex flex-col', a.status === 'awaiting_review' && 'border-amber-200')}>
                  <div className="px-4 pt-3 pb-2 flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="flex items-center gap-1.5 text-[13.5px] font-semibold text-text-primary"><Bot className="h-3.5 w-3.5 text-text-tertiary" aria-hidden />{a.name}</p>
                      <p className="mt-0.5 text-[12px] text-text-secondary leading-snug">{a.purpose}</p>
                    </div>
                    <Pill tone={m.tone} className="shrink-0"><StatusDot tone={m.tone} pulse={a.status === 'running'} />{m.label}{a.status === 'awaiting_review' && a.reviewCount ? ` · ${a.reviewCount}` : ''}</Pill>
                  </div>
                  <dl className="px-4 pb-3 grid grid-cols-[76px_minmax(0,1fr)] gap-x-2 gap-y-1 text-[11.5px]">
                    <dt className="text-text-tertiary">Trigger</dt><dd className="text-text-primary">{a.trigger}</dd>
                    <dt className="text-text-tertiary">Reads</dt>
                    <dd className="flex flex-wrap gap-1">{a.scope.map((s) => <span key={s} className="px-1.5 rounded border border-border-hairline bg-surface-secondary text-text-secondary">{s}</span>)}<span className="text-text-muted">read-only</span></dd>
                    <dt className="text-text-tertiary">May produce</dt><dd className="text-text-primary">{a.produces}</dd>
                    <dt className="text-text-tertiary">Human gate</dt><dd className="text-text-primary">{a.gate}</dd>
                    <dt className="text-text-tertiary">Owner</dt><dd className="text-text-primary">{a.owner}</dd>
                  </dl>
                  <div className="mt-auto flex items-center gap-2 px-4 py-2 border-t border-border-hairline bg-surface-secondary/40">
                    <p className="flex-1 min-w-0 truncate text-[11.5px] text-text-tertiary" title={a.detail}>{a.detail}</p>
                    {a.href && <LinkButton size="sm" variant="ghost" href={a.href}>Open</LinkButton>}
                    <Button size="sm" onClick={() => togglePause(a)} aria-label={`${a.status === 'paused' ? 'Resume' : 'Pause'} ${a.name}`}>
                      {a.status === 'paused' ? <><Play className="h-3 w-3" /> Resume</> : <><Pause className="h-3 w-3" /> Pause</>}
                    </Button>
                  </div>
                </Card>
              );
            })}
            {shown.length === 0 && <p className="text-[12.5px] text-text-tertiary">No agents in this state.</p>}
          </div>
        </div>

        <div className="space-y-4 min-w-0">
          <EventStream />
          <Card>
            <CardHeader title="What agents cannot do" />
            <ul className="px-4 py-3 space-y-1.5 text-[12.5px] text-text-secondary list-disc pl-8">
              <li>Change setpoints, recipes or equipment states.</li>
              <li>File, approve or close records in QMS or LIMS.</li>
              <li>Read data outside the requesting user’s permissions.</li>
              <li>Mark their own proposals as approved or effective.</li>
            </ul>
          </Card>
        </div>
      </div>

      <Card className="mt-4">
        <CardHeader title="Execution ledger" subtitle="Recent runs across all agents · every row links to its audit trail entry" />
        <div className={table.wrap}>
          <table className={table.root}>
            <thead>
              <tr>
                {['Run', 'Agent', 'Trigger', 'Duration', 'Data scope (read)', 'Outcome', 'Reviewer'].map((h) => <th key={h} className={table.th}>{h}</th>)}
              </tr>
            </thead>
            <tbody>
              {LEDGER.map((r) => (
                <tr key={r.run} className={table.tr}>
                  <td className={table.td}>{r.href ? <Link href={r.href} className="font-mono text-brand-teal hover:underline">{r.run}</Link> : <span className="font-mono">{r.run}</span>}</td>
                  <td className={table.td}>{r.agent}</td>
                  <td className={cn(table.td, 'text-text-secondary')}>{r.trigger}</td>
                  <td className={cn(table.td, 'tabular-nums')}>{r.duration}</td>
                  <td className={cn(table.td, 'text-text-secondary')}>{r.scope}</td>
                  <td className={table.td}><Pill tone={r.tone}>{r.outcome}</Pill></td>
                  <td className={cn(table.td, 'text-text-secondary')}>{r.reviewer}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Modal
        open={deploy.open}
        onClose={deploy.onClose}
        title="Deploy an agent workflow"
        footer={
          <>
            <Button onClick={deploy.onClose}>Cancel</Button>
            <Button variant="primary" onClick={() => { deploy.onClose(); router.push('/workspaces'); }}>Continue in Workspaces <ArrowRight className="h-3.5 w-3.5" /></Button>
          </>
        }
      >
        <div className="space-y-3 text-[13px] text-text-secondary">
          <p>Agent workflows are attached to an objective workspace so they inherit its data scope and reviewers. You will:</p>
          <ol className="list-decimal pl-5 space-y-1.5">
            <li><span className="text-text-primary font-medium">Pick a workspace and objective</span> — e.g. “UP-01 yield consistency”.</li>
            <li><span className="text-text-primary font-medium">Choose an agent role and trigger</span> — scope is limited to the workspace’s read-only connectors.</li>
            <li><span className="text-text-primary font-medium">Name the human gate</span> — who must review outputs before anyone acts on them.</li>
          </ol>
          <p className="text-[12px] text-text-tertiary">New workflows start paused until the workspace owner enables them. DCS writeback stays locked regardless of configuration.</p>
        </div>
      </Modal>
    </div>
  );
}
