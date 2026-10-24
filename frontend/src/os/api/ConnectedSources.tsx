import { useCallback, useEffect, useState } from "react";
import { Button } from "../../lab/ui";
import { PageHead } from "../workbench/shared";
import { useConnected } from "./ConnectedWorkspace";
import { errorMessage, type ConnectorCatalog, type ConnectorRecord } from "./client";

export function ConnectedSources() {
  const { client, me, loadEvidence } = useConnected();
  const [catalog, setCatalog] = useState<ConnectorCatalog | null>(null);
  const [items, setItems] = useState<ConnectorRecord[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [adding, setAdding] = useState(false);
  const [family, setFamily] = useState("MES");
  const [transport, setTransport] = useState("rest");
  const [id, setId] = useState("");
  const [site, setSite] = useState("");
  const [endpoint, setEndpoint] = useState("");
  const [path, setPath] = useState("/events");
  const [credential, setCredential] = useState("");
  const [addresses, setAddresses] = useState("");
  const [security, setSecurity] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [mapping, setMapping] = useState("");
  const [pollSeconds, setPollSeconds] = useState(0);
  const mayConfigure = me?.roles.some((r) => ["admin", "manufacturing_systems", "quality_systems"].includes(r));
  const refresh = useCallback(async () => {
    if (client) setItems(await client.listConnectors());
  }, [client]);
  useEffect(() => {
    if (!client || !mayConfigure) return;
    let alive = true;
    Promise.all([client.connectorCatalog(), client.listConnectors()]).then(([c, rows]) => {
      if (alive) { setCatalog(c); setItems(rows); }
    }).catch((e) => alive && setError(errorMessage(e)));
    return () => { alive = false; };
  }, [client, mayConfigure]);

  async function run(connector: ConnectorRecord, action: "preview" | "sync") {
    if (!client) return;
    setBusy(connector.connector_id); setError(""); setResult(null);
    try {
      setResult(await (action === "preview" ? client.previewConnector(connector.connector_id) : client.syncConnector(connector.connector_id)));
      await refresh();
      if (action === "sync") await loadEvidence(true);
    } catch (e) { setError(errorMessage(e)); }
    finally { setBusy(""); }
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!client || !me) return;
    setBusy("save"); setError("");
    try {
      const options: Record<string, unknown> = {};
      options.poll_seconds = pollSeconds;
      if (transport === "file") options.directory = endpoint;
      else if (transport === "webhook") options.secret_env = credential;
      else options.base_url = endpoint;
      if (transport === "rest") {
        options.events_path = path;
        if (credential) options.auth_env = credential;
      }
      if (transport === "mqtt" || transport === "opcua") {
        options.addresses = addresses.split("\n").map((s) => s.trim()).filter(Boolean);
        if (username) options.username_env = username;
        if (password) options.password_env = password;
      }
      if (transport === "opcua") options.security_string_env = security;
      const customMapping = mapping.trim() ? JSON.parse(mapping) : undefined;
      await client.configureConnector({ connector_id: id, family, transport, site_id: site,
        owner: me.actor_id, options, mapping: customMapping });
      await refresh(); setAdding(false); setResult(null);
    } catch (e) { setError(errorMessage(e)); }
    finally { setBusy(""); }
  }

  return <div className="ws-page">
    <PageHead eyebrow="" title="Sources" description="Connect authorized records while existing systems retain ownership." />
    {!mayConfigure ? <p>Ask a manufacturing systems administrator to configure source connections for your site.</p> : <>
      <div className="ws-notice"><p>Connections start read-only. Vendor qualification is tracked separately from a successful connection test.</p></div>
      <Button onClick={() => setAdding(!adding)}>{adding ? "Close setup" : "Add connection"}</Button>
      {adding && <form className="cw-form cw-connector-form ws-surface" onSubmit={(e) => void save(e)}>
        <h2>Add a source</h2>
        <label>Connection ID<input required value={id} onChange={(e) => setId(e.target.value)} pattern="[A-Za-z0-9_.-]{1,80}" placeholder="northfield-lims" /></label>
        <label>Site<input required value={site} onChange={(e) => setSite(e.target.value)} placeholder="NF1" /></label>
        <label>System<select value={family} onChange={(e) => setFamily(e.target.value)}>{catalog?.families.map((f) => <option key={f.system}>{f.system}</option>)}</select></label>
        <label>Transport<select value={transport} onChange={(e) => setTransport(e.target.value)}>{catalog?.transports.map((t) => <option key={t.transport} value={t.transport} disabled={!t.available}>{t.transport}{t.available ? "" : " — driver not installed"}</option>)}</select></label>
        {transport !== "webhook" && <label>{transport === "file" ? "Export directory" : "Endpoint"}<input required value={endpoint} onChange={(e) => setEndpoint(e.target.value)} placeholder={transport === "file" ? "/approved-exports/lims" : "https://source.example.com"} /></label>}
        {transport === "rest" && <label>Records path<input required value={path} onChange={(e) => setPath(e.target.value)} /></label>}
        {(transport === "rest" || transport === "webhook") && <label>{transport === "webhook" ? "Signing-secret setting" : "Access-token setting (optional)"}<input required={transport === "webhook"} value={credential} onChange={(e) => setCredential(e.target.value)} placeholder="LIMS_READ_TOKEN" /><small>Name of a server environment setting; enter no secret values here.</small></label>}
        {(transport === "mqtt" || transport === "opcua") && <>
          <label>{transport === "mqtt" ? "Topics" : "Node IDs"}<textarea required rows={3} value={addresses} onChange={(e) => setAddresses(e.target.value)} placeholder="One per line" /></label>
          <label>Username setting (optional)<input value={username} onChange={(e) => setUsername(e.target.value)} /></label>
          <label>Password setting (optional)<input value={password} onChange={(e) => setPassword(e.target.value)} /></label>
        </>}
        {transport === "opcua" && <label>Signing/encryption setting<input required value={security} onChange={(e) => setSecurity(e.target.value)} placeholder="OPCUA_SECURITY" /></label>}
        <label>Automatic sync interval (seconds)<input type="number" min={0} step={10} value={pollSeconds} onChange={(e) => setPollSeconds(Number(e.target.value))} /><small>0 means manual sync. Automatic sync requires at least 10 seconds.</small></label>
        <details><summary>Advanced field mapping</summary><p>Leave blank for the system template, or supply a versioned mapping.</p><textarea rows={8} value={mapping} onChange={(e) => setMapping(e.target.value)} aria-label="Field mapping JSON" /><pre>{JSON.stringify(catalog?.families.find((f) => f.system === family)?.template, null, 2)}</pre></details>
        <Button type="submit" variant="primary" disabled={!!busy}>Save connection</Button>
      </form>}
      {!items.length && !error && <p>No connections configured for your accessible sites.</p>}
      <div className="ws-connection-list">{items.map((c) => <section className="ws-connection" key={c.connector_id}>
        <div className="ws-connection-heading"><div><h2>{c.connector_id}</h2><p>{c.family} · {c.transport} · {c.site_id}</p></div><span className="ws-tag">{c.qualification === "supported" ? "Qualified contract" : "Not vendor-qualified"}</span></div>
        <p>Last sync: {c.last_sync ? new Date(c.last_sync).toLocaleString() : "Never"}</p>
        {c.last_error && <p className="cw-error">{c.last_error}</p>}
        {c.last_result && <p>{c.last_result.ingested} ingested · {c.last_result.duplicates} duplicates · {c.last_result.corrections} corrections · {c.last_result.mapping_issues} mapping issues</p>}
        {c.transport === "webhook" && <p>Signed intake: <code>/v1/webhooks/{me?.tenant_id}/{c.connector_id}</code></p>}
        {c.transport !== "mqtt" && <Button disabled={!!busy} onClick={() => void run(c, "preview")}>Preview mapping</Button>}
        <Button disabled={!!busy || c.enabled === false} onClick={() => void run(c, "sync")}>{busy === c.connector_id ? "Working…" : "Sync records"}</Button>
      </section>)}</div>
    </>}
    {error && <p className="cw-error" role="alert">{error}</p>}
    {result && <details open className="cw-command"><summary>Connection result</summary><pre>{JSON.stringify(result, null, 2)}</pre></details>}
  </div>;
}
