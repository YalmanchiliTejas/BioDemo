import { createContext, useContext, useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { RiPauseLine, RiPlayLine } from "@remixicon/react";
import "./atmosphere.css";

const preferenceKey = "manufacturing-background-paused";
const MotionContext = createContext({ paused: false, reduced: false, toggle: () => {} });

/** Shared preference survives navigation between the landing page and workspace. */
export function MotionProvider({ children }: { children: ReactNode }) {
  const [paused, setPaused] = useState(() => {
    try { return localStorage.getItem(preferenceKey) === "true"; } catch { return false; }
  });
  const [reduced, setReduced] = useState(() => matchMedia("(prefers-reduced-motion: reduce)").matches);
  useEffect(() => {
    const query = matchMedia("(prefers-reduced-motion: reduce)");
    const change = () => setReduced(query.matches);
    const storage = (event: StorageEvent) => {
      if (event.key === preferenceKey || event.key === null) setPaused(event.newValue === "true");
    };
    query.addEventListener("change", change);
    addEventListener("storage", storage);
    return () => { query.removeEventListener("change", change); removeEventListener("storage", storage); };
  }, []);
  const toggle = () => {
    const next = !paused;
    setPaused(next);
    try { localStorage.setItem(preferenceKey, String(next)); } catch { /* Session-only preference when storage is unavailable. */ }
  };
  return <MotionContext.Provider value={{ paused, reduced, toggle }}>{children}</MotionContext.Provider>;
}

export const useAmbientMotion = () => useContext(MotionContext);

export function MotionControl({ className = "" }: { className?: string }) {
  const { paused, reduced, toggle } = useAmbientMotion();
  return <button type="button" className={`motion-control ${className}`} onClick={toggle} disabled={reduced} aria-pressed={paused || reduced} aria-label={reduced ? "Reduced motion: background animation disabled by system preference" : paused ? "Resume background animation" : "Pause background animation"} title={reduced ? "Follows your system’s reduced-motion preference" : undefined}>
    {paused || reduced ? <RiPlayLine size={14} /> : <RiPauseLine size={14} />}<span>{reduced ? "Reduced motion" : paused ? "Resume" : "Pause"}</span>
  </button>;
}

/** Image-matched light and reflections. Only transform/opacity change per frame.
 * Decorative layers never receive focus; offscreen and background-tab motion pauses.
 */
export function Atmosphere({ className = "", priority = false }: { className?: string; priority?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  const { paused, reduced } = useAmbientMotion();
  useEffect(() => {
    const root = ref.current;
    if (!root) return;
    let visible = false;
    const sync = () => { root.dataset.active = String(visible && !document.hidden); };
    const observer = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; sync(); });
    observer.observe(root);
    document.addEventListener("visibilitychange", sync);
    return () => { observer.disconnect(); document.removeEventListener("visibilitychange", sync); };
  }, []);
  return <div ref={ref} className={`atmosphere ${className}`} data-still={paused || reduced} data-active="false" aria-hidden="true">
    <div className="ambient-image"><img src="/os/assets/perplex-landscape.jpg" alt="" width={2048} height={1148} srcSet="/os/assets/perplex-landscape-mobile.jpg 1120w, /os/assets/perplex-landscape.jpg 2048w" sizes="100vw" fetchPriority={priority ? "high" : "auto"} loading={priority ? "eager" : "lazy"} /></div>
    <div className="ambient-light ambient-light-cool" /><div className="ambient-light ambient-light-warm" />
    <div className="ambient-reflection" />
    <div className="ambient-dust">{Array.from({ length: 7 }, (_, i) => <i key={i} style={{ "--particle": i } as CSSProperties} />)}</div>
  </div>;
}
