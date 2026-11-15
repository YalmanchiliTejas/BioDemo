'use client';

import { useEffect, useRef, useState } from 'react';

// Session storage is account/workspace scoped and is never sent as model context.
const drafts = new Map<string, string>();
function read(key: string) {
  if (drafts.has(key)) return drafts.get(key)!;
  try { return sessionStorage.getItem(key) ?? ''; } catch { return ''; }
}
function write(key: string, text: string) {
  drafts.set(key, text);
  try { if (text) sessionStorage.setItem(key, text); else sessionStorage.removeItem(key); } catch { /* In-memory drafts still work. */ }
}

/** A send may finish after more typing or navigation. Only clear the draft it submitted. */
export function useAssistantDraft(scope: string, conversationId: string | null) {
  const key = `${scope}:draft:${conversationId ?? 'new'}`;
  const [state, setState] = useState(() => ({ key, text: read(key) }));
  const current = useRef(key); current.current = key;
  useEffect(() => { setState({ key, text: read(key) }); }, [key]);
  const setDraft = (text: string) => { write(key, text); setState({ key, text }); };
  const clearSubmitted = (submittedKey: string, submitted: string) => {
    if (read(submittedKey) !== submitted) return;
    write(submittedKey, '');
    if (current.current === submittedKey) setState({ key: submittedKey, text: '' });
  };
  const moveTo = (submittedKey: string, id: string) => {
    const next = `${scope}:draft:${id}`;
    write(next, read(submittedKey)); write(submittedKey, '');
    return next;
  };
  const writeForConversation = (id: string, text: string) => {
    const target = `${scope}:draft:${id}`; write(target, text);
    if (current.current === target) setState({ key: target, text });
  };
  return { draft: state.key === key ? state.text : read(key), draftKey: key, setDraft, clearSubmitted, moveTo, writeForConversation };
}
