import { useState } from "react";
import { RiCloseLine, RiFolder3Line, RiPulseLine } from "@remixicon/react";
import { action, agitation, antifoam, batch, dissolvedO2, events, NOW, onlineHours, people, zip } from "./scenario";
import { useScenario } from "./state";
import { TrendChart, type TrendProps } from "./TrendChart";
import { LabTable } from "./familiar";
import { AgentMark, cx } from "./ui";

// Simulated host applications: the customer's own historian, LIMS, MES and QMS. They keep their
// own, deliberately conventional look so the Assistant can be judged against what engineers know.

export type Tag = "DO" | "AG" | "AF" | "TEMP" | "PH";
export const tags: { id: Tag; tag: string; label: string; unit: string }[] = [
  { id: "DO", tag: "BR04.DO.PV", label: "Dissolved oxygen", unit: "%" },
  { id: "AG", tag: "BR04.SIC-110.OUT", label: "Agitation", unit: "rpm" },
  { id: "AF", tag: "BR04.AF.TOT", label: "Antifoam total", unit: "mL" },
  { id: "TEMP", tag: "BR04.TEMP.PV", label: "Temperature", unit: "°C" },
  { id: "PH", tag: "BR04.PH.PV", label: "pH", unit: "" },
];

const wobble = (h: number, a: number) => Math.sin(h * 1.7) * a + Math.cos(h * 0.6) * a * 0.5;
const flat = (base: number, amp: number) => onlineHours.map((h) => +(base + wobble(h, amp)).toFixed(2));

function hostSeries(tag: Tag, overlay: boolean): Pick<TrendProps, "series" | "band" | "y" | "yTicks" | "limit" | "markers" | "digits" | "unit"> {
  const cur = (ys: number[]) => ({ id: "cur", label: "F-2408", kind: "primary" as const, points: zip(onlineHours, ys) });
  const ref = (ys: number[]) => ({ id: "ref", label: "Assistant overlay · reference mean", kind: "reference" as const, points: zip(onlineHours, ys) });
  switch (tag) {
    case "DO":
      return {
        series: overlay ? [ref(dissolvedO2.mean), cur(dissolvedO2.current)] : [cur(dissolvedO2.current)],
        band: overlay ? { label: "Assistant overlay · reference range", lo: zip(onlineHours, dissolvedO2.min), hi: zip(onlineHours, dissolvedO2.max) } : undefined,
        y: [0, 100], yTicks: [0, 20, 40, 60, 80, 100], limit: { y: 40, label: "SP 40" },
        markers: overlay ? [{ x: 22, label: "foam alarm" }, { x: 27, label: "agitation at limit" }] : undefined, digits: 1, unit: "%",
      };
    case "AG":
      return { series: overlay ? [ref(agitation.mean), cur(agitation.current)] : [cur(agitation.current)], y: [200, 900], yTicks: [200, 400, 600, 800], limit: { y: 800, label: "HI 800" }, markers: overlay ? [{ x: 27, label: "at limit" }] : undefined, digits: 0, unit: "rpm" };
    case "AF":
      return { series: overlay ? [ref(antifoam.mean), cur(antifoam.current)] : [cur(antifoam.current)], y: [0, 350], yTicks: [0, 100, 200, 300], markers: overlay ? [{ x: 22, label: "foam alarm" }] : undefined, digits: 0, unit: "mL" };
    case "TEMP":
      return { series: [cur(flat(30, 0.08))], y: [29, 31], yTicks: [29, 29.5, 30, 30.5, 31], digits: 2, unit: "°C" };
    case "PH":
      return { series: [cur(flat(6.8, 0.02))], y: [6.6, 7.0], yTicks: [6.6, 6.7, 6.8, 6.9, 7.0], digits: 2, unit: "" };
  }
}

export const tagContext: Record<Tag, { linked: boolean; text: string }> = {
  DO: { linked: true, text: "This trend is the centre of the finding. DO left its setpoint at 27 h, when agitation saturated." },
  AG: { linked: true, text: "Agitation hit its 800 rpm limit at 27 h. References peaked at 560–650 rpm." },
  AF: { linked: true, text: "Antifoam is 2.7× the reference since the 22 h foam alarm, a plausible cause of reduced oxygen transfer." },
  TEMP: { linked: false, text: "Temperature is within ±0.2 °C of recipe. Checked; not part of this finding." },
  PH: { linked: false, text: "pH is within ±0.05 of recipe. Checked; not part of this finding." },
};


