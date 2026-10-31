'use client';
import { useEffect, useState, type FormEvent } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { ArrowRight, Eye, EyeOff, ShieldCheck, Loader2 } from 'lucide-react';
import { BrandMark } from '@/components/shell/BrandMark';
import { authConfigured, authMode, safeNext, sendPasswordReset, signIn, signOut, SIGNED_OUT_MESSAGE, useSession } from '@/lib/auth';
export default function SignInPage() {
    const router = useRouter();
    const { email: signedIn, loading } = useSession();
    const [next, setNext] = useState('/cmo/');
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [visible, setVisible] = useState(false);
    const [error, setError] = useState('');
    const [notice, setNotice] = useState('');
    const [busy, setBusy] = useState<'sign-in' | 'reset' | null>(null);
    const configured = authConfigured();
    useEffect(() => {
        const params = new URLSearchParams(window.location.search);
        setNext(safeNext(params.get('next'), '/cmo/'));
        if (params.get('reason') === 'expired')
            setNotice(SIGNED_OUT_MESSAGE);
    }, []);
    const proceed = async () => {
        setBusy('sign-in');
        setError('');
        try {
            router.replace(`/account/?next=${encodeURIComponent(next)}`);
        }
        catch (err) {
            setError((err as Error).message);
            setBusy(null);
        }
    };
    const submit = async (event: FormEvent) => {
        event.preventDefault();
        setError('');
        setNotice('');
        setBusy('sign-in');
        try {
            await signIn(email, password);
            await proceed();
        }
        catch (err) {
            setError((err as Error).message);
            setBusy(null);
        }
    };
    const reset = async () => {
        if (!email.trim()) {
            setError('Enter your email address, then select Forgot password.');
            return;
        }
        setBusy('reset');
        setError('');
        setNotice('');
        try {
            await sendPasswordReset(email);
            setNotice('If this address has an account, a password reset link is on its way. Check your inbox.');
        }
        catch (err) {
            setError((err as Error).message);
        }
        finally {
            setBusy(null);
        }
    };
    return <div className="auth-shell">
    <section className="auth-story">
      <BrandMark href="/"/>
      <div className="auth-story-copy"><p className="setup-eyebrow">CONNECTED KNOWLEDGE. CLEARER DECISIONS.</p>
        <h1>Your data.<br /> A clearer<br /><span>way forward.</span></h1>
        <p>Bring your manufacturing knowledge together. Trace every finding to its source. Take the next step with confidence.</p>
      </div>
      <div className="auth-story-foot"><ShieldCheck size={20}/><span>Your systems stay the source of truth.<br />You stay in control of access.</span></div>
      <div className="brand-ribbon" aria-hidden="true"/>
    </section>
    <main className="auth-main"><Link href="/" className="auth-overview">Product overview ↗</Link>
      <div className="auth-form-wrap"><p className="setup-eyebrow">WELCOME TO SIEVANCE</p><h2>Good to have you here.</h2>
        <p className="setup-subtitle">Sign in to your workspace to continue.</p>
        {error && <div className="setup-message error" role="alert">{error}</div>}
        {notice && <div className="setup-message" role="status">{notice}</div>}
        {loading ? <p role="status">Checking your session…</p> : !configured ? <div className="setup-message"><strong>{authMode() === 'development' ? 'Local development workspace' : 'Sign-in needs configuration'}</strong><p>Account sign-in is not configured here. Your administrator must configure the Supabase project URL and public key, then rebuild the frontend.</p><Link className="setup-primary" href="/onboarding/start/">Configure data connections <ArrowRight size={17}/></Link><Link className="setup-text-link" href="/cmo/">Explore the demo workspace</Link></div> : signedIn ? <div className="auth-fields"><p>Signed in as <strong>{signedIn}</strong></p><button className="setup-primary" onClick={proceed} disabled={busy !== null}>Continue to workspace <ArrowRight size={17}/></button><button className="setup-text-link" disabled={busy !== null} onClick={async () => { setBusy('sign-in'); setError(''); try {
            await signOut();
        }
        catch (err) {
            setError((err as Error).message);
        }
        finally {
            setBusy(null);
        } }}>Use a different account</button></div> : <form onSubmit={submit} className="auth-fields">
          <label>Work email<input type="email" autoComplete="username" required value={email} onChange={e => setEmail(e.target.value)} placeholder="you@company.com"/></label>
          <label>Password<div className="password-field"><input type={visible ? 'text' : 'password'} autoComplete="current-password" required value={password} onChange={e => setPassword(e.target.value)} placeholder="Enter your password"/><button type="button" aria-label={visible ? 'Hide password' : 'Show password'} aria-pressed={visible} onClick={() => setVisible(v => !v)}>{visible ? <EyeOff size={18}/> : <Eye size={18}/>}</button></div></label>
          <button type="button" className="auth-forgot" disabled={busy !== null} onClick={reset}>{busy === 'reset' ? 'Sending link…' : 'Forgot password?'}</button>
          <button type="submit" className="setup-primary" disabled={busy !== null}>{busy === 'sign-in' ? <><Loader2 size={17} className="animate-spin"/> Signing in…</> : <>Sign in <ArrowRight size={17}/></>}</button>
        </form>}
        <p className="auth-invite">New to Sievance? <Link href="/sign-up/" className="text-brand-teal underline">Create an account</Link><br />Joining a team? Ask its administrator to grant access after you register.</p>
      </div><footer className="auth-footer"><ShieldCheck size={15}/> Access follows your organization’s permissions.</footer>
    </main>
  </div>;
}
