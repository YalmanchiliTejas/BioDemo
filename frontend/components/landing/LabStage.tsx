'use client';

import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from 'react';
import { PlantScene, STATIONS } from './PlantScene';
import { cameraTransform } from './sceneKit';
import { lerp } from './motion';
import type { Lab, StationKey } from './labScene';
import { cn } from '@/lib/cn';

/* The hero's scene. Loads the three.js render of the facility after first paint and drives its camera imperatively;
 * falls back to the SVG plant when WebGL is unavailable or the context is lost. */

export type View = { station: StationKey; zoom: number };
export type StageHandle = { setView(a: View, b: View, t: number): void };

function webglAvailable() {
  try {
    return !!document.createElement('canvas').getContext('webgl2');
  } catch {
    return false;
  }
}

const LABEL = 'Rendered biologics facility: a goods-receipt bay with CMO deliveries, a control room with MES, LIMS and historian screens, jacketed bioreactors with a control skid and feed pump, a QC bench with a biosafety cabinet, a production freeze dryer and a glass-walled review office.';

export const LabStage = forwardRef<StageHandle, { initial: View; still?: boolean; anchor?: number; className?: string }>(function LabStage({ initial, still = false, anchor, className }, ref) {
  const [mode, setMode] = useState<'loading' | 'webgl' | 'svg'>('loading');
  const host = useRef<HTMLDivElement>(null);
  const svgCamera = useRef<SVGGElement>(null);
  const lab = useRef<Lab | null>(null);
  const last = useRef<[View, View, number]>([initial, initial, 1]);

  const svgTransform = useCallback(([a, b, t]: [View, View, number]) => {
    const fa = STATIONS[a.station], fb = STATIONS[b.station];
    return cameraTransform([lerp(fa[0], fb[0], t), lerp(fa[1], fb[1], t), lerp(fa[2], fb[2], t)], lerp(a.zoom, b.zoom, t), anchor);
  }, [anchor]);

  useImperativeHandle(ref, () => ({
    setView(a, b, t) {
      last.current = [a, b, t];
      lab.current?.setView(a.station, b.station, t);
      svgCamera.current?.setAttribute('transform', svgTransform(last.current));
    },
  }), [svgTransform]);

  useEffect(() => {
    if (!webglAvailable()) { setMode('svg'); return; }
    let cancelled = false;
    let instance: Lab | null = null;
    const fail = () => {
      if (cancelled) return;
      cancelled = true;
      lab.current = null;
      instance?.dispose();
      instance = null;
      setMode('svg');
    };
    import('./labScene')
      .then(async ({ createLab }) => {
        if (cancelled || !host.current) return;
        const [a0, b0, t0] = last.current;
        const created = await createLab(host.current, { still, initial: [a0.station, b0.station, t0], onLost: fail });
        if (cancelled) { created.dispose(); return; }
        instance = created;
        lab.current = created;
        const [a, b, t] = last.current;
        created.setView(a.station, b.station, t);
        setMode('webgl');
      })
      .catch(fail);
    return () => {
      cancelled = true;
      lab.current = null;
      instance?.dispose();
    };
  }, [still]);

  return (
    <div className={cn('lp-lab', className)} data-mode={mode} role={mode === 'svg' ? undefined : 'img'} aria-label={mode === 'svg' ? undefined : LABEL}>
      {mode === 'svg' ? (
        <PlantScene ref={svgCamera} initial={svgTransform(last.current)} className="h-full w-full" />
      ) : (
        <>
          <div className="lp-lab-placeholder" aria-hidden />
          <div ref={host} className="lp-lab-canvas" />
        </>
      )}
    </div>
  );
});
