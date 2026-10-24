import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  createClient,
  errorMessage,
  newIdempotencyKey,
  type ApiClient,
  type EvidenceRecord,
  type Health,
  type Me,
  type Mission,
  type Proposal,
} from "./client";
import {
  loadConnection,
  saveConnection,
  sampleConnection,
  type Connection,
} from "./connection";
import { evidenceTitles } from "./mapping";

export type ConnectionStatus = "sample" | "connecting" | "ready" | "error";
type LoadState = "idle" | "loading" | "ready" | "error";

type Ctx = {
  /** True only when the user chose connected mode. Sample mode never touches the network. */
  active: boolean;
  connection: Connection;
  /** Set when stored connection settings were unreadable; they were not overwritten. */
  storedProblem: boolean;
  status: ConnectionStatus;
  error: string;
  me: Me | null;
  health: Health | null;
  client: ApiClient | null;
  missions: Mission[];
  missionsState: LoadState;
  missionsError: string;
  refreshMissions: () => Promise<void>;
  createMission: (objective: string, constraints: string[], key?: string) => Promise<Mission>;
  evidence: EvidenceRecord[];
  evidenceState: LoadState;
  evidenceError: string;
  evidenceTitles: Record<string, string>;
  loadEvidence: (force?: boolean) => Promise<void>;
  connect: (tenant: string, actor: string) => Promise<Me>;
  disconnect: () => void;
  retry: () => void;
};

const Context = createContext<Ctx | null>(null);
const HEALTH_POLL_MS = 30_000;
const STREAM_POLL_MS = 5_000;
const FULL_REFRESH_EVERY = 6;

