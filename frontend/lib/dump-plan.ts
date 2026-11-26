/**
 * Propose how a dropped dump splits into deliveries, by CDMO and month, from folder and file names.
 *
 * Folders describe how the CDMO organised the dump, so a month in a folder name wins over a date in a
 * file name inside it. Only CDMO names already known in this workspace split by CDMO: unknown folder
 * names are usually file types ("CoAs", "LIMS"), not CDMOs. The person always confirms or edits the plan.
 * ponytail: names only; reading dates from inside files (email Date, CoA headers) is the upgrade path.
 */
export type PlannedGroup = { key: string; cmo: string; month: string | null; label: string; paths: string[] };

const MONTHS = ['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december'];
const ABBREVIATIONS = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'];
const ISO = /(?:^|\D)(20\d{2})[-_. ]?(0[1-9]|1[0-2])(?:[-_. ]?(?:0[1-9]|[12]\d|3[01]))?(?=\D|$)/;
// What the delivery checks can read, or can open (archives, emails); mirrors the server's intake rules.
const CHECKABLE = /\.(pdf|csv|tsv|xlsx|xlsm|txt|log|docx|json|png|jpe?g|tiff?|zip|eml|msg)$/i;
const squash = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, '');

/** "2026-10", "10" (month without a year) or null. */
export function monthOf(segment: string): string | null {
  const iso = segment.match(ISO);
  if (iso) return `${iso[1]}-${iso[2]}`;
  const words = segment.toLowerCase().split(/[^a-z]+/);
  const year = segment.match(/(?:^|\D)(20\d{2})(?=\D|$)/)?.[1];
  let month = words.map(w => MONTHS.indexOf(w)).find(i => i >= 0);
  // Three-letter forms ("Oct") are common words too ("mar", "jan"), so only trust them next to a year.
  if (month === undefined && year) month = words.map(w => ABBREVIATIONS.indexOf(w === 'sept' ? 'sep' : w)).find(i => i >= 0);
  if (month === undefined) return null;
  const mm = String(month + 1).padStart(2, '0');
  return year ? `${year}-${mm}` : mm;
}

export function monthLabel(month: string | null) {
  if (!month) return 'no month found';
  const [y, m] = month.includes('-') ? month.split('-') : [null, month];
  const name = MONTHS[Number(m) - 1];
  return `${name[0].toUpperCase()}${name.slice(1)}${y ? ` ${y}` : ''}`;
}

export function planDump(paths: string[], knownCmos: string[], fallbackCmo: string): PlannedGroup[] {
  const known = knownCmos.filter(c => squash(c).length >= 3).sort((a, b) => b.length - a.length);
  const groups = new Map<string, PlannedGroup>();
  for (const path of paths) {
    const segments = path.split('/');
    const cmo = segments.map(s => known.find(c => squash(s).includes(squash(c)))).find(Boolean) ?? fallbackCmo;
    const month = segments.map(monthOf).find(Boolean) ?? null;
    const key = `${cmo}\u0000${month ?? ''}`;
    const group = groups.get(key) ?? { key, cmo, month, label: '', paths: [] };
    group.paths.push(path);
    groups.set(key, group);
  }
  let list = [...groups.values()];
  // A month without a year joins the same month with a year, when there is exactly one.
  for (const g of list.filter(g => g.month && !g.month.includes('-'))) {
    const match = list.filter(o => o.cmo === g.cmo && o.month?.endsWith(`-${g.month}`));
    if (match.length === 1) { match[0].paths.push(...g.paths); g.paths = []; }
  }
  // Undated files (a cover letter at the top) belong to the CDMO's only dated delivery, if it has one.
  for (const g of list.filter(g => !g.month)) {
    const dated = list.filter(o => o.cmo === g.cmo && o.month && o.paths.length);
    if (dated.length === 1) { dated[0].paths.push(...g.paths); g.paths = []; }
  }
  // A group of only non-data files (a README) cannot be checked alone: it joins the CDMO's first delivery.
  for (const g of list.filter(g => g.paths.length && !g.paths.some(p => CHECKABLE.test(p)))) {
    const home = list.find(o => o !== g && o.cmo === g.cmo && o.paths.some(p => CHECKABLE.test(p))) ?? list.find(o => o !== g && o.paths.some(p => CHECKABLE.test(p)));
    if (home) { home.paths.push(...g.paths); g.paths = []; }
  }
  list = list.filter(g => g.paths.length);
  for (const g of list) g.label = `${g.cmo} · ${monthLabel(g.month)}`;
  return list.sort((a, b) => a.cmo.localeCompare(b.cmo) || (a.month ?? '9999').localeCompare(b.month ?? '9999'));
}
