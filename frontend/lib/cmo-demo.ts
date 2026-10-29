'use client';

/** Guided demo on the public CHO dataset. Each browser session gets its own CMO
 * workspace, so formats confirmed by one visitor never carry into another's demo. */
const KEY = 'cmo.demoCmo';

export const DEMO_STEPS = [
  { packageId: 'cho-calibration', month: 'September', title: 'First delivery', body: 'New CMO, new formats. Confirm how 4 files are read, once.' },
  { packageId: 'cho-returning', month: 'October', title: 'Same formats', body: 'Recognised from September. Values verify without column decisions.' },
  { packageId: 'cho-changed', month: 'November', title: 'Layout changed', body: 'Renamed and new columns, a conflicting lab result and a missing certificate.' },
] as const;

export function demoCmo() {
  let value = sessionStorage.getItem(KEY);
  if (!value) {
    value = `Northfield Biologics · demo ${Math.random().toString(36).slice(2, 6)}`;
    sessionStorage.setItem(KEY, value);
  }
  return value;
}

export function isDemoCmo(cmo?: string) {
  return !!cmo && typeof window !== 'undefined' && sessionStorage.getItem(KEY) === cmo;
}

export function resetDemo() { sessionStorage.removeItem(KEY); }
