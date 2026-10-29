/** Client for the CMO delivery API (backend/src/manufacturing_data/cmo/api.py), served by the platform API. */
import { PROCESS_API } from './process-api';

export type SourceRef = { path: string; sheet?: string | null; cell?: string | null; row?: number | null; column?: string | null; page?: number | null; region?: number[] | null; span?: string | null };
export type Measurement = {
  id: string; source_id: string; batch: string; time: string; parameter: string; value: number | null; unit: string;
  value_raw: string; unit_raw: string | null; unit_declared?: string | null; parser: string; status: 'needs_review' | 'auto_accepted' | 'accepted' | 'corrected' | 'rejected';
  rule_codes: string[]; source: SourceRef; source_sha256: string; review_binding: string; template_id: string | null; source_verified: boolean;
  extraction_confidence?: Record<string, number | null> | null;
};
export type MappingSpec = { columns: Record<string, string>; batch_column: string | null; time_column: string | null; units?: Record<string, string>; ignored_columns?: string[] };
export type Layout = {
  fingerprint: string; kind: string; sheet: string | null; path: string; headers: string[]; mapping: MappingSpec; confirmed: boolean;
  template_version: number | null; template_origin: string | null; records: number; example_source_id: string;
  based_on: null | { template_id: string; version: number; added_headers: string[]; removed_headers: string[]; reused_headers: string[] };
  decisions?: Array<{ header?: string; choice?: string; confidence?: number; status?: string }>;
};
export type Issue = {
  id: string; rule_code: string; status: 'open' | 'resolved'; path?: string; message?: string; header?: string; sheet?: string;
  batch?: string; parameter?: string; time?: string; row?: number; doc_type?: string; count?: number; elements?: number;
  lines?: Array<{ element_id: string; page: number | null; text: string; pattern: string }>; truncated?: boolean;
  actor?: string; reason?: string; at?: string; expected_pages?: number; actual_pages?: number;
};
export type Coverage = { elements: number; measurement: number; identifier: number; ignored: number; flagged: number; unaccounted: number;
  by_document: Record<string, { elements: number; measurement: number; identifier: number; ignored: number; flagged: number; unaccounted: number }> };
export type ReviewGroup = { id: string; path: string; sheet: string | null; column: string; parameter: string; rule_codes: string[]; count: number;
  batches: string[]; measurement_ids: string[]; unit_raw: string | null; unit: string; invalid_values: number };
export type GuaranteeCheck = { id: string; label: string; passed: boolean; detail: string };
export type Summary = { measurements: number; auto_accepted: number; accepted: number; needs_review: number; rejected: number; open_issues: number;
  review_groups: number; unconfirmed_layouts?: number; corrections: number; model_calls: number; inference_cost_usd: number | null; elements: number | null; unaccounted: number | null; verified_package: boolean };
export type DocumentInfo = { source_id: string; path: string; doc_type: string; classification_method: string; classification_evidence: string | null; sha256: string };
export type Review = { at: string; actor: string; reason: string; decision: string; before: Measurement; after: Measurement; carried_from?: { run_id: string } };
export type Run = {
  id: string; cmo: string; status: 'queued' | 'running' | 'complete' | 'failed' | 'unavailable' | 'interrupted'; error?: string; unavailable_reasons?: string[];
  stages: Array<{ stage: string; state: string; elapsed_seconds: number }>; configuration?: string; requested_configuration?: string; configuration_notes?: string[];
  hosted_inference?: { approved: boolean; synthetic: boolean; basis: string }; package_id?: string; package_ref?: string; delivery_name?: string; disclosure?: string;
  started_at?: string; completed_at?: string; runtime_seconds?: number; superseded_by?: string; carried_over?: { from_run: string; reviews: number; skipped: unknown[] };
  measurements?: Measurement[]; layouts?: Layout[]; issues?: Issue[]; documents?: DocumentInfo[]; coverage?: Coverage; summary?: Summary;
  review_groups?: ReviewGroup[]; guarantee?: { holds: boolean; checks: GuaranteeCheck[]; scope: string }; reviews?: Review[];
  expectations_basis?: { run_id: string; completed_at: string; document_types: string[]; parameters: string[] } | null;
  model_usage?: Array<{ role: string; model: string; status: string; input_tokens: number | null; cost_usd: number | null }>;
};
export type RunListing = Pick<Run, 'id' | 'cmo' | 'status' | 'started_at' | 'completed_at' | 'package_id' | 'delivery_name' | 'superseded_by' | 'runtime_seconds'> & { summary?: Summary; documents: number };
export type CatalogItem = { id: string; kind: 'sample' | 'upload' | 'delivery'; cmo: string; name?: string; dataset?: string; condition?: string; synthetic: boolean; disclosure?: string; files: Array<{ path: string; size?: number; sha256?: string }> };
export type Catalog = { packages: CatalogItem[]; hosted_inference_approved: boolean; storage: { records: string; originals: string }; cmos: string[];
  customer_availability: Record<string, string[]> };
