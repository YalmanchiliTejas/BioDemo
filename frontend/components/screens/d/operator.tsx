'use client';

import { useState } from 'react';
import { BellRing, Check, ChevronDown, ChevronRight, FileText, Phone } from 'lucide-react';
import { Button, Modal } from '@/components/ui';
import { CITATIONS } from '@/fixtures/biomanufacturingData';
import { useAppContext } from '@/lib/app-context';
import { cn } from '@/lib/cn';

/* ------------------------------------------------------------------ Gauge */

type Band = { from: number; to: number; color: string };

/** Large semicircular gauge for gloved, at-a-distance reading. */
export function TouchGauge({ label, value, unit, min, max, bands, marker, markerLabel, status, tone }: {
  label: string;
  value: number;
  unit: string;
  min: number;
  max: number;
  bands: Band[];
  marker?: number;
  markerLabel?: string;
  status: string;
  tone: 'warning' | 'critical' | 'ok';
}) {
  const W = 260, H = 150, cx = 130, cy = 132, r = 104;
  const ang = (v: number) => Math.PI * (1 - (Math.min(max, Math.max(min, v)) - min) / (max - min));
  const pt = (v: number, rr = r) => [cx + rr * Math.cos(ang(v)), cy - rr * Math.sin(ang(v))] as const;
  const arc = (a: number, b: number) => {
    const [x1, y1] = pt(a);
    const [x2, y2] = pt(b);
    return `M${x1.toFixed(1)},${y1.toFixed(1)} A${r},${r} 0 0 1 ${x2.toFixed(1)},${y2.toFixed(1)}`;
  };
  const [nx, ny] = pt(value, r - 18);
  const toneCls = tone === 'critical' ? 'bg-red-600 text-white' : tone === 'warning' ? 'bg-amber-400 text-slate-900' : 'bg-emerald-600 text-white';
  return (
    <div className="rounded-card border-2 border-border-strong bg-surface p-2.5">
      <div className="flex items-center justify-between gap-2">
        <p className="text-[15px] font-semibold text-text-primary">{label}</p>
        <span className={cn('px-2.5 py-1 rounded-control text-[13px] font-bold uppercase tracking-wide', toneCls)}>{status}</span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-[100px]" role="img" aria-label={`${label}: ${value} ${unit}, ${status}`}>
        <path d={arc(min, max)} stroke="#e2e8f0" strokeWidth="18" fill="none" />
        {bands.map((b, i) => <path key={i} d={arc(b.from, b.to)} stroke={b.color} strokeWidth="18" fill="none" />)}
        {marker !== undefined && (() => {
          const [a1, b1] = pt(marker, r - 14);
          const [a2, b2] = pt(marker, r + 14);
          return <line x1={a1} y1={b1} x2={a2} y2={b2} stroke="#0f172a" strokeWidth="3" />;
        })()}
        <line x1={cx} y1={cy} x2={nx} y2={ny} stroke="#0f172a" strokeWidth="5" strokeLinecap="round" />
        <circle cx={cx} cy={cy} r="9" fill="#0f172a" />
        <text x={cx - r} y={H - 2} fontSize="13" textAnchor="middle" fill="#475569">{min}</text>
        <text x={cx + r} y={H - 2} fontSize="13" textAnchor="middle" fill="#475569">{max}</text>
      </svg>
      <p className="-mt-1 text-center tabular-nums">
        <span className="text-[30px] leading-none font-bold text-text-primary">{value.toFixed(2)}</span>
        <span className="ml-1 text-[16px] text-text-secondary">{unit}</span>
      </p>
      {markerLabel && <p className="mt-1 text-center text-[13px] text-text-secondary">{markerLabel}</p>}
    </div>
  );
}

/* ------------------------------------------------------------------ Inline source excerpt (no inspector on tablet) */

