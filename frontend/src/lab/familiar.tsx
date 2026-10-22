import { useState, type ReactNode } from "react";
import { RiCheckLine, RiExternalLinkLine } from "@remixicon/react";
import { TrendChart } from "./TrendChart";
import {
  agitation,
  antifoam,
  batchRecord,
  checked,
  dissolvedO2,
  events,
  hypotheses,
  labResults,
  NOW,
  onlineHours,
  titer,
  zip,
  type Evidence,
  type Point,
} from "./scenario";
import { useScenario } from "./state";
import { DataAvailability, useTiterSeries } from "./charts";
import { useEvidence } from "./evidence";
import { ActionCard } from "./review";
import { AgentMark, Button, Confidence, MISSING, SourceRef, StanceMark, Tip, cx, stanceLabel } from "./ui";

/* ───────── Batch header and the phase strip (the MES batch record's own element) ───────── */

export function BatchHeader({ actions }: { actions?: ReactNode }) {
  const { receipt } = useScenario();
  return (
    <header className="record-header">
      <div className="record-title">
        <p className="crumbs">
          <span>Batches</span> / <span>BR-04</span> /
        </p>
        <h1>
          Batch F-2408 <span className="pill pill-neutral">{batchRecord.status}</span>
          {receipt?.decision === "sent" ? <span className="pill pill-pos">Deviation draft with QA</span> : <span className="pill pill-warn">Below reference range</span>}
        </h1>
      </div>
      {actions && <div className="title-actions">{actions}</div>}
      <dl className="record-facts">
        <div>
          <dt>Product</dt>
          <dd>{batchRecord.product}</dd>
        </div>
        <div>
          <dt>Recipe</dt>
          <dd>{batchRecord.recipe}</dd>
        </div>
        <div>
          <dt>Unit</dt>
          <dd>{batchRecord.unit}</dd>
        </div>
        <div>
          <dt>Started</dt>
          <dd>{batchRecord.started}</dd>
        </div>
        <div>
          <dt>Batch age</dt>
          <dd className="num">{NOW.batchAge} h</dd>
        </div>
        <div>
          <dt>Phase</dt>
          <dd>{batchRecord.phase}</dd>
        </div>
      </dl>
      <PhaseStrip />
    </header>
  );
}

export function PhaseStrip() {
  const end = batchRecord.phases[batchRecord.phases.length - 1].to;
  const pct = (h: number) => `${(h / end) * 100}%`;
  const marks = events.filter((e) => e.kind === "Alarm" || e.kind === "Maintenance");
  return (
    <div className="phases" role="img" aria-label={`Batch phases: inoculation, batch, fed-batch, harvest over ${end} hours. Now ${NOW.batchAge} hours, in fed-batch. Alarms at 22 and 27 hours; off-gas analyser offline 31 to 44 hours.`}>
      <div className="phase-labels" aria-hidden="true">
        {batchRecord.phases
          .filter((p) => p.to - p.from >= 8)
          .map((p) => (
            <span key={p.name} className={cx(NOW.batchAge >= p.from && NOW.batchAge < p.to && "is-current")} style={{ left: pct(p.from) }}>
              {p.name}
              {NOW.batchAge >= p.from && NOW.batchAge < p.to && <small> · now {NOW.batchAge} h</small>}
            </span>
          ))}
      </div>
      <div className="phase-track">
        {batchRecord.phases.map((p) => (
          <div key={p.name} className="phase" style={{ left: pct(p.from), width: pct(p.to - p.from) }} title={p.name} />
        ))}
        <i className="phase-progress" style={{ width: pct(NOW.batchAge) }} />
        {marks.map((m) => (
          <Tip key={m.age + m.text} label={`${m.age} h · ${m.text}`}>
            <i className={cx("phase-mark", m.kind === "Alarm" ? "is-alarm" : "is-maint")} style={{ left: pct(m.age) }} tabIndex={0} aria-label={`${m.age} h, ${m.text}`} />
          </Tip>
        ))}
        <i className="phase-now" style={{ left: pct(NOW.batchAge) }} />
      </div>
      <div className="phase-axis" aria-hidden="true">
        {[0, 24, 48, 72, 96].map((t, i, all) => (
          <span key={t} style={{ left: pct(t) }} className={cx(i === 0 && "first", i === all.length - 1 && "last")}>
            {i === all.length - 1 ? `${t} h` : t}
          </span>
        ))}
      </div>
    </div>
  );
}

/* ───────── Tabs, the way every batch record has them ───────── */

