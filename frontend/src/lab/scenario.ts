// Illustrative fixture. Every value, person, record and connector response here is
// invented for the interaction study and must never be presented as plant data.

export type System = "Historian" | "LIMS" | "MES" | "QMS";
export type Stance = "supports" | "contradicts" | "missing";
export type Point = [x: number, y: number | null];

export const NOW = { label: "09:42", day: "Thursday 22 October", batchAge: 49.7 };

export const batch = {
  id: "F-2408",
  vessel: "BR-04",
  recipe: "R7",
  product: "Recombinant enzyme, fed-batch",
  started: "Tue 20 Oct, 08:00",
  references: ["F-2377", "F-2381", "F-2385", "F-2391", "F-2396", "F-2402"],
};

export const people = {
  you: { name: "Priya Raman", role: "Process engineering", initials: "PR" },
  qa: { name: "Daniel Okafor", role: "Quality assurance" },
};

export type Connector = {
  id: string;
  system: System;
  label: string;
  scope: string;
  access: "read" | "draft";
  lastSync: string;
  status: "simulated";
};

export const connectors: Connector[] = [
  { id: "hist", system: "Historian", label: "Plant historian", scope: "214 tags · BR-01 to BR-06", access: "read", lastSync: "09:41", status: "simulated" },
  { id: "lims", system: "LIMS", label: "Laboratory results", scope: "Fermentation assays · seed train", access: "read", lastSync: "09:30", status: "simulated" },
  { id: "mes", system: "MES", label: "Batch records", scope: "Executed records · work orders", access: "read", lastSync: "09:38", status: "simulated" },
  { id: "qms", system: "QMS", label: "Quality events", scope: "Draft events only · human submits", access: "draft", lastSync: "09:12", status: "simulated" },
];

// Offline titer assay, sampled every 12 h. Reference envelope = min/max of six prior R7 batches.
export const titerHours = [0, 12, 24, 36, 48, 60, 72];
export const titer = {
  mean: [0.1, 0.42, 0.98, 1.57, 2.12, 2.6, 3.05],
  min: [0.09, 0.38, 0.91, 1.45, 1.98, 2.43, 2.86],
  max: [0.11, 0.46, 1.05, 1.69, 2.27, 2.77, 3.24],
  current: [0.1, 0.41, 0.95, 1.33, 1.74] as number[],
  posted60: 2.16,
};

const range = (a: number, b: number, step: number) => {
  const out: number[] = [];
  for (let x = a; x <= b + 1e-9; x += step) out.push(+x.toFixed(2));
  return out;
};
export const onlineHours = range(0, 48, 2);

// Dissolved oxygen, % air saturation. Cascade setpoint 40 %.
const doRef = (h: number) => (h < 18 ? 100 - (60 * h) / 18 : 40);
const doCur = (h: number) => (h <= 26 ? doRef(h) : 40 - (15 * (h - 26)) / 22);
export const dissolvedO2 = {
  setpoint: 40,
  mean: onlineHours.map((h) => +doRef(h).toFixed(1)),
  min: onlineHours.map((h) => +(doRef(h) - (h < 18 ? 3 : 2)).toFixed(1)),
  max: onlineHours.map((h) => +(doRef(h) + (h < 18 ? 3 : 3)).toFixed(1)),
  current: onlineHours.map((h) => +doCur(h).toFixed(1)),
};

// Agitation, rpm. Cascade upper limit 800 rpm.
const agRef = (h: number) => (h < 14 ? 300 : 300 + (h - 14) * 9.5);
const agCur = (h: number) => (h < 14 ? 300 : h < 22 ? 300 + (h - 14) * 9.5 : Math.min(800, 376 + (h - 22) * 85));
export const agitation = {
  limit: 800,
  mean: onlineHours.map((h) => Math.round(agRef(h))),
  current: onlineHours.map((h) => Math.round(agCur(h))),
};

// Cumulative antifoam, mL.
const afRef = (h: number) => Math.max(0, (h - 6) * 2.85);
const afCur = (h: number) => (h < 22 ? afRef(h) : afRef(22) + (h - 22) * 10.7);
export const antifoam = {
  mean: onlineHours.map((h) => Math.round(afRef(h))),
  current: onlineHours.map((h) => Math.round(afCur(h))),
};

export const offGasGap: [number, number] = [31, 44];

export const zip = (xs: number[], ys: (number | null)[]): Point[] => xs.map((x, i) => [x, ys[i] ?? null]);