export type Parameter = { id: string; unit: string; aliases: string[]; range: [number, number] };

const TOKEN_KEY = 'cmo.apiToken';

export function apiBase() {
  if (process.env.NEXT_PUBLIC_CMO_API_URL) return process.env.NEXT_PUBLIC_CMO_API_URL.replace(/\/$/, '');
  // Delivery verification is part of the platform API. `next dev` (port 5180) has no same-origin proxy.
  if (process.env.NEXT_PUBLIC_LIFESCI_API_URL) return PROCESS_API.replace(/\/$/, '');
  if (typeof window !== 'undefined' && window.location.port === '5180') return PROCESS_API;
  return '';
}

export const getToken = () => (typeof window === 'undefined' ? '' : sessionStorage.getItem(TOKEN_KEY) ?? '');
export const setToken = (value: string) => sessionStorage.setItem(TOKEN_KEY, value);

export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message); }
}

export async function cmoFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = getToken();
  let response: Response;
  try {
    response = await fetch(`${apiBase()}/api/cmo-ingestion${path}`, {
      ...init,
      headers: { ...(init.body && typeof init.body === 'string' ? { 'Content-Type': 'application/json' } : {}), ...(token ? { 'X-CMO-Token': token } : {}), ...init.headers },
    });
  } catch {
    throw new ApiError('Cannot reach the CMO data service. Check your connection, or ask the administrator whether the service is running.', 0);
  }
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try { const body = await response.json(); message = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail ?? body); } catch { /* keep status text */ }
    if (response.status === 401) message = 'This workspace needs an access token. Enter it under Connection.';
    throw new ApiError(message, response.status);
  }
  return response;
}

export const getJson = async <T,>(path: string) => (await cmoFetch(path)).json() as Promise<T>;
export const postJson = async <T,>(path: string, body: unknown) => (await cmoFetch(path, { method: 'POST', body: JSON.stringify(body) })).json() as Promise<T>;

export async function uploadFile(deliveryId: string, file: File) {
  return (await cmoFetch(`/deliveries/${deliveryId}/files?filename=${encodeURIComponent(file.name)}`, { method: 'POST', body: file, headers: { 'Content-Type': 'application/octet-stream' } })).json() as Promise<CatalogItem>;
}

export async function download(path: string, filename: string) {
  const response = await cmoFetch(path);
  const url = URL.createObjectURL(await response.blob());
  const a = document.createElement('a'); a.href = url; a.download = filename; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  return { complete: response.headers.get('X-Package-Complete') === 'true' };
}

export const ACCEPTED = new Set(['auto_accepted', 'accepted', 'corrected']);

/** Decisions a reviewer still owes: value groups, open issues and unconfirmed layouts. */
export const decisionCount = (summary?: Summary) => summary ? summary.review_groups + summary.open_issues + (summary.unconfirmed_layouts ?? 0) : 0;

