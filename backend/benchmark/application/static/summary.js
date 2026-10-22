"use strict";

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "text") node.textContent = value;
    else if (key === "class") node.className = value;
    else node.setAttribute(key, value);
  }
  for (const child of children.flat()) {
    if (child != null) node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

function dateLabel(value) {
  return value ? new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" }).format(new Date(value)) : null;
}

function svgNode(tag, attrs = {}, text) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value));
  if (text != null) node.textContent = text;
  return node;
}

function plotSeries(series, options = {}) {
  const svg = svgNode("svg", { viewBox: "0 0 800 270", class: "evidence-chart", role: "img", "aria-label": options.title });
  svg.append(svgNode("title", {}, options.title));
  const points = series.flatMap(s => s.points).filter(p => Number.isFinite(p[0]) && Number.isFinite(p[1]));
  if (!points.length) return el("p", { class: "empty", text: "No comparable measurements available." });
  const xs = points.map(p => p[0]), ys = points.map(p => p[1]);
  const loX = Math.min(...xs), hiX = Math.max(...xs);
  const loY = Math.min(0, ...ys), hiY = Math.max(options.limit || 0, ...ys) * 1.15 || 1;
  const x = v => 65 + (v - loX) / (hiX - loX || 1) * 670;
  const y = v => 220 - (v - loY) / (hiY - loY || 1) * 185;
  for (let i = 0; i < 5; i++) {
    const value = loY + (hiY - loY) * i / 4;
    svg.append(svgNode("line", { x1: 65, x2: 735, y1: y(value), y2: y(value), stroke: "#e2e7e1" }),
      svgNode("text", { x: 55, y: y(value) + 4, "text-anchor": "end", class: "chart-label" }, value.toFixed(2)));
  }
  if (options.limit) svg.append(svgNode("line", { x1: 65, x2: 735, y1: y(options.limit), y2: y(options.limit), stroke: "#b4663a", "stroke-dasharray": "6 4" }),
    svgNode("text", { x: 735, y: y(options.limit) - 7, "text-anchor": "end", class: "chart-label" }, "Action limit · 1.00"));
  series.forEach((s, index) => {
    const color = index ? "#6684b2" : "#14795c";
    const valid = s.points.filter(p => Number.isFinite(p[0]) && Number.isFinite(p[1]));
    if (!options.scatter) svg.append(svgNode("path", { d: valid.map((p, i) => `${i ? "L" : "M"}${x(p[0])},${y(p[1])}`).join(" "), stroke: color, "stroke-width": 2, fill: "none" }));
    valid.forEach((p, i) => {
      const circle = svgNode("circle", { cx: x(p[0]), cy: y(p[1]), r: options.scatter ? 7 : 2, fill: color });
      circle.append(svgNode("title", {}, `${s.label}: ${p[1]} · ${options.dates ? dateLabel(new Date(p[0]).toISOString()) : `${p[0].toFixed(2)} h`}`));
      svg.append(circle);
      if (options.scatter) svg.append(svgNode("text", { x: x(p[0]), y: y(p[1]) - 14, "text-anchor": "middle", class: "chart-label" }, s.labels[i]));
    });
  });
  for (let i = 0; i < 4; i++) {
    const value = loX + (hiX - loX) * i / 3;
    svg.append(svgNode("text", { x: x(value), y: 248, "text-anchor": "middle", class: "chart-label" }, options.dates ? dateLabel(new Date(value).toISOString()) : `${value.toFixed(1)} h`));
  }
  return svg;
}

function recordDetails(item) {
  const record = item.record;
  const id = record.id || record.result_id || record.deviation_id || record.work_order || record.sample_id || record.complaint_id || "Source record";
  return el("details", { class: "record-excerpt" },
    el("summary", {}, el("strong", { text: id }), el("span", { text: `${item.collection.replaceAll("_", " ")} · ${record.batch_id || record.linked_batch_id || record.lot || ""}` })),
    el("p", { class: "source-caption", text: "Synthetic record excerpt · benchmark/incident_demo/data/agent_data.json" }),
    el("dl", { class: "record-fields" }, Object.entries(record).filter(([, v]) => v != null).map(([key, value]) =>
      [el("dt", { text: key.replaceAll("_", " ") }), el("dd", { text: typeof value === "object" ? JSON.stringify(value) : value })])));
}

