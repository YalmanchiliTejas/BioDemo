'use client';

import { useEffect, useState, type FormEvent } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Loader2 } from 'lucide-react';
import { Button, Callout, LinkButton } from '@/components/ui';
import { BrandMark } from '@/components/shell/BrandMark';
import { useAppContext } from '@/lib/app-context';
import { authMode, updatePassword, useSession } from '@/lib/auth';

const MIN_LENGTH = 12;
const fieldClass = 'mt-1 w-full h-10 px-3 rounded-control border border-border-strong bg-surface text-[14px] text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-teal';
const labelClass = 'block text-[11px] font-semibold uppercase tracking-wide text-text-tertiary';

/** Landing page for Supabase invite and password-recovery links; supabase-js reads the session from the URL. */
export default function SetPasswordPage() {
  const router = useRouter();
  const { organization } = useAppContext();
  const [linkType, setLinkType] = useState<'invite' | 'recovery' | null>(null);
  const [linkError, setLinkError] = useState('');
  // Read before the auth client consumes and clears the URL fragment.
  useEffect(() => {
    const params = new URLSearchParams(window.location.hash.slice(1) || window.location.search);
    const type = params.get('type');
    if (type === 'invite' || type === 'recovery') setLinkType(type);
    if (params.get('error') || params.get('error_code')) {
      setLinkError(params.get('error_code') === 'otp_expired'
        ? 'This link has expired or was already used.'
        : 'This link could not be used.');
    }
  }, []);
  const { email, loading } = useSession();
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    if (password.length < MIN_LENGTH) { setError(`Use at least ${MIN_LENGTH} characters.`); return; }
    if (password !== confirm) { setError('The two passwords do not match.'); return; }
    setBusy(true);
    try { await updatePassword(password); setDone(true); setTimeout(() => router.replace(linkType === 'recovery' ? '/cmo/' : '/onboarding/start/'), 1200); }
    catch (err) { setError((err as Error).message); setBusy(false); }
  };

  const heading = linkType === 'invite' ? 'Create your password' : 'Set a new password';
  let body;
  if (authMode() !== 'supabase') {
    body = <Callout tone="info">Password sign-in is not configured for this deployment. Use the sign-in page instead.</Callout>;
  } else if (loading) {
    body = <p className="flex items-center gap-2 text-[13px] text-text-secondary"><Loader2 className="h-4 w-4 animate-spin" aria-hidden />Checking your link…</p>;
  } else if (!email) {
    body = (
      <div className="space-y-4">
        <Callout tone="warning" title={linkError || 'This link has expired or was already used.'}>
          Links work once and expire after a short time. On the sign-in page, enter your email and choose “Forgot password?” to get a new one. If you were invited, ask your administrator to resend the invitation.
        </Callout>
        <LinkButton href="/sign-in/" variant="primary" size="lg" className="w-full">Go to sign-in</LinkButton>
      </div>
    );
  } else if (done) {
    body = <Callout tone="success">Password saved. Opening the app…</Callout>;
  } else {
    body = (
      <form className="space-y-4" onSubmit={submit} noValidate>
        <p className="text-[12.5px] text-text-secondary">For <span className="font-medium text-text-primary">{email}</span>. Use at least {MIN_LENGTH} characters; a short phrase is easier to remember.</p>
        {error && <Callout tone="critical">{error}</Callout>}
        <input type="email" autoComplete="username" value={email} readOnly hidden />
        <label className="block">
          <span className={labelClass}>New password</span>
          <input type="password" autoComplete="new-password" autoFocus minLength={MIN_LENGTH} value={password} onChange={e => setPassword(e.target.value)} className={fieldClass} />
        </label>
        <label className="block">
          <span className={labelClass}>Confirm password</span>
          <input type="password" autoComplete="new-password" value={confirm} onChange={e => setConfirm(e.target.value)} className={fieldClass} />
        </label>
        <Button type="submit" variant="primary" size="lg" className="w-full" disabled={busy}>
          {busy ? <><Loader2 className="h-4 w-4 animate-spin" aria-hidden />Saving…</> : 'Save password and continue'}
        </Button>
      </form>
    );
  }

  return <div className="setup-shell">
    <header className="setup-header"><BrandMark href="/" /><Link href="/sign-in/">Back to sign in</Link></header>
    <main className="auth-main" style={{ minHeight: 'calc(100dvh - 88px)' }}>
      <div className="auth-form-wrap"><p className="setup-eyebrow">YOUR SIEVANCE ACCOUNT</p><h1 className="text-3xl tracking-tight mb-4">{heading}</h1><div className="auth-fields">{body}</div></div>
    </main>
  </div>;
}
