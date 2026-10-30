import * as THREE from 'three';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';

/* Shared building blocks for the landing-page lab render: canvas textures, PBR materials and a batcher that
 * merges static parts per material so the whole plant draws in a few dozen calls. Units are metres, +y up. */

export type Disposable = { dispose(): void };

export class Kit {
  readonly disposables: Disposable[] = [];
  readonly font: string;
  readonly anisotropy: number;

  constructor(renderer: THREE.WebGLRenderer) {
    this.anisotropy = Math.min(8, renderer.capabilities.getMaxAnisotropy());
    const family = typeof document !== 'undefined' ? getComputedStyle(document.body).fontFamily : '';
    this.font = family || 'Inter, system-ui, sans-serif';
  }

  track<T extends Disposable>(item: T): T {
    this.disposables.push(item);
    return item;
  }

  canvas(width: number, height: number, draw: (ctx: CanvasRenderingContext2D, w: number, h: number) => void, { color = true, repeat }: { color?: boolean; repeat?: [number, number] } = {}) {
    const el = document.createElement('canvas');
    el.width = width;
    el.height = height;
    const ctx = el.getContext('2d')!;
    draw(ctx, width, height);
    const tex = new THREE.CanvasTexture(el);
    if (color) tex.colorSpace = THREE.SRGBColorSpace;
    tex.anisotropy = this.anisotropy;
    if (repeat) {
      tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
      tex.repeat.set(repeat[0], repeat[1]);
    }
    return this.track(tex);
  }

  text(ctx: CanvasRenderingContext2D, text: string, x: number, y: number, size: number, color: string, weight = 500, align: CanvasTextAlign = 'left', spacing = 0) {
    ctx.font = `${weight} ${size}px ${this.font}`;
    ctx.fillStyle = color;
    ctx.textAlign = align;
    ctx.textBaseline = 'alphabetic';
    if ('letterSpacing' in ctx) (ctx as unknown as { letterSpacing: string }).letterSpacing = `${spacing}px`;
    ctx.fillText(text, x, y);
  }

  std(params: THREE.MeshStandardMaterialParameters) {
    return this.track(new THREE.MeshStandardMaterial(params));
  }

  phys(params: THREE.MeshPhysicalMaterialParameters) {
    return this.track(new THREE.MeshPhysicalMaterial(params));
  }

  /** A self-lit display: dark glass with the canvas as emission, so screens glow but still reflect the room. */
  screen(width: number, height: number, draw: (ctx: CanvasRenderingContext2D, w: number, h: number) => void, intensity = 1.15) {
    const map = this.canvas(width, height, draw);
    return this.std({ color: '#050708', roughness: 0.18, metalness: 0, emissive: '#ffffff', emissiveMap: map, emissiveIntensity: intensity });
  }
}

export const noise = (seed: number) => {
  let s = seed >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 4294967296;
  };
};

