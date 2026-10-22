"""Compact, artifact-backed figures for the benchmark's public landing page."""
from __future__ import annotations

import html
import json
import math
from collections import defaultdict


def esc(value):
    return html.escape(str(value), quote=True)


CSS = """
:root{--ink:#183c32;--muted:#738077;--line:#dfe5dd;--bg:#f5f6f1;--panel:#fff}
body{color:var(--ink);background:var(--bg);font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
.page{max-width:1180px;padding:0 28px 50px}.report-nav{display:flex;justify-content:space-between;align-items:center;padding:24px 0;border-bottom:1px solid var(--line)}
.report-nav .brand{font-size:27px;font-weight:650;letter-spacing:-1.5px;text-decoration:none;color:var(--ink)}.report-nav nav{display:flex;gap:22px}.report-nav nav a{font-size:12px;color:var(--ink);text-decoration:none}
.report-intro{padding:54px 0 32px}.kicker{font:10px ui-monospace,monospace;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}
.report-intro h1{font-size:clamp(36px,5vw,60px);font-weight:500;letter-spacing:-2.6px;line-height:1.08;margin:18px 0}.report-intro h1 span{color:#829283}.report-intro>p:last-child{font-size:15px;color:var(--muted)}
.visual-section{background:none;border:0;padding:0;margin:0 0 38px}.visual-heading{display:flex;justify-content:space-between;gap:20px;align-items:center;margin:20px 0}.visual-heading h2{font-size:22px;font-weight:550;letter-spacing:-.6px}.basis-tag{font:10px ui-monospace,monospace;border:1px solid var(--line);padding:6px 10px;border-radius:20px;color:var(--muted)}
.hero-stats{display:grid;grid-template-columns:1.6fr 1fr 1fr;background:#193e33;color:#fff;border-radius:14px;margin-bottom:18px;overflow:hidden}.hero-stat{padding:28px;border-right:1px solid #ffffff20}.hero-stat:last-child{border:0}.hero-stat strong{font-size:clamp(28px,4.5vw,52px);font-weight:500;letter-spacing:-1.8px;display:block;line-height:1.25;margin:9px 0}.hero-stat small{color:#b8ccc0;font-size:11px}.hero-stat .kicker{color:#b8ccc0}.hero-stat p{font-size:11px;color:#b8ccc0;margin:0}
.visual-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}.figure{min-width:0;background:white;border:1px solid var(--line);border-radius:12px;padding:24px;margin:0}.figure h3{font-size:17px;font-weight:550;margin:10px 0 5px;letter-spacing:-.3px}.figure .deck{font-size:12px;color:var(--muted);margin-bottom:20px}.figure figcaption,.visual-note{font-size:11px;color:var(--muted);line-height:1.6;margin-top:16px}.figure figcaption code{font-size:10px;white-space:normal;overflow-wrap:anywhere}.figure svg{width:100%;height:auto;display:block}.figure svg text{font-family:ui-monospace,monospace;fill:#738077;font-size:10px}.legend-inline{display:flex;gap:18px;font-size:10px;color:var(--muted);flex-wrap:wrap;margin:10px 0 18px}.legend-inline i{display:inline-block;width:8px;height:8px;background:#1a8061;border-radius:50%;margin-right:6px}.legend-inline .second{background:#bd8a48}.legend-inline .fail{background:#ba7968}
.visual-bar{display:grid;grid-template-columns:98px minmax(0,1fr) 52px;gap:10px;align-items:center;font-size:11px;margin:14px 0}.visual-bar>span{color:var(--muted)}.visual-bar b{font:11px ui-monospace,monospace;text-align:right}.visual-track{height:12px;background:#edf0e9;border-radius:3px;overflow:hidden}.visual-track i{display:block;height:100%;background:#1a8061;border-radius:3px}.visual-track i.second{background:#bd8a48}.visual-track i.fail{background:#ba7968}.bar-axis{display:flex;justify-content:space-between;margin:0 62px 0 108px;color:var(--muted);font:9px ui-monospace,monospace}.pending{border:1px dashed #c7d1c6;padding:16px;border-radius:8px;font-size:12px;color:var(--muted);margin-top:18px}.status-strip{display:flex;gap:4px;height:9px;margin:18px 0 12px;border-radius:4px;overflow:hidden}.status-strip span{flex:1;background:#1a8061}.status-strip .failed{background:#ba7968}.status-strip .other{background:#d6c493}
.technical{margin-top:32px}.technical>summary{font-size:13px;padding:18px 20px}.technical section{margin:16px 0}.technical .case-head h2{font-size:20px}.foot{display:flex;justify-content:space-between;gap:20px;border-top:1px solid var(--line);padding-top:20px;font-size:10px}
@media(max-width:650px){.page{padding-inline:18px}.report-intro{padding-top:34px}.report-intro h1{letter-spacing:-1.5px}.visual-grid{grid-template-columns:1fr}.hero-stats{grid-template-columns:1fr 1fr}.hero-stat{padding:20px}.hero-stat:first-child{grid-column:1/-1;border-bottom:1px solid #ffffff20}.hero-stat strong{font-size:35px}.visual-heading{align-items:flex-start}.basis-tag{max-width:150px;text-align:center}.figure{padding:18px}.report-nav nav{gap:16px}.foot{flex-direction:column}}
@media print{.technical{display:none}.visual-section,.figure,.hero-stats{break-inside:avoid}.page{max-width:none}.report-intro{padding-top:20px}}
"""


