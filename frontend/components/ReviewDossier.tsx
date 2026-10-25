'use client';

import { useState } from 'react';
import { Fingerprint, KeyRound, Lock, ShieldAlert, XCircle } from 'lucide-react';
import { Button, Callout, ClaimTag, Modal, Pill, SectionLabel, table, type Tone } from './ui';
import { cn } from '@/lib/cn';

export interface ReviewDossierProps {
  actionId: string;
  title: string;
  entityScope: string;
  proposedChanges: Array<{ parameter: string; baseline: string; proposed: string; unit: string }>;
  riskTier: 'LOW' | 'MEDIUM' | 'HIGH' | 'BLOCKER';
  author: string;
  approversRequired: Array<{ role: string; name?: string; status: 'SIGNED' | 'PENDING' | 'REJECTED' }>;
  onAuthorizeSignature: (justificationReason: string, fidoAuthToken: string) => Promise<void>;
  onRejectReview: (rejectionNotes: string) => Promise<void>;
  /** What the signature attests to, shown in the signing dialog. */
  signatureMeaning?: string;
  /** Optional extra content (evidence, rationale) rendered between diff and signature block. */
  children?: React.ReactNode;
}

const RISK_TONE: Record<ReviewDossierProps['riskTier'], Tone> = { LOW: 'success', MEDIUM: 'warning', HIGH: 'critical', BLOCKER: 'critical' };
const MIN_JUSTIFICATION = 20;