export function makeMaterials(kit: Kit) {
  const rnd = noise(7);
  const brushed = kit.canvas(512, 512, (ctx, w, h) => {
    ctx.fillStyle = 'rgb(200,200,200)';
    ctx.fillRect(0, 0, w, h);
    for (let i = 0; i < 3200; i++) {
      const v = 175 + rnd() * 55;
      ctx.strokeStyle = `rgba(${v},${v},${v},${0.12 + rnd() * 0.18})`;
      ctx.lineWidth = rnd() * 1.1 + 0.3;
      const y = rnd() * h;
      const x = rnd() * w;
      ctx.beginPath();
      ctx.moveTo(x - 260, y);
      ctx.lineTo(x + 260, y + (rnd() - 0.5) * 1.5);
      ctx.stroke();
    }
  }, { color: false, repeat: [1, 4] });

  const mottled = kit.canvas(512, 512, (ctx, w, h) => {
    ctx.fillStyle = 'rgb(150,150,150)';
    ctx.fillRect(0, 0, w, h);
    for (let i = 0; i < 900; i++) {
      const v = 130 + rnd() * 50;
      const r = 6 + rnd() * 40;
      const x = rnd() * w, y = rnd() * h;
      const g = ctx.createRadialGradient(x, y, 0, x, y, r);
      g.addColorStop(0, `rgba(${v},${v},${v},0.25)`);
      g.addColorStop(1, `rgba(${v},${v},${v},0)`);
      ctx.fillStyle = g;
      ctx.fillRect(x - r, y - r, r * 2, r * 2);
    }
  }, { color: false, repeat: [6, 4] });

  const floorMap = kit.canvas(1024, 1024, (ctx, w, h) => {
    ctx.fillStyle = '#cfd3d6';
    ctx.fillRect(0, 0, w, h);
    for (let i = 0; i < 26000; i++) {
      const v = 180 + rnd() * 50;
      ctx.fillStyle = `rgba(${v},${v + 2},${v + 4},${0.12 + rnd() * 0.18})`;
      ctx.fillRect(rnd() * w, rnd() * h, 1 + rnd() * 1.6, 1 + rnd() * 1.6);
    }
    for (let i = 0; i < 260; i++) {
      const x = rnd() * w, y = rnd() * h, r = 30 + rnd() * 120;
      const g = ctx.createRadialGradient(x, y, 0, x, y, r);
      const d = rnd() > 0.5 ? 255 : 120;
      g.addColorStop(0, `rgba(${d},${d},${d},0.035)`);
      g.addColorStop(1, `rgba(${d},${d},${d},0)`);
      ctx.fillStyle = g;
      ctx.fillRect(x - r, y - r, r * 2, r * 2);
    }
  }, { repeat: [5, 3.3] });

  // Wall panels 1.2 m wide, 3.4 m tall, with a horizontal break at 2.4 m.
  const wallMap = kit.canvas(256, 512, (ctx, w, h) => {
    ctx.fillStyle = '#f1f2f3';
    ctx.fillRect(0, 0, w, h);
    const g = ctx.createLinearGradient(0, 0, w, 0);
    g.addColorStop(0, 'rgba(0,0,0,0.035)');
    g.addColorStop(0.5, 'rgba(255,255,255,0.02)');
    g.addColorStop(1, 'rgba(0,0,0,0.035)');
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, w, h);
    ctx.fillStyle = '#c9cdd1';
    ctx.fillRect(0, 0, 2, h);
    ctx.fillRect(w - 1, 0, 1, h);
    ctx.fillRect(0, Math.round(h * (1 - 2.4 / 3.4)), w, 2);
  }, { repeat: [1, 1] });

  const ceilingMap = kit.canvas(256, 256, (ctx, w, h) => {
    ctx.fillStyle = '#f3f4f5';
    ctx.fillRect(0, 0, w, h);
    ctx.fillStyle = '#d5d9dc';
    ctx.fillRect(0, 0, w, 3);
    ctx.fillRect(0, 0, 3, h);
  }, { repeat: [1, 1] });

  const hepaMap = kit.canvas(256, 256, (ctx, w, h) => {
    ctx.fillStyle = '#e9ebec';
    ctx.fillRect(0, 0, w, h);
    ctx.fillStyle = '#c3c8cc';
    for (let y = 22; y < h - 18; y += 7) for (let x = 22 + ((y / 7) % 2) * 3.5; x < w - 18; x += 7) {
      ctx.beginPath();
      ctx.arc(x, y, 1.8, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.strokeStyle = '#bfc4c8';
    ctx.lineWidth = 6;
    ctx.strokeRect(5, 5, w - 10, h - 10);
  });

  const perforated = kit.canvas(128, 256, (ctx, w, h) => {
    ctx.fillStyle = '#30353a';
    ctx.fillRect(0, 0, w, h);
    ctx.fillStyle = '#0d0f11';
    for (let y = 8; y < h - 6; y += 6) for (let x = 8 + ((y / 6) % 2) * 3; x < w - 6; x += 6) ctx.fillRect(x, y, 3, 3);
  });

  const wood = kit.canvas(256, 64, (ctx, w, h) => {
    ctx.fillStyle = '#c9ad84';
    ctx.fillRect(0, 0, w, h);
    for (let i = 0; i < 70; i++) {
      ctx.strokeStyle = `rgba(${120 + rnd() * 40},${90 + rnd() * 30},${55 + rnd() * 20},${0.15 + rnd() * 0.25})`;
      ctx.lineWidth = 0.6 + rnd() * 1.5;
      const y = rnd() * h;
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.bezierCurveTo(w * 0.3, y + (rnd() - 0.5) * 6, w * 0.7, y + (rnd() - 0.5) * 6, w, y + (rnd() - 0.5) * 4);
      ctx.stroke();
    }
  });

  const cardboard = kit.canvas(256, 256, (ctx, w, h) => {
    ctx.fillStyle = '#b89870';
    ctx.fillRect(0, 0, w, h);
    for (let i = 0; i < 4000; i++) {
      const v = rnd();
      ctx.fillStyle = v > 0.5 ? 'rgba(220,195,160,0.12)' : 'rgba(120,90,60,0.1)';
      ctx.fillRect(rnd() * w, rnd() * h, 2, 1);
    }
    ctx.fillStyle = 'rgba(200,175,140,0.85)';
    ctx.fillRect(w * 0.44, 0, w * 0.12, h);
  });

  const steel = kit.phys({ color: '#dfe2e5', metalness: 1, roughness: 0.26, roughnessMap: brushed });
  const steelPolished = kit.phys({ color: '#e6e8ea', metalness: 1, roughness: 0.12 });
  const steelMatte = kit.phys({ color: '#d2d6d9', metalness: 1, roughness: 0.4, roughnessMap: brushed });
  return {
    brushed,
    steel,
    steelPolished,
    steelMatte,
    aluminium: kit.std({ color: '#bfc4c9', metalness: 1, roughness: 0.38, roughnessMap: mottled }),
    floor: kit.phys({ map: floorMap, roughness: 0.32, roughnessMap: mottled, metalness: 0, clearcoat: 0.55, clearcoatRoughness: 0.18 }),
    slabEdge: kit.std({ color: '#9aa0a5', roughness: 0.9 }),
    wall: kit.std({ map: wallMap, roughness: 0.55, metalness: 0 }),
    wallTop: kit.std({ color: '#d9dcdf', roughness: 0.8 }),
    ceiling: kit.std({ map: ceilingMap, roughness: 0.7, transparent: true }),
    hepa: kit.std({ map: hepaMap, roughness: 0.6, transparent: true }),
    lightPanel: kit.track(new THREE.MeshBasicMaterial({ color: new THREE.Color(1.9, 1.9, 1.95), transparent: true })),
    lightFrame: kit.std({ color: '#e6e8ea', roughness: 0.4, metalness: 0.2, transparent: true }),
    paintWhite: kit.phys({ color: '#eceef0', roughness: 0.38, clearcoat: 0.25, clearcoatRoughness: 0.35 }),
    paintGrey: kit.std({ color: '#8d959b', roughness: 0.5 }),
    rackDark: kit.std({ color: '#262a2e', roughness: 0.55, metalness: 0.35 }),
    rackDoor: kit.std({ map: perforated, roughness: 0.5, metalness: 0.4 }),
    rubber: kit.std({ color: '#1b1d1f', roughness: 0.85 }),
    plasticWhite: kit.std({ color: '#e7e9ea', roughness: 0.45 }),
    plasticGrey: kit.std({ color: '#a2a9ae', roughness: 0.55 }),
    plasticDark: kit.std({ color: '#2a2e31', roughness: 0.45 }),
    tote: kit.std({ color: '#7f898f', roughness: 0.62 }),
    teal: kit.std({ color: '#0e7490', roughness: 0.45 }),
    worktop: kit.std({ color: '#d8dbdd', roughness: 0.35 }),
    worktopDark: kit.std({ color: '#3a3f43', roughness: 0.4 }),
    wood: kit.std({ map: wood, roughness: 0.85 }),
    cardboard: kit.std({ map: cardboard, roughness: 0.92 }),
    film: kit.phys({ color: '#ffffff', roughness: 0.12, transparent: true, opacity: 0.16, depthWrite: false, side: THREE.DoubleSide }),
    glass: kit.phys({ color: '#f4f9f9', metalness: 0, roughness: 0.03, transmission: 1, thickness: 0.012, ior: 1.5, specularIntensity: 1 }),
    vialGlass: kit.phys({ color: '#f3f8f9', metalness: 0, roughness: 0.06, transparent: true, opacity: 0.32, specularIntensity: 1, depthWrite: false }),
    darkGlass: kit.std({ color: '#0b0d0f', roughness: 0.08, metalness: 0.1 }),
    fabric: kit.std({ color: '#3b4146', roughness: 0.95 }),
    tape: kit.std({ color: '#7b848a', roughness: 0.6 }),
    tapeTeal: kit.std({ color: '#2a7f93', roughness: 0.6 }),
    bag: kit.phys({ color: '#f1efe4', roughness: 0.25, transmission: 0.0, transparent: true, opacity: 0.82, clearcoat: 0.6 }),
    liquid: kit.std({ color: '#e6d39a', roughness: 0.3 }),
    ledGreen: kit.track(new THREE.MeshBasicMaterial({ color: new THREE.Color(0.25, 1.6, 0.7) })),
    ledAmber: kit.track(new THREE.MeshBasicMaterial({ color: new THREE.Color(1.8, 1.0, 0.2) })),
    ledTeal: kit.track(new THREE.MeshBasicMaterial({ color: new THREE.Color(0.3, 1.3, 1.6) })),
  };
}
export type Mats = ReturnType<typeof makeMaterials>;

/** Collects static parts and merges them per material (and shadow behaviour) into single meshes. */
export class Sink {
  private groups = new Map<string, { material: THREE.Material; cast: boolean; receive: boolean; parts: THREE.BufferGeometry[] }>();

  add(geometry: THREE.BufferGeometry, material: THREE.Material, matrix: THREE.Matrix4, cast = true, receive = true) {
    const key = `${material.uuid}:${cast}:${receive}`;
    let group = this.groups.get(key);
    if (!group) this.groups.set(key, (group = { material, cast, receive, parts: [] }));
    const g = geometry.index ? geometry.toNonIndexed() : geometry.clone();
    for (const name of Object.keys(g.attributes)) if (name !== 'position' && name !== 'normal' && name !== 'uv') g.deleteAttribute(name);
    if (!g.attributes.uv) g.setAttribute('uv', new THREE.BufferAttribute(new Float32Array(g.attributes.position.count * 2), 2));
    if (!g.attributes.normal) g.computeVertexNormals();
    g.clearGroups();
    g.applyMatrix4(matrix);
    group.parts.push(g);
  }

  build(parent: THREE.Object3D) {
    for (const { material, cast, receive, parts } of this.groups.values()) {
      const merged = mergeGeometries(parts, false);
      parts.forEach(p => p.dispose());
      if (!merged) continue;
      const mesh = new THREE.Mesh(merged, material);
      mesh.castShadow = cast;
      mesh.receiveShadow = receive;
      mesh.matrixAutoUpdate = false;
      if ((material as THREE.MeshBasicMaterial).transparent) mesh.renderOrder = 1;
      parent.add(mesh);
    }
    this.groups.clear();
  }
}

const _m = new THREE.Matrix4();
const _q = new THREE.Quaternion();
const _e = new THREE.Euler();
const _s = new THREE.Vector3();
const _p = new THREE.Vector3();

/** Matrix from position, Euler rotation (radians, YXZ) and optional scale. */
export function T(x = 0, y = 0, z = 0, ry = 0, rx = 0, rz = 0, sx = 1, sy = sx, sz = sx) {
  return new THREE.Matrix4().compose(_p.set(x, y, z), _q.setFromEuler(_e.set(rx, ry, rz, 'YXZ')), _s.set(sx, sy, sz));
}

/** A transform scope for building equipment in local coordinates. */
export class B {
  constructor(readonly sink: Sink, readonly root: THREE.Object3D, readonly base = new THREE.Matrix4()) {}

  at(m: THREE.Matrix4) {
    return new B(this.sink, this.root, this.base.clone().multiply(m));
  }

  add(geometry: THREE.BufferGeometry, material: THREE.Material, m?: THREE.Matrix4, cast = true, receive = true) {
    this.sink.add(geometry, material, m ? _m.multiplyMatrices(this.base, m) : this.base, cast, receive);
  }

  /** Adds a standalone object (screens, moving parts) placed in this scope. */
  object<T extends THREE.Object3D>(obj: T, m?: THREE.Matrix4): T {
    const world = m ? this.base.clone().multiply(m) : this.base.clone();
    world.decompose(obj.position, obj.quaternion, obj.scale);
    this.root.add(obj);
    return obj;
  }

  world(x = 0, y = 0, z = 0) {
    return new THREE.Vector3(x, y, z).applyMatrix4(this.base);
  }
}

/** Geometry cache: one template per shape, cloned and baked by the sink. */
export class Geo {
  private cache = new Map<string, THREE.BufferGeometry>();
  constructor(private kit: Kit) {}

  private get<G extends THREE.BufferGeometry>(key: string, make: () => G): G {
    let g = this.cache.get(key) as G | undefined;
    if (!g) {
      g = make();
      this.cache.set(key, g);
      this.kit.track(g);
    }
    return g;
  }

  box(w: number, h: number, d: number) {
    return this.get(`b${w},${h},${d}`, () => new THREE.BoxGeometry(w, h, d));
  }

  rbox(w: number, h: number, d: number, r = 0.02, seg = 3) {
    return this.get(`rb${w},${h},${d},${r},${seg}`, () => new RoundedBoxGeometry(w, h, d, seg, Math.min(r, w / 2 - 1e-4, h / 2 - 1e-4, d / 2 - 1e-4)));
  }

  cyl(rt: number, rb: number, h: number, seg = 24, open = false) {
    return this.get(`c${rt},${rb},${h},${seg},${open}`, () => new THREE.CylinderGeometry(rt, rb, h, seg, 1, open));
  }

  sphere(r: number, ws = 20, hs = 12) {
    return this.get(`s${r},${ws},${hs}`, () => new THREE.SphereGeometry(r, ws, hs));
  }

  torus(r: number, tube: number, rs = 10, ts = 32, arc = Math.PI * 2) {
    return this.get(`t${r},${tube},${rs},${ts},${arc}`, () => new THREE.TorusGeometry(r, tube, rs, ts, arc));
  }

  plane(w: number, h: number) {
    return this.get(`p${w},${h}`, () => new THREE.PlaneGeometry(w, h));
  }

  circle(r: number, seg = 32) {
    return this.get(`ci${r},${seg}`, () => new THREE.CircleGeometry(r, seg));
  }

  lathe(key: string, points: [number, number][], seg = 48) {
    return this.get(`l${key}`, () => new THREE.LatheGeometry(points.map(([r, y]) => new THREE.Vector2(r, y)), seg));
  }

  custom<G extends THREE.BufferGeometry>(key: string, make: () => G) {
    return this.get(key, make);
  }
}

/** Soft contact-shadow textures: a rounded rectangle and a disc, blurred. */
export function shadowTextures(kit: Kit) {
  const rect = kit.canvas(256, 256, (ctx, w, h) => {
    ctx.shadowColor = 'rgba(0,0,0,1)';
    ctx.shadowBlur = 34;
    ctx.shadowOffsetX = 1000;
    ctx.fillStyle = '#000';
    ctx.beginPath();
    ctx.roundRect(52 - 1000, 52, w - 104, h - 104, 18);
    ctx.fill();
  });
  const disc = kit.canvas(256, 256, (ctx, w, h) => {
    const g = ctx.createRadialGradient(w / 2, h / 2, 0, w / 2, h / 2, w / 2);
    g.addColorStop(0, 'rgba(0,0,0,1)');
    g.addColorStop(0.45, 'rgba(0,0,0,0.75)');
    g.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, w, h);
  });
  const mat = (map: THREE.Texture, opacity: number) => kit.track(new THREE.MeshBasicMaterial({ color: '#000000', map, transparent: true, opacity, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 }));
  return { rect: mat(rect, 0.55), disc: mat(disc, 0.6) };
}
