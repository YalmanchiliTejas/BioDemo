import { processRequest } from './process-api';
import type { Signal } from './signals-api';

export type Ref = { kind: string; id: string; revision: number; site_id?: string };
export type Fields = Record<string, any>;
export type Source = { ref: Ref; state: Fields; current_revision: number; url: string };
export type Assignee = { actor_id: string; label: string; roles: string[]; eligible_owner: boolean; eligible_qa_reviewer: boolean };
export type AdoptionContext = {assignment_issues?: string[]; case: Fields; signals: Signal[]; discovery_refs: Ref[]; local_only: true};
export type QualityWorkspace = {
  case: Fields; revision: number; workflow: Fields; sources: Source[]; timeline: Fields[];
  hypotheses: Fields[]; science: Fields; assessment: Fields; impact: Fields;
  requests: Fields[]; actions: Fields[]; reviews: Fields[]; activity: Fields[];
  allowed_actions: string[]; completeness: { complete: boolean; missing: string[]; gaps: Fields[]; source_drift: Fields[]; submission_drift: boolean };
  local_only: true; external_status: string;
};
export type Original = { ref: Ref; state: Fields; content_text?: string; content_base64?: string; original_base64?: string; snapshot_path?: string; snapshot_sha256?: string; source_coordinate?: unknown };
const root = '/v1/quality/workspaces';
export const qualityPath = (id: string) => `${root}/${encodeURIComponent(id)}`;
export const listQuality = () => processRequest<{items: QualityWorkspace[]}>(root);
export const getQuality = (id: string) => processRequest<QualityWorkspace>(qualityPath(id));
export const getAdoptionContext = (id: string) => processRequest<AdoptionContext>(`${qualityPath(id)}/adoption-context`);
export const qualityAssignees = (site: string) => processRequest<{items: Assignee[]}>(`${root}/assignees?site_id=${encodeURIComponent(site)}`);
// Keep the same request/key after a transport failure. A revision change is a new intent.
const pending = new Map<string, string>();
export async function qualityMutation(path: string, body: unknown, intentKey?: string): Promise<QualityWorkspace> {
  const intent = JSON.stringify([path, body]);
  let key = intentKey ?? pending.get(intent);
  try { key ??= sessionStorage.getItem(`quality-intent:${intent}`) ?? undefined; } catch { /* Memory fallback. */ }
  key ??= crypto.randomUUID(); pending.set(intent, key);
  try { sessionStorage.setItem(`quality-intent:${intent}`, key); } catch { /* Memory fallback. */ }
  const result = await processRequest<QualityWorkspace>(path, body, key);
  pending.delete(intent);
  try { sessionStorage.removeItem(`quality-intent:${intent}`); } catch { /* Storage unavailable. */ }
  return result;
}
export const createQuality = (body: Fields, intentKey?: string) => qualityMutation(root, body, intentKey);
export const updateQuality = (workspace: QualityWorkspace, operation: string, fields: Fields = {}) => qualityMutation(`${qualityPath(workspace.case.case_id)}/${operation}`, {expected_revision: workspace.revision, ...fields});
