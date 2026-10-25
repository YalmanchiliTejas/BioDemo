'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { ArrowRight, Fingerprint, KeyRound, PlayCircle, ShieldAlert } from 'lucide-react';
import { Button, Pill } from '@/components/ui';
import { BrandMark } from '@/components/shell/BrandMark';
import { ROLE_LABELS, ROLE_PEOPLE, useAppContext, type UserRole } from '@/lib/app-context';
import { cn } from '@/lib/cn';

const CAMPAIGNS = [
  { id: 'CMP-26-10', label: 'CMP-26-10 · AB-mAb-014 fed-batch (3 batches, yield decline)' },
  { id: 'CMP-26-08', label: 'CMP-26-08 · AB-mAb-014 (historical, no open events)' },
];

const DEMO_ROLES: UserRole[] = ['MSAT_LEAD', 'QA_REVIEWER', 'CLEANROOM_SUPERVISOR', 'OPERATOR'];

export default function SignInPage() {
  const router = useRouter();
  const { userRole, setRole, organization, notify } = useAppContext();
  const [campaign, setCampaign] = useState('CMP-26-10');
  const [launching, setLaunching] = useState(false);

  const launch = () => {
    setLaunching(true);
    if (campaign !== 'CMP-26-10') notify('Only CMP-26-10 is loaded in this demo; opening it instead.', 'info');
    router.push(userRole === 'OPERATOR' ? '/operator/shift' : '/home');
  };

  return (
    <div className="min-h-screen bg-canvas flex flex-col">
      <header className="h-14 flex items-center justify-between px-4 md:px-6">
        <BrandMark href="/" />
        <Link href="/" className="text-[12.5px] text-text-secondary hover:text-text-primary">Product overview</Link>
      </header>

      <main className="flex-1 flex items-start md:items-center justify-center px-4 py-8">
        <div className="w-full max-w-[440px]">
          <div className="bg-surface border border-border-hairline rounded-card shadow-sm">
            <div className="px-6 pt-6 pb-5 border-b border-border-hairline">
              <div className="flex items-center gap-3">
                <span className="h-10 w-10 rounded-card bg-slate-900 text-white flex items-center justify-center text-sm font-semibold tracking-tight" aria-hidden>AB</span>
                <div className="min-w-0">
                  <p className="text-[11px] font-semibold uppercase tracking-wider text-text-tertiary">Workspace</p>
                  <h1 className="text-base font-semibold text-text-primary">{organization}</h1>
                </div>
                <Pill tone="muted" className="ml-auto">Mesa Site</Pill>
              </div>
              <p className="mt-3 text-[12.5px] text-text-secondary">Sign in with your organization’s identity provider. Access is scoped by your existing site and role assignments.</p>
            </div>

            <div className="px-6 py-5 space-y-3">
              <Link
                href="/onboarding/start"
                className="w-full inline-flex items-center justify-center gap-2 h-10 px-4 rounded-control bg-slate-900 text-white text-sm font-medium hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-teal focus-visible:ring-offset-1"
              >
                <KeyRound className="h-4 w-4" aria-hidden /> Sign in with Enterprise SSO
              </Link>
              <div className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1 text-[11px] text-text-tertiary">
                <span>Okta · SAML 2.0</span>
                <span aria-hidden>·</span>
                <span className="inline-flex items-center gap-1"><Fingerprint className="h-3 w-3" aria-hidden />FIDO2 WebAuthn</span>
                <span aria-hidden>·</span>
                <span>Simulated in demo</span>
              </div>
            </div>

            <div className="mx-6 mb-6 rounded-card border border-cyan-200 bg-brand-teal-light/60 p-4">
              <div className="flex items-center gap-2">
                <PlayCircle className="h-4 w-4 text-brand-teal" aria-hidden />
                <h2 className="text-[13px] font-semibold text-text-primary">Launch Demo Sandbox</h2>
              </div>
              <p className="mt-1 text-[12px] text-text-secondary">Explore a synthetic campaign with real-looking records. No account needed.</p>

              <label htmlFor="campaign" className="mt-3 block text-[11px] font-semibold uppercase tracking-wide text-text-tertiary">Demo campaign</label>
              <select
                id="campaign"
                value={campaign}
                onChange={(e) => setCampaign(e.target.value)}
                className="mt-1 w-full h-8 px-2 rounded-control border border-border-strong bg-surface text-[13px] text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-teal"
              >
                {CAMPAIGNS.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
              </select>

              <fieldset className="mt-3">
                <legend className="text-[11px] font-semibold uppercase tracking-wide text-text-tertiary">View as</legend>
                <div className="mt-1 grid grid-cols-2 gap-1.5">
                  {DEMO_ROLES.map((r) => (
                    <label
                      key={r}
                      className={cn(
                        'flex flex-col gap-0 px-2.5 py-1.5 rounded-control border cursor-pointer text-[12.5px] focus-within:ring-2 focus-within:ring-brand-teal',
                        userRole === r ? 'border-brand-teal bg-surface' : 'border-border-hairline bg-surface/60 hover:bg-surface',
                      )}
                    >
                      <input type="radio" name="role" value={r} checked={userRole === r} onChange={() => setRole(r)} className="sr-only" />
                      <span className="font-medium text-text-primary">{ROLE_LABELS[r]}</span>
                      <span className="text-[11px] text-text-tertiary">{ROLE_PEOPLE[r]}</span>
                    </label>
                  ))}
                </div>
              </fieldset>

              <Button variant="primary" size="lg" className="mt-4 w-full" onClick={launch} disabled={launching}>
                {launching ? 'Opening sandbox…' : 'Launch Demo Sandbox'} <ArrowRight className="h-4 w-4" aria-hidden />
              </Button>
            </div>
          </div>

          <div className="mt-4 flex items-start gap-2 rounded-card border border-amber-200 bg-status-warning-bg px-3 py-2.5 text-[12px] text-amber-800" role="note">
            <ShieldAlert className="h-4 w-4 mt-px shrink-0" aria-hidden />
            <p>
              <span className="font-semibold">Demo environment; does not write to production PLCs.</span> All records are synthetic. No connection is made to MES, DCS/PLC, LIMS, QMS or ERP systems, and no signature here has regulatory effect.
            </p>
          </div>
          <p className="mt-3 text-center text-[11px] text-text-muted">Session activity in the sandbox is kept in this browser only.</p>
        </div>
      </main>
    </div>
  );
}
