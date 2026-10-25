'use client';

import { useState } from 'react';
import { ArrowRight, Check, LifeBuoy, PhoneCall, ShieldAlert } from 'lucide-react';
import { Button, LinkButton, useDisclosure } from '@/components/ui';
import { CallEngineeringModal, SourceExcerpt, TouchGauge } from '@/components/screens/d/operator';
import { cn } from '@/lib/cn';

const CHECKS = [
  { id: 'c1', text: 'Feed bag FM-2207 connected; lot scanned in eBR' },
  { id: 'c2', text: 'Tubing seated centered in pump-head track (see guide)' },
  { id: 'c3', text: 'Pump-head latch closed; no visible kinks or twists' },
  { id: 'c4', text: 'Bolus volume on eBR matches batch record (read only)' },
  { id: 'c5', text: 'Flow alarm acknowledged in DeltaV; engineering informed' },
];

export default function OperatorShiftPage() {
  const [done, setDone] = useState<string[]>(['c1']);
  const call = useDisclosure();
  const activeStep = '05.4 Bolus Nutrient Addition';
  const pumpFlowRate = '14.48 mL/min (Droop Warning)';
  const headPressure = '1.48 bar (Limit Alert)';

  const toggle = (id: string) => setDone((d) => (d.includes(id) ? d.filter((x) => x !== id) : [...d, id]));

  return (
    <div className="h-full flex flex-col p-4 gap-3 text-[16px]">
      <div className="flex items-center gap-3">
        <div className="min-w-0">
          <p className="text-[13px] font-semibold uppercase tracking-wider text-text-tertiary">Active step · Skid BR-UP-01 · MES-26073</p>
          <h1 className="text-[22px] font-bold text-text-primary leading-tight">Step {activeStep}</h1>
        </div>
        <div className="ml-auto flex items-center gap-2 rounded-card border-2 border-amber-400 bg-status-warning-bg px-3 py-2 text-[14px] text-amber-900 max-w-[420px]">
          <ShieldAlert className="h-5 w-5 shrink-0" aria-hidden />
          <span>Do not change setpoints from this tablet. Run checks, then escalate.</span>
        </div>
      </div>

      <div className="flex-1 min-h-0 grid grid-cols-[280px_minmax(0,1fr)_300px] gap-3">
        <section aria-label="Live parameters" className="space-y-3 min-h-0">
          <TouchGauge
            label="PM-204 feed flow"
            value={14.48}
            unit="mL/min"
            min={10}
            max={20}
            bands={[{ from: 10, to: 16.39, color: '#fbbf24' }, { from: 16.39, to: 17.41, color: '#10b981' }, { from: 17.41, to: 20, color: '#fbbf24' }]}
            marker={16.9}
            markerLabel="Setpoint 16.90 · −14.3%"
            status="Droop warning"
            tone="warning"
          />
          <TouchGauge
            label="PM-204 head pressure"
            value={1.48}
            unit="bar"
            min={0}
            max={2}
            bands={[{ from: 0, to: 1.2, color: '#10b981' }, { from: 1.2, to: 2, color: '#ef4444' }]}
            marker={1.2}
            markerLabel="Ceiling 1.20 bar"
            status="Limit alert"
            tone="critical"
          />
          <p className="sr-only">{pumpFlowRate}; {headPressure}</p>
        </section>

        <section aria-label="Step verification checklist" className="rounded-card border-2 border-border-strong bg-surface flex flex-col min-h-0">
          <div className="flex items-center justify-between px-4 py-2.5 border-b border-border-hairline">
            <h2 className="text-[17px] font-semibold text-text-primary">Step verification</h2>
            <span className="text-[15px] font-semibold tabular-nums text-text-secondary">{done.length} of {CHECKS.length} verified</span>
          </div>
          <ul className="flex-1 min-h-0 overflow-y-auto divide-y divide-border-hairline">
            {CHECKS.map((c) => {
              const on = done.includes(c.id);
              return (
                <li key={c.id}>
                  <button
                    type="button"
                    role="checkbox"
                    aria-checked={on}
                    onClick={() => toggle(c.id)}
                    className={cn('w-full min-h-[64px] flex items-center gap-3 px-4 text-left active:bg-surface-secondary', on && 'bg-status-success-bg')}
                  >
                    <span className={cn('h-8 w-8 shrink-0 rounded-control border-2 flex items-center justify-center', on ? 'bg-emerald-600 border-emerald-600 text-white' : 'border-slate-400 bg-surface')}>
                      {on && <Check className="h-5 w-5" strokeWidth={3} />}
                    </span>
                    <span className={cn('text-[16px] leading-snug', on ? 'text-text-primary' : 'text-text-primary font-medium')}>{c.text}</span>
                  </button>
                </li>
              );
            })}
          </ul>
          <p className="px-4 py-2 border-t border-border-hairline text-[13px] text-text-tertiary">Checks are recorded on this tablet only (demo). Execution is signed in DeltaV eBR.</p>
        </section>

        <section aria-label="SOP guidance" className="rounded-card border-2 border-border-strong bg-surface flex flex-col min-h-0 overflow-y-auto">
          <div className="px-3 pt-2.5">
            <p className="text-[13px] font-semibold uppercase tracking-wider text-text-tertiary">SOP-UP-014 Rev 7 · §7.2</p>
            <p className="mt-1 text-[15px] leading-snug text-text-primary">After any occlusion adjustment, a <strong>dynamic slip verification</strong> is required before returning the pump to GMP service.</p>
          </div>
          <TubingGuide />
          <div className="px-3 pb-3">
            <SourceExcerpt id="sop-up-014" label="Read SOP excerpt" />
          </div>
        </section>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <LinkButton href="/operator/troubleshooting" size="touch" variant="secondary" className="text-[17px] border-2"><LifeBuoy className="h-5 w-5" /> Open troubleshooting guide</LinkButton>
        <Button size="touch" variant="danger" className="text-[17px] border-2" onClick={call.onOpen}><PhoneCall className="h-5 w-5" /> Call engineering</Button>
        <LinkButton href="/operator/handoff" size="touch" variant="primary" className="text-[17px]">Proceed to shift handoff <ArrowRight className="h-5 w-5" /></LinkButton>
      </div>

      <CallEngineeringModal open={call.open} onClose={call.onClose} context="Suite 3B · BR-UP-01 · PM-204 flow droop (14.48 mL/min) and head pressure 1.48 bar during Step 05.4 on MES-26073. Please attend." />
    </div>
  );
}