const short = value => new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", timeZone: "UTC" }).format(new Date(value));
const lotName = id => `Lot ${id.replace(/^\D+/, "")}`;

function kpiBand(view) {
  return el("div", { class: "kpi-band" }, view.kpis.map(kpi => {
    const show = value => kpi.kind === "date" ? dateLabel(value) : String(value);
    return el("article", { class: "kpi" },
      el("h4", { text: kpi.label }),
      el("div", { class: "kpi-values" },
        el("div", { class: "kpi-before" }, el("small", { text: "WITHOUT AGENT" }), el("strong", { text: show(kpi.before) }), el("span", { text: kpi.before_note })),
        el("span", { class: "kpi-arrow", "aria-hidden": "true", text: "→" }),
        el("div", { class: "kpi-after" }, el("small", { text: "WITH AGENT" }), el("strong", { text: show(kpi.after) }), el("span", { text: kpi.after_note }))),
      el("p", { class: "kpi-delta", text: kpi.delta }));
  }));
}

// Lot-by-lot Gantt view: one lane for the recorded chronology, one for the projected replay.
function plantTimeline(view) {
  const W = 1100, left = 150, right = 1080;
  const start = Date.UTC(2024, 10, 1), end = Date.UTC(2025, 11, 1);
  const x = t => left + (Date.parse(t) - start) / (end - start) * (right - left);
  const rowH = 30, laneGap = 62, top = 46;
  const lots = view.lots;
  const laneH = lots.length * rowH + 40;
  const lane2 = top + laneH + laneGap;
  const H = lane2 + laneH + 34;
  const svg = svgNode("svg", { viewBox: `0 0 ${W} ${H}`, class: "plant-timeline", role: "img",
    "aria-label": "Timeline of each flagged lot without and with the agent" });
  const esc = x(view.escalation.time), rec = x(view.recognized.time);
  // Month grid
  for (let m = 0; m <= 13; m++) {
    const t = Date.UTC(2024, 10 + m, 1), px = left + (t - start) / (end - start) * (right - left);
    svg.append(svgNode("line", { x1: px, x2: px, y1: top - 10, y2: H - 26, stroke: "#eef1ec" }));
    if (m < 13) svg.append(svgNode("text", { x: px + 4, y: H - 10, class: "tl-month" },
      new Intl.DateTimeFormat("en-US", { month: "short", timeZone: "UTC" }).format(t) + (m === 2 || m === 0 ? ` ’${String(new Date(t).getUTCFullYear()).slice(2)}` : "")));
  }
  function lane(y0, title, sub, projected) {
    svg.append(svgNode("rect", { x: 8, y: y0 - 26, width: W - 16, height: laneH + 8, rx: 10, fill: projected ? "#f3f8f2" : "#fbf6f3", stroke: projected ? "#cfe2d0" : "#efdcd2" }));
    svg.append(svgNode("text", { x: 22, y: y0 - 6, class: "tl-lane" }, title), svgNode("text", { x: 22 + title.length * 7.6 + 10, y: y0 - 6, class: "tl-sub" }, sub));
    lots.forEach((lot, i) => {
      const y = y0 + 22 + i * rowH;
      svg.append(svgNode("text", { x: 22, y: y + 4, class: "tl-lot" }, lotName(lot.batch)),
        svgNode("text", { x: 82, y: y + 4, class: "tl-sub" }, `${lot.excursion.value.toFixed(2)}× limit`));
      const ex = x(lot.excursion.time), rel = x(lot.released), ship = x(lot.shipped);
      const held = projected && lot.projected === "held";
      svg.append(svgNode("line", { x1: ex, x2: held ? ex + 6 : rel, y1: y, y2: y, stroke: "#b9c2b9", "stroke-width": 4, "stroke-linecap": "round" }));
      if (held) {
        svg.append(svgNode("line", { x1: ex + 12, x2: right, y1: y, y2: y, stroke: "#14795c", "stroke-width": 3, "stroke-dasharray": "2 5", "stroke-linecap": "round" }));
        const g = svgNode("g", { transform: `translate(${ex + 12},${y - 9})` });
        g.append(svgNode("rect", { width: 52, height: 18, rx: 9, fill: "#14795c" }), svgNode("text", { x: 26, y: 12.5, "text-anchor": "middle", class: "tl-pill" }, "ON HOLD"));
        g.append(svgNode("title", {}, `${lotName(lot.batch)} held for a QA decision from ${short(view.escalation.time)} (projected)`));
        svg.append(g);
      } else {
        svg.append(svgNode("line", { x1: rel, x2: ship, y1: y, y2: y, stroke: "#d8b9a8", "stroke-width": 4 }),
          svgNode("line", { x1: ship, x2: right, y1: y, y2: y, stroke: "#c4553b", "stroke-width": 4, opacity: .55 }));
        const r = svgNode("circle", { cx: rel, cy: y, r: 4, fill: "white", stroke: "#8e978e", "stroke-width": 2 });
        r.append(svgNode("title", {}, `Released ${short(lot.released)} after passing final tests`));
        const s = svgNode("path", { d: `M${ship - 5},${y - 6} L${ship + 5},${y} L${ship - 5},${y + 6} Z`, fill: "#c4553b" });
        s.append(svgNode("title", {}, `First shipment ${short(lot.shipped)}`));
        svg.append(r, s);
        if (projected) {
          const f = svgNode("g", { transform: `translate(${esc + 8},${y - 9})` });
          f.append(svgNode("rect", { width: 150, height: 18, rx: 9, fill: "#fff3dc", stroke: "#e2c483" }),
            svgNode("text", { x: 75, y: 12.5, "text-anchor": "middle", class: "tl-pill amber" }, "SHIPPED · FLAGGED TO QA"));
          f.append(svgNode("title", {}, `Already shipped ${short(lot.shipped)}, two days before the repeat pattern existed. Flagged for QA market-action review ${short(view.escalation.time)} (projected).`));
          svg.append(f);
        }
      }
      const dot = svgNode("circle", { cx: ex, cy: y, r: 6.5, fill: "#c4553b", stroke: "white", "stroke-width": 2 });
      dot.append(svgNode("title", {}, `${lotName(lot.batch)} · upstream bioburden ${lot.excursion.value.toFixed(2)}× action limit · ${short(lot.excursion.time)}`));
      svg.append(dot);
    });
  }
  lane(top, "Without the agent", "· what was recorded", false);
  lane(lane2, "With the agent", "· projected replay, same data", true);
  // Recorded lane: complaint + recall
  const lane1Bottom = top + laneH - 18;
  const marks = [[view.recognized.time, "Complaint", "#9a3d2a", 0], [view.recall?.time, "Recall · 3 lots", "#9a3d2a", 14]];
  marks.filter(m => m[0]).forEach(([t, label, color, dy]) => {
    const px = x(t);
    svg.append(svgNode("line", { x1: px, x2: px, y1: top - 4, y2: lane1Bottom, stroke: color, "stroke-width": 1.5, "stroke-dasharray": "3 3" }),
      svgNode("text", { x: px - 4, y: lane1Bottom + 12 + dy, "text-anchor": "end", class: "tl-mark" }, `${label} · ${short(t)}`));
  });
  // Projected lane: escalation line
  const lane2Bottom = lane2 + laneH - 18;
  svg.append(svgNode("line", { x1: esc, x2: esc, y1: lane2 - 4, y2: lane2Bottom, stroke: "#14795c", "stroke-width": 2 }),
    svgNode("text", { x: esc + 6, y: lane2Bottom + 12, class: "tl-mark green" }, `Agent links ${view.escalation.batches.map(lotName).join(" + ")} and escalates to QA · ${short(view.escalation.time)}`));
  // Lead-time bracket between lanes
  const by = top + laneH + laneGap / 2 - 4;
  svg.append(svgNode("path", { d: `M${esc},${by - 6} V${by} H${rec} V${by - 6}`, fill: "none", stroke: "#14795c", "stroke-width": 1.5 }),
    svgNode("rect", { x: (esc + rec) / 2 - 92, y: by - 10, width: 184, height: 20, rx: 10, fill: "#14795c" }),
    svgNode("text", { x: (esc + rec) / 2, y: by + 4, "text-anchor": "middle", class: "tl-pill big" }, `${view.lead_days} days earlier warning`));
  const cursor = svgNode("g", { class: "tl-cursor", visibility: "hidden" });
  const cursorLine = svgNode("line", { y1: top - 30, y2: H - 26, stroke: "#d49236", "stroke-width": 2 });
  const cursorLabel = svgNode("text", { y: top - 32, "text-anchor": "middle", class: "tl-cursor-label" });
  cursor.append(cursorLine, cursorLabel);
  svg.append(cursor);
  return {
    node: el("div", { class: "plant-timeline-wrap" }, svg),
    setCursor(time) {
      if (!time) { cursor.setAttribute("visibility", "hidden"); return; }
      const px = Math.max(left, Math.min(right, x(time)));
      cursorLine.setAttribute("x1", px); cursorLine.setAttribute("x2", px);
      cursorLabel.setAttribute("x", Math.max(left + 50, Math.min(right - 50, px))); cursorLabel.textContent = `Replay checkpoint · ${short(time)}`;
      cursor.setAttribute("visibility", "visible");
    },
  };
}