export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: { id: T; label: string; badge?: ReactNode }[]; value: T; onChange: (t: T) => void }) {
  return (
    <div className="tabs" role="tablist" aria-label="Batch record">
      {tabs.map((t) => (
        <button key={t.id} type="button" role="tab" aria-selected={value === t.id} className="tab" onClick={() => onChange(t.id)}>
          {t.label}
          {t.badge}
        </button>
      ))}
    </div>
  );
}

/* ───────── Trend viewer with a pen list (PI Vision style) ───────── */

const wobble = (h: number, a: number) => Math.sin(h * 1.7) * a + Math.cos(h * 0.6) * a * 0.5;

export type PenId = "do" | "ag" | "af" | "temp" | "ph";
type Pen = { id: PenId; tag: string; label: string; unit: string; y: [number, number]; ticks: number[]; digits: number; current: Point[]; mean?: Point[]; band?: { lo: Point[]; hi: Point[] }; limit?: { y: number; label: string }; markers?: { x: number; label: string }[] };

export const pens: Pen[] = [
  { id: "do", tag: "BR04.DO.PV", label: "Dissolved oxygen, %", unit: "%", y: [0, 100], ticks: [0, 50, 100], digits: 0, current: zip(onlineHours, dissolvedO2.current), mean: zip(onlineHours, dissolvedO2.mean), band: { lo: zip(onlineHours, dissolvedO2.min), hi: zip(onlineHours, dissolvedO2.max) }, limit: { y: 40, label: "SP 40" } },
  { id: "ag", tag: "BR04.SIC-110.OUT", label: "Agitation, rpm", unit: "rpm", y: [0, 1000], ticks: [0, 500, 1000], digits: 0, current: zip(onlineHours, agitation.current), mean: zip(onlineHours, agitation.mean), limit: { y: 800, label: "HI 800" }, markers: [{ x: 27, label: "At limit" }] },
  { id: "af", tag: "BR04.AF.TOT", label: "Antifoam total, mL", unit: "mL", y: [0, 400], ticks: [0, 200, 400], digits: 0, current: zip(onlineHours, antifoam.current), mean: zip(onlineHours, antifoam.mean), markers: [{ x: 22.1, label: "Foam alarm" }] },
  { id: "temp", tag: "BR04.TEMP.PV", label: "Temperature, °C", unit: "°C", y: [29, 31], ticks: [29, 30, 31], digits: 2, current: zip(onlineHours, onlineHours.map((h) => +(30 + wobble(h, 0.08)).toFixed(2))), limit: { y: 30, label: "SP 30.0" } },
  { id: "ph", tag: "BR04.PH.PV", label: "pH", unit: "", y: [6.6, 7], ticks: [6.6, 6.8, 7], digits: 2, current: zip(onlineHours, onlineHours.map((h) => +(6.8 + wobble(h, 0.02)).toFixed(2))), limit: { y: 6.8, label: "SP 6.80" } },
];

export function TrendViewer({ selected, onSelected, reference, onReference }: { selected: PenId[]; onSelected: (p: PenId[]) => void; reference: boolean; onReference: (v: boolean) => void }) {
  const [hx, setHx] = useState<number | null>(null);
  const shown = pens.filter((p) => selected.includes(p.id));
  return (
    <div className="trendviewer">
      <fieldset className="penlist">
        <legend>Pens</legend>
        {pens.map((p) => (
          <label key={p.id} className="pen">
            <input type="checkbox" checked={selected.includes(p.id)} onChange={(e) => onSelected(e.target.checked ? [...selected, p.id] : selected.filter((x) => x !== p.id))} />
            <span>
              <b className="id">{p.tag}</b>
              <small>{p.label}</small>
            </span>
          </label>
        ))}
        <label className="pen is-assistant">
          <input type="checkbox" checked={reference} onChange={(e) => onReference(e.target.checked)} />
          <span>
            <b>Reference, 6 R7 batches</b>
            <small>
              <AgentMark size={11} /> Added by Assistant
            </small>
          </span>
        </label>
        <p className="pen-note">Time range: batch start to now · 1-min data</p>
      </fieldset>
      <div className="trend-stack">
        {shown.length === 0 && <div className="empty">Select a pen to plot it.</div>}
        {shown.map((p, i) => (
          <TrendChart
            key={p.id}
            height={i === shown.length - 1 ? 168 : 140}
            showXAxis={i === shown.length - 1}
            title={
              <>
                <span className="id">{p.tag}</span> · {p.label}
              </>
            }
            legend={i === 0}
            ariaLabel={`${p.label} for F-2408 from 0 to ${NOW.batchAge} hours${reference && p.mean ? ", with the reference from 6 prior batches" : ""}. Use the arrow keys to read values.`}
            series={[
              { id: "cur", label: "F-2408", kind: "primary", points: p.current },
              ...(reference && p.mean ? [{ id: "ref", label: "Reference mean", kind: "reference" as const, points: p.mean }] : []),
            ]}
            band={reference && p.band ? { label: "Range of 6 batches", ...p.band } : undefined}
            x={[0, 50]}
            xTicks={[0, 12, 24, 36, 48]}
            y={p.y}
            yTicks={p.ticks}
            unit={p.unit}
            digits={p.digits}
            limit={p.limit}
            markers={p.markers}
            now={NOW.batchAge}
            hoverX={hx}
            onHoverX={setHx}
          />
        ))}
      </div>
    </div>
  );
}

