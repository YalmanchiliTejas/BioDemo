/** The workbench: one selection, the calculated picture that follows it, and the work plan that keeps the next steps.
 *  Types follow the backend's workspace-task and work-plan responses. Nothing here calls a model except `explain`. */
import { processRequest } from './process-api';
import { emptyTask, runTask, type SourceRef, type TaskResult, type TaskSpec } from './assistant-workflows';

export type Dataset = { id: string; run_id?: string; revision?: number; status?: string; site_id?: string; cmo?: string | null; delivery_name?: string | null;
  measurements?: number | null; batches?: string[] | null; parameters?: string[] | null; verification?: 'verified' | 'provisional'; published_at?: string;
  review?: { pending_values?: number; rejected_values?: number; open_issues?: number } | null };
export type ProfileSeries = { batch: string; parameter: string; unit: string | null; n: number; first_time_h: number | null; last_time_h: number | null; min: number; max: number; mean: number; values_in_review: number };
export type Profile = { values: number; batches: string[]; parameters: { parameter: string; units: (string | null)[]; batches: number; values: number }[]; series: ProfileSeries[];
  time_range_h: [number, number] | null; values_in_review: number; conflicting_sample_times: number; verification: 'verified' | 'provisional';
  review: { pending_values?: number; rejected_values?: number; open_issues?: number } | null; delivery_name?: string | null };

/** A task without its operation. `batches: []` means every batch; both ends of the time window are inclusive. */
export type Selection = { site_id: string; dataset_ids: string[]; batches: string[]; parameter: string | null; time_from_h: number | null; time_to_h: number | null;
  align_tolerance_h: number; include_unverified: boolean; limit: number };
export const selectionFor = (siteId: string, from: Partial<Selection> = {}): Selection => ({
  dataset_ids: [...(from.dataset_ids ?? [])], batches: [...(from.batches ?? [])], parameter: from.parameter ?? null,
  time_from_h: from.time_from_h ?? null, time_to_h: from.time_to_h ?? null, align_tolerance_h: from.align_tolerance_h ?? 0,
  include_unverified: !!from.include_unverified, limit: 100, site_id: siteId,
});

export type Location = { path?: string; sheet?: string; row?: number | string; column?: number | string; cell?: string; page?: number | string };
export type MeasurementSource = { evidence_id: string; revision: number; measurement_id?: string; source?: Location | null };
export type Measurement = { dataset_id?: string; batch: string; parameter: string; time_h: number | null; value: number; unit: string | null;
  original_value?: number | string | null; original_unit?: string | null; sources?: MeasurementSource[] };
export type Series = { dataset_id?: string; batch: string; parameter: string; unit: string | null; n: number; min: number; max: number; first_time_h: number; last_time_h: number; points: [number, number][] };
export type ComparisonSummary = { parameter: string; unit: string | null; left_batch: string; right_batch: string; left_dataset_id?: string; right_dataset_id?: string; matched_times: number;
  first_time_h: number; last_time_h: number; mean_difference: number; largest_difference: { time_h: number; difference: number; left_value: number; right_value: number };
  statistics?: { n: number; mean: number; median: number; standard_deviation: number | null; min: number; max: number; root_mean_square: number; share_positive: number; note?: string };
  share_of_samples_matched?: number | null; difference_definition: string };
export type CohortVerdict = 'same' | 'differs' | 'not_recorded';
export type Cohort = { attributes: { attribute: string; label: string; values: Record<string, string | number | null>; verdict: CohortVerdict }[];
  verdict: 'same_context' | 'differs' | 'not_established'; differs: string[]; not_recorded: string[]; meaning: string };
export type Verification = { dataset_id: string; state: 'verified' | 'provisional'; values_still_in_review_used?: number; open_checks?: number | null; rejected_values_excluded?: number | null; meaning?: string };
export type GapStatus = 'required_missing' | 'unavailable' | 'not_yet_known' | 'not_in_selected_data';
export type Gap = { batch?: string; parameter?: string; time_h?: number; document_kind?: string; status: GapStatus; required_by?: string; meaning?: string };
export type DraftRequest = { title: string; description: string; questions?: string[]; status: string; sending?: string };
export type Issue = { code: string; message: string; [key: string]: unknown };
type Measured = { series?: Series[]; measurements?: Measurement[]; measurement_count?: number; series_complete?: boolean; verification?: Verification[] | null; deliveries?: Record<string, string> };
export type CompareData = Measured & { comparison_summary?: ComparisonSummary[]; cohort?: Cohort | null; alignment?: { tolerance_h: number; method: string }; unmatched_counts?: Record<string, number>; limitations?: string[] };
export type GapsData = Measured & { gaps?: Gap[]; gap_count?: number; gaps_truncated?: boolean; expectation_basis?: 'approved_specifications' | 'user_supplied' | 'none';
  requirements_checked?: number; gap_status_counts?: Record<string, number>; coverage?: string; draft_request?: DraftRequest };
