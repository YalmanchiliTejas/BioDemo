import { useId, useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import type { Point } from "./scenario";
import { cx } from "./ui";

// Extends the rules of taste-skill's charts.js (one hue on the main series, 3–5 faint gridlines, round ticks
// above the maximum, annotation labels in rows above the plot, legend drawn from the marks, plain tooltip)
// with what this product needs and the helper lacks: a reference envelope, hatched data gaps and a
// not-yet-sampled mark.

export type Series = { id: string; label: string; points: Point[]; kind: "primary" | "reference"; dots?: boolean };

export type TrendProps = {
  series: Series[];
  band?: { lo: Point[]; hi: Point[]; label: string };
  x: [number, number];
  y: [number, number];
  yTicks: number[];
  xTicks?: number[];
  title?: ReactNode;
  unit: string;
  digits?: number;
  limit?: { y: number; label: string };
  gaps?: { from: number; to: number; label: string }[];
  markers?: { x: number; label: string }[];
  pending?: { x: number; label: string };
  now?: number;
  height?: number;
  compact?: boolean;
  showXAxis?: boolean;
  legend?: boolean;
  hoverX?: number | null;
  onHoverX?: (x: number | null) => void;
  ariaLabel: string;
};

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [w, setW] = useState(0);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    setW(el.clientWidth);
    const ro = new ResizeObserver(([e]) => setW(e.contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, w] as const;
}

const linePath = (pts: Point[], sx: (v: number) => number, sy: (v: number) => number) => {
  let d = "";
  let pen = false;
  for (const [x, y] of pts) {
    if (y == null) {
      pen = false;
      continue;
    }
    d += `${pen ? "L" : "M"}${sx(x).toFixed(1)},${sy(y).toFixed(1)}`;
    pen = true;
  }
  return d;
};

const ROW = 15;
const charW = 6.4; // 11px label, estimated

export function TrendChart(p: TrendProps) {
  const [wrap, width] = useWidth<HTMLDivElement>();
  const uid = useId().replace(/:/g, "");
  const [localHover, setLocalHover] = useState<number | null>(null);
  const hoverX = p.onHoverX ? (p.hoverX ?? null) : localHover;
  const setHover = p.onHoverX ?? setLocalHover;
  const compact = p.compact ?? false;
  const showX = p.showXAxis ?? !compact;
  const digits = p.digits ?? 1;
  const fmt = (v: number) => `${v.toFixed(digits)}${p.unit ? (p.unit === "%" ? " %" : ` ${p.unit}`) : ""}`;

  const padL = compact ? 2 : 40;
  const padR = compact ? 2 : 64;
  const iw = Math.max(10, width - padL - padR);
  const sx = (v: number) => padL + ((v - p.x[0]) / (p.x[1] - p.x[0])) * iw;

  // Annotation lane: markers, "now" and the pending sample, laid out in up to two rows above the plot.
  const lane = useMemo(() => {
    if (compact || !width) return { rows: 0, items: [] as { x: number; label: string; row: number; left: boolean }[] };
    const raw = [
      ...(p.markers ?? []).map((m) => ({ x: m.x, label: m.label })),
      ...(p.now != null ? [{ x: p.now, label: "now" }] : []),
      ...(p.pending ? [{ x: p.pending.x, label: p.pending.label }] : []),
    ].sort((a, b) => a.x - b.x);
    const ends: number[] = [-Infinity, -Infinity];
    const items = raw.map((it) => {
      const w = it.label.length * charW;
      const px = sx(it.x);
      const left = px + 4 + w > padL + iw + padR;
      const start = left ? px - 4 - w : px + 4;
      let row = ends.findIndex((e) => e + 8 < start);
      if (row < 0) row = 1;
      ends[row] = start + w;
      return { ...it, row, left };
    });
    return { rows: items.length ? Math.max(...items.map((i) => i.row)) + 1 : 0, items };
  }, [p.markers, p.now, p.pending, width, compact]); // eslint-disable-line react-hooks/exhaustive-deps

  const laneH = lane.rows ? 4 + lane.rows * ROW : 0;
  const height = p.height ?? (compact ? 64 : 220);
  const padT = compact ? 6 : 8 + laneH;
  const padB = compact ? 6 : showX ? 28 : 8;
  const ih = Math.max(10, height - padT - padB);
  const sy = (v: number) => padT + ih - ((v - p.y[0]) / (p.y[1] - p.y[0])) * ih;

  const xs = useMemo(() => {
    const set = new Set<number>();
    p.series.forEach((s) => s.points.forEach(([x, y]) => y != null && set.add(x)));
    return [...set].sort((a, b) => a - b);
  }, [p.series]);

  const primary = p.series.find((s) => s.kind === "primary");
  const lastPrimary = primary ? [...primary.points].reverse().find(([, y]) => y != null) : undefined;
  const valueAt = (pts: Point[], x: number) => pts.find(([px]) => px === x)?.[1] ?? null;

  const pick = (clientX: number) => {
    const el = wrap.current;
    if (!el || !xs.length) return;
    const v = p.x[0] + ((clientX - el.getBoundingClientRect().left - padL) / iw) * (p.x[1] - p.x[0]);
    let best = xs[0];
    for (const x of xs) if (Math.abs(x - v) < Math.abs(best - v)) best = x;
    setHover(best);
  };
  const onKey = (e: KeyboardEvent) => {
    if (!xs.length) return;
    const i = hoverX == null ? -1 : xs.indexOf(hoverX);
    if (e.key === "ArrowRight") setHover(xs[Math.min(xs.length - 1, i + 1)]);
    else if (e.key === "ArrowLeft") setHover(xs[Math.max(0, i < 0 ? xs.length - 1 : i - 1)]);
    else if (e.key === "Escape" && hoverX != null) setHover(null);
    else return;
    e.preventDefault();
    e.stopPropagation();
  };

  const inGap = hoverX != null ? p.gaps?.find((g) => hoverX >= g.from && hoverX <= g.to) : undefined;

  const legend = p.legend !== false && !compact && (
    <span className="legend">
      {p.series.map((s) => (
        <span key={s.id}>
          <svg width="16" height="8" aria-hidden="true">
            <line x1="0" x2="16" y1="4" y2="4" className={cx("tc-line", `tc-${s.kind}`)} />
          </svg>
          {s.label}
        </span>
      ))}
      {p.band && (
        <span>
          <svg width="12" height="8" aria-hidden="true">
            <rect width="12" height="8" className="tc-band" />
          </svg>
          {p.band.label}
        </span>
      )}
      {p.pending && (
        <span>
          <svg width="10" height="10" aria-hidden="true">
            <circle cx="5" cy="5" r="3.5" className="tc-pending" />
          </svg>
          Not yet sampled
        </span>
      )}
      {p.gaps?.length ? (
        <span>
          <svg width="12" height="8" aria-hidden="true">
            <rect width="12" height="8" fill={`url(#hatch-${uid})`} />
          </svg>
          No data
        </span>
      ) : null}
    </span>
  );

  return (
    <figure className={cx("trend", compact && "is-compact")}>
      {!compact && (p.title || legend) && (
        <figcaption className="chart-head">
          {p.title && <span className="chart-title">{p.title}</span>}
          {legend}
        </figcaption>
      )}
      <div
        ref={wrap}
        className="trend-plot"
        style={{ height }}
        tabIndex={compact ? -1 : 0}
        role="img"
        aria-label={p.ariaLabel}
        onPointerMove={compact ? undefined : (e) => pick(e.clientX)}
        onPointerLeave={compact ? undefined : () => setHover(null)}
        onKeyDown={compact ? undefined : onKey}
        onBlur={compact ? undefined : () => setHover(null)}
      >
        {width > 0 && (
          <svg width={width} height={height} aria-hidden="true">
            <defs>
              <pattern id={`hatch-${uid}`} width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
                <line x1="0" y1="0" x2="0" y2="5" className="tc-hatch" />
              </pattern>
            </defs>
            {!compact &&
              p.yTicks.map((t) => (
                <g key={t}>
                  <line x1={padL} x2={padL + iw} y1={sy(t)} y2={sy(t)} className="tc-grid" shapeRendering="crispEdges" />
                  <text x={padL - 8} y={sy(t)} dy="0.32em" textAnchor="end" className="tc-axis">
                    {t}
                  </text>
                </g>
              ))}
            {p.gaps?.map((g) => <rect key={g.from} x={sx(g.from)} y={padT} width={sx(g.to) - sx(g.from)} height={ih} fill={`url(#hatch-${uid})`} />)}
            {p.band && (
              <path
                className="tc-band"
                d={
                  linePath(p.band.hi, sx, sy) +
                  [...p.band.lo]
                    .reverse()
                    .filter(([, y]) => y != null)
                    .map(([x, y]) => `L${sx(x).toFixed(1)},${sy(y as number).toFixed(1)}`)
                    .join("") +
                  "Z"
                }
              />
            )}
            {p.limit && (
              <g>
                <line x1={padL} x2={padL + iw} y1={sy(p.limit.y)} y2={sy(p.limit.y)} className="tc-ref" />
                {!compact && (
                  <text x={padL + iw + 8} y={sy(p.limit.y)} dy="0.32em" className="tc-note">
                    {p.limit.label}
                  </text>
                )}
              </g>
            )}
            {lane.items.map((m) => (
              <g key={m.label + m.x}>
                <line x1={sx(m.x)} x2={sx(m.x)} y1={8 + m.row * ROW + 2} y2={padT + ih} className={m.label === "now" ? "tc-now" : "tc-marker"} />
                <text x={sx(m.x) + (m.left ? -4 : 4)} y={8 + m.row * ROW + 9} textAnchor={m.left ? "end" : "start"} className="tc-note">
                  {m.label}
                </text>
              </g>
            ))}
            {p.series.map((s) => (
              <path key={s.id} d={linePath(s.points, sx, sy)} className={cx("tc-line", `tc-${s.kind}`)} />
            ))}
            {p.series
              .filter((s) => s.dots)
              .map((s) =>
                s.points
                  .filter(([, y]) => y != null)
                  .map(([x, y]) => <circle key={s.id + x} cx={sx(x)} cy={sy(y as number)} r={compact ? 2 : 2.75} className="tc-dot" />),
              )}
            {p.pending && <circle cx={sx(p.pending.x)} cy={lastPrimary && lastPrimary[1] != null ? sy(lastPrimary[1]) : padT + ih / 2} r="4" className="tc-pending" />}
            {lastPrimary && lastPrimary[1] != null && !compact && (() => {
              const near = p.now != null && Math.abs(sx(p.now) - sx(lastPrimary[0])) < 36;
              return (
                <text x={sx(lastPrimary[0]) + (near ? -6 : 8)} y={sy(lastPrimary[1]) + (near ? -12 : 0)} dy="0.32em" textAnchor={near ? "end" : "start"} className="tc-end">
                  {lastPrimary[1].toFixed(digits)}
                </text>
              );
            })()}
            {showX &&
              (p.xTicks ?? []).map((t, i, all) => (
                <text key={t} x={sx(t)} y={padT + ih + 19} textAnchor={i === 0 ? "start" : i === all.length - 1 ? "end" : "middle"} className="tc-axis">
                  {i === all.length - 1 ? `${t} h` : t}
                </text>
              ))}
            {hoverX != null && !compact && (
              <g>
                <line x1={sx(hoverX)} x2={sx(hoverX)} y1={padT} y2={padT + ih} className="tc-cross" />
                {p.series.map((s) => {
                  const v = valueAt(s.points, hoverX);
                  return v == null ? null : <circle key={s.id} cx={sx(hoverX)} cy={sy(v)} r="4" className={cx("tc-hover", `tc-${s.kind}`)} />;
                })}
              </g>
            )}
          </svg>
        )}
        {hoverX != null && !compact && width > 0 && (
          <div className="chart-tip" style={{ left: Math.min(width - 200, Math.max(0, sx(hoverX) + 12)), top: padT }} role="status">
            <b>{hoverX} h</b>
            {p.series.map((s) => {
              const v = valueAt(s.points, hoverX);
              return v == null ? null : (
                <span key={s.id}>
                  {s.label}
                  <em>{fmt(v)}</em>
                </span>
              );
            })}
            {p.band &&
              (() => {
                const lo = valueAt(p.band.lo, hoverX);
                const hi = valueAt(p.band.hi, hoverX);
                return lo != null && hi != null ? (
                  <span>
                    {p.band.label}
                    <em>
                      {lo.toFixed(digits)}–{hi.toFixed(digits)}
                    </em>
                  </span>
                ) : null;
              })()}
            {inGap && <span>{inGap.label}</span>}
          </div>
        )}
      </div>
    </figure>
  );
}
