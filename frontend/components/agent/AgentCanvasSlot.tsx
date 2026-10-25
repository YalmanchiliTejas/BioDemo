'use client';

import { Bot } from 'lucide-react';
import { templateOf, useAgent } from '@/lib/agent/agent-context';
import { Card, CardHeader, Pill } from '../ui';
import { InlineArtifactCard } from './InlineArtifactCard';
import { ReviewRequiredGate } from './ReviewRequiredGate';

/** Agent drafts the user explicitly inserted into this screen's canvas. Renders nothing otherwise. */
export function AgentCanvasSlot({ frame, className }: { frame: string; className?: string }) {
  const { tasks } = useAgent();
  const items = tasks.flatMap((task) => templateOf(task).artifacts.filter((a) => task.artifacts[a.id]?.insertedInto.includes(frame)).map((a) => ({ task, a })));
  if (items.length === 0) return null;
  return (
    <div className={className ?? 'space-y-3'}>
      {items.map(({ task, a }) => <InlineArtifactCard key={task.uid + a.id} task={task} artifactId={a.id} variant="canvas" currentFrame={frame} />)}
    </div>
  );
}

/** REV-01: agent proposals routed for a named human decision. */
export function AgentReviewQueue() {
  const { tasks } = useAgent();
  const routed = tasks.filter((t) => t.review.routedAt && templateOf(t).review);
  if (routed.length === 0) return null;
  return (
    <Card className="mb-4">
      <CardHeader
        icon={<Bot className="h-4 w-4" />}
        title="Agent proposals awaiting decision"
        subtitle="Routed from agent tasks in this session. Signatures are simulated and stored in this browser only."
        actions={<Pill tone="warning" dot>{routed.filter((t) => t.state === 'PROPOSAL_NEEDS_REVIEW').length} pending</Pill>}
      />
      <div className="p-4 space-y-4">
        {routed.map((t) => <ReviewRequiredGate key={t.uid} task={t} variant="review" />)}
      </div>
    </Card>
  );
}

/** WORK-01: artifacts pinned from agent tasks. */
export function AgentPinnedArtifacts() {
  const { tasks } = useAgent();
  const items = tasks.flatMap((task) => templateOf(task).artifacts.filter((a) => task.artifacts[a.id]?.pinned).map((a) => ({ task, a })));
  if (items.length === 0) return null;
  return (
    <Card className="mb-4">
      <CardHeader icon={<Bot className="h-4 w-4" />} title="Pinned from agent tasks" subtitle="Drafts stay labelled as unreviewed until they pass review." />
      <div className="p-4 grid grid-cols-1 xl:grid-cols-2 gap-3">
        {items.map(({ task, a }) => <InlineArtifactCard key={task.uid + a.id} task={task} artifactId={a.id} variant="canvas" currentFrame="WORK-01" />)}
      </div>
    </Card>
  );
}
