'use client';

import { useMemo, useState } from 'react';
import { ArrowLeft, Ban, Check, PhoneCall, RotateCcw, X } from 'lucide-react';
import { Button, LinkButton, useDisclosure } from '@/components/ui';
import { CallEngineeringModal, SourceExcerpt } from '@/components/screens/d/operator';
import { ANOMALY_HOUR } from '@/fixtures/biomanufacturingData';
import { cn } from '@/lib/cn';

const STEPS = [
  { id: 's1', title: 'Tubing path', check: 'Tubing runs inlet → rollers → outlet, centered in the track, no twist. Look only.' },
  { id: 's2', title: 'Lumen clarity', check: 'Tubing is clear: no particles, collapse or flat spots where rollers contact.' },
  { id: 's3', title: 'Occlusion clamp position', check: 'Compare clamp position with the painted reference mark. Visual check — do not adjust.' },
  { id: 's4', title: 'Feed bag load cell', check: 'On the DeltaV HMI, confirm the feed bag weight is still decreasing. Read only.' },
];

type Result = 'ok' | 'notok' | null;
const sig = (x: number) => 1 / (1 + Math.exp(-x));

export default function OperatorTroubleshootingPage() {
  const [results, setResults] = useState<Record<string, Result>>({});
  const call = useDisclosure();
  const alarmId = 'ALM-UP-204';
  const tripTimestamp = 'Hour 264.4';
  const headPressureSpike = '1.48 bar';

  const answered = STEPS.filter((s) => results[s.id]).length;
  const anyNotOk = STEPS.some((s) => results[s.id] === 'notok');
  const allDone = answered === STEPS.length;

  return (
    <div className="h-full flex flex-col p-4 gap-3 text-[16px]">
      <div className="flex items-center gap-3 rounded-card border-2 border-red-300 bg-status-critical-bg px-4 py-2">
        <span className="h-3 w-3 rounded-full bg-red-600 animate-pulse" aria-hidden />
        <div className="min-w-0">
          <h1 className="text-[20px] font-bold text-red-800 leading-tight">Alarm <span className="font-mono">{alarmId}</span> · PM-204 head pressure high</h1>
          <p className="text-[14px] text-red-900">Tripped at {tripTimestamp} · peak {headPressureSpike} (ceiling 1.20 bar) · feed flow drooped to 14.48 mL/min</p>
        </div>
        <div className="ml-auto flex items-center gap-2 rounded-control bg-red-700 text-white px-3 py-2 text-[15px] font-semibold max-w-[330px]">
          <Ban className="h-5 w-5 shrink-0" aria-hidden />
          Do not adjust occlusion or setpoints — escalate
        </div>
      </div>

      <div className="flex-1 min-h-0 grid grid-cols-[minmax(0,1fr)_480px] gap-3">
        <div className="min-h-0 overflow-y-auto space-y-3 pr-1">
          <section aria-label="Telemetry snapshot" className="rounded-card border-2 border-border-strong bg-surface p-3">
            <div className="flex items-center justify-between">
              <h2 className="text-[17px] font-semibold text-text-primary">Incident snapshot · MES-26073</h2>
              <span className="text-[13px] text-text-tertiary">Hour 240–280 · synthetic</span>
            </div>
            <Waveform />
            <div className="mt-1 flex flex-wrap gap-4 text-[14px] text-text-secondary">
              <span className="flex items-center gap-1.5"><span className="h-1 w-5 rounded bg-red-600" />Head pressure (bar, left)</span>
              <span className="flex items-center gap-1.5"><span className="h-1 w-5 rounded bg-sky-600" />Feed flow (mL/min, right)</span>
              <span className="flex items-center gap-1.5"><span className="w-5 border-t-2 border-dashed border-slate-500" />Ceiling 1.20 bar</span>
            </div>
            <div className="mt-2"><SourceExcerpt id="historian-up01" label="Historian rows at trip (PI)" /></div>
          </section>

          <section aria-label="OEM tubing specification" className="rounded-card border-2 border-border-strong bg-surface p-3 space-y-2">
            <h2 className="text-[17px] font-semibold text-text-primary">Tubing service life (OEM)</h2>
            <p className="text-[15px] text-text-primary leading-snug">Masterflex size 24 platinum silicone: expected life <strong>400–500 h</strong>. This tubing set is at <strong>412 h</strong> — inside the wear window.</p>
            <TubingLife hours={412} />
            <SourceExcerpt id="oem-masterflex" label="OEM manual · Table 4" />
            <SourceExcerpt id="d-cmms-tubing-hours" label="Maximo run-hours meter · TS-24-0931" />
          </section>
        </div>

        <section aria-label="Non-invasive verification" className="rounded-card border-2 border-border-strong bg-surface flex flex-col min-h-0">
          <div className="flex items-center justify-between px-4 py-2.5 border-b border-border-hairline">
            <h2 className="text-[17px] font-semibold text-text-primary">Non-invasive checks</h2>
            <span className="flex items-center gap-3">
              <span className="text-[15px] font-semibold tabular-nums text-text-secondary">{answered}/4</span>
              {answered > 0 && <button type="button" onClick={() => setResults({})} className="min-h-[44px] min-w-[44px] flex items-center justify-center rounded-control text-text-secondary active:bg-surface-secondary" aria-label="Reset checks"><RotateCcw className="h-5 w-5" /></button>}
            </span>
          </div>
          <ol className="flex-1 min-h-0 overflow-y-auto divide-y divide-border-hairline">
            {STEPS.map((s, i) => {
              const r = results[s.id] ?? null;
              const set = (v: Result) => setResults((x) => ({ ...x, [s.id]: x[s.id] === v ? null : v }));
              return (
                <li key={s.id} className={cn('px-4 py-2', r === 'notok' && 'bg-status-critical-bg', r === 'ok' && 'bg-status-success-bg')}>
                  <div className="flex items-center gap-3">
                  <div className="min-w-0 flex-1">
                    <p className="text-[16px] font-semibold text-text-primary"><span className="tabular-nums text-text-tertiary mr-1.5">{i + 1}.</span>{s.title}</p>
                    <p className="text-[14px] text-text-secondary leading-snug">{s.check}</p>
                  </div>
                  <div className="shrink-0 grid grid-cols-2 gap-2 w-[188px]" role="radiogroup" aria-label={`${s.title} result`}>
                    <button type="button" role="radio" aria-checked={r === 'ok'} onClick={() => set('ok')} className={cn('min-h-[56px] rounded-control border-2 text-[16px] font-semibold flex items-center justify-center gap-2', r === 'ok' ? 'bg-emerald-600 border-emerald-600 text-white' : 'border-border-strong bg-surface text-text-primary active:bg-surface-secondary')}>
                      <Check className="h-5 w-5" strokeWidth={3} /> OK
                    </button>
                    <button type="button" role="radio" aria-checked={r === 'notok'} onClick={() => set('notok')} className={cn('min-h-[56px] rounded-control border-2 text-[16px] font-semibold flex items-center justify-center gap-2', r === 'notok' ? 'bg-red-600 border-red-600 text-white' : 'border-border-strong bg-surface text-text-primary active:bg-surface-secondary')}>
                      <X className="h-5 w-5" strokeWidth={3} /> Not OK
                    </button>
                  </div>
                  </div>
                </li>
              );
            })}
          </ol>
          <div className={cn('px-4 py-2.5 border-t-2 text-[14px] leading-snug', anyNotOk ? 'border-red-300 bg-red-50 text-red-900' : allDone ? 'border-amber-300 bg-amber-50 text-amber-900' : 'border-border-hairline text-text-secondary')} role="status">
            {anyNotOk
              ? 'A check failed. Call engineering now and leave the pump as it is.'
              : allDone
                ? 'All visual checks OK, but the alarm is still active. Escalate to engineering and record results in eBR.'
                : 'Record each result. These checks do not clear the alarm; engineering decides any adjustment.'}
          </div>
        </section>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <LinkButton href="/operator/shift" size="touch" className="text-[17px] border-2"><ArrowLeft className="h-5 w-5" /> Back to active step checklist</LinkButton>
        <Button size="touch" variant={anyNotOk || allDone ? 'primary' : 'danger'} className="text-[17px] border-2" onClick={call.onOpen}><PhoneCall className="h-5 w-5" /> Call engineering / on-call support</Button>
      </div>

      <CallEngineeringModal
        open={call.open}
        onClose={call.onClose}
        context={`${alarmId} on PM-204 (BR-UP-01, MES-26073) at ${tripTimestamp}, head pressure ${headPressureSpike}. Operator checks: ${answered}/4 recorded${anyNotOk ? ', at least one NOT OK' : ''}. Please attend Suite 3B.`}
      />
    </div>
  );
}