export type PictureResult<D> = { task_status: 'completed' | 'needs_information'; summary: string; data: D; issues: Issue[]; evidence_state?: 'verified' | 'provisional' | null; source_refs: SourceRef[] };
export type Timing = { seconds: number; target_seconds: number; within_target: boolean };
/** What the current selection shows. Calculated on every change and never saved. */
export type Picture = { saved: false; results: { reconcile: PictureResult<Measured>; compare: PictureResult<CompareData>; gaps: PictureResult<GapsData> }; timing: Timing };
/** The same three results, saved, so a step, a request, a proposal or an explanation can cite one. */
export type SavedPicture = { results: Partial<Record<'reconcile' | 'compare' | 'gaps', { id: string; summary: string; work_status?: string }>>; problems?: { task: string; issues: unknown[] }[] };
export type SavedIds = { reconcile?: string; compare?: string; gaps?: string };

export type Usage = { identifier: string; used_as?: string; batch_id: string; step_id?: string; performed_at?: string | null };
export type Mention = { kind: string; id: string; label?: string | null; time?: string | null };
export type Trace = { recorded_usage?: Usage[]; recorded_usage_count?: number; affected_batches?: string[]; records?: Mention[];
  genealogy?: { status: string; complete: boolean; batches_without_usage_records: number; note: string }; results_depending_on_these_records?: unknown[];
  limitation?: string; coverage?: string; target_missing?: string | null };

export type ProposableAction = { operation: string; label: string; risk: string; approved_by: string[]; approved_by_words?: string[] };
export type ActionCatalog = { operations: ProposableAction[]; other?: { risk: string; approved_by: string[] }; note: string };
export type Proposal = { proposal_id: string; operation: string; target_id: string; status: string; execution_status: string; required_roles: string[]; risk: string; constraints: string[] };
export type WorkRequest = { id: string; title: string; owner_id: string; status?: string };
export type Explanation = { status: 'completed' | 'withheld' | 'unavailable'; explanation?: string; observations?: string[]; hypotheses?: { statement: string; check: string }[]; unknowns?: string[];
  model?: string | null; timing?: Timing & { model_seconds?: number }; grounding?: string; reason?: string; next_step?: string };

export type StepKind = 'check' | 'request' | 'action' | 'note';
export type PlanStep = { can_complete?: boolean; waiting_on?: 'approval' | 'execution' | 'reply' | null; step_id: string; kind: StepKind; text: string; status: 'open' | 'done' | 'dropped'; basis?: string | null; result_id?: string | null; proposal_id?: string | null;
  work_request_id?: string | null; outcome?: string | null; stands: string;
  proposal?: { operation?: string; target_id?: string; status?: string; execution_status?: string; required_roles?: string[] };
  request?: { title?: string; owner_id?: string; status?: string } };
export type Plan = { id: string; title: string; status: 'open' | 'closed'; revision: number; site_id: string; selection: Partial<Selection>; steps: PlanStep[];
  progress: { open: number; done: number; to_do?: number; waiting_for_approval: number; waiting_for_reply: number }; updated_at: string };
export type PlanSummary = { id: string; title: string; status: string; revision: number; steps: number; open_steps: number; updated_at: string };
export type NewStep = { kind: StepKind; text: string; result_id?: string; basis?: string; proposal_id?: string; work_request_id?: string };

const site = (id: string) => `site_id=${encodeURIComponent(id)}`;
const at = (id: string) => encodeURIComponent(id);
export const listDeliveries = (siteId: string) => processRequest<{ datasets: Dataset[] }>(`/v1/cmo-datasets?${site(siteId)}&include_provisional=true`);
export const deliveryProfile = (id: string, siteId: string) => processRequest<Profile>(`/v1/workspace-tasks/deliveries/${at(id)}/profile?${site(siteId)}`);
export const previewPicture = (selection: Selection) => processRequest<Picture>('/v1/workspace-tasks/templates/batch_picture/preview', { selection });
export const savePicture = (selection: Selection) => processRequest<SavedPicture>('/v1/workspace-tasks/templates/batch_picture/run', { selection });
/** Where one plotted value came from: the same selection narrowed to one batch at one sample time.
 *  A lookup, so it is calculated without saving a result. */
export const valueSource = async (selection: Selection, batch: string, time_h: number) =>
  ((await processRequest<TaskResult>('/v1/workspace-tasks/preview', { ...selection, operation: 'reconcile', batches: [batch], time_from_h: time_h, time_to_h: time_h, limit: 5 })).data.measurements ?? []) as Measurement[];
export const traceIdentifier = (siteId: string, record_id: string) => runTask(emptyTask(siteId, { operation: 'trace_impact', record_id }));
export const suggestCauses = (siteId: string, record_id: string) => runTask(emptyTask(siteId, { operation: 'suggest_causes', record_id }));
export const listActions = () => processRequest<ActionCatalog>('/v1/workspace-tasks/actions');
export const proposeAction = (resultId: string, body: { operation: string; target_id: string; rationale: string; expected_result: string; follow_up_measure?: string }) =>
  processRequest<Proposal>(`/v1/workspace-tasks/results/${at(resultId)}/propose`, body);
