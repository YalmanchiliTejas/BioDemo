import type { Kit } from './labKit';

/* Canvas drawings for in-world screens and signage. Values mirror the synthetic demo campaign used in the hero copy. */

type Ctx = CanvasRenderingContext2D;
export type Draw = (ctx: Ctx, w: number, h: number) => void;

const TEAL = '#38b2c6';
const TEAL_DARK = '#0e7490';
const AMBER = '#e0a43a';
const RED = '#e5534b';

function trend(ctx: Ctx, x: number, y: number, w: number, h: number, values: number[], color: string, width = 2) {
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.lineJoin = 'round';
  ctx.beginPath();
  values.forEach((v, i) => {
    const px = x + (i / (values.length - 1)) * w;
    const py = y + h - v * h;
    if (i) ctx.lineTo(px, py); else ctx.moveTo(px, py);
  });
  ctx.stroke();
}

const wave = (n: number, base: number, amp: number, seed: number, drop?: [number, number]) =>
  Array.from({ length: n }, (_, i) => {
    let v = base + Math.sin(i * 0.37 + seed) * amp + Math.sin(i * 1.7 + seed * 3) * amp * 0.35;
    if (drop && i > drop[0]) v -= drop[1] * Math.min(1, (i - drop[0]) / 6);
    return v;
  });

function grid(ctx: Ctx, x: number, y: number, w: number, h: number, color: string, rows = 4, cols = 8) {
  ctx.strokeStyle = color;
  ctx.lineWidth = 1;
  for (let i = 0; i <= rows; i++) { ctx.beginPath(); ctx.moveTo(x, y + (i * h) / rows); ctx.lineTo(x + w, y + (i * h) / rows); ctx.stroke(); }
  for (let i = 0; i <= cols; i++) { ctx.beginPath(); ctx.moveTo(x + (i * w) / cols, y); ctx.lineTo(x + (i * w) / cols, y + h); ctx.stroke(); }
}

function dark(ctx: Ctx, w: number, h: number) {
  const g = ctx.createLinearGradient(0, 0, 0, h);
  g.addColorStop(0, '#0f1d22');
  g.addColorStop(1, '#0a1418');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, w, h);
}

function light(ctx: Ctx, w: number, h: number) {
  ctx.fillStyle = '#f3f5f6';
  ctx.fillRect(0, 0, w, h);
}

function header(kit: Kit, ctx: Ctx, w: number, title: string, sub: string, isDark: boolean, s = 1) {
  ctx.fillStyle = isDark ? '#14272d' : '#0b1e22';
  ctx.fillRect(0, 0, w, 44 * s);
  kit.text(ctx, title, 18 * s, 29 * s, 18 * s, '#ffffff', 600);
  kit.text(ctx, sub, w - 18 * s, 29 * s, 14 * s, '#9fb4ba', 500, 'right');
}

