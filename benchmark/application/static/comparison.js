/* Benchmark case comparison dashboard.
   Reads the /api/case-comparison endpoints; renders only recorded values.
   Evidence classification vocabulary mirrors benchmark/case_comparison/scorecard.py. */
"use strict";

const CLASSIFICATIONS = {
  verified: "Checked against an independent ground truth or the published source.",
  observed: "Directly measured in the dataset or recorded in execution logs.",
  modeled: "Produced by the documented simulation or workflow assumptions.",
  predicted: "Estimated by a model and not experimentally confirmed.",
  not_measured: "No recorded benchmark output supports this value.",
};

const DIFFERENCE_CATEGORIES = {
  evidence_first: "Earlier AI evidence",
  one_sided_evidence: "One-sided evidence",
  missed_evidence: "Missed evidence",
  eliminated_steps: "Eliminated / accelerated steps",
  hypotheses: "Hypotheses",
  escalation_timing: "Escalation timing",
  decisions: "Decision correctness",
  human_intervention: "Human intervention",
  unsupported_conclusions: "Unsupported AI conclusions",
  found_by_traditional_only: "Recorded only by the traditional workflow",
  reference_observation: "Descriptive reference observation",
};

const state = {
  index: null,
  caseId: null,
  payload: null,
  view: "compare",
  differencesOnly: false,
  replay: {
    events: [], duration: 0, cursor: 0, playing: false, speed: 32, timer: null,
  },
  presentation: { active: false, step: 0 },
};