export function ReviewDossier({ actionId, title, entityScope, proposedChanges, riskTier, author, approversRequired, onAuthorizeSignature, onRejectReview, children, signatureMeaning = 'Approved for implementation planning' }: ReviewDossierProps) {
  const [justification, setJustification] = useState('');
  const [rejectNotes, setRejectNotes] = useState('');
  const [signOpen, setSignOpen] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [credential, setCredential] = useState('');
  const [meaning, setMeaning] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canSign = justification.trim().length >= MIN_JUSTIFICATION;

  const authorize = async () => {
    if (!credential || !meaning) return;
    setBusy(true);
    setError(null);
    try {
      await onAuthorizeSignature(justification.trim(), `demo-fido-${credential.length}-${Date.now()}`);
      setSignOpen(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Signature could not be recorded.');
    } finally {
      setBusy(false);
    }
  };

  const reject = async () => {
    if (rejectNotes.trim().length < 10) return;
    setBusy(true);
    try {
      await onRejectReview(rejectNotes.trim());
      setRejectOpen(false);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <code className="text-xs font-mono text-text-secondary">{actionId}</code>
            <ClaimTag kind="recommendation" />
            <Pill tone={RISK_TONE[riskTier]} dot>Risk: {riskTier}</Pill>
          </div>
          <h2 className="mt-1 text-base font-semibold text-text-primary">{title}</h2>
          <p className="text-xs text-text-tertiary mt-0.5">Scope: {entityScope} · Authored by {author}</p>
        </div>
      </div>

      <div>
        <SectionLabel>Proposed changes · before / after</SectionLabel>
        <div className={cn(table.wrap, 'mt-2 border border-border-hairline rounded-card')}>
          <table className={table.root}>
            <thead>
              <tr>
                <th className={table.th}>Parameter</th>
                <th className={table.th}>Baseline</th>
                <th className={table.th}>Proposed</th>
                <th className={table.th}>Unit</th>
              </tr>
            </thead>
            <tbody>
              {proposedChanges.map((c) => (
                <tr key={c.parameter} className={table.tr}>
                  <td className={cn(table.td, 'font-medium')}>{c.parameter}</td>
                  <td className={cn(table.td, 'font-mono text-text-secondary')}><span className="bg-red-50 text-red-800 px-1 rounded line-through decoration-red-300">{c.baseline}</span></td>
                  <td className={cn(table.td, 'font-mono')}><span className="bg-emerald-50 text-emerald-800 px-1 rounded">{c.proposed}</span></td>
                  <td className={cn(table.td, 'text-text-tertiary')}>{c.unit}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {children}

      <div>
        <SectionLabel>Required signatures</SectionLabel>
        <ul className="mt-2 divide-y divide-border-hairline border border-border-hairline rounded-card">
          {approversRequired.map((a) => (
            <li key={a.role} className="flex items-center justify-between gap-3 px-3 py-2 text-[13px]">
              <div>
                <p className="font-medium text-text-primary">{a.role}</p>
                <p className="text-xs text-text-tertiary">{a.name ?? 'Unassigned'}</p>
              </div>
              <Pill tone={a.status === 'SIGNED' ? 'success' : a.status === 'REJECTED' ? 'critical' : 'warning'} dot>{a.status}</Pill>
            </li>
          ))}
        </ul>
      </div>

      <div>
        <label htmlFor={`just-${actionId}`} className="text-[11px] font-semibold uppercase tracking-wider text-text-tertiary">
          Justification <span className="text-status-critical">*</span>
        </label>
        <textarea
          id={`just-${actionId}`}
          value={justification}
          onChange={(e) => setJustification(e.target.value)}
          rows={3}
          placeholder="State why you are approving, what evidence you reviewed, and any conditions."
          className="mt-2 w-full rounded-control border border-border-strong bg-surface px-3 py-2 text-[13px] text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-brand-teal"
        />
        <p className="mt-1 text-[11px] text-text-tertiary tabular-nums">{Math.min(justification.trim().length, MIN_JUSTIFICATION)}/{MIN_JUSTIFICATION} characters minimum</p>
      </div>

      <Callout tone="neutral" icon={<Lock className="h-4 w-4" />}>
        Approving records your decision only. It does not push the change to DeltaV or any control system. A separate, authorized change-control step in your existing systems is still required.
      </Callout>

      <div className="flex flex-wrap items-center justify-end gap-2">
        <Button variant="danger" onClick={() => setRejectOpen(true)}><XCircle className="h-3.5 w-3.5" /> Reject / request telemetry</Button>
        <Button variant="primary" disabled={!canSign} onClick={() => setSignOpen(true)} title={canSign ? undefined : 'Enter a justification first'}>
          <Fingerprint className="h-3.5 w-3.5" /> Approve &amp; authorize signature
        </Button>
      </div>

      <Modal
        open={signOpen}
        onClose={() => setSignOpen(false)}
        title="Electronic signature"
        footer={
          <>
            <Button onClick={() => setSignOpen(false)}>Cancel</Button>
            <Button variant="primary" disabled={!credential || !meaning || busy} onClick={authorize}>
              <KeyRound className="h-3.5 w-3.5" /> {busy ? 'Recording…' : 'Sign'}
            </Button>
          </>
        }
      >
        <div className="space-y-4 text-[13px]">
          <Callout tone="warning" icon={<ShieldAlert className="h-4 w-4" />} title="Demo signature">
            This sandbox simulates a credential challenge. It is stored in this browser only and is not a 21 CFR Part 11 electronic record.
          </Callout>
          <div className="rounded-control bg-surface-secondary border border-border-hairline p-3 text-xs space-y-1">
            <p><span className="text-text-tertiary">Action</span> <code className="font-mono">{actionId}</code></p>
            <p><span className="text-text-tertiary">Meaning of signature</span> {signatureMeaning}</p>
            <p className="text-text-secondary">“{justification.trim()}”</p>
          </div>
          <label className="block">
            <span className="text-xs font-medium text-text-secondary">Password or security key PIN (Okta / FIDO2)</span>
            <input
              type="password"
              value={credential}
              onChange={(e) => setCredential(e.target.value)}
              autoComplete="off"
              className="mt-1 w-full h-9 rounded-control border border-border-strong px-3 text-[13px] focus:outline-none focus:ring-2 focus:ring-brand-teal"
            />
          </label>
          <label className="flex items-start gap-2">
            <input type="checkbox" checked={meaning} onChange={(e) => setMeaning(e.target.checked)} className="mt-0.5 accent-[#0e7490]" />
            <span className="text-xs text-text-secondary">I have reviewed the evidence and understand this signature is attributable to me.</span>
          </label>
          {error && <p className="text-xs text-status-critical">{error}</p>}
        </div>
      </Modal>

      <Modal
        open={rejectOpen}
        onClose={() => setRejectOpen(false)}
        title="Reject or request more evidence"
        footer={
          <>
            <Button onClick={() => setRejectOpen(false)}>Cancel</Button>
            <Button variant="danger" disabled={rejectNotes.trim().length < 10 || busy} onClick={reject}>Send back to author</Button>
          </>
        }
      >
        <label className="block text-[13px]">
          <span className="text-xs font-medium text-text-secondary">What is missing or wrong?</span>
          <textarea
            value={rejectNotes}
            onChange={(e) => setRejectNotes(e.target.value)}
            rows={4}
            placeholder="e.g. Need gravimetric slip data from PM-204 at 184 RPM before approving."
            className="mt-1 w-full rounded-control border border-border-strong px-3 py-2 text-[13px] focus:outline-none focus:ring-2 focus:ring-brand-teal"
          />
        </label>
      </Modal>
    </div>
  );
}
