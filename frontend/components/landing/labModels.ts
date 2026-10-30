import * as THREE from 'three';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import { B, T, type Geo, type Kit, type Mats, shadowTextures } from './labKit';
import { labelDraw, screens, signDraw, type Draw } from './labScreens';

/* Procedural equipment for a biologics suite, in metres. Every builder works in local coordinates with +z as the
 * front of the unit and the floor at y = 0. */

export const ROOM = { x0: -11, x1: 11, z0: -8, z1: 6.5, h: 3.8 };

export type Ctx = {
  kit: Kit;
  m: Mats;
  g: Geo;
  sh: ReturnType<typeof shadowTextures>;
  scr: ReturnType<typeof screens>;
  anim: { couplings: THREE.Object3D[]; glow: THREE.MeshStandardMaterial[] };
  fade: THREE.Material[];
};

const V = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z);
const UP = V(0, 1, 0);
const _q = new THREE.Quaternion();

/** Matrix placing a +Y-aligned part at p, pointing along dir, scaled along its axis. */
function along(p: THREE.Vector3, dir: THREE.Vector3, len = 1) {
  _q.setFromUnitVectors(UP, dir.clone().normalize());
  return new THREE.Matrix4().compose(p, _q, V(1, len, 1));
}

function basis(p: THREE.Vector3, x: THREE.Vector3, y: THREE.Vector3) {
  const xx = x.clone().normalize();
  const zz = new THREE.Vector3().crossVectors(xx, y).normalize();
  const yy = new THREE.Vector3().crossVectors(zz, xx).normalize();
  return new THREE.Matrix4().makeBasis(xx, yy, zz).setPosition(p);
}

export function blob(c: Ctx, b: B, w: number, d: number, x = 0, z = 0, round = false) {
  b.add(c.g.plane(1, 1), round ? c.sh.disc : c.sh.rect, T(x, 0.004, z, 0, -Math.PI / 2, 0, w * 1.35, d * 1.35, 1), false, false);
}

export function screen(c: Ctx, b: B, w: number, h: number, draw: Draw, m: THREE.Matrix4, px = 512, intensity = 1.1, bezel = true) {
  const mat = c.kit.screen(px, Math.round((px * h) / w), draw, intensity);
  const mesh = new THREE.Mesh(c.g.plane(w, h), mat);
  b.at(m).object(mesh, T(0, 0, 0.0016));
  if (bezel) b.at(m).add(c.g.rbox(w + 0.024, h + 0.024, 0.026, 0.006, 2), c.m.plasticDark, T(0, 0, -0.012));
  return mat;
}

export function sign(c: Ctx, b: B, w: number, h: number, title: string, sub: string | undefined, m: THREE.Matrix4) {
  const cw = Math.min(2048, Math.round((256 * w) / h));
  const map = c.kit.canvas(cw, Math.round((cw * h) / w), signDraw(c.kit, title, sub));
  const face = new THREE.Mesh(c.g.plane(w, h), c.kit.std({ map, roughness: 0.4 }));
  b.at(m).object(face, T(0, 0, 0.0071));
  b.at(m).add(c.g.rbox(w + 0.02, h + 0.02, 0.014, 0.004, 2), c.m.plasticWhite);
}

function label(c: Ctx, b: B, w: number, h: number, lines: string[], m: THREE.Matrix4, barcode = true) {
  const map = c.kit.canvas(256, Math.round((256 * h) / w), labelDraw(c.kit, lines, barcode));
  b.at(m).object(new THREE.Mesh(c.g.plane(w, h), c.kit.std({ map, roughness: 0.6 })));
}

/* ---------- sanitary piping ---------- */

function clamp(c: Ctx, b: B, p: THREE.Vector3, dir: THREE.Vector3, r: number) {
  const m = along(p, dir);
  const s = b.at(m);
  s.add(c.g.cyl(r * 1.45, r * 1.45, 0.026, 20), c.m.steelPolished);
  s.add(c.g.torus(r * 1.5, r * 0.26, 8, 24), c.m.steelPolished, T(0, 0, 0, 0, Math.PI / 2));
  s.add(c.g.box(0.012, 0.02, r * 1.2), c.m.steelPolished, T(r * 1.85, 0, 0));
}

export function pipe(c: Ctx, b: B, pts: THREE.Vector3[], r: number, { clamps = 1.3, bend = 0.12, mat = c.m.steelPolished, cast = true }: { clamps?: number; bend?: number; mat?: THREE.Material; cast?: boolean } = {}) {
  let start = pts[0].clone();
  const tubes: THREE.BufferGeometry[] = [];
  for (let i = 1; i < pts.length; i++) {
    const p = pts[i];
    const dirIn = p.clone().sub(pts[i - 1]).normalize();
    let end = p.clone();
    let next: THREE.Vector3 | null = null;
    if (i < pts.length - 1) {
      const dirOut = pts[i + 1].clone().sub(p).normalize();
      const rb = Math.min(bend, p.distanceTo(pts[i - 1]) / 2, p.distanceTo(pts[i + 1]) / 2);
      end = p.clone().addScaledVector(dirIn, -rb);
      next = p.clone().addScaledVector(dirOut, rb);
      tubes.push(new THREE.TubeGeometry(new THREE.QuadraticBezierCurve3(end, p.clone(), next), 8, r, 14));
    }
    const len = start.distanceTo(end);
    if (len > 1e-3) {
      b.add(c.g.cyl(r, r, 1, 14, true), mat, along(start.clone().lerp(end, 0.5), dirIn, len), cast);
      if (clamps > 0) {
        const n = Math.floor(len / clamps);
        for (let k = 1; k <= n; k++) clamp(c, b, start.clone().lerp(end, k / (n + 1)), dirIn, r);
      }
    }
    if (next) start = next;
  }
  tubes.forEach(t => { b.add(t, mat, undefined, cast); t.dispose(); });
}

export function valve(c: Ctx, b: B, p: THREE.Vector3, dir: THREE.Vector3, up: THREE.Vector3, r: number) {
  const s = b.at(basis(p, dir, up));
  s.add(c.g.rbox(0.13, r * 3.2, r * 3, 0.012), c.m.steel);
  s.add(c.g.cyl(r * 1.6, r * 1.9, r * 2.6, 20), c.m.steel, T(0, r * 2.6, 0));
  s.add(c.g.cyl(r * 2.2, r * 2.2, r * 0.9, 24), c.m.steelPolished, T(0, r * 4.2, 0));
  s.add(c.g.torus(r * 2.2, r * 0.35, 8, 24), c.m.steelPolished, T(0, r * 4.2, 0, 0, Math.PI / 2));
  clamp(c, s, V(-0.075, 0, 0), V(1, 0, 0), r);
  clamp(c, s, V(0.075, 0, 0), V(1, 0, 0), r);
}

/* ---------- bioreactor ---------- */