export function ConnectedProvider({ children }: { children: ReactNode }) {
  const [initial] = useState(loadConnection);
  const [connection, setConnection] = useState<Connection>(initial.connection);
  const [storedProblem, setStoredProblem] = useState(initial.corrupt);
  const [status, setStatus] = useState<ConnectionStatus>(
    initial.connection.mode === "connected" ? "connecting" : "sample",
  );
  const [error, setError] = useState("");
  const [me, setMe] = useState<Me | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [missions, setMissions] = useState<Mission[]>([]);
  const [missionsState, setMissionsState] = useState<LoadState>("idle");
  const [missionsError, setMissionsError] = useState("");
  const [evidence, setEvidence] = useState<EvidenceRecord[]>([]);
  const [evidenceState, setEvidenceState] = useState<LoadState>("idle");
  const [evidenceError, setEvidenceError] = useState("");
  const [attempt, setAttempt] = useState(0);

  const active = connection.mode === "connected";
  const client = useMemo(
    () =>
      active
        ? createClient({ tenant: connection.tenant, actor: connection.actor })
        : null,
    [active, connection.tenant, connection.actor],
  );

  useEffect(() => {
    setMe(null);
    setHealth(null);
    setMissions([]);
    setMissionsState("idle");
    setEvidence([]);
    setEvidenceState("idle");
    if (!client) {
      setStatus("sample");
      setError("");
      return;
    }
    let alive = true;
    setStatus("connecting");
    setError("");
    client.health().then(
      (h) => alive && setHealth(h),
      () => undefined,
    );
    client.me().then(
      (m) => {
        if (!alive) return;
        setMe(m);
        setStatus("ready");
      },
      (e) => {
        if (!alive) return;
        setError(errorMessage(e));
        setStatus("error");
      },
    );
    const timer = window.setInterval(() => {
      client.health().then(
        (h) => alive && setHealth(h),
        () => undefined,
      );
    }, HEALTH_POLL_MS);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [client, attempt]);

  const refreshMissions = useCallback(async () => {
    if (!client) return;
    setMissionsState((s) => (s === "ready" ? s : "loading"));
    try {
      const items = await client.listMissions();
      setMissions(items);
      setMissionsState("ready");
      setMissionsError("");
    } catch (e) {
      setMissionsError(errorMessage(e));
      setMissionsState("error");
    }
  }, [client]);

  const evidenceStateRef = useRef<LoadState>("idle");
  evidenceStateRef.current = evidenceState;
  const titles = useMemo(() => evidenceTitles(evidence), [evidence]);
  const loadEvidence = useCallback(
    async (force = false) => {
      if (!client) return;
      const now = evidenceStateRef.current;
      if (!force && (now === "ready" || now === "loading")) return;
      setEvidenceState("loading");
      try {
        const all: EvidenceRecord[] = [];
        let cursor: string | undefined;
        for (let page = 0; page < 5; page += 1) {
          const result = await client.listEvidence(200, cursor);
          all.push(...result.items);
          if (!result.next_cursor) break;
          cursor = result.next_cursor;
        }
        setEvidence(all);
        setEvidenceState("ready");
        setEvidenceError("");
      } catch (e) {
        setEvidenceError(errorMessage(e));
        setEvidenceState("error");
      }
    },
    [client],
  );

  const value: Ctx = {
    active,
    connection,
    storedProblem,
    status,
    error,
    me,
    health,
    client,
    missions,
    missionsState,
    missionsError,
    refreshMissions,
    createMission: async (objective, constraints, key) => {
      if (!client || !me) throw new Error("Connect to a server first.");
      const mission = await client.createMission(
        {
          objective: objective.trim(),
          owner_id: me.actor_id,
          scope: { site_ids: me.site_ids },
          ...(constraints.length ? { constraints } : {}),
        },
        key ?? newIdempotencyKey(),
      );
      await refreshMissions();
      return mission;
    },
    evidence,
    evidenceState,
    evidenceError,
    evidenceTitles: titles,
    loadEvidence,
    connect: async (tenant, actor) => {
      const next = createClient({ tenant, actor });
      const identity = await next.me();
      const chosen: Connection = { mode: "connected", tenant, actor };
      saveConnection(chosen);
      setStoredProblem(false);
      setConnection(chosen);
      return identity;
    },
    disconnect: () => {
      const back: Connection = { ...sampleConnection(), tenant: connection.tenant, actor: connection.actor };
      saveConnection(back);
      setConnection(back);
    },
    retry: () => setAttempt((n) => n + 1),
  };
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useConnected() {
  const ctx = useContext(Context);
  if (!ctx) throw Error("ConnectedProvider is required");
  return ctx;
}

type OpenMission = {
  mission: Mission | null;
  proposals: Proposal[];
  phase: "loading" | "ready" | "error";
  error: string;
  /** Set when background refresh failed; shown data may be out of date. */
  liveError: string;
  reload: () => Promise<void>;
};

/**
 * Loads one mission with its proposals and keeps it current: polls the mission stream
 * from the last cursor every 5 s and reloads proposals when events arrive. The stream
 * only carries events that name the mission, so proposals are also re-read periodically.
 */
export function useOpenMission(id: string): OpenMission {
  const { client, status } = useConnected();
  const [mission, setMission] = useState<Mission | null>(null);
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [phase, setPhase] = useState<OpenMission["phase"]>("loading");
  const [error, setError] = useState("");
  const [liveError, setLiveError] = useState("");
  const cursor = useRef(0);
  const busy = useRef(false);
  const generation = useRef(0);

  const sync = useCallback(
    async (withProposals: boolean, initialLoad = false) => {
      if (!client || busy.current) return;
      busy.current = true;
      const mine = generation.current;
      try {
        const streamed = await client.stream(id, cursor.current);
        const items =
          withProposals || streamed.events.length ? await client.listProposals(id) : null;
        if (mine !== generation.current) return;
        cursor.current = streamed.cursor;
        setMission(streamed.snapshot);
        if (items) setProposals(items);
        setPhase("ready");
        setError("");
        setLiveError("");
      } catch (e) {
        if (mine !== generation.current) return;
        if (initialLoad) {
          setError(errorMessage(e));
          setPhase("error");
        } else {
          setLiveError(errorMessage(e));
        }
      } finally {
        if (mine === generation.current) busy.current = false;
      }
    },
    [client, id],
  );

  useEffect(() => {
    generation.current += 1;
    cursor.current = 0;
    busy.current = false;
    setMission(null);
    setProposals([]);
    setError("");
    setLiveError("");
    if (!client || status !== "ready") {
      setPhase(status === "error" ? "error" : "loading");
      if (status === "error") setError("The server connection is not available.");
      return;
    }
    setPhase("loading");
    void sync(true, true);
    let tick = 0;
    const timer = window.setInterval(() => {
      if (document.hidden) return;
      tick += 1;
      void sync(tick % FULL_REFRESH_EVERY === 0);
    }, STREAM_POLL_MS);
    return () => {
      generation.current += 1;
      window.clearInterval(timer);
    };
  }, [client, status, id, sync]);

  const reload = useCallback(async () => {
    for (let i = 0; i < 30 && busy.current; i += 1) {
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
    await sync(true);
  }, [sync]);

  return { mission, proposals, phase, error, liveError, reload };
}

/**
 * Keeps one idempotency key per distinct request body, so a retry after a network
 * failure reuses the key (no duplicate record) while an edited form gets a fresh one.
 */
export function useAttemptKey() {
  const current = useRef<{ body: string; key: string } | null>(null);
  return {
    keyFor(body: unknown) {
      const json = JSON.stringify(body);
      if (!current.current || current.current.body !== json) {
        current.current = { body: json, key: newIdempotencyKey() };
      }
      return current.current.key;
    },
    done() {
      current.current = null;
    },
  };
}