def bar(label, value, display=None, maximum=1, kind=""):
    if value is None:
        return f'<div class="visual-bar"><span>{esc(label)}</span><span>Not measured</span></div>'
    width = max(0, min(100, value / maximum * 100))
    return (f'<div class="visual-bar"><span>{esc(label)}</span><div class="visual-track">'
            f'<i class="{kind}" style="width:{width:.4f}%"></i></div>'
            f'<b>{esc(display if display is not None else f"{value:.1%}")}</b></div>')


def figure(kicker, title, deck, content, caption):
    return (f'<figure class="figure"><div class="kicker">{esc(kicker)}</div><h3>{esc(title)}</h3>'
            f'<p class="deck">{esc(deck)}</p>{content}<figcaption>{caption}</figcaption></figure>')


def load_runs(repository):
    """Read published run artifacts only; an in-progress write can be retried on refresh."""
    runs = []
    for path in sorted((repository / "results/evaluation").glob("*/run.json")):
        try:
            run = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if run.get("benchmark_id") == "cho" and run.get("version") == "manufacturing-evaluation-v2":
            # Reports need metadata and scores, not the large embedded agent output.
            runs.append({key: run.get(key) for key in (
                "run_id", "version", "benchmark_id", "case_id", "condition", "mode",
                "status", "started_at", "wall_clock_seconds", "objective_scores",
            )})
    return sorted(runs, key=lambda r: (r.get("started_at", ""), r["run_id"]))


def reconstruction_chart(service):
    source = service.store.get("cho_full_series") or {}
    groups = defaultdict(lambda: [0, 0])
    for row in source.get("files", []):
        experiment = row["aligned_csv"].split("_")[0]
        for measurement in row.get("measurements", {}).values():
            groups[experiment][0] += measurement.get("within_tolerance", 0)
            groups[experiment][1] += measurement.get("pairs", 0)
    bars = "".join(bar(key, correct / total if total else None, f"{correct/total:.2%}" if total else None)
                   for key, (correct, total) in sorted(groups.items()))
    return figure("01 / reconstruction", "Does the pipeline preserve the data?", "Conventional pipeline · agreement by experiment",
                  '<div class="bar-axis"><span>0%</span><span>100%</span></div>' + (bars or '<p class="pending">Reconstruction results pending.</p>'),
                  'Publisher-aligned reference · normalized tolerance ≤ 0.01. '
                  f'{source.get("missing_reconstruction_values", "—")} missing values excluded from the agreement denominator. '
                  '<code>benchmarks/cho/reports/full_series_comparison.json</code>')


