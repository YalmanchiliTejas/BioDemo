import { useState } from "react";
import { TrendChart } from "./TrendChart";
import { agitation, antifoam, dissolvedO2, NOW, offGasGap, onlineHours, RUN_AXIS, titer, titerHours, vessels, zip } from "./scenario";
import { useScenario } from "./state";
import { cx } from "./ui";

export function useTiterSeries() {
  const { assayPosted } = useScenario();
  const current = assayPosted ? [...titer.current, titer.posted60] : titer.current;
  const at = assayPosted ? 60 : 48;
  const value = current[current.length - 1];
  const mean = titer.mean[current.length - 1];
  return { current, assayPosted, at, value, mean, gap: Math.round((1 - value / mean) * 100) };
}

export function TiterChart({ height = 240, compact = false, title = true }: { height?: number; compact?: boolean; title?: boolean }) {
  const { current, assayPosted, at, value, mean } = useTiterSeries();
  const i = current.length - 1;
  return (
    <TrendChart
      compact={compact}
      height={compact ? 56 : height}
      title={title && !compact ? "Titer, g/L · offline assay every 12 h" : undefined}
      ariaLabel={`F-2408 titer ${value} g/L at ${at} h against a reference mean of ${mean} g/L and a range of ${titer.min[i]}–${titer.max[i]} g/L across 6 prior batches. Use the arrow keys to read each sample.`}
      series={[
        { id: "cur", label: "F-2408", kind: "primary", dots: true, points: zip(titerHours, current) },
        { id: "ref", label: "Reference mean", kind: "reference", points: zip(titerHours, titer.mean) },
      ]}
      band={{ label: "Range of 6 batches", lo: zip(titerHours, titer.min), hi: zip(titerHours, titer.max) }}
      x={[0, 72]}
      y={[0, 3.5]}
      yTicks={[0, 1, 2, 3]}
      xTicks={[0, 12, 24, 36, 48, 60, 72]}
      unit="g/L"
      digits={2}
      now={NOW.batchAge}
      pending={assayPosted ? { x: 72, label: "72 h tomorrow" } : { x: 60, label: "60 h due 20:00" }}
      markers={[{ x: 27, label: "DO leaves setpoint" }]}
    />
  );
}

export function ProcessStack() {
  const [hx, setHx] = useState<number | null>(null);
  const common = { x: [0, 50] as [number, number], xTicks: [0, 12, 24, 36, 48], hoverX: hx, onHoverX: setHx, now: NOW.batchAge };
  return (
    <div className="stack">
      <TrendChart
        {...common}
        height={168}
        showXAxis={false}
        title="Dissolved oxygen, % air saturation"
        ariaLabel="Dissolved oxygen held at its 40 percent setpoint until 27 hours, then fell to 25 percent at 48 hours. The six reference batches stayed between 38 and 43 percent."
        series={[
          { id: "cur", label: "F-2408", kind: "primary", points: zip(onlineHours, dissolvedO2.current) },
          { id: "ref", label: "Reference mean", kind: "reference", points: zip(onlineHours, dissolvedO2.mean) },
        ]}
        band={{ label: "Range of 6 batches", lo: zip(onlineHours, dissolvedO2.min), hi: zip(onlineHours, dissolvedO2.max) }}
        y={[0, 100]}
        yTicks={[0, 50, 100]}
        unit="%"
        digits={0}
        limit={{ y: 40, label: "Setpoint 40" }}
      />
      <TrendChart
        {...common}
        height={132}
        showXAxis={false}
        legend={false}
        title="Agitation, rpm"
        ariaLabel="Agitation reached its 800 rpm cascade limit at 27 hours. The reference batches peaked between 560 and 650 rpm."
        series={[
          { id: "cur", label: "F-2408", kind: "primary", points: zip(onlineHours, agitation.current) },
          { id: "ref", label: "Reference mean", kind: "reference", points: zip(onlineHours, agitation.mean) },
        ]}
        y={[0, 1000]}
        yTicks={[0, 500, 1000]}
        unit="rpm"
        digits={0}
        limit={{ y: 800, label: "Limit 800" }}
      />
      <TrendChart
        {...common}
        height={150}
        legend={false}
        title="Antifoam added, mL cumulative"
        ariaLabel="Cumulative antifoam reached 324 millilitres at 48 hours against a 120 millilitre reference mean, rising after a foam alarm at 22 hours."
        series={[
          { id: "cur", label: "F-2408", kind: "primary", points: zip(onlineHours, antifoam.current) },
          { id: "ref", label: "Reference mean", kind: "reference", points: zip(onlineHours, antifoam.mean) },
        ]}
        y={[0, 400]}
        yTicks={[0, 200, 400]}
        unit="mL"
        digits={0}
        markers={[{ x: 22, label: "Foam alarm" }]}
      />
    </div>
  );
}

const streams: { label: string; source: string; segments: { from: number; to: number; state: "ok" | "gap" | "denied"; note?: string }[]; samples?: number[] }[] = [
  { label: "Dissolved oxygen", source: "BR04.DO.PV", segments: [{ from: 0, to: NOW.batchAge, state: "ok" }] },
  { label: "Agitation", source: "BR04.SIC-110", segments: [{ from: 0, to: NOW.batchAge, state: "ok" }] },
  {
    label: "Off-gas O\u2082 uptake",
    source: "BR04.OUR.PV",
    segments: [
      { from: 0, to: offGasGap[0], state: "ok" },
      { from: offGasGap[0], to: offGasGap[1], state: "gap", note: "Offline" },
      { from: offGasGap[1], to: NOW.batchAge, state: "ok" },
    ],
  },
  { label: "Inlet airflow", source: "BR04.FIC-201", segments: [{ from: 0, to: NOW.batchAge, state: "denied", note: "Not in the agent's scope" }] },
  { label: "Titer assay", source: "LIMS", segments: [], samples: [0, 12, 24, 36, 48] },
];

