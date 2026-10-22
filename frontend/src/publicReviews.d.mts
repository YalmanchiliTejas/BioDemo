export type EditorialObservation = {text: string; match: string};
export type ReviewSection = {experiment?: string; observations: EditorialObservation[]; notes?: string[]; supplementalCase?: string; hypotheses: string[]; tasks: string[]};
export type PublicReview = {hash: string | null; summary: string; sections: ReviewSection[]; rerun: string; quarantine?: boolean};
export const publicReviews: Record<string, PublicReview>;
export function reviewedCase(caseId: string, outputHash: string | null): PublicReview | null;
export function supportingIds(report: {observed_facts?: {statement: string; evidence_ids?: string[]}[]; hypotheses?: {statement: string; supporting_evidence_ids?: string[]}[]}, observation: EditorialObservation): string[];
