import { useEffect, useRef, useState, type ReactNode } from "react";
import { Command } from "cmdk";
import * as Dialog from "@radix-ui/react-dialog";
import {
  RiArrowRightSLine,
  RiCloseLine,
  RiHome5Line,
  RiInboxLine,
  RiMenuLine,
  RiSearchLine,
  RiStackLine,
  RiTaskLine,
  RiPlugLine,
  RiAddLine,
} from "@remixicon/react";
import { AgentMark, Kbd, ProductMark } from "../lab/ui";
import { useScenario } from "../lab/state";
import { useWorkspace, downloadWork } from "./WorkspaceProvider";
import { useConnected } from "./api/ConnectedWorkspace";
import { ConnectionSheet } from "./api/ConnectionSheet";
import { authLabel, initials } from "./api/mapping";

export type View =
  | "home"
  | "work"
  | "item"
  | "queue"
  | "record"
  | "actions"
  | "sources"
  | "historian"
  | "lims"
  | "mes"
  | "qms";
export const viewName: Record<View, string> = {
  home: "Workspace",
  work: "Saved work",
  item: "Work details",
  queue: "Work queue",
  record: "Batch F-2408",
  actions: "Actions",
  sources: "Sources",
  historian: "PlantView Historian",
  lims: "LabWare LIMS",
  mes: "Syncade MES",
  qms: "QualityTrack QMS",
};
const links = [
  { id: "home" as View, label: "Workspace", icon: RiHome5Line },
  { id: "work" as View, label: "Saved work", icon: RiStackLine },
  { id: "queue" as View, label: "Work queue", icon: RiInboxLine },
  { id: "actions" as View, label: "Actions", icon: RiTaskLine },
  { id: "sources" as View, label: "Sources", icon: RiPlugLine },
];
export function WorkspaceShell({
  view,
  go,
  openWork,
  onNewWork,
  children,
  assistant,
  onAssistant,
  assistantOpen,
}: {
  view: View;
  go: (v: View) => void;
  openWork: (id: string) => void;
  onNewWork: () => void;
  children: ReactNode;
  assistant: ReactNode;
  onAssistant: () => void;
  assistantOpen: boolean;
}) {
  const [menu, setMenu] = useState(false);
  const menuTrigger = useRef<HTMLButtonElement>(null);
  const [search, setSearch] = useState(false);
  const { data, issue } = useWorkspace();
  const cw = useConnected();
  const [connectOpen, setConnectOpen] = useState(false);
  const { storageIssue } = useScenario();
  const workItems = cw.active
    ? cw.missions.map((m) => ({ id: m.mission_id, goal: m.objective }))
    : data.work;
  const current = view === "item" ? "work" : view;
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setSearch((v) => !v);
      }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, []);
  const navContent = (
    <>
      <a
        className="studio-sidebar-brand"
        href="/"
        aria-label="Manufacturing OS home"
      >
        <ProductMark size={22} />
        <span>Manufacturing OS</span>
      </a>
      <div className="studio-team">
        <span>N</span>
        <div>
          Northfield<small>Manufacturing</small>
        </div>
      </div>
      <button
        type="button"
        className="flow-nav-new"
        aria-label="New work"
        onClick={() => {
          onNewWork();
          setMenu(false);
        }}
      >
        <RiAddLine size={17} />
        New work
      </button>
      <div className="ws-nav-label">Workspace</div>
      {links.map((l) => (
        <button
          type="button"
          className="ws-nav-item"
          key={l.id}
          aria-current={current === l.id ? "page" : undefined}
          onClick={() => {
            go(l.id);
            setMenu(false);
          }}
        >
          <l.icon size={18} />
          <span>{l.label}</span>
          {l.id === "work" && <small>{workItems.length}</small>}
        </button>
      ))}
      <div className="ws-nav-divider" />
      <div className="ws-nav-label">Recent work</div>
      {workItems.slice(0, 3).map((w) => (
        <button
          type="button"
          className="ws-nav-item flow-recent-link"
          key={w.id}
          title={w.goal}
          onClick={() => {
            openWork(w.id);
            setMenu(false);
          }}
        >
          <RiStackLine size={15} />
          <span>{w.goal}</span>
        </button>
      ))}
      <div className="ws-sidebar-bottom">
        {cw.active ? (
          <details className="studio-demo-details">
            <summary>
              <span className="studio-demo-dot" />
              Server workspace
            </summary>
            <p>
              Records, notes and approvals are saved on the server under your
              sign-in.
            </p>
            <button
              type="button"
              className="ws-export"
              onClick={() => {
                setConnectOpen(true);
                setMenu(false);
              }}
            >
              Connection <RiArrowRightSLine size={14} />
            </button>
          </details>
        ) : (
          <details className="studio-demo-details">
            <summary>
              <span className="studio-demo-dot" />
              Demo workspace
            </summary>
            <p>
              Simulated records. Saved in this browser. No live systems
              connected.
            </p>
            <button
              type="button"
              className="ws-export"
              onClick={() => downloadWork("manufacturing-workspace.json", data)}
            >
              Export saved work <RiArrowRightSLine size={14} />
            </button>
          </details>
        )}
        {cw.active ? (
          <div className="studio-user">
            <span className="ws-avatar">{initials(cw.connection.actor)}</span>
            <div>
              {cw.connection.actor}
              <small>{cw.me ? cw.me.roles.join(", ") || "No roles" : "Connecting…"}</small>
            </div>
          </div>
        ) : (
          <div className="studio-user">
            <span className="ws-avatar">PR</span>
            <div>
              Priya Raman<small>Demo account</small>
            </div>
          </div>
        )}
      </div>
    </>
  );
  return (
    <div className={`ws-shell${assistantOpen ? " ws-assistant-open" : ""}`}>
      <header className="ws-topbar">
        <button
          type="button"
          className="icon-btn ws-mobile"
          ref={menuTrigger}
          aria-expanded={menu}
          aria-label="Open menu"
          onClick={() => setMenu(true)}
        >
          <RiMenuLine size={20} />
        </button>
        <a className="ws-brand" href="/" aria-label="Manufacturing OS home">
          <ProductMark size={22} />
          <span>
            Manufacturing <b>OS</b>
          </span>
        </a>
        <nav className="ws-primary" aria-label="Manufacturing OS">
          <button
            type="button"
            className="flow-nav-new"
            aria-label="New work"
            onClick={onNewWork}
          >
            <RiAddLine size={16} />
            New work
          </button>
          {links.map((l) => (
            <button
              type="button"
              className="ws-nav-item"
              key={l.id}
              aria-current={current === l.id ? "page" : undefined}
              onClick={() => go(l.id)}
            >
              <span>{l.label}</span>
              {l.id === "work" && <small>{workItems.length}</small>}
            </button>
          ))}
        </nav>
        <div className="ws-top-actions">
          <button
            type="button"
            className="ws-search"
            aria-label="Search workspace"
            onClick={() => setSearch(true)}
          >
            <RiSearchLine size={16} />
            <span>Search</span>
            <Kbd>⌘K</Kbd>
          </button>
          <button
            type="button"
            className="ws-assistant-toggle"
            aria-label={assistantOpen ? "Close assistant" : "Open assistant"}
            aria-pressed={assistantOpen}
            onClick={onAssistant}
          >
            <AgentMark size={16} />
            <span>Assistant</span>
          </button>
          {cw.active ? (
            <span
              className="ws-avatar"
              title={`${cw.connection.actor} · ${cw.connection.tenant}`}
            >
              {initials(cw.connection.actor)}
            </span>
          ) : (
            <span className="ws-avatar" title="Priya Raman · demo identity">
              PR
            </span>
          )}
        </div>
      </header>
      <main className="sheet-page" id="work">
        {storageIssue && (
          <div className="ws-storage-error" role="alert">
            {storageIssue}
          </div>
        )}
        {issue && (
          <div className="ws-storage-error" role="alert">
            <p>{issue}</p>
            <button
              type="button"
              onClick={() =>
                downloadWork("manufacturing-session-recovery.json", data)
              }
            >
              Export this session
            </button>
          </div>
        )}
        {cw.active ? (
          <div className="ws-contextbar">
            <div className="ws-contextbar-left">
              <span className="ws-contextbar-mode">
                <i />{" "}
                {cw.status === "ready"
                  ? "Connected"
                  : cw.status === "error"
                    ? "Server unavailable"
                    : "Connecting…"}
              </span>
              <span className="ws-contextbar-site">
                <b>{cw.connection.tenant}</b>
              </span>
              <span>
                {cw.connection.actor}
                {cw.me ? ` (${cw.me.roles.join(", ") || "no roles"})` : ""}
              </span>
              <span className="ws-contextbar-optional">
                {cw.me ? authLabel(cw.me.auth_mode) : "Sign-in pending"}
              </span>
              <span className="ws-contextbar-optional">Server records</span>
            </div>
            <div className="ws-contextbar-right">
              <span className="ws-contextbar-optional">Human approval</span>
              <button type="button" onClick={() => setConnectOpen(true)}>
                Connection <RiArrowRightSLine size={12} />
              </button>
            </div>
          </div>
        ) : (
          <div className="ws-contextbar">
            <div className="ws-contextbar-left">
              <span className="ws-contextbar-site">
                <b>Northfield</b> · Upstream
              </span>
              <span className="ws-contextbar-mode">
                <i /> Sample mode
              </span>
              <span className="ws-contextbar-optional">Read-only snapshots</span>
              <span className="ws-contextbar-optional">Browser-local</span>
            </div>
            <div className="ws-contextbar-right">
              <span className="ws-contextbar-optional">Human review</span>
              <button type="button" onClick={() => setConnectOpen(true)}>
                Connect to server <RiArrowRightSLine size={12} />
              </button>
              <button type="button" onClick={() => go("sources")}>
                Review boundary <RiArrowRightSLine size={12} />
              </button>
            </div>
          </div>
        )}
        {children}
      </main>
      {assistantOpen && (
        <aside className="assistant" aria-label="Assistant">
          {assistant}
        </aside>
      )}
      <Dialog.Root open={menu} onOpenChange={setMenu}>
        <Dialog.Portal>
          <Dialog.Overlay className="lab sheet-overlay" />
          <Dialog.Content
            className="lab os-app ws-mobile-nav"
            onCloseAutoFocus={(event) => {
              event.preventDefault();
              menuTrigger.current?.focus();
            }}
          >
            <div className="ws-mobile-nav-head">
              <Dialog.Title>Workspace navigation</Dialog.Title>
              <Dialog.Close className="icon-btn" aria-label="Close menu">
                <RiCloseLine size={19} />
              </Dialog.Close>
            </div>
            <Dialog.Description className="sr-only">
              Navigate your workspace
            </Dialog.Description>
            {navContent}
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
      <ConnectionSheet open={connectOpen} onOpenChange={setConnectOpen} />
      <Command.Dialog
        open={search}
        onOpenChange={setSearch}
        label="Search"
        className="palette"
        contentClassName="lab palette-content"
        overlayClassName="lab sheet-overlay"
      >
        <div className="palette-input">
          <RiSearchLine size={18} />
          <Command.Input placeholder="Find work, sources, or actions…" />
          <Kbd>Esc</Kbd>
        </div>
        <Command.List>
          <Command.Empty>
            No matching work. Start with a new question from the workspace.
          </Command.Empty>
          <Command.Group heading="Go to">
            {links.map((l) => (
              <Command.Item
                key={l.id}
                value={l.label}
                onSelect={() => {
                  setSearch(false);
                  go(l.id);
                }}
              >
                <l.icon size={16} />
                {l.label}
              </Command.Item>
            ))}
          </Command.Group>
          <Command.Group heading="Saved work">
            {workItems.map((w) => (
              <Command.Item
                key={w.id}
                value={w.goal}
                onSelect={() => {
                  setSearch(false);
                  openWork(w.id);
                }}
              >
                <RiStackLine size={16} />
                {w.goal}
              </Command.Item>
            ))}
          </Command.Group>
          <Command.Group heading="Start">
            <Command.Item
              onSelect={() => {
                setSearch(false);
                onNewWork();
              }}
            >
              <RiAddLine size={16} />
              Start new work
            </Command.Item>
          </Command.Group>
        </Command.List>
      </Command.Dialog>
    </div>
  );
}