export function bioreactor(c: Ctx, b: B, { R, H, leg, name, volume, front = 0 }: { R: number; H: number; leg: number; name: string; volume: string; front?: number }) {
  const { g, m } = c;
  const hd = R * 0.42;
  const y0 = leg + hd;
  const y1 = y0 + H;
  const key = `${R},${H},${leg}`;
  const pts: [number, number][] = [];
  for (let i = 0; i <= 12; i++) { const a = (i / 12) * (Math.PI / 2); pts.push([R * Math.sin(a), y0 - hd * Math.cos(a)]); }
  for (let i = 0; i <= 14; i++) { const a = (i / 14) * (Math.PI / 2); pts.push([R * Math.cos(a) + (i === 14 ? 0 : 0), y1 + hd * Math.sin(a)]); }
  b.add(g.lathe(`vessel${key}`, pts, 72), m.steel);
  const yTop = (rho: number) => y1 + hd * Math.sqrt(Math.max(0, 1 - (rho / R) ** 2));

  // cooling jacket
  const yb = y0 + 0.05, yt = y0 + H * 0.74, J = R + 0.045;
  b.add(g.lathe(`jacket${key}`, [[R - 0.002, yb - 0.05], [R + 0.025, yb - 0.01], [J, yb + 0.03], [J, yt - 0.03], [R + 0.025, yt + 0.01], [R - 0.002, yt + 0.05]], 72), m.steelMatte);
  for (const y of [y1, y0 + H * 0.86]) b.add(g.torus(R + 0.001, 0.0035, 6, 72), m.steelPolished, T(0, y, 0, 0, Math.PI / 2));
  for (const y of [yb + 0.35, yb + 0.7]) if (y < yt - 0.1) b.add(g.torus(J + 0.001, 0.003, 6, 72), m.steelPolished, T(0, y, 0, 0, Math.PI / 2));

  // legs with pads and levelling feet
  const legs = R > 0.5 ? 4 : 3;
  for (let i = 0; i < legs; i++) {
    const a = (i / legs) * Math.PI * 2 + Math.PI / legs + front;
    const rl = J + 0.055;
    const x = Math.sin(a) * rl, z = Math.cos(a) * rl;
    const top = y0 + 0.4;
    b.add(g.cyl(0.042, 0.042, top - 0.07, 20), m.steel, T(x, 0.07 + (top - 0.07) / 2, z));
    b.add(g.sphere(0.042, 16, 8), m.steel, T(x, top, z));
    b.add(g.rbox(0.13, 0.26, 0.03, 0.008), m.steelMatte, T(Math.sin(a) * (J + 0.016), top - 0.12, Math.cos(a) * (J + 0.016), a));
    b.add(g.cyl(0.022, 0.022, 0.06, 12), m.steelPolished, T(x, 0.045, z));
    b.add(g.cyl(0.075, 0.08, 0.022, 24), m.steelMatte, T(x, 0.011, z));
  }
  blob(c, b, R * 2.4, R * 2.4, 0, 0, true);

  // top-mounted agitator drive
  const yd = y1 + hd;
  b.add(g.cyl(0.21, 0.21, 0.05, 32), m.steelPolished, T(0, yd + 0.02, 0));
  for (let i = 0; i < 4; i++) { const a = (i / 4) * Math.PI * 2 + Math.PI / 4; b.add(g.cyl(0.016, 0.016, 0.2, 10), m.steelPolished, T(Math.sin(a) * 0.16, yd + 0.145, Math.cos(a) * 0.16)); }
  b.add(g.cyl(0.03, 0.03, 0.22, 16), m.steelPolished, T(0, yd + 0.15, 0));
  const coupling = new THREE.Mesh(c.g.custom('coupling', () => {
    const parts: THREE.BufferGeometry[] = [new THREE.CylinderGeometry(0.065, 0.065, 0.1, 28)];
    for (let i = 0; i < 6; i++) { const a = (i / 6) * Math.PI * 2; parts.push(new THREE.CylinderGeometry(0.009, 0.009, 0.112, 8).translate(Math.sin(a) * 0.05, 0, Math.cos(a) * 0.05)); }
    parts.push(new THREE.BoxGeometry(0.135, 0.018, 0.02));
    const merged = mergeGeometries(parts.map(p => p.toNonIndexed()))!;
    parts.forEach(p => p.dispose());
    return merged;
  }), m.steelPolished);
  b.object(coupling, T(0, yd + 0.15, 0));
  c.anim.couplings.push(coupling);
  b.add(g.cyl(0.2, 0.2, 0.03, 32), m.steelPolished, T(0, yd + 0.26, 0));
  b.add(g.rbox(0.36, 0.2, 0.3, 0.03), m.steelMatte, T(0, yd + 0.375, 0));
  const fins: [number, number][] = [[0, 0]];
  for (let i = 0; i <= 18; i++) { fins.push([i % 2 ? 0.145 : 0.13, (i / 18) * 0.38]); }
  fins.push([0, 0.38]);
  b.add(g.lathe('motor', fins, 40), m.steelMatte, T(0, yd + 0.475, 0));
  b.add(g.cyl(0.135, 0.13, 0.07, 32), m.steelPolished, T(0, yd + 0.89, 0));
  b.add(g.rbox(0.12, 0.12, 0.09, 0.012), m.steelMatte, T(0.18, yd + 0.62, 0));
  pipe(c, b, [V(0.18, yd + 0.66, 0.05), V(0.32, yd + 0.66, 0.05), V(0.32, ROOM.h, 0.05)], 0.012, { clamps: 0, mat: m.plasticDark });

  // head nozzles
  const nozzle = (a: number, rho: number, rn: number, kind: 'blind' | 'light' | 'vent' | 'open') => {
    const x = Math.sin(a + front) * rho, z = Math.cos(a + front) * rho;
    const base = yTop(rho) - 0.03;
    const top = base + 0.15;
    b.add(g.cyl(rn, rn, top - base, 20), m.steel, T(x, (base + top) / 2, z));
    b.add(g.cyl(rn * 1.45, rn * 1.45, 0.02, 24), m.steelPolished, T(x, top - 0.01, z));
    b.add(g.torus(rn * 1.5, rn * 0.25, 8, 24), m.steelPolished, T(x, top + 0.004, z, 0, Math.PI / 2));
    if (kind === 'blind') b.add(g.cyl(rn * 1.45, rn * 1.45, 0.014, 24), m.steelPolished, T(x, top + 0.012, z));
    if (kind === 'light') {
      b.add(g.cyl(rn * 1.5, rn * 1.5, 0.03, 24), m.steelPolished, T(x, top + 0.02, z));
      b.add(g.cyl(rn * 1.05, rn * 1.05, 0.01, 24), m.glass, T(x, top + 0.04, z));
    }
    if (kind === 'vent') {
      b.add(g.cyl(0.058, 0.058, 0.34, 24), m.steelPolished, T(x, top + 0.18, z));
      b.add(g.sphere(0.058, 24, 10), m.steelPolished, T(x, top + 0.35, z));
      b.add(g.torus(0.062, 0.012, 8, 24), m.steelPolished, T(x, top + 0.2, z, 0, Math.PI / 2));
    }
    return V(x, top, z);
  };
  nozzle(0.3, R * 0.62, 0.032, 'vent');
  nozzle(1.3, R * 0.6, 0.026, 'light');
  nozzle(2.1, R * 0.64, 0.024, 'blind');
  nozzle(-0.5, R * 0.5, 0.02, 'blind');
  nozzle(-1.3, R * 0.66, 0.022, 'blind');
  const feed = nozzle(-2.3, R * 0.6, 0.022, 'open');
  const exhaust = nozzle(3.0, R * 0.55, 0.03, 'open');

  // manway with swing bolts and a sight glass
  const ma = 0.95 + front - Math.PI / 2;
  const mx = Math.sin(ma) * R * 0.45, mz = Math.cos(ma) * R * 0.45, my = yTop(R * 0.45);
  const man = b.at(T(mx, my, mz));
  const mr = Math.min(0.2, R * 0.32);
  man.add(g.cyl(mr, mr, 0.14, 36), m.steel, T(0, 0.04, 0));
  man.add(g.cyl(mr + 0.035, mr + 0.035, 0.035, 40), m.steelPolished, T(0, 0.13, 0));
  man.add(g.cyl(mr * 0.42, mr * 0.42, 0.02, 24), m.steelPolished, T(0, 0.155, 0));
  man.add(g.cyl(mr * 0.34, mr * 0.34, 0.006, 24), m.glass, T(0, 0.167, 0));
  for (let i = 0; i < 6; i++) {
    const a = (i / 6) * Math.PI * 2;
    man.add(g.cyl(0.011, 0.011, 0.09, 8), m.steelPolished, T(Math.sin(a) * (mr + 0.05), 0.12, Math.cos(a) * (mr + 0.05)));
    man.add(g.torus(0.024, 0.006, 6, 16), m.steelPolished, T(Math.sin(a) * (mr + 0.05), 0.17, Math.cos(a) * (mr + 0.05), 0, Math.PI / 2));
  }

  // side sight glass above the jacket
  const sg = b.at(T(0, (yt + y1) / 2 + 0.02, 0, front + 0.35));
  sg.add(g.cyl(0.085, 0.085, 0.04, 32), m.steelPolished, T(0, 0, R + 0.012, 0, Math.PI / 2));
  sg.add(g.cyl(0.06, 0.06, 0.008, 32), m.glass, T(0, 0, R + 0.034, 0, Math.PI / 2));
  sg.add(g.cyl(0.04, 0.04, 0.004, 24), m.darkGlass, T(0, 0, R + 0.02, 0, Math.PI / 2));
  for (let i = 0; i < 6; i++) { const a = (i / 6) * Math.PI * 2; sg.add(g.cyl(0.008, 0.008, 0.012, 6), m.steelPolished, T(Math.cos(a) * 0.072, Math.sin(a) * 0.072, R + 0.036, 0, Math.PI / 2)); }

  // probe ports angled 15° down: pH, DO, temperature
  [-0.35, -0.12, 0.11].forEach((a, i) => {
    const s = b.at(T(0, yb + 0.22 + i * 0.03, 0, front + a));
    const dir = V(0, Math.sin(0.26), Math.cos(0.26));
    s.add(g.cyl(0.026, 0.026, 0.08, 16), m.steelPolished, along(V(0, 0, J + 0.03), dir));
    s.add(g.cyl(0.012, 0.012, 0.2, 12), m.steelPolished, along(V(0, 0.03, J + 0.1), dir));
    s.add(g.cyl(0.019, 0.019, 0.07, 16), i === 1 ? m.plasticWhite : m.plasticDark, along(V(0, 0.06, J + 0.2), dir));
    const cable = new THREE.TubeGeometry(new THREE.CatmullRomCurve3([V(0, 0.08, J + 0.24), V(0, 0.06, J + 0.33), V(0, -0.3, J + 0.36), V(0, -0.7 + i * 0.03, J + 0.18)]), 16, 0.004, 6);
    s.add(cable, m.rubber);
    cable.dispose();
  });

  // bottom outlet valve
  const yBot = y0 - hd;
  b.add(g.cyl(0.03, 0.03, 0.12, 16), m.steel, T(0, yBot - 0.06, 0));
  valve(c, b, V(0, yBot - 0.16, 0), V(1, 0, 0).applyAxisAngle(UP, front), UP, 0.022);

  // nameplate
  const plate = b.at(T(0, y0 + H * 0.45, 0, front - 0.25));
  label(c, plate, 0.3, 0.13, [name, volume, 'Jacketed · 3 bar · 145 °C'], T(0, 0, J + 0.003), false);

  return { y0, y1, yTop: yd, feed, exhaust, outlet: V(0, yBot - 0.16, 0) };
}

