'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Activity, AlertTriangle, Check, ChevronDown, ChevronRight, Delete, Lock, Send, UserCheck } from 'lucide-react';
import { Button, LinkButton, Modal } from '@/components/ui';
import { SourceExcerpt } from '@/components/screens/d/operator';
import { useAppContext } from '@/lib/app-context';
import { cn } from '@/lib/cn';

const EXCEPTIONS = [
  {
    id: 'PM-204', title: 'PM-204 feed flow droop', severity: 'critical' as const,
    summary: 'Flow 14.48 mL/min vs setpoint 16.90 (−14.3%); head pressure 1.48 bar above 1.20 ceiling since Hour 264.4.',
    status: 'Alarm ALM-UP-204 active · engineering informed · non-invasive checks pending',
    next: 'Incoming shift: keep monitoring; do not adjust occlusion or setpoints. MSAT investigation INV-104 open.',
    source: 'ebr-mes-26073',
  },
  {
    id: 'CIP', title: 'CIP clashes with MES-26074 inoculation', severity: 'warning' as const,
    summary: 'CIP-UP01-118 on BR-UP-01 overlaps MES-26074 inoculation on Mon 26 Oct by 4.5 h.',
    status: 'Two scenarios drafted for supervisor; none applied',
    next: 'Scenario A (shift inoculation +4.5 h) is awaiting supervisor and QA signatures; it must be decided before Mon 26 Oct 06:00.',
    source: 'd-mes-cip-schedule',
  },
  {
    id: 'QC-948', title: 'QC-948 attestation pending', severity: 'warning' as const,
    summary: 'Harvest titer 3.42 g/L out of trend (spec >3.80). Analyst signed; QA second-person review pending.',
    status: 'Awaiting QA reviewer Priya Natarajan',
    next: 'No operator action. Batch MES-26073 stays on QA hold.',
    source: 'lims-qc-948',
  },
];

type Signer = 'outgoing' | 'incoming';
const SIGNERS: Record<Signer, { name: string; role: string }> = {
  outgoing: { name: 'Taylor Reed', role: 'Outgoing lead · Shift B' },
  incoming: { name: 'Sarah Chen', role: 'Incoming lead · Shift C' },
};

