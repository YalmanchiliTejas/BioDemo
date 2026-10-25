// Deterministic synthetic telemetry for the three campaign batches (elapsed hours 0–280).
import { ANOMALY_HOUR, BATCH_COLORS, GAP_INTERVAL } from './biomanufacturingData';

export type Point = { elapsedHours: number; value: number; imputed?: boolean };
export type Series = { id: string; color: string; dataPoints: Point[] };

const BATCH_IDS = ['MES-26071', 'MES-26072', 'MES-26073'] as const;

function noise(seed: number, i: number) {
  const x = Math.sin(seed * 9301 + i * 49297) * 233280;
  return x - Math.floor(x) - 0.5;
}

function build(fn: (h: number, b: number) => number, step = 4, seed = 1, amp = 0.2, gapOn73 = true): Series[] {
  return BATCH_IDS.map((id, b) => {
    const pts: Point[] = [];
    let i = 0;
    for (let h = 0; h <= 280; h += step) {
      const inGap = gapOn73 && b === 2 && h >= GAP_INTERVAL.startHour && h <= GAP_INTERVAL.endHour;
      const v = fn(h, b);
      if (Number.isNaN(v)) { i++; continue; }
      pts.push({ elapsedHours: h, value: +(fn(h, b) + noise(seed + b, i) * amp).toFixed(3), imputed: inGap || undefined });
      i++;
    }
    if (gapOn73 && b === 2) {
      // Make sure the gap is represented even at coarse step sizes.
      pts.push({ elapsedHours: 182.35, value: +fn(182.35, b).toFixed(3), imputed: true });
      pts.sort((a, c) => a.elapsedHours - c.elapsedHours);
    }
    return { id, color: BATCH_COLORS[id], dataPoints: pts };
  });
}

const sigmoid = (x: number) => 1 / (1 + Math.exp(-x));

/** Feed-pump delivered flow (mL/min). Feeding starts at T+72h; MES-26073 droops after the T+264.4h pressure event. */
export const feedRateSeries = build((h, b) => {
  if (h < 72) return NaN;
  const base = 16.9 - b * 0.18;
  const wear = b === 2 ? Math.max(0, h - 200) * 0.006 : b === 1 ? Math.max(0, h - 230) * 0.004 : 0;
  const droop = b === 2 ? 2.4 * sigmoid((h - ANOMALY_HOUR) * 1.4) : 0;
  return base - wear - droop;
}, 4, 3, 0.12);

/** Normalized yield index trajectory; ends at 81.2 / 78.4 / 75.9. */
export const yieldSeries = build((h, b) => {
  const end = [81.2, 78.4, 75.9][b];
  const s = sigmoid((h - 150) / 32);
  const late = b === 2 ? -1.8 * sigmoid((h - ANOMALY_HOUR) * 0.8) : 0;
  return (end + (b === 2 ? 1.8 : 0)) * s + late;
}, 4, 7, 0.25);

/** PM-204 discharge head pressure (bar). */
export const headPressureSeries = build((h, b) => {
  // MES-26073 peaks at 1.48 bar at T+264.4h (ceiling 1.20) and stays elevated afterwards.
  const base = 0.78 + b * 0.03 + h * 0.0004 * (b + 1);
  const spike = b === 2 ? 0.32 * Math.exp(-(((h - ANOMALY_HOUR) / 5) ** 2)) + (h > ANOMALY_HOUR ? 0.12 : 0) : 0;
  return base + spike;
}, 4, 11, 0.015);

export const doSeries = build((h) => 40 - 0.6 * Math.sin(h / 24), 4, 13, 0.5);
export const phSeries = build((h) => 7.05 - 0.0001 * h, 4, 17, 0.015);
export const tempSeries = build((h) => (h < 120 ? 36.8 : 34.0), 4, 19, 0.06);
export const agitationSeries = build(() => 85, 4, 23, 0.4);

export const VARIABLES = [
  { key: 'yield', label: 'Normalized yield index', unit: 'idx', series: yieldSeries, tag: 'CALC.YIELD_IDX', group: 'Calculated' },
  { key: 'feed', label: 'Feed rate (PM-204)', unit: 'mL/min', series: feedRateSeries, tag: 'PM204.FLOW_PV', group: 'Feed & pump', envelope: { min: 15.8, max: 17.6 } },
  { key: 'pressure', label: 'Head pressure (PM-204)', unit: 'bar', series: headPressureSeries, tag: 'PM204.HEAD_P', group: 'Feed & pump', envelope: { min: 0.6, max: 1.2 } },
  { key: 'do', label: 'Dissolved oxygen', unit: '%', series: doSeries, tag: 'BR.DO_A', group: 'Bioreactor', envelope: { min: 35, max: 45 } },
  { key: 'ph', label: 'pH', unit: 'pH', series: phSeries, tag: 'BR.PH_PV', group: 'Bioreactor', envelope: { min: 6.9, max: 7.2 } },
  { key: 'temp', label: 'Temperature', unit: '°C', series: tempSeries, tag: 'BR.TEMP_PV', group: 'Bioreactor' },
  { key: 'agitation', label: 'Agitation', unit: 'rpm', series: agitationSeries, tag: 'BR.AGIT_PV', group: 'Bioreactor' },
] as const;

/** Simple chromatogram for HPLC viewer (IgG1 monomer at 4.25 min). */
export const chromatogram: Array<{ t: number; mAU: number }> = Array.from({ length: 241 }, (_, i) => {
  const t = i * 0.035;
  const peak = (c: number, h: number, w: number) => h * Math.exp(-(((t - c) / w) ** 2));
  return { t: +t.toFixed(3), mAU: +(2 + peak(1.1, 18, 0.08) + peak(3.62, 9, 0.07) + peak(4.25, 312, 0.09) + peak(5.05, 14, 0.1) + noise(5, i) * 1.2).toFixed(2) };
});
