/** Session-scoped onboarding state shared between the three onboarding steps. */
export const GOAL_STORAGE_KEY = 'mos.onboarding.goal';
export const TZ_STORAGE_KEY = 'mos.onboarding.timezone';

export function readSession(key: string): string | null {
  try {
    return sessionStorage.getItem(key);
  } catch {
    return null;
  }
}

export function writeSession(key: string, value: string | null) {
  try {
    if (value) sessionStorage.setItem(key, value);
    else sessionStorage.removeItem(key);
  } catch {
    /* storage unavailable */
  }
}
