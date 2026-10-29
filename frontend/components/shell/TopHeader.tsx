'use client';

import { useState } from 'react';
import { Check, UserRound } from 'lucide-react';
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

export function TopHeader() {
  return (
    <header className="shrink-0 px-3 pt-3">
      <div className="mx-auto flex h-14 max-w-6xl items-center gap-2 rounded-xl sm:gap-6 border border-border-hairline bg-white/90 px-3 sm:px-5 shadow-[0_8px_30px_rgba(11,30,34,0.05)] backdrop-blur">
        <BrandMark href="/" />
        <div className="flex flex-1 justify-center"><PrimaryNav /></div>
        <Person />
      </div>
    </header>
  );
}
