import type { ReactNode } from 'react';

/* Isometric drawing primitives. World units: x runs to the lower right, y to the lower left, z up. */

export const C = 0.866;
export const project = (x: number, y: number, z = 0): [number, number] => [(x - y) * C, (x + y) * 0.5 - z];
export const pts = (list: [number, number, number][]) => list.map(([x, y, z]) => project(x, y, z).map(n => n.toFixed(1)).join(',')).join(' ');

/** The scene's own coordinate frame; the camera transform maps world points into it. */
export const VIEWBOX = { x: -620, y: -260, w: 1240, h: 920 };

/** SVG transform that centres a world point at a given zoom; `anchor` is the vertical position of the focus (0–1). */
export function cameraTransform(f: readonly [number, number, number], zoom: number, anchor = 0.44) {
  const [fx, fy] = project(f[0], f[1], f[2]);
  return `translate(0 ${(VIEWBOX.y + VIEWBOX.h * anchor).toFixed(1)}) scale(${zoom.toFixed(4)}) translate(${(-fx).toFixed(2)} ${(-fy).toFixed(2)})`;
}

export const TONES = {
  paper: ['#ffffff', '#e9e8e4', '#d7d5d0'],
  light: ['#e7e6e2', '#c9c7c1', '#adaba5'],
  mid: ['#a3a19c', '#82807b', '#696763'],
  dark: ['#5b5955', '#42413e', '#2f2e2c'],
  crate: ['#d9d3c7', '#bdb6a8', '#a39c8e'],
  teal: ['#5fb7c4', '#1b8aa3', '#0e6f86'],
} as const;
export type Tone = keyof typeof TONES;

export function Box({ x, y, z = 0, w, d, h, tone = 'light' }: { x: number; y: number; z?: number; w: number; d: number; h: number; tone?: Tone }) {
  const [top, left, right] = TONES[tone];
  const stroke = tone === 'dark' ? '#262523' : '#8f8d88';
  return (
    <g stroke={stroke} strokeWidth={0.6} strokeLinejoin="round">
      <polygon fill={left} points={pts([[x, y + d, z], [x + w, y + d, z], [x + w, y + d, z + h], [x, y + d, z + h]])} />
      <polygon fill={right} points={pts([[x + w, y, z], [x + w, y + d, z], [x + w, y + d, z + h], [x + w, y, z + h]])} />
      <polygon fill={top} points={pts([[x, y, z + h], [x + w, y, z + h], [x + w, y + d, z + h], [x, y + d, z + h]])} />
    </g>
  );
}

/** A quad lying on a face: 'top' (z fixed), 'left' (y fixed, faces lower left) or 'right' (x fixed, faces lower right). */
export function Quad({ face, at, a0, a1, b0, b1, fill, stroke, strokeWidth = 0.6, dash }: { face: 'top' | 'left' | 'right'; at: number; a0: number; a1: number; b0: number; b1: number; fill: string; stroke?: string; strokeWidth?: number; dash?: string }) {
  const p: [number, number, number][] = face === 'top'
    ? [[a0, b0, at], [a1, b0, at], [a1, b1, at], [a0, b1, at]]
    : face === 'left'
      ? [[a0, at, b0], [a1, at, b0], [a1, at, b1], [a0, at, b1]]
      : [[at, a0, b0], [at, a1, b0], [at, a1, b1], [at, a0, b1]];
  return <polygon points={pts(p)} fill={fill} stroke={stroke} strokeWidth={strokeWidth} strokeDasharray={dash} />;
}

/**
 * A 2D drawing surface mapped onto a face plane. Local x runs along the face (+x for 'left'/'top', −y for 'right'),
 * local y runs down the face (−z), or along +y for 'top'. Origin is the given world point.
 */
export function Face({ face, x, y, z, children }: { face: 'top' | 'left' | 'right'; x: number; y: number; z: number; children: ReactNode }) {
  const [sx, sy] = project(x, y, z);
  const m = face === 'top' ? `matrix(${C} 0.5 ${-C} 0.5 ${sx} ${sy})` : face === 'left' ? `matrix(${C} 0.5 0 1 ${sx} ${sy})` : `matrix(${C} -0.5 0 1 ${sx} ${sy})`;
  return <g transform={m}>{children}</g>;
}

export function Label({ x, y, size = 9, fill = '#2f2e2c', weight = 600, children }: { x: number; y: number; size?: number; fill?: string; weight?: number; children: ReactNode }) {
  return <text x={x} y={y} fontSize={size} fill={fill} fontWeight={weight} fontFamily="var(--font-inter), Inter, sans-serif" letterSpacing="0.04em">{children}</text>;
}

export function Legs({ x, y, w, d, h, s = 7 }: { x: number; y: number; w: number; d: number; h: number; s?: number }) {
  return (
    <>
      <Box x={x} y={y} w={s} d={s} h={h} tone="dark" />
      <Box x={x + w - s} y={y} w={s} d={s} h={h} tone="dark" />
      <Box x={x} y={y + d - s} w={s} d={s} h={h} tone="dark" />
      <Box x={x + w - s} y={y + d - s} w={s} d={s} h={h} tone="dark" />
    </>
  );
}

export function Sheet({ x, y, z, w = 58, d = 42, tag, tagFill = '#0e7490' }: { x: number; y: number; z: number; w?: number; d?: number; tag?: string; tagFill?: string }) {
  return (
    <g>
      <Box x={x} y={y} z={z} w={w} d={d} h={2} tone="paper" />
      {[0.32, 0.5, 0.68, 0.84].map(f => <Quad key={f} face="top" at={z + 2} a0={x + 6} a1={x + w - 8} b0={y + d * f} b1={y + d * f + 1.4} fill="#c9c7c1" />)}
      <Quad face="top" at={z + 2} a0={x + 6} a1={x + 26} b0={y + 5} b1={y + 11} fill={tagFill} />
      {tag && <Face face="top" x={x + 8} y={y + 10} z={z + 2.2}><Label x={0} y={0} size={5.5} fill="#ffffff">{tag}</Label></Face>}
    </g>
  );
}

/** Upright cylinder; `id` names its shading gradient. */
export function Cylinder({ cx, cy, z = 0, r, h, id, top = '#e9eaea', dark = false }: { cx: number; cy: number; z?: number; r: number; h: number; id: string; top?: string; dark?: boolean }) {
  const rx = r * 1.2247, ry = r * 0.7071;
  const [bx, by] = project(cx, cy, z);
  const [tx, ty] = project(cx, cy, z + h);
  const stops = dark ? ['#6b6966', '#4a4845', '#2f2e2c'] : ['#f2f2f0', '#c9cbcb', '#8e9192'];
  return (
    <g stroke={dark ? '#262523' : '#7f8283'} strokeWidth={0.7}>
      <defs>
        <linearGradient id={id} x1="0" x2="1" y1="0" y2="0">
          <stop offset="0" stopColor={stops[1]} />
          <stop offset="0.28" stopColor={stops[0]} />
          <stop offset="0.75" stopColor={stops[1]} />
          <stop offset="1" stopColor={stops[2]} />
        </linearGradient>
      </defs>
      <path fill={`url(#${id})`} d={`M${bx - rx},${by} A${rx},${ry} 0 0 0 ${bx + rx},${by} L${tx + rx},${ty} A${rx},${ry} 0 0 1 ${tx - rx},${ty} Z`} />
      <ellipse cx={tx} cy={ty} rx={rx} ry={ry} fill={top} />
    </g>
  );
}