export function DataAvailability() {
  const { assayPosted } = useScenario();
  const pct = (h: number) => `${(h / 72) * 100}%`;
  return (
    <div className="avail" role="table" aria-label="What the agent could see, by data stream, from 0 to 72 hours">
      <div className="avail-row avail-axis" role="row" aria-hidden="true">
        <span role="cell" />
        <span role="cell" className="avail-ticks">
          {[0, 12, 24, 36, 48, 60, 72].map((t, i, all) => (
            <i key={t} style={{ left: pct(t) }} className={cx(i === 0 && "first", i === all.length - 1 && "last")}>
              {i === all.length - 1 ? `${t} h` : t}
            </i>
          ))}
        </span>
      </div>
      {streams.map((s) => {
        const samples = s.samples ? (assayPosted ? [...s.samples, 60] : s.samples) : undefined;
        const next = s.samples ? (assayPosted ? 72 : 60) : undefined;
        return (
          <div className="avail-row" role="row" key={s.label}>
            <span role="rowheader" className="avail-label">
              {s.label}
              <small className="id">{s.source}</small>
            </span>
            <span role="cell" className="avail-track">
              {s.segments.map((g) => (
                <i key={g.from} className={`seg seg-${g.state}`} style={{ left: pct(g.from), width: pct(g.to - g.from) }}>
                  {g.note && <em>{g.note}</em>}
                </i>
              ))}
              {samples?.map((x) => <i key={x} className="sample" style={{ left: pct(x) }} />)}
              {next != null && <i className="sample is-next" style={{ left: pct(next) }} />}
              <i className="avail-now" style={{ left: pct(NOW.batchAge) }} />
              <span className="sr-only">
                {s.segments.map((g) => `${g.from}–${g.to} h ${g.state === "ok" ? "available" : g.note}`).join("; ")}
                {samples && `Samples at ${samples.join(", ")} h; next at ${next} h.`}
              </span>
            </span>
          </div>
        );
      })}
      <div className="avail-row" aria-hidden="true">
        <span />
        <span className="legend avail-key">
          <span>
            <i className="key seg-ok" /> Available
          </span>
          <span>
            <i className="key seg-gap" /> No data
          </span>
          <span>
            <i className="key seg-denied" /> Not in scope
          </span>
          <span>
            <i className="key-dot" /> Sample
          </span>
          <span>
            <i className="key-dot is-next" /> Not yet sampled
          </span>
        </span>
      </div>
    </div>
  );
}

/** The floor: six vessels on one run axis. Only the vessel with a finding carries the accent. */
export function Floor({ onOpen }: { onOpen?: (id: string) => void }) {
  const { receipt } = useScenario();
  const pct = (h: number) => `${(h / RUN_AXIS) * 100}%`;
  return (
    <div className="floor" role="table" aria-label="Bioreactors BR-01 to BR-06 on a 0 to 120 hour run axis">
      <div className="floor-row floor-axis" role="row" aria-hidden="true">
        <span role="cell" />
        <span role="cell" className="avail-ticks">
          {[0, 24, 48, 72, 96, 120].map((t, i, all) => (
            <i key={t} style={{ left: pct(t) }} className={cx(i === 0 && "first", i === all.length - 1 && "last")}>
              {i === all.length - 1 ? `${t} h` : t}
            </i>
          ))}
        </span>
        <span role="cell" />
      </div>
      {vessels.map((v) => {
        const state = v.flagged && receipt?.decision === "sent" ? "Verification with QA" : v.state;
        const Row = v.flagged && onOpen ? "button" : "div";
        return (
          <Row key={v.id} type={Row === "button" ? "button" : undefined} role="row" className={cx("floor-row", v.flagged && "is-flagged", !v.batch && "is-idle")} onClick={v.flagged && onOpen ? () => onOpen(v.id) : undefined}>
            <span role="rowheader" className="floor-label">
              <b>{v.id}</b>
              <small>{v.batch ? `${v.batch} · ${v.recipe}` : "No batch"}</small>
            </span>
            <span role="cell" className="floor-track">
              {v.runLength != null && <i className="run-plan" style={{ width: pct(v.runLength) }} />}
              {v.age != null && <i className="run-done" style={{ width: pct(v.age) }} />}
              {v.samples.map((s) => (
                <i key={s} className="run-sample" style={{ left: pct(s) }} />
              ))}
              {v.age != null && <i className="run-now" style={{ left: pct(v.age) }} />}
              <span className="sr-only">{v.age != null ? `${v.age} of ${v.runLength} h, ${v.samples.length} samples` : "Idle"}</span>
            </span>
            <span role="cell" className="floor-state">
              {v.age != null && <span className="num">{v.age.toFixed(1)} h</span>}
              <span className={cx(v.flagged && "is-flagged")}>{state}</span>
            </span>
          </Row>
        );
      })}
    </div>
  );
}