def trajectory_chart(service):
    variable = "Dissolved CO2 (%-sat)"
    lines = []
    for reactor in ("R01", "R02"):
        try:
            points = service.series(f"EXP001_batch_{reactor}", [variable], 100)["variables"][variable]["points"]
        except KeyError:
            points = []
        lines.append([(x, y) for x, y in points if math.isfinite(x) and math.isfinite(y)])
    all_points = [p for points in lines for p in points]
    if not all_points:
        content = '<p class="pending">Published trajectories unavailable.</p>'
    else:
        xmax = max(x for x, _ in all_points) or 1
        ymax = max(y for _, y in all_points) * 1.1 or 1
        svg = ['<svg viewBox="0 0 480 280" role="img" aria-label="EXP001 dissolved CO2 over cultivation time, reactors R01 and R02"><title>Published CHO trajectories · dissolved CO2 (%-sat)</title>']
        for i in range(5):
            y = 224 - i * 48
            svg.append(f'<path d="M46 {y}H464" stroke="#e8ece5"/><text x="36" y="{y+3}" text-anchor="end">{ymax*i/4:.0f}</text>')
            x = 46 + i * 104.5
            svg.append(f'<text x="{x}" y="245" text-anchor="middle">{xmax*i/4:.0f}</text>')
        for points, color in zip(lines, ("#1a8061", "#bd8a48")):
            coords = " ".join(f'{46+x/xmax*418:.2f},{224-y/ymax*192:.2f}' for x, y in points)
            svg.append(f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="2.2"/>')
        svg.append('<text x="255" y="272" text-anchor="middle">Time since inoculation (h)</text></svg>')
        content = '<div class="legend-inline"><span><i></i>Reactor 01</span><span><i class="second"></i>Reactor 02</span></div>' + "".join(svg)
    return figure("02 / process comparison", "Same experiment. Two trajectories.", "EXP001 · dissolved CO₂ (% saturation)", content,
                  'Downsampled publisher reference. Descriptive process comparison; no causal or yield claim. '
                  '<code>benchmarks/cho/reference/aligned/EXP001_batch_R0{1,2}_inline.csv</code>')


def run_charts(runs):
    # Keep task, condition and workflow visible; never pool different experiments into one score.
    cohorts = defaultdict(list)
    for run in runs:
        cohorts[(run.get("case_id"), run.get("condition"), run.get("mode"))].append(run)
    labels = {"full_rlm": "Manufacturing OS", "retrieval_llm": "Retrieval + LLM", "conventional": "Conventional", "manual": "Manual engineer"}
    cards = []
    for (case, condition, mode), group in sorted(cohorts.items()):
        scored = [r for r in group if r.get("objective_scores") and r.get("status") == "completed"]
        if not scored:
            continue
        bars = '<div class="legend-inline"><span><i></i>Field accuracy</span><span><i class="second"></i>Field coverage</span></div>'
        for run in scored:
            score = run["objective_scores"].get("data_preparation", {})
            short = run["run_id"][:6]
            bars += bar(f'{short} · accuracy', score.get("field_accuracy", {}).get("value"))
            bars += bar(f'{short} · coverage', score.get("field_coverage", {}).get("value"), kind="second")
        cards.append(figure(f"{case} / {condition} / {labels.get(mode, mode)}", "Correct fields. Complete coverage?", f"{len(scored)} scored outputs · every completed attempt shown", bars,
                             'Frozen field checks, not all-cell accuracy or investigation quality. Missing checks reduce coverage. '
                             '<code>results/evaluation/*/run.json → objective_scores.data_preparation</code>'))
    if not cards:
        cards.append(figure("03 / AI evaluation", "Results are on the way.", "Completed CHO outputs will appear here on refresh.",
                            '<p class="pending">No scored CHO outputs recorded yet.</p>', 'Execution completion and investigation qualification are reported separately.'))
    if runs:
        maximum = max((r.get("wall_clock_seconds") or 0 for r in runs), default=1) or 1
        completed = sum(r.get("status") == "completed" for r in runs)
        failed = sum(r.get("status") == "failed" for r in runs)
        strips = ''.join(f'<span class="{"failed" if r.get("status")=="failed" else "" if r.get("status")=="completed" else "other"}" title="{esc(r["run_id"]+": "+r.get("status", "unknown"))}"></span>' for r in runs)
        bars = ''.join(bar(f'{r.get("case_id")} · {r["run_id"][:6]}', r.get("wall_clock_seconds"),
                           f'{r["wall_clock_seconds"]/60:.1f}m' if r.get("wall_clock_seconds") is not None else None,
                           maximum, "fail" if r.get("status") == "failed" else "") for r in runs)
        cards.append(figure("04 / execution", "Every attempt counts.", f"{completed} completed · {failed} failed · {len(runs)-completed-failed} other", '<div class="status-strip">'+strips+'</div><div class="legend-inline"><span><i></i>Completed</span><span><i class="fail"></i>Failed</span></div>'+bars,
                            'Machine wall time, not human effort. All recorded CHO attempts across tasks, conditions and methods; no pooled speedup. '
                            '<code>results/evaluation/*/run.json → wall_clock_seconds</code>'))
    return ''.join(cards)


def render_visuals(service):
    source = service.store.get("cho_full_series") or {}
    manifest = service.store.get("cho_normalization_manifest") or {}
    inventory = service.store.get("cho_inventory") or {}
    agreement = source.get("within_tolerance_fraction")
    agreement_text = f"{agreement:.3%}" if agreement is not None else "Pending"
    count = source.get("comparable_values")
    count_text = f"{count/1e6:.1f}M" if count is not None else "—"
    cultivations = len(manifest.get("cultivations", []))
    workbooks = len(inventory.get("workbooks", []))
    # Like the other report sections, keep a consistent snapshot per service.
    # The HTTP route creates a fresh service on each refresh.
    snapshot_key = ("cho", "visual_runs")
    if snapshot_key not in service._cache:
        service._cache[snapshot_key] = load_runs(service.repository)
    runs = service._cache[snapshot_key]
    return f'''
<section class="visual-section" id="cho-results">
  <div class="visual-heading"><h2>CHO: from raw files to comparable experiments.</h2><span class="basis-tag">Published laboratory data</span></div>
  <div class="hero-stats">
    <div class="hero-stat"><div class="kicker">Conventional reconstruction</div><strong>{agreement_text}</strong><p>agreement with publisher-aligned values</p></div>
    <div class="hero-stat"><div class="kicker">Scale checked</div><strong>{count_text}</strong><p>comparable measurement values</p></div>
    <div class="hero-stat"><div class="kicker">Dataset</div><strong>{cultivations or '—'}</strong><p>cultivations across {workbooks or '—'} workbooks</p></div>
  </div>
  <div class="visual-grid">{reconstruction_chart(service)}{trajectory_chart(service)}</div>
  <div class="visual-heading"><h2>CHO benchmark runs.</h2><span class="basis-tag">{len(runs)} recorded attempts</span></div>
  <div class="visual-grid">{run_charts(runs)}</div>
  <p class="visual-note">Investigation quality and human-effort savings await matched reviews and measured effort. Charts above report technical checks and execution only.</p>
</section>
{render_synthetic(service)}'''


def render_synthetic(service):
    metrics = {m['id']: m for m in service.section('fresenius', 'scorecard')['metrics']}
    metric = metrics.get('incident_detection_recall', {})
    content = bar('Rules baseline', metric.get('traditional', {}).get('value'), kind='second') + bar('Connected rules', metric.get('ai', {}).get('value'))
    sources = ''.join(f'<code>{esc(s.get("path", ""))}</code> ' for s in metric.get('sources', []))
    return '<section class="visual-section"><div class="visual-heading"><h2>Why connected evidence matters.</h2><span class="basis-tag">Synthetic diagnostic</span></div>' + figure(
        'Separate test / five seeded incidents', 'How many incidents were detected?',
        'Deterministic rules with different evidence access · 0–100% scale', content,
        'Synthetic context-ablation test. These are deterministic rule results; no live-agent or real-world prevention claim. '+sources) + '</section>'