export function HistorianApp({ tag, setTag, overlay, setOverlay, linked }: { tag: Tag; setTag: (t: Tag) => void; overlay: boolean; setOverlay: (v: boolean) => void; linked: boolean }) {
  const s = useScenario();
  const ctx = tagContext[tag];
  const cur = tags.find((t) => t.id === tag)!;
  const hs = hostSeries(tag, overlay && ctx.linked);
  const pen = hs.series[hs.series.length - 1].points.map((p) => p[1] as number);
  const open = linked;
  return (
    <div className="host">
            <div className="host-menu" aria-hidden="true">
              <span>File</span>
              <span>View</span>
              <span>Trend</span>
              <span>Tools</span>
              <span>Help</span>
              <span className="host-menu-right">Northfield · BR-04 · Live</span>
            </div>
            <div className="host-body">
              <nav className="host-tree" aria-label="Historian tags">
                <p className="host-tree-h">
                  <RiFolder3Line size={14} /> Fermentation / BR-04
                </p>
                <ul>
                  {tags.map((t) => (
                    <li key={t.id}>
                      <button type="button" className={cx(tag === t.id && "is-on")} aria-current={tag === t.id || undefined} onClick={() => setTag(t.id)}>
                        <RiPulseLine size={13} />
                        <span className="id">{t.tag}</span>
                        {open && tagContext[t.id].linked && !s.detecting && <span className="host-agent-dot" title="Linked to the agent's finding" />}
                      </button>
                    </li>
                  ))}
                  <li>
                    <span className="host-locked">
                      <span className="id">BR04.FIC-201</span>
                      <small>no Assistant access</small>
                    </span>
                  </li>
                </ul>
              </nav>
              <section className="host-main">
                <div className="host-toolbar">
                  <h1 className="host-h1">
                    {cur.tag} · {cur.label}
                  </h1>
                  <span>Batch {batch.id} · 0–50 h</span>
                  <span className="host-tb-right">
                    <span className="host-btn">Zoom</span>
                    <span className="host-btn">Export</span>
                    <span className="host-btn">Add pen</span>
                  </span>
                </div>
                <div className={cx("host-chart", overlay && ctx.linked && "has-overlay")}>
                  {overlay && ctx.linked && (
                    <div className="overlay-tag">
                      <AgentMark size={12} /> Assistant overlay · reference from 6 R7 batches
                      <button type="button" onClick={() => setOverlay(false)} aria-label="Remove Assistant overlay">
                        <RiCloseLine size={13} />
                      </button>
                    </div>
                  )}
                  <TrendChart
                    {...hs}
                    x={[0, 50]}
                    xTicks={[0, 6, 12, 18, 24, 30, 36, 42, 48]}
                    now={NOW.batchAge}
                    height={360}
                    ariaLabel={`${cur.label} trend for ${batch.id}${overlay && ctx.linked ? " with the Assistant's reference overlay" : ""}. Use arrow keys to read values.`}
                  />
                </div>
                <div className="host-table" aria-hidden="true">
                  <span>Pen</span>
                  <span>Value</span>
                  <span>Min</span>
                  <span>Max</span>
                  <span className="id">{cur.tag}</span>
                  <span className="id">{pen[pen.length - 1].toFixed(hs.digits)}</span>
                  <span className="id">{Math.min(...pen).toFixed(hs.digits)}</span>
                  <span className="id">{Math.max(...pen).toFixed(hs.digits)}</span>
                </div>
              </section>
            </div>
          </div>
  );
}

const qmsFields = [
  { id: "title", label: "Event title", value: "F-2408 titer below R7 reference range at 48 h (BR-04)" },
  { id: "class", label: "Classification", value: "Process performance · minor (proposed)" },
  { id: "desc", label: "Description", value: "Offline titer 1.74 g/L at 48 h vs reference 1.98–2.27 g/L (n=6). DO below 40 % setpoint from 27 h with agitation at 800 rpm limit; antifoam 324 mL vs 120 mL mean after foam alarm at 22 h. Cause not established." },
  { id: "tasks", label: "Investigation tasks", value: action.steps.map((s, i) => `${i + 1}. ${s.text} (${s.owner}, ${s.due})`).join("\n") },
  { id: "gaps", label: "Known data gaps", value: "Off-gas 31–44 h (WO-5531). Inlet airflow BR04.FIC-201 not available to the Assistant. 60 h titer pending." },
];

