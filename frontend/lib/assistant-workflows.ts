import { processRequest } from './process-api';

export type TaskOperation = 'find_records' | 'select_evidence' | 'reconcile' | 'compare' | 'check_gaps' | 'trace_impact' | 'prepare_review' | 'review_changes' | 'suggest_causes';
export type SourceRef = { kind: string; id: string; revision: number; site_id?: string; label?: string; [key: string]: unknown };
export type TaskSpec = {
  operation: TaskOperation; site_id: string; query: string; kinds: string[]; record_refs: SourceRef[];
  dataset_ids: string[]; series: { dataset_id: string; batch: string }[]; batches: string[]; parameter: string | null; target_unit: string | null;
  expected_parameters: string[]; expected_document_kinds: string[]; expected_times: number[];
  process_stage: string | null; effective_at: string | null; record_id: string | null; record_kind: string | null; limit: number;
  time_from_h?: number | null; time_to_h?: number | null; align_tolerance_h?: number;
  offset: number; include_unverified: boolean; use_decision_model: boolean;
};
export type TaskTiming = { phases: Record<string, number>; seconds: number; target_seconds: number; within_target: boolean; includes?: string };
/** One call to the optional decision model: what it answered and whether the host used each answer. */
export type TaskDecision = { task: string; status: 'completed' | 'fallback'; reason: string; model: string | null; policy_version: string; run_id: string | null; latency_ms: number | null;
  answers: { question: string; about?: string; status: 'accepted' | 'advisory' | 'flagged'; value: unknown; probability: number | null; reason: string }[] };
// Results saved before timing and decisions were recorded omit those fields.
export type TaskResult = { id: string; operation: TaskOperation; task_status: 'completed' | 'needs_information'; site_id: string; owner_id: string;
  summary: string; data: Record<string, unknown>; issues: { code: string; message: string; [key: string]: unknown }[];
  source_refs: SourceRef[]; elapsed_seconds: number; model_calls: number; status: 'current' | 'stale' | 'quarantined'; task?: TaskSpec;
  timing?: TaskTiming; evidence_state?: 'verified' | 'provisional'; decision_model_calls?: number; decisions?: TaskDecision[]; template_version?: string };
export type TaskCatalog = { id: TaskOperation; title: string; description: string; requires_dataset: boolean }[];
export type DecisionModel = { enabled: boolean; model?: string | null; calibrated_tasks?: Record<string, { model: string; threshold: number; eval_id: string; held_out_n: number }>; acceptance?: string; configuration_issue?: string | null };
export type TaskCatalogResponse = { operations: TaskCatalog; template_version?: string; decision_model?: DecisionModel };
export type SuggestedTask = Pick<TaskSpec, 'operation' | 'dataset_ids' | 'parameter' | 'batches'>;
/** Whether typed words are exactly one routine task (`direct`) or need the assistant. Routing runs nothing. */
export type TaskRoute = { route: 'direct' | 'assistant'; basis: 'host_rules' | 'decision_model'; task: TaskSpec | null; suggested_task: SuggestedTask | null;
  reason: string; decisions: TaskDecision[]; timing?: TaskTiming };
export type RoutineTrigger = 'case' | 'evidence' | 'batch' | 'sample' | 'deviation' | 'alarm' | 'team_request';
export type RoutineDefinition = { name: string; description: string; task: TaskSpec; triggers: RoutineTrigger[]; every_minutes: number | null; max_runs: number };
export type AssistantRoutine = RoutineDefinition & { id: string; revision: number; site_id: string; status: 'draft' | 'active' | 'paused';
  runs_admitted: number; thread_id: string; updated_at: string; latest_result?: TaskResult | null; runs?: Record<string, unknown>[] };
export type TaskContext = { label: string; task: Partial<TaskSpec> };
export const TRIGGERS: [RoutineTrigger, string][] = [['case', 'Deviation cases'], ['evidence', 'New or corrected evidence'], ['batch', 'Batch changes'], ['sample', 'Sample changes'], ['deviation', 'Early warnings and deviations'], ['alarm', 'Alarms'], ['team_request', 'Team requests']];
export const emptyTask = (siteId: string, context: Partial<TaskSpec> = {}): TaskSpec => ({
  operation: 'find_records', query: '', kinds: [], record_refs: [], dataset_ids: [], series: [], batches: [], parameter: null,
  target_unit: null, expected_parameters: [], expected_document_kinds: [], expected_times: [], process_stage: null,
  effective_at: null, record_id: null, record_kind: null, limit: 50, offset: 0, include_unverified: false, use_decision_model: true,
  ...context, site_id: siteId,
});
export const getTaskCatalog = () => processRequest<TaskCatalogResponse>('/v1/workspace-tasks/catalog');
export const routeRequest = (siteId: string, text: string, datasetIds: string[], includeUnverified = false) => processRequest<TaskRoute>('/v1/workspace-tasks/route', { site_id: siteId, text, dataset_ids: datasetIds, include_unverified: includeUnverified });
export const runTask = (task: TaskSpec) => processRequest<TaskResult>('/v1/workspace-tasks/run', task);
export const getTaskResult = (id: string) => processRequest<TaskResult>(`/v1/workspace-tasks/results/${encodeURIComponent(id)}`);
export const getRoutines = (siteId: string) => processRequest<{ routines: AssistantRoutine[] }>(`/v1/assistant-routines?site_id=${encodeURIComponent(siteId)}`);
export const getRoutine = (id: string) => processRequest<AssistantRoutine>(`/v1/assistant-routines/${encodeURIComponent(id)}`);
export const saveRoutine = (definition: RoutineDefinition, existing?: AssistantRoutine) => processRequest<AssistantRoutine>(
  existing ? `/v1/assistant-routines/${encodeURIComponent(existing.id)}/update` : '/v1/assistant-routines',
  { ...definition, ...(existing ? { expected_revision: existing.revision } : {}) });
export const activateRoutine = (routine: AssistantRoutine) => processRequest<AssistantRoutine>(`/v1/assistant-routines/${encodeURIComponent(routine.id)}/activate`, { expected_revision: routine.revision, acknowledge_inference: true });
export const pauseRoutine = (routine: AssistantRoutine) => processRequest<AssistantRoutine>(`/v1/assistant-routines/${encodeURIComponent(routine.id)}/pause`, { expected_revision: routine.revision });
export const runRoutine = (id: string, task: TaskSpec) => {
  const { operation: _operation, site_id: _site, ...parameters } = task;
  return processRequest<TaskResult>(`/v1/assistant-routines/${encodeURIComponent(id)}/run`, { parameters });
};
