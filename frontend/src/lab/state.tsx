import { createContext, useCallback, useContext, useEffect, useMemo, useReducer, type ReactNode } from "react";
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
  detecting: boolean;
  reach: (s: Stage) => void;
  setAssay: (v: boolean) => void;
  setReceipt: (r: Receipt | null) => void;
  request: (id: string) => void;
  snooze: (v: boolean) => void;
  replay: () => void;
};
const ScenarioContext = createContext<Ctx | null>(null);

export function ScenarioProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, reduceMotion(), initial);
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
      detecting,
      reach,
      setAssay: (v) => dispatch({ type: "assay", value: v }),
      setReceipt: (r) => dispatch({ type: "receipt", receipt: r }),
      request: (id) => dispatch({ type: "request", id }),
      snooze: (v) => dispatch({ type: "snooze", value: v }),
      replay: () => dispatch({ type: "reset", instant: reduceMotion() }),
    }),
    [state, detecting, reach],
  );
  return <ScenarioContext.Provider value={value}>{children}</ScenarioContext.Provider>;
}

export function useScenario() {
  const ctx = useContext(ScenarioContext);
  if (!ctx) throw new Error("useScenario outside ScenarioProvider");
  return ctx;
}
