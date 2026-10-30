import * as THREE from 'three';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { GTAOPass } from 'three/addons/postprocessing/GTAOPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { B, Geo, Kit, Sink, T, makeMaterials, shadowTextures } from './labKit';
import { screens } from './labScreens';
import { ROOM, mobileTank, singleUseMixer, bioreactor, controlRoom, controlSkid, dockDoor, floorTape, floorText, freezeDryer, glassWall, goodsReceipt, pipe, pipeRack, pumpCart, qcLab, reviewOffice, room, sign, type Ctx } from './labModels';

/* Renders the bioprocess suite on demand. The hero tour drives the camera through `setView`; nothing re-renders
 * unless the camera moved, the canvas resized, or a nearby animated part (agitator coupling, HMI) needs a frame. */

export type StationKey = 'overview' | 'partners' | 'connect' | 'monitor' | 'investigate' | 'predict' | 'act';
type Pose = { pos: [number, number, number]; target: [number, number, number]; fov: number; shift: number; lift?: number; via?: [number, number, number]; maxBack?: number };

/** Camera per station. `shift` moves the subject sideways (lens shift) to leave room for the callout. */
export const POSES: Record<StationKey, Pose> = {
  overview: { pos: [5.5, 12.5, 17.5], target: [0.6, 0.4, -2.0], fov: 38, shift: -0.06 },
  partners: { pos: [-4.0, 2.7, 8.0], target: [-8.2, 0.55, 2.6], fov: 44, shift: 0.14, lift: 0.08 },
  connect: { pos: [-7.3, 2.4, 0.6], target: [-8.9, 1.15, -6.4], fov: 46, shift: 0.14, lift: 0.08 },
  monitor: { pos: [0.6, 2.0, 0.9], target: [-2.6, 1.55, -5.0], fov: 44, shift: -0.14, lift: 0.08 },
  investigate: { pos: [1.3, 1.7, -0.2], target: [-1.2, 1.0, -3.8], fov: 42, shift: -0.12, lift: 0.08 },
  predict: { pos: [4.4, 2.2, 0.2], target: [9.6, 1.25, -4.6], fov: 44, shift: -0.14, lift: 0.08 },
  act: { pos: [6.55, 1.9, 3.85], target: [10.9, 1.35, 3.85], fov: 48, shift: 0.12, lift: 0.06, via: [9.6, 1.9, -0.8], maxBack: 1.05 },
};

export type Lab = { setView(a: StationKey, b: StationKey, t: number): void; dispose(): void };

const tick = () => new Promise<void>(resolve => setTimeout(resolve, 0));