/* ---------- control skid with HMI ---------- */

export function controlSkid(c: Ctx, b: B) {
  const { g, m } = c;
  b.add(g.box(1.3, 0.06, 0.06), m.steelMatte, T(0, 0.08, 0.32));
  b.add(g.box(1.3, 0.06, 0.06), m.steelMatte, T(0, 0.08, -0.32));
  for (const x of [-0.62, 0.62]) for (const z of [-0.32, 0.32]) {
    b.add(g.cyl(0.03, 0.03, 0.06, 12), m.steelPolished, T(x, 0.03, z));
  }
  b.add(g.box(0.06, 1.9, 0.06), m.steelMatte, T(-0.45, 1.05, -0.3));
  b.add(g.box(0.06, 1.9, 0.06), m.steelMatte, T(0.45, 1.05, -0.3));
  // stainless control enclosure
  b.add(g.rbox(0.8, 0.95, 0.32, 0.02), m.steelMatte, T(0, 1.42, -0.12));
  b.add(g.box(0.004, 0.9, 0.004), m.rackDark, T(0.0, 1.42, 0.042));
  b.add(g.rbox(0.02, 0.16, 0.03, 0.006), m.steelPolished, T(0.33, 1.42, 0.06));
  b.add(g.cyl(0.03, 0.03, 0.03, 20), m.rackDark, T(-0.25, 1.06, 0.05, 0, Math.PI / 2));
  // stack light, green lit
  b.add(g.cyl(0.02, 0.02, 0.16, 12), m.steelPolished, T(0.3, 1.97, -0.12));
  b.add(g.cyl(0.032, 0.032, 0.06, 20), m.plasticWhite, T(0.3, 2.08, -0.12));
  b.add(g.cyl(0.032, 0.032, 0.06, 20), m.ledGreen, T(0.3, 2.14, -0.12));
  b.add(g.cyl(0.032, 0.032, 0.06, 20), m.plasticGrey, T(0.3, 2.2, -0.12));
  // HMI on a swivel arm
  b.add(g.cyl(0.025, 0.025, 0.3, 12), m.steelPolished, T(-0.1, 1.05, 0.15, 0, 0, Math.PI / 2));
  const hmi = screen(c, b, 0.46, 0.3, c.scr.hmiBioreactor, T(-0.32, 1.12, 0.22, 0.25, -0.18), 512, 1.15);
  c.anim.glow.push(hmi);
  // transfer manifold
  pipe(c, b, [V(-0.55, 0.45, 0.05), V(0.55, 0.45, 0.05)], 0.019, { clamps: 0.5 });
  pipe(c, b, [V(-0.55, 0.7, 0.05), V(0.55, 0.7, 0.05)], 0.019, { clamps: 0.5 });
  valve(c, b, V(-0.2, 0.45, 0.05), V(1, 0, 0), V(0, 0, 1), 0.019);
  valve(c, b, V(0.2, 0.7, 0.05), V(1, 0, 0), V(0, 0, 1), 0.019);
  blob(c, b, 1.4, 0.8);
}

/* ---------- peristaltic feed pump on a cart, with a media bag ---------- */

export function pumpCart(c: Ctx, b: B, to: THREE.Vector3) {
  const { g, m } = c;
  for (const x of [-0.3, 0.3]) for (const z of [-0.22, 0.22]) {
    b.add(g.box(0.03, 0.82, 0.03), m.steelMatte, T(x, 0.5, z));
    b.add(g.cyl(0.035, 0.035, 0.03, 16), m.rubber, T(x, 0.045, z, 0, 0, Math.PI / 2));
    b.add(g.box(0.03, 0.06, 0.05), m.steelMatte, T(x, 0.08, z));
  }
  b.add(g.rbox(0.68, 0.025, 0.5, 0.008), m.steel, T(0, 0.9, 0));
  b.add(g.rbox(0.68, 0.025, 0.5, 0.008), m.steel, T(0, 0.3, 0));
  // pump drive
  b.add(g.rbox(0.36, 0.26, 0.3, 0.03), m.plasticWhite, T(-0.08, 1.045, 0));
  b.add(g.cyl(0.085, 0.085, 0.06, 32), m.plasticGrey, T(-0.12, 1.06, 0.18, 0, Math.PI / 2));
  b.add(g.cyl(0.08, 0.08, 0.01, 32), m.glass, T(-0.12, 1.06, 0.215, 0, Math.PI / 2));
  b.add(g.rbox(0.06, 0.03, 0.03, 0.008), m.teal, T(-0.12, 1.15, 0.2));
  screen(c, b, 0.1, 0.06, c.scr.pump, T(0.04, 1.08, 0.152, 0, -0.1), 256, 1.1);
  label(c, b, 0.12, 0.05, ['PM-204', 'Feed pump'], T(0.04, 0.99, 0.152), false);
  // media bag in a bin on the lower shelf
  b.add(g.rbox(0.42, 0.3, 0.36, 0.02), m.steelMatte, T(0.08, 0.465, 0));
  b.add(g.custom('bag', () => new THREE.SphereGeometry(0.2, 24, 12).scale(1, 0.38, 0.85)), m.bag, T(0.08, 0.64, 0));
  label(c, b, 0.1, 0.06, ['FM-2207', 'Feed media 50 L'], T(0.08, 0.66, 0.172, 0, -0.35), false);
  const tube = new THREE.TubeGeometry(new THREE.CatmullRomCurve3([V(0.08, 0.7, 0.05), V(0.2, 0.95, 0.15), V(-0.02, 1.06, 0.22), V(-0.22, 1.06, 0.22), V(-0.4, 1.2, 0.1), to]), 64, 0.0065, 8);
  b.add(tube, m.plasticWhite);
  tube.dispose();
  blob(c, b, 0.7, 0.55);
}

/* ---------- freeze dryer ---------- */

