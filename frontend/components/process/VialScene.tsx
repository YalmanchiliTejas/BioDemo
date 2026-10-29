'use client';

import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

export type GeometryRecord = {
  kind: string; inner_diameter_m: number; outer_diameter_m: number; frozen_fill_height_m: number;
  critical_temperature_c: number; geometry_provenance: string; reconstructed_details: string[]; color_encoding: string;
  frames: { time_h: number; interface_temperature_c: number; dried_layer_m: number; remaining_ice_kg_per_vial: number; critical_margin_c: number }[];
};

export default function VialScene({ geometry, recordId }: { geometry: GeometryRecord; recordId: string }) {
  const container = useRef<HTMLDivElement>(null);
  const actions = useRef<{ update: (index: number) => void; rotate: () => void; reset: () => void; export: () => void } | null>(null);
  const [frame, setFrame] = useState(0);
  const [error, setError] = useState('');
  const row = geometry.frames[Math.min(frame, geometry.frames.length-1)];

  useEffect(() => {
    if (!container.current || !geometry.frames.length) return;
    setFrame(0); setError('');
    let renderer: THREE.WebGLRenderer;
    try { renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true }); }
    catch { setError('3D rendering is unavailable in this browser. The calculated states and charts remain available.'); return; }
    const el = container.current;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
    renderer.domElement.setAttribute('role', 'img');
    renderer.domElement.setAttribute('aria-label', '3D vial cutaway showing computed remaining ice and dried layer');
    renderer.domElement.tabIndex = 0;
    el.appendChild(renderer.domElement);
    const scene = new THREE.Scene(); scene.background = new THREE.Color('#edf5f5');
    const camera = new THREE.PerspectiveCamera(35, 1, .001, 2);
    const home = new THREE.Vector3(.075, .05, .075);
    camera.position.copy(home);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.target.set(0, .012, 0); controls.minDistance = .045; controls.maxDistance = .25;
    controls.enableDamping = false; controls.enablePan = false; controls.update();
    scene.add(new THREE.HemisphereLight('#ffffff', '#718b9b', 2.4));
    const light = new THREE.DirectionalLight('#ffffff', 3); light.position.set(.1, .15, .1); scene.add(light);
    const shelf = new THREE.Mesh(new THREE.BoxGeometry(.075, .003, .065), new THREE.MeshStandardMaterial({ color: '#96aeb8', metalness: .4, roughness: .6 }));
    shelf.position.y = -.0015; scene.add(shelf);
    const glass = new THREE.Mesh(new THREE.CylinderGeometry(geometry.outer_diameter_m/2, geometry.outer_diameter_m/2, .034, 48, 1, true),
      new THREE.MeshStandardMaterial({ color: '#a3d5db', transparent: true, opacity: .16, depthWrite: false, side: THREE.DoubleSide }));
    glass.position.y = .017; scene.add(glass);
    const iceMaterial = new THREE.MeshStandardMaterial({ color: '#377caa', roughness: .45 });
    const ice = new THREE.Mesh(new THREE.CylinderGeometry(geometry.inner_diameter_m/2, geometry.inner_diameter_m/2, 1, 48), iceMaterial);
    scene.add(ice);
    const dry = new THREE.Mesh(new THREE.CylinderGeometry(geometry.inner_diameter_m/2, geometry.inner_diameter_m/2, 1, 48), new THREE.MeshStandardMaterial({ color: '#ead8ad', roughness: .95 })); scene.add(dry);
    const front = new THREE.Mesh(new THREE.CylinderGeometry(geometry.inner_diameter_m/2+.0001, geometry.inner_diameter_m/2+.0001, .00012, 48), new THREE.MeshBasicMaterial({ color: '#ffffff' })); scene.add(front);
    const render = () => renderer.render(scene, camera);
    const update = (index: number) => {
      const state = geometry.frames[index]; if (!state) return;
      const dried = Math.min(geometry.frozen_fill_height_m, Math.max(0, state.dried_layer_m));
      const remaining = geometry.frozen_fill_height_m-dried;
      ice.visible = remaining > 1e-7; ice.scale.y = Math.max(1e-7, remaining); ice.position.y = remaining/2;
      dry.visible = dried > 1e-7; dry.scale.y = Math.max(1e-7, dried); dry.position.y = remaining+dried/2;
      front.position.y = remaining; front.visible = remaining > 1e-7;
      const fraction = THREE.MathUtils.clamp((state.interface_temperature_c+50)/22, 0, 1);
      iceMaterial.color.setHSL(.59*(1-fraction), .65, .46);
      renderer.domElement.dataset.frameTimeH = state.time_h.toFixed(4);
      render();
    };
    const resize = () => { const width = el.clientWidth || 500; renderer.setSize(width, 340); camera.aspect = width/340; camera.updateProjectionMatrix(); render(); };
    const observer = new ResizeObserver(resize); observer.observe(el);
    controls.addEventListener('change', render);
    actions.current = { update,
      rotate: () => { camera.position.sub(controls.target).applyAxisAngle(new THREE.Vector3(0, 1, 0), Math.PI/6).add(controls.target); controls.update(); render(); },
      reset: () => { camera.position.copy(home); controls.update(); render(); },
      export: () => { render(); const a = document.createElement('a'); a.download = `${recordId}-vial-review.png`; a.href = renderer.domElement.toDataURL('image/png'); a.click(); },
    };
    const keyboard = (event: KeyboardEvent) => { if (event.key === 'ArrowRight') { event.preventDefault(); actions.current?.rotate(); } };
    renderer.domElement.addEventListener('keydown', keyboard);
    resize(); update(0);
    return () => {
      actions.current = null; observer.disconnect(); controls.removeEventListener('change', render); controls.dispose();
      renderer.domElement.removeEventListener('keydown', keyboard);
      const materials = new Set<THREE.Material>();
      scene.traverse(object => { if (object instanceof THREE.Mesh) { object.geometry.dispose(); (Array.isArray(object.material) ? object.material : [object.material]).forEach(m => materials.add(m)); } });
      materials.forEach(material => material.dispose()); renderer.dispose(); renderer.domElement.remove();
    };
  }, [geometry, recordId]);

  useEffect(() => { actions.current?.update(frame); }, [frame]);

  if (!row) return <p>No valid calculated states are available for 3D review.</p>;
  return <div className="space-y-3">
    <div ref={container} className="w-full min-h-[340px] rounded border overflow-hidden" />
    {error && <p role="alert">{error}</p>}
    <div className="flex flex-wrap items-center gap-3"><button className="underline" onClick={() => actions.current?.rotate()}>Rotate 3D view</button><button className="underline" onClick={() => actions.current?.reset()}>Reset camera</button><button className="underline" onClick={() => actions.current?.export()} disabled={!!error}>Save 3D review PNG</button></div>
    <label className="block">Review time: {row.time_h.toFixed(2)} h<input className="w-full mt-2" aria-label="3D review time" type="range" min={0} max={geometry.frames.length-1} step={1} value={Math.min(frame, geometry.frames.length-1)} onChange={event => setFrame(+event.target.value)} /></label>
    <div className="grid gap-2 sm:grid-cols-3 text-xs"><p>Interface: <strong>{row.interface_temperature_c.toFixed(2)}°C</strong></p><p>Dried layer: <strong>{(row.dried_layer_m*1000).toFixed(2)} mm</strong></p><p>Ice remaining: <strong>{(row.remaining_ice_kg_per_vial*1000).toFixed(3)} g/vial</strong></p></div>
    <p className="text-xs text-text-secondary">Blue → red encodes −50 → −28°C at the modeled interface. Beige is the dried layer; white marks the planar ice front. {geometry.color_encoding}. {geometry.geometry_provenance}. Glass height and shelf are schematic. Drag to orbit, scroll to zoom, or use the camera buttons.</p>
  </div>;
}