/** Plain-language explanations of rule codes, written for a data reviewer. */
export const RULES: Record<string, { title: string; help: string }> = {
  DRAFT_MAPPING: { title: 'Column meaning not confirmed', help: 'Confirm what this column means once; future deliveries in the same layout are then checked automatically.' },
  LAYOUT_CHANGED: { title: 'Layout changed since the last confirmed delivery', help: 'Columns were added, removed or renamed. Unchanged columns keep their confirmed meaning as a proposal.' },
  UNMAPPED_FIELD: { title: 'Column not used', help: 'This column was not converted into data. Map it to a parameter or mark it as ignored.' },
  UNRECOGNIZED_TABLE: { title: 'Table with no known process parameters', help: 'Read it, then map its columns or ignore the whole table for this CMO.' },
  UNACCOUNTED_CONTENT: { title: 'Text not converted into data', help: 'These lines are listed so nothing is lost. Read them; ignore recurring letterhead or footers for future deliveries.' },
  MISSING_FIELD: { title: 'Expected value missing', help: 'A mapped column is empty here, or the file has no batch or time column.' },
  MISSING_PAGE: { title: 'Pages missing', help: 'The document says it has more pages than were delivered.' },
  DUPLICATE_CONFLICT: { title: 'Conflicting values', help: 'The same batch, time and parameter has different values. Decide which is correct.' },
  DUPLICATE_RECORD: { title: 'Repeated record in one file', help: 'The same reading appears more than once in a file. Keep one copy.' },
  ROW_CONFLICT: { title: 'Row contains a conflicting value', help: 'Another value on this row conflicts with a duplicate record, so this row needs a look.' },
  BATCH_MISMATCH: { title: 'Batch not in the process data', help: 'This batch ID does not appear in the process export. It may be a typo.' },
  TIME_ORDER: { title: 'Process time out of order or unreadable', help: 'Times go backwards or could not be read as hours or a timestamp with a time zone.' },
  UNIT_UNKNOWN: { title: 'Unit not stated', help: 'The source prints no unit, or an unknown one. Declare the unit in the mapping to apply it to future deliveries.' },
  UNIT_CONVERT: { title: 'Unit cannot be converted', help: 'The printed unit cannot be converted to the standard unit without more information.' },
  RANGE: { title: 'Value outside the plausible range', help: 'Check the source. A real excursion should be accepted with a reason.' },
  SOURCE_REVIEW: { title: 'Read by OCR or a model', help: 'This value was not read directly from the file text. Compare it with the page image.' },
  VALUE_INVALID: { title: 'Not a number', help: 'Correct the value from the source or reject it.' },
  PARSE_ERROR: { title: 'File could not be read', help: 'Inspect the original file. It may be damaged or password protected.' },
  CLASSIFICATION_UNCERTAIN: { title: 'Document type unknown', help: 'The document type could not be determined from its name or content.' },
  EXTRACTION_UNCERTAIN: { title: 'Extraction needs review', help: 'The extraction model was unsure or failed for part of this document.' },
  MAPPING_UNCERTAIN: { title: 'Column meaning uncertain', help: 'The mapping model was not confident. Confirm the meaning yourself.' },
  BATCH_DOCUMENT_MISSING: { title: 'Batch missing a document', help: 'Other batches in this delivery have this document; this batch does not.' },
  EXPECTED_DOCUMENT_MISSING: { title: 'Document missing compared with last delivery', help: 'The previous verified delivery from this CMO included this document type.' },
  EXPECTED_PARAMETER_MISSING: { title: 'Parameter missing compared with last delivery', help: 'The previous verified delivery reported this parameter.' },
};
export const ruleTitle = (code: string) => RULES[code]?.title ?? code.replace(/_/g, ' ').toLowerCase();

export function sourceLabel(source: SourceRef) {
  if (source.sheet && source.cell) return `${source.path} · ${source.sheet}!${source.cell}`;
  if (source.row) return `${source.path} · row ${source.row}${source.column ? ` · ${source.column}` : ''}`;
  if (source.page) return `${source.path} · page ${source.page}`;
  return source.path;
}

export const kindLabel = (kind: string) => ({ instrument_export: 'Process export', lab_results: 'Lab results', batch_record: 'Batch record', coa: 'Certificate of analysis', environmental_monitoring: 'Environmental monitoring',
  microbiology: 'Microbiology', maintenance: 'Maintenance', deviation_report: 'Deviation report', investigation_report: 'Investigation report', other: 'Unknown type' } as Record<string, string>)[kind] ?? kind;