/* ───────── Lab results (LIMS) and events (historian and MES) ───────── */

export function LabTable({ onOpenSample }: { onOpenSample?: () => void }) {
  const { assayPosted } = useScenario();
  const rows = labResults.map((r) => (r.age === 60 && assayPosted ? { ...r, result: titer.posted60, status: "Below range" as const } : r));
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th scope="col">Sample</th>
            <th scope="col">Test</th>
            <th scope="col" className="n">
              Age, h
            </th>
            <th scope="col" className="n">
              Result
            </th>
            <th scope="col" className="n">
              Reference range
            </th>
            <th scope="col">Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.sample} aria-selected={r.status === "Below range" || undefined}>
              <th scope="row" className="id">
                {r.sample}
              </th>
              <td>{r.test}</td>
              <td className="n num">{r.age ?? MISSING}</td>
              <td className="n num">{r.result == null ? <span className="dash">{MISSING}</span> : `${r.result.toFixed(r.unit === "%" ? 0 : 2)} ${r.unit}`}</td>
              <td className="n num">
                {r.lo.toFixed(r.unit === "%" ? 0 : 2)}–{r.hi.toFixed(r.unit === "%" ? 0 : 2)} {r.unit}
              </td>
              <td>
                <span className={cx("pill", r.status === "Below range" ? "pill-warn" : r.status === "Pending" ? "pill-neutral" : "pill-plain")}>{r.status === "Pending" ? (r.age === 60 ? "Due 20:00" : "Pending") : r.status}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="table-foot">
        Reference range: lowest and highest of 6 prior R7 batches in BR-04 at the same age. Source: LIMS.{" "}
        {onOpenSample && (
          <button type="button" className="link" onClick={onOpenSample}>
            Open in LIMS
          </button>
        )}
      </p>
    </div>
  );
}