export const requestEvidence = (resultId: string, body: { owner_id: string; title?: string; description?: string }) =>
  processRequest<WorkRequest>(`/v1/workspace-tasks/results/${at(resultId)}/request-evidence`, body);
export const explainResult = (resultId: string) => processRequest<Explanation>(`/v1/workspace-tasks/results/${at(resultId)}/explain`, {});
export const listPlans = (siteId: string) => processRequest<{ plans: PlanSummary[] }>(`/v1/work-plans?${site(siteId)}`);
export const getPlan = (id: string) => processRequest<Plan>(`/v1/work-plans/${at(id)}`);
export const createPlan = (siteId: string, title: string, selection: Selection) => processRequest<Plan>('/v1/work-plans', { site_id: siteId, title, selection });
export const updatePlan = (plan: Plan, change: { title?: string; selection?: Selection }) => processRequest<Plan>(`/v1/work-plans/${at(plan.id)}/update`, { expected_revision: plan.revision, ...change });
export const addPlanStep = (plan: Plan, step: NewStep) => processRequest<Plan>(`/v1/work-plans/${at(plan.id)}/steps`, { expected_revision: plan.revision, ...step });
export const updatePlanStep = (plan: Plan, stepId: string, change: { status?: PlanStep['status']; text?: string; outcome?: string }) =>
  processRequest<Plan>(`/v1/work-plans/${at(plan.id)}/steps/${at(stepId)}`, { expected_revision: plan.revision, ...change });
export type { TaskResult };

/* ---- wording: recorded names and numbers as people read them ---- */

/** Four significant figures; floating-point residue (1e-16) reads as zero. */
export const fig = (value: unknown, digits = 4) => typeof value !== 'number' || !Number.isFinite(value) ? '—'
  : Math.abs(value) < 1e-9 ? '0' : String(Number(value.toPrecision(digits)));
export const hours = (value: unknown) => fig(value, 6);
export const withUnit = (value: unknown, unit?: string | null) => `${fig(value)}${unit && typeof value === 'number' ? ` ${unit}` : ''}`;
export const count = (n: number, one: string, many = `${one}s`) => `${n.toLocaleString('en-US')} ${n === 1 ? one : many}`;
export const sentence = (text: string) => text ? text[0].toUpperCase() + text.slice(1) : text;
export const sameName = (a: string, b: string) => a.trim().toLowerCase() === b.trim().toLowerCase();
export const seconds = (value: number) => value < 10 ? `${Number(value.toFixed(2))} s` : `${Math.round(value)} s`;
export const deliveryName = (dataset?: Dataset | null) => dataset?.delivery_name || dataset?.cmo || 'Unnamed delivery';
/** The place in the file a value was read from, without opening the file. */
export function locationText(source?: Location | null) {
  if (!source) return 'Location not recorded';
  const place = source.cell ? [source.sheet ? `sheet ${source.sheet}` : '', `cell ${source.cell}`]
    : [source.sheet ? `sheet ${source.sheet}` : '', source.page != null ? `page ${source.page}` : '', source.row != null ? `row ${source.row}` : '', source.column != null ? `column ${source.column}` : ''];
  return place.filter(Boolean).join(', ') || 'Location not recorded';
}
const ROLES: Record<string, string> = { qa: 'QA', qa_reviewer: 'a QA reviewer', msat: 'MSAT', engineering: 'Engineering', supervisor: 'a supervisor', supply_chain: 'Supply chain' };
export const roles = (ids: string[] = []) => ids.map(id => ROLES[id] ?? id.replaceAll('_', ' ')).join(' and ') || 'an authorized reviewer';
export const actionLabel = (operation: string, catalog?: ActionCatalog | null) =>
  (catalog?.operations.find(item => item.operation === operation)?.label ?? sentence(operation.replaceAll('_', ' '))).replace(/\bcapa\b/i, 'CAPA');
export const STEP_KINDS: Record<StepKind, string> = { check: 'Check', request: 'Request', action: 'Action', note: 'Note' };
export const GAP_STATUS: Record<GapStatus, { title: string; meaning: string }> = {
  required_missing: { title: 'Required and missing', meaning: 'An approved specification requires it, the batch is finished, and no selected delivery holds it.' },
  unavailable: { title: 'Not recorded in any selected delivery', meaning: 'It may be held in a system that is not connected here.' },
  not_yet_known: { title: 'Not yet known', meaning: 'The batch is still in progress, so the value may not exist yet.' },
  not_in_selected_data: { title: 'Expected and not in the selected deliveries', meaning: 'It was listed as expected for this check and is absent from the deliveries in view.' },
};
/** Default name for a plan nobody has named: what is in view. */
export const planTitle = (selection: Selection | null) => !selection?.parameter ? 'Untitled work'
  : `${selection.parameter} · ${selection.batches.length ? selection.batches.join(', ') : 'all batches'}`.slice(0, 160);
