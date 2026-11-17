/** Everything waiting on the signed-in person, read in one request. Each decision still goes to the service that owns it. */
import { processRequest } from './process-api';

export type Decide = { type: 'decide'; proposal_id: string; revision: number; roles: string[]; recent_sign_in: boolean };
export type Reply = { type: 'reply'; request_id: string; revision: number };
export type Answer = { type: 'answer'; conversation_id: string; revision: number; questions: string[] };
export type Acknowledge = { type: 'acknowledge'; signal_id: string };
/** A request drafted from a delivery's missing evidence. Sending it is the person's own act. */
export type SendRequest = { type: 'send_request'; result_id: string; title: string; description: string };
export type ProposalFacts = { action: string; target: string; system?: string | null; rationale: string; expected_result: string; follow_up_measure?: string | null;
  constraints: string[]; risk: string; approvers: string; proposed_by: string; rests_on: string;
  /** The host's own account of the result the proposal cites. The result itself is private to its author. */ result_says?: string | null };
export type WorkItem = { id: string; kind: 'approval' | 'proposal' | 'request' | 'question' | 'assistant' | 'signal' | 'quality' | 'delivery' | 'missing_evidence';
  title: string; detail: string; by: string; at: string | null; href: string | null; action: Decide | Reply | Answer | Acknowledge | SendRequest | null;
  severity?: string; proposal?: ProposalFacts };
export type Group = 'needs_you' | 'in_progress' | 'done';
export type Worklist = { site_id: string; as_of: string; done_since: string; needs_you: WorkItem[]; in_progress: WorkItem[]; done: WorkItem[];
  counts: Record<Group, number>; covers: string[]; not_covered: string[]; unavailable: { source: string; covers: string }[] };
export type Person = { id: string; label: string };

const at = encodeURIComponent;
export const getWorklist = (siteId: string) => processRequest<Worklist>(`/v1/worklist?site_id=${at(siteId)}`);
export const listPeople = (siteId: string) => processRequest<{ people: Person[] }>(`/v1/worklist/people?site_id=${at(siteId)}`).then(r => r.people);
/** Records this person's decision on exactly the revision they were shown. Approval is not execution. */
export const decideProposal = (action: Decide, decision: 'approved' | 'rejected', comment: string) =>
  processRequest<unknown>(`/v1/proposals/${at(action.proposal_id)}/decisions`, { expected_revision: action.revision, decision, role: action.roles[0], comment: comment || null });
export const sendDraftedRequest = (action: SendRequest, body: { owner_id: string; title: string; description: string }) =>
  processRequest<{ id: string; owner_id: string }>(`/v1/workspace-tasks/results/${at(action.result_id)}/request-evidence`, body);
export const answerRequest = (action: Reply, reply: string) =>
  processRequest<unknown>(`/v1/work-requests/${at(action.request_id)}/answer`, { expected_revision: action.revision, reply });
/** An answer to the assistant's question is the next message in that conversation; the assistant then continues. */
export const answerAssistant = (action: Answer, text: string) =>
  processRequest<unknown>(`/v1/process-model/conversations/${at(action.conversation_id)}/messages`, { text, expected_revision: action.revision });

/** "3 h ago", "2 d ago"; the exact time stays available as a tooltip. */
export function ago(iso: string | null, now = Date.now()): string {
  const then = iso ? new Date(iso).getTime() : NaN;
  if (Number.isNaN(then)) return '';
  const minutes = Math.max(0, Math.round((now - then) / 60000));
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes} min ago`;
  if (minutes < 60 * 24) return `${Math.round(minutes / 60)} h ago`;
  return `${Math.round(minutes / (60 * 24))} d ago`;
}

/** The one line above the list. It never says nothing is waiting when part of the list could not be read. */
export function headline(list: Pick<Worklist, 'counts' | 'unavailable'>): string {
  const n = list.counts.needs_you;
  if (n) return `${n} ${n === 1 ? 'thing needs' : 'things need'} you`;
  return list.unavailable.length ? 'Nothing found that needs you, but part of the list could not be read' : 'Nothing needs you right now';
}