export function freezeDryer(c: Ctx, b: B) {
  const { g, m } = c;
  // cabinet through the wall: front face at z = 0
  const W = 2.5, Hc = 2.6, D = 0.9;
  b.add(g.rbox(W, Hc, D, 0.03), m.steelMatte, T(0, Hc / 2, -D / 2));
  // front panels with seams
  ([[-0.35, 1.7, 1.35, 2.45], [0.85, 0.7, 1.9, 1.3], [0.85, 0.7, 0.66, 1.12]] as const).forEach(([x, w, y, h]) => {
    b.add(g.rbox(w - 0.012, h - 0.012, 0.02, 0.006), m.steel, T(x, y, 0.01));
  });
  b.add(g.box(W - 0.04, 0.08, 0.06), m.steelMatte, T(0, 0.04, 0.02));
  // round chamber door
  const door = b.at(T(-0.35, 1.32, 0.02));
  door.add(g.torus(0.66, 0.035, 12, 64), m.steelPolished, T(0, 0, 0.02));
  door.add(g.torus(0.62, 0.016, 8, 64), m.rubber, T(0, 0, 0.04));
  door.add(g.lathe('lyoDoor', [[0, 0.11], [0.2, 0.105], [0.4, 0.09], [0.55, 0.065], [0.63, 0.035], [0.64, 0]], 64), m.steel, T(0, 0, 0.03, 0, Math.PI / 2));
  door.add(g.cyl(0.19, 0.19, 0.03, 40), m.steelPolished, T(0, 0, 0.14, 0, Math.PI / 2));
  door.add(g.cyl(0.155, 0.155, 0.006, 40), m.glass, T(0, 0, 0.158, 0, Math.PI / 2));
  door.add(g.cyl(0.15, 0.15, 0.004, 32), m.darkGlass, T(0, 0, 0.1, 0, Math.PI / 2));
  for (let i = 0; i < 3; i++) door.add(g.box(0.26, 0.006, 0.01), m.steelMatte, T(0, -0.07 + i * 0.07, 0.106));
  // locking wheel
  door.add(g.torus(0.27, 0.016, 10, 48), m.steelPolished, T(0, 0, 0.2));
  door.add(g.cyl(0.04, 0.04, 0.08, 20), m.steelPolished, T(0, 0, 0.17, 0, Math.PI / 2));
  for (let i = 0; i < 4; i++) door.add(g.cyl(0.01, 0.01, 0.27, 8), m.steelPolished, T(0, 0, 0.2, 0, 0, (i / 4) * Math.PI * 2 + Math.PI / 4).multiply(T(0, 0.135, 0)));
  // hinge
  for (const y of [-0.38, 0.38]) {
    b.add(g.rbox(0.18, 0.12, 0.08, 0.01), m.steelPolished, T(0.38, 1.32 + y, 0.06));
    b.add(g.cyl(0.03, 0.03, 0.16, 16), m.steelPolished, T(0.45, 1.32 + y, 0.1));
  }
  // control panel
  screen(c, b, 0.5, 0.38, c.scr.lyo, T(0.85, 1.52, 0.022), 512, 1.1);
  b.add(g.cyl(0.03, 0.03, 0.03, 20), m.rackDark, T(0.85, 1.12, 0.03, 0, Math.PI / 2));
  label(c, b, 0.34, 0.13, ['LYO-02', 'Production freeze dryer', '12 m² shelf area'], T(0.85, 1.94, 0.022), false);
  b.add(g.cyl(0.02, 0.02, 0.12, 12), m.steelPolished, T(1.05, Hc + 0.06, -0.2));
  b.add(g.cyl(0.03, 0.03, 0.055, 20), m.ledGreen, T(1.05, Hc + 0.15, -0.2));
  b.add(g.cyl(0.03, 0.03, 0.055, 20), m.plasticWhite, T(1.05, Hc + 0.205, -0.2));
  blob(c, b, W, 0.5, 0, 0.1);

  // external condenser vessel on saddles, connected by a vapour duct with an isolation valve
  const cx = W / 2 + 1.1;
  const cy = 1.45;
  const cond = b.at(T(cx, cy, -0.45, 0, 0, Math.PI / 2));
  const Rc = 0.48, Lc = 1.3;
  const prof: [number, number][] = [];
  for (let i = 0; i <= 10; i++) { const a = (i / 10) * (Math.PI / 2); prof.push([Rc * Math.sin(a), -Lc / 2 - 0.2 * Math.cos(a)]); }
  for (let i = 0; i <= 10; i++) { const a = (i / 10) * (Math.PI / 2); prof.push([Rc * Math.cos(a), Lc / 2 + 0.2 * Math.sin(a)]); }
  cond.add(g.lathe('condenser', prof, 56), m.steel);
  for (const y of [-Lc / 2, Lc / 2]) cond.add(g.torus(Rc + 0.002, 0.006, 6, 56), m.steelPolished, T(0, y, 0, 0, Math.PI / 2));
  for (const x of [cx - 0.45, cx + 0.45]) {
    b.add(g.box(0.1, cy - 0.4, 0.7), m.steelMatte, T(x, (cy - 0.4) / 2, -0.45));
    b.add(g.box(0.16, 0.03, 0.8), m.steelMatte, T(x, 0.015, -0.45));
  }
  pipe(c, b, [V(W / 2 - 0.05, cy, -0.45), V(cx - Lc / 2 - 0.1, cy, -0.45)], 0.17, { clamps: 0, mat: m.steel });
  b.add(g.cyl(0.23, 0.23, 0.08, 32), m.steelPolished, T(W / 2 + 0.17, cy, -0.45, 0, 0, Math.PI / 2));
  b.add(g.rbox(0.2, 0.22, 0.18, 0.02), m.plasticGrey, T(W / 2 + 0.17, cy + 0.36, -0.45));
  b.add(g.cyl(0.03, 0.03, 0.12, 12), m.steelPolished, T(W / 2 + 0.17, cy + 0.22, -0.45));
  for (let i = 0; i < 6; i++) { const a = (i / 6) * Math.PI * 2; cond.add(g.cyl(0.03, 0.03, 0.1, 12), m.steelPolished, T(Math.cos(a) * 0.26, Lc / 2 + 0.24, Math.sin(a) * 0.26)); }
  label(c, b, 0.26, 0.1, ['LYO-02 CONDENSER', '−75 °C · 300 kg ice'], T(cx, cy, -0.45 + Rc + 0.002), false);
  // vacuum pump skid
  b.add(g.rbox(0.7, 0.42, 0.45, 0.03), m.paintGrey, T(cx + 0.1, 0.24, 0.35));
  b.add(g.cyl(0.11, 0.11, 0.36, 24), m.paintGrey, T(cx + 0.1, 0.56, 0.35, 0, 0, Math.PI / 2));
  pipe(c, b, [V(cx + 0.28, 0.56, 0.35), V(cx + 0.5, 0.56, 0.35), V(cx + 0.5, cy - 0.3, 0.1)], 0.03, { clamps: 0, mat: m.steel });
  blob(c, b, 2.0, 1.1, cx, -0.3);

  // vial loading trolley in front of the door
  const cart = b.at(T(-0.35, 0, 1.15));
  for (const x of [-0.42, 0.42]) for (const z of [-0.3, 0.3]) {
    cart.add(g.box(0.03, 0.82, 0.03), m.steelMatte, T(x, 0.49, z));
    cart.add(g.cyl(0.04, 0.04, 0.035, 16), m.rubber, T(x, 0.05, z, 0, 0, Math.PI / 2));
  }
  cart.add(g.rbox(0.92, 0.03, 0.66, 0.008), m.steel, T(0, 0.9, 0));
  cart.add(g.rbox(0.92, 0.03, 0.66, 0.008), m.steel, T(0, 0.25, 0));
  cart.add(g.box(0.78, 0.015, 0.52), m.steelPolished, T(0, 0.922, 0));
  const nx = 18, nz = 12, sp = 0.04;
  const vials = new THREE.InstancedMesh(g.custom('vial', () => new THREE.LatheGeometry([V(0, 0, 0), V(0.0145, 0, 0), V(0.0155, 0.004, 0), V(0.0155, 0.036, 0), V(0.0095, 0.043, 0), V(0.0095, 0.05, 0), V(0.0, 0.05, 0)].map(p => new THREE.Vector2(p.x, p.y)), 14)), m.vialGlass, nx * nz);
  const stoppers = new THREE.InstancedMesh(g.cyl(0.011, 0.0105, 0.012, 12), m.paintGrey, nx * nz);
  const cake = new THREE.InstancedMesh(g.cyl(0.0138, 0.0138, 0.012, 12), m.plasticWhite, nx * nz);
  let k = 0;
  for (let i = 0; i < nx; i++) for (let j = 0; j < nz; j++) {
    const lx = (i - (nx - 1) / 2) * sp, lz = (j - (nz - 1) / 2) * sp;
    vials.setMatrixAt(k, cart.base.clone().multiply(T(lx, 0.93, lz)));
    stoppers.setMatrixAt(k, cart.base.clone().multiply(T(lx, 0.985, lz)));
    cake.setMatrixAt(k, cart.base.clone().multiply(T(lx, 0.94, lz)));
    k++;
  }
  for (const im of [vials, stoppers, cake]) { im.castShadow = im !== vials; im.receiveShadow = true; b.root.add(im); }
  blob(c, cart, 0.95, 0.7);
}

/* ---------- QC bench with a class II biosafety cabinet ---------- */