export type Evidence = {
  id: string;
  stance: Stance;
  hypothesis: "H1" | "H2" | "H3";
  claim: string;
  detail: string;
  weight: "strong" | "moderate" | "weak";
  system: System;
  ref: string;
  location: string;
  retrieved: string;
  query: string;
  columns: string[];
  rows: (string | number)[][];
  limit: string;
  request?: string;
};

export const evidence: Evidence[] = [
  {
    id: "S1",
    stance: "supports",
    hypothesis: "H1",
    claim: "Dissolved oxygen fell below its 40 % setpoint at 27 h and reached 25 % by 48 h",
    detail: "All six reference batches held DO between 38 and 43 % after 18 h.",
    weight: "strong",
    system: "Historian",
    ref: "BR04.DO.PV",
    location: "1-min interpolated · 18–48 h",
    retrieved: "09:41",
    query: "SELECT avg(value) FROM BR04.DO.PV WHERE batch='F-2408' GROUP BY 6h",
    columns: ["Batch age", "F-2408", "Reference mean", "Reference range"],
    rows: [
      ["24 h", "40.0 %", "40.0 %", "38–43 %"],
      ["30 h", "37.3 %", "40.0 %", "38–43 %"],
      ["36 h", "33.2 %", "40.0 %", "38–43 %"],
      ["42 h", "29.1 %", "40.0 %", "38–43 %"],
      ["48 h", "25.0 %", "40.0 %", "38–43 %"],
    ],
    limit: "Shows DO fell. It does not establish why. One probe; no independent second measurement.",
  },
  {
    id: "S2",
    stance: "supports",
    hypothesis: "H1",
    claim: "Agitation reached its 800 rpm cascade limit at 27 h, the same hour DO started falling",
    detail: "References peaked between 560 and 650 rpm. A saturated cascade means the controller had no more capacity to add oxygen.",
    weight: "moderate",
    system: "Historian",
    ref: "BR04.SIC-110.OUT",
    location: "Controller output · 14–48 h",
    retrieved: "09:41",
    query: "SELECT max(value) FROM BR04.SIC-110.OUT WHERE batch IN (F-2408, refs) GROUP BY batch",
    columns: ["Batch", "Peak agitation", "Hours at limit"],
    rows: [
      ["F-2408", "800 rpm", "≈ 22 h"],
      ["Reference max", "650 rpm", "0 h"],
      ["Reference min", "560 rpm", "0 h"],
    ],
    limit: "Independent of the DO probe, so it weakens probe drift. Aeration rate is not visible to the agent, so total oxygen supply is incomplete.",
  },
  {
    id: "S3",
    stance: "supports",
    hypothesis: "H1",
    claim: "Antifoam use was 2.7× the reference after a foam alarm at 22 h",
    detail: "Silicone antifoam is known to reduce oxygen transfer (kLa). Dosing rose sharply after the alarm.",
    weight: "moderate",
    system: "MES",
    ref: "Batch record F-2408 · step 4.3",
    location: "Executed record · foam alarm acknowledgement",
    retrieved: "09:38",
    query: "GET /batch-records/F-2408/steps/4.3 ; Historian BR04.AF.TOT",
    columns: ["Source", "Entry", "Value"],
    rows: [
      ["MES step 4.3", "Foam alarm acknowledged", "22:04 h · operator J.T."],
      ["Historian BR04.AF.TOT", "Cumulative antifoam at 48 h", "324 mL"],
      ["Reference mean", "Cumulative antifoam at 48 h", "120 mL"],
    ],
    limit: "Mechanism is plausible, not demonstrated. The size of the kLa effect for this antifoam lot is not in any connected record.",
  },
  {
    id: "C1",
    stance: "contradicts",
    hypothesis: "H1",
    claim: "F-2391 ran at 30 % DO for 10 hours and finished with normal titer",
    detail: "A comparable low-DO period did not reduce output in that batch, so low DO alone may not explain an 18 % gap.",
    weight: "moderate",
    system: "LIMS",
    ref: "F-2391 · final titer assay",
    location: "LIMS result 7 · Historian BR04.DO.PV (Aug)",
    retrieved: "09:39",
    query: "Precedent search: reference batches with DO < 32 % for > 6 h",
    columns: ["Batch", "Low-DO duration", "Titer at 48 h", "vs mean"],
    rows: [
      ["F-2391", "10 h at ≈30 %", "2.08 g/L", "−2 %"],
      ["F-2408", "21 h, now 25 %", "1.74 g/L", "−18 %"],
    ],
    limit: "F-2391's low-DO period was shorter and shallower. It weakens, but does not rule out, oxygen limitation.",
  },
  {
    id: "C2",
    stance: "contradicts",
    hypothesis: "H2",
    claim: "Inoculum viability was 94 %, below the 97–99 % seen in reference seed trains",
    detail: "Points to a second possible contributor. It is still within the 90 % specification.",
    weight: "weak",
    system: "LIMS",
    ref: "Seed train S-2408-3 · viability",
    location: "LIMS result 2 · transfer sample",
    retrieved: "09:30",
    query: "GET /lims/samples?lot=S-2408-3&test=viability",
    columns: ["Seed train", "Viability", "Specification"],
    rows: [
      ["S-2408-3 (F-2408)", "94 %", "≥ 90 %"],
      ["Reference range", "97–99 %", "≥ 90 %"],
    ],
    limit: "Early growth (0–24 h) matched the reference, which argues against a weak start.",
  },
  {
    id: "M1",
    stance: "missing",
    hypothesis: "H1",
    claim: "Off-gas analysis is missing from 31 h to 44 h",
    detail: "The analyser was offline for planned maintenance. Off-gas oxygen uptake would directly test whether the culture was oxygen-limited.",
    weight: "strong",
    system: "MES",
    ref: "Work order WO-5531",
    location: "Analyser AN-02 · maintenance window",
    retrieved: "09:38",
    query: "Historian BR04.OUR.PV returned no values 31.0–44.2 h; MES WO-5531 explains gap",
    columns: ["Window", "Status", "Reason"],
    rows: [
      ["0–31 h", "Available", "—"],
      ["31–44 h", "No data", "WO-5531 planned maintenance"],
      ["44–49 h", "Available", "—"],
    ],
    limit: "The agent will not interpolate across this gap. Raw analyser logs may exist on the local instrument.",
    request: "Ask automation for the analyser's local log export",
  },
  {
    id: "M2",
    stance: "missing",
    hypothesis: "H1",
    claim: "Inlet airflow (BR04.FIC-201) is outside the agent's authorised scope",
    detail: "Without airflow, the agent cannot tell whether aeration was also limited or only agitation.",
    weight: "moderate",
    system: "Historian",
    ref: "BR04.FIC-201",
    location: "Connector scope policy",
    retrieved: "09:41",
    query: "403 · tag not in connector allow-list",
    columns: ["Tag", "Status"],
    rows: [["BR04.FIC-201", "Not authorised for this connector"]],
    limit: "Access is a customer decision. The agent has not attempted any workaround.",
    request: "Request read access from the connector administrator",
  },
  {
    id: "M3",
    stance: "missing",
    hypothesis: "H1",
    claim: "The 60 h titer sample is not due until 20:00",
    detail: "It will show whether the gap is still widening, holding or closing.",
    weight: "moderate",
    system: "LIMS",
    ref: "Sample F-2408-60h",
    location: "Sampling schedule",
    retrieved: "09:30",
    query: "GET /lims/schedule?batch=F-2408",
    columns: ["Sample", "Scheduled", "Status"],
    rows: [["F-2408-60h", "20:00 today", "Not yet taken"]],
    limit: "Scheduled, not overdue. The agent will check it when it posts.",
  },
];

