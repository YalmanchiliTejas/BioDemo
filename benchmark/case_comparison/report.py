"""Static, self-contained benchmark report.

Renders the recorded comparison payloads (the same data the ``/comparison``
dashboard consumes) into one standalone HTML file: inline CSS, native
``<details>`` collapsibles, no scripts and no network assets, so the file can
be opened directly from disk or served read-only from ``/benchmark-report``.

Nothing here computes benchmark values. Every number, classification and
citation comes from :class:`benchmark.case_comparison.service.ComparisonService`,
which reads the recorded artifacts. Missing measurements render as
"Not measured" with their recorded reason.

Regenerate with::

    python -m benchmark.case_comparison.report

The default output path is ``benchmark/application/static/benchmark-report.html``.
"""

from __future__ import annotations

import argparse
import html
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

from .scorecard import CLASSIFICATION_DEFINITIONS, CLASSIFICATION_LABELS, format_duration_seconds
from .service import CASE_ORDER, ComparisonService
from .sources import REPOSITORY
from .visual_report import CSS as VISUAL_CSS, render_visuals

REPORT_TITLE = "Benchmark report — evidence, in view"

DEFAULT_OUTPUT = (
    Path(__file__).resolve().parents[1] / "application" / "static" / "benchmark-report.html"
)

CASE_ROLE_LABELS = {
    "fresenius": "Case 1 · reconstructed manufacturing-quality incident",
    "cho": "Case 2 · published bioprocess dataset (real data)",
}

# Human labels for the difference categories emitted by the case modules.
DIFFERENCE_CATEGORY_LABELS = {
    "evidence_first": "Earlier AI evidence",
    "one_sided_evidence": "One-sided evidence",
    "missed_evidence": "Missed evidence",
    "eliminated_steps": "Eliminated / accelerated steps",
    "hypotheses": "Hypotheses",
    "escalation_timing": "Escalation timing",
    "decisions": "Decision correctness",
    "human_intervention": "Human intervention",
    "unsupported_conclusions": "Unsupported AI conclusions",
    "found_by_traditional_only": "Recorded only by the traditional workflow",
    "reference_observation": "Descriptive reference observation",
}

# Evidence-matrix statuses collapse onto the five classification chip styles
# plus one "alert" style for gaps (missed / unavailable / misinterpreted).
STATUS_CHIP_KINDS = {
    "retrieved": "observed",
    "interpreted_correctly": "verified",
    "verified": "verified",
    "interpreted_delayed": "modeled",
    "partially_interpreted": "modeled",
    "predicted": "predicted",
    "not_measured": "not_measured",
    "missed": "alert",
    "interpreted_incorrectly": "alert",
    "unavailable": "alert",
}

MILESTONE_LABELS = {
    "risk_acknowledged": "Risk acknowledged",
    "cross_batch_pattern": "Cross-batch pattern correlated",
    "escalation_decision": "Escalation decision",
}

CHIP_KINDS = {"verified", "observed", "modeled", "predicted", "not_measured", "alert"}

REPORT_CSS = """
.chart-grid,.outcome-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin:22px 0}
.chart-card{border:1px solid var(--line);border-radius:12px;padding:20px;background:#fcfdfc;margin:16px 0;min-width:0}
.chart-grid .chart-card{margin:0}.chart-card h3{margin:0 0 8px;font-size:18px}.chart-card h4{margin:20px 0 10px;font-size:12px}.chart-card .sources{overflow-wrap:anywhere}.chart-card .sources code{white-space:normal}
.chart-row{display:grid;grid-template-columns:105px minmax(0,1fr) 60px;align-items:center;gap:10px;margin:10px 0;font-size:11px}
.chart-row b{text-align:right;font-variant-numeric:tabular-nums}.chart-track{height:13px;background:#e8ede9;border-radius:3px;overflow:hidden}.chart-track i{height:100%;display:block;background:#16795c}.chart-track.missing{height:auto;min-height:20px;background:repeating-linear-gradient(135deg,#f2f4f2,#f2f4f2 4px,#e8ece8 4px,#e8ece8 5px);color:#606e66;font-size:10px;text-align:center;grid-column:2/4}
.outcome-stat{background:#edf5ef;border:1px solid #d3e2d7;padding:20px;border-radius:10px}.outcome-stat strong{display:block;font-size:23px;margin:8px 0}.outcome-stat small{text-transform:uppercase;font-size:10px}
@media(max-width:650px){.chart-grid,.outcome-grid{grid-template-columns:1fr}.chart-row{grid-template-columns:85px minmax(0,1fr) 55px}.page{padding-inline:12px}section{padding:20px 14px}}

:root{--ink:#111827;--muted:#5c6673;--line:#d8dee6;--bg:#f6f8fa;--panel:#ffffff;
  --verified:#0f7b4d;--observed:#1d4ed8;--modeled:#7c3aed;--predicted:#b45309;--not-measured:#6b7280;--alert:#b42318;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.page{max-width:1080px;margin:0 auto;padding:28px 22px 80px}
a{color:#1d4ed8}
.masthead{background:#0f172a;color:#e5e9f0;border-radius:14px;padding:26px 28px}
.masthead h1{margin:0 0 8px;font-size:24px;letter-spacing:-.01em}
.masthead p{margin:4px 0;color:#b9c2d0;font-size:13.5px;max-width:860px}
.masthead .meta{font-size:12px;color:#8e99ab;margin-top:10px}
h2{font-size:21px;margin:0 0 6px;letter-spacing:-.01em}
h3{font-size:15px;margin:20px 0 8px}
p{margin:6px 0}
ul{margin:6px 0;padding-left:20px}
li{margin:3px 0}
small{color:var(--muted)}
.muted{color:var(--muted)}
section{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:22px 24px;margin-top:18px}
.case{border-top:5px solid #0f172a}
.case-head .label{font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);font-weight:700;margin:0 0 6px}
.case-head h2{font-size:23px}
.question{font-size:14.5px;color:#374151;max-width:860px}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin:10px 0}
.chip{display:inline-block;font-size:11px;font-weight:600;letter-spacing:.02em;border-radius:999px;padding:2px 9px;border:1px solid transparent;vertical-align:middle;white-space:nowrap}
.chip-verified{background:#e7f5ee;color:var(--verified);border-color:#bfe3d1}
.chip-observed{background:#e8eefc;color:var(--observed);border-color:#c4d3f7}
.chip-modeled{background:#f1eafd;color:var(--modeled);border-color:#dbc8f8}
.chip-predicted{background:#fdf1e0;color:var(--predicted);border-color:#f3d9ae}
.chip-not_measured{background:#eef1f4;color:var(--not-measured);border-color:#d6dbe2}
.chip-alert{background:#fdeceb;color:var(--alert);border-color:#f5c6c2}
.chip-neutral{background:#eef1f4;color:#374151;border-color:#d6dbe2}
.callout{border-radius:10px;padding:12px 14px;margin:12px 0;font-size:13.5px}
.callout-info{background:#eef4fd;border:1px solid #cddcf5}
.callout-warn{background:#fdf3ec;border:1px solid #f2d8c2}
.callout-note{background:#f4f6f8;border:1px solid var(--line)}
table.grid{display:block;max-width:100%;overflow-x:auto;border-collapse:collapse;margin:10px 0;font-size:13px}
table.grid th{font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);text-align:left;border-bottom:2px solid var(--line);padding:7px 9px;vertical-align:bottom}
table.grid td{border-bottom:1px solid var(--line);padding:8px 9px;vertical-align:top}
table.grid tr:last-child td{border-bottom:none}
table.grid tr.group-row td{background:#f0f3f7;font-weight:700;font-size:12px;letter-spacing:.05em;text-transform:uppercase}
table.grid td.value strong{display:block;font-size:14px}
table.grid td.value small{display:block;color:var(--muted);font-size:12px;margin-top:3px}
.metric-name b{display:block}
.metric-name small{display:block;color:var(--muted);font-size:12px;margin-top:3px}
details{border:1px solid var(--line);border-radius:10px;margin:12px 0;padding:0}
details>summary{cursor:pointer;font-weight:600;padding:10px 14px;font-size:13.5px}
details>*:not(summary){margin:0 14px 12px}
code{background:#eef1f4;border:1px solid #dde3ea;border-radius:6px;padding:1px 6px;font-size:11.5px;white-space:nowrap}
.sources{margin-top:6px}
.sources code{display:inline-block;margin:2px 4px 2px 0;color:#374151}
.diff{border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin:10px 0}
.diff h4{margin:8px 0 4px;font-size:14px}
.diff p{margin:4px 0;font-size:13px;color:#374151}
.refs{margin-top:8px}
.refs code{display:inline-block;margin:2px 4px 2px 0;white-space:normal}
.mile{border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin:10px 0}
.mile h4{margin:0 0 6px;font-size:14px}
.mile .side-line{margin:4px 0;font-size:13px}
.legend{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin-top:10px}
.legend div{border:1px solid var(--line);border-radius:10px;padding:10px 12px;background:#fafbfc}
.legend b{display:block;font-size:12.5px;margin-bottom:4px}
.legend p{font-size:11.5px;color:var(--muted);margin:0}
.finding-block{margin:14px 0}
.finding-block h3{margin-bottom:4px}
.finding-block ul{margin-top:4px}
.foot{margin-top:22px;color:var(--muted);font-size:12px}
.foot code{white-space:normal}
.case-toc{display:flex;gap:10px;flex-wrap:wrap;margin-top:12px}
.case-toc a{background:#eef1f4;border:1px solid var(--line);border-radius:999px;padding:4px 12px;font-size:12.5px;text-decoration:none;color:#1f2937}
@media print{body{background:#fff}section,.masthead{border-radius:0}.page{padding:0}}
@media(max-width:840px){.legend{grid-template-columns:1fr 1fr}table.grid{font-size:12px}}
"""