export function QmsApp() {
  const s = useScenario();
  const [checkedFields, setChecked] = useState<string[]>([]);
  const all = checkedFields.length === qmsFields.length;
  const saved = s.receipt?.decision === "sent";
  return (
    <div className="host qms">
      <div className="host-menu" aria-hidden="true">
        <span>Home</span>
        <span>Events</span>
        <span>CAPA</span>
        <span>Change control</span>
        <span className="host-menu-right">{people.you.name}</span>
      </div>
      <div className="qms-body">
        <div className="qms-head">
          <div>
            <p className="qms-crumb">Events / New / {action.target.record}</p>
            <h1 className="host-h1">New quality event</h1>
          </div>
          <span className={cx("qms-status", saved && "is-saved")}>{saved ? "Draft saved · routed to QA" : "Unsaved draft"}</span>
        </div>
        <form
          className="qms-form"
          onSubmit={(e) => {
            e.preventDefault();
            if (all) s.setReceipt({ decision: "sent", note: "Saved via QualityTrack", at: "09:51", steps: action.steps.map((x) => x.id) });
          }}
        >
          {qmsFields.map((f) => {
            const ok = checkedFields.includes(f.id);
            return (
              <div key={f.id} className={cx("qms-field", "is-drafted", ok && "is-checked")}>
                <label htmlFor={`q-${f.id}`}>{f.label}</label>
                {f.value.length > 70 ? <textarea id={`q-${f.id}`} defaultValue={f.value} rows={f.id === "tasks" ? 4 : 3} disabled={saved} /> : <input id={`q-${f.id}`} defaultValue={f.value} disabled={saved} />}
                <span className="qms-draft-tag">
                  <AgentMark size={11} /> Drafted by Assistant
                  <label className="qms-check">
                    <input type="checkbox" checked={ok} disabled={saved} onChange={(e) => setChecked(e.target.checked ? [...checkedFields, f.id] : checkedFields.filter((x) => x !== f.id))} />
                    I've checked this
                  </label>
                </span>
              </div>
            );
          })}
          <div className="qms-field">
            <label htmlFor="q-owner">Event owner</label>
            <input id="q-owner" defaultValue={people.you.name} disabled={saved} />
          </div>
          <div className="qms-field">
            <label htmlFor="q-qa">QA approver</label>
            <input id="q-qa" defaultValue={people.qa.name} disabled={saved} />
          </div>
          <div className="qms-actions">
            <span className="qms-hint">{saved ? "Saved. QA review happens in QualityTrack as usual." : all ? "All drafted fields checked." : `${qmsFields.length - checkedFields.length} drafted field${qmsFields.length - checkedFields.length === 1 ? "" : "s"} left to check`}</span>
            <button type="button" className="qms-btn" disabled={saved}>
              Cancel
            </button>
            <button type="submit" className="qms-btn is-primary" disabled={!all || saved}>
              Save draft &amp; route to QA
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}


export function LimsApp() {
  return (
    <div className="host lims">
      <div className="host-menu" aria-hidden="true">
        <span>Samples</span>
        <span>Results</span>
        <span>Specifications</span>
        <span>Reports</span>
        <span className="host-menu-right">LabWare LIMS · Northfield QC</span>
      </div>
      <div className="qms-body">
        <div className="qms-head">
          <div>
            <p className="qms-crumb">Results / Batch {batch.id}</p>
            <h1 className="host-h1">Results for batch {batch.id}</h1>
          </div>
        </div>
        <div className="host-panel">
          <LabTable />
        </div>
      </div>
    </div>
  );
}

const steps = [
  { step: "3.1", name: "Inoculation", status: "Complete", by: "J. Tan", at: "Tue 08:00" },
  { step: "3.2", name: "Batch phase checks", status: "Complete", by: "J. Tan", at: "Wed 02:00" },
  { step: "4.1", name: "Start feed, programmed profile", status: "Complete", by: "M. Ortiz", at: "Wed 02:04" },
  { step: "4.3", name: "Foam control, on-demand antifoam", status: "Complete, alarm acknowledged", by: "J. Tan", at: "Wed 06:07" },
  { step: "4.4", name: "Sampling every 12 h", status: "In progress, 48 h taken", by: "M. Ortiz", at: "Thu 08:05" },
  { step: "5.1", name: "Harvest readiness", status: "Not started", by: "", at: "" },
];

export function MesApp() {
  return (
    <div className="host mes">
      <div className="host-menu" aria-hidden="true">
        <span>Orders</span>
        <span>Batch records</span>
        <span>Equipment</span>
        <span>Reports</span>
        <span className="host-menu-right">Syncade MES · {people.you.name}</span>
      </div>
      <div className="qms-body">
        <div className="qms-head">
          <div>
            <p className="qms-crumb">Batch records / BR-04</p>
            <h1 className="host-h1">Executed batch record {batch.id}</h1>
          </div>
          <span className="qms-status">In progress · {NOW.batchAge} h</span>
        </div>
        <div className="host-panel">
          <table className="host-grid">
            <thead>
              <tr>
                <th className="n">Step</th>
                <th>Instruction</th>
                <th>Status</th>
                <th>Performed by</th>
                <th className="n">Time</th>
              </tr>
            </thead>
            <tbody>
              {steps.map((st) => (
                <tr key={st.step}>
                  <td className="n num">{st.step}</td>
                  <td>{st.name}</td>
                  <td>{st.status}</td>
                  <td>{st.by}</td>
                  <td className="n num">{st.at}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="host-panel">
          <h2 className="host-h2">Recorded events</h2>
          <table className="host-grid">
            <tbody>
              {events
                .filter((e) => e.source === "MES")
                .map((e) => (
                  <tr key={e.age + e.text}>
                    <td className="n num">{e.clock}</td>
                    <td>{e.text}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