export const checked = [
  { label: "Temperature", value: "30.0 °C", note: "within ±0.2 °C of recipe" },
  { label: "pH", value: "6.80", note: "within ±0.05 of recipe" },
  { label: "Feed rate", value: "as programmed", note: "MES step 5, no manual override" },
  { label: "DO probe calibration", value: "passed", note: "CAL-082, 3 days before start" },
];

export type Hypothesis = {
  id: "H1" | "H2" | "H3";
  title: string;
  status: "Leading" | "Possible" | "Unlikely";
  confidence: 1 | 2 | 3;
  summary: string;
  wouldChange: string;
};

export const hypotheses: Hypothesis[] = [
  {
    id: "H1",
    title: "Oxygen transfer fell after heavy antifoam dosing",
    status: "Leading",
    confidence: 2,
    summary: "DO dropped when agitation hit its limit, soon after antifoam use rose sharply. F-2391 suggests low DO alone may not explain the full gap.",
    wouldChange: "Off-gas data for 31–44 h, or a portable DO check that disagrees with the probe.",
  },
  {
    id: "H2",
    title: "A weaker inoculum is limiting productivity",
    status: "Possible",
    confidence: 1,
    summary: "Seed viability was lower than usual but within specification. Growth matched the reference for the first 24 h.",
    wouldChange: "A late productivity drop in other batches from lower-viability seed trains.",
  },
  {
    id: "H3",
    title: "The DO probe is drifting",
    status: "Unlikely",
    confidence: 1,
    summary: "Calibration passed 3 days before start, and agitation saturation is independent of the probe.",
    wouldChange: "A portable DO reading well above 25 %.",
  },
];