# --------------------------------------------------------------------- helpers
def _esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _chip(label: str, kind: str) -> str:
    css = kind if kind in CHIP_KINDS else "neutral"
    return f'<span class="chip chip-{css}">{_esc(label)}</span>'


def _classification_chip(side: dict[str, Any]) -> str:
    kind = side.get("classification") or "not_measured"
    label = side.get("classification_label") or CLASSIFICATION_LABELS.get(kind, kind)
    return _chip(label, kind)


def _fmt_timestamp(value: Any) -> str:
    if not value:
        return "—"
    text = str(value)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text
    return parsed.strftime("%Y-%m-%d %H:%M") + " UTC"


def _fmt_number(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return f"{round(value, 6):g}"
    return str(value)


def _fmt_count(value: Any) -> str:
    if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
        return "—"
    return f"{int(value):,}"


def _fmt_seconds(value: Any) -> str:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return "Not measured"
    return format_duration_seconds(float(value))


def _side_cell(side: dict[str, Any]) -> str:
    detail = side.get("detail")
    return (
        f'<td class="value"><strong>{_esc(side.get("display", "Not measured"))}</strong>'
        f'{_classification_chip(side)}'
        f'{f"<small>{_esc(detail)}</small>" if detail else ""}</td>'
    )


def _delta_cell(delta: dict[str, Any] | None) -> str:
    if not delta:
        return '<td class="muted">—</td>'
    percent = delta.get("improvement_percent")
    percent_text = f" · {_fmt_number(percent)}%" if percent is not None else " · no percentage (zero baseline)"
    return (
        f'<td><strong>{_esc(delta.get("glyph", ""))} {_esc(_fmt_number(delta.get("absolute_change")))}</strong>'
        f'<br><small>{_esc(delta.get("verdict", ""))}{_esc(percent_text)}</small></td>'
    )


def _source_codes(sources: Iterable[dict[str, Any]]) -> str:
    items = []
    for source in sources:
        available = source.get("available", True)
        title = "recorded artifact" if available else "artifact missing"
        path = source.get("path") or source.get("artifact") or ""
        items.append(f'<code title="{_esc(title)}">{_esc(path)}</code>')
    if not items:
        return ""
    return f'<div class="sources">{"".join(items)}</div>'


def _table(headers: Sequence[str], rows: Iterable[str]) -> str:
    head = "".join(f"<th>{_esc(header)}</th>" for header in headers)
    body = "".join(rows)
    return f'<table class="grid"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def _details(summary: str, body: str) -> str:
    return f"<details><summary>{_esc(summary)}</summary>{body}</details>"


def _callout(title: str, text: str, kind: str = "info") -> str:
    return (
        f'<div class="callout callout-{kind}"><strong>{_esc(title)}</strong>'
        f'<div>{_esc(text)}</div></div>'
    )


def _bullet_list(items: Iterable[Any]) -> str:
    entries = "".join(f"<li>{_esc(item)}</li>" for item in items)
    return f"<ul>{entries}</ul>" if entries else '<p class="muted">None recorded.</p>'


def _ref_text(ref: dict[str, Any]) -> str:
    detail = ref.get("detail") or ""
    suffix = f" — {detail[:160]}" if detail else ""
    return f'{ref.get("kind", "ref")}: {ref.get("id", "")}{suffix}'


# ------------------------------------------------------------------- sections
def _render_how_to_read() -> str:
    legend = "".join(
        f'<div><b>{_esc(CLASSIFICATION_LABELS[kind])}</b><p>{_esc(CLASSIFICATION_DEFINITIONS[kind])}</p></div>'
        for kind in ("verified", "observed", "modeled", "predicted", "not_measured")
    )
    return f"""
<section id="how-to-read">
  <h2>How to read this report</h2>
  <p>Both case studies compare a <b>traditional workflow</b> with an <b>AI operating layer</b> over frozen,
  recorded benchmark artifacts. Every value below is read from those artifacts or produced by evaluating the
  existing deterministic agents over the frozen datasets. Nothing is estimated for presentation.</p>
  <ul>
    <li>Missing measurements are shown as <b>Not measured</b> together with the recorded reason — never as zero or a placeholder.</li>
    <li>Every result carries a classification: Verified, Observed, Modeled, Predicted or Not measured.</li>
    <li>Replay timelines follow each case's recorded clock. They are not wall-clock traces and imply no synchronization between the two workflows.</li>
    <li>Modeled campaign figures are projections under documented assumptions, not measured human performance.</li>
  </ul>
  <div class="legend">{legend}</div>
</section>"""


def _render_dataset(payload: dict[str, Any]) -> str:
    dataset = payload.get("dataset") or {}
    rows = []
    fields = (
        ("Dataset", dataset.get("label")),
        ("Version", dataset.get("version")),
        ("Fingerprint", dataset.get("fingerprint")),
        ("Records", dataset.get("records")),
        ("License", dataset.get("license")),
        ("Archive MD5", dataset.get("archive_md5")),
        ("Provenance", dataset.get("provenance")),
        ("Disclaimer", dataset.get("disclaimer")),
    )
    for label, value in fields:
        if value:
            rows.append(f"<tr><td><b>{_esc(label)}</b></td><td>{_esc(value)}</td></tr>")
    provenance = f"<h3>Dataset &amp; provenance</h3>{_table(['Field', 'Recorded value'], rows)}" if rows else ""

    facts = (payload.get("public_facts") or []) + (payload.get("facts") or [])
    fact_rows = []
    for fact in facts:
        statement = _esc(fact.get("statement") or "")
        source = fact.get("source")
        url = fact.get("source_url")
        source_text = ""
        if url:
            source_text = f'<a href="{_esc(url)}">{_esc(source or url)}</a>'
        elif source:
            source_text = _esc(source)
        available = fact.get("available_at")
        fact_rows.append(
            f'<tr><td><b>{_esc(fact.get("id") or "FACT")}</b></td><td>{statement}</td>'
            f"<td>{source_text}</td><td>{_esc(_fmt_timestamp(available)) if available else '—'}</td></tr>"
        )
    facts_html = ""
    if fact_rows:
        facts_html = (
            "<h3>Anchoring facts</h3>"
            + _table(["ID", "Statement", "Source", "Available at"], fact_rows)
        )
    return f"{provenance}{facts_html}"


def _render_scorecard(scorecard: dict[str, Any]) -> str:
    rows = []
    for group in scorecard.get("groups") or []:
        rows.append(f'<tr class="group-row"><td colspan="4">{_esc(group)}</td></tr>')
        for metric in scorecard.get("metrics") or []:
            if metric.get("group") != group:
                continue
            meta = [f"<b>{_esc(metric.get('label'))}</b>", f"<small>{_esc(metric.get('definition'))}</small>"]
            if metric.get("note"):
                meta.append(f"<small>{_esc(metric['note'])}</small>")
            meta.append(_source_codes(metric.get("sources") or []))
            rows.append(
                "<tr>"
                f'<td class="metric-name">{"".join(meta)}</td>'
                f'{_side_cell(metric.get("traditional") or {})}'
                f'{_side_cell(metric.get("ai") or {})}'
                f'{_delta_cell(metric.get("delta"))}'
                "</tr>"
            )
    conclusion = scorecard.get("conclusion")
    conclusion_html = f'<p class="muted"><b>Recorded conclusion.</b> {_esc(conclusion)}</p>' if conclusion else ""
    return (
        "<h3>Full scorecard</h3>"
        + _table(["Metric", "Traditional workflow", "AI operating layer", "Δ (AI vs traditional)"], rows)
        + conclusion_html
    )


def _render_differences(differences: list[dict[str, Any]]) -> str:
    if not differences:
        return '<p class="muted">No differences are recorded for this case.</p>'
    cards = []
    for entry in differences:
        category = DIFFERENCE_CATEGORY_LABELS.get(entry.get("category"), entry.get("category") or "")
        refs = "".join(f"<code>{_esc(_ref_text(ref))}</code>" for ref in entry.get("refs") or [])
        cards.append(
            '<article class="diff">'
            f'<div class="chips">{_chip(category, "neutral")}{_chip(entry.get("classification"), entry.get("classification"))}</div>'
            f'<h4>{_esc(entry.get("title"))}</h4>'
            f'<p>{_esc(entry.get("detail"))}</p>'
            f'{f"<div class=refs>{refs}</div>" if refs else ""}'
            "</article>"
        )
    return (
        "<h3>What changed between the two workflows</h3>"
        f'<p class="muted">{len(differences)} recorded finding(s). Each finding references the underlying event or artifact.</p>'
        + "".join(cards)
    )


def _render_effort(effort: dict[str, Any]) -> str:
    parts = ["<h3>Effort breakdown</h3>"]
    if effort.get("basis"):
        parts.append(f'<p class="muted">{_esc(effort["basis"])}</p>')

    phase_rows = effort.get("phase_rows") or []
    if phase_rows:
        rows = []
        for row in phase_rows:
            rows.append(
                "<tr>"
                f'<td>{_esc(row.get("label"))}</td>'
                f'<td>{_esc(row.get("display_traditional"))}</td>'
                f'<td>{_esc(row.get("display_ai"))}</td>'
                f'<td>{_chip(row.get("classification"), row.get("classification"))}</td>'
                "</tr>"
            )
        parts.append(_table(["Phase", "Traditional", "AI operating layer", "Class"], rows))
    elif effort.get("phase_note"):
        parts.append(_callout("Phase durations", effort["phase_note"], "note"))

    hours = effort.get("engineer_hours") or {}
    if hours.get("classification") == "not_measured":
        parts.append(_callout("Engineer hours", hours.get("reason") or "Not measured.", "note"))
    elif hours:
        rows = [
            ("Per investigation", f'{_fmt_number(hours.get("per_investigation_traditional"))} h → '
                                  f'{_fmt_number(hours.get("per_investigation_ai"))} h'),
            ("Campaign total", f'{_fmt_number(hours.get("total_traditional"))} h → '
                               f'{_fmt_number(hours.get("total_ai"))} h'),
        ]
        body = "".join(
            f"<tr><td>{_esc(label)}</td><td>{_esc(value)}</td>"
            f'<td>{_chip(hours.get("classification", "modeled"), hours.get("classification", "modeled"))}</td></tr>'
            for label, value in rows
        )
        parts.append("<h4>Engineer hours</h4>" + _table(["Scope", "Traditional → AI", "Class"], body))

    machine = effort.get("machine_execution") or []
    if machine:
        rows = []
        for row in machine:
            note = row.get("note") or ""
            source = row.get("source") or ""
            extra = f'<small>{_esc(source)}</small>' if source else ""
            label = f'<b>{_esc(row.get("label"))}</b>{extra}{f"<small>{_esc(note)}</small>" if note else ""}'
            rows.append(
                "<tr>"
                f"<td>{label}</td><td>{_esc(row.get('display'))}</td>"
                f'<td>{_chip(row.get("classification"), row.get("classification"))}</td>'
                "</tr>"
            )
        parts.append("<h4>Machine execution (observed)</h4>" + _table(["Step", "Time", "Class"], rows))

    model_cost = effort.get("model_cost")
    if model_cost:
        calls = _fmt_number(model_cost.get("model_calls"))
        cost = model_cost.get("inference_cost_usd")
        cost_text = f"${cost:.2f}" if isinstance(cost, (int, float)) else "Not measured"
        parts.append(
            _callout("Model usage", f"{calls} model calls · {cost_text} inference cost. "
                     f"{model_cost.get('note') or ''}".strip(),
                     "note")
        )

    tracked = effort.get("tracked_effects") or {}
    if tracked:
        rows = []
        for key, value in tracked.items():
            rows.append(
                "<tr>"
                f'<td>{_esc(key.replace("_", " "))}</td>'
                f'<td>{_esc(_fmt_number(value.get("traditional")))} → {_esc(_fmt_number(value.get("ai")))}</td>'
                f'<td>{_chip(value.get("classification"), value.get("classification"))}</td>'
                "</tr>"
            )
        parts.append("<h4>Tracked operational effects (modeled)</h4>"
                     + _table(["Effect", "Traditional → AI", "Class"], rows))

    unsupported = effort.get("unsupported_categories") or []
    if unsupported:
        parts.append(_details(
            f"Activities the recorded benchmark does not decompose ({len(unsupported)})",
            _bullet_list(unsupported),
        ))
    if effort.get("note"):
        parts.append(f'<p class="muted">{_esc(effort["note"])}</p>')
    return "".join(parts)


def _event_table(events: list[dict[str, Any]]) -> str:
    rows = []
    for event in events:
        offset = event.get("offset_seconds")
        offset_text = f"<br><small>+{_fmt_number(offset)} s</small>" if offset is not None else ""
        detail = event.get("detail")
        detail_text = f"<br><small>{_esc(detail)}</small>" if detail else ""
        rows.append(
            "<tr>"
            f'<td><code>{_esc(event.get("id"))}</code></td>'
            f'<td>{_esc(_fmt_timestamp(event.get("timestamp")))}'
            f"{offset_text}</td>"
            f'<td>{_esc(event.get("kind"))}</td>'
            f'<td><b>{_esc(event.get("title"))}</b>{detail_text}</td>'
            "</tr>"
        )
    return _table(["ID", "Case-clock timestamp", "Kind", "Event"], rows)


def _render_replay(replay: dict[str, Any]) -> str:
    status = replay.get("status")
    parts = ["<h3>Replay &amp; methodology</h3>"]
    if status == "not_measured":
        parts.append(_callout("Replay not measured", replay.get("reason") or "No replay artifacts.", "warn"))
        return "".join(parts)

    clock = replay.get("clock") or {}
    if clock:
        ended = clock.get("end")
        window = (f"{_esc(_fmt_timestamp(clock.get('start')))} → {_esc(_fmt_timestamp(ended))}"
                  if ended is not None else "—")
        parts.append(_callout(
            clock.get("label") or "Replay clock",
            f"{window}. Duration {_esc(_fmt_seconds(clock.get('duration_seconds')))}. "
            f"{clock.get('note') or ''} Not a wall clock: {'yes' if not clock.get('is_wall_clock') else 'no'}.",
            "info",
        ))

    if status == "process_only":
        parts.append(_callout("No synchronized two-workflow replay", replay.get("reason") or "", "warn"))
        ai_run = replay.get("ai_run") or {}
        if ai_run.get("recorded"):
            facts = []
            if ai_run.get("as_of"):
                facts.append(("Recorded as of", _fmt_timestamp(ai_run.get("as_of"))))
            if ai_run.get("objective"):
                facts.append(("Objective", ai_run.get("objective")))
            if ai_run.get("ingestion_seconds") is not None:
                facts.append(("Workbook ingestion", _fmt_seconds(ai_run.get("ingestion_seconds"))))
            if ai_run.get("investigation_seconds") is not None:
                facts.append(("Investigation (Prime SDK)", _fmt_seconds(ai_run.get("investigation_seconds"))))
            if ai_run.get("cited_evidence_count") is not None:
                facts.append(("Cited evidence records", _fmt_count(ai_run.get("cited_evidence_count"))))
            if ai_run.get("hypothesis_count") is not None:
                facts.append(("Hypotheses", _fmt_count(ai_run.get("hypothesis_count"))))
            if ai_run.get("pending_evidence_request_count") is not None:
                facts.append(("Pending evidence requests", _fmt_count(ai_run.get("pending_evidence_request_count"))))
            if ai_run.get("model_calls") is not None:
                facts.append(("Model calls (root session)", _fmt_count(ai_run.get("model_calls"))))
            parts.append(
                "<h4>Recorded AI OS pilot run (unscored)</h4>"
                + _table(["Field", "Recorded value"], [
                    f"<tr><td>{_esc(label)}</td><td>{value}</td></tr>" for label, value in facts
                ])
                + f'<p class="muted">{_esc(ai_run.get("note") or "")}</p>'
            )
        execution = replay.get("execution") or {}
        entries = execution.get("entries") or []
        if entries:
            rows = []
            for entry in entries:
                rows.append(
                    "<tr>"
                    f'<td><b>{_esc(entry.get("task"))}</b></td>'
                    f'<td>{_esc(entry.get("objective"))}</td>'
                    f'<td>{_esc(entry.get("display"))}</td>'
                    f'<td>{_chip(entry.get("classification"), entry.get("classification"))}</td>'
                    "</tr>"
                )
            intro = ""
            if execution.get("started_at"):
                intro = f'<p class="muted">Recorded run at {_esc(_fmt_timestamp(execution["started_at"]))}. {_esc(execution.get("note") or "")}</p>'
            parts.append("<h4>Recorded pipeline execution</h4>" + intro
                         + _table(["Task", "Objective", "Recorded time", "Class"], rows))
        process = replay.get("process") or {}
        experiments = process.get("experiments") or []
        if experiments:
            rows = []
            for experiment in experiments:
                deltas = []
                for item in experiment.get("largest_differences") or []:
                    flag = f" ({', '.join(item['flags'])})" if item.get("flags") else ""
                    deltas.append(f'{item.get("variable")}: Δ {_fmt_number(item.get("normalized_delta"))}{flag}')
                rows.append(
                    "<tr>"
                    f'<td><b>{_esc(experiment.get("id"))}</b></td>'
                    f'<td>{_esc(experiment.get("process_mode"))}</td>'
                    f'<td>{_esc(", ".join(experiment.get("reactors") or []))}</td>'
                    f'<td>{_esc("; ".join(deltas))}</td>'
                    "</tr>"
                )
            note = process.get("flags_note") or ""
            parts.append("<h4>Reactor-pair differences (descriptive, no causality claim)</h4>"
                         + _table(["Experiment", "Mode", "Reactors", "Largest recorded differences"], rows)
                         + (f'<p class="muted">{_esc(note)}</p>' if note else ""))
        if process.get("reference_note"):
            parts.append(f'<p class="muted">{_esc(process["reference_note"])}</p>')
        cultivations = process.get("cultivations") or []
        if cultivations:
            rows = []
            for row in cultivations:
                rows.append(
                    "<tr>"
                    f'<td><code>{_esc(row.get("id"))}</code></td>'
                    f'<td>{_esc(row.get("experiment"))}</td>'
                    f'<td>{_esc(row.get("reactor"))}</td>'
                    f'<td>{_esc(row.get("process_mode"))}</td>'
                    f'<td>{_esc(row.get("variable_count"))}</td>'
                    f'<td>{_esc(_fmt_seconds(row.get("duration_hours") * 3600) if row.get("duration_hours") else "—")}</td>'
                    "</tr>"
                )
            parts.append(_details(
                f"Aligned cultivations ({len(cultivations)})",
                _table(["Cultivation", "Experiment", "Reactor", "Mode", "Variables", "Duration"], rows),
            ))
    if status == "ok":
        milestones = replay.get("milestones") or {}
        for key, label in MILESTONE_LABELS.items():
            milestone = milestones.get(key)
            if not milestone:
                continue
            lines = []
            for track_label, track_key in (("Traditional", "traditional"), ("AI OS", "ai")):
                ref = milestone.get(track_key)
                if not ref:
                    lines.append(f'<div class="side-line"><b>{track_label}:</b> not recorded</div>')
                    continue
                lines.append(
                    f'<div class="side-line"><b>{track_label}:</b> {_esc(ref.get("title"))} · '
                    f'{_esc(_fmt_timestamp(ref.get("timestamp")))} · <code>{_esc(ref.get("event_id"))}</code></div>'
                )
            note = milestone.get("traditional_note") or milestone.get("ai_note")
            if note:
                lines.append(f'<div class="side-line muted">{_esc(note)}</div>')
            parts.append(f'<div class="mile"><h4>{_esc(label)}</h4>{"".join(lines)}</div>')

    divergences = replay.get("divergences") or []
    if divergences:
        rows = []
        for divergence in divergences:
            traditional = divergence.get("traditional") or {}
            ai = divergence.get("ai") or {}
            traditional_text = (f'{traditional.get("event_id", "—")} · {_fmt_timestamp(traditional.get("timestamp"))}'
                                if traditional else "—")
            ai_text = f'{ai.get("event_id", "—")} · {_fmt_timestamp(ai.get("timestamp"))}' if ai else "—"
            detail = divergence.get("verdict_label") or divergence.get("verdict")
            if divergence.get("difference_seconds") is not None:
                detail += f' · Δ {_fmt_seconds(divergence["difference_seconds"])}'
            if divergence.get("normalized_delta") is not None:
                detail += f' · normalized Δ {_fmt_number(divergence["normalized_delta"])}'
            rows.append(
                "<tr>"
                f'<td>{_esc(divergence.get("label"))}</td>'
                f"<td>{_esc(detail)}</td>"
                f"<td>{_esc(traditional_text)}</td>"
                f"<td>{_esc(ai_text)}</td>"
                "</tr>"
            )
        parts.append("<h4>Recorded divergences</h4>"
                     + _table(["Item", "Verdict", "Traditional", "AI OS"], rows))

    tracks = replay.get("tracks") or {}
    if tracks.get("traditional") or tracks.get("ai"):
        for track_key, label in (("traditional", "Traditional workflow trace"), ("ai", "AI operating layer trace")):
            events = tracks.get(track_key) or []
            if events:
                parts.append(_details(f"{label} ({len(events)} events)", _event_table(events)))

    wall_clock = replay.get("wall_clock") or {}
    if wall_clock.get("entries"):
        rows = []
        for entry in wall_clock["entries"]:
            note = entry.get("note")
            note_text = f"<br><small>{_esc(note)}</small>" if note else ""
            rows.append(
                "<tr>"
                f'<td><b>{_esc(entry.get("label"))}</b>{note_text}'
                f'<br><small>{_esc(entry.get("source") or "")}</small></td>'
                f'<td>{_esc(entry.get("display"))}</td>'
                f'<td>{_chip(entry.get("classification"), entry.get("classification"))}</td>'
                "</tr>"
            )
        parts.append("<h4>Wall-clock runtime (machine time, not human labor)</h4>"
                     + _table(["Step", "Time", "Class"], rows)
                     + (f'<p class="muted">{_esc(wall_clock.get("note"))}</p>' if wall_clock.get("note") else ""))

    guardrails = replay.get("guardrails") or []
    if guardrails:
        rows = []
        for guardrail in guardrails:
            rows.append(
                "<tr>"
                f'<td><b>{_esc(guardrail.get("check"))}</b></td>'
                f'<td>{_esc(guardrail.get("basis"))}</td>'
                f'<td><code>{_esc(guardrail.get("source"))}</code></td>'
                "</tr>"
            )
        parts.append("<h4>Guardrails</h4>"
                     + _table(["Check", "Basis", "Source"], rows))
    return "".join(parts)


def _render_issue_chain(chain: dict[str, Any]) -> str:
    status = chain.get("status")
    parts = ["<h3>Investigation chain</h3>"]
    if status == "not_measured":
        parts.append(_callout("Chain not measured", chain.get("reason") or "No chain artifacts.", "warn"))
        return "".join(parts)

    if status == "ok":
        moment = chain.get("moment") or {}
        parts.append(_callout(
            "Recorded replay moment",
            f"cursor {moment.get('cursor')} · {_fmt_timestamp(moment.get('cutoff'))} · {moment.get('event_id') or ''}",
            "note",
        ))
        issue = chain.get("issue") or {}
        parts.append(
            f'<h4>{_esc(issue.get("title"))}</h4>'
            f'<p>{_esc(issue.get("detail"))}</p>'
            f'<div class="chips">{_chip((issue.get("severity") or "").upper() or "severity n/a", "neutral")}'
            f'{_chip(issue.get("triage_level") or "triage n/a", "neutral")}'
            f'{_chip(issue.get("classification"), issue.get("classification"))}</div>'
        )
        hypotheses = chain.get("competing_hypotheses") or []
        if hypotheses:
            parts.append("<h4>Competing hypotheses</h4>")
            for hypothesis in hypotheses:
                confidence = hypothesis.get("confidence")
                confidence_text = f" ({confidence * 100:.0f}%)" if isinstance(confidence, (int, float)) else ""
                parts.append(
                    f'<p><b>{_esc(hypothesis.get("title"))}</b>{confidence_text} — '
                    f'supporting {len(hypothesis.get("supporting_evidence_ids") or [])}, '
                    f'contradicting {len(hypothesis.get("contradicting_evidence_ids") or [])} evidence records.</p>'
                )
        missing = chain.get("missing_information") or []
        if missing:
            parts.append("<h4>Missing information at the cutoff</h4>" + _bullet_list(missing))
        actions = chain.get("recommended_investigation") or []
        if actions:
            rows = []
            for action in actions:
                approval = "required" if action.get("requires_human_approval") else "not required"
                rows.append(
                    "<tr>"
                    f'<td>{_esc(action.get("action"))}</td>'
                    f'<td>{_esc(action.get("owner") or "unassigned")}</td>'
                    f'<td>{_esc(action.get("priority") or "—")}</td>'
                    f'<td>{_esc(approval)}</td>'
                    "</tr>"
                )
            parts.append("<h4>Recommended investigation</h4>"
                         + _table(["Action", "Owner", "Priority", "Human approval"], rows))
        escalation = chain.get("escalation_decision") or {}
        if escalation:
            parts.append(_callout("Escalation decision", f'{escalation.get("decision")} — {escalation.get("authority")}', "info"))
        supporting = chain.get("supporting_evidence") or []
        if supporting:
            rows = []
            for card in supporting:
                rows.append(
                    "<tr>"
                    f'<td><code>{_esc(card.get("id"))}</code></td>'
                    f'<td>{_esc(card.get("type"))}</td>'
                    f'<td>{_esc(_fmt_timestamp(card.get("timestamp")))}</td>'
                    f'<td>{_esc(card.get("summary"))}</td>'
                    "</tr>"
                )
            parts.append(_details(f"Supporting evidence cited at the cutoff ({len(supporting)})",
                                  _table(["ID", "Type", "Timestamp", "Summary"], rows)))
        available = chain.get("evidence_available") or {}
        if available:
            by_type = ", ".join(f"{key}: {value}" for key, value in (available.get("by_type") or {}).items())
            parts.append(_callout(
                "Evidence available at the cutoff",
                f"{available.get('count')} records existed at the cutoff ({by_type}). {available.get('guardrail') or ''}",
                "note",
            ))
        return "".join(parts)

    # CHO partial chain.
    if chain.get("reason"):
        parts.append(_callout("Partial chain", chain["reason"], "warn"))
    observation = chain.get("observation") or {}
    if observation.get("difference"):
        parts.append(
            f'<h4>Observed difference</h4><p>{_esc(observation.get("difference"))}</p>'
            f'<div class="chips">{_chip(observation.get("classification"), observation.get("classification"))}'
            + "".join(_chip(flag, "neutral") for flag in observation.get("flags") or [])
            + "</div>"
        )
        variables = observation.get("variables") or []
        if variables:
            rows = []
            for item in variables:
                rows.append(
                    "<tr>"
                    f'<td>{_esc(item.get("variable"))}</td>'
                    f'<td>{_esc(_fmt_number(item.get("normalized_delta")))}</td>'
                    f'<td>{_esc(_fmt_number(item.get("r01_mean")))}</td>'
                    f'<td>{_esc(_fmt_number(item.get("r02_mean")))}</td>'
                    f'<td>{_esc(", ".join(item.get("flags") or []) or "—")}</td>'
                    "</tr>"
                )
            parts.append(_table(["Variable", "Normalized Δ (R02−R01)", "R01 mean", "R02 mean", "Flags"], rows))
    for key, label in (
        ("hypotheses", "Hypotheses"),
        ("contradictory_evidence", "Contradictory evidence"),
        ("next_analysis", "Next analysis"),
    ):
        block = observation.get(key) or {}
        if block.get("status") == "not_measured":
            parts.append(f'<h4>{_esc(label)}</h4>' + _callout("Not measured", block.get("reason") or "", "note"))
    supporting = observation.get("supporting_evidence") or {}
    if supporting.get("records"):
        parts.append(
            f'<h4>Supporting reference</h4><p><code>{_esc(", ".join(supporting.get("records")))}</code> '
            f'{_chip(supporting.get("classification"), "neutral")}</p>'
            f'<p class="muted">{_esc(supporting.get("detail"))}</p>'
        )
    moment = chain.get("moment") or {}
    if moment:
        parts.append(f'<p class="muted">Reference: {_esc(moment.get("cultivation"))} · clock {_esc(moment.get("clock"))}</p>')
    return "".join(parts)


def _render_evidence(evidence: dict[str, Any]) -> str:
    rows = []
    for row in evidence.get("rows") or []:
        traditional = row.get("traditional") or {}
        ai = row.get("ai") or {}
        traditional_detail = traditional.get("detail")
        ai_detail = ai.get("detail")
        traditional_detail_html = f"<br><small>{_esc(traditional_detail)}</small>" if traditional_detail else ""
        ai_detail_html = f"<br><small>{_esc(ai_detail)}</small>" if ai_detail else ""
        rows.append(
            "<tr>"
            f'<td><code>{_esc(row.get("id"))}</code><br><b>{_esc(row.get("label"))}</b>'
            f'<br><small>{_esc(row.get("type"))} · {_esc(_fmt_timestamp(row.get("timestamp")))} · '
            f'{_esc(", ".join(row.get("entities") or []))}</small>'
            f'{_source_codes(row.get("sources") or [])}</td>'
            f'<td>{_chip(traditional.get("label") or traditional.get("status"), STATUS_CHIP_KINDS.get(traditional.get("status"), "neutral"))}'
            f"{traditional_detail_html}</td>"
            f'<td>{_chip(ai.get("label") or ai.get("status"), STATUS_CHIP_KINDS.get(ai.get("status"), "neutral"))}'
            f"{ai_detail_html}</td>"
            f'<td>{"yes" if row.get("pilot_cited") else "no"}</td>'
            f'<td>{_esc(row.get("influence"))}</td>'
            "</tr>"
        )
    basis = evidence.get("basis")
    annotations = evidence.get("annotations") or {}
    annotation_items = []
    for key, value in annotations.items():
        label = key.replace("_", " ")
        if isinstance(value, list):
            body = _bullet_list(value) if value else '<p class="muted">None.</p>'
        else:
            body = f"<p>{_esc(value)}</p>"
        annotation_items.append(f"<h4>{_esc(label)}</h4>{body}")
    annotations_html = "".join(annotation_items)
    return (
        "<h3>Evidence matrix</h3>"
        + (f'<p class="muted">{_esc(basis)}</p>' if basis else "")
        + _table(["Evidence", "Traditional", "AI operating layer", "Pilot cited", "Influence"], rows)
        + (f"<h3>Annotations</h3>{annotations_html}" if annotations_html else "")
    )


def _render_findings(presentation: dict[str, Any]) -> str:
    blocks = []
    for title, key in (
        ("Verified findings", "verified_findings"),
        ("Observed / modeled findings", "modeled_findings"),
        ("Not measured / unavailable", "unavailable_findings"),
        ("Limitations", "limitations"),
    ):
        items = presentation.get(key) or []
        if items:
            blocks.append(f'<div class="finding-block"><h3>{_esc(title)}</h3>{_bullet_list(items)}</div>')
    if not blocks:
        return ""
    return "<h3>Findings &amp; limitations</h3>" + "".join(blocks)


def _bar(label: str, value: float | None, display: str | None = None, maximum: float = 1, missing_label: str = "Not measured") -> str:
    if value is None:
        return f'<div class="chart-row"><span>{_esc(label)}</span><div class="chart-track missing">{_esc(missing_label)}</div></div>'
    width = max(0, min(100, value / maximum * 100)) if maximum else 0
    display = display or f"{value * 100:.1f}%"
    return (f'<div class="chart-row"><span>{_esc(label)}</span><div class="chart-track">'
            f'<i style="width:{width:.4f}%"></i></div><b>{_esc(display)}</b></div>')


def _render_comparison_groups(evaluation):
    rows = []
    for group in evaluation.get("groups", {}).values():
        rows.append("<tr>" + "".join(f"<td>{_esc(v)}</td>" for v in (
            group["label"], group["status"], group["attempted_cases"],
            "Not measured" if group["quality_qualified_rate"] is None else f'{group["quality_qualified_rate"]:.1%}',
            "Undefined" if group["effort_per_qualified_status"] == "undefined" else "Not measured" if group["human_hours_per_qualified_case"] is None else f'{group["human_hours_per_qualified_case"]:.3f} h')) + "</tr>")
    attempts = []
    for run in evaluation.get("runs", []):
        modes = run.get("failure_modes", [])
        detail = "Provider 402: insufficient balance" if "provider_payment_required_402" in modes else ", ".join(modes) if modes else "No investigation-quality claim" if run["qualification"]["status"] == "not_applicable" else run["qualification"]["status"]
        attempts.append("<tr>" + "".join(f"<td>{_esc(value)}</td>" for value in (
            f'{run["case_id"]} / {run["run_id"][:8]}', run["mode"], run["status"], detail)) + "</tr>")
    attempt_table = _details("All recorded attempts and execution failures", _table(["Case / run", "Group", "Execution", "Qualification / failure"], attempts)) if attempts else ""
    comparison = evaluation.get("comparison", {})
    reduction = comparison.get("paired_human_effort_reduction_pct")
    return ("<h3>Five comparison groups · raw-input investigations</h3>" + _table(
        ["Group", "Status", "Attempts", "Qualified rate", "Human hours / qualified case"], rows)
        + f'<p>Paired effort reduction: {"Not measured" if reduction is None else f"{reduction:.1f}%"}; matched qualified pairs: {comparison.get("paired_sample_size", 0)}.</p>'
        + attempt_table
        + '<p class="muted">Execution failures are distinct from scientific accuracy scores. Incumbents are not tested without fair hands-on access. Unsupported capabilities are N/A. Raw, clean, unfamiliar, updated and historical conditions are reported separately. Draft thresholds and routing rubrics require independent review before qualification.</p>'
        + '<p class="muted">Evaluation specification: README_benchmarks.md · manufacturing-evaluation-v2. Existing simulation scores are retained below as diagnostics; no internal RCA accuracy is established.</p>')


def _render_evaluation(evaluation: dict) -> str:
    cards = []
    for chart in evaluation.get("case_charts", []):
        plots = []
        for series in chart["series"]:
            plots.append(f'<h4>{_esc(series["label"])}</h4>' + "".join(
                _bar(row["label"], row["value"], missing_label="N/A" if row.get("status")=="not_applicable" else "Not measured") for row in series["values"]))
        cards.append(f'<article class="chart-card"><h3>{_esc(chart["title"])}</h3>'
                     f'<p class="muted">{_esc(chart["definition"])}</p>{"".join(plots)}'
                     f'{_source_codes(chart["sources"])}</article>')
    legacy_cards = []
    for chart in evaluation["charts"]:
        plots = []
        for series in chart["series"]:
            plots.append(f'<h4>{_esc(series["label"])}</h4>' + "".join(_bar(row["label"], row["value"]) for row in series["values"]))
        legacy_cards.append(f'<article class="chart-card"><h3>{_esc(chart["title"])}</h3><p>{_esc(chart["definition"])}</p>{"".join(plots)}{_source_codes(chart["sources"])}</article>')
    legacy_charts = _details("Earlier task diagnostics · different protocol and source versions", f'<div class="chart-grid">{"".join(legacy_cards)}</div>')
    maximum = max((p["minutes"] or 0 for side in evaluation["effort"] for p in side["phases"]), default=0) or 1
    effort = []
    for side in evaluation["effort"]:
        effort.append(f'<h4>{_esc(side["label"])}</h4>' + "".join(
            _bar(row["phase"].title(), row["minutes"], f'{row["minutes"]:g} person-min' if row["minutes"] is not None else None, maximum)
            for row in side["phases"]))
    outcomes = []
    for side in evaluation["outcomes"]:
        accepted, assigned = side["accepted"], side["assigned"]
        rate = side["rate"]
        outcomes.append(f'<div class="outcome-stat"><small>{_esc(side["label"])}</small>'
                        f'<strong>{"Not measured" if rate is None else f"{rate:.1%} quality-qualified"}</strong>'
                        f'<p>{"No reviewed assignments" if accepted is None else f"{accepted}/{assigned} investigations qualified"}</p>'
                        f'<p>Human hours per qualified case: {"Undefined" if side.get("status")=="undefined" else "Not measured" if side.get("hours_per_qualified") is None else _fmt_number(side.get("hours_per_qualified"))}</p></div>')
    paired = "Matching paired assignments recorded." if evaluation["paired"] else "Matched, quality-qualified comparison pending; no labor-savings claim established."
    effort_chart = f'<article class="chart-card"><h3>Where engineers spend time</h3><p class="muted">Shared scale across both workflows; missing observations are not zero minutes.</p>{"".join(effort)}</article>'
    if all(p["minutes"] is None for side in evaluation["effort"] for p in side["phases"]):
        effort_chart = _details("Human effort evaluation · seven stages, including coordination and ongoing configuration", effort_chart)
    return ("<h3>Does useful work improve—and does total manual effort fall?</h3>"
            '<p>Manufacturing quality and messy-data preparation are evaluated separately. Human effort includes every phase, including checking and corrections.</p>'
            f'<div class="chart-grid">{"".join(cards)}</div>' + legacy_charts +
            f'<p class="callout callout-note">{_esc(evaluation["qualification"])}</p>'
            '<h3>Quality comes before efficiency</h3>'
            f'<div class="outcome-grid">{"".join(outcomes)}</div><p class="muted">{paired}</p>'
            + effort_chart +
            '<p class="muted">Seven active-work stages: setup, data preparation, investigation, verification, corrections, coordination and ongoing configuration. Failed attempts count. Shared setup is allocated only across declared measured cases; first-case costs remain visible in the per-case results.</p>'
            + _render_comparison_groups(evaluation) +
            '<p class="muted">Acceptance requires completeness, evidence support, material risk coverage, correct escalation and appropriate uncertainty. Citation validity alone does not pass these gates.</p>')


def _render_experiments(experiments: dict[str, Any]) -> str:
    rows = []
    for experiment in experiments["experiments"]:
        cells = []
        for workflow in ("traditional", "ai"):
            result = experiment["sides"][workflow]
            cells.append("Not measured" if result["value"] is None else
                         f'{result["value"]:.3f} work units/h; {result["correctly_completed"]}/{result["assigned"]} accepted; {result["person_hours"]:.3f} person-hours')
        rows.append("<tr>" + "".join(f"<td>{_esc(cell)}</td>" for cell in (
            f'{experiment["id"]}. {experiment["label"]}', experiment["objective"],
            "; ".join(experiment["variants"]), *cells)) + "</tr>")
    return (
        "<h3>Engineering work experiments</h3><p class=\"muted\">Legacy five-stage protocol, preserved for reproducibility. V2 qualification and seven-stage effort use README_benchmarks.md; these earlier ledgers are not migrated into the primary endpoints.</p>"
        f'<p><b>{_esc(experiments["headline"])}</b></p>'
        "<p>Experiment A measures the end-to-end rate. Experiments B and C test unfamiliar data and trustworthiness separately. "
        "Setup, alignment, analysis, verification and rework all count; failed attempts remain in total effort. "
        "A deliverable counts only when every review gate passes.</p>"
        + _table(["Experiment", "Assignment", "Challenge / effort capture", "Traditional", "AI OS"], rows)
        + f'<p class="muted">{_esc(experiments["qualification"])}</p>'
    )


def _render_case(service: ComparisonService, case_id: str) -> str:
    payload = service.case(case_id)
    header = payload.get("header") or {}
    role = CASE_ROLE_LABELS.get(case_id, header.get("kind") or case_id)
    version = (header.get("dataset") or {}).get("version")
    chips = [_chip(header.get("kind") or "case study", "neutral")]
    if version:
        chips.append(_chip(f"dataset {version}", "neutral"))
    replay = payload.get("replay") or {}
    ai_run = replay.get("ai_run") or {}
    if case_id == "cho":
        chips.append(_chip("AI OS run: recorded pilot", "observed") if ai_run.get("recorded")
                     else _chip("AI OS run: not recorded", "not_measured"))
    presentation = payload.get("presentation") or {}
    headline = presentation.get("headline")
    assumptions = (
        _callout("Simulation savings are assumptions, not measured agent gains",
                 "The campaign assigns diagnosis delays of 12–18 hours to the traditional controller and 4–6 hours to the assisted controller. "
                 "It also assigns different engineer-effort formulas. The resulting averages and percentage reductions follow those assumptions; "
                 "repeating the simulation does not turn them into measurements of human performance. "
                 "The five-incident detection comparison is a separate synthetic context-ablation test using deterministic rules. "
                 "It is not a live Prime-agent quality score. Source: benchmark/controllers/traditional.py and benchmark/controllers/agent_assisted.py.", "warn")
        if case_id == "fresenius" else ""
    )
    return f"""
<section class="case" id="{_esc(case_id)}">
  <div class="case-head">
    <p class="label">{_esc(role)}</p>
    <h2>{_esc(header.get("name"))} — {_esc(header.get("title"))}</h2>
    <p class="question">{_esc(header.get("question"))}</p>
    <div class="chips">{"".join(chips)}</div>
  </div>
  {f'<div class="callout callout-note"><strong>Summary.</strong> {_esc(headline)}</div>' if headline else ""}
  {_render_evaluation(payload["evaluation"])}
  {_details("Dataset, provenance and scope", _render_dataset(header))}
  {_details("Evaluation protocol and acceptance criteria", _render_experiments(payload["experiments"]))}
  {_details("Supporting scorecard · includes modeled diagnostics", assumptions + _render_scorecard(payload.get("scorecard") or {}))}
  {_details("Workflow differences and effort details", _render_differences(payload.get("differences") or []) + _render_effort(payload.get("effort") or {}))}
  {_details("Recorded chronology and investigation chain", _render_replay(payload.get("replay") or {}) + _render_issue_chain(payload.get("issue_chain") or {}))}
  {_details("Evidence matrix and limitations", _render_evidence(payload.get("evidence") or {}) + _render_findings(presentation))}
</section>"""


def _render_sources(service: ComparisonService) -> str:
    rows = []
    for case_id in CASE_ORDER:
        for source in (service.case(case_id).get("header") or {}).get("inputs") or []:
            digest = None
            key = source.get("artifact")
            if key:
                digest = service.store.digest(key)
            status = "available" if source.get("available", True) else "missing"
            rows.append(
                "<tr>"
                f'<td><code>{_esc(key)}</code></td>'
                f'<td>{_esc(source.get("path"))}</td>'
                f"<td>{_esc(status)}</td>"
                f'<td>{_esc(digest or "—")}</td>'
                "</tr>"
            )
    return f"""
<section id="sources">
  <h2>Appendix — recorded artifacts</h2>
  <p>Every figure in this report is projected from the artifacts below. Content digests are shown so the
  exact input state can be verified; regenerate the report after the artifacts change.</p>
  {_table(["Artifact", "Path", "Status", "Content digest"], rows)}
  <p class="muted">Regenerate with <code>python -m benchmark.case_comparison.report</code>
  (optionally <code>--output PATH</code>). The data behind this report is also available live at
  <code>/api/case-comparison/&lt;case_id&gt;</code> when the demo server is running.</p>
</section>"""


# ------------------------------------------------------------------ assembly
def build_report(service: ComparisonService | None = None) -> str:
    """Render the full static report as a single self-contained HTML document."""
    service = service or ComparisonService()
    index = service.dashboard()
    case_links = "".join(
        f'<a href="#{_esc(item["id"])}">{_esc(item["name"])}</a>' for item in index.get("cases") or []
    )
    body = [
        '<div class="page">',
        f"""
<header class="report-nav"><a href="/" class="brand">lotic /</a>
  <nav aria-label="Main navigation"><a href="/">Demo</a><a href="/benchmark" aria-current="page">Benchmarks ↗</a></nav>
</header>
<div class="report-intro"><p class="kicker">The benchmark / evidence before claims</p>
  <h1>Real experiments.<br><span>Visible results.</span></h1>
  <p>Real CHO data. Recorded runs. Results you can inspect.</p>
</div>""",
        render_visuals(service),
        '<details class="technical"><summary>Methodology, full scorecards &amp; source artifacts</summary>',
        f'<nav class="case-toc" aria-label="Detailed case studies">{case_links}</nav>',
        _render_how_to_read(),
    ]
    for case_id in index.get("order") or CASE_ORDER:
        body.append(_render_case(service, case_id))
    body.append(_render_sources(service))
    body.append('</details>')
    body.append(
        '<p class="foot"><span>lotic / engineering, connected.</span>'
        '<span>Recorded artifacts · refresh for new completed runs · no causal claim</span></p></div>'
    )
    return (
        "<!doctype html>\n<html lang=\"en\">\n<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        f'<meta name="description" content="{_esc(REPORT_TITLE)}">\n'
        f"<title>{_esc(REPORT_TITLE)}</title>\n"
        f"<style>{REPORT_CSS}{VISUAL_CSS}</style>\n"
        "</head>\n<body>\n"
        + "".join(body)
        + "\n</body>\n</html>\n"
    )


def write_report(output: Path | None = None, service: ComparisonService | None = None) -> Path:
    """Write the report and, for the served default, its demo story."""
    if output is None or Path(output) == DEFAULT_OUTPUT:
        from .demo import build_demo
        import json
        demo_service = service or ComparisonService()
        story = {"cases": [build_demo(demo_service.case(case_id)) for case_id in CASE_ORDER]}
        story_path = Path(__file__).resolve().parents[1] / "application/static/demo-story.json"
        story_path.write_text(json.dumps(story, indent=2) + "\n", encoding="utf-8")
    path = Path(output) if output else DEFAULT_OUTPUT
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_report(service), encoding="utf-8")
    return path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the static benchmark report.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                        help="output HTML path (default: benchmark/application/static/benchmark-report.html)")
    parser.add_argument("--repository", type=Path, default=REPOSITORY,
                        help="repository root holding the recorded artifacts")
    args = parser.parse_args(argv)
    path = write_report(args.output, ComparisonService(args.repository))
    print(f"wrote {path} ({path.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