function Waveform() {
  const { pPath, fPath, W, H, L, R, T, B, x, yP } = useMemo(() => {
    const W = 520, H = 190, L = 44, R = 48, T = 12, B = 26;
    const x = (h: number) => L + ((h - 240) / 40) * (W - L - R);
    const yP = (v: number) => T + (1 - (v - 0.8) / 0.8) * (H - T - B);
    const yF = (v: number) => T + (1 - (v - 13) / 5) * (H - T - B);
    let pPath = '', fPath = '';
    for (let h = 240; h <= 280.001; h += 0.5) {
      const p = 0.97 + 0.46 * Math.exp(-(((h - ANOMALY_HOUR) / 2.2) ** 2)) + (h > ANOMALY_HOUR ? 0.14 * (1 - Math.exp(-(h - ANOMALY_HOUR) / 3)) : 0) + 0.002 * (h - 240);
      const f = 16.9 - 0.006 * (h - 200) - 2.05 * sig((h - ANOMALY_HOUR) * 1.4);
      pPath += `${h === 240 ? 'M' : 'L'}${x(h).toFixed(1)},${yP(p).toFixed(1)}`;
      fPath += `${h === 240 ? 'M' : 'L'}${x(h).toFixed(1)},${yF(f).toFixed(1)}`;
    }
    return { pPath, fPath, W, H, L, R, T, B, x, yP };
  }, []);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="mt-1 w-full h-[190px]" role="img" aria-label="Head pressure rises to 1.48 bar at hour 264.4 while feed flow drops from about 16.6 to 14.5 mL/min">
      {[0.8, 1.0, 1.2, 1.4, 1.6].map((v) => (
        <g key={v}>
          <line x1={L} x2={W - R} y1={yP(v)} y2={yP(v)} stroke="#e2e8f0" />
          <text x={L - 6} y={yP(v) + 4} fontSize="12" textAnchor="end" fill="#b91c1c">{v.toFixed(1)}</text>
        </g>
      ))}
      {[13, 14, 15, 16, 17, 18].map((v) => (
        <text key={v} x={W - R + 6} y={T + (1 - (v - 13) / 5) * (H - T - B) + 4} fontSize="12" fill="#0369a1">{v}</text>
      ))}
      {[240, 250, 260, 270, 280].map((h) => (
        <text key={h} x={x(h)} y={H - 6} fontSize="12" textAnchor="middle" fill="#475569">{h}h</text>
      ))}
      <line x1={L} x2={W - R} y1={yP(1.2)} y2={yP(1.2)} stroke="#64748b" strokeWidth="1.5" strokeDasharray="6 4" />
      <line x1={x(ANOMALY_HOUR)} x2={x(ANOMALY_HOUR)} y1={T} y2={H - B} stroke="#dc2626" strokeWidth="2" strokeDasharray="5 4" />
      <text x={x(ANOMALY_HOUR) - 6} y={T + 12} fontSize="13" fontWeight="700" textAnchor="end" fill="#b91c1c">Trip 264.4h · 1.48 bar</text>
      <path d={fPath} fill="none" stroke="#0284c7" strokeWidth="3" strokeLinejoin="round" />
      <path d={pPath} fill="none" stroke="#dc2626" strokeWidth="3" strokeLinejoin="round" />
    </svg>
  );
}

function TubingLife({ hours }: { hours: number }) {
  const max = 600;
  const pct = (v: number) => `${(v / max) * 100}%`;
  return (
    <div aria-label={`Tubing at ${hours} of 400 to 500 hours expected life`}>
      <div className="relative h-6 rounded-control bg-slate-200 overflow-hidden">
        <div className="absolute inset-y-0 bg-amber-300" style={{ left: pct(400), width: pct(100) }} />
        <div className="absolute inset-y-0 bg-red-300" style={{ left: pct(500), right: 0 }} />
        <div className="absolute inset-y-0 w-1 bg-slate-900" style={{ left: pct(hours) }} />
      </div>
      <div className="relative h-5 text-[13px] text-text-secondary tabular-nums">
        <span className="absolute left-0">0 h</span>
        <span className="absolute -translate-x-1/2" style={{ left: pct(400) }}>400</span>
        <span className="absolute -translate-x-1/2 font-bold text-text-primary" style={{ left: pct(hours + 24) }}>{hours} h</span>
        <span className="absolute -translate-x-1/2" style={{ left: pct(500) }}>500</span>
        <span className="absolute right-0">600 h</span>
      </div>
    </div>
  );
}