export async function createLab(container: HTMLElement, { still = false, initial, onLost }: { still?: boolean; initial: [StationKey, StationKey, number]; onLost: () => void }): Promise<Lab> {
  const small = Math.min(window.innerWidth, window.innerHeight * 1.6) < 900;
  const useAO = !small;
  // Full resolution when the camera rests; a lighter resolution while it moves, where softness is invisible.
  const fullDpr = Math.min(window.devicePixelRatio || 1, small ? 1.5 : 1.75);
  const motionDpr = Math.min(fullDpr, 1);
  const renderer = new THREE.WebGLRenderer({ antialias: !useAO, alpha: true, powerPreference: 'high-performance' });
  renderer.setPixelRatio(fullDpr);
  renderer.setClearColor(0x000000, 0);
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.0;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFShadowMap;
  renderer.shadowMap.autoUpdate = false;
  renderer.transmissionResolutionScale = 0.5;
  const canvas = renderer.domElement;
  canvas.style.cssText = 'display:block;width:100%;height:100%';
  canvas.setAttribute('aria-hidden', 'true');

  let disposed = false;
  const lost = (e: Event) => { e.preventDefault(); if (!disposed) onLost(); };
  canvas.addEventListener('webglcontextlost', lost);

  if (document.fonts?.ready) await Promise.race([document.fonts.ready, new Promise(r => setTimeout(r, 800))]);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(40, 1, 0.1, 120);
  const kit = new Kit(renderer);
  const c: Ctx = { kit, m: makeMaterials(kit), g: new Geo(kit), sh: shadowTextures(kit), scr: screens(kit), anim: { couplings: [], glow: [] }, fade: [] };
  const root = new THREE.Group();
  scene.add(root);
  const sink = new Sink();
  const b = new B(sink, root);
  const V = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z);

  room(c, b);
  await tick();

  // control room behind a glazed partition
  glassWall(c, b, V(-6.5, 0, ROOM.z0), V(-6.5, 0, -3.6), ROOM.h);
  controlRoom(c, b.at(T(-8.75, 0, -5.8)));
  sign(c, b, 1.3, 0.24, 'CONTROL ROOM', 'MES · LIMS · historian', T(-8.75, 3.15, ROOM.z0 + 0.01));

  // upstream suite
  const br1 = b.at(T(-2.7, 0, -5.2, 0.45));
  const r1 = bioreactor(c, br1, { R: 0.62, H: 1.45, leg: 0.45, name: 'BR-UP-01', volume: '2000 L working volume' });
  const br2 = b.at(T(0.9, 0, -6.2, 0.15));
  const r2 = bioreactor(c, br2, { R: 0.42, H: 0.95, leg: 0.5, name: 'BR-UP-02', volume: '500 L working volume' });
  controlSkid(c, b.at(T(-4.75, 0, -3.7, 0.65)));
  const cart = b.at(T(-0.55, 0, -3.0, -0.35));
  const feed = br1.world(r1.feed.x, r1.feed.y, r1.feed.z);
  pumpCart(c, cart, feed.clone().add(V(0, 0.02, 0)).applyMatrix4(cart.base.clone().invert()));
  pipeRack(c, b, -5.6, 4.6, ROOM.z0);
  for (const [scope, r] of [[br1, r1], [br2, r2]] as const) {
    const e = scope.world(r.exhaust.x, r.exhaust.y, r.exhaust.z);
    pipe(c, b, [e, V(e.x, 2.8, e.z), V(e.x, 2.8, ROOM.z0 + 0.36)], 0.022, { clamps: 0.9 });
    const o = scope.world(r.outlet.x + 0.12, r.outlet.y, r.outlet.z);
    pipe(c, b, [o, V(o.x + 0.25, o.y, o.z), V(o.x + 0.25, 0.22, o.z), V(o.x + 0.25, 0.22, ROOM.z0 + 0.25), V(o.x + 0.25, 2.8, ROOM.z0 + 0.25)], 0.019, { clamps: 1.1 });
  }
  sign(c, b, 1.7, 0.28, 'UPSTREAM · SUITE 2', 'Grade C · gowning required', T(-1.2, 3.25, ROOM.z0 + 0.01));
  await tick();

  // buffer preparation in the middle of the hall
  mobileTank(c, b.at(T(-3.0, 0, 0.9, 0.3)));
  mobileTank(c, b.at(T(-2.05, 0, 1.35, -0.2)), 0.3, 0.5);
  mobileTank(c, b.at(T(-3.3, 0, 2.0, 0.8)), 0.3, 0.5);
  singleUseMixer(c, b.at(T(0.9, 0, 1.0, -0.4)));
  floorTape(c, b, -4.2, 0.1, 2.2, 2.9, c.m.tape);
  sign(c, b, 1.2, 0.22, 'BUFFER PREP', 'Mobile vessels', T(-1.0, 2.7, 2.95));
  for (const x of [-1.5, -0.5]) b.add(c.g.cyl(0.003, 0.003, ROOM.h - 2.81, 6), c.m.steelPolished, T(x, (ROOM.h + 2.81) / 2, 2.95), false, false);

  // QC lab and freeze dryer
  qcLab(c, b.at(T(5.2, 0, -7.4)));
  sign(c, b, 1.1, 0.22, 'QC LAB', 'Biosafety level 2', T(5.2, 3.2, ROOM.z0 + 0.01));
  freezeDryer(c, b.at(T(10.0, 0, -5.45, -Math.PI / 2)));
  sign(c, b, 1.5, 0.26, 'LYOPHILISATION', 'LYO-02 · production', T(ROOM.x1 - 0.01, 3.2, -5.45, -Math.PI / 2));
  await tick();

  // goods receipt for CMO deliveries
  dockDoor(c, b.at(T(ROOM.x0, 0, 3.1, Math.PI / 2)));
  goodsReceipt(c, b.at(T(-8.4, 0, 2.3)));
  floorTape(c, b, -10.7, 0.8, -6.0, 5.9, c.m.tape);
  floorText(c, b, 'QUARANTINE', 1.6, 0.28, T(-8.6, 0, 1.25));
  sign(c, b, 1.6, 0.28, 'GOODS RECEIPT', 'CMO deliveries · quarantine', T(ROOM.x0 + 0.01, 2.75, 0.4, Math.PI / 2));

  // glass-walled review office
  reviewOffice(c, b, 6.2, 1.2, ROOM.x1, ROOM.z1);
  await tick();

  sink.build(root);
  root.updateMatrixWorld(true);
  root.traverse(o => { if (!c.anim.couplings.includes(o)) { o.matrixAutoUpdate = false; o.updateMatrix(); } });

  // lighting: a soft high key that casts the (static) shadows, a faint fill, and image-based light
  const key = new THREE.DirectionalLight('#fffaf3', 3.2);
  key.position.set(3, 14, 5.5);
  key.target.position.set(0, 0, -1);
  key.castShadow = true;
  const sc = key.shadow.camera;
  sc.left = -15; sc.right = 15; sc.top = 12; sc.bottom = -12; sc.near = 2; sc.far = 34;
  key.shadow.mapSize.set(small ? 1024 : 2048, small ? 1024 : 2048);
  key.shadow.radius = 2;
  key.shadow.bias = -0.0004;
  key.shadow.normalBias = 0.025;
  scene.add(key, key.target);
  const fill = new THREE.DirectionalLight('#eef4f8', 0.35);
  fill.position.set(-8, 6, 10);
  scene.add(fill, new THREE.HemisphereLight('#ffffff', '#9ea4a9', 0.12));

  // First light the lab with a neutral studio environment, then capture the lab itself from the middle of the
  // floor so steel, glass and the epoxy floor reflect white panels and ceiling lights rather than a studio.
  const pmrem = new THREE.PMREMGenerator(renderer);
  const roomEnv = new RoomEnvironment();
  const studio = pmrem.fromScene(roomEnv, 0.04).texture;
  roomEnv.dispose();
  scene.environment = studio;
  scene.environmentIntensity = 0.7;
  renderer.shadowMap.needsUpdate = true;
  const env = pmrem.fromScene(scene, 0.02, 0.05, 60, { size: small ? 128 : 256, position: new THREE.Vector3(0.5, 1.9, -1.6) }).texture;
  pmrem.dispose();
  studio.dispose();
  scene.environment = env;
  scene.environmentIntensity = 0.42;

  // camera state
  const from = new THREE.Vector3(), to = new THREE.Vector3(), mid = new THREE.Vector3(), pos = new THREE.Vector3(), target = new THREE.Vector3();
  let view: [StationKey, StationKey, number] = initial;
  let width = 1, height = 1;
  let dirty = true;

  const apply = () => {
    const [ka, kb, t] = view;
    const A = POSES[ka], Bp = POSES[kb];
    from.fromArray(A.pos); to.fromArray(Bp.pos);
    if (ka !== kb && Bp.via) {
      const u = 1 - t;
      pos.copy(from).multiplyScalar(u * u).addScaledVector(mid.fromArray(Bp.via), 2 * u * t).addScaledVector(to, t * t);
    } else {
      pos.lerpVectors(from, to, t);
      if (ka !== kb && A.pos[1] < ROOM.h && Bp.pos[1] < ROOM.h) pos.y += Math.sin(Math.PI * t) * Math.min(0.5, from.distanceTo(to) * 0.05);
    }
    target.lerpVectors(from.fromArray(A.target), to.fromArray(Bp.target), t);
    let fov = THREE.MathUtils.lerp(A.fov, Bp.fov, t);
    let shift = THREE.MathUtils.lerp(A.shift, Bp.shift, t);
    const lift = THREE.MathUtils.lerp(A.lift ?? 0, Bp.lift ?? 0, t);
    const aspect = width / height;
    if (aspect < 1.3) {
      // keep the designed horizontal framing on narrow screens: widen first, then step back
      shift = 0;
      const half = Math.atan(Math.tan(THREE.MathUtils.degToRad(fov) / 2) * 1.35);
      let v = 2 * Math.atan(Math.tan(half) / aspect);
      const cap = THREE.MathUtils.degToRad(68);
      if (v > cap) {
        const back = Math.min(THREE.MathUtils.lerp(A.maxBack ?? 1.7, Bp.maxBack ?? 1.7, t), Math.tan(half) / (Math.tan(cap / 2) * aspect));
        pos.sub(target).multiplyScalar(back).add(target);
        v = cap;
      }
      fov = THREE.MathUtils.radToDeg(v);
    }
    camera.position.copy(pos);
    camera.lookAt(target);
    camera.fov = fov;
    camera.aspect = aspect;
    camera.setViewOffset(width, height, shift * width, lift * height, width, height);
    camera.updateProjectionMatrix();
    const op = THREE.MathUtils.clamp((ROOM.h - 0.12 - pos.y) / 0.45, 0, 1);
    for (const mat of c.fade) { mat.opacity = op; mat.visible = op > 0.01; }
    dirty = true;
  };

  // Ground-truth ambient occlusion on larger screens, computed at half resolution (it is low-frequency).
  let composer: EffectComposer | null = null;
  let gtao: GTAOPass | null = null;
  if (useAO) {
    composer = new EffectComposer(renderer, new THREE.WebGLRenderTarget(1, 1, { type: THREE.HalfFloatType, samples: 4 }));
    composer.addPass(new RenderPass(scene, camera));
    gtao = new GTAOPass(scene, camera, 1, 1);
    gtao.output = GTAOPass.OUTPUT.Default;
    gtao.blendIntensity = 0.85;
    gtao.updateGtaoMaterial({ radius: 0.45, distanceExponent: 1.6, thickness: 1.2, scale: 1.1, samples: 10, distanceFallOff: 1 });
    gtao.updatePdMaterial({ lumaPhi: 10, depthPhi: 2, normalPhi: 3, radius: 9, radiusExponent: 1.5, rings: 2, samples: 14 });
    composer.addPass(gtao);
    composer.addPass(new OutputPass());
  }

  const render = () => {
    if (composer) composer.render(); else renderer.render(scene, camera);
    dirty = false;
  };

  const size = () => {
    width = Math.max(1, container.clientWidth);
    height = Math.max(1, container.clientHeight);
    renderer.setSize(width, height, false);
    if (composer && gtao) {
      const pr = renderer.getPixelRatio();
      composer.setPixelRatio(pr);
      composer.setSize(width, height);
      gtao.setSize(Math.round(width * pr * 0.5), Math.round(height * pr * 0.5));
    }
  };

  const resize = () => {
    size();
    apply();
    if (still) render();
  };

  let dpr = fullDpr;
  let settleAt = 0;
  let movedAt = 0;
  const setDpr = (next: number) => {
    if (next === dpr) return;
    dpr = next;
    renderer.setPixelRatio(next);
    size();
    dirty = true;
  };

  // Gentle life: the agitator couplings turn and the HMI breathes when the camera is close enough to see them,
  // at a low frame rate and only for a few seconds after arriving, so a resting page does not keep the GPU busy.
  const near = new THREE.Vector3();
  let last = 0;
  const animate = (time: number) => {
    if (settleAt && time > settleAt) { settleAt = 0; setDpr(fullDpr); }
    if (!still && !settleAt && time - movedAt < 8000 && time - last > 50) {
      const dt = last ? Math.min(0.1, (time - last) / 1000) : 0;
      let seen = false;
      for (const cp of c.anim.couplings) if (camera.position.distanceTo(cp.getWorldPosition(near)) < 7.5) { seen = true; break; }
      if (seen) {
        for (const cp of c.anim.couplings) cp.rotation.y += dt * 1.4;
        for (const g of c.anim.glow) g.emissiveIntensity = 1.12 + Math.sin(time / 1300) * 0.06;
        dirty = true;
      }
      last = time;
    }
    if (dirty) render();
  };

  let running = false;
  const setRunning = (on: boolean) => {
    if (still || disposed || on === running) return;
    running = on;
    renderer.setAnimationLoop(on ? animate : null);
  };
  const io = new IntersectionObserver(([entry]) => setRunning(entry.isIntersecting), { rootMargin: '120px' });
  const ro = new ResizeObserver(resize);

  container.appendChild(canvas);
  size();
  apply();
  await renderer.compileAsync(scene, camera).catch(() => undefined);
  if (disposed) return { setView() {}, dispose() {} };
  renderer.shadowMap.needsUpdate = true;
  render();
  ro.observe(container);
  if (!still) io.observe(container);

  return {
    setView(a, bk, t) {
      if (view[0] === a && view[1] === bk && Math.abs(view[2] - t) < 1e-4) return;
      view = [a, bk, t];
      apply();
      if (still) { render(); return; }
      movedAt = performance.now();
      settleAt = movedAt + 220;
      setDpr(motionDpr);
    },
    dispose() {
      disposed = true;
      io.disconnect();
      ro.disconnect();
      renderer.setAnimationLoop(null);
      canvas.removeEventListener('webglcontextlost', lost);
      scene.traverse(o => {
        const mesh = o as THREE.Mesh;
        if (mesh.isMesh) { mesh.geometry.dispose(); if ((mesh as unknown as THREE.InstancedMesh).isInstancedMesh) (mesh as unknown as THREE.InstancedMesh).dispose(); }
      });
      kit.disposables.forEach(d => d.dispose());
      env.dispose();
      gtao?.dispose();
      composer?.dispose();
      key.shadow.map?.dispose();
      renderer.renderLists.dispose();
      renderer.dispose();
      renderer.forceContextLoss();
      canvas.remove();
    },
  };
}