export const action = {
  title: "Verify oxygen transfer before changing anything",
  why: "The leading explanation is plausible but not confirmed, and two inputs that would test it directly are missing.",
  target: { system: "QMS" as System, record: "EV-2026-0418", type: "Process performance event · minor", state: "Draft, not submitted" },
  steps: [
    { id: "a1", text: "Take a portable DO reading on BR-04 at the 12:00 sample", owner: "Shift process engineer", due: "Today 12:00" },
    { id: "a2", text: "Export analyser AN-02 local logs for 31–44 h", owner: "Automation", due: "Today 16:00" },
    { id: "a3", text: "Grant read access to BR04.FIC-201 for this connector", owner: "Connector administrator", due: "Fri 23 Oct" },
  ],
  notProposed: "No changes to agitation, aeration, antifoam or feed setpoints. Those go through change control.",
  followUp: "Re-assess when the 60 h titer posts (≈20:00). Alert you if the gap exceeds 20 % or DO stays below 30 % for 4 more hours.",
  approvals: ["You · Process engineering", "Daniel Okafor · QA, in QMS"],
};

export const responsibilities = [
  { id: "r1", title: "Watching BR-04 fermentation", meta: "F-2408 · checks every 15 min", status: "attention" as const, note: "1 finding" },
  { id: "r2", title: "Cleaning verification, Suite 2", meta: "Due tomorrow 07:00", status: "ready" as const, note: "Ready for your review" },
  { id: "r3", title: "Pending LIMS assays", meta: "3 samples across BR-02, BR-04", status: "waiting" as const, note: "Next result ≈ 11:30" },
  { id: "r4", title: "CAPA-0112 effectiveness check", meta: "Media hold-time change", status: "quiet" as const, note: "No relevant batches since 14 Oct" },
];

export const earlier = [
  { time: "08:15", text: "Prepared the Suite 2 cleaning verification. No discrepancies in 3 records." },
  { time: "07:02", text: "Summarised night-shift handover for BR-02, BR-04 and BR-05." },
  { time: "06:30", text: "Compared F-2408 seed train with 6 references. Viability lower, in specification." },
  { time: "05:50", text: "Drafted the BR-03 harvest record for the 11:00 harvest." },
];

export type Vessel = {
  id: string;
  batch: string | null;
  recipe: string | null;
  age: number | null; // h
  runLength: number | null; // planned h
  samples: number[];
  state: string;
  flagged?: boolean;
};

/** The floor: six vessels on one 0–120 h run axis. */
export const RUN_AXIS = 120;
export const vessels: Vessel[] = [
  { id: "BR-01", batch: null, recipe: null, age: null, runLength: null, samples: [], state: "CIP complete 06:10" },
  { id: "BR-02", batch: "F-2406", recipe: "R7", age: 70.3, runLength: 96, samples: [0, 12, 24, 36, 48, 60], state: "On reference" },
  { id: "BR-03", batch: "F-2405", recipe: "R5", age: 94.1, runLength: 96, samples: [0, 12, 24, 36, 48, 60, 72, 84], state: "Harvest 11:00" },
  { id: "BR-04", batch: "F-2408", recipe: "R7", age: 49.7, runLength: 96, samples: [0, 12, 24, 36, 48], state: "18 % below reference", flagged: true },
  { id: "BR-05", batch: "F-2409", recipe: "R7", age: 12.4, runLength: 96, samples: [0, 12], state: "On reference" },
  { id: "BR-06", batch: null, recipe: null, age: null, runLength: null, samples: [], state: "Seed transfer 14:00" },
];

// ── Familiar views: work queue, lab results, events, batch phases ──

export type QueueItem = {
  id: string;
  priority: "High" | "Medium" | "Low";
  title: string;
  unit: string;
  batch: string;
  source: System | "Assistant";
  due: string;
  status: string;
  assistant?: "finding" | "prepared";
};

