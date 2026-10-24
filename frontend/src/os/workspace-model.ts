/** Browser-local demo model. It never represents authorization in a source system. */
export type WorkKind =
  "goal" | "question" | "comparison" | "data-review" | "follow-up";
export type WorkContext = "sample" | "none";
export type WorkItem = {
  id: string;
  goal: string;
  kind: WorkKind;
  context: WorkContext;
  createdAt: string;
  updatedAt: string;
  notes: WorkNote[];
};
export type WorkNote = { id: string; body: string; at: string; author: string };
export type ActionStatus =
  "proposed" | "reviewed" | "in_progress" | "outcome_recorded";
export type ActionEvent = {
  status: ActionStatus;
  at: string;
  actor: string;
  note: string;
};
export type WorkAction = {
  id: string;
  workId: string;
  title: string;
  owner: string;
  rationale: string;
  expected: string;
  constraint: string;
  evidenceIds: string[];
  status: ActionStatus;
  events: ActionEvent[];
};
export type WorkspaceData = {
  version: 1;
  work: WorkItem[];
  actions: WorkAction[];
};
export const WORKSPACE_KEY = "manufacturing-os:workspace:v1";
export const SAMPLE_ID = "sample-f2408";
export const kindLabel: Record<WorkKind, string> = {
  goal: "Goal",
  question: "Question",
  comparison: "Comparison",
  "data-review": "Data review",
  "follow-up": "Follow-up",
};
export const actionLabel: Record<ActionStatus, string> = {
  proposed: "Proposed",
  reviewed: "Reviewed locally",
  in_progress: "In progress",
  outcome_recorded: "Outcome recorded",
};
export function initialWorkspace(): WorkspaceData {
  return {
    version: 1,
    work: [
      {
        id: SAMPLE_ID,
        goal: "Understand the lower titer in F-2408",
        kind: "question",
        context: "sample",
        createdAt: "2026-10-22T09:42:00-07:00",
        updatedAt: "2026-10-22T09:42:00-07:00",
        notes: [],
      },
    ],
    actions: [],
  };
}
const record = (value: unknown): value is Record<string, unknown> =>
  !!value && typeof value === "object" && !Array.isArray(value);
const str = (value: unknown): value is string => typeof value === "string";
const timestamp = (value: unknown): value is string =>
  str(value) && Number.isFinite(Date.parse(value));
const strings = (value: unknown): value is string[] =>
  Array.isArray(value) && value.every(str);
const kinds = ["goal", "question", "comparison", "data-review", "follow-up"];
const statuses = ["proposed", "reviewed", "in_progress", "outcome_recorded"];
export function decodeWorkspace(raw: string): WorkspaceData {
  const data: unknown = JSON.parse(raw);
  if (
    !record(data) ||
    data.version !== 1 ||
    !Array.isArray(data.work) ||
    !Array.isArray(data.actions)
  )
    throw Error("Unsupported saved workspace format");
  for (const w of data.work) {
    if (
      !record(w) ||
      !str(w.id) ||
      !str(w.goal) ||
      !w.goal.trim() ||
      !kinds.includes(String(w.kind)) ||
      !["sample", "none"].includes(String(w.context)) ||
      !timestamp(w.createdAt) ||
      !timestamp(w.updatedAt) ||
      !Array.isArray(w.notes)
    )
      throw Error("Invalid saved work");
    for (const n of w.notes)
      if (
        !record(n) ||
        !str(n.id) ||
        !str(n.body) ||
        !str(n.author) ||
        !timestamp(n.at)
      )
        throw Error("Invalid saved note");
  }
  const workIds = new Set(data.work.map((w) => w.id));
  if (workIds.size !== data.work.length)
    throw Error("Duplicate work identifiers");
  for (const a of data.actions) {
    if (
      !record(a) ||
      !str(a.id) ||
      !str(a.workId) ||
      !workIds.has(a.workId) ||
      ![a.title, a.owner, a.rationale, a.expected, a.constraint].every(str) ||
      !strings(a.evidenceIds) ||
      !statuses.includes(String(a.status)) ||
      !Array.isArray(a.events) ||
      !a.events.length
    )
      throw Error("Invalid saved action");
    for (const e of a.events)
      if (
        !record(e) ||
        !statuses.includes(String(e.status)) ||
        !timestamp(e.at) ||
        !str(e.actor) ||
        !str(e.note)
      )
        throw Error("Invalid action history");
    if (a.events[a.events.length - 1].status !== a.status)
      throw Error("Action history does not match its status");
  }
  if (new Set(data.actions.map((a) => a.id)).size !== data.actions.length)
    throw Error("Duplicate action identifiers");
  return data as WorkspaceData;
}
export function createWork(
  data: WorkspaceData,
  input: { goal: string; kind: WorkKind; context: WorkContext },
  id: string,
  at: string,
): WorkspaceData {
  const goal = input.goal.trim();
  if (
    !goal ||
    goal.length > 1200 ||
    !kinds.includes(input.kind) ||
    !["sample", "none"].includes(input.context) ||
    data.work.some((w) => w.id === id)
  )
    throw Error(
      "Provide a goal of 1 to 1,200 characters and a unique identifier.",
    );
  return {
    ...data,
    work: [
      { ...input, goal, id, createdAt: at, updatedAt: at, notes: [] },
      ...data.work,
    ],
  };
}
export function addNote(
  data: WorkspaceData,
  workId: string,
  body: string,
  actor: string,
  id: string,
  at: string,
): WorkspaceData {
  if (
    !body.trim() ||
    !actor.trim() ||
    body.length > 4000 ||
    !data.work.some((w) => w.id === workId)
  )
    throw Error("A work item, author and note are required.");
  return {
    ...data,
    work: data.work.map((w) =>
      w.id === workId
        ? {
            ...w,
            updatedAt: at,
            notes: [...w.notes, { id, body: body.trim(), author: actor, at }],
          }
        : w,
    ),
  };
}
export function proposeAction(
  data: WorkspaceData,
  input: Omit<WorkAction, "id" | "status" | "events">,
  actor: string,
  id: string,
  at: string,
): WorkspaceData {
  if (
    !data.work.some((w) => w.id === input.workId) ||
    data.actions.some((a) => a.id === id) ||
    ![
      input.title,
      input.owner,
      input.rationale,
      input.expected,
      input.constraint,
      actor,
    ].every((s) => s.trim())
  )
    throw Error(
      "Complete the action, owner, rationale, expected result and constraints.",
    );
  return {
    ...data,
    actions: [
      ...data.actions,
      {
        ...input,
        id,
        status: "proposed",
        events: [
          {
            status: "proposed",
            at,
            actor,
            note: "Proposal recorded; no action authorized or executed.",
          },
        ],
      },
    ],
  };
}
export function transitionAction(
  data: WorkspaceData,
  id: string,
  next: ActionStatus,
  note: string,
  actor: string,
  at: string,
): WorkspaceData {
  const action = data.actions.find((a) => a.id === id);
  const allowed: Partial<Record<ActionStatus, ActionStatus>> = {
    proposed: "reviewed",
    reviewed: "in_progress",
    in_progress: "outcome_recorded",
  };
  if (
    !action ||
    allowed[action.status] !== next ||
    !note.trim() ||
    !actor.trim()
  )
    throw Error("A valid next status, reviewer and explanation are required.");
  return {
    ...data,
    actions: data.actions.map((a) =>
      a.id === id
        ? {
            ...a,
            status: next,
            events: [
              ...a.events,
              { status: next, note: note.trim(), actor, at },
            ],
          }
        : a,
    ),
  };
}