/* ---------------------------------------------------------------- helpers */
async function fetchJSON(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${url} → ${response.status}`);
  return response.json();
}

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on") && typeof value === "function") node.addEventListener(key.slice(2), value);
    else if (value === true) node.setAttribute(key, "");
    else if (value !== false && value != null) node.setAttribute(key, value);
  }
  for (const child of children.flat()) {
    if (child == null || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); return node; }

function chip(label, kind) {
  return el("span", { class: `chip ${kind || ""}`, text: label, title: CLASSIFICATIONS[kind] || "" });
}

function classificationChip(side) {
  return chip(side.classification_label || side.classification, side.classification);
}

function statusChip(status) {
  const label = status.label || status.status;
  return chip(label, `status-${status.status}`);
}

function fmtSecondsTotal(seconds) {
  if (seconds == null) return "—";
  const abs = Math.abs(seconds);
  if (abs >= 86400) return `${(seconds / 86400).toFixed(1)} days`;
  if (abs >= 3600) return `${(seconds / 3600).toFixed(1)} h`;
  if (abs >= 60) return `${(seconds / 60).toFixed(1)} min`;
  return `${seconds.toFixed(1)} s`;
}

function fmtClock(seconds) {
  if (seconds == null) return "—";
  const sign = seconds < 0 ? "-" : "";
  let rest = Math.abs(seconds);
  const days = Math.floor(rest / 86400); rest -= days * 86400;
  const hours = Math.floor(rest / 3600); rest -= hours * 3600;
  const minutes = Math.floor(rest / 60);
  if (days > 0) return `${sign}${days}d ${String(hours).padStart(2, "0")}h ${String(minutes).padStart(2, "0")}m`;
  return `${sign}${hours}h ${String(minutes).padStart(2, "0")}m`;
}

function fmtTimestamp(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toISOString().replace("T", " ").slice(0, 16) + " UTC";
}

function shortPath(path) { return path ? path.split("/").slice(-2).join("/") : ""; }

/* ------------------------------------------------------------- app loading */
async function init() {
  try {
    state.index = await fetchJSON("/api/case-comparison");
  } catch (error) {
    document.getElementById("caseStatus").innerHTML =
      `<span>CASE STATUS</span><strong>Unavailable</strong><small>${error.message}</small>`;
    return;
  }
  renderClassificationLegend();
  renderCaseSelector();
  renderViewSelector();
  wireToolbar();
  wirePresentation();
  await loadCase(state.index.order[0]);
}

function renderClassificationLegend() {
  const legend = document.getElementById("classificationLegend");
  clear(legend);
  legend.append(chip("Verified", "verified"), chip("Observed", "observed"), chip("Modeled", "modeled"),
    chip("Predicted", "predicted"), chip("Not measured", "not_measured"));
}

function renderCaseSelector() {
  const nav = clear(document.getElementById("caseSelector"));
  for (const [index, item] of state.index.cases.entries()) {
    nav.append(el("button", {
      class: `nav-item ${item.id === state.caseId ? "active" : ""}`,
      onclick: () => loadCase(item.id),
    }, el("span", { text: String(index + 1).padStart(2, "0") }),
      el("b", { text: item.name }),
      el("small", { text: item.kind || "" })));
  }
}

function renderViewSelector() {
  const views = [
    ["compare", "01", "Compare", "Scorecard & differences"],
    ["replay", "02", "Synchronized replay", "Shared clock, two workflows"],
    ["evidence", "03", "Evidence", "Retrieved / used / missed"],
  ];
  const nav = clear(document.getElementById("viewSelector"));
  for (const [id, number, title, subtitle] of views) {
    nav.append(el("button", {
      class: `nav-item ${state.view === id ? "active" : ""}`,
      onclick: () => setView(id),
    }, el("span", { text: number }), el("b", { text: title }), el("small", { text: subtitle })));
  }
}

function setView(view, refreshReplay = true) {
  state.view = view;
  for (const section of document.querySelectorAll("main .view")) section.classList.remove("active");
  document.getElementById(`${view}View`).classList.add("active");
  renderViewSelector();
  if (view === "replay" && refreshReplay) renderReplay();
}

async function loadCase(caseId) {
  stopPlayback();
  state.caseId = caseId;
  state.view = state.view || "compare";
  renderCaseSelector();
  const status = document.getElementById("caseStatus");
  clear(status).append(el("span", { text: "CASE STATUS" }), el("strong", { text: "Loading…" }));
  try {
    state.payload = await fetchJSON(`/api/case-comparison/${caseId}`);
  } catch (error) {
    clear(status).append(el("span", { text: "CASE STATUS" }), el("strong", { text: "Failed" }), el("small", { text: error.message }));
    return;
  }
  renderAll();
}

function renderAll() {
  renderHero();
  renderScorecard();
  renderDifferences();
  renderEffort();
  renderChain();
  renderFindings();
  prepareReplayState();
  renderReplay();
  renderEvidence();
  renderPresentationBar();
  applyDifferencesMode(false);
  setView(state.view, false);
  const status = document.getElementById("caseStatus");
  clear(status).append(
    el("span", { text: "CASE STATUS" }),
    el("strong", { text: state.payload.header.name }),
    el("small", { text: state.payload.header.dataset.label }),
    el("small", { text: `replay: ${state.payload.replay.status}` }),
  );
}

/* ------------------------------------------------------------------- hero */
function renderHero() {
  const { header, scorecard } = state.payload;
  const container = clear(document.getElementById("caseHero"));
  const left = el("article", { class: "panel" },
    el("div", { class: "panel-head" },
      el("div", {}, el("p", { class: "eyebrow", text: `${header.kind.toUpperCase()} · EVIDENCE-BACKED COMPARISON` }),
        el("h2", { text: header.title }))),
    el("div", { class: "panel-body" },
      el("p", { class: "lead", text: header.question }),
      el("div", { class: "case-kicker" },
        chip(`dataset ${header.dataset.version || "recorded"}`, ""),
        header.dataset.fingerprint ? chip(`fingerprint ${String(header.dataset.fingerprint).slice(0, 12)}…`, "") : null),
      el("p", { class: "muted", style: "font-size:12.5px;margin-top:10px", text: scorecard.conclusion || "" })));
  for (const experiment of state.payload.experiments?.experiments || []) {
    left.append(el("div", { class: "panel-body" },
      el("b", { text: `${experiment.id}. ${experiment.label}` }),
      el("p", { text: experiment.objective }),
      el("p", { class: "muted", text: experiment.variants.join(" · ") }),
      el("p", { text: ["traditional", "ai"].map(workflow => {
        const result = experiment.sides[workflow];
        return `${workflow === "ai" ? "AI OS" : "Traditional"}: ${result.value == null ? "Not measured" : `${result.value.toFixed(3)} work units/h; ${result.correctly_completed}/${result.assigned} accepted; ${result.person_hours.toFixed(3)} person-hours`}`;
      }).join(" · ") })));
  }
  const right = el("article", { class: "panel" },
    el("div", { class: "panel-head" }, el("div", {}, el("p", { class: "eyebrow", text: "DATASET & PROVENANCE" }), el("h2", { text: "What this comparison uses" }))),
    el("div", { class: "panel-body" },
      el("div", { class: "dataset-list" },
        el("div", {}, el("b", { text: header.dataset.label })),
        el("div", { text: header.dataset.records || "" }),
        header.dataset.provenance ? el("div", { text: header.dataset.provenance }) : null,
        header.dataset.disclaimer ? el("div", { class: "responsive-note", text: header.dataset.disclaimer }) : null)));
  container.append(left, right);

  const inlineFacts = (header.public_facts || []).concat(header.facts || []);
  if (inlineFacts.length) {
    const facts = el("article", { class: "panel" },
      el("div", { class: "panel-head" }, el("div", {}, el("p", { class: "eyebrow", text: "PUBLIC / SOURCE FACTS" }), el("h2", { text: "Statements this comparison is anchored to" }))),
      el("div", { class: "public-facts" }, inlineFacts.slice(0, 5).map((fact) =>
        el("div", { class: "public-fact" }, el("b", { text: `${fact.id || "FACT"}: ` }), fact.statement || "", fact.source ? el("div", { class: "responsive-note", text: fact.source }) : null))));
    container.append(facts);
  }
}

/* --------------------------------------------------------------- scorecard */
function renderScorecard() {
  const scorecard = state.payload.scorecard;
  const headline = clear(document.getElementById("headlineGrid"));
  for (const metric of scorecard.headline || []) {
    const delta = metric.delta;
    headline.append(el("article", { class: "metric-card" },
      el("div", { class: "metric-label", text: metric.label }),
      el("div", { class: "sides" },
        el("div", { class: "side" }, el("span", { text: "TRADITIONAL" }), el("strong", { text: metric.traditional.display })),
        el("div", { class: "side" }, el("span", { text: "AI OS" }), el("strong", { text: metric.ai.display }))),
      el("div", { class: "delta" },
        delta ? el("span", {}, el("b", { class: delta.verdict, text: `${delta.glyph} ${delta.improvement_percent != null ? `${Math.abs(delta.improvement_percent)}% ` : ""}${delta.verdict}` }),
          ` · Δ ${delta.absolute_change}`) : el("span", { class: "muted", text: "No paired measurement" })),
      el("div", { class: "def", text: metric.definition })));
  }

  const body = clear(document.getElementById("scorecardBody"));
  const table = el("table", { class: "scorecard" });
  table.append(el("thead", {}, el("tr", {},
    el("th", { text: "Metric" }), el("th", { text: "Traditional workflow" }),
    el("th", { text: "AI OS" }), el("th", { text: "Improvement" }))));
  const tbody = el("tbody");
  for (const group of scorecard.groups) {
    tbody.append(el("tr", { class: "group-row" }, el("td", { colspan: "4", text: group })));
    for (const metric of scorecard.metrics.filter((row) => row.group === group)) {
      tbody.append(scorecardRow(metric));
    }
  }
  table.append(tbody);
  body.append(table);
  document.getElementById("scorecardPanel").classList.toggle("hidden", state.differencesOnly);
}

function scorecardRow(metric) {
  const sideCell = (side) => el("td", { class: `value ${side.available ? "" : "missing"}` },
    el("strong", { text: side.display }),
    classificationChip(side),
    side.detail ? el("small", { class: "muted", style: "font-size:11.5px", text: side.detail }) : null);
  const delta = metric.delta;
  return el("tr", {},
    el("td", {}, el("div", { class: "metric-name" }, metric.label,
      el("small", { text: metric.definition }),
      metric.note ? el("small", { class: "muted", text: metric.note }) : null,
      state.differencesOnly ? null : sourceRow(metric.sources))),
    sideCell(metric.traditional),
    sideCell(metric.ai),
    el("td", {}, delta
      ? el("span", {}, el("b", { class: delta.verdict, text: `${delta.glyph} ${delta.absolute_change}` }),
        el("small", { class: "muted", style: "display:block", text: delta.improvement_percent != null ? `${delta.improvement_percent}% vs traditional` : "no percentage (zero baseline)" }))
      : el("span", { class: "muted", text: "—" })));
}

function sourceRow(sources) {
  if (!sources || !sources.length) return null;
  return el("div", { class: "source-list dev-only" }, sources.map((source) =>
    el("code", { text: source.path, title: source.available ? "recorded artifact" : "artifact missing", onclick: () => openSourceDrawer(source) })));
}

/* ------------------------------------------------------------- differences */
function renderDifferences() {
  const panel = document.getElementById("differencesPanel");
  panel.classList.toggle("hidden", !state.differencesOnly);
  const body = clear(document.getElementById("differencesBody"));
  const entries = state.payload.differences || [];
  document.getElementById("differencesCount").textContent = `${entries.length} findings`;
  for (const entry of entries) {
    body.append(el("article", { class: "diff-card" },
      el("header", {},
        chip(DIFFERENCE_CATEGORIES[entry.category] || entry.category, ""),
        chip((entry.classification || "observed").replace("_", " "), entry.classification)),
      el("h3", { text: entry.title }),
      el("p", { text: entry.detail }),
      el("div", { class: "diff-refs dev-only" }, (entry.refs || []).map((ref) =>
        el("button", { onclick: () => openRef(ref) }, el("b", { text: `${ref.kind}: ` }), ref.id, ref.detail ? ` — ${String(ref.detail).slice(0, 80)}` : "")))));
  }
  if (!entries.length) body.append(el("p", { class: "muted", text: "No differences are recorded for this case." }));
}

function openRef(ref) {
  if (ref.kind === "replay_event") {
    setView("replay");
    const event = state.replay.events.find((item) => item.id === ref.id);
    if (event) seekReplay(event.offset_seconds);
    return;
  }
  if (ref.kind === "evidence") {
    const row = (state.payload.evidence.rows || []).find((item) => item.id === ref.id);
    if (row) { setView("evidence"); openEvidenceDrawer(row); return; }
  }
  openDrawer(ref.id, [
    { label: ref.kind.replace("_", " "), text: ref.detail || "Referenced by the recorded benchmark.", },
    { label: "Traceability", text: "Open the referenced artifact in the repository for the full record." },
  ]);
}

/* ------------------------------------------------------------------ effort */
function renderEffort() {
  const effort = state.payload.effort;
  const grid = clear(document.getElementById("effortBody"));

  const phases = el("article", {},
    el("p", { class: "eyebrow", text: "PHASE DURATIONS" }),
    el("table", { class: "plain" },
      el("thead", {}, el("tr", {}, el("th", { text: "Phase" }), el("th", { text: "Traditional" }), el("th", { text: "AI OS" }), el("th", { text: "Class" }))),
      el("tbody", {}, (effort.phase_rows || []).length
        ? effort.phase_rows.map((row) => el("tr", {},
            el("td", { text: row.label }),
            el("td", { text: row.display_traditional }),
            el("td", { text: row.display_ai }),
            el("td", {}, chip(row.classification, row.classification))))
        : el("tr", {}, el("td", { colspan: 4 }, el("span", { class: "muted", text: effort.phase_note || "Phase durations are not recorded for this case." }))))),
    engineerHours(effort),
    el("p", { class: "responsive-note", style: "margin-top:10px", text: effort.basis }));

  const right = el("article", {},
    el("p", { class: "eyebrow", text: "MACHINE EXECUTION (OBSERVED)" }),
    el("table", { class: "plain" }, el("tbody", {}, (effort.machine_execution || []).map((row) =>
      el("tr", {},
        el("td", {}, el("div", {}, row.label), el("small", { class: "muted", text: row.source || "" })),
        el("td", { text: row.display }),
        el("td", {}, chip(row.classification, row.classification)))))),
    (effort.tracked_effects && Object.keys(effort.tracked_effects).length)
      ? el("div", { style: "margin-top:12px" }, el("p", { class: "eyebrow", text: "TRACKED OPERATIONAL EFFECTS (MODELED)" }),
          el("table", { class: "plain" }, el("tbody", {}, Object.entries(effort.tracked_effects).map(([key, value]) =>
            el("tr", {}, el("td", { text: key.replaceAll("_", " ") }), el("td", { text: `${value.traditional} → ${value.ai}` }), el("td", {}, chip(value.classification, value.classification)))))))
      : null,
    el("div", { style: "margin-top:12px" }, el("p", { class: "eyebrow", text: "NOT SUPPORTED BY THE RECORDED BENCHMARK" }),
      el("ul", { class: "unsupported" }, (effort.unsupported_categories || []).map((text) => el("li", { text })))),
    el("p", { class: "responsive-note", style: "margin-top:10px", text: effort.note }));

  grid.append(phases, right);
}

function engineerHours(effort) {
  const hours = effort.engineer_hours || {};
  if (hours.classification === "not_measured") {
    return el("div", { style: "margin-top:12px" },
      el("p", { class: "eyebrow", text: "ENGINEER HOURS" }),
      el("p", { class: "muted", text: hours.reason || "Not measured." }));
  }
  return el("div", { style: "margin-top:12px" },
    el("p", { class: "eyebrow", text: "ENGINEER HOURS" }),
    el("table", { class: "plain" }, el("tbody", {},
      el("tr", {}, el("td", { text: "Total (per investigation)" }), el("td", { text: `${hours.per_investigation_traditional} h → ${hours.per_investigation_ai} h` }), el("td", {}, chip(hours.classification || "modeled", hours.classification || "modeled"))),
      el("tr", {}, el("td", { text: "Campaign total" }), el("td", { text: `${hours.total_traditional} h → ${hours.total_ai} h` }), el("td", {}, chip(hours.classification || "modeled", hours.classification || "modeled"))))));
}

/* -------------------------------------------------------------- issue chain */
function renderChain() {
  const chain = state.payload.issue_chain;
  const body = clear(document.getElementById("chainBody"));
  const moment = document.getElementById("chainMoment");
  const eyebrow = document.getElementById("chainEyebrow");
  if (chain.status === "ok") {
    eyebrow.textContent = "ISSUE IDENTIFIED CHAIN · RECORDED REPLAY MOMENT";
    moment.textContent = `cursor ${chain.moment.cursor} · ${fmtTimestamp(chain.moment.cutoff)}`;
    body.append(...freseniusChain(chain));
  } else {
    eyebrow.textContent = state.caseId === "cho" ? "INVESTIGATION CHAIN · PARTIAL" : "ISSUE IDENTIFIED CHAIN";
    moment.textContent = chain.status;
    body.append(...choChain(chain));
  }
}

function chainStep(label, ...children) {
  return el("div", { class: "chain-step" }, el("div", { class: "step-label", text: label }), el("div", { class: "step-body" }, children));
}

function freseniusChain(chain) {
  const steps = [];
  steps.push(chainStep("Evidence", el("strong", { text: chain.issue.title }),
    el("div", { class: "stat", text: `${chain.issue.severity?.toUpperCase()} · ${chain.issue.triage_level} · ${chain.evidence_available.count} records existed at the cutoff` }),
    el("div", { class: "chain-evidence" }, chain.supporting_evidence.slice(0, 8).map((card) =>
      el("button", { text: card.id, title: card.summary, onclick: () => openDrawer(card.id, [
        { label: card.type || "record", text: card.summary }, { label: "timestamp", text: fmtTimestamp(card.timestamp) },
        { label: "traceability", text: "Record visible in the deterministic agent state at this cursor (visible_state())." },
      ]) }))),
    el("button", { class: "text-button", text: `Inspect all ${chain.evidence_available.count} evidence records at this moment`, onclick: () => openEvidenceMoment(chain) })));
  steps.push(chainStep("Batches", el("div", { class: "stat", text: `${chain.related_records.length} incident-related records visible (batches, deviations, process events, labs)` }),
    el("div", { class: "chain-evidence" }, [...new Set(chain.related_records.map((card) => card.batch_id).filter(Boolean))].map((batch) =>
      el("button", { text: batch, onclick: () => openDrawer(batch, chain.related_records.filter((card) => card.batch_id === batch).slice(0, 12).map((card) => ({ label: `${card.type} · ${fmtTimestamp(card.timestamp)}`, text: card.summary }))) })))));
  steps.push(chainStep("Hypotheses", ...chain.competing_hypotheses.map((hypothesis) =>
    el("div", {}, el("strong", { text: `${hypothesis.title} (${(hypothesis.confidence * 100).toFixed(0)}%)` }),
      el("div", { class: "stat", text: `supporting ${hypothesis.supporting_evidence_ids.length} · contradicting ${hypothesis.contradicting_evidence_ids.length} evidence records` })))));
  steps.push(chainStep("Missing info", ...chain.missing_information.map((text) => el("div", { class: "stat", text }))));
  steps.push(chainStep("Recommended", ...chain.recommended_investigation.map((action) =>
    el("div", {}, el("strong", { text: action.action }),
      el("div", { class: "stat", text: `${action.priority || "priority n/a"} · owner ${action.owner || "unassigned"}${action.requires_human_approval ? " · requires human approval" : ""}` })))));
  steps.push(chainStep("Escalation", el("strong", { text: chain.escalation_decision.decision }),
    el("div", { class: "stat", text: chain.escalation_decision.authority })));
  return steps;
}

function choChain(chain) {
  if (chain.status !== "partial") {
    return [el("div", { class: "chain-step muted-step" },
      el("div", { class: "step-label", text: "Not measured" }),
      el("div", { class: "step-body" }, el("strong", { text: "No investigation chain is recorded." }), el("div", { class: "stat", text: chain.reason || "" })))];
  }
  const observation = chain.observation;
  return [
    chainStep("Difference", el("strong", { text: observation.difference }),
      el("div", { class: "stat", text: `classification: ${observation.classification}${observation.flags && observation.flags.length ? ` · flags: ${observation.flags.join(", ")}` : ""}` })),
    chainStep("Variables", ...observation.variables.slice(0, 6).map((item) =>
      el("div", { class: "stat", text: `${item.variable}: Δ ${item.normalized_delta.toFixed(3)}${item.flags && item.flags.length ? ` (${item.flags.join(", ")})` : ""}` }))),
    chainStep("Hypotheses", el("strong", { class: "muted", text: "Not measured" }), el("div", { class: "stat", text: observation.hypotheses.reason })),
    chainStep("Supporting", el("div", { class: "stat", text: (observation.supporting_evidence.records || []).join(" · ") }),
      el("div", { class: "stat", text: observation.supporting_evidence.detail })),
    chainStep("Contradictory", el("strong", { class: "muted", text: "Not measured" }), el("div", { class: "stat", text: observation.contradictory_evidence.reason })),
    chainStep("Next analysis", el("strong", { class: "muted", text: "Not recorded" }), el("div", { class: "stat", text: observation.next_analysis.reason })),
  ];
}

function openEvidenceMoment(chain) {
  const blocks = chain.evidence_available.records.slice(0, 60).map((card) => ({
    label: `${card.type} · ${fmtTimestamp(card.timestamp)}`,
    text: `${card.id} — ${card.summary}`,
  }));
  if (chain.evidence_available.truncated) {
    blocks.push({ label: "note", text: `Preview limited to ${chain.evidence_available.preview_limit} of ${chain.evidence_available.count} records; the full state is reproducible from the incident-demo assessment endpoint with cursor ${chain.moment.cursor}.` });
  }
  openDrawer(`Evidence at ${fmtTimestamp(chain.moment.cutoff)}`, blocks);
}

/* ---------------------------------------------------------------- findings */
function renderFindings() {
  const presentation = state.payload.presentation;
  const container = clear(document.getElementById("findingsBody"));
  const groups = [
    ["Verified", presentation.verified_findings || [], "verified"],
    ["Observed / modeled", presentation.modeled_findings || [], "modeled"],
    ["Not measured / unavailable", presentation.unavailable_findings || [], "not_measured"],
    ["Limitations", presentation.limitations || [], ""],
  ];
  for (const [title, items, kind] of groups) {
    container.append(el("article", {},
      el("p", { class: "eyebrow", text: title }),
      items.length ? el("ul", { class: "findings-list" }, items.map((text) => el("li", {}, text, kind ? " " : null, kind ? chip(kind.replace("_", " "), kind) : null)))
        : el("p", { class: "muted", text: "None recorded." })));
  }
}

/* ------------------------------------------------------------------ replay */
function prepareReplayState() {
  stopPlayback();
  const replay = state.payload.replay;
  state.replay.cursor = 0;
  state.replay.duration = 0;
  state.replay.events = [];
  if (replay.status !== "ok") return;
  const events = [];
  for (const event of replay.tracks.traditional) events.push({ ...event, track: "traditional" });
  for (const event of replay.tracks.ai) events.push({ ...event, track: "ai" });
  events.sort((a, b) => (a.offset_seconds ?? 0) - (b.offset_seconds ?? 0));
  state.replay.events = events;
  state.replay.duration = replay.clock.duration_seconds || (events.length ? events[events.length - 1].offset_seconds : 0);
}

function renderReplay() {
  const replay = state.payload.replay;
  const lead = document.getElementById("replayLead");
  const pill = document.getElementById("replayStatusPill");
  const toolbar = document.getElementById("replayToolbar");
  const track = clear(document.getElementById("sharedTrack"));
  const strip = clear(document.getElementById("divergenceStrip"));
  const narrative = replay.status === "ok";

  toolbar.classList.toggle("hidden", !narrative);
  document.getElementById("traditionalColumn").classList.toggle("hidden", !narrative);
  document.getElementById("aiColumn").classList.toggle("hidden", !narrative);
  document.getElementById("wallclockPanel").classList.toggle("hidden", !narrative && !(state.payload.effort.machine_execution || []).length);
  document.getElementById("choProcessPanel").classList.toggle("hidden", narrative);
  renderGuardrails();

  if (!narrative) {
    pill.textContent = replay.status === "process_only"
      ? (replay.ai_run && replay.ai_run.recorded ? "process view only · pilot run recorded" : "process view only · no AI run")
      : "not measured";
    lead.textContent = replay.reason || "No synchronized replay is recorded for this case.";
    renderChoProcess();
    renderWallclock(replay);
    return;
  }

  pill.textContent = `${replay.clock.label} · not wall clock`;
  lead.textContent = replay.clock.note || "";
  document.getElementById("traditionalTitle").textContent = "Reconstructed case workflow";
  document.getElementById("aiTitle").textContent = "Deterministic agent replay (time-valid)";

  const duration = state.replay.duration || 1;
  toolbar.querySelector("#replayPlay").onclick = startPlayback;
  toolbar.querySelector("#replayPause").onclick = stopPlayback;
  toolbar.querySelector("#replayStep").onclick = stepPlayback;
  toolbar.querySelector("#replayRestart").onclick = () => { stopPlayback(); seekReplay(0); };
  toolbar.querySelector("#replaySpeed").onchange = (event) => { state.replay.speed = Number(event.target.value); };

  track.append(el("div", { class: "fill", id: "trackFill" }));
  for (const event of state.replay.events) {
    const position = ((event.offset_seconds ?? 0) / duration) * 100;
    track.append(el("button", {
      class: `tick ${event.track} ${event.milestone ? "milestone" : ""}`,
      style: `left:${position}%`,
      title: `${event.track === "ai" ? "AI OS" : "Traditional"} · ${fmtClock(event.offset_seconds)} · ${event.title}`,
      onclick: () => seekReplay(event.offset_seconds),
    }));
  }
  for (const divergence of replay.divergences) {
    strip.append(el("button", {
      class: "divergence-chip",
      onclick: () => jumpToDivergence(divergence),
    }, chip(divergence.verdict.replaceAll("_", " "), `verdict-${divergence.verdict}`),
      el("b", { text: divergence.kind.replaceAll("_", " ") }),
      divergence.difference_seconds != null ? `${fmtSecondsTotal(divergence.difference_seconds)} apart` : divergence.verdict_label));
  }
  if (!replay.divergences.length) strip.append(el("span", { class: "muted", text: "No divergences recorded." }));
  renderWallclock(replay);
  renderTracks();
  updateClock();
}

function renderTracks() {
  const replay = state.payload.replay;
  const cursor = state.replay.cursor;
  for (const [trackId, containerId, countId] of [["traditional", "traditionalBody", "traditionalCount"], ["ai", "aiBody", "aiCount"]]) {
    const events = replay.tracks[trackId];
    const past = events.filter((event) => (event.offset_seconds ?? 0) <= cursor + 0.5);
    const next = events.find((event) => (event.offset_seconds ?? 0) > cursor + 0.5);
    const current = past[past.length - 1];
    const container = clear(document.getElementById(containerId));
    document.getElementById(countId).textContent = `${past.length}/${events.length}`;
    container.append(trackCard(current, trackId, "current"), trackCard(next, trackId, "next"));
    const history = el("div", { class: "track-history" });
    for (const event of [...past].reverse().slice(0, 30)) {
      history.append(el("button", {
        class: event === current ? "active" : "",
        onclick: () => seekReplay(event.offset_seconds),
      }, el("b", { text: event.title }),
        el("span", { class: "when", text: `${fmtClock(event.offset_seconds)} · ${fmtTimestamp(event.timestamp)}` }),
        event.milestone ? chip(trackId === "ai" ? "AI milestone" : "workflow milestone", trackId === "ai" ? "verified" : "") : null));
    }
    container.append(el("p", { class: "eyebrow", style: "margin-top:12px", text: "EVENTS SO FAR" }), history);
  }
}

function trackCard(event, trackId, kind) {
  if (!event) {
    return el("div", { class: "track-current next" }, el("h3", { text: kind === "current" ? "No event at this point" : "End of recorded stream" }),
      el("p", { text: kind === "current" ? "Move the shared clock forward to stream recorded events." : "The recorded chronology ends here." }));
  }
  const isAiMilestone = trackId === "ai" && event.milestone;
  return el("div", { class: `track-current ${kind === "next" ? "next" : ""} ${isAiMilestone ? "ai-milestone" : ""}` },
    isAiMilestone ? el("div", { class: "flag", text: `AI ACCOMPLISHMENT · ${event.kind.replaceAll("_", " ").toUpperCase()}` }) : null,
    el("h3", { text: event.title }),
    event.detail ? el("p", { text: event.detail.length > 420 ? `${event.detail.slice(0, 420)}…` : event.detail }) : null,
    el("div", { class: "meta" },
      el("span", { text: kind === "next" ? `next · in ${fmtSecondsTotal((event.offset_seconds ?? 0) - state.replay.cursor)}` : fmtClock(event.offset_seconds) }),
      el("span", { text: fmtTimestamp(event.timestamp) }),
      event.severity ? el("span", { text: `severity ${event.severity}` }) : null,
      event.evidence && event.evidence.length ? el("span", { text: `${event.evidence.length} cited records` }) : null),
    event.evidence && event.evidence.length
      ? el("div", { class: "chain-evidence dev-only" }, event.evidence.slice(0, 10).map((id) => el("button", { text: id, onclick: () => openDrawer(id, [{ label: "cited evidence", text: `Record ${id} was visible at this cutoff and cited by the agent.` }]) })))
      : null,
    event.source ? el("div", { class: "responsive-note", text: event.source }) : null);
}

function seekReplay(offset) {
  stopPlayback();
  state.replay.cursor = Math.max(0, Math.min(offset, state.replay.duration));
  const fill = document.getElementById("trackFill");
  if (fill) fill.style.width = `${(state.replay.cursor / (state.replay.duration || 1)) * 100}%`;
  renderTracks();
  updateClock();
}

function jumpToDivergence(divergence) {
  const offsets = [divergence.ai, divergence.traditional].filter(Boolean).map((ref) => ref.offset_seconds).filter((value) => value != null);
  const offset = divergence.verdict === "ai_only" ? offsets[0] : Math.max(...offsets);
  if (offset != null) seekReplay(offset);
}

function updateClock() {
  const replay = state.payload.replay;
  const cursor = state.replay.cursor;
  const clock = document.getElementById("replayClockText");
  const elapsed = document.getElementById("replayElapsed");
  if (replay.status !== "ok") { clock.textContent = "—"; elapsed.textContent = ""; return; }
  const start = new Date(replay.clock.start).getTime();
  const current = new Date(start + cursor * 1000);
  clock.textContent = current.toISOString().replace("T", " ").slice(0, 16) + " UTC";
  elapsed.textContent = `elapsed ${fmtClock(cursor)} of ${fmtClock(state.replay.duration)}`;
}

function startPlayback() {
  stopPlayback();
  if (!state.replay.events.length) return;
  if (state.replay.cursor >= state.replay.duration) state.replay.cursor = 0;
  state.replay.playing = true;
  document.getElementById("replayPlay").textContent = "▶ Playing";
  state.replay.timer = setInterval(() => {
    const speed = state.replay.speed || 32;
    const step = speed * 8640; // select value = simulated days per wall-clock second (one 100 ms tick)
    if (state.replay.cursor + step >= state.replay.duration) {
      seekReplay(state.replay.duration);
      stopPlayback();
      return;
    }
    state.replay.cursor += step;
    const fill = document.getElementById("trackFill");
    if (fill) fill.style.width = `${(state.replay.cursor / (state.replay.duration || 1)) * 100}%`;
    renderTracks();
    updateClock();
  }, 100);
}

function stopPlayback() {
  state.replay.playing = false;
  if (state.replay.timer) { clearInterval(state.replay.timer); state.replay.timer = null; }
  const button = document.getElementById("replayPlay");
  if (button) button.textContent = "▶ Play";
}

function stepPlayback() {
  stopPlayback();
  const next = state.replay.events.find((event) => (event.offset_seconds ?? 0) > state.replay.cursor + 0.5);
  if (next) seekReplay(next.offset_seconds);
}

function renderWallclock(replay) {
  const container = clear(document.getElementById("wallclockBody"));
  const effort = state.payload.effort;
  const rows = effort.machine_execution || [];
  if (replay.status === "ok") {
    container.append(el("table", { class: "plain wallclock-table" },
      el("thead", {}, el("tr", {}, el("th", { text: "Recorded run" }), el("th", { text: "Value" }), el("th", { text: "Class" }))),
      el("tbody", {}, (replay.wall_clock?.entries || []).map((entry) =>
        el("tr", {}, el("td", {}, el("div", { text: entry.label }), el("small", { class: "muted", text: entry.source || "" })),
          el("td", { text: entry.display }), el("td", {}, chip(entry.classification, entry.classification)))))));
    container.append(el("p", { class: "responsive-note", text: replay.wall_clock?.note || "" }));
    return;
  }
  if (!rows.length) { container.append(el("p", { class: "muted", text: "No recorded machine execution available." })); return; }
  const execution = replay.execution || {};
  container.append(el("p", { class: "muted", style: "font-size:12.5px", text: execution.note || "" }));
  container.append(el("table", { class: "plain wallclock-table" },
    el("thead", {}, el("tr", {}, el("th", { text: "Task" }), el("th", { text: "Runtime" }), el("th", { text: "Class" }))),
    el("tbody", {}, rows.map((row) => el("tr", {},
      el("td", {}, el("div", { text: row.label }), el("small", { class: "muted", text: row.source || "" })),
      el("td", { text: row.display }), el("td", {}, chip(row.classification, row.classification)))))));
}

function renderGuardrails() {
  const container = clear(document.getElementById("guardrailsBody"));
  const guardrails = state.payload.replay.guardrails || [];
  container.append(el("div", { class: "diff-grid" }, guardrails.map((item) =>
    el("div", { class: "diff-card" },
      el("header", {}, chip(item.status, "observed"), el("h3", { text: item.check })),
      el("p", { text: item.basis }),
      el("div", { class: "responsive-note dev-only", text: item.source })))));
}

/* ------------------------------------------------------- CHO process view */
function renderChoProcess() {
  const replay = state.payload.replay;
  const container = clear(document.getElementById("choProcessPanel"));
  const process = replay.process || {};
  if (!(process.experiments || []).length) {
    container.append(el("article", { class: "panel" },
      el("div", { class: "panel-head" }, el("div", {}, el("p", { class: "eyebrow", text: "PROCESS VIEW" }), el("h2", { text: "No process reference artifacts are available" })))));
    return;
  }
  const controls = el("div", { class: "process-controls" });
  const experimentSelect = el("select", { id: "choExperiment" }, process.experiments.map((experiment) =>
    el("option", { value: experiment.id, text: `${experiment.id} (${experiment.process_mode})` })));
  const variableSelect = el("select", { id: "choVariable" });
  const refresh = () => {
    const experiment = process.experiments.find((item) => item.id === experimentSelect.value);
    clear(variableSelect);
    const names = (experiment.largest_differences || []).map((item) => item.variable);
    const all = process.variables || [];
    const ordered = [...new Set([...names, ...all])];
    for (const name of ordered) variableSelect.append(el("option", { value: name, text: name }));
    loadChoSeries(experimentSelect.value, variableSelect.value, process);
  };
  experimentSelect.onchange = refresh;
  variableSelect.onchange = () => loadChoSeries(experimentSelect.value, variableSelect.value, process);
  controls.append(el("label", {}, "EXPERIMENT", experimentSelect), el("label", {}, "PROCESS VARIABLE", variableSelect));

  const divergenceRow = el("div", { class: "divergence-strip" }, (replay.divergences || []).map((divergence) =>
    el("button", { class: "divergence-chip", onclick: () => {
      const experimentId = divergence.id.replace("DIV-", "");
      const variable = divergence.label.split(": ")[1];
      experimentSelect.value = experimentId;
      refresh();
      variableSelect.value = variable;
      loadChoSeries(experimentId, variable, process);
    } }, chip(divergence.verdict_label.split(" (")[0], "verdict-descriptive"),
      el("b", { text: divergence.label }),
      `${divergence.normalized_delta >= 0 ? "+" : ""}${divergence.normalized_delta.toFixed(3)} normalized`)));

  const note = el("p", { class: "responsive-note", text: process.reference_note || "" });
  const flags = process.flags_note ? el("p", { class: "responsive-note", style: "margin-top:6px", text: process.flags_note }) : null;
  const plot = el("div", { class: "plot-wrap", id: "choPlot" }, el("p", { class: "muted", style: "padding:20px", text: "Loading trajectories…" }));

  container.append(
    el("article", { class: "panel" },
      el("div", { class: "panel-head" }, el("div", {}, el("p", { class: "eyebrow", text: "PROCESS ENGINEERING INTELLIGENCE" }), el("h2", { text: "Reactor-pair trajectories — descriptive comparison" }))),
      el("div", { class: "panel-body" }, controls, divergenceRow, plot, note, flags,
        el("div", { class: "plot-legend" }, el("span", {}, el("i", { style: "background:#101828" }), "R01"), el("span", {}, el("i", { style: "background:#0e9384" }), "R02")))));
  refresh();
}

async function loadChoSeries(experimentId, variable, process) {
  const plot = document.getElementById("choPlot");
  if (!plot || !variable) return;
  const pair = (process.cultivations || []).filter((item) => item.experiment === experimentId);
  if (pair.length < 2) { plot.innerHTML = '<p class="muted" style="padding:20px">No reactor pair recorded for this experiment.</p>'; return; }
  plot.innerHTML = '<p class="muted" style="padding:20px">Loading trajectories…</p>';
  try {
    const [first, second] = await Promise.all(pair.slice(0, 2).map((item) =>
      fetchJSON(`/api/case-comparison/cho/series?cultivation=${encodeURIComponent(item.id)}&variables=${encodeURIComponent(variable)}&max_points=300`)));
    drawChoPlot(plot, variable, first, second);
  } catch (error) {
    plot.innerHTML = `<p class="muted" style="padding:20px">Could not load series: ${error.message}</p>`;
  }
}

function drawChoPlot(container, variable, first, second) {
  clear(container);
  const seriesA = first.variables[variable];
  const seriesB = second.variables[variable];
  if (!seriesA || !seriesB) { container.append(el("p", { class: "muted", text: "Variable not found in both files." })); return; }
  const width = 900, height = 260, pad = { left: 56, right: 14, top: 14, bottom: 26 };
  const points = seriesA.points.concat(seriesB.points);
  const xs = points.map((point) => point[0]);
  const ys = points.map((point) => point[1]);
  const xMin = Math.min(...xs), xMax = Math.max(...xs);
  let yMin = Math.min(...ys), yMax = Math.max(...ys);
  if (yMin === yMax) { yMin -= 1; yMax += 1; }
  const x = (value) => pad.left + ((value - xMin) / (xMax - xMin || 1)) * (width - pad.left - pad.right);
  const y = (value) => pad.top + (1 - (value - yMin) / (yMax - yMin || 1)) * (height - pad.top - pad.bottom);
  const path = (series) => series.points.map((point, index) => `${index ? "L" : "M"}${x(point[0]).toFixed(1)},${y(point[1]).toFixed(1)}`).join(" ");
  const svgNs = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(svgNs, "svg");
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("width", "100%");
  svg.style.display = "block";
  const grid = document.createElementNS(svgNs, "g");
  for (let tick = 0; tick <= 4; tick += 1) {
    const value = yMin + ((yMax - yMin) * tick) / 4;
    const line = document.createElementNS(svgNs, "line");
    line.setAttribute("x1", pad.left); line.setAttribute("x2", width - pad.right);
    line.setAttribute("y1", y(value)); line.setAttribute("y2", y(value));
    line.setAttribute("stroke", "#eef0f4");
    const label = document.createElementNS(svgNs, "text");
    label.setAttribute("x", pad.left - 8); label.setAttribute("y", y(value) + 4);
    label.setAttribute("text-anchor", "end"); label.setAttribute("fill", "#98a2b3"); label.setAttribute("font-size", "10");
    label.textContent = value.toFixed(2);
    grid.append(line, label);
  }
  for (let tick = 0; tick <= 4; tick += 1) {
    const value = xMin + ((xMax - xMin) * tick) / 4;
    const label = document.createElementNS(svgNs, "text");
    label.setAttribute("x", x(value)); label.setAttribute("y", height - 8);
    label.setAttribute("text-anchor", "middle"); label.setAttribute("fill", "#98a2b3"); label.setAttribute("font-size", "10");
    label.textContent = `${value.toFixed(0)} h`;
    grid.append(label);
  }
  svg.append(grid);
  const pathA = document.createElementNS(svgNs, "path");
  pathA.setAttribute("d", path(seriesA)); pathA.setAttribute("fill", "none");
  pathA.setAttribute("stroke", "#101828"); pathA.setAttribute("stroke-width", "1.6");
  const pathB = document.createElementNS(svgNs, "path");
  pathB.setAttribute("d", path(seriesB)); pathB.setAttribute("fill", "none");
  pathB.setAttribute("stroke", "#0e9384"); pathB.setAttribute("stroke-width", "1.6");
  svg.append(pathA, pathB);
  container.append(svg);
  container.append(el("p", { class: "responsive-note", style: "padding:6px 8px 2px", text:
    `${variable} · ${first.cultivation} (R01, dark) vs ${second.cultivation} (R02, teal) · publisher-aligned reference data · downsampled ×${first.downsample_stride} · x-axis: cultivation time (h)` }));
}

/* ---------------------------------------------------------------- evidence */
function renderEvidence() {
  const evidence = state.payload.evidence;
  const lead = document.getElementById("evidenceLead");
  lead.textContent = evidence.basis || "";
  const container = clear(document.getElementById("evidenceBody"));
  document.getElementById("evidenceCount").textContent = `${evidence.rows.length} items`;
  const table = el("table", { class: "evidence" });
  table.append(el("thead", {}, el("tr", {},
    el("th", { text: "Evidence" }), el("th", { text: "Traditional workflow" }), el("th", { text: "AI OS" }), el("th", { text: "Influence" }))));
  table.append(el("tbody", {}, evidence.rows.map((row) =>
    el("tr", { onclick: () => openEvidenceDrawer(row) },
      el("td", {}, el("div", { class: "metric-name" }, row.label,
        el("small", { text: `${row.type}${row.pilot_cited ? " · cited in recorded pilot run" : ""}` }))),
      el("td", {}, el("div", { class: "statuses" }, statusChip(row.traditional)), el("small", { class: "muted", text: (row.traditional.detail || "").slice(0, 120) })),
      el("td", {}, el("div", { class: "statuses" }, statusChip(row.ai)), el("small", { class: "muted", text: (row.ai.detail || "").slice(0, 120) })),
      el("td", {}, el("div", { class: "influence", text: row.influence }))))));
  container.append(table);

  const annotations = clear(document.getElementById("annotationsBody"));
  const data = evidence.annotations || {};
  const blocks = [];
  if (data.pilot_unverified?.length) blocks.push({ label: "pilot run — unresolved questions", text: data.pilot_unverified.join(" · ") });
  if (data.pilot_pending_evidence_requests != null) blocks.push({ label: "pilot run — open evidence requests", text: String(data.pilot_pending_evidence_requests) });
  if (data.reliability_runs != null) blocks.push({ label: "repeatability runs recorded", text: String(data.reliability_runs) });
  if (data.rules_never_detected?.length) blocks.push({ label: "batches the rules condition never detects", text: data.rules_never_detected.join(", ") });
  if (data.time_zero_mismatch_examples != null) blocks.push({ label: "time-zero mismatches", text: data.time_zero_mismatch_examples.length ? data.time_zero_mismatch_examples.join(" · ") : "none recorded" });
  if (data.perturbation_notes?.length) blocks.push({ label: "perturbation notes", text: data.perturbation_notes.join(" · ") });
  if (data.reference_type) blocks.push({ label: "reference type", text: data.reference_type });
  annotations.append(...blocks.map((block) => el("div", {}, el("b", { text: `${block.label}: ` }), block.text)));
  if (!blocks.length) annotations.append(el("p", { class: "muted", text: "No annotations recorded." }));
}

function openEvidenceDrawer(row) {
  const blocks = [];
  for (const [sideId, label] of [["traditional", "Traditional workflow"], ["ai", "AI OS"]]) {
    const side = row[sideId];
    blocks.push({ label: `${label} — ${side.label || side.status}`, text: side.detail || "No detail recorded." });
  }
  blocks.push({ label: "influence", text: row.influence });
  blocks.push({ label: "timestamp", text: fmtTimestamp(row.timestamp) });
  if (row.entities?.length) blocks.push({ label: "entities", text: row.entities.join(", ") });
  if (row.pilot_cited != null) blocks.push({ label: "pilot citation", text: row.pilot_cited ? "Cited in the recorded pilot run." : "Not cited in the recorded pilot run." });
  blocks.push({ label: "traceability", text: (row.sources || []).map((source) => source.path).join(" · ") || "No artifact listed." });
  openDrawer(row.label || row.id, blocks);
}

/* ------------------------------------------------------------------ drawer */
function openDrawer(title, blocks) {
  const drawer = document.getElementById("drawer");
  clear(drawer);
  drawer.append(el("div", { class: "drawer-head" },
    el("h2", { text: title }),
    el("button", { class: "secondary small-button", text: "Close", onclick: closeDrawer })));
  for (const block of blocks) {
    drawer.append(el("div", { class: "drawer-block" },
      el("span", { text: block.label }), el("div", { text: block.text || "—" })));
  }
  drawer.classList.remove("hidden");
  document.getElementById("drawerBackdrop").classList.remove("hidden");
}

function openSourceDrawer(source) {
  openDrawer(source.path, [
    { label: "artifact", text: source.artifact },
    { label: "availability", text: source.available ? "Recorded artifact present in the repository." : "Artifact missing; affected values render as Not measured." },
    source.fields ? { label: "fields read", text: source.fields.join(", ") } : null,
  ].filter(Boolean));
}

function closeDrawer() {
  document.getElementById("drawer").classList.add("hidden");
  document.getElementById("drawerBackdrop").classList.add("hidden");
}

/* ------------------------------------------------------------ presentation */
function applyDifferencesMode(scroll) {
  const toggle = document.getElementById("differencesToggle");
  toggle.setAttribute("aria-pressed", String(state.differencesOnly));
  toggle.textContent = state.differencesOnly ? "Show full scorecard" : "Show only differences";
  document.getElementById("scorecardPanel").classList.toggle("hidden", state.differencesOnly);
  document.getElementById("differencesPanel").classList.toggle("hidden", !state.differencesOnly);
  document.getElementById("differencesNote").textContent = state.differencesOnly
    ? "Differences mode — only the findings that changed between the two workflows."
    : "Viewing the full scorecard — every recorded metric, both workflows.";
  if (scroll && state.differencesOnly) {
    document.getElementById("differencesPanel").scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

function wireToolbar() {
  document.getElementById("differencesToggle").addEventListener("click", () => {
    state.differencesOnly = !state.differencesOnly;
    applyDifferencesMode(true);
  });
  document.getElementById("drawerBackdrop").addEventListener("click", closeDrawer);
}

function wirePresentation() {
  document.getElementById("presentationToggle").addEventListener("click", () => setPresentation(!state.presentation.active));
  document.getElementById("presentationExit").addEventListener("click", () => setPresentation(false));
  document.getElementById("presentationPrev").addEventListener("click", () => presentationStep(state.presentation.step - 1));
  document.getElementById("presentationNext").addEventListener("click", () => presentationStep(state.presentation.step + 1));
  document.addEventListener("keydown", (event) => {
    if (!state.presentation.active) return;
    if (event.key === "Escape") setPresentation(false);
    if (event.key === "ArrowRight") presentationStep(state.presentation.step + 1);
    if (event.key === "ArrowLeft") presentationStep(state.presentation.step - 1);
  });
}

function setPresentation(active) {
  state.presentation.active = active;
  document.body.classList.toggle("presentation", active);
  document.getElementById("presentationBar").classList.toggle("hidden", !active);
  document.getElementById("presentationToggle").textContent = active ? "■ Exit presentation" : "▶ Presentation mode";
  if (active) { state.presentation.step = 0; presentationStep(0); }
}

function renderPresentationBar() {
  const steps = clear(document.getElementById("presentationSteps"));
  const presentation = state.payload.presentation;
  for (const [index, step] of presentation.steps.entries()) {
    steps.append(el("button", {
      class: `step ${index === state.presentation.step ? "active" : ""}`,
      onclick: () => presentationStep(index),
    }, `${index + 1}. ${step.label}`));
  }
}

function presentationStep(index) {
  const presentation = state.payload.presentation;
  const steps = presentation.steps || [];
  if (!steps.length) return;
  state.presentation.step = Math.max(0, Math.min(index, steps.length - 1));
  const step = steps[state.presentation.step];
  renderPresentationBar();
  switch (step.id) {
    case "scorecard":
      setView("compare");
      document.getElementById("scorecardPanel").scrollIntoView({ behavior: "smooth", block: "start" });
      break;
    case "divergence": {
      setView("replay");
      const divergence = (state.payload.replay.divergences || []).find((item) => item.kind === "cross_batch_pattern"
        || item.kind === "reactor_pair_difference");
      if (divergence && state.payload.replay.status === "ok") jumpToDivergence(divergence);
      else document.getElementById("choProcessPanel").scrollIntoView({ behavior: "smooth", block: "start" });
      break;
    }
    case "process":
      setView("replay");
      document.getElementById("choProcessPanel").scrollIntoView({ behavior: "smooth", block: "start" });
      break;
    case "evidence":
      setView("evidence");
      break;
    default:
      setView("compare");
      document.getElementById("findingsPanel").scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

init();