function lotOutcomes(view) {
  const projectedText = lot => lot.projected === "held"
    ? { cls: "good", status: "Held before release", text: `On hold from ${short(lot.excursion.time > view.escalation.time ? lot.excursion.time : view.escalation.time)} until QA decides. Not shipped.` }
    : { cls: "warn", status: "Already shipped · flagged", text: `Shipped ${short(lot.shipped)}, before a repeat pattern existed. Flagged to QA for market-action review on ${short(view.escalation.time)} — ${view.lead_days} days before the complaint.` };
  return el("div", { class: "lot-outcomes" }, view.lots.map(lot => {
    const after = projectedText(lot);
    return el("article", { class: "lot-card" },
      el("header", {}, el("strong", { text: lotName(lot.batch) }), el("span", { text: `${lot.line} · upstream bioburden ${lot.excursion.value.toFixed(2)}× action limit on ${short(lot.excursion.time)}` })),
      el("div", { class: "lot-sides" },
        el("div", { class: "lot-side bad" }, el("small", { text: "WITHOUT AGENT" }), el("b", { text: "Released & shipped" }),
          el("p", { text: `Passed final tests, released ${short(lot.released)}, shipped ${short(lot.shipped)}.${lot.complaint ? ` Customer complaint ${short(lot.complaint)}.` : ""}` })),
        el("div", { class: `lot-side ${after.cls}` }, el("small", { text: "WITH AGENT" }), el("b", { text: after.status }), el("p", { text: after.text }))));
  }));
}