export function EventsTable() {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th scope="col" className="n">
              Age, h
            </th>
            <th scope="col">Time</th>
            <th scope="col">Type</th>
            <th scope="col">Description</th>
            <th scope="col">Source</th>
          </tr>
        </thead>
        <tbody>
          {events.map((e) => (
            <tr key={e.age + e.text}>
              <td className="n num">{e.age.toFixed(1)}</td>
              <td className="num">{e.clock}</td>
              <td>
                <span className={cx("pill", e.kind === "Alarm" ? "pill-warn" : "pill-plain")}>{e.kind}</span>
              </td>
              <td>{e.text}</td>
              <td>
                <SourceRef system={e.source} refId={e.tag} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ───────── The investigation, as a deviation form with drafted sections ───────── */

export function DraftSection({ id, title, children, by = "Assistant", note }: { id: string; title: string; children: ReactNode; by?: string; note?: ReactNode }) {
  const [reviewed, setReviewed] = useState(false);
  return (
    <section className={cx("form-section", reviewed && "is-reviewed")} aria-labelledby={id}>
      <header className="form-section-head">
        <h2 id={id}>{title}</h2>
        <span className="draft-by">
          <AgentMark size={12} /> Drafted by {by} at {NOW.label}
        </span>
        <label className="review-check">
          <input type="checkbox" checked={reviewed} onChange={(e) => setReviewed(e.target.checked)} />
          Reviewed
        </label>
      </header>
      {note && <p className="form-note">{note}</p>}
      {children}
    </section>
  );
}

export function EvidenceTable({ onOpen, stances = ["supports", "contradicts", "missing"] }: { onOpen: (e: Evidence) => void; stances?: Evidence["stance"][] }) {
  const { requested } = useScenario();
  const list = useEvidence().filter((e) => stances.includes(e.stance));
  return (
    <div className="table-wrap">
      <table className="ev-table">
        <thead>
          <tr>
            <th scope="col">Effect</th>
            <th scope="col">Evidence</th>
            <th scope="col">Source record</th>
            <th scope="col">Weight</th>
          </tr>
        </thead>
        <tbody>
          {list.map((e) => (
            <tr key={e.id} className="clickable" onClick={() => onOpen(e)}>
              <td>
                <span className="stance-cell">
                  <StanceMark stance={e.stance} />
                  {stanceLabel[e.stance]}
                </span>
              </td>
              <td>
                <button type="button" className="row-link" onClick={(ev) => { ev.stopPropagation(); onOpen(e); }} aria-label={`${stanceLabel[e.stance]}: ${e.claim}. Open the source record.`}>
                  {e.claim}
                </button>
                {e.id === "S4" && <span className="pill pill-neutral">New at 20:14</span>}
              </td>
              <td>
                <SourceRef system={e.system} refId={e.ref} />
              </td>
              <td>{e.stance === "missing" ? requested.includes(e.id) ? <span className="done-inline"><RiCheckLine size={13} /> Requested</span> : <span className="dash">{MISSING}</span> : e.weight}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function CausesTable() {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th scope="col">Possible cause</th>
            <th scope="col">Status</th>
            <th scope="col">Confidence</th>
            <th scope="col">What would change it</th>
          </tr>
        </thead>
        <tbody>
          {hypotheses.map((h) => (
            <tr key={h.id}>
              <th scope="row">
                <b>{h.title}</b>
                <small className="cell-sub">{h.summary}</small>
              </th>
              <td>{h.status}</td>
              <td>
                <Confidence level={h.confidence} />
              </td>
              <td className="muted-cell">{h.wouldChange}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function CheckedTable() {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th scope="col">Checked</th>
            <th scope="col" className="n">
              Value
            </th>
            <th scope="col">Note</th>
          </tr>
        </thead>
        <tbody>
          {checked.map((c) => (
            <tr key={c.label}>
              <th scope="row">{c.label}</th>
              <td className="n num">{c.value}</td>
              <td className="muted-cell">{c.note}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Description() {
  const { at, value, mean, gap } = useTiterSeries();
  return (
    <>
      <p className="form-text">
        At {at} h, batch F-2408 in BR-04 has a titer of <b className="num">{value.toFixed(2)} g/L</b>, {gap} % below the mean of 6 prior R7 batches (<span className="num">{mean.toFixed(2)} g/L</span>) and outside their range. Dissolved oxygen left its 40 % setpoint at 27 h, when agitation reached its 800 rpm limit, after antifoam use rose following a foam alarm at 22 h. Reduced oxygen transfer is the leading explanation. It is <b>not confirmed</b>: one earlier batch argues against it, and off-gas data for 31–44 h is missing.
      </p>
      <div className="form-status">
        <Confidence level={2} />
        <span className="muted-cell">No product impact assessed yet. Final titer unknown.</span>
      </div>
    </>
  );
}

export function InvestigationForm({ onOpen, onReview }: { onOpen: (e: Evidence) => void; onReview: () => void }) {
  return (
    <div className="form">
      <WhatsNewInline />
      <DraftSection id="f-desc" title="Description">
        <Description />
      </DraftSection>
      <DraftSection id="f-ev" title="Evidence" note="Every row links to the record in its own system. Contradicting evidence and gaps are listed with the rest.">
        <EvidenceTable onOpen={onOpen} />
      </DraftSection>
      <DraftSection id="f-cause" title="Possible causes" note="Confidence is a judgement with reasons, not a computed probability.">
        <CausesTable />
      </DraftSection>
      <DraftSection id="f-checked" title="Checked and within normal range">
        <CheckedTable />
      </DraftSection>
      <DraftSection id="f-gaps" title="Data gaps" note="Gaps are shown as gaps. Nothing is interpolated.">
        <DataAvailability />
      </DraftSection>
      <section className="form-section" aria-labelledby="f-act">
        <h2 id="f-act" className="sr-only">
          Proposed actions
        </h2>
        <ActionCard onReview={onReview} />
      </section>
    </div>
  );
}

function WhatsNewInline() {
  return (
    <p className="form-intro">
      This is your usual deviation form. Sections marked <AgentMark size={12} /> were drafted by the Assistant from the records listed under Evidence. Tick <b>Reviewed</b> as you check each one; nothing is submitted until you send it.
    </p>
  );
}

export function OpenInSource({ system }: { system: string }) {
  return (
    <Tip label="Opens the record in its own application. Not connected in this prototype.">
      <span>
        <Button size="sm" variant="secondary" disabled icon={<RiExternalLinkLine size={14} />}>
          Open in {system}
        </Button>
      </span>
    </Tip>
  );
}
