'use client';

import { useEffect, useRef, useState } from 'react';
import { Pause, Play, Radio } from 'lucide-react';
import { Button, Card, CardHeader, Pill, StatusDot } from '@/components/ui';
import { STREAM_TEMPLATES } from './agents';

type Ev = { id: number; time: string; topic: string; text: string };

function seeded(i: number) {
  const x = Math.sin(i * 12.9898) * 43758.5453;
  return x - Math.floor(x);
}

/** Simulated event-stream pulse. No real transport is connected in the demo. */
export function EventStream() {
  const [running, setRunning] = useState(true);
  const [events, setEvents] = useState<Ev[]>([]);
  const [rates, setRates] = useState<number[]>(() => Array.from({ length: 36 }, (_, i) => 6 + Math.round(seeded(i + 1) * 9)));
  const n = useRef(0);

  useEffect(() => {
    if (!running) return;
    const tick = () => {
      const i = n.current++;
      const t = STREAM_TEMPLATES[i % STREAM_TEMPLATES.length];
      const digit = Math.floor(seeded(i + 7) * 10);
      const now = new Date();
      const time = now.toISOString().slice(11, 19) + 'Z';
      setEvents((e) => [{ id: i, time, topic: t.topic, text: t.text.replace('x', String(digit)) }, ...e].slice(0, 7));
      setRates((r) => [...r.slice(1), 5 + Math.round(seeded(i + 31) * 11) + (t.topic.startsWith('agent') ? 3 : 0)]);
    };
    tick();
    const h = setInterval(tick, 1800);
    return () => clearInterval(h);
  }, [running]);

  const max = Math.max(...rates, 1);
  const W = 300, H = 44;
  const bw = W / rates.length;

  return (
    <Card>
      <CardHeader
        icon={<Radio className="h-4 w-4" />}
        title="Event stream"
        subtitle="Kafka transport · topic mos.events.up01 · read-only consumers"
        actions={
          <>
            <Pill tone="muted">Simulated</Pill>
            <Button size="sm" variant="ghost" onClick={() => setRunning((r) => !r)} aria-label={running ? 'Pause stream view' : 'Resume stream view'}>
              {running ? <Pause className="h-3 w-3" /> : <Play className="h-3 w-3" />}
            </Button>
          </>
        }
      />
      <div className="px-4 pt-3">
        <div className="flex items-center justify-between text-[11px] text-text-tertiary">
          <span className="flex items-center gap-1.5"><StatusDot tone={running ? 'success' : 'muted'} pulse={running} />{running ? 'Live (simulated)' : 'View paused — events still arrive'}</span>
          <span className="tabular-nums">{rates[rates.length - 1]} events / tick</span>
        </div>
        <svg viewBox={`0 0 ${W} ${H}`} className="mt-1.5 w-full h-11" role="img" aria-label="Simulated event rate over the last 36 ticks">
          {rates.map((r, i) => {
            const h = (r / max) * (H - 4);
            return <rect key={i} x={i * bw + 1} y={H - h} width={bw - 2} height={h} rx="1" fill={i === rates.length - 1 ? '#0e7490' : '#cbd5e1'} />;
          })}
        </svg>
      </div>
      <ul className="px-4 py-2.5 space-y-1 font-mono text-[11px] min-h-[150px]" aria-live="off">
        {events.map((e, i) => (
          <li key={e.id} className={i === 0 ? 'text-text-primary' : 'text-text-tertiary'}>
            <span className="tabular-nums">{e.time}</span> <span className="text-brand-teal-dark">{e.topic}</span> {e.text}
          </li>
        ))}
      </ul>
    </Card>
  );
}
