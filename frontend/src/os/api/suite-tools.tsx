import { useEffect, useRef, useState, type ReactNode } from "react";
import { useConnected } from "./ConnectedWorkspace";
import { errorMessage, newIdempotencyKey, type SuiteRecord } from "./client";

export function useSuite() {
  const { client, me } = useConnected();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<unknown>(null);
  const [version, setVersion] = useState(0);
  async function run<T>(task: () => Promise<T>): Promise<T | undefined> {
    setBusy(true); setError("");
    try { const r = await task(); setResult(r); setVersion((v) => v + 1); return r; }
    catch (e) { setError(errorMessage(e)); }
    finally { setBusy(false); }
  }
  const command = <T,>(path: string, body?: unknown) => client!.suiteCommand<T>(path, body, newIdempotencyKey());
  const read = <T,>(path: string) => client!.suiteRead<T>(path);
  return { client: client!, me: me!, busy, error, result, version, run, command, read };
}

export function useRecords(kind: string, version = 0) {
  const { client } = useConnected();
  const [records, setRecords] = useState<SuiteRecord[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    let live = true;
    const fetchPages = async () => {
      const items: SuiteRecord[] = [];
      let cursor: string | undefined;
      do {
        if (!live || !client) return items;
        const page = await client.listRecords(kind, cursor);
        items.push(...page.items);
        cursor = page.next_cursor ?? undefined;
      } while (cursor);
      return items;
    };
    void fetchPages().then((items) => { if (live) { setRecords(items); setError(""); } })
      .catch((e) => { if (live) setError(errorMessage(e)); });
    return () => { live = false; };
  }, [kind, client, version]);
  return { records, error };
}

export function Field({ label, value, onChange, type = "text", required = true }: {
  label: string; value: string; onChange: (s: string) => void; type?: string; required?: boolean;
}) {
  return <label>{label}<input required={required} type={type} step={type === "number" ? "any" : undefined} value={value} onChange={(e) => onChange(e.target.value)} /></label>;
}

export function JsonField({ label, value, onChange }: { label: string; value: unknown; onChange: (x: any) => void }) {
  const [text, setText] = useState(() => JSON.stringify(value, null, 2));
  const [error, setError] = useState("");
  const focused = useRef(false);
  useEffect(() => { if (!focused.current) setText(JSON.stringify(value, null, 2)); }, [value]);
  return <label>{label}<textarea rows={5} value={text} onFocus={() => { focused.current = true; }} onBlur={() => { focused.current = false; }} onChange={(e) => { setText(e.target.value); try { onChange(JSON.parse(e.target.value)); setError(""); e.target.setCustomValidity(""); } catch { setError("Enter valid JSON with the expected structure before saving"); e.target.setCustomValidity("Enter valid JSON before saving"); } }} />{error && <span role="alert">{error}</span>}</label>;
}

export function RecordPicker({ label, kind, value, onChange, version = 0, required = true }: {
  label: string; kind: string; value: string; onChange: (s: string) => void; version?: number; required?: boolean;
}) {
  const { records, error } = useRecords(kind, version);
  return <label>{label}<select required={required} value={value} onChange={(e) => onChange(e.target.value)}><option value="">Choose…</option>{records.map((r) => <option key={r.id} value={r.id}>{String(r.state.name ?? r.id)} · {String(r.state.status ?? "saved")}</option>)}</select>{error && <span role="alert">{error}</span>}</label>;
}

export function SuitePanel({ state, children }: { state: ReturnType<typeof useSuite>; children: ReactNode }) {
  return <div className="suite-workflow" aria-busy={state.busy}>
    {state.error && <p role="alert" className="suite-error">{state.error}</p>}
    <fieldset disabled={state.busy} className="suite-workflow-controls">{children}</fieldset>
    {state.busy && <p role="status">Working…</p>}
    {state.result != null && <details open className="suite-result"><summary>Operation result and evidence</summary><pre>{JSON.stringify(state.result, null, 2)}</pre></details>}
  </div>;
}
