import type { WorkContext, WorkKind } from "./workspace-model";

export type WorkEntry = { goal: string; kind: WorkKind; context: WorkContext };
export type Workflow = WorkEntry & {
  id: string;
  title: string;
  area: string;
  description: string;
  output: string;
  group: "understand" | "verify" | "follow";
};
export const workflows: Workflow[] = [
  {
    id: "yield",
    kind: "question",
    context: "sample",
    title: "Understand a change in performance",
    area: "Process understanding",
    description:
      "Bring process signals and lab results into the same question.",
    goal: "What could explain the lower titer in F-2408?",
    output: "Sample evidence, competing explanations and open questions",
    group: "understand",
  },
  {
    id: "compare",
    kind: "comparison",
    context: "sample",
    title: "Compare a batch with its reference",
    area: "Scientific analysis",
    description:
      "Inspect the difference, its calculation and the limits of the comparison.",
    goal: "Compare F-2408 with the six R7 reference batches",
    output: "Existing sample trends and reference data",
    group: "understand",
  },
  {
    id: "coverage",
    kind: "data-review",
    context: "sample",
    title: "Find the gaps in your evidence",
    area: "Data review",
    description:
      "Check what is available, what conflicts, and what is outside the access scope.",
    goal: "Check the source coverage and data gaps for F-2408",
    output: "Source records, missing data and access boundaries",
    group: "verify",
  },
  {
    id: "quality",
    kind: "follow-up",
    context: "sample",
    title: "Prepare a reviewable next step",
    area: "Quality & decisions",
    description:
      "Keep the rationale, responsible role and required review together.",
    goal: "Plan the checks needed before changing the process",
    output: "A local proposal with an owner, constraints and expected evidence",
    group: "follow",
  },
  {
    id: "cleaning",
    kind: "goal",
    context: "none",
    title: "Bring a new question to the workspace",
    area: "Your own context",
    description:
      "Start with the work you need to do. Attach relevant evidence when it is available.",
    goal: "Review cleaning verification for Suite 2",
    output: "A saved draft; authorized context is still needed",
    group: "verify",
  },
  {
    id: "handoff",
    kind: "follow-up",
    context: "sample",
    title: "Keep a follow-up moving",
    area: "Collaboration & continuity",
    description:
      "Record what was reviewed, what happened, and what is still uncertain.",
    goal: "Prepare a reviewable evidence handoff for F-2408",
    output: "Saved notes, action history and a portable work export",
    group: "follow",
  },
];
export const entryExamples = workflows.slice(0, 4);
const PENDING_KEY = "manufacturing-os:pending-entry:v1";
export const emptyEntry = (): WorkEntry => ({
  goal: "",
  kind: "goal",
  context: "sample",
});
export function initialEntry(): WorkEntry {
  const params = new URLSearchParams(location.search);
  const token = params.get("draft");
  if (token) {
    try {
      const saved = JSON.parse(sessionStorage.getItem(PENDING_KEY) || "null");
      if (
        saved?.version === 1 &&
        saved.id === token &&
        typeof saved.goal === "string" &&
        saved.goal.trim() &&
        saved.goal.length <= 1200 &&
        ["goal", "question", "comparison", "data-review", "follow-up"].includes(
          saved.kind,
        ) &&
        ["sample", "none"].includes(saved.context)
      )
        return { goal: saved.goal, kind: saved.kind, context: saved.context };
    } catch {
      /* An unavailable handoff does not block a fresh start. */
    }
  }
  const example = workflows.find((w) => w.kind === params.get("intent"));
  return example
    ? { goal: example.goal, kind: example.kind, context: example.context }
    : emptyEntry();
}
/** Carry an explicit draft between pages without putting the user's text in URLs. */
export function carryEntry(entry: WorkEntry): string {
  const id = crypto.randomUUID();
  if (!entry.goal.trim() || entry.goal.length > 1200)
    throw Error("Enter a goal of up to 1,200 characters.");
  sessionStorage.setItem(
    PENDING_KEY,
    JSON.stringify({ version: 1, id, ...entry, goal: entry.goal.trim() }),
  );
  return `/app?draft=${id}`;
}
export function clearEntry() {
  try {
    sessionStorage.removeItem(PENDING_KEY);
  } catch {
    /* The work itself is managed by WorkspaceProvider. */
  }
  // Keep Back navigation useful after the draft has become durable work.
  const url = new URL(location.href);
  if (url.searchParams.has("draft")) {
    url.searchParams.delete("draft");
    history.replaceState(null, "", url);
  }
}