function plantView(data, timeline) {
  const view = data.plant_view;
  return el("div", { class: "plant-view" },
    kpiBand(view),
    el("div", { class: "plant-block" },
      el("div", { class: "block-head" }, el("p", { class: "eyebrow", text: "01 / THE SAME YEAR, TWO WAYS" }),
        el("h3", { text: "Every flagged lot, without and with the agent" }),
        el("p", { text: "Red dots are upstream bioburden failures. Without the agent, each lot passed its final tests and shipped (red line = in the market). With the agent, the second failure is linked to the first and the lots still in the plant are held." })),
      timeline.node,
      el("ul", { class: "tl-legend" },
        el("li", {}, el("i", { class: "lg-dot" }), "Upstream failure"),
        el("li", {}, el("i", { class: "lg-rel" }), "Released"),
        el("li", {}, el("i", { class: "lg-ship" }), "Shipped / in market"),
        el("li", {}, el("i", { class: "lg-hold" }), "Held for QA decision"))),
    el("div", { class: "plant-block" },
      el("div", { class: "block-head" }, el("p", { class: "eyebrow", text: "02 / LOT BY LOT" }),
        el("h3", { text: "What happens to each flagged lot" })),
      lotOutcomes(view)),
    el("div", { class: "assumption-strip" }, el("strong", { text: "How to read this projection" }),
      el("ul", {}, view.assumptions.map(text => el("li", { text })))));
}

