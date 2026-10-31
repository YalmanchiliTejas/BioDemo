'use client';
import { useState, type FormEvent } from 'react';
import Link from 'next/link';
import { BrandMark } from '@/components/shell/BrandMark';
import { authConfigured, signUp } from '@/lib/auth';

export default function SignUpPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [sent, setSent] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('');
    try {
      const signedIn = await signUp(email, password);
      if (signedIn) window.location.assign('/account/');
      else setSent(true);
    } catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }
  return <main className="min-h-screen bg-canvas px-5 py-8"><div className="mx-auto max-w-md"><BrandMark href="/"/>
    <div className="mt-14 rounded-xl border border-border-hairline bg-white p-7"><h1 className="text-3xl font-medium">Create your account</h1><p className="mt-4 text-sm leading-6 text-text-secondary">Create an organization after signing in, or ask your team administrator to grant you access. Creating an account grants no access to an existing organization.</p>
      {!authConfigured() && <p role="alert" className="setup-message error mt-5">Account sign-up is not configured for this deployment.</p>}
      {error && <p role="alert" className="setup-message error mt-5">{error}</p>}
      {sent ? <div role="status" className="mt-6"><h2 className="text-lg font-medium">Check your email</h2><p className="mt-3 text-sm leading-6">If registration is available for this address, you will receive a confirmation link. Confirm your email to continue. If you already have an account, sign in below.</p></div> : <form className="auth-fields mt-6" onSubmit={submit}>
        <label>Work email<input type="email" autoComplete="email" required value={email} onChange={e=>setEmail(e.target.value)}/></label>
        <label>Password<input type="password" autoComplete="new-password" required minLength={12} value={password} onChange={e=>setPassword(e.target.value)} aria-describedby="password-help"/></label><p id="password-help" className="text-xs text-text-secondary">Use at least 12 characters.</p>
        <button className="setup-primary" disabled={busy || !authConfigured()}>{busy?'Creating account…':'Create account'}</button>
      </form>}
      <p className="mt-6 text-sm">Already registered? <Link className="text-brand-teal underline" href="/sign-in/">Sign in</Link></p>
    </div></div></main>;
}
