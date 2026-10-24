import { createContext, useCallback, useContext, useEffect, useMemo, useReducer, useState, type ReactNode } from "react";
import { agentSteps } from "./scenario";

export type Stage = "notice" | "open" | "inspect" | "review" | "follow";
export const stages: { id: Stage; label: string }[] = [
  { id: "notice", label: "Notice" },
  { id: "open", label: "Open" },
  { id: "inspect", label: "Inspect" },
  { id: "review", label: "Review" },
  { id: "follow", label: "Follow up" },
];

export type Receipt = { decision: "sent" | "declined"; note: string; at: string; steps: string[] };

type State = {
  step: number; // agent detection progress; agentSteps.length = finding surfaced
  reached: Stage[];
  assayPosted: boolean;
  receipt: Receipt | null;
  requested: string[];
  snoozed: boolean;
};

type Action =
  | { type: "tick" }
  | { type: "reach"; stage: Stage }
  | { type: "assay"; value: boolean }
  | { type: "receipt"; receipt: Receipt | null }
  | { type: "request"; id: string }
  | { type: "snooze"; value: boolean }
  | { type: "reset"; instant: boolean };

const initial = (instant: boolean): State => ({
  step: instant ? agentSteps.length : 0,
  reached: instant ? ["notice"] : [],
  assayPosted: false,
  receipt: null,
  requested: [],
  snoozed: false,
});

function reducer(s: State, a: Action): State {
  switch (a.type) {
    case "tick": {
      const step = Math.min(agentSteps.length, s.step + 1);
      return { ...s, step, reached: step === agentSteps.length && !s.reached.includes("notice") ? ["notice"] : s.reached };
    }
    case "reach":
      return s.reached.includes(a.stage) ? s : { ...s, reached: [...s.reached, a.stage] };
    case "assay":
      return { ...s, assayPosted: a.value };
    case "receipt":
      return { ...s, receipt: a.receipt, reached: a.receipt && !s.reached.includes("follow") ? [...s.reached, "follow"] : s.reached };
    case "request":
      return s.requested.includes(a.id) ? s : { ...s, requested: [...s.requested, a.id] };
    case "snooze":
      return { ...s, snoozed: a.value };
    case "reset":
      return initial(a.instant);
  }
}

// ?instant skips the agent's detection sequence, for inspection and screenshots.
const reduceMotion = () =>
  (typeof location !== "undefined" && new URLSearchParams(location.search).has("instant")) ||
  (typeof matchMedia !== "undefined" && matchMedia("(prefers-reduced-motion: reduce)").matches);

type Ctx = State & {
  storageIssue: string;
  detecting: boolean;
  reach: (s: Stage) => void;
  setAssay: (v: boolean) => void;
  setReceipt: (r: Receipt | null) => void;
  request: (id: string) => void;
  snooze: (v: boolean) => void;
  replay: () => void;
};
const ScenarioContext = createContext<Ctx | null>(null);

export function ScenarioProvider({ children, persistKey }: { children: ReactNode; persistKey?: string }) {
  const [restored] = useState(() => {
    const fallback = initial(reduceMotion());
    if (!persistKey) return { state: fallback, issue: "", writable: true };
    try {
      const raw = localStorage.getItem(persistKey);
      if (!raw) return { state: fallback, issue: "", writable: true };
      const saved = JSON.parse(raw);
      const value = saved?.state;
      const validReceipt = value?.receipt === null || (value?.receipt && ["sent", "declined"].includes(value.receipt.decision) && typeof value.receipt.note === "string" && typeof value.receipt.at === "string" && Array.isArray(value.receipt.steps) && value.receipt.steps.every((s: unknown) => typeof s === "string"));
      if (saved?.version !== 1 || !value || !Number.isInteger(value.step) || value.step < 0 || value.step > agentSteps.length || !Array.isArray(value.reached) || !value.reached.every((s: unknown) => stages.some(stage => stage.id === s)) || typeof value.assayPosted !== "boolean" || !validReceipt || !Array.isArray(value.requested) || !value.requested.every((s: unknown) => typeof s === "string") || typeof value.snoozed !== "boolean") throw Error("Invalid sample state");
      return { state: value as State, issue: "", writable: true };
    } catch {
      return { state: fallback, issue: "Sample review history could not be restored. The saved copy is unchanged; new sample reviews will only last for this session.", writable: false };
    }
  });
  const [state, dispatch] = useReducer(reducer, restored.state);
  const [storageIssue, setStorageIssue] = useState(restored.issue);
  useEffect(() => {
    if (!persistKey || !restored.writable || storageIssue) return;
    try { localStorage.setItem(persistKey, JSON.stringify({ version: 1, state })); }
    catch { setStorageIssue("Sample review history could not be saved. New sample review changes will only last for this session."); }
  }, [state, persistKey, restored.writable, storageIssue]);
  const detecting = state.step < agentSteps.length;

  useEffect(() => {
    if (!detecting) return;
    const t = setTimeout(() => dispatch({ type: "tick" }), state.step === 0 ? 500 : 700);
    return () => clearTimeout(t);
  }, [detecting, state.step]);

  const reach = useCallback((stage: Stage) => dispatch({ type: "reach", stage }), []);
  const value = useMemo<Ctx>(
    () => ({
      ...state,
      storageIssue,
      detecting,
      reach,
      setAssay: (v) => dispatch({ type: "assay", value: v }),
      setReceipt: (r) => dispatch({ type: "receipt", receipt: r }),
      request: (id) => dispatch({ type: "request", id }),
      snooze: (v) => dispatch({ type: "snooze", value: v }),
      replay: () => dispatch({ type: "reset", instant: reduceMotion() }),
    }),
    [state, detecting, reach, storageIssue],
  );
  return <ScenarioContext.Provider value={value}>{children}</ScenarioContext.Provider>;
}

export function useScenario() {
  const ctx = useContext(ScenarioContext);
  if (!ctx) throw new Error("useScenario outside ScenarioProvider");
  return ctx;
}
