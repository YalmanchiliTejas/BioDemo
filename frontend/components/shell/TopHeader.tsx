'use client';

import { useEffect, useState } from 'react';
import { Check, LogOut, UserRound } from 'lucide-react';
import { authMode, signOut, useSession } from '@/lib/auth';
import { setReviewer, useReviewer } from '@/lib/reviewer';
import { BrandMark } from './BrandMark';
import { PrimaryNav } from './Sidebar';

function Person() {
  const name = useReviewer();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState('');
  if (editing || !name) {
    return (
      <form className="flex min-w-0 items-center gap-1" onSubmit={e => { e.preventDefault(); if (draft.trim()) { setReviewer(draft); setEditing(false); } }}>
        <input autoFocus={editing} aria-label="Your name" placeholder="Your name" value={draft} onChange={e => setDraft(e.target.value)}
          className="h-8 w-20 min-w-0 rounded-control sm:w-36 border border-amber-400 px-2 text-[13px]" />
        <button type="submit" className="flex h-8 w-8 shrink-0 items-center justify-center rounded-control text-text-secondary hover:bg-surface-secondary" aria-label="Save name"><Check className="h-4 w-4" /></button>
      </form>
    );
  }
  return (
    <button onClick={() => { setDraft(name); setEditing(true); }} title="Recorded on your decisions. Click to change."
      className="flex h-8 items-center gap-1.5 rounded-control px-2 text-[13px] text-text-secondary hover:bg-surface-secondary">
      <UserRound className="h-4 w-4" aria-hidden /><span className="max-w-[80px] truncate sm:max-w-[140px]">{name}</span>
    </button>
  );
}

/** Supabase mode: decisions are recorded under the signed-in email, so the name is not editable here. */
function Account() {
  const { email, loading } = useSession();
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (email) setReviewer(email); }, [email]);
  if (loading) return null;
  if (!email) {
    return <a href="/sign-in/" className="flex h-8 items-center rounded-control px-2 text-[13px] text-text-secondary hover:bg-surface-secondary">Sign in</a>;
  }
  const leave = async () => {
    setBusy(true);
    try { await signOut(); } catch { /* the local session is cleared regardless */ }
    window.location.assign('/sign-in/');
  };
  return (
    <div className="flex min-w-0 items-center gap-1">
      <span title={`Signed in as ${email}. Recorded on your decisions.`} className="flex h-8 min-w-0 items-center gap-1.5 px-2 text-[13px] text-text-secondary">
        <UserRound className="h-4 w-4 shrink-0" aria-hidden /><span className="max-w-[80px] truncate sm:max-w-[180px]">{email}</span>
      </span>
      <button onClick={leave} disabled={busy} title="Sign out" aria-label="Sign out"
        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-control text-text-secondary hover:bg-surface-secondary disabled:opacity-50">
        <LogOut className="h-4 w-4" aria-hidden />
      </button>
    </div>
  );
}

export function TopHeader() {
  return (
    <header className="shrink-0 px-3 pt-3">
      <div className="mx-auto flex h-14 max-w-6xl items-center gap-2 rounded-xl sm:gap-6 border border-border-hairline bg-white/90 px-3 sm:px-5 shadow-[0_8px_30px_rgba(11,30,34,0.05)] backdrop-blur">
        <BrandMark href="/" />
        <div className="flex flex-1 justify-center"><PrimaryNav /></div>
        {authMode() === 'supabase' ? <Account /> : <Person />}
      </div>
    </header>
  );
}
