import { useEffect, useRef, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import {
  RiArrowRightLine,
  RiArrowLeftLine,
  RiCloseLine,
  RiCheckLine,
  RiAddLine,
  RiFlaskLine,
  RiPulseLine,
  RiFileTextLine,
  RiLinksLine,
  RiArrowRightUpLine,
  RiDownloadLine,
  RiLayoutGridLine,
  RiTimeLine,
  RiSearchLine,
  RiShieldCheckLine,
} from "@remixicon/react";
import { batches, evidence, type Evidence } from "./fixtures";
import "./concepts.css";

type Concept = "a" | "b" | "c";
type Filter = "support" | "against" | "missing";
const names = {
  a: "Ambient teammate",
  b: "Scientific workspace",
  c: "Embedded companion",
};
function Mark({ small = false }: { small?: boolean }) {
  return (
    <span className={"agent-mark " + (small ? "small" : "")} aria-hidden="true">
      <i />
      <i />
      <i />
    </span>
  );
}
function Arrow() {
  return <RiArrowRightLine size={17} />;
}
function Pill({
  children,
  tone = "green",
}: {
  children: React.ReactNode;
  tone?: string;
}) {
  return (
    <span className={"pill " + tone}>
      <span />
      {children}
    </span>
  );
}
function Modal({
  title,
  description,
  children,
  onClose,
  wide = false,
}: {
  title: string;
  description: string;
  children: React.ReactNode;
  onClose: () => void;
  wide?: boolean;
}) {
  const returnFocus = useRef(document.activeElement as HTMLElement | null);
  return (
    <Dialog.Root
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="cl-overlay" />
        <Dialog.Content
          onEscapeKeyDown={(event) => event.stopPropagation()}
          onCloseAutoFocus={(e) => {
            e.preventDefault();
            returnFocus.current?.focus();
          }}
          className={"concept-lab cl-dialog " + (wide ? "wide" : "")}
        >
          <div className="dialog-heading">
            <div>
              <Dialog.Title>{title}</Dialog.Title>
              <Dialog.Description>{description}</Dialog.Description>
            </div>
            <Dialog.Close className="icon-button" aria-label="Close dialog">
              <RiCloseLine size={21} />
            </Dialog.Close>
          </div>
          {children}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
function Chart({
  metric = "product",
  compact = false,
}: {
  metric?: "product" | "oxygen";
  compact?: boolean;
}) {
  const isProduct = metric === "product",
    max = isProduct ? 2.5 : 80;
  const x = (hour: number) => 62 + (hour / 48) * 646,
    y = (v: number) => 224 - (v / max) * 184;
  const path = (reference: boolean) =>
    batches
      .map(
        (d, i) =>
          `${i ? "L" : "M"}${x(d.hour)},${y(isProduct ? (reference ? d.reference : d.product) : reference ? d.refOxygen : d.oxygen)}`,
      )
      .join(" ");
  return (
    <div
      className={"chart " + (compact ? "compact" : "")}
      role="region"
      aria-label="Scientific chart; scroll horizontally on narrow screens"
      tabIndex={0}
    >
      <svg
        viewBox="0 0 770 280"
        role="img"
        aria-label={
          isProduct
            ? "Illustrative product concentration: F-2408 1.74 g/L versus six-batch reference mean 2.12 g/L at 48 hours"
            : "Illustrative dissolved oxygen: F-2408 25% versus reference mean 40% at 48 hours"
        }
      >
        <text x="18" y="18" className="axis-title">
          {isProduct
            ? "Product concentration (g/L)"
            : "Dissolved oxygen (% air saturation)"}
        </text>
        {(isProduct ? [0, 0.5, 1, 1.5, 2, 2.5] : [0, 20, 40, 60, 80]).map(
          (value) => (
            <g key={value}>
              <line
                x1="62"
                x2="708"
                y1={y(value)}
                y2={y(value)}
                stroke="#e4eae7"
              />
              <text x="47" y={y(value) + 4} textAnchor="end">
                {value.toFixed(isProduct ? 1 : 0)}
              </text>
            </g>
          ),
        )}
        <rect
          x={x(24)}
          y="40"
          width={x(48) - x(24)}
          height="184"
          fill="#32684f"
          opacity=".045"
        />
        <path
          d={path(true)}
          stroke="#8b9c96"
          strokeWidth="2"
          strokeDasharray="6 5"
          fill="none"
        />
        <path d={path(false)} stroke="#32684f" strokeWidth="3" fill="none" />
        {batches.map((d) => (
          <g key={d.hour}>
            <circle
              cx={x(d.hour)}
              cy={y(isProduct ? d.product : d.oxygen)}
              r="3.5"
              fill="#32684f"
              stroke="white"
              strokeWidth="1.5"
            >
              <title>
                {d.hour} h:{" "}
                {isProduct ? d.product + " g/L" : d.oxygen + "% air sat."}
              </title>
            </circle>
            <text x={x(d.hour)} y="249" textAnchor="middle">
              {d.hour}
            </text>
          </g>
        ))}
        <text x="385" y="273" textAnchor="middle">
          Batch age (hours)
        </text>
        <text
          x="718"
          y={y(isProduct ? 1.74 : 25) + 4}
          fill="#32684f"
          fontWeight="600"
        >
          {isProduct ? "1.74" : "25%"}
        </text>
      </svg>
      <div className="chart-legend">
        <span>
          <i />
          F-2408
        </span>
        <span>
          <i className="dashed" />
          Prior six batches, mean
        </span>
      </div>
    </div>
  );
}
function EvidenceList({
  filter,
  onFilter,
  onSource,
}: {
  filter: Filter;
  onFilter: (f: Filter) => void;
  onSource: (e: Evidence) => void;
}) {
  return (
    <>
      <div className="segmented" aria-label="Evidence categories">
        {(
          [
            ["support", "Supporting", 2],
            ["against", "Counterevidence", 2],
            ["missing", "Missing", 2],
          ] as const
        ).map(([id, label, count]) => (
          <button
            key={id}
            aria-pressed={filter === id}
            onClick={() => onFilter(id)}
          >
            {label}
            <span>{count}</span>
          </button>
        ))}
      </div>
      <div className="evidence-list">
        {evidence
          .filter((e) => e.kind === filter)
          .map((e) => (
            <button
              className="evidence-row"
              key={e.id}
              onClick={() => onSource(e)}
            >
              <span
                className={
                  "evidence-icon " + (filter === "missing" ? "amber" : "")
                }
              >
                <RiFileTextLine size={19} />
              </span>
              <span>
                <b>{e.title}</b>
                <small>
                  {e.source} <span className="source-id">{e.id}</span>
                </small>
              </span>
              <RiArrowRightUpLine size={17} />
            </button>
          ))}
      </div>
    </>
  );
}
function DataTable() {
  return (
    <div className="table-scroll">
      <table className="data-table">
        <caption>
          Aligned observations · synthetic fixture · no interpolation
        </caption>
        <thead>
          <tr>
            <th>Age (h)</th>
            <th>F-2408 (g/L)</th>
            <th>Reference (g/L)</th>
            <th>DO (% air sat.)</th>
          </tr>
        </thead>
        <tbody>
          {batches.map((d) => (
            <tr key={d.hour}>
              <td>{d.hour}</td>
              <td>{d.product.toFixed(2)}</td>
              <td>{d.reference.toFixed(2)}</td>
              <td>{d.oxygen}</td>
            </tr>
          ))}
          <tr>
            <td>72</td>
            <td>Not posted</td>
            <td>Not in snapshot</td>
            <td>Not in snapshot</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}
export default function ConceptLab() {
  const initial = new URLSearchParams(location.search).get("concept");
  const [concept, setConcept] = useState<Concept>(
    initial === "b" || initial === "c" ? initial : "a",
  );
  const [open, setOpen] = useState(false),
    [filter, setFilter] = useState<Filter>("support"),
    [source, setSource] = useState<Evidence | null>(null);
  const [review, setReview] = useState(false),
    [connections, setConnections] = useState(false),
    [compare, setCompare] = useState(false),
    [responsibility, setResponsibility] = useState(false);
  const [tool, setTool] = useState("Trends"),
    [metric, setMetric] = useState<"product" | "oxygen">(
      initial === "c" ? "oxygen" : "product",
    ),
    [hostTab, setHostTab] = useState("Process trends");
  const [companion, setCompanion] = useState(true),
    [snoozed, setSnoozed] = useState(false),
    [requested, setRequested] = useState(false);
  const [reviewer, setReviewer] = useState(""),
    [notes, setNotes] = useState(""),
    [receipt, setReceipt] = useState(""),
    [decision, setDecision] = useState("");
  const [notice, setNotice] = useState("");
  const switchConcept = (c: Concept) => {
    setConcept(c);
    setMetric(c === "c" ? "oxygen" : "product");
    setOpen(false);
    setTool("Trends");
    setFilter("support");
    setReceipt("");
    setDecision("");
    setSnoozed(false);
    setCompanion(true);
    setRequested(false);
    history.replaceState({}, "", `/concepts/v1?concept=${c}`);
  };
  useEffect(() => {
    document.title = `${names[concept]} · Manufacturing OS concept lab`;
  }, [concept]);
  useEffect(() => {
    const fn = (e: KeyboardEvent) => {
      if (e.defaultPrevented) return;
      if (
        (e.target as HTMLElement).closest("input,textarea,select") ||
        e.metaKey ||
        e.ctrlKey ||
        e.altKey ||
        source ||
        review ||
        connections ||
        compare ||
        responsibility
      )
        return;
      if (["1", "2", "3"].includes(e.key)) {
        e.preventDefault();
        switchConcept((["a", "b", "c"] as const)[Number(e.key) - 1]);
      }
      if (e.key.toLowerCase() === "e") {
        setOpen(true);
        setCompanion(true);
      }
      if (e.key.toLowerCase() === "r" && (open || concept === "b"))
        setReview(true);
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", fn);
    return () => window.removeEventListener("keydown", fn);
  }, [source, review, connections, compare, responsibility, open, concept]);
  useEffect(() => {
    if (notice) {
      const timeout = setTimeout(() => setNotice(""), 4500);
      return () => clearTimeout(timeout);
    }
  }, [notice]);
  const download = () => {
    const blob = new Blob(
      [
        `# Illustrative fermentation investigation\n\nSIMULATED DATA — no real integrations or GMP signature.\n\nF-2408 at 48 h: 1.74 g/L vs 2.12 g/L reference mean (six prior batches); DO 25% vs 40%. Association only. Temperature and pH near targets; probe calibration in date. Final yield, airflow and 72 h assay unknown.\n\n${evidence.map((e) => `${e.id}: ${e.title}\n${e.source}; ${e.location}\n${e.detail}\nLimitation: ${e.caveat}`).join("\n\n")}\n\nProposed: verify oxygen reading and actual airflow through existing approved sampling procedures. Owner: process engineering. Due: next shift (14:00). QA review required for any process change.\n\nPrototype review: ${receipt || "Not reviewed"}\nReviewer: ${reviewer || "Unassigned"}\nDecision: ${decision || "Pending"}\nNote: ${notes || "None"}\n`,
      ],
      { type: "text/markdown" },
    );
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "illustrative-fermentation-review.md";
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    setNotice("Illustrative evidence packet downloaded.");
  };
  const reviewButton = (
    <button className="primary" onClick={() => setReview(true)}>
      {receipt ? "View review receipt" : "Review next action"}
      <Arrow />
    </button>
  );
  const uncertainty = (
    <div className="uncertainty">
      <span className="uncertainty-dot" />
      <div>
        <b>A working hypothesis, with gaps</b>
        <p>
          Oxygen availability may be involved. Sensor drift and biological
          variation remain plausible. Actual airflow and the 72 h assay are
          missing.
        </p>
        <button className="text-button" onClick={() => setSource(evidence[4])}>
          Inspect missing data <Arrow />
        </button>
      </div>
    </div>
  );
  const workspace = (
    <div className="investigation-body">
      <div className="section-title">
        <div>
          <p className="muted">Investigation F-2408 / BR-04</p>
          <h2>A change worth understanding.</h2>
        </div>
        <Pill tone="amber">Cause unresolved</Pill>
      </div>
      <p className="body-copy">
        Product concentration has fallen behind comparable batches. Lower
        dissolved oxygen appears at the same time. Let’s verify the signal
        before changing the process.
      </p>
      <div className="chart-heading">
        <b>Where the trajectories separate</b>
        <select
          aria-label="Chart measurement"
          value={metric}
          onChange={(e) => setMetric(e.target.value as "product" | "oxygen")}
        >
          <option value="product">Product concentration</option>
          <option value="oxygen">Dissolved oxygen</option>
        </select>
      </div>
      <Chart metric={metric} />
      <p className="chart-note">
        Illustrative observations, aligned by batch age. Reference mean of six
        same-recipe batches; comparability is not established.
      </p>
      <EvidenceList filter={filter} onFilter={setFilter} onSource={setSource} />
      {uncertainty}
      <div className="next-action">
        <div>
          <small>Suggested next step</small>
          <h3>Verify oxygen availability before adjusting the recipe.</h3>
          <p>
            Prepare a verification task for process engineering, with the
            evidence attached.
          </p>
        </div>
        {reviewButton}
      </div>
    </div>
  );
  return (
    <div className={"concept-lab concept-" + concept}>
      <div className="lab-bar">
        <a href="/" className="lab-home">
          <RiArrowLeftLine size={14} />
          Existing app
        </a>
        <span className="lab-label">Interaction study</span>
        <nav aria-label="Interface concepts">
          {(["a", "b", "c"] as const).map((c, i) => (
            <button
              key={c}
              onClick={() => switchConcept(c)}
              aria-current={concept === c ? "page" : undefined}
            >
              <span>{c.toUpperCase()}</span>
              {names[c]}
              <kbd>{i + 1}</kbd>
            </button>
          ))}
        </nav>
        <button className="compare-button" onClick={() => setCompare(true)}>
          Compare concepts <RiLayoutGridLine size={15} />
        </button>
      </div>
      <div className="simulation-label">
        <span className="sim-dot" />
        Illustrative prototype{" "}
        <span className="sim-detail">
          All data, connectors and agent activity are simulated. Actions stay in
          this browser session.
        </span>
      </div>
      {concept !== "c" && (
        <header className="app-header">
          <a href="/concepts/v1" className="brand">
            <Mark small />
            manufacturing<span>os</span>
          </a>
          <div className="header-center">
            <span className="site-dot" />
            Northfield / Pilot plant <span className="header-slash">
              /
            </span>{" "}
            {concept === "a" ? "Your work" : "Fermentation investigation"}
          </div>
          <button
            className="connection-button"
            onClick={() => setConnections(true)}
          >
            <RiLinksLine size={16} />
            <span>3 sources connected</span>
            <span className="connection-dot" />
          </button>
          <span className="avatar" aria-label="Engineer Maya Chen">
            MC
          </span>
        </header>
      )}
      {concept === "a" && (
        <main className="ambient-main">
          <div className="ambient-intro">
            <div className="date-line">
              Wednesday, 21 October <span>Morning brief</span>
            </div>
            <h1>A little ahead of the unexpected.</h1>
            <p>
              Your agent is following three responsibilities.
              <br />
              One development could use your perspective.
            </p>
          </div>
          <div className="ambient-columns">
            <div className="attention-column">
              <div className="section-label">
                <span>For your attention</span>
                <span>1 development</span>
              </div>
              {!open ? (
                <article
                  className={"priority-story " + (snoozed ? "snoozed" : "")}
                >
                  <div className="story-meta">
                    <Mark small />
                    <span>Fermentation watch</span>
                    <time>09:42</time>
                    <Pill tone="amber">Needs a look</Pill>
                  </div>
                  <h2>BR-04 is taking a different path.</h2>
                  <p>
                    Product concentration is 18% below the reference at 48
                    hours. I found a coinciding oxygen change, but the cause is
                    still open.
                  </p>
                  <div className="micro-trend">
                    <svg
                      viewBox="0 0 600 94"
                      aria-label="Illustrative trajectories separating after 24 hours"
                      role="img"
                    >
                      <path
                        d="M8 79 C90 78 140 68 208 57 S340 30 410 21 S510 12 585 7"
                        fill="none"
                        stroke="#9eaea7"
                        strokeDasharray="5 5"
                        strokeWidth="2"
                      />
                      <path
                        d="M8 79 C90 78 140 68 208 58 S340 48 410 41 S510 29 585 24"
                        fill="none"
                        stroke="#32684f"
                        strokeWidth="2.5"
                      />
                      <circle cx="585" cy="24" r="4" fill="#32684f" />
                    </svg>
                    <div>
                      <span>Batch start</span>
                      <span>
                        48 hours <b>1.74 g/L</b>
                      </span>
                    </div>
                  </div>
                  <div className="story-bottom">
                    <button className="primary" onClick={() => setOpen(true)}>
                      Open investigation <Arrow />
                    </button>
                    <button
                      className="text-button"
                      onClick={() => setSnoozed(!snoozed)}
                    >
                      <RiTimeLine size={16} />
                      {snoozed
                        ? "Restore to attention"
                        : "Remind me next shift"}
                    </button>
                  </div>
                  {snoozed && (
                    <p role="status" className="inline-status">
                      Reminder set for 14:00 in this simulation. Investigation
                      remains available.
                    </p>
                  )}
                  <div className="story-footnote">
                    <RiShieldCheckLine size={15} />2 supporting observations · 2
                    counterpoints · 2 missing inputs
                  </div>
                </article>
              ) : (
                <article className="ambient-investigation">
                  <button
                    className="text-button back"
                    onClick={() => setOpen(false)}
                  >
                    <RiArrowLeftLine size={16} />
                    Back to your brief
                  </button>
                  {workspace}
                </article>
              )}
              <section className="quiet-update">
                <span className="quiet-check">
                  <RiCheckLine size={18} />
                </span>
                <div>
                  <b>Cleaning review is ready for tomorrow.</b>
                  <p>No new discrepancies in the three records in scope.</p>
                  <button
                    className="text-button"
                    onClick={() => setResponsibility(true)}
                  >
                    See responsibility <Arrow />
                  </button>
                </div>
                <time>08:15</time>
              </section>
            </div>
            <aside className="responsibility-column">
              <div className="section-label">
                <span>In good hands</span>
                <Mark small />
              </div>
              <h3>Work that keeps moving.</h3>
              <p className="muted">I’ll bring you in when it matters.</p>
              {[
                {
                  icon: RiPulseLine,
                  title: "Watch fermentation",
                  sub: "BR-04 · recipe R7",
                  status: "Investigating one change",
                },
                {
                  icon: RiFileTextLine,
                  title: "Prepare cleaning review",
                  sub: "Suite 2 · next review tomorrow",
                  status: "Ready for your review",
                },
                {
                  icon: RiFlaskLine,
                  title: "Follow pending assays",
                  sub: "F-2408 · next sample at 72 h",
                  status: requested
                    ? "Request drafted for lab review"
                    : "Waiting on lab results",
                },
              ].map((r, i) => (
                <button
                  className="responsibility"
                  key={r.title}
                  onClick={() =>
                    i === 0
                      ? setOpen(true)
                      : i === 2
                        ? setSource(evidence[4])
                        : setResponsibility(true)
                  }
                >
                  <r.icon size={19} />
                  <span>
                    <b>{r.title}</b>
                    <small>{r.sub}</small>
                    <em>
                      <span className={i === 0 ? "amber-dot" : "green-dot"} />
                      {r.status}
                    </em>
                  </span>
                  <RiArrowRightUpLine size={15} />
                </button>
              ))}
              <button
                className="add-responsibility"
                onClick={() => setResponsibility(true)}
              >
                <RiAddLine size={17} />
                Manage responsibilities
              </button>
              <div className="scope-note">
                <RiLinksLine size={18} />
                <p>
                  Working with your historian, LIMS and MES.{" "}
                  <button onClick={() => setConnections(true)}>
                    View authorized scope
                  </button>
                </p>
              </div>
            </aside>
          </div>
          <footer className="ambient-footer">
            <span>
              <span className="green-dot" />
              Following your work. Keeping you in control.
            </span>
            <span>
              <kbd>E</kbd> Open evidence <kbd>R</kbd> Review action
            </span>
          </footer>
        </main>
      )}
      {concept === "b" && (
        <main className="scientific-main">
          <aside className="investigation-index">
            <div className="index-heading">
              <RiFlaskLine size={19} />
              <b>Investigation</b>
            </div>
            <h1>
              Fermentation
              <br />
              performance shift
            </h1>
            <Pill tone="amber">Under investigation</Pill>
            <p className="muted">
              F-2408 · BR-04
              <br />
              Recipe R7 · 48 h snapshot
            </p>
            <div className="index-divider" />
            {["Trends", "Batch table", "Hypotheses"].map((name, i) => (
              <button
                className={tool === name ? "index-item active" : "index-item"}
                key={name}
                onClick={() => setTool(name)}
              >
                <span>
                  {i === 0 ? (
                    <RiPulseLine size={18} />
                  ) : i === 1 ? (
                    <RiLayoutGridLine size={18} />
                  ) : (
                    <RiSearchLine size={18} />
                  )}
                </span>
                {name}
              </button>
            ))}
            <button className="index-item" onClick={() => setConnections(true)}>
              <RiLinksLine size={18} />
              Source scope
            </button>
            <div className="index-bottom">
              <Mark small />
              <b>Investigation paused at a decision</b>
              <p>Evidence assembled. Your review is the next step.</p>
            </div>
          </aside>
          <section className="workbench">
            <div className="workbench-top">
              <div>
                <span className="breadcrumb">Fermentation / F-2408</span>
                <h2>
                  {tool === "Trends"
                    ? "Follow the change."
                    : tool === "Batch table"
                      ? "Inspect the observations."
                      : "Keep alternatives in view."}
                </h2>
              </div>
              <button className="secondary" onClick={download}>
                <RiDownloadLine size={16} />
                Evidence packet
              </button>
            </div>
            <div className="finding-strip">
              <span className="finding-number">
                −18<span>%</span>
              </span>
              <div>
                <b>Lower product concentration at 48 h</b>
                <p>1.74 vs 2.12 g/L reference mean · six prior batches</p>
              </div>
              <Pill tone="neutral">Descriptive finding</Pill>
            </div>
            {tool === "Trends" ? (
              <div className="analysis-panel">
                <div className="chart-heading">
                  <h3>Batch-age aligned comparison</h3>
                  <select
                    aria-label="Chart measurement"
                    value={metric}
                    onChange={(e) =>
                      setMetric(e.target.value as "product" | "oxygen")
                    }
                  >
                    <option value="product">Product concentration</option>
                    <option value="oxygen">Dissolved oxygen</option>
                  </select>
                </div>
                <Chart metric={metric} />
                <p className="chart-note">
                  Same recipe and vessel. Lot and inoculum differences
                  unadjusted. Lines connect illustrative observations; no
                  statistical interval is implied.
                </p>
              </div>
            ) : tool === "Batch table" ? (
              <DataTable />
            ) : (
              <div className="hypothesis-list">
                {[
                  [
                    "Oxygen availability changed",
                    "Supported by coinciding DO decline. Verify actual airflow and an independent oxygen reading.",
                    "Plausible",
                  ],
                  [
                    "Oxygen sensor drift",
                    "Pre-batch calibration passed, but current accuracy is unverified.",
                    "Open",
                  ],
                  [
                    "Biological or feed variation",
                    "Raw-material and inoculum differences are not controlled in this comparison.",
                    "Open",
                  ],
                ].map(([title, detail, status]) => (
                  <article key={title}>
                    <Pill tone="neutral">{status}</Pill>
                    <h3>{title}</h3>
                    <p>{detail}</p>
                  </article>
                ))}
              </div>
            )}
            <div className="evidence-section-heading">
              <h3>Evidence, with its limits</h3>
              <span>Source-linked observations</span>
            </div>
            <EvidenceList
              filter={filter}
              onFilter={setFilter}
              onSource={setSource}
            />
          </section>
          <aside className="reasoning-panel">
            <div className="reasoning-title">
              <Mark small />
              <b>Working interpretation</b>
            </div>
            <h3>The oxygen signal is a lead, not a conclusion.</h3>
            <p>
              The timing is consistent with reduced oxygen availability.
              Temperature and pH remain near target, and the probe calibration
              passed.
            </p>
            <button
              className="text-button"
              onClick={() => setFilter("against")}
            >
              Inspect counterevidence <Arrow />
            </button>
            {uncertainty}
            <div className="reasoning-next">
              <small>Next decision</small>
              <h3>Verify before intervening.</h3>
              <p>
                Independent oxygen check and actual airflow review, using
                approved site procedures.
              </p>
              <dl>
                <div>
                  <dt>Owner</dt>
                  <dd>Process engineering</dd>
                </div>
                <div>
                  <dt>Due</dt>
                  <dd>Next shift, 14:00</dd>
                </div>
                <div>
                  <dt>Process change</dt>
                  <dd>None proposed</dd>
                </div>
              </dl>
              {reviewButton}
            </div>
            <p className="tiny-note">
              No recipe, batch disposition or release action is authorized by
              this prototype.
            </p>
          </aside>
        </main>
      )}
      {concept === "c" && (
        <main className="embedded-main">
          <header className="host-header">
            <span className="host-brand">
              <RiPulseLine size={24} />
              ProcessView <span>Historian</span>
            </span>
            <span>Northfield · Pilot plant</span>
            <button className="host-user" onClick={() => setConnections(true)}>
              <RiLinksLine size={16} />
              Read-only connection
            </button>
          </header>
          <div className="host-location">
            <span>Plant overview</span>
            <span>/</span>
            <span>Fermentation</span>
            <span>/</span>
            <b>BR-04</b>
          </div>
          <div className="host-title">
            <div>
              <Pill tone="neutral">Batch in progress</Pill>
              <h1>BR-04 / Fermentation</h1>
              <p>F-2408 · Penicillin · Recipe R7 · Started 19 Oct, 09:00</p>
            </div>
            <span className="host-clock">
              Snapshot at 48 h<br />
              <b>21 Oct · 09:00</b>
            </span>
          </div>
          <nav className="host-tabs" aria-label="Historian views">
            {["Process trends", "Batch records", "Shift notes"].map((t) => (
              <button
                key={t}
                aria-current={hostTab === t ? "page" : undefined}
                onClick={() => setHostTab(t)}
              >
                {t}
              </button>
            ))}
          </nav>
          <section
            className={"host-content " + (companion ? "with-companion" : "")}
          >
            <div className="host-chart-panel">
              {hostTab === "Process trends" ? (
                <>
                  <div className="chart-heading">
                    <h2>Process trends</h2>
                    <select
                      aria-label="Host trend measurement"
                      value={metric}
                      onChange={(e) =>
                        setMetric(e.target.value as "product" | "oxygen")
                      }
                    >
                      <option value="product">Product concentration</option>
                      <option value="oxygen">Dissolved oxygen</option>
                    </select>
                  </div>
                  <Chart metric={metric} />
                  <div className="host-measurements">
                    <div>
                      <span>Temperature</span>
                      <b>
                        25.0 <small>°C</small>
                      </b>
                      <em>Recipe target 25.0 °C</em>
                    </div>
                    <div>
                      <span>pH</span>
                      <b>6.5</b>
                      <em>Recipe target 6.5</em>
                    </div>
                    <div>
                      <span>Dissolved oxygen</span>
                      <b>
                        25 <small>% air sat.</small>
                      </b>
                      <em>Reference mean 40%</em>
                    </div>
                  </div>
                  <p className="chart-note">
                    Simulated host application · plotted batch-age observations,
                    not a live process trend.
                  </p>
                </>
              ) : hostTab === "Batch records" ? (
                <>
                  <h2>Batch observations</h2>
                  <DataTable />
                  <button
                    className="secondary"
                    onClick={() => setSource(evidence[3])}
                  >
                    Inspect probe calibration <Arrow />
                  </button>
                </>
              ) : (
                <>
                  <h2>Shift handover</h2>
                  <article className="shift-note">
                    <span>09:00 · Maya Chen · Illustrative record</span>
                    <h3>48 h sample collected.</h3>
                    <p>
                      Maintain the approved recipe. Independent oxygen
                      verification is awaiting engineering review. No process
                      adjustment recorded.
                    </p>
                  </article>
                  <article className="shift-note">
                    <span>Next shift · 14:00</span>
                    <h3>Follow up on verification.</h3>
                    <p>
                      Review oxygen check and request actual airflow through the
                      authorized workflow.
                    </p>
                  </article>
                </>
              )}
            </div>
            {companion && (
              <aside className="companion-panel">
                <div className="companion-heading">
                  <span>
                    <Mark small />
                    <b>Alongside</b>
                  </span>
                  <button
                    className="icon-button"
                    aria-label="Dismiss companion"
                    onClick={() => setCompanion(false)}
                  >
                    <RiCloseLine size={18} />
                  </button>
                </div>
                <p className="companion-context">
                  <RiLinksLine size={14} />
                  Reading this batch in context
                </p>
                <div className="companion-alert">
                  <Pill tone="amber">One development</Pill>
                  <h2>There’s more to this oxygen trend.</h2>
                  <p>
                    F-2408 is also showing lower product concentration. I
                    compared the lab results with six prior batches.
                  </p>
                  <div className="companion-observation">
                    <b>
                      1.74 <small>g/L</small>
                    </b>
                    <span>
                      at 48 h<br />
                      18% below reference
                    </span>
                  </div>
                  <p className="companion-caution">
                    A relationship to investigate. The cause is unconfirmed.
                  </p>
                  <button className="primary" onClick={() => setOpen(true)}>
                    Inspect linked evidence <Arrow />
                  </button>
                  <button
                    className="text-button"
                    onClick={() => setSource(evidence[4])}
                  >
                    What’s missing? <Arrow />
                  </button>
                </div>
                <div className="companion-scope">
                  <RiShieldCheckLine size={18} />
                  <p>
                    Reading authorized sources.
                    <br />
                    You review every proposed action.
                  </p>
                </div>
                {receipt && (
                  <div className="inline-status">
                    <RiCheckLine size={17} />
                    Review recorded locally
                  </div>
                )}
              </aside>
            )}
          </section>
          {!companion && (
            <button
              className="companion-launcher"
              onClick={() => setCompanion(true)}
            >
              <Mark small />
              Alongside <span>1</span>
            </button>
          )}
          <footer className="host-footer">
            <span>ProcessView is an illustrative existing application.</span>
            <button
              className="text-button"
              onClick={() => setConnections(true)}
            >
              Inspect companion permissions <Arrow />
            </button>
          </footer>
        </main>
      )}
      {concept === "c" && open && !source && !review && (
        <Modal
          title="A change across process and lab data"
          description="Alongside / Investigation F-2408 · Illustrative evidence workspace"
          onClose={() => setOpen(false)}
          wide
        >
          {workspace}
        </Modal>
      )}
      {source && (
        <Modal
          title={source.title}
          description={`${source.id} / ${source.source}`}
          onClose={() => setSource(null)}
        >
          <Pill tone={source.kind === "missing" ? "amber" : "neutral"}>
            {source.kind === "against"
              ? "Counterevidence"
              : source.kind === "missing"
                ? "Unavailable data"
                : "Supporting observation"}
          </Pill>
          <p className="modal-copy">{source.detail}</p>
          <div className="source-excerpt">
            <span>{source.location}</span>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Record</th>
                  <th>Context</th>
                  <th>Value / status</th>
                </tr>
              </thead>
              <tbody>
                {source.records.map((row) => (
                  <tr key={row[0]}>
                    {row.map((cell, i) => (
                      <td key={i}>{cell}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="uncertainty">
            <RiSearchLine size={20} />
            <div>
              <b>Interpretation limit</b>
              <p>{source.caveat}</p>
            </div>
          </div>
          <p className="tiny-note">
            Simulated connector response · invented source excerpt · snapshot 21
            Oct, 09:42. This record is not retrieved from a real system.
          </p>
          {source.kind === "missing" && (
            <button
              className="primary"
              disabled={requested}
              onClick={() => {
                setRequested(true);
                setNotice(
                  "Evidence request drafted locally. No request was sent.",
                );
              }}
            >
              {requested
                ? "Request drafted locally"
                : "Draft request for missing evidence"}
              {!requested && <Arrow />}
            </button>
          )}
        </Modal>
      )}
      {review && (
        <Modal
          title={receipt ? "Review receipt" : "Review the next action"}
          description="Verification task / Illustrative QMS handoff"
          onClose={() => setReview(false)}
        >
          {receipt ? (
            <>
              <div className="review-receipt">
                <RiCheckLine size={28} />
                <h3>
                  {decision === "request_changes"
                    ? "Changes requested"
                    : "Draft accepted for handoff"}
                </h3>
                <p>{receipt}</p>
                <dl>
                  <div>
                    <dt>Reviewer</dt>
                    <dd>{reviewer}</dd>
                  </div>
                  <div>
                    <dt>Comment</dt>
                    <dd>{notes}</dd>
                  </div>
                </dl>
              </div>
              <p className="modal-copy">
                This receipt exists only in the prototype session. No task has
                been sent to QMS, and no manufacturing action has been
                authorized.
              </p>
              <button className="primary" onClick={download}>
                <RiDownloadLine size={17} />
                Download review packet
              </button>
            </>
          ) : (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                setDecision("accepted");
                setReceipt(new Date().toLocaleString());
              }}
            >
              <Pill tone="amber">Human review required</Pill>
              <h3 className="review-action-title">
                Confirm the oxygen signal before changing the process.
              </h3>
              <p className="modal-copy">
                Prepare an independent DO check and review actual airflow using
                approved site procedures. Reassess the hypothesis when the 72 h
                assay is available.
              </p>
              <dl className="review-details">
                <div>
                  <dt>Owner</dt>
                  <dd>Process engineering</dd>
                </div>
                <div>
                  <dt>Due</dt>
                  <dd>Next shift · 14:00</dd>
                </div>
                <div>
                  <dt>Destination</dt>
                  <dd>Existing QMS · draft task</dd>
                </div>
                <div>
                  <dt>Evidence</dt>
                  <dd>E01–E05 · gaps included</dd>
                </div>
                <div>
                  <dt>Follow-up</dt>
                  <dd>
                    Compare independent DO to historian; record actual airflow
                    and assay, then reassess.
                  </dd>
                </div>
              </dl>
              <label className="form-label">
                Reviewer name
                <input
                  autoComplete="name"
                  required
                  value={reviewer}
                  onChange={(e) => setReviewer(e.target.value)}
                  placeholder="Your name"
                />
              </label>
              <label className="form-label">
                Review comment
                <textarea
                  required
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="Record your rationale or requested changes"
                  rows={3}
                />
              </label>
              <p className="tiny-note">
                Acceptance prepares a local draft only. Engineering / QA
                approval remains required under site procedures. No setpoints,
                batch disposition or release decisions change.
              </p>
              <div className="review-buttons">
                <button
                  className="secondary"
                  type="button"
                  disabled={!reviewer.trim() || !notes.trim()}
                  onClick={() => {
                    setDecision("request_changes");
                    setReceipt(new Date().toLocaleString());
                  }}
                >
                  Request changes
                </button>
                <button
                  className="primary"
                  disabled={!reviewer.trim() || !notes.trim()}
                  type="submit"
                >
                  Accept draft for handoff <Arrow />
                </button>
              </div>
            </form>
          )}
        </Modal>
      )}
      {connections && (
        <Modal
          title="Connected, within your scope."
          description="Illustrative connector setup · no real integrations are active"
          onClose={() => setConnections(false)}
        >
          <p className="modal-copy">
            The prototype starts after initial connector authorization. The
            agent works with existing records; no document upload is required.
          </p>
          {[
            [
              "Historian",
              "BR-04 · DO, pH, temperature · read-only",
              "Actual airflow excluded from authorized scope.",
            ],
            [
              "LIMS",
              "F-2408 and six reference batches · read-only",
              "72 h assay not posted; last snapshot 09:35.",
            ],
            [
              "MES",
              "Recipe R7 and calibration records · read-only",
              "Last snapshot 09:38.",
            ],
            [
              "QMS",
              "Draft handoff destination · not connected",
              "Download the review packet for an existing workflow.",
            ],
          ].map(([title, scope, gap]) => (
            <div className="connector-row" key={title}>
              <RiLinksLine size={20} />
              <div>
                <b>{title}</b>
                <p>{scope}</p>
                <small>{gap}</small>
              </div>
              <Pill tone={title === "QMS" ? "neutral" : "green"}>
                {title === "QMS" ? "Unavailable" : "Simulated"}
              </Pill>
            </div>
          ))}
        </Modal>
      )}
      {responsibility && (
        <Modal
          title="Ongoing responsibilities"
          description="Remembered work · illustrative assignment scope"
          onClose={() => setResponsibility(false)}
        >
          <div className="responsibility-detail">
            <h3>Watch fermentation</h3>
            <p>
              Compare F-2408 with six same-recipe batches at aligned batch ages.
              Surface material changes with source evidence. Continue until the
              next engineering review.
            </p>
            <h3>Prepare cleaning review</h3>
            <p>
              Follow three Suite 2 records for discrepancies before tomorrow’s
              review. Current simulated snapshot: no new discrepancies.
            </p>
            <h3>Follow pending assays</h3>
            <p>
              Look for the 72 h sample result. Missing values stay unavailable.
              Notify the engineer when the evidence can resolve an open
              question.
            </p>
          </div>
          <p className="tiny-note">
            These are scripted responsibilities. No background monitoring runs
            in this prototype.
          </p>
          <button
            className="primary"
            onClick={() => {
              setResponsibility(false);
              setConnections(true);
            }}
          >
            Inspect authorized sources <Arrow />
          </button>
        </Modal>
      )}
      {compare && (
        <Modal
          title="Three ways into the same work."
          description="Design assessment · interaction counts are walkthrough counts; times need user testing"
          onClose={() => setCompare(false)}
          wide
        >
          <div className="table-scroll">
            <table className="data-table comparison">
              <thead>
                <tr>
                  <th>Dimension</th>
                  <th>A / Ambient</th>
                  <th>B / Scientific</th>
                  <th>C / Embedded</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <th>Attention</th>
                  <td>One concise development</td>
                  <td>Finding + analytical context</td>
                  <td>Contextual companion alert</td>
                </tr>
                <tr>
                  <th>To original evidence</th>
                  <td>2 clicks: open, source</td>
                  <td>1 click: source</td>
                  <td>2 clicks: inspect, source</td>
                </tr>
                <tr>
                  <th>Uncertainty</th>
                  <td>Progressively disclosed</td>
                  <td>Always-visible reasoning</td>
                  <td>Brief first, full view on demand</td>
                </tr>
                <tr>
                  <th>Action review</th>
                  <td>Within investigation</td>
                  <td>Persistent decision panel</td>
                  <td>Focused review over host app</td>
                </tr>
                <tr>
                  <th>Visual character</th>
                  <td>Quiet daily brief</td>
                  <td>Modern scientific workbench</td>
                  <td>Small companion in familiar host</td>
                </tr>
                <tr>
                  <th>Engineer familiarity</th>
                  <td>Moderate; new work model</td>
                  <td>High; charts and tables</td>
                  <td>Highest; host stays in place</td>
                </tr>
                <tr>
                  <th>Main tradeoff</th>
                  <td>Extra step to inspect detail</td>
                  <td>More initial cognitive load</td>
                  <td>Host integration and occlusion</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div className="recommendation">
            <Mark small />
            <div>
              <h3>A as the home. B when the science gets deep.</h3>
              <p>
                Use the ambient brief for ongoing work, open the scientific
                workspace for complex comparisons, and add C as an optional
                entry point where host integrations allow it. Validate attention
                time with engineers before choosing the default.
              </p>
            </div>
          </div>
          <p className="tiny-note">
            Suggested study: ask engineers what needs attention, then have them
            find a contradictory source and review the verification task. Record
            time, clicks, uncertainty comprehension and review errors. No speed
            or usability benefit has been measured.
          </p>
        </Modal>
      )}
      {notice && (
        <div className="cl-toast" role="status">
          <RiCheckLine size={18} />
          {notice}
        </div>
      )}
    </div>
  );
}