export function qcLab(c: Ctx, b: B) {
  const { g, m } = c;
  // BSC on its stand, front at z = 0.4
  const bsc = b.at(T(-1.6, 0, 0));
  for (const x of [-0.85, 0.85]) for (const z of [-0.32, 0.32]) bsc.add(g.box(0.045, 0.72, 0.045), m.paintGrey, T(x, 0.36, z));
  bsc.add(g.box(1.75, 0.04, 0.04), m.paintGrey, T(0, 0.18, 0.32));
  const y0 = 0.72;
  bsc.add(g.rbox(1.8, 0.24, 0.8, 0.02), m.paintWhite, T(0, y0 + 0.12, 0));
  for (const x of [-0.88, 0.88]) bsc.add(g.rbox(0.06, 1.25, 0.8, 0.015), m.paintWhite, T(x, y0 + 0.86, 0));
  bsc.add(g.box(1.72, 1.2, 0.04), m.steelMatte, T(0, y0 + 0.84, -0.36));
  bsc.add(g.box(1.72, 0.02, 0.66), m.steel, T(0, y0 + 0.25, -0.02));
  bsc.add(g.rbox(1.8, 0.5, 0.8, 0.02), m.paintWhite, T(0, y0 + 1.72, 0));
  bsc.add(g.rbox(1.6, 0.18, 0.62, 0.02), m.paintWhite, T(0, y0 + 2.06, -0.05));
  bsc.add(g.box(1.6, 0.012, 0.6), m.paintGrey, T(0, y0 + 1.47, -0.05));
  // sloped glass sash over the work opening
  bsc.add(g.box(1.7, 0.56, 0.01), m.glass, T(0, y0 + 1.18, 0.36, 0, -0.17));
  bsc.add(g.box(1.72, 0.03, 0.03), m.aluminium, T(0, y0 + 0.92, 0.4));
  bsc.add(g.box(1.72, 0.012, 0.02), m.paintWhite, T(0, y0 + 0.26, 0.4));
  screen(c, bsc, 0.32, 0.12, c.scr.bsc, T(0.55, y0 + 1.72, 0.402), 256, 1.1);
  sign(c, bsc, 0.5, 0.11, 'BSC-03', 'Class II · A2', T(-0.45, y0 + 1.75, 0.402));
  // items inside
  bsc.add(g.rbox(0.18, 0.05, 0.1, 0.008), m.plasticWhite, T(-0.3, y0 + 0.285, -0.05));
  for (let i = 0; i < 6; i++) bsc.add(g.cyl(0.009, 0.007, 0.09, 10), m.plasticWhite, T(-0.37 + i * 0.028, y0 + 0.34, -0.05));
  bsc.add(g.cyl(0.04, 0.035, 0.11, 20), m.vialGlass, T(0.25, y0 + 0.315, -0.12));
  bsc.add(g.cyl(0.012, 0.008, 0.22, 12), m.plasticWhite, T(0.05, y0 + 0.32, 0.0, 0.4, 0, 1.2));
  blob(c, bsc, 1.85, 0.85);

  // lab bench
  const bench = b.at(T(1.4, 0, 0));
  const L = 2.9;
  for (const x of [-L / 2 + 0.05, 0, L / 2 - 0.05]) {
    bench.add(g.box(0.05, 0.86, 0.05), m.paintGrey, T(x, 0.43, -0.3));
    bench.add(g.box(0.05, 0.05, 0.62), m.paintGrey, T(x, 0.06, 0));
  }
  bench.add(g.rbox(L, 0.035, 0.78, 0.008), m.worktop, T(0, 0.9, 0));
  bench.add(g.rbox(0.9, 0.7, 0.62, 0.012), m.paintWhite, T(-0.9, 0.42, -0.04));
  for (let i = 0; i < 3; i++) {
    bench.add(g.box(0.88, 0.004, 0.004), m.paintGrey, T(-0.9, 0.3 + i * 0.2, 0.272));
    bench.add(g.rbox(0.18, 0.02, 0.02, 0.006), m.steelPolished, T(-0.9, 0.38 + i * 0.2, 0.29));
  }
  // shelf uprights and reagent shelf
  for (const x of [-L / 2 + 0.1, L / 2 - 0.1]) bench.add(g.box(0.035, 1.0, 0.035), m.aluminium, T(x, 1.42, -0.33));
  bench.add(g.rbox(L - 0.1, 0.025, 0.3, 0.006), m.worktop, T(0, 1.62, -0.24));
  for (let i = 0; i < 9; i++) bench.add(g.cyl(0.04, 0.04, 0.16 + (i % 3) * 0.04, 20), i % 4 === 0 ? m.plasticWhite : m.vialGlass, T(-1.2 + i * 0.28, 1.72 + (i % 3) * 0.02, -0.24));
  // HPLC stack with solvent bottles and its workstation monitor
  [0, 1, 2].forEach(i => {
    bench.add(g.rbox(0.38, 0.17, 0.5, 0.012), m.plasticWhite, T(-0.85, 1.005 + i * 0.175, -0.08));
    bench.add(g.box(0.3, 0.004, 0.002), m.plasticGrey, T(-0.85, 0.98 + i * 0.175, 0.171));
    bench.add(g.box(0.03, 0.012, 0.002), i === 1 ? m.ledGreen : m.ledTeal, T(-0.98, 1.05 + i * 0.175, 0.171));
  });
  for (let i = 0; i < 4; i++) {
    bench.add(g.cyl(0.035, 0.035, 0.12, 20), m.vialGlass, T(-0.98 + i * 0.09, 1.58, -0.12));
    bench.add(g.cyl(0.02, 0.02, 0.03, 12), i === 2 ? m.teal : m.plasticGrey, T(-0.98 + i * 0.09, 1.655, -0.12));
  }
  bench.add(g.rbox(0.42, 0.012, 0.3, 0.004), m.plasticGrey, T(-0.85, 1.535, -0.12));
  screen(c, bench, 0.54, 0.32, c.scr.hplc, T(-0.25, 1.24, -0.12, -0.1), 512, 1.05);
  bench.add(g.box(0.04, 0.24, 0.04), m.plasticDark, T(-0.25, 1.02, -0.17));
  bench.add(g.rbox(0.2, 0.012, 0.14, 0.004), m.plasticDark, T(-0.25, 0.925, -0.17));
  bench.add(g.rbox(0.42, 0.018, 0.14, 0.005), m.plasticDark, T(-0.25, 0.927, 0.15));
  // centrifuge
  bench.add(g.rbox(0.46, 0.32, 0.5, 0.05), m.plasticWhite, T(0.45, 1.08, -0.06));
  bench.add(g.rbox(0.38, 0.03, 0.4, 0.03), m.plasticGrey, T(0.45, 1.24, -0.08));
  bench.add(g.box(0.14, 0.05, 0.002), m.darkGlass, T(0.45, 1.06, 0.191));
  // sample racks
  for (let r = 0; r < 2; r++) {
    bench.add(g.rbox(0.24, 0.05, 0.1, 0.005), m.plasticWhite, T(0.95, 0.94, -0.05 + r * 0.14));
    for (let i = 0; i < 6; i++) {
      bench.add(g.cyl(0.008, 0.008, 0.09, 10), m.vialGlass, T(0.85 + i * 0.04, 0.99, -0.05 + r * 0.14));
      bench.add(g.cyl(0.0095, 0.0095, 0.018, 10), r === 1 && i === 3 ? m.ledAmber : m.teal, T(0.85 + i * 0.04, 1.04, -0.05 + r * 0.14));
    }
  }
  blob(c, bench, L, 0.8);
}

/* ---------- control room: systems of record ---------- */

