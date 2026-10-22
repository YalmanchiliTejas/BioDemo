import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { Command } from "cmdk";
import {
  RiBarChart2Line,
  RiCheckLine,
  RiCloseLine,
  RiErrorWarningLine,
  RiFileList3Line,
  RiFlaskLine,
  RiInboxLine,
  RiLineChartLine,
  RiMenuLine,
  RiPlugLine,
  RiRobot2Line,
  RiSearchLine,
  RiStackLine,
} from "@remixicon/react";
import { connectors, people, workQueue } from "./scenario";
import { useScenario } from "./state";
import { AgentMark, Kbd, ProductMark, Sheet, SimNote, SourceRef, cx } from "./ui";

type LabUI = { openConnectors: () => void; toast: (msg: string) => void };
const LabUIContext = createContext<LabUI>({ openConnectors: () => {}, toast: () => {} });
export const useLabUI = () => useContext(LabUIContext);

export function LabUIProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const toast = useCallback((m: string) => setMsg(m), []);
  useEffect(() => {
    if (!msg) return;
    const t = setTimeout(() => setMsg(null), 4200);
    return () => clearTimeout(t);
  }, [msg]);
  return (
    <LabUIContext.Provider value={{ openConnectors: () => setOpen(true), toast }}>
      {children}
      <ConnectorsSheet open={open} onOpenChange={setOpen} />
      <div className="lab toast-region" role="status" aria-live="polite">
        {msg && <div className="toast">{msg}</div>}
      </div>
    </LabUIContext.Provider>
  );
}

function ConnectorsSheet({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange} title="Connected sources" description="Your existing systems stay where they are. The Assistant reads them inside this scope." width={520}>
      <div className="rows">
        {connectors.map((c) => (
          <div key={c.id} className="row conn">
            <div className="conn-main">
              <b>{c.label}</b>
              <span>
                <SourceRef system={c.system} /> · {c.scope}
              </span>
            </div>
            <div className="conn-side">
              <span>{c.access === "read" ? "Read only" : "Drafts only, cannot submit"}</span>
              <span className="num">synced {c.lastSync}</span>
            </div>
            <SimNote />
          </div>
        ))}
      </div>
      <div className="runtime">
        <RiRobot2Line size={16} />
        <div>
          <b>Prime Agent runtime: not connected</b>
          <p>Assistant activity here is scripted. In production, investigations run through the existing FastAPI service and the Prime Agent harness, and this list comes from /api/connectors.</p>
        </div>
      </div>
      <p className="conn-foot">
        <RiCheckLine size={14} /> Nothing is uploaded or migrated. The Assistant cannot change a source record.
      </p>
    </Sheet>
  );
}

export type NavId = "queue" | "batches" | "trends" | "lab" | "events" | "deviations" | "sources" | (string & {});
export type NavGroup = { group: string; items: { id: string; label: string; icon: ReactNode; count?: number; note?: string }[] };
const defaultNav: NavGroup[] = [
  { group: "My work", items: [{ id: "queue", label: "Work queue", icon: <RiInboxLine size={16} /> }] },
  {
    group: "Production",
    items: [
      { id: "batches", label: "Batches", icon: <RiStackLine size={16} /> },
      { id: "trends", label: "Trends", icon: <RiLineChartLine size={16} /> },
      { id: "events", label: "Events and alarms", icon: <RiErrorWarningLine size={16} /> },
    ],
  },
  {
    group: "Quality",
    items: [
      { id: "lab", label: "Lab results", icon: <RiFlaskLine size={16} /> },
      { id: "deviations", label: "Deviations", icon: <RiFileList3Line size={16} /> },
    ],
  },
];

export type ShellCommand = { id: string; label: string; group: string; icon?: ReactNode; run: () => void };