function incidentWorkspace(data, setStage) {
  let selected = Math.min(1, data.stages.length - 1);
  const body = el("div", { class: "investigation-workspace" });
  const checkpoints = el("div", { class: "checkpoint-nav", role: "group", "aria-label": "Evidence available at each checkpoint" });
  const focus = el("div", { "aria-live": "polite" });
  const buttons = data.stages.map((stage, index) => {
    const button = el("button", { type: "button", class: "checkpoint" },
      el("small", { text: dateLabel(stage.time) }), el("strong", { text: stage.label }));
    button.addEventListener("click", () => select(index));
    checkpoints.append(button);
    return button;
  });
  function select(index) {
    selected = index; setStage(index);
    buttons.forEach((b, i) => b.setAttribute("aria-pressed", String(i === selected)));
    const stage = data.stages[index], comparison = stage.comparison, records = stage.source_records || [];
    const evidence = comparison.evidence;
    const sources = el("div", { class: "records-list" }, records.map(recordDetails));
    const labButtons = evidence.map(record => {
      const button = el("button", { type: "button", class: "signal-select" }, el("strong", { text: record.batch }),
        el("span", { text: `${record.value.toFixed(2)} × action limit` }), el("small", { text: `${record.id} · inspect record ↗` }));
      button.addEventListener("click", () => {
        const target = [...sources.children].find(n => n.querySelector("summary strong")?.textContent === record.id);
        if (target) { target.open = true; target.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth", block: "nearest" }); target.querySelector("summary").focus(); }
      });
      return button;
    });
    const next = el("div", { class: "decision-summary" },
      el("p", { class: "eyebrow", text: "PROPOSED IMPROVEMENT · MODELED REPLAY" }),
      el("h3", { text: comparison.change }), el("p", { text: comparison.with.decision }),
      el("div", { class: "decision-comparison" },
        el("div", {}, el("h4", { text: "Recorded case actions" }), el("p", { text: comparison.without.decision })),
        el("div", {}, el("h4", { text: "Connected investigation" }), el("p", { text: comparison.with.scope }))),
      el("div", { class: "uncertainty-box" }, el("strong", { text: "What this does—and does not—establish" }),
        el("p", { text: `${evidence.length > 1 ? "Repeated upstream excursions warrant investigating recurrence." : "One upstream excursion warrants investigation; recurrence is not yet established."} Where available, passing release tests are counter-evidence to a simple claim of final-product failure. A common contamination source is not established.` }),
        el("p", { text: comparison.without.qualification })),
      el("h4", { text: "Human next step" }), el("p", { text: "QA and Microbiology review the affected batches, test methods, organism identification and shared operating conditions before deciding on scope or disposition." }));
    focus.replaceChildren(
      el("div", { class: "workspace-heading" }, el("p", { class: "eyebrow", text: `EVIDENCE CUTOFF · ${dateLabel(stage.time)}` }),
        el("h3", { text: evidence.length > 1 ? `${evidence.length} affected batches. A recurring signal.` : "First excursion. Recurrence is not established." }),
        el("p", { text: "Select a batch to inspect its record. Later evidence is excluded from this checkpoint." })),
      el("div", { class: "signal-plot" }, el("p", { class: "source-caption", text: "Upstream bioburden · normalized action-limit ratios · synthetic measurements" }),
        plotSeries([{ label: "Upstream signal", points: evidence.map(r => [Date.parse(r.time), r.value]), labels: evidence.map(r => r.batch) }], { title: "Visible upstream bioburden signals against the action limit", limit: 1, dates: true, scatter: true }),
        el("div", { class: "signal-choices" }, labButtons)),
      el("div", { class: "investigation-columns" }, el("div", {}, el("p", { class: "eyebrow", text: "SOURCE EVIDENCE · INCLUDING RELEASE TESTS AND DEVIATIONS" }), sources), next));
  }
  body.append(checkpoints, focus);
  if (selected >= 0) select(selected);
  else focus.append(el("p", { class: "empty", text: "No recorded evidence checkpoints are available." }));
  return body;
}

function choWorkspace(data) {
  const body = el("div", { class: "investigation-workspace" });
  body.append(el("div", { class: "workspace-heading" }, el("p", { class: "eyebrow", text: "THE EVERYDAY ENGINEERING WORKLOAD" }),
    el("h3", { text: data.workload.records }), el("p", { text: "Different sheets, sampling rates and measurement units. Inspect the original workbook excerpts before looking at the reconstructed comparison." })));
  const previews = data.source_previews || [];
  const input = el("div", { class: "source-preview" });
  const select = el("select", { "aria-label": "Workbook and worksheet excerpt" }, previews.map((p, i) => el("option", { value: i, text: `${p.file} / ${p.sheet}` })));
  const tableWrap = el("div", { class: "table-scroll" });
  function showPreview() {
    const source = previews[Number(select.value)];
    if (!source) { tableWrap.replaceChildren(el("p", { text: "Source inventory unavailable." })); return; }
    tableWrap.replaceChildren(el("p", { class: "source-caption", text: `${source.rows?.toLocaleString() || "Unknown"} observed rows · actual workbook excerpt from recorded inventory` }),
      el("table", { class: "source-table" }, el("tbody", {}, source.preview.map((row, i) => el("tr", {}, row.map(value => el(i ? "td" : "th", { text: value ?? "—" })))))));
  }
  select.addEventListener("change", showPreview);
  input.append(el("p", { class: "eyebrow", text: "01 / RAW SOURCE FILES" }), select, tableWrap); showPreview();
  body.append(input);
  body.append(el("div", { class: "preparation-result" }, el("p", { class: "eyebrow", text: "02 / RECORDED PREPARATION · CONVENTIONAL PIPELINE" }),
    el("div", { class: "preparation-stats" }, (data.reconstruction || []).map(m => el("div", {}, el("strong", { text: m.traditional.display }), el("small", { text: m.label })))),
    el("p", { text: "These results belong to the conventional reconstruction pipeline. They establish a reference for evaluating OS preparation; they do not establish an OS advantage or zero setup effort." })));
  const observation = data.observation;
  if (observation?.variables?.length) {
    const comparison = el("div", { class: "cultivation-comparison" });
    const variable = el("select", { "aria-label": "EXP008 measurement" }, observation.variables.map(v => el("option", { value: v.variable, text: v.variable })));
    const plot = el("div", { class: "signal-plot", "aria-live": "polite" });
    let revision = 0;
    async function refresh() {
      const current = ++revision, name = variable.value;
      plot.replaceChildren(el("p", { text: "Loading recorded trajectories…" }));
      try {
        const pair = await Promise.all(["R01", "R02"].map(async reactor => {
          const response = await fetch(`/api/case-comparison/cho/series?cultivation=EXP008_batch_${reactor}&variables=${encodeURIComponent(name)}&max_points=240`);
          if (!response.ok) throw new Error("Recorded series unavailable");
          const result = await response.json();
          return { label: reactor, points: result.variables[name]?.points || [] };
        }));
        if (revision !== current) return;
        plot.replaceChildren(plotSeries(pair, { title: `${name} · EXP008 reactor pair over cultivation time` }),
          el("p", { class: "source-caption", text: "R01 green · R02 blue · time in hours · publication-aligned evaluation references, downsampled for display" }));
      } catch (error) { if (revision === current) plot.replaceChildren(el("p", { text: error.message })); }
    }
    variable.addEventListener("change", refresh);
    comparison.append(el("p", { class: "eyebrow", text: "03 / INSPECT A CULTIVATION DIFFERENCE · EVALUATION REFERENCE" }),
      el("h3", { text: "Same experiment. Two reactor trajectories." }), variable, plot,
      el("p", { text: "These descriptive differences show what an engineering comparison must explain. They are reference observations, not agent discoveries, causal drivers or optimization recommendations." }));
    body.append(comparison); refresh();
  }
  body.append(el("div", { class: "uncertainty-box" }, el("strong", { text: "What still needs an engineer—and measurement" }),
    el("p", { text: "Validate identity, units and time alignment; check the comparison; investigate confounding; review the final finding. OS setup, manual corrections and verification time are not yet recorded. Run the agent below to produce a separate investigation for review." })));
  return body;
}

function measurementPanel(data) {
  const measurement = data.productivity;
  const sides = ["traditional", "ai"].map(workflow => {
    const value = measurement.sides[workflow];
    return el("div", { class: "measured-side" },
      el("small", { text: workflow === "ai" ? "WITH OS" : "WITHOUT OS" }),
      el("strong", { text: value.value == null ? "Not measured" : `${value.value.toFixed(3)} human h / qualified case` }),
      el("p", { text: value.value == null ? "Needs a reviewed deliverable and a complete human-effort log." : `${value.correctly_completed}/${value.assigned} accepted deliverables; total effort includes every attempted case.` }));
  });
  return el("section", { class: "improvements" },
    el("div", { class: "improvements-heading" }, el("h3", { text: "What benefit is actually measured?" }), el("a", { href: `/benchmark#${data.id}`, text: "Evidence & methodology ↗" })),
    el("p", { class: "measurement-label", text: measurement.label }),
    el("div", { class: "measured-sides" }, sides),
    el("p", { class: "improvement-note", text: measurement.detail }),
    el("p", { class: "measurement-explanation", text: data.measurement_note }));
}

function renderCase(data, index) {
  let selectedStage = data.id === "cho" ? 2 : 1;
  const section = el("section", { class: "case-section", id: data.id, "aria-labelledby": `${data.id}-title` });
  section.append(el("header", { class: "case-head" },
    el("div", { class: "case-meta" }, el("p", { class: "eyebrow", text: `CASE 0${index + 1} / ${data.name}` }), el("span", { class: "basis", text: data.badge })),
    el("h2", { id: `${data.id}-title`, text: data.title }), el("p", { class: "case-intro", text: data.intro })));
  if (data.id === "fresenius" && data.plant_view) {
    const timeline = plantTimeline(data.plant_view);
    section.append(plantView(data, timeline),
      el("div", { class: "block-head replay-head" }, el("p", { class: "eyebrow", text: "03 / REPLAY IT YOURSELF" }),
        el("h3", { text: "What the plant knew on each date" }),
        el("p", { text: "Pick a checkpoint. Only evidence available on that date is shown, and the orange line moves on the timeline above." })),
      incidentWorkspace(data, value => { selectedStage = value; timeline.setCursor(data.stages[value]?.time); }));
  } else section.append(data.id === "fresenius" ? incidentWorkspace(data, value => { selectedStage = value; }) : choWorkspace(data));
  section.append(liveAgentPanel(data, () => selectedStage), measurementPanel(data));
  return section;
}

function liveAgentPanel(data, getStage) {
  const button = el("button", { type: "button", class: "play-button run-agent", text: "↗ Run agent", "aria-label": `Run agent for ${data.name}` });
  const status = el("p", { class: "agent-status", role: "status", text:
    data.agent?.available ? (data.id === "fresenius" ? "Run a live investigation using evidence available at the selected milestone." : "Run a live investigation on the raw CHO workbooks.") : (data.agent?.reason || "Agent connection unavailable.") });
  const result = el("div", { class: "agent-result", hidden: "" });
  const panel = el("div", { class: "live-agent-panel" }, el("div", { class: "live-agent-actions" }, button, status), result);
  button.disabled = !data.agent?.available;
  const storageKey = `lotic-demo-run-${data.id}`;
  const storage = {
    get() { try { return localStorage.getItem(storageKey); } catch { return null; } },
    set(value) { try { localStorage.setItem(storageKey, value); } catch {} },
  };
  let polling = false;
  async function request(url, options) {
    const response = await fetch(url, options);
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || `Request failed (${response.status})`);
    return body;
  }
  function show(job) {
    const running = ["queued", "running"].includes(job.status);
    button.disabled = running || !data.agent?.available;
    button.textContent = running ? "Agent running…" : job.status === "completed" ? "↗ Run again" : "↗ Run agent";
    status.textContent = job.error ? `Run failed: ${job.error}` : job.phase;
    if (job.result) {
      result.removeAttribute("hidden");
      result.replaceChildren(el("p", { class: "eyebrow", text: "LIVE AGENT RESULT · HUMAN REVIEW REQUIRED" }),
        el("h3", { text: job.result.report_status === "complete_for_available_evidence" ? "Available evidence reviewed · scientific review required" : "Partial investigation · work remains" }),
        el("p", { text: job.result.assessment || "The agent submitted an investigation report." }),
        el("p", { class: "agent-counts", text: `${job.result.evidence_count} evidence references · ${job.result.hypotheses.length} hypotheses · ${job.result.open_questions.length} open questions` }));
      const review = job.result.investigation_review || {};
      result.append(el("p", { class: "agent-counts", text: `${review.screened_unit_count ?? "Unknown"} units screened · ${review.reviewed_unit_count ?? "Unknown"} reviewed · ${review.cited_unit_count ?? "Unknown"} cited` }));
      if (job.result.cross_scope_synthesis) result.append(el("h4", { text: "Across the reviewed sources" }), el("p", { text: job.result.cross_scope_synthesis }));
      if (review.coverage?.length) result.append(el("details", {}, el("summary", { text: "Coverage and unresolved work by entity" }),
        el("ul", {}, review.coverage.map(unit => el("li", { text: `${unit.entity_id || unit.source_id}: ${unit.status.replaceAll("_", " ")} — ${unit.reason}` })))));
      for (const [key, title] of [["observed_facts", "Source observations"], ["interpretations", "Interpretations requiring review"]]) {
        const items = job.result[key] || [];
        if (items.length) result.append(el("details", {}, el("summary", { text: `${title} (${items.length})` }),
          el("ul", {}, items.slice(0, 8).map(item => el("li", { text: `${item.statement} · ${(item.evidence_ids || []).length} source references` }))),
          ...(items.length > 8 ? [el("p", { text: `Showing 8 of ${items.length}; complete findings are retained in the investigation artifact.` })] : [])));
      }
      result.append(el("p", { class: "improvement-note", text: "Machine screening is not investigator review. Citations and calculations do not prove causation; hypothesis probabilities are not statistically calibrated." }));
      if (job.result.open_questions.length) {
        result.append(el("h4", { text: "Open questions" }), el("ul", {}, job.result.open_questions.map(question => el("li", { text: typeof question === "string" ? question : question.question || JSON.stringify(question) }))));
      }
      result.append(el("p", { class: "improvement-note", text: "This live run is separate from the modeled timeline and benchmark scores." }));
    }
    return running;
  }
  async function poll(id) {
    if (polling) return;
    polling = true;
    try {
      let running = true;
      while (running) {
        running = show(await request(`/api/demo/runs/${encodeURIComponent(id)}`));
        if (running) await new Promise(resolve => setTimeout(resolve, 2000));
      }
    } catch (error) {
      status.textContent = `Could not refresh the run: ${error.message}. Reload to reconnect.`;
      button.disabled = !data.agent?.available;
      button.textContent = "↗ Run agent";
    } finally { polling = false; }
  }
  button.addEventListener("click", async () => {
    button.disabled = true;
    status.textContent = "Starting agent…";
    result.setAttribute("hidden", "");
    try {
      const job = await request(`/api/demo/${data.id}/runs`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ milestone: getStage() }),
      });
      storage.set(job.id);
      show(job);
      await poll(job.id);
    } catch (error) {
      status.textContent = `Could not start the agent: ${error.message}`;
      button.disabled = !data.agent?.available;
      button.textContent = "↗ Run agent";
    }
  });
  const previous = storage.get();
  if (previous) poll(previous);
  return panel;
}

async function init() {
  const root = document.getElementById("demoRoot");
  try {
    const response = await fetch("/api/demo");
    if (!response.ok) throw new Error(`Request failed (${response.status})`);
    let data = await response.json();
    // A running agent can keep an older server process alive during a UI update.
    // Use the generated story for the new layout without interrupting that run.
    if (data.cases.some(item => item.presentation_version !== 7)) {
      const storyResponse = await fetch("/assets/demo-story.json?v=7");
      if (!storyResponse.ok) throw new Error("Updated demo story unavailable");
      const story = await storyResponse.json();
      data = { cases: story.cases.map(item => ({ ...item, agent: data.cases.find(previous => previous.id === item.id)?.agent })) };
    }
    root.replaceChildren(...data.cases.map(renderCase));
  } catch (error) {
    root.replaceChildren(el("div", { class: "error-card", role: "alert" },
      el("strong", { text: "The demo could not load. " }), error.message,
      el("button", { type: "button", id: "retryDemo", text: "Try again" })));
    document.getElementById("retryDemo").addEventListener("click", init);
  } finally {
    root.setAttribute("aria-busy", "false");
  }
}
init();
