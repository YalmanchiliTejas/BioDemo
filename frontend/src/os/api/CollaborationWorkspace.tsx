import { useEffect, useRef, useState } from "react";
import { Field, RecordPicker, SuitePanel, useSuite } from "./suite-tools";
import type { Room } from "livekit-client";

type Session = { session_id: string; status: string; media_provider: string; participants: unknown[] };
type Annotation = { annotation_id: string; tool: string; author: string; content: { text?: string; points?: number[][] } };
export function CollaborationWorkspace() {
  const s = useSuite();
  const [caseId, setCaseId] = useState(""); const [people, setPeople] = useState("");
  const [providers, setProviders] = useState<string[]>([]); const [provider, setProvider] = useState("");
  const [providerError, setProviderError] = useState("");
  const [sessions, setSessions] = useState<Session[]>([]); const [sid, setSid] = useState("");
  const [annotations, setAnnotations] = useState<Annotation[]>([]); const [text, setText] = useState("");
  const [connected, setConnected] = useState(false); const [mic, setMic] = useState(false); const [camera, setCamera] = useState(false);
  const [points, setPoints] = useState<number[][]>([]); const drawing = useRef(false);
  const room = useRef<Room | null>(null); const media = useRef<HTMLDivElement>(null);
  useEffect(() => { let live = true; s.read<{ configured: string[] }>("/v1/collaboration/providers").then((r) => { if (live) { setProviders(r.configured); setProvider(r.configured[0] ?? ""); } }).catch(() => { if (live) setProviderError("Could not load media configuration. Check your access and connection."); }); return () => { live = false; }; }, [s.client]);
  useEffect(() => { if (!caseId) return; let live = true; s.read<{ items: Session[] }>(`/v1/collaboration/cases/${encodeURIComponent(caseId)}/sessions`).then((r) => { if (live) setSessions(r.items); }).catch(() => { if (live) setSessions([]); }); return () => { live = false; }; }, [s.client, caseId, s.version]);
  useEffect(() => {
    if (!sid) return;
    let live = true;
    const update = () => s.read<{ items: Annotation[] }>(`/v1/collaboration/sessions/${sid}/annotations`).then((r) => { if (live) setAnnotations(r.items); }).catch(() => { if (live) { void room.current?.disconnect(); setConnected(false); } });
    void update(); const timer = setInterval(update, 2500);
    return () => { live = false; clearInterval(timer); void room.current?.disconnect(); room.current = null; media.current?.replaceChildren(); setConnected(false); };
  }, [s.client, sid]);
  async function join() {
    await s.run(async () => {
      await s.command(`/v1/collaboration/sessions/${sid}/consent`, { granted: true });
      const token = await s.command<{ server_url: string; token: string }>(`/v1/collaboration/sessions/${sid}/join`);
      if (!token.server_url) throw new Error("This provider does not supply browser media");
      const { Room, RoomEvent } = await import("livekit-client");
      await room.current?.disconnect();
      const r = new Room(); room.current = r;
      r.on(RoomEvent.TrackSubscribed, (track) => { media.current?.appendChild(track.attach()); });
      r.on(RoomEvent.TrackUnsubscribed, (track) => { track.detach().forEach((el) => el.remove()); });
      r.on(RoomEvent.LocalTrackPublished, (publication) => { if (publication.track?.kind === "video") { const el = publication.track.attach(); el.muted = true; media.current?.appendChild(el); } });
      r.on(RoomEvent.LocalTrackUnpublished, (publication) => { publication.track?.detach().forEach((el) => el.remove()); });
      r.on(RoomEvent.Disconnected, () => { setConnected(false); setCamera(false); setMic(false); media.current?.replaceChildren(); });
      await r.connect(token.server_url, token.token); await r.startAudio(); setConnected(true);
      return { connected: true, camera_enabled: false, microphone_enabled: false };
    });
  }
  return <SuitePanel state={s}><div className="suite-columns"><section>
    <form onSubmit={(e) => { e.preventDefault(); void s.run(async () => { const r = await s.command<Session>("/v1/collaboration/sessions", { case_id: caseId, participants: people.split(",").map((p) => p.trim()).filter(Boolean), media_provider: provider }); setSid(r.session_id); return r; }); }}><h2>Remote assistance</h2><RecordPicker label="Case" kind="case" value={caseId} onChange={setCaseId} version={s.version} /><Field label="Participants (person IDs, comma separated)" value={people} onChange={setPeople} /><label>Media service<select value={provider} onChange={(e) => setProvider(e.target.value)}>{providers.map((p) => <option key={p}>{p}</option>)}</select></label>{!providers.length && <p role="status">No media service configured. Configure the LiveKit server URL and credentials on the backend.</p>}<button disabled={!provider}>Create assistance session</button></form>
    {providerError && <p role="alert">{providerError}</p>}
    {sessions.map((r) => <article className="suite-result" key={r.session_id}><p>{r.session_id} · {r.status}</p><button disabled={r.status !== "active"} onClick={() => setSid(r.session_id)}>Open session</button>{["creating", "creation_unknown"].includes(r.status) && <button onClick={() => void s.run(() => s.command(`/v1/collaboration/sessions/${r.session_id}/reconcile`))}>Reconcile room creation</button>}{r.status === "ending_unknown" && <button onClick={() => void s.run(() => s.command(`/v1/collaboration/sessions/${r.session_id}/end`))}>Confirm room closure</button>}</article>)}
    {sid && <section><h2>Session controls</h2><p>Joining enables live media reception. Camera and microphone stay off until you enable them. Recording is disabled.</p><div className="suite-buttons">
      <button disabled={connected} onClick={() => void join()}>Agree and join live session</button>
      <button disabled={!connected} onClick={() => void s.run(async () => { await room.current!.localParticipant.setMicrophoneEnabled(!mic); setMic(!mic); return { microphone_enabled: !mic }; })}>{mic ? "Mute microphone" : "Enable microphone"}</button>
      <button disabled={!connected} onClick={() => void s.run(async () => { await room.current!.localParticipant.setCameraEnabled(!camera); setCamera(!camera); return { camera_enabled: !camera }; })}>{camera ? "Disable camera" : "Enable camera"}</button>
      <button disabled={!connected} onClick={() => void s.run(async () => { await room.current!.localParticipant.setScreenShareEnabled(!room.current!.localParticipant.isScreenShareEnabled); return { screen_share: room.current!.localParticipant.isScreenShareEnabled }; })}>Toggle screen share</button>
      <button onClick={() => { void room.current?.disconnect(); }}>Leave call</button>
      <button onClick={() => void s.run(async () => { const r = await s.command(`/v1/collaboration/sessions/${sid}/end`); await room.current?.disconnect(); return r; })}>End session for everyone</button>
    </div></section>}
    </section><section><h2>Live media</h2><div className="suite-media" ref={media} />
    {sid && <><form onSubmit={(e) => { e.preventDefault(); void s.run(async () => { const r = await s.command(`/v1/collaboration/sessions/${sid}/annotations`, { tool: "chat", content: { text } }); setText(""); return r; }); }}><Field label="Case-linked message" value={text} onChange={setText} /><button>Send to session</button></form>
    <h3>Shared sketch</h3><svg className="suite-sketch" viewBox="0 0 100 100" role="img" aria-label="Shared drawing canvas" onPointerDown={(e) => { drawing.current = true; e.currentTarget.setPointerCapture(e.pointerId); const b = e.currentTarget.getBoundingClientRect(); setPoints([[(e.clientX-b.left)/b.width*100, (e.clientY-b.top)/b.height*100]]); }} onPointerMove={(e) => { if (!drawing.current) return; const b=e.currentTarget.getBoundingClientRect(); setPoints((p) => p.length < 500 ? [...p, [(e.clientX-b.left)/b.width*100, (e.clientY-b.top)/b.height*100]] : p); }} onPointerUp={() => { drawing.current = false; }}>
      {[...annotations.filter((a) => a.tool === "drawing").map((a) => a.content.points ?? []), points].map((p, i) => <polyline key={i} points={p.map((x) => x.join(",")).join(" ")} stroke="#245f4a" strokeWidth="0.7" fill="none" />)}
    </svg><button disabled={!points.length} onClick={() => void s.run(async () => { const r = await s.command(`/v1/collaboration/sessions/${sid}/annotations`, { tool: "drawing", content: { points } }); setPoints([]); return r; })}>Share sketch</button>
    <ol>{annotations.filter((a) => a.tool === "chat").map((a) => <li key={a.annotation_id}><b>{a.author}</b>: {a.content.text}</li>)}</ol></>}
    </section></div></SuitePanel>;
}