function TubingGuide() {
  return (
    <figure className="px-3 py-2">
      <svg viewBox="0 0 260 150" className="w-full h-[140px]" role="img" aria-label="Tubing seating guide: tubing runs from inlet on the left, around the rollers, to outlet on the right, centered in the track with the latch closed.">
        <rect x="70" y="18" width="120" height="110" rx="14" fill="#f1f5f9" stroke="#334155" strokeWidth="2.5" />
        <circle cx="130" cy="73" r="34" fill="#e2e8f0" stroke="#475569" strokeWidth="2" />
        {[0, 120, 240].map((a) => {
          const r = (a * Math.PI) / 180;
          return <circle key={a} cx={130 + 26 * Math.cos(r)} cy={73 + 26 * Math.sin(r)} r="7" fill="#64748b" />;
        })}
        <path d="M10,112 L84,112 Q84,30 130,30 Q176,30 176,112 L250,112" fill="none" stroke="#0e7490" strokeWidth="7" strokeLinecap="round" />
        <path d="M30,104 l10,8 l-10,8" fill="none" stroke="#0e7490" strokeWidth="3" />
        <path d="M222,104 l10,8 l-10,8" fill="none" stroke="#0e7490" strokeWidth="3" />
        <text x="10" y="138" fontSize="14" fill="#0f172a" fontWeight="600">Inlet</text>
        <text x="250" y="138" fontSize="14" fill="#0f172a" fontWeight="600" textAnchor="end">Outlet</text>
        <rect x="112" y="122" width="36" height="10" rx="3" fill="#334155" />
        <text x="130" y="14" fontSize="12" fill="#334155" textAnchor="middle">Centered in track</text>
      </svg>
      <figcaption className="text-[13px] text-text-secondary">Visual check only: tubing centered, no twist, latch closed. Do not adjust occlusion.</figcaption>
    </figure>
  );
}