export function screens(kit: Kit) {
  const t = kit.text.bind(kit);
  return {
    hmiBioreactor: ((ctx, w, h) => {
      dark(ctx, w, h);
      header(kit, ctx, w, 'BR-UP-01', 'MES-26073 · day 9', true);
      const tiles: [string, string, string][] = [['Temp', '36.9 °C', TEAL], ['pH', '7.02', TEAL], ['DO', '41 %', TEAL], ['Agit.', '72 rpm', TEAL]];
      tiles.forEach(([k, v, c], i) => {
        const x = 16 + i * ((w - 32) / 4);
        ctx.fillStyle = '#13262c';
        ctx.fillRect(x, 58, (w - 32) / 4 - 10, 64);
        t(ctx, k, x + 10, 80, 13, '#7f979e');
        t(ctx, v, x + 10, 110, 22, c, 600);
      });
      grid(ctx, 16, 140, w - 32, h - 210, 'rgba(120,160,170,0.12)');
      trend(ctx, 16, 150, w - 32, h - 230, wave(60, 0.62, 0.03, 1, [44, 0.22]), TEAL, 2.5);
      trend(ctx, 16, 150, w - 32, h - 230, wave(60, 0.35, 0.02, 4, [44, -0.18]), AMBER, 2);
      ctx.fillStyle = 'rgba(229,83,75,0.16)';
      ctx.fillRect(16 + (w - 32) * 0.74, 140, (w - 32) * 0.26, h - 210);
      ctx.fillStyle = '#3a1c1c';
      ctx.fillRect(16, h - 56, w - 32, 40);
      t(ctx, 'PM-204 head pressure 1.48 bar  ·  limit 1.20', 28, h - 30, 15, '#ffb4ae', 600);
    }) as Draw,

    mes: ((ctx, w, h) => {
      light(ctx, w, h);
      header(kit, ctx, w, 'MES · Electronic batch record', 'read-only', false);
      t(ctx, 'Batch MES-26073  ·  BR-UP-01  ·  CHO fed-batch', 18, 76, 15, '#0b1e22', 600);
      const rows = ['Media prep verified', 'Inoculation', 'Feed 1 · FM-2207', 'Feed 2 · FM-2207', 'Temperature shift', 'Feed 3', 'Harvest'];
      rows.forEach((r, i) => {
        const y = 100 + i * 38;
        ctx.fillStyle = i % 2 ? '#ffffff' : '#eef1f3';
        ctx.fillRect(14, y, w - 28, 36);
        t(ctx, r, 26, y + 24, 14, '#334148');
        const done = i < 5;
        ctx.fillStyle = done ? TEAL_DARK : i === 5 ? AMBER : '#b7c0c5';
        ctx.beginPath(); ctx.arc(w - 40, y + 18, 7, 0, Math.PI * 2); ctx.fill();
        t(ctx, done ? 'signed' : i === 5 ? 'open' : 'pending', w - 56, y + 23, 13, '#6b7a81', 500, 'right');
      });
    }) as Draw,

    historian: ((ctx, w, h) => {
      dark(ctx, w, h);
      header(kit, ctx, w, 'PI historian · BR-UP-01', 'read-only', true);
      grid(ctx, 16, 60, w - 32, h - 90, 'rgba(120,160,170,0.12)', 5, 10);
      ctx.fillStyle = 'rgba(224,164,58,0.13)';
      ctx.fillRect(16 + (w - 32) * 0.52, 60, (w - 32) * 0.09, h - 90);
      t(ctx, 'gap 42 min', 16 + (w - 32) * 0.535, 82, 12, AMBER, 600);
      trend(ctx, 16, 70, w - 32, h - 110, wave(90, 0.7, 0.04, 2, [70, 0.2]), TEAL, 2.2);
      trend(ctx, 16, 70, w - 32, h - 110, wave(90, 0.45, 0.03, 5), '#8fb8c1', 1.6);
      trend(ctx, 16, 70, w - 32, h - 110, wave(90, 0.22, 0.02, 9, [70, -0.25]), AMBER, 1.8);
    }) as Draw,

    lims: ((ctx, w, h) => {
      light(ctx, w, h);
      header(kit, ctx, w, 'LIMS · Sample results', 'read-only', false);
      const cols = ['Sample', 'Test', 'Result', 'Spec'];
      cols.forEach((c, i) => t(ctx, c, 22 + i * ((w - 40) / 4), 76, 13, '#6b7a81', 600));
      const rows = [['S-26073-11', 'VCD', '18.2', '≥ 12'], ['S-26073-11', 'Viability', '94 %', '≥ 85'], ['S-26073-12', 'Titer', '3.1 g/L', 'info'], ['S-26073-12', 'Glucose', '2.4 g/L', '1–6'], ['S-26073-13', 'Lactate', '1.9 g/L', '< 4'], ['S-26073-13', 'Osmol.', '338', '< 420']];
      rows.forEach((r, j) => {
        const y = 90 + j * 34;
        ctx.fillStyle = j % 2 ? '#ffffff' : '#eef1f3';
        ctx.fillRect(14, y, w - 28, 32);
        r.forEach((c, i) => t(ctx, c, 22 + i * ((w - 40) / 4), y + 22, 14, i === 2 ? '#0b1e22' : '#334148', i === 2 ? 600 : 400));
      });
    }) as Draw,

    plantOverview: ((ctx, w, h) => {
      dark(ctx, w, h);
      header(kit, ctx, w, 'Plant overview · Suite 2', 'CMP-26-10', true, 1.4);
      const units: [string, string, string][] = [['BR-UP-01', 'Running · alarm', RED], ['BR-UP-02', 'Running', TEAL], ['LYO-02', 'Primary drying', TEAL], ['BSC-03', 'Airflow OK', TEAL], ['Receipt', '8 files verified', TEAL], ['QA review', '1 pending', AMBER]];
      units.forEach(([n, s, c], i) => {
        const x = 24 + (i % 3) * ((w - 48) / 3);
        const y = 90 + Math.floor(i / 3) * ((h - 110) / 2);
        const tw = (w - 48) / 3 - 18, th = (h - 110) / 2 - 18;
        ctx.fillStyle = '#13262c';
        ctx.fillRect(x, y, tw, th);
        ctx.fillStyle = c;
        ctx.fillRect(x, y, 6, th);
        t(ctx, n, x + 24, y + 48, 30, '#e6eef0', 600);
        t(ctx, s, x + 24, y + 88, 22, '#8fa7ad');
        trend(ctx, x + 24, y + th - 70, tw - 48, 46, wave(30, 0.5, 0.18, i * 2), c, 2.5);
      });
    }) as Draw,

    lyo: ((ctx, w, h) => {
      dark(ctx, w, h);
      header(kit, ctx, w, 'LYO-02 · Primary drying', 'step 4 / 7', true);
      const tiles: [string, string][] = [['Shelf', '−25.0 °C'], ['Chamber', '0.10 mbar'], ['Product', '−33.8 °C'], ['Condenser', '−68 °C']];
      tiles.forEach(([k, v], i) => {
        const x = 16 + (i % 2) * ((w - 32) / 2), y = 58 + Math.floor(i / 2) * 58;
        ctx.fillStyle = '#13262c';
        ctx.fillRect(x, y, (w - 32) / 2 - 10, 50);
        t(ctx, k, x + 10, y + 20, 12, '#7f979e');
        t(ctx, v, x + 10, y + 42, 18, TEAL, 600);
      });
      const top = 186, ch = h - top - 24;
      grid(ctx, 16, top, w - 32, ch, 'rgba(120,160,170,0.12)', 4, 8);
      ctx.setLineDash([8, 6]);
      ctx.strokeStyle = AMBER;
      ctx.lineWidth = 2;
      ctx.beginPath(); ctx.moveTo(16, top + ch * 0.28); ctx.lineTo(w - 16, top + ch * 0.28); ctx.stroke();
      ctx.setLineDash([]);
      t(ctx, 'vapor limit', w - 22, top + ch * 0.28 - 8, 12, AMBER, 600, 'right');
      const curve = Array.from({ length: 50 }, (_, i) => 0.1 + Math.sin((i / 49) * Math.PI) * 0.52);
      trend(ctx, 16, top, w - 32, ch, curve, TEAL, 2.5);
    }) as Draw,

    laptopReceipt: ((ctx, w, h) => {
      light(ctx, w, h);
      header(kit, ctx, w, 'October delivery · 8 files', 'CMO', false);
      const rows: [string, string][] = [['Values verified', '1,843 / 1,843'], ['Wrong values accepted', '0'], ['Unaccounted cells', '0'], ['CoA matched to lot', '8 / 8']];
      rows.forEach(([k, v], i) => {
        const y = 66 + i * 40;
        t(ctx, k, 22, y + 24, 15, '#334148');
        t(ctx, v, w - 22, y + 24, 15, '#0b1e22', 600, 'right');
        ctx.fillStyle = '#e1e6e9';
        ctx.fillRect(18, y + 36, w - 36, 1);
      });
    }) as Draw,

    review: ((ctx, w, h) => {
      ctx.fillStyle = '#f5f6f7';
      ctx.fillRect(0, 0, w, h);
      ctx.fillStyle = '#0b1e22';
      ctx.fillRect(0, 0, w, 70);
      t(ctx, 'Proposal · mass-balance feed control', 30, 46, 30, '#ffffff', 600);
      t(ctx, 'Not executed · signatures required', w - 30, 46, 20, '#9fb4ba', 500, 'right');
      t(ctx, 'Predicted yield effect  +5.1 pts  (3.2–6.8)', 30, 124, 26, '#0b1e22', 500);
      [0.78, 0.62, 0.7, 0.5].forEach((f, i) => { ctx.fillStyle = '#dde2e5'; ctx.fillRect(30, 150 + i * 24, (w * 0.55) * f, 10); });
      const box = (x: number, label: string, state: string, ok: boolean) => {
        ctx.strokeStyle = ok ? TEAL_DARK : AMBER;
        ctx.lineWidth = 3;
        if (!ok) ctx.setLineDash([12, 8]);
        ctx.strokeRect(x, h - 190, w * 0.4, 150);
        ctx.setLineDash([]);
        t(ctx, label, x + 22, h - 150, 24, ok ? TEAL_DARK : '#9a6510', 600);
        t(ctx, state, x + 22, h - 116, 20, '#5d6b72');
        if (ok) {
          ctx.strokeStyle = TEAL_DARK;
          ctx.lineWidth = 3;
          ctx.beginPath();
          ctx.moveTo(x + 26, h - 70);
          ctx.bezierCurveTo(x + 60, h - 110, x + 90, h - 40, x + 130, h - 80);
          ctx.bezierCurveTo(x + 160, h - 100, x + 180, h - 60, x + 220, h - 76);
          ctx.stroke();
        }
      };
      box(30, 'MSAT review', 'Signed · named reviewer', true);
      box(w * 0.5 + 10, 'QA review', 'Pending', false);
      t(ctx, 'Changes sent to MES or DCS: none', w - 30, 124, 18, '#5d6b72', 500, 'right');
    }) as Draw,

    hplc: ((ctx, w, h) => {
      light(ctx, w, h);
      header(kit, ctx, w, 'Chromatogram · S-26073-12', 'LIMS', false);
      grid(ctx, 20, 60, w - 40, h - 90, '#e0e5e8', 4, 8);
      const pts = Array.from({ length: 160 }, (_, i) => {
        const x = i / 159;
        const peak = (c: number, s: number, a: number) => a * Math.exp(-((x - c) ** 2) / (2 * s * s));
        return 0.05 + peak(0.22, 0.012, 0.25) + peak(0.46, 0.018, 0.82) + peak(0.51, 0.01, 0.18) + peak(0.74, 0.015, 0.3);
      });
      trend(ctx, 20, 70, w - 40, h - 110, pts, TEAL_DARK, 2);
    }) as Draw,

    bsc: ((ctx, w, h) => {
      dark(ctx, w, h);
      t(ctx, 'BSC-03', 14, 30, 20, '#e6eef0', 600);
      t(ctx, 'Inflow 0.45 m/s', 14, 62, 16, TEAL, 600);
      t(ctx, 'Airflow OK', w - 14, 30, 16, TEAL, 600, 'right');
    }) as Draw,

    pump: ((ctx, w, h) => {
      dark(ctx, w, h);
      t(ctx, 'PM-204', 12, 28, 20, '#e6eef0', 600);
      t(ctx, '1.48 bar', 12, 60, 20, '#ffb4ae', 600);
      t(ctx, '118 rpm', w - 12, 60, 16, TEAL, 500, 'right');
    }) as Draw,
  };
}

