/**
 * Per-tab, in-memory cache of GET responses so client-side navigation renders the last
 * known data at once while the page refetches (stale-while-revalidate).
 *
 * Never persisted: sign-out and organization switches do full page loads, which empty it,
 * so cached data cannot cross accounts. Any successful mutation drops everything except
 * artifacts, which are immutable once recorded.
 * ponytail: unbounded Map; add an LRU cap if a session ever holds thousands of responses.
 */
const store = new Map<string, unknown>();

export const cached = <T,>(key: string): T | undefined => store.get(key) as T | undefined;

export function remember(key: string, value: unknown) {
  store.set(key, value);
}

export function forgetMutable() {
  for (const key of Array.from(store.keys())) if (!key.includes('/artifacts/')) store.delete(key);
}

export function clearCache() {
  store.clear();
}