export function SourceExcerpt({ id, label }: { id: string; label?: string }) {
  const [open, setOpen] = useState(false);
  const c = CITATIONS[id];
  if (!c) return null;
  return (
    <div className="rounded-control border border-border-strong bg-surface">
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} className="w-full min-h-[56px] flex items-center gap-2 px-3 text-left text-[15px] font-medium text-text-primary active:bg-surface-secondary">
        <FileText className="h-5 w-5 text-brand-teal shrink-0" aria-hidden />
        <span className="flex-1 min-w-0 truncate">{label ?? `${c.documentName} · ${c.sectionOrClause}`}</span>
        <span className="text-[13px] text-text-tertiary">{open ? 'Hide source' : 'Show source'}</span>
        {open ? <ChevronDown className="h-5 w-5" /> : <ChevronRight className="h-5 w-5" />}
      </button>
      {open && (
        <div className="px-3 pb-3">
          <p className="text-[13px] text-text-tertiary">{c.sourceSystem} · {c.sectionOrClause} · {c.timestamp}</p>
          <pre className="mt-1.5 whitespace-pre-wrap break-words text-[14px] leading-relaxed font-mono text-text-primary bg-surface-secondary border border-border-hairline rounded-control p-3">{c.rawExcerpt}</pre>
          <p className="mt-1.5 text-[12px] font-mono text-text-tertiary break-all">sha256:{c.sha256Hash} (synthetic)</p>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ Call engineering */

const CONTACTS = [
  { id: 'msat', role: 'On-call MSAT', name: 'Alex Rivera', phone: 'ext. 4417', pager: '2417' },
  { id: 'maint', role: 'Maintenance (PM-204)', name: 'D. Huang', phone: 'ext. 2204', pager: '2204' },
  { id: 'sup', role: 'Shift supervisor', name: 'Marcus Bell', phone: 'ext. 3310', pager: '3310' },
];

export function CallEngineeringModal({ open, onClose, context }: { open: boolean; onClose: () => void; context: string }) {
  const { notify } = useAppContext();
  const [who, setWho] = useState<string>('msat');
  const c = CONTACTS.find((x) => x.id === who)!;
  const send = () => {
    onClose();
    notify(`Page sent to ${c.name} (${c.role}) (demo — no message delivered).`, 'info');
  };
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Call engineering / on-call support"
      width="max-w-xl"
      footer={
        <>
          <Button size="touch" onClick={onClose}>Cancel</Button>
          <Button size="touch" variant="primary" onClick={send}><BellRing className="h-5 w-5" /> Send page</Button>
        </>
      }
    >
      <div className="space-y-3">
        <div role="radiogroup" aria-label="Who to page" className="space-y-2">
          {CONTACTS.map((x) => (
            <button
              key={x.id}
              type="button"
              role="radio"
              aria-checked={who === x.id}
              onClick={() => setWho(x.id)}
              className={cn('w-full min-h-[64px] flex items-center gap-3 rounded-card border-2 px-4 text-left', who === x.id ? 'border-brand-teal bg-brand-teal-light' : 'border-border-strong bg-surface active:bg-surface-secondary')}
            >
              <span className={cn('h-6 w-6 rounded-full border-2 flex items-center justify-center shrink-0', who === x.id ? 'border-brand-teal bg-brand-teal text-white' : 'border-border-strong')}>
                {who === x.id && <Check className="h-4 w-4" />}
              </span>
              <span className="flex-1 min-w-0">
                <span className="block text-[16px] font-semibold text-text-primary">{x.role}</span>
                <span className="block text-[14px] text-text-secondary">{x.name}</span>
              </span>
              <span className="text-right text-[14px] tabular-nums text-text-primary">
                <span className="flex items-center gap-1 justify-end"><Phone className="h-4 w-4" />{x.phone}</span>
                <span className="block text-text-tertiary">Pager {x.pager}</span>
              </span>
            </button>
          ))}
        </div>
        <div className="rounded-control bg-surface-secondary border border-border-hairline p-3">
          <p className="text-[13px] text-text-tertiary">Message that will be sent</p>
          <p className="mt-0.5 text-[15px] text-text-primary">{context}</p>
        </div>
        <p className="text-[13px] text-text-tertiary">Demo: no page or call is actually placed.</p>
      </div>
    </Modal>
  );
}
