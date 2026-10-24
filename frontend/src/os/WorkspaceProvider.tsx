import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import {
  WORKSPACE_KEY,
  initialWorkspace,
  decodeWorkspace,
  createWork,
  addNote,
  proposeAction,
  transitionAction,
  type WorkspaceData,
  type WorkKind,
  type WorkContext,
  type WorkAction,
  type ActionStatus,
} from "./workspace-model";

function restore() {
  try {
    const raw = localStorage.getItem(WORKSPACE_KEY);
    return {
      data: raw ? decodeWorkspace(raw) : initialWorkspace(),
      issue: "",
      canSave: true,
    };
  } catch {
    return {
      data: initialWorkspace(),
      issue:
        "Saved work could not be read. This session still works; the existing saved data has been left untouched.",
      canSave: false,
    };
  }
}
type Ctx = {
  data: WorkspaceData;
  issue: string;
  create: (goal: string, kind: WorkKind, context: WorkContext) => string;
  note: (workId: string, body: string) => void;
  attachSample: (workId: string) => void;
  propose: (input: Omit<WorkAction, "id" | "status" | "events">) => void;
  transition: (id: string, next: ActionStatus, note: string) => void;
};
const Context = createContext<Ctx | null>(null);
export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [saved, setSaved] = useState(restore);
  useEffect(() => {
    if (!saved.canSave) return;
    try {
      localStorage.setItem(WORKSPACE_KEY, JSON.stringify(saved.data));
    } catch {
      setSaved((s) => ({
        ...s,
        canSave: false,
        issue:
          "Browser storage is unavailable or full. Changes remain in this session. Export your work before leaving.",
      }));
    }
  }, [saved.data, saved.canSave]);
  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key !== WORKSPACE_KEY) return;
      try {
        if (e.newValue)
          setSaved({
            data: decodeWorkspace(e.newValue),
            issue: "",
            canSave: true,
          });
      } catch {
        setSaved((s) => ({
          ...s,
          canSave: false,
          issue:
            "Saved data changed in another tab and could not be read. This session has been retained; export it before leaving.",
        }));
      }
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);
  const update = (fn: (data: WorkspaceData) => WorkspaceData) =>
    setSaved((s) => ({ ...s, data: fn(s.data) }));
  const actor = "Priya Raman (demo)";
  return (
    <Context.Provider
      value={{
        data: saved.data,
        issue: saved.issue,
        create: (goal, kind, context) => {
          const id = crypto.randomUUID();
          const at = new Date().toISOString();
          update((d) => createWork(d, { goal, kind, context }, id, at));
          return id;
        },
        note: (id, body) => {
          const noteId = crypto.randomUUID();
          const at = new Date().toISOString();
          update((d) => addNote(d, id, body, actor, noteId, at));
        },
        attachSample: (workId) => {
          const id = crypto.randomUUID();
          const at = new Date().toISOString();
          update((data) => {
            if (!data.work.some((w) => w.id === workId && w.context === "none"))
              return data;
            const updated = addNote(
              data,
              workId,
              "Attached the F-2408 sample context for exploration. No new analysis has run.",
              actor,
              id,
              at,
            );
            return {
              ...updated,
              work: updated.work.map((w) =>
                w.id === workId ? { ...w, context: "sample" as const } : w,
              ),
            };
          });
        },
        propose: (input) => {
          const id = crypto.randomUUID();
          const at = new Date().toISOString();
          update((d) => proposeAction(d, input, actor, id, at));
        },
        transition: (id, next, note) => {
          const at = new Date().toISOString();
          update((d) => transitionAction(d, id, next, note, actor, at));
        },
      }}
    >
      {children}
    </Context.Provider>
  );
}
export function useWorkspace() {
  const ctx = useContext(Context);
  if (!ctx) throw Error("WorkspaceProvider is required");
  return ctx;
}
export function downloadWork(name: string, value: unknown) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
