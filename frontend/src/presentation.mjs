// Presentation calculations preserve the frozen records and their assumed dates.
export const FDA_RECALL_URL = "https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/fresenius-kabi-issues-voluntary-nationwide-recall-three-lots-famotidine-injection-usp-20-mg-2-ml-10";
export const elapsedDays = (start, end) => Math.max(0, (Date.parse(end) - Date.parse(start)) / 864e5);
export const unaddressedCount = (lots, time, escalation, projected) => lots.filter(lot =>
  lot.shipped <= time && time < escalation && (!projected || lot.projected !== "held")
).length;
export const lotDays = (lots, escalation, projected) => lots.reduce((sum, lot) =>
  sum + (projected && lot.projected === "held" ? 0 : elapsedDays(lot.shipped, escalation)), 0);