export const workQueue: QueueItem[] = [
  { id: "q1", priority: "High", title: "Titer below reference range", unit: "BR-04", batch: "F-2408", source: "Assistant", due: "Today", status: "New", assistant: "finding" },
  { id: "q2", priority: "Medium", title: "Approve harvest record", unit: "BR-03", batch: "F-2405", source: "MES", due: "11:00", status: "Ready", assistant: "prepared" },
  { id: "q3", priority: "Medium", title: "Review 72 h lab results", unit: "BR-02", batch: "F-2406", source: "LIMS", due: "11:30", status: "Waiting on lab" },
  { id: "q4", priority: "Medium", title: "Sign off cleaning verification", unit: "Suite 2", batch: "", source: "MES", due: "Tomorrow 07:00", status: "Ready", assistant: "prepared" },
  { id: "q5", priority: "Low", title: "Seed transfer checklist", unit: "BR-06", batch: "F-2410", source: "MES", due: "14:00", status: "Not started" },
  { id: "q6", priority: "Low", title: "CAPA-0112 effectiveness check", unit: "", batch: "", source: "QMS", due: "30 Oct", status: "Open" },
];

export const batchRecord = {
  product: "Recombinant enzyme",
  recipe: "R7 v3",
  unit: "BR-04 · 2,000 L",
  started: "Tue 20 Oct 08:00",
  phase: "Fed-batch",
  status: "In progress",
  phases: [
    { name: "Inoculation", from: 0, to: 2 },
    { name: "Batch", from: 2, to: 18 },
    { name: "Fed-batch", from: 18, to: 84 },
    { name: "Harvest", from: 84, to: 96 },
  ],
};

export type LabResult = { sample: string; age: number | null; test: string; result: number | null; unit: string; lo: number; hi: number; status: "Within range" | "Below range" | "Pending" };
export const labResults: LabResult[] = [
  { sample: "S-2408-3", age: null, test: "Seed viability", result: 94, unit: "%", lo: 90, hi: 100, status: "Within range" },
  { sample: "F-2408-00h", age: 0, test: "Titer", result: 0.1, unit: "g/L", lo: 0.09, hi: 0.11, status: "Within range" },
  { sample: "F-2408-12h", age: 12, test: "Titer", result: 0.41, unit: "g/L", lo: 0.38, hi: 0.46, status: "Within range" },
  { sample: "F-2408-24h", age: 24, test: "Titer", result: 0.95, unit: "g/L", lo: 0.91, hi: 1.05, status: "Within range" },
  { sample: "F-2408-36h", age: 36, test: "Titer", result: 1.33, unit: "g/L", lo: 1.45, hi: 1.69, status: "Below range" },
  { sample: "F-2408-48h", age: 48, test: "Titer", result: 1.74, unit: "g/L", lo: 1.98, hi: 2.27, status: "Below range" },
  { sample: "F-2408-60h", age: 60, test: "Titer", result: null, unit: "g/L", lo: 2.43, hi: 2.77, status: "Pending" },
];

export type BatchEvent = { age: number; clock: string; kind: "Alarm" | "Event" | "Operator" | "Maintenance"; text: string; source: System; tag?: string };
export const events: BatchEvent[] = [
  { age: 0, clock: "Tue 08:00", kind: "Event", text: "Inoculation complete", source: "MES" },
  { age: 18, clock: "Wed 02:00", kind: "Event", text: "DO reached 40 % setpoint, cascade active", source: "Historian", tag: "BR04.DO.PV" },
  { age: 18, clock: "Wed 02:00", kind: "Event", text: "Feed started, programmed profile", source: "MES" },
  { age: 22.1, clock: "Wed 06:06", kind: "Alarm", text: "Foam high", source: "Historian", tag: "BR04.LSH-120" },
  { age: 22.1, clock: "Wed 06:07", kind: "Operator", text: "Foam alarm acknowledged, antifoam dosing on demand", source: "MES" },
  { age: 27, clock: "Wed 11:00", kind: "Alarm", text: "Agitation at cascade limit, 800 rpm", source: "Historian", tag: "BR04.SIC-110" },
  { age: 31, clock: "Wed 15:00", kind: "Maintenance", text: "Off-gas analyser AN-02 offline, WO-5531", source: "MES" },
  { age: 40.7, clock: "Thu 00:42", kind: "Event", text: "DO below 30 % air saturation", source: "Historian", tag: "BR04.DO.PV" },
  { age: 44.2, clock: "Thu 04:12", kind: "Maintenance", text: "Off-gas analyser AN-02 back online", source: "MES" },
];

export const agentSteps = [
  "Comparing F-2408 titer with 6 prior R7 batches",
  "Reading DO, agitation and antifoam from the historian",
  "Checking batch record and calibration history",
  "Searching for precedents with similar DO behaviour",
];