export function Shell({
  current,
  title,
  onNavigate,
  nav = defaultNav,
  commands = [],
  assistantOpen,
  onAssistant,
  assistant,
  children,
}: {
  current: string;
  title: string;
  onNavigate: (id: NavId) => void;
  nav?: NavGroup[];
  commands?: ShellCommand[];
  assistantOpen?: boolean;
  onAssistant?: () => void;
  assistant?: ReactNode;
  children: ReactNode;
}) {
  const { openConnectors } = useLabUI();
  const s = useScenario();
  const [menu, setMenu] = useState(false);
  const [search, setSearch] = useState(false);
  const open = workQueue.length - (s.receipt ? 1 : 0) - (s.detecting ? 1 : 0);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setSearch((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const go = (id: string) => {
    setMenu(false);
    if (id === "sources") openConnectors();
    else onNavigate(id as NavId);
  };

  return (
    <div className={cx("frame", assistant && assistantOpen ? "has-assistant" : false)}>
      <header className="topbar">
        <button type="button" className="icon-btn phone-only" aria-label="Open menu" aria-expanded={menu} onClick={() => setMenu(true)}>
          <RiMenuLine size={18} />
        </button>
        <span className="brand">
          <ProductMark size={20} />
          <b>Manufacturing OS</b>
        </span>
        <span className="site desk-only">Northfield · Upstream</span>
        <span className="phone-title phone-only">{title}</span>
        <button type="button" className="search" onClick={() => setSearch(true)}>
          <RiSearchLine size={15} />
          <span className="desk-only">Search batches, tags, samples</span>
          <Kbd>⌘K</Kbd>
        </button>
        <span className="topbar-right">
          {onAssistant && (
            <button type="button" className={cx("assistant-btn", assistantOpen && "is-on")} aria-label={assistantOpen ? "Close assistant" : "Open assistant"} aria-pressed={assistantOpen} onClick={onAssistant}>
              <AgentMark size={15} working={s.detecting} />
              <span className="desk-only">Assistant</span>
            </button>
          )}
          <span className="avatar" title={`${people.you.name} · ${people.you.role}`}>
            {people.you.initials}
          </span>
        </span>
      </header>

      <nav className={cx("sidebar", menu && "open")} aria-label="Manufacturing OS">
        <div className="sidebar-phone-head phone-only">
          <b>Menu</b>
          <button type="button" className="icon-btn" aria-label="Close menu" onClick={() => setMenu(false)}>
            <RiCloseLine size={18} />
          </button>
        </div>
        {nav.map((g) => (
          <div key={g.group} className="nav-group">
            <p className="group-label">{g.group}</p>
            {g.items.map((it) => (
              <button key={it.id} type="button" className="nav-item" aria-current={current === it.id ? "page" : undefined} onClick={() => go(it.id)}>
                {it.icon}
                <span className="nav-label">
                  {it.label}
                  {it.note && <small>{it.note}</small>}
                </span>
                {it.id === "queue" && it.count == null && <span className="nav-count num">{open}</span>}
                {it.count != null && <span className="nav-count num">{it.count}</span>}
              </button>
            ))}
          </div>
        ))}
        <div className="nav-group nav-bottom">
          <button type="button" className="nav-item" onClick={() => go("sources")}>
            <RiPlugLine size={16} /> Connected sources
          </button>
        </div>
      </nav>

      <main className="sheet-page" id="work">
        {children}
      </main>

      {assistant && assistantOpen && <aside className="assistant" aria-label="Assistant">{assistant}</aside>}

      <footer className="statusbar">
        <span className="status-sources">
          {connectors.map((c) => (
            <span key={c.id}>
              <i className="ok" aria-hidden="true" />
              {c.system}
            </span>
          ))}
          <span className="sim">simulated</span>
        </span>
        <span className="desk-only">Last sync 09:41</span>
        <span className="status-assistant">
          <AgentMark size={12} working={s.detecting} />
          {s.detecting ? "Assistant checking BR-04" : "Assistant watching BR-02, BR-04, BR-05"}
        </span>
        <span className="desk-only status-right">Demo environment</span>
      </footer>

      <Command.Dialog open={search} onOpenChange={setSearch} label="Search" className="palette" contentClassName="lab palette-content" overlayClassName="lab sheet-overlay">
        <div className="palette-input">
          <RiSearchLine size={16} />
          <Command.Input placeholder="Search batches, tags, samples, or ask the Assistant" />
          <Kbd>Esc</Kbd>
        </div>
        <Command.List>
          <Command.Empty>No match in this prototype. Try F-2408, BR-04 or DO.</Command.Empty>
          {[...new Set(commands.map((c) => c.group))].map((g) => (
            <Command.Group key={g} heading={g}>
              {commands
                .filter((c) => c.group === g)
                .map((c) => (
                  <Command.Item
                    key={c.id}
                    value={c.label}
                    onSelect={() => {
                      setSearch(false);
                      c.run();
                    }}
                  >
                    {c.icon ?? <RiBarChart2Line size={16} />} {c.label}
                  </Command.Item>
                ))}
            </Command.Group>
          ))}
          <Command.Group heading="Workspace">
            <Command.Item
              onSelect={() => {
                setSearch(false);
                openConnectors();
              }}
            >
              <RiPlugLine size={16} /> Connected sources
            </Command.Item>
          </Command.Group>
        </Command.List>
      </Command.Dialog>
    </div>
  );
}

/** The one line that explains the one new thing. Dismissed for the session. */
export function WhatsNew({ id, children }: { id: string; children: ReactNode }) {
  const [hidden, setHidden] = useState(() => sessionStorage.getItem(`lab-new-${id}`) === "1");
  if (hidden) return null;
  return (
    <div className="whatsnew" role="note">
      <AgentMark size={14} />
      <p>{children}</p>
      <button
        type="button"
        className="btn btn-ghost btn-sm"
        onClick={() => {
          sessionStorage.setItem(`lab-new-${id}`, "1");
          setHidden(true);
        }}
      >
        Got it
      </button>
    </div>
  );
}