export function controlRoom(c: Ctx, b: B) {
  const { g, m } = c;
  // server racks along the left wall, fronts facing +x
  ['MES', 'LIMS', 'PI HISTORIAN'].forEach((name, i) => {
    const r = b.at(T(-1.6, 0, -1.5 + i * 0.64, Math.PI / 2));
    r.add(g.rbox(0.6, 2.0, 1.0, 0.012), m.rackDark, T(0, 1.02, 0));
    r.add(g.box(0.52, 1.62, 0.01), m.rackDoor, T(0, 0.98, 0.502));
    r.add(g.rbox(0.025, 0.3, 0.03, 0.006), m.steelPolished, T(0.22, 1.05, 0.52));
    r.add(g.box(0.5, 0.14, 0.01), m.darkGlass, T(0, 1.9, 0.502));
    for (let k = 0; k < 6; k++) r.add(g.box(0.012, 0.008, 0.004), k % 3 === 2 ? m.ledAmber : m.ledGreen, T(-0.2 + k * 0.03, 1.9, 0.51));
    label(c, r, 0.2, 0.06, [name, 'read-only'], T(0.12, 1.9, 0.508), false);
    r.add(g.box(0.6, 0.03, 1.0), m.rubber, T(0, 0.015, 0));
  });
  blob(c, b, 1.2, 2.0, -1.6, -0.86);

  // operator desk with three screens facing +z
  const desk = b.at(T(0.5, 0, -1.1));
  desk.add(g.rbox(2.4, 0.035, 0.8, 0.01), m.worktop, T(0, 0.74, 0));
  for (const x of [-1.1, 1.1]) {
    desk.add(g.box(0.06, 0.72, 0.06), m.aluminium, T(x, 0.36, 0));
    desk.add(g.box(0.08, 0.03, 0.7), m.aluminium, T(x, 0.015, 0));
  }
  desk.add(g.box(2.1, 0.05, 0.03), m.aluminium, T(0, 0.68, -0.3));
  const monitor = (x: number, ry: number, draw: Draw) => {
    desk.add(g.box(0.05, 0.36, 0.03), m.plasticDark, T(x, 0.92, -0.18, ry));
    desk.add(g.rbox(0.24, 0.015, 0.18, 0.004), m.plasticDark, T(x, 0.765, -0.18, ry));
    screen(c, desk, 0.62, 0.36, draw, T(x, 1.08, -0.15, ry).multiply(T(0, 0, 0.02)), 640, 1.05);
  };
  monitor(-0.68, 0.32, c.scr.mes);
  monitor(0, 0, c.scr.historian);
  monitor(0.68, -0.32, c.scr.lims);
  desk.add(g.rbox(0.44, 0.018, 0.14, 0.005), m.plasticDark, T(-0.1, 0.767, 0.16));
  desk.add(g.rbox(0.06, 0.02, 0.1, 0.01), m.plasticDark, T(0.25, 0.767, 0.17));
  blob(c, desk, 2.4, 0.8);
  chair(c, b.at(T(0.2, 0, -0.3, 0.2)));
  chair(c, b.at(T(1.1, 0, -0.2, -0.3)));

  // wall display on the back wall
  screen(c, b, 1.7, 0.96, c.scr.plantOverview, T(0.5, 1.95, -1.98), 1024, 1.0);
}

export function chair(c: Ctx, b: B) {
  const { g, m } = c;
  for (let i = 0; i < 5; i++) {
    const a = (i / 5) * Math.PI * 2;
    b.add(g.box(0.035, 0.03, 0.3), m.plasticDark, T(Math.sin(a) * 0.14, 0.07, Math.cos(a) * 0.14, a));
    b.add(g.sphere(0.025, 10, 6), m.rubber, T(Math.sin(a) * 0.28, 0.025, Math.cos(a) * 0.28));
  }
  b.add(g.cyl(0.025, 0.025, 0.36, 12), m.steelPolished, T(0, 0.27, 0));
  b.add(g.rbox(0.48, 0.07, 0.46, 0.03), m.fabric, T(0, 0.48, 0));
  b.add(g.rbox(0.44, 0.5, 0.06, 0.03), m.fabric, T(0, 0.8, -0.24, 0, -0.1));
  b.add(g.box(0.04, 0.24, 0.04), m.plasticDark, T(0, 0.58, -0.24));
  blob(c, b, 0.55, 0.55, 0, 0, true);
}

/* ---------- goods receipt ---------- */

function pallet(c: Ctx, b: B) {
  const { g, m } = c;
  for (const z of [-0.35, 0, 0.35]) b.add(g.box(1.2, 0.022, 0.1), m.wood, T(0, 0.011, z));
  for (const x of [-0.53, 0, 0.53]) for (const z of [-0.35, 0, 0.35]) b.add(g.box(0.14, 0.078, 0.1), m.wood, T(x, 0.061, z));
  for (const x of [-0.53, 0, 0.53]) b.add(g.box(0.14, 0.022, 0.8), m.wood, T(x, 0.111, 0));
  for (let i = 0; i < 5; i++) b.add(g.box(1.2, 0.022, 0.12), m.wood, T(0, 0.133, -0.34 + i * 0.17));
}

export function goodsReceipt(c: Ctx, b: B) {
  const { g, m } = c;
  // pallet 1: wrapped cartons from the CMO
  const p1 = b.at(T(0, 0, 0, 0.04));
  pallet(c, p1);
  for (let lx = 0; lx < 2; lx++) for (let lz = 0; lz < 2; lz++) for (let ly = 0; ly < 3; ly++) {
    if (ly === 2 && lx === 1 && lz === 0) continue;
    p1.add(g.rbox(0.58, 0.4, 0.39, 0.012), m.cardboard, T(-0.3 + lx * 0.6, 0.345 + ly * 0.405, -0.2 + lz * 0.4));
  }
  p1.add(g.rbox(1.22, 1.0, 0.82, 0.03), m.film, T(0, 0.66, 0), false, false);
  label(c, p1, 0.2, 0.14, ['CMO DELIVERY', 'CMP-26-10 · 8 files', 'CoA enclosed'], T(-0.3, 0.75, 0.401));
  label(c, p1, 0.2, 0.14, ['CMO DELIVERY', 'Lot DS-2610-03', 'Quarantine'], T(0.6 + 0.001, 0.45, 0.1, Math.PI / 2));
  blob(c, p1, 1.2, 0.8);

  // pallet 2: sealed totes
  const p2 = b.at(T(1.65, 0, -0.15, -0.05));
  pallet(c, p2);
  for (let lx = 0; lx < 2; lx++) for (let ly = 0; ly < 3; ly++) {
    if (ly === 2 && lx === 1) continue;
    const s = p2.at(T(-0.3 + lx * 0.6, 0.144 + ly * 0.37, 0));
    s.add(g.rbox(0.58, 0.32, 0.78, 0.02), m.tote, T(0, 0.16, 0));
    s.add(g.rbox(0.6, 0.04, 0.8, 0.012), m.plasticGrey, T(0, 0.34, 0));
    s.add(g.torus(0.012, 0.003, 6, 12), m.teal, T(0, 0.3, 0.402));
    label(c, s, 0.14, 0.08, ['TOTE ' + (ly * 2 + lx + 11), 'sealed · 2–8 °C'], T(-0.12, 0.17, 0.392), true);
  }
  blob(c, p2, 1.2, 0.8);

  // insulated shippers and a loose tote
  const s3 = b.at(T(0.75, 0, 1.2, 0.3));
  s3.add(g.rbox(0.5, 0.46, 0.5, 0.03), m.paintWhite, T(0, 0.23, 0));
  s3.add(g.rbox(0.52, 0.06, 0.52, 0.02), m.paintWhite, T(0, 0.49, 0));
  label(c, s3, 0.18, 0.12, ['COLD CHAIN', '2–8 °C · logger 4471'], T(0, 0.27, 0.252));
  blob(c, s3, 0.5, 0.5);
  const s4 = b.at(T(1.35, 0, 1.25, -0.2));
  s4.add(g.rbox(0.58, 0.32, 0.4, 0.02), m.tote, T(0, 0.16, 0));
  s4.add(g.rbox(0.6, 0.04, 0.42, 0.012), m.plasticGrey, T(0, 0.34, 0));
  blob(c, s4, 0.6, 0.42);

  // pallet jack
  const pj = b.at(T(-1.35, 0, 0.5, 0.5));
  for (const x of [-0.2, 0.2]) pj.add(g.rbox(0.16, 0.06, 1.15, 0.01), m.paintGrey, T(x, 0.05, 0));
  pj.add(g.rbox(0.56, 0.2, 0.14, 0.02), m.paintGrey, T(0, 0.12, 0.62));
  pj.add(g.cyl(0.05, 0.05, 0.3, 16), m.rackDark, T(0, 0.35, 0.64));
  pj.add(g.cyl(0.08, 0.08, 0.06, 20), m.rubber, T(0, 0.08, 0.68, 0, 0, Math.PI / 2));
  pipe(c, pj, [V(0, 0.45, 0.66), V(0, 1.05, 0.9), V(0.12, 1.12, 0.94)], 0.016, { clamps: 0, mat: m.paintGrey });
  pj.add(g.torus(0.1, 0.016, 8, 24), m.rubber, T(0, 1.15, 0.93, 0, -0.4));
  blob(c, pj, 0.6, 1.4);

  // receiving desk with a laptop
  const d = b.at(T(3.1, 0, 1.2, -0.5));
  d.add(g.rbox(1.0, 0.03, 0.6, 0.008), m.worktop, T(0, 0.98, 0));
  d.add(g.box(0.06, 0.96, 0.06), m.aluminium, T(0, 0.49, -0.15));
  d.add(g.box(0.7, 0.03, 0.08), m.aluminium, T(0, 0.015, -0.15));
  d.add(g.rbox(0.34, 0.014, 0.24, 0.004), m.aluminium, T(-0.1, 1.003, 0.05));
  screen(c, d, 0.32, 0.2, c.scr.laptopReceipt, T(-0.1, 1.11, -0.07, 0, -0.25), 512, 1.0, false);
  d.add(g.box(0.34, 0.22, 0.008), m.aluminium, T(-0.1, 1.11, -0.075, 0, -0.25));
  d.add(g.rbox(0.06, 0.03, 0.16, 0.01), m.plasticDark, T(0.3, 1.01, 0.08, 0.4));
  blob(c, d, 1.0, 0.6);
}

