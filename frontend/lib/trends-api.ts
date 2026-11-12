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
/** Calculated at measured times only: the sharpest steps within a batch, and the widest gaps between batches at one time. */
export type Standouts = {
  largest_changes_between_consecutive_samples?: Array<{ key: string; batch: string; from_h: number; to_h: number; from: number; to: number; change: number }>;
  typical_change_between_samples?: number;
  largest_same_time_differences?: Array<{ key: string; batch: string; time_h: number; value: number; median_of_other_runs: number; difference: number; runs_at_this_time: number }>;
  from_sampled_profiles: boolean;
};
export type TrendData = TrendCatalogue & { parameter: string; series: TrendSeries[]; standouts: Standouts };

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

export type ExportFormat = 'csv' | 'xlsx' | 'json';
/** Leaving parameters, batches or columns out means all of them. */
export type ExportOptions = { layout: ExportLayout; parameters?: string[]; batches?: string[]; columns?: string[];
  timeFrom?: number | null; timeTo?: number | null; celsius?: boolean; verifiedOnly?: boolean };
export type ExportPreview = { columns: string[]; rows: Array<Record<string, string | number | boolean | null>>; total_rows: number };

function exportQuery(options: ExportOptions) {
  const query = new URLSearchParams({ layout: options.layout });
  options.parameters?.forEach(p => query.append('parameter', p));
  options.batches?.forEach(b => query.append('batch', b));
  options.columns?.forEach(c => query.append('column', c));
  if (options.timeFrom != null) query.set('time_from', String(options.timeFrom));
  if (options.timeTo != null) query.set('time_to', String(options.timeTo));
  if (options.celsius) query.set('celsius', 'true');
  if (options.verifiedOnly) query.set('verified_only', 'true');
  return query;
}

export function exportTrends(options: ExportOptions & { format: ExportFormat }) {
  const query = exportQuery(options); query.set('format', options.format);
  return download(`/trends/export?${query}`, `batch-values-${options.layout}.${options.format}`);
}

/** The first rows of exactly what a download would contain. */
export async function previewExport(options: ExportOptions, rows = 8) {
  const query = exportQuery(options); query.set('preview', String(rows));
  return (await cmoFetch(`/trends/export?${query}`)).json() as Promise<ExportPreview>;
}

/** What Trends hands to the Export page when its button is used: the parameter and batches on screen. */
export const EXPORT_HANDOFF = 'export.handoff';

/** Readable without false precision: four significant figures, no exponent for ordinary magnitudes. */
export function formatValue(v: number | null | undefined) {
  if (v == null || !Number.isFinite(v)) return '—';
  const a = Math.abs(v);
  if (a !== 0 && (a < 0.001 || a >= 1e7)) return v.toExponential(2);
  return String(Number(v.toPrecision(4)));
}
