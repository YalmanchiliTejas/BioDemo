'use client';

import { useSyncExternalStore } from 'react';

/** The person recorded on decisions. Replaced by the signed-in identity once authentication exists. */
const KEY = 'cmo.reviewer';
const EVENT = 'reviewer-change';

function subscribe(callback: () => void) {
  window.addEventListener(EVENT, callback);
  window.addEventListener('storage', callback);
  return () => { window.removeEventListener(EVENT, callback); window.removeEventListener('storage', callback); };
}

export function setReviewer(name: string) {
  localStorage.setItem(KEY, name.trim());
  window.dispatchEvent(new Event(EVENT));
}

export function useReviewer() {
  return useSyncExternalStore(subscribe, () => localStorage.getItem(KEY) ?? '', () => '');
}