/* ---------- glass review office ---------- */

export function reviewOffice(c: Ctx, b: B, x0: number, z0: number, x1: number, z1: number) {
  const { g, m } = c;
  const H = ROOM.h;
  glassWall(c, b, V(x0, 0, z1), V(x0, 0, z0), H);
  glassWall(c, b, V(x0, 0, z0), V(x1, 0, z0), H, 1);
  // solid front wall, single-sided so the overview looks straight through it
  const fw = x1 - x0;
  b.add(g.custom(`officeFront${fw}`, () => {
    const p = new THREE.PlaneGeometry(fw, H);
    const uv = p.attributes.uv as THREE.BufferAttribute;
    for (let i = 0; i < uv.count; i++) uv.setX(i, uv.getX(i) * (fw / 1.2));
    return p;
  }), m.wall, T((x0 + x1) / 2, H / 2, z1, Math.PI), false, true);
  const side = b.at(T((x0 + x1) / 2 + 0.6, 0, z1 - 0.25, Math.PI));
  side.add(g.rbox(1.8, 0.75, 0.45, 0.015), m.paintWhite, T(0, 0.375, 0));
  for (let i = 0; i < 3; i++) side.add(g.box(0.002, 0.7, 0.002), m.paintGrey, T(-0.6 + i * 0.6, 0.375, 0.226));
  side.add(g.rbox(0.24, 0.3, 0.2, 0.01), m.plasticGrey, T(-0.5, 0.9, 0));
  side.add(g.rbox(0.32, 0.04, 0.24, 0.005), m.plasticWhite, T(0.4, 0.77, 0));
  const cx = (x0 + x1) / 2 + 0.2, cz = (z0 + z1) / 2;
  const t = b.at(T(cx, 0, cz, Math.PI / 2));
  t.add(g.rbox(2.2, 0.035, 1.0, 0.012), m.worktop, T(0, 0.74, 0));
  for (const x of [-0.8, 0.8]) {
    t.add(g.box(0.05, 0.72, 0.6), m.aluminium, T(x, 0.36, 0));
  }
  blob(c, t, 2.2, 1.0);
  for (const [x, z, a] of [[-0.6, 0.75, Math.PI], [0.4, 0.75, Math.PI], [-0.6, -0.75, 0], [0.4, -0.75, 0]] as const) chair(c, t.at(T(x, 0, z, a)));
  t.add(g.rbox(0.3, 0.004, 0.21, 0.002), m.plasticWhite, T(-0.3, 0.76, 0.2, 0.2));
  t.add(g.rbox(0.3, 0.004, 0.21, 0.002), m.plasticWhite, T(0.5, 0.76, -0.15, -0.1));
  // large wall display on the right wall
  const disp = b.at(T(x1 - 0.04, 0, cz, -Math.PI / 2));
  screen(c, disp, 2.1, 1.18, c.scr.review, T(0, 1.55, 0), 1280, 1.0);
  disp.add(g.rbox(1.6, 0.06, 0.1, 0.01), m.plasticDark, T(0, 0.82, 0.05));
  sign(c, b, 1.0, 0.18, 'QA REVIEW', 'Proposals and sign-off', T(x0 - 0.05, 2.6, z0 + 1.6, -Math.PI / 2));
}

/** A full-height glazed partition with aluminium mullions and a frosted manifestation band. */
export function glassWall(c: Ctx, b: B, a: THREE.Vector3, z: THREE.Vector3, H: number, door = -1) {
  const { g, m } = c;
  const dir = z.clone().sub(a);
  const L = dir.length();
  dir.normalize();
  const ry = Math.atan2(dir.x, dir.z) - Math.PI / 2;
  const s = b.at(T(a.x, 0, a.z, ry));
  const n = Math.max(1, Math.round(L / 1.2));
  const pw = L / n;
  s.add(g.box(L, 0.06, 0.08), m.aluminium, T(L / 2, 0.03, 0));
  s.add(g.box(L, 0.08, 0.08), m.aluminium, T(L / 2, H - 0.04, 0));
  s.add(g.box(L, 0.05, 0.06), m.aluminium, T(L / 2, 2.25, 0));
  for (let i = 0; i <= n; i++) s.add(g.box(0.05, H, 0.08), m.aluminium, T(i * pw, H / 2, 0));
  const band = c.kit.std({ color: '#f4f6f7', roughness: 0.9, transparent: true, opacity: 0.55 });
  for (let i = 0; i < n; i++) {
    const cx = (i + 0.5) * pw;
    s.add(g.box(pw - 0.05, 2.2, 0.01), m.glass, T(cx, 1.12, 0), false, false);
    s.add(g.box(pw - 0.05, H - 2.33, 0.01), m.glass, T(cx, (2.28 + H - 0.08) / 2, 0), false, false);
    s.add(g.box(pw - 0.05, 0.1, 0.012), band, T(cx, 1.3, 0), false, false);
    if (i === door) {
      s.add(g.cyl(0.014, 0.014, 1.1, 12), m.steelPolished, T(cx + pw * 0.36, 1.05, 0.06));
      s.add(g.cyl(0.014, 0.014, 1.1, 12), m.steelPolished, T(cx + pw * 0.36, 1.05, -0.06));
    }
  }
}

/* ---------- the room shell ---------- */

export function room(c: Ctx, b: B) {
  const { g, m } = c;
  const { x0, x1, z0, z1, h } = ROOM;
  const W = x1 - x0, D = z1 - z0;
  const cxr = (x0 + x1) / 2, czr = (z0 + z1) / 2;
  // floor slab
  const floorGeo = g.custom('floor', () => new THREE.PlaneGeometry(W, D));
  b.add(floorGeo, m.floor, T(cxr, 0, czr, 0, -Math.PI / 2), false, true);
  b.add(g.box(W + 0.3, 0.35, D + 0.15), m.slabEdge, T(cxr, -0.176, czr - 0.075), false, false);

  // walls: interior panel faces plus a thick body with a cap
  const wallFace = (len: number) => g.custom(`wall${len}`, () => {
    const p = new THREE.PlaneGeometry(len, h);
    const uv = p.attributes.uv as THREE.BufferAttribute;
    for (let i = 0; i < uv.count; i++) uv.setX(i, uv.getX(i) * (len / 1.2));
    return p;
  });
  b.add(wallFace(W), m.wall, T(cxr, h / 2, z0), false, true);
  b.add(wallFace(D), m.wall, T(x0, h / 2, czr, Math.PI / 2), false, true);
  b.add(wallFace(D), m.wall, T(x1, h / 2, czr, -Math.PI / 2), false, true);
  b.add(g.box(W + 0.3, h, 0.15), m.wallTop, T(cxr, h / 2, z0 - 0.076), true, false);
  b.add(g.box(0.15, h, D), m.wallTop, T(x0 - 0.076, h / 2, czr), true, false);
  b.add(g.box(0.15, h, D), m.wallTop, T(x1 + 0.076, h / 2, czr), true, false);

  // ceiling with light panels and HEPA diffusers (faces down, fades when the camera rises through it)
  const ceilGeo = g.custom('ceil', () => {
    const p = new THREE.PlaneGeometry(W, D);
    const uv = p.attributes.uv as THREE.BufferAttribute;
    for (let i = 0; i < uv.count; i++) uv.setXY(i, uv.getX(i) * (W / 0.6), uv.getY(i) * (D / 0.6));
    return p;
  });
  b.add(ceilGeo, m.ceiling, T(cxr, h, czr, 0, Math.PI / 2), false, false);
  for (let x = -9; x <= 9.01; x += 3) for (let z = -6.6; z <= 5.4; z += 2.4) {
    b.add(g.plane(1.16, 0.56), m.lightPanel, T(x, h - 0.026, z, 0, Math.PI / 2), false, false);
    b.add(g.box(1.24, 0.04, 0.64), m.lightFrame, T(x, h - 0.004, z), false, false);
    b.add(g.plane(0.58, 0.58), m.hepa, T(x + 1.5, h - 0.004, z + 1.2, 0, Math.PI / 2), false, false);
  }
  c.fade.push(m.ceiling, m.lightPanel, m.lightFrame, m.hepa);
}