/** A wall sign: dark text on a white plate with a small teal rule. */
export function signDraw(kit: Kit, title: string, sub?: string): Draw {
  return (ctx, w, h) => {
    ctx.fillStyle = '#fbfbfb';
    ctx.fillRect(0, 0, w, h);
    ctx.fillStyle = TEAL_DARK;
    ctx.fillRect(h * 0.22, h * 0.24, h * 0.06, h * 0.52);
    kit.text(ctx, title, h * 0.45, sub ? h * 0.5 : h * 0.62, h * 0.3, '#1d2a2f', 600, 'left', h * 0.02);
    if (sub) kit.text(ctx, sub, h * 0.45, h * 0.8, h * 0.18, '#6b7a81', 500);
  };
}

export function labelDraw(kit: Kit, lines: string[], barcode = true): Draw {
  return (ctx, w, h) => {
    ctx.fillStyle = '#fafaf7';
    ctx.fillRect(0, 0, w, h);
    lines.forEach((l, i) => kit.text(ctx, l, w * 0.06, h * (0.24 + i * 0.17), h * (i ? 0.11 : 0.14), '#22282b', i ? 500 : 700));
    if (barcode) {
      let x = w * 0.06;
      let s = 3;
      while (x < w * 0.94) {
        s = (s * 7 + 3) % 11;
        const bw = 1 + (s % 3);
        ctx.fillStyle = '#111';
        ctx.fillRect(x, h * 0.74, bw, h * 0.18);
        x += bw + 1 + (s % 2) * 2;
      }
    }
  };
}