export default function OperatorHandoffPage() {
  const router = useRouter();
  const { notify } = useAppContext();
  const [open, setOpen] = useState<string | null>('PM-204');
  const [notes, setNotes] = useState<Array<{ by: string; text: string; time: string }>>([
    { by: 'Taylor Reed', text: 'Feed bag FM-2207 at ~38% remaining. Next bag staged in airlock 2.', time: '13:42' },
  ]);
  const [note, setNote] = useState('');
  const [signed, setSigned] = useState<Record<Signer, string | null>>({ outgoing: null, incoming: null });
  const [pinFor, setPinFor] = useState<Signer | null>(null);
  const [pin, setPin] = useState('');
  const unresolvedAlerts = EXCEPTIONS.length;
  const bothSigned = !!signed.outgoing && !!signed.incoming;

  const addNote = () => {
    if (!note.trim()) return;
    setNotes((n) => [...n, { by: 'Taylor Reed', text: note.trim(), time: new Date().toTimeString().slice(0, 5) }]);
    setNote('');
  };

  const confirmPin = () => {
    if (!pinFor || pin.length < 4) return;
    setSigned((s) => ({ ...s, [pinFor]: new Date().toTimeString().slice(0, 5) }));
    notify(`${SIGNERS[pinFor].name} signed the handoff (demo PIN; not a validated e-signature).`);
    setPinFor(null);
    setPin('');
  };

  const submit = () => {
    notify('Handoff submitted to supervisor Marcus Bell with 3 open exceptions (demo — not written to MES).');
    router.push('/home');
  };

  return (
    <div className="h-full flex flex-col p-4 gap-3 text-[16px]">
      <div className="flex items-center gap-3">
        <div>
          <p className="text-[13px] font-semibold uppercase tracking-wider text-text-tertiary">Shift handoff · Suite 3B · MES-26073</p>
          <h1 className="text-[22px] font-bold text-text-primary leading-tight">Shift B → Shift C</h1>
        </div>
        <div className="ml-auto grid grid-cols-4 gap-2 text-center">
          {[
            ['Step', '05.4'],
            ['Batch day', '11 of 14'],
            ['Room', 'Grade B · in spec'],
            ['Open alerts', String(unresolvedAlerts)],
          ].map(([k, v]) => (
            <div key={k} className={cn('rounded-control border-2 px-3 py-1.5 min-w-[112px]', k === 'Open alerts' ? 'border-red-300 bg-status-critical-bg' : 'border-border-strong bg-surface')}>
              <p className="text-[12px] text-text-tertiary">{k}</p>
              <p className={cn('text-[16px] font-bold tabular-nums', k === 'Open alerts' ? 'text-red-700' : 'text-text-primary')}>{v}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="flex-1 min-h-0 grid grid-cols-[minmax(0,1fr)_340px] gap-3">
        <div className="min-h-0 overflow-y-auto space-y-3 pr-1">
          <section aria-label="Open exceptions" className="space-y-2">
            {EXCEPTIONS.map((e) => {
              const isOpen = open === e.id;
              return (
                <div key={e.id} className={cn('rounded-card border-2 bg-surface', e.severity === 'critical' ? 'border-red-300' : 'border-amber-300')}>
                  <button type="button" onClick={() => setOpen(isOpen ? null : e.id)} aria-expanded={isOpen} className="w-full min-h-[60px] flex items-center gap-3 px-4 text-left active:bg-surface-secondary">
                    <AlertTriangle className={cn('h-6 w-6 shrink-0', e.severity === 'critical' ? 'text-red-600' : 'text-amber-600')} aria-hidden />
                    <span className="flex-1 min-w-0">
                      <span className="block text-[16px] font-semibold text-text-primary">{e.title}</span>
                      <span className="block text-[13px] text-text-secondary truncate">{e.status}</span>
                    </span>
                    {isOpen ? <ChevronDown className="h-6 w-6" /> : <ChevronRight className="h-6 w-6" />}
                  </button>
                  {isOpen && (
                    <div className="px-4 pb-3 space-y-2">
                      <p className="text-[15px] text-text-primary leading-snug">{e.summary}</p>
                      <p className="text-[15px] text-text-primary leading-snug"><span className="font-semibold">Next: </span>{e.next}</p>
                      <SourceExcerpt id={e.source} />
                    </div>
                  )}
                </div>
              );
            })}
          </section>

          <section aria-label="Shift notes" className="rounded-card border-2 border-border-strong bg-surface p-3">
            <h2 className="text-[17px] font-semibold text-text-primary">Shift notes</h2>
            <ul className="mt-2 space-y-1.5">
              {notes.map((n, i) => (
                <li key={i} className="text-[15px] text-text-primary"><span className="font-mono text-[13px] text-text-tertiary tabular-nums">{n.time}</span> <span className="font-semibold">{n.by}:</span> {n.text}</li>
              ))}
            </ul>
            <div className="mt-2 flex gap-2">
              <label htmlFor="shift-note" className="sr-only">Add shift note</label>
              <input id="shift-note" value={note} onChange={(e) => setNote(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && addNote()} placeholder="Add a note for Shift C" className="flex-1 min-h-[56px] rounded-control border-2 border-border-strong px-3 text-[16px] focus:outline-none focus:ring-2 focus:ring-brand-teal" />
              <Button size="touch" onClick={addNote} disabled={!note.trim()}>Add note</Button>
            </div>
          </section>
        </div>

        <aside className="flex flex-col gap-3 min-h-0">
          <section aria-label="Dual sign-off" className="rounded-card border-2 border-border-strong bg-surface p-3 space-y-2">
            <h2 className="text-[17px] font-semibold text-text-primary">Dual sign-off</h2>
            <p className="text-[13px] text-text-secondary">Outgoing lead signs first, then incoming lead. Both confirm they reviewed all 3 open exceptions.</p>
            {(['outgoing', 'incoming'] as Signer[]).map((s, i) => {
              const done = signed[s];
              const blocked = s === 'incoming' && !signed.outgoing;
              return (
                <button
                  key={s}
                  type="button"
                  disabled={!!done || blocked}
                  onClick={() => { setPinFor(s); setPin(''); }}
                  className={cn('w-full min-h-[64px] flex items-center gap-3 rounded-card border-2 px-3 text-left disabled:cursor-not-allowed', done ? 'border-emerald-400 bg-status-success-bg' : blocked ? 'border-border-hairline bg-surface-secondary opacity-60' : 'border-brand-teal bg-brand-teal-light active:bg-cyan-100')}
                >
                  <span className={cn('h-9 w-9 shrink-0 rounded-full flex items-center justify-center text-[15px] font-bold', done ? 'bg-emerald-600 text-white' : 'bg-surface border-2 border-border-strong text-text-secondary')}>
                    {done ? <Check className="h-5 w-5" strokeWidth={3} /> : i + 1}
                  </span>
                  <span className="flex-1 min-w-0">
                    <span className="block text-[16px] font-semibold text-text-primary">{SIGNERS[s].name}</span>
                    <span className="block text-[13px] text-text-secondary">{SIGNERS[s].role}</span>
                  </span>
                  <span className="text-[14px] font-semibold text-text-primary">
                    {done ? `Signed ${done}` : blocked ? <span className="flex items-center gap-1 text-text-tertiary"><Lock className="h-4 w-4" />After #1</span> : <span className="flex items-center gap-1"><UserCheck className="h-5 w-5" />Sign</span>}
                  </span>
                </button>
              );
            })}
          </section>

          <div className="mt-auto space-y-2">
            <LinkButton href="/operator/troubleshooting" size="touch" className="w-full text-[17px] border-2"><Activity className="h-5 w-5" /> Inspect telemetry curve</LinkButton>
            <Button size="touch" variant="primary" className="w-full text-[17px]" disabled={!bothSigned} onClick={submit}>
              <Send className="h-5 w-5" /> Submit handoff to supervisor
            </Button>
            {!bothSigned && <p className="text-center text-[13px] text-text-tertiary">Enabled after both leads sign</p>}
          </div>
        </aside>
      </div>

      <Modal
        open={!!pinFor}
        onClose={() => setPinFor(null)}
        title={pinFor ? `Sign as ${SIGNERS[pinFor].name} · demo PIN` : ''}
        width="max-w-sm"
        footer={<><Button size="touch" onClick={() => setPinFor(null)}>Cancel</Button><Button size="touch" variant="primary" onClick={confirmPin} disabled={pin.length < 4}>Confirm signature</Button></>}
      >
        <p className="text-[14px] text-text-secondary">Meaning: “I reviewed the cleanroom state and the open exceptions.” Demo: any 4 digits are accepted; this is not a validated e-signature.</p>
        <div className="mt-3 flex justify-center gap-3" aria-label={`${pin.length} of 4 digits entered`}>
          {[0, 1, 2, 3].map((i) => <span key={i} className={cn('h-4 w-4 rounded-full border-2', i < pin.length ? 'bg-slate-900 border-slate-900' : 'border-slate-400')} />)}
        </div>
        <div className="mt-3 grid grid-cols-3 gap-2">
          {['1', '2', '3', '4', '5', '6', '7', '8', '9', '', '0', 'del'].map((k, i) =>
            k === '' ? <span key={i} /> : (
              <button
                key={i}
                type="button"
                onClick={() => setPin((p) => (k === 'del' ? p.slice(0, -1) : p.length < 4 ? p + k : p))}
                aria-label={k === 'del' ? 'Delete digit' : `Digit ${k}`}
                className="min-h-[60px] rounded-control border-2 border-border-strong bg-surface text-[22px] font-semibold text-text-primary active:bg-surface-secondary flex items-center justify-center"
              >
                {k === 'del' ? <Delete className="h-6 w-6" /> : k}
              </button>
            ),
          )}
        </div>
      </Modal>
    </div>
  );
}