/* ---------- roller dock door ---------- */

export function dockDoor(c: Ctx, b: B) {
  const { g, m } = c;
  const slats = c.kit.canvas(64, 512, (ctx, w, h) => {
    ctx.fillStyle = '#d9dcdf';
    ctx.fillRect(0, 0, w, h);
    for (let y = 0; y < h; y += 16) {
      const gr = ctx.createLinearGradient(0, y, 0, y + 16);
      gr.addColorStop(0, '#eceef0');
      gr.addColorStop(0.7, '#d2d6d9');
      gr.addColorStop(1, '#9ea4a9');
      ctx.fillStyle = gr;
      ctx.fillRect(0, y, w, 16);
    }
  });
  slats.wrapS = THREE.RepeatWrapping;
  slats.repeat.set(4, 1);
  const door = c.kit.std({ map: slats, roughness: 0.45, metalness: 0.5 });
  b.add(g.box(3.0, 3.0, 0.04), door, T(0, 1.5, 0.03));
  b.add(g.box(0.14, 3.15, 0.12), m.paintGrey, T(-1.57, 1.575, 0.06));
  b.add(g.box(0.14, 3.15, 0.12), m.paintGrey, T(1.57, 1.575, 0.06));
  b.add(g.box(3.28, 0.4, 0.3), m.paintGrey, T(0, 3.25, 0.15));
  b.add(g.box(2.9, 0.06, 0.06), m.rubber, T(0, 0.03, 0.06));
  for (const x of [-1.0, 1.0]) b.add(g.rbox(0.25, 0.3, 0.12, 0.02), m.rubber, T(x, 0.55, 0.12));
  b.add(g.rbox(0.12, 0.2, 0.06, 0.01), m.paintGrey, T(1.85, 1.3, 0.03));
  b.add(g.cyl(0.02, 0.02, 0.02, 12), m.ledGreen, T(1.85, 1.35, 0.065, 0, Math.PI / 2));
}

/** Floor tape marking a rectangle. */
export function floorTape(c: Ctx, b: B, x0: number, z0: number, x1: number, z1: number, mat: THREE.Material) {
  const w = 0.05;
  b.add(c.g.box(x1 - x0, 0.002, w), mat, T((x0 + x1) / 2, 0.001, z0), false, true);
  b.add(c.g.box(x1 - x0, 0.002, w), mat, T((x0 + x1) / 2, 0.001, z1), false, true);
  b.add(c.g.box(w, 0.002, z1 - z0), mat, T(x0, 0.001, (z0 + z1) / 2), false, true);
  b.add(c.g.box(w, 0.002, z1 - z0), mat, T(x1, 0.001, (z0 + z1) / 2), false, true);
}

export function floorText(c: Ctx, b: B, text: string, w: number, h: number, m: THREE.Matrix4) {
  const map = c.kit.canvas(1024, Math.round((1024 * h) / w), (ctx, cw, ch) => {
    ctx.clearRect(0, 0, cw, ch);
    c.kit.text(ctx, text, cw / 2, ch * 0.78, ch * 0.8, 'rgba(70,78,84,0.32)', 700, 'center', ch * 0.08);
  });
  const mat = c.kit.std({ map, transparent: true, roughness: 0.5, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -1 });
  b.add(c.g.plane(w, h), mat, m.clone().multiply(T(0, 0.002, 0, 0, -Math.PI / 2)), false, true);
}

/** Wall-mounted sanitary pipe rack running along the back wall. */
export function pipeRack(c: Ctx, b: B, xa: number, xb: number, z: number) {
  const { g, m } = c;
  for (let x = xa; x <= xb + 0.01; x += 1.5) {
    b.add(g.box(0.04, 0.04, 0.42), m.steelMatte, T(x, 2.75, z + 0.21));
    b.add(g.box(0.04, 0.3, 0.04), m.steelMatte, T(x, 2.75, z + 0.02));
  }
  [0.12, 0.24, 0.36].forEach((dz, i) => pipe(c, b, [V(xa - 0.3, 2.8, z + dz), V(xb + 0.3, 2.8, z + dz)], 0.022 + (i === 2 ? 0.01 : 0), { clamps: 1.5, cast: false }));
}

/* ---------- buffer preparation: mobile vessels and a single-use mixer ---------- */

export function mobileTank(c: Ctx, b: B, R = 0.36, H = 0.62) {
  const { g, m } = c;
  const y0 = 0.42;
  const prof: [number, number][] = [];
  for (let i = 0; i <= 8; i++) { const a = (i / 8) * (Math.PI / 2); prof.push([R * Math.sin(a), y0 - R * 0.3 * Math.cos(a)]); }
  prof.push([R, y0 + H], [R + 0.02, y0 + H + 0.01], [R + 0.02, y0 + H + 0.03], [0, y0 + H + 0.05]);
  b.add(g.lathe(`mtank${R},${H}`, prof, 48), m.steel);
  b.add(g.cyl(0.07, 0.07, 0.06, 20), m.steelPolished, T(0, y0 + H + 0.08, 0));
  b.add(g.torus(R + 0.022, 0.008, 6, 48), m.steelPolished, T(0, y0 + H + 0.02, 0, 0, Math.PI / 2));
  for (let i = 0; i < 4; i++) {
    const a = (i / 4) * Math.PI * 2 + Math.PI / 4;
    const x = Math.sin(a) * (R - 0.04), z = Math.cos(a) * (R - 0.04);
    b.add(g.cyl(0.02, 0.02, y0 - 0.08, 12), m.steel, T(x, (y0 - 0.08) / 2 + 0.08, z));
    b.add(g.box(0.05, 0.03, 0.06), m.steelMatte, T(x, 0.075, z));
    b.add(g.cyl(0.035, 0.035, 0.03, 16), m.rubber, T(x, 0.04, z, a, 0, Math.PI / 2));
  }
  pipe(c, b, [V(-R * 0.7, y0 + H - 0.05, R * 0.75), V(-R * 0.7, y0 + H + 0.3, R * 0.75), V(R * 0.7, y0 + H + 0.3, R * 0.75), V(R * 0.7, y0 + H - 0.05, R * 0.75)], 0.012, { clamps: 0, bend: 0.06 });
  b.add(g.cyl(0.02, 0.02, 0.1, 12), m.steel, T(0, y0 - R * 0.3 - 0.05, 0));
  valve(c, b, V(0.06, y0 - R * 0.3 - 0.12, 0), V(1, 0, 0), V(0, 0, 1), 0.016);
  blob(c, b, R * 2.2, R * 2.2, 0, 0, true);
}

export function singleUseMixer(c: Ctx, b: B) {
  const { g, m } = c;
  for (const x of [-0.42, 0.42]) for (const z of [-0.42, 0.42]) {
    b.add(g.box(0.04, 0.4, 0.04), m.steelMatte, T(x, 0.24, z));
    b.add(g.cyl(0.035, 0.035, 0.03, 16), m.rubber, T(x, 0.04, z, 0, 0, Math.PI / 2));
  }
  b.add(g.rbox(0.9, 0.06, 0.9, 0.01), m.steelMatte, T(0, 0.45, 0));
  b.add(g.custom('sum', () => new THREE.LatheGeometry([[0, 0], [0.38, 0], [0.42, 0.04], [0.42, 1.0], [0.4, 1.04], [0, 1.05]].map(([r, y]) => new THREE.Vector2(r, y)), 48)), m.steelMatte, T(0, 0.48, 0));
  b.add(g.cyl(0.39, 0.39, 0.01, 40), m.bag, T(0, 1.535, 0));
  b.add(g.rbox(0.24, 0.24, 0.24, 0.02), m.plasticWhite, T(0, 0.33, 0));
  b.add(g.box(0.06, 1.3, 0.06), m.steelMatte, T(0.55, 0.95, 0));
  b.add(g.rbox(0.28, 0.2, 0.08, 0.01), m.plasticWhite, T(0.55, 1.55, 0.05));
  screen(c, b, 0.16, 0.1, c.scr.pump, T(0.55, 1.56, 0.091), 256, 1.0, false);
  const tube = new THREE.TubeGeometry(new THREE.CatmullRomCurve3([V(-0.2, 1.54, 0.1), V(-0.5, 1.7, 0.2), V(-0.7, 1.0, 0.4), V(-0.8, 0.05, 0.6)]), 32, 0.008, 8);
  b.add(tube, m.plasticWhite);
  tube.dispose();
  label(c, b, 0.2, 0.08, ['SUM-03', 'Buffer 500 L'], T(0, 1.0, 0.425), false);
  blob(c, b, 1.0, 1.0);
}
