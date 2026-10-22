export const FDA_RECALL_URL: string;
export function elapsedDays(start: string, end: string): number;
export function unaddressedCount(lots: { shipped: string; projected: string }[], time: string, escalation: string, projected: boolean): number;
export function lotDays(lots: { shipped: string; projected: string }[], escalation: string, projected: boolean): number;
