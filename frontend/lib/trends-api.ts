/** Accepted values across every delivery (backend/src/manufacturing_data/cmo/trends.py). No model call is involved. */
import { cmoFetch, download } from './cmo-api';

export type TrendBatch = { key: string; batch: string; run_id: string; cmo: string | null; delivery_name: string | null; completed_at: string | null;
  delivery_verified: boolean; time_basis: 'recorded_hours' | 'hours_since_first_reading' };
export type TrendParameter = { id: string; units: Array<string | null>; batches: number; values: number };
export type TrendPoint = { time_h: number | null; value: number; id: string };
export type TrendSummary = { n: number; mean: number; min: TrendPoint; max: TrendPoint; first: TrendPoint; last: TrendPoint };
/** points: [time_h, value, measurement id] in time order. */
export type TrendSeries = TrendBatch & { unit: string | null; summary: TrendSummary; points: Array<[number, number, string]>;
  points_total: number; points_without_time: number; sampled_every: number };
export type TrendCatalogue = { parameters: TrendParameter[]; batches: TrendBatch[]; deliveries: number };
export type TrendData = TrendCatalogue & { parameter: string; series: TrendSeries[] };

export type Statistic = 'last' | 'max' | 'min' | 'mean' | 'first';
export const STATISTICS: Array<{ value: Statistic; label: string }> = [
  { value: 'last', label: 'Final value' }, { value: 'max', label: 'Maximum' }, { value: 'min', label: 'Minimum' },
  { value: 'mean', label: 'Mean' }, { value: 'first', label: 'First value' },
];
export const statistic = (s: TrendSummary, which: Statistic) => which === 'mean' ? s.mean : s[which].value;

export type ExportLayout = 'long' | 'wide' | 'summary';
export const LAYOUTS: Array<{ value: ExportLayout; label: string; detail: string }> = [
  { value: 'long', label: 'One value per row', detail: 'Every value with its source file, cell or page, and file hash. Best for traceability and for tools that pivot themselves.' },
  { value: 'wide', label: 'One row per time point', detail: 'Parameters as columns, one row per batch and time. Best for statistics packages and spreadsheets.' },
  { value: 'summary', label: 'One row per batch', detail: 'First, final, minimum, maximum and mean of each parameter per batch.' },
];

export const getTrends = async <T extends TrendCatalogue = TrendCatalogue>(parameter?: string) =>
  (await cmoFetch(`/trends${parameter ? `?parameter=${encodeURIComponent(parameter)}` : ''}`)).json() as Promise<T>;

/** Leaving parameters or batches out exports all of them. */
export function exportTrends(options: { format: 'csv' | 'xlsx'; layout: ExportLayout; parameters?: string[]; batches?: string[] }) {
  const query = new URLSearchParams({ format: options.format, layout: options.layout });
  options.parameters?.forEach(p => query.append('parameter', p));
  options.batches?.forEach(b => query.append('batch', b));
  return download(`/trends/export?${query}`, `batch-values-${options.layout}.${options.format}`);
}

/** Readable without false precision: four significant figures, no exponent for ordinary magnitudes. */
export function formatValue(v: number | null | undefined) {
  if (v == null || !Number.isFinite(v)) return '—';
  const a = Math.abs(v);
  if (a !== 0 && (a < 0.001 || a >= 1e7)) return v.toExponential(2);
  return String(Number(v.toPrecision(4)));
}
