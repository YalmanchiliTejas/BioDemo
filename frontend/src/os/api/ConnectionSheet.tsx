import { useEffect, useState } from "react";
import { Button, Sheet } from "../../lab/ui";
import { createClient, errorMessage, type Health } from "./client";
import { useConnected } from "./ConnectedWorkspace";
import { DEFAULT_ACTOR, DEFAULT_TENANT, isIdentifier } from "./connection";
import { authLabel } from "./mapping";

export function ConnectionSheet({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const cw = useConnected();
  const [tenant, setTenant] = useState(cw.connection.tenant || DEFAULT_TENANT);
  const [actor, setActor] = useState(cw.connection.actor || DEFAULT_ACTOR);
  const [probe, setProbe] = useState<
    { state: "checking" } | { state: "ok"; health: Health } | { state: "down"; message: string }
  >({ state: "checking" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!open) return;
    let alive = true;
    setProbe({ state: "checking" });
    setError("");
    createClient({ tenant: "", actor: "" })
      .health()
      .then(
        (health) => alive && setProbe({ state: "ok", health }),
        (e) => alive && setProbe({ state: "down", message: errorMessage(e) }),
      );
    return () => {
      alive = false;
    };
  }, [open]);
  const valid = isIdentifier(tenant.trim()) && isIdentifier(actor.trim());
  const connect = async () => {
    setBusy(true);
    setError("");
    try {
      await cw.connect(tenant.trim(), actor.trim());
      onOpenChange(false);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Sheet
      open={open}
      onOpenChange={onOpenChange}
      title="Connect to server"
      description="Use records, approvals and people from the server instead of this browser’s sample data."
      footer={
        cw.active ? (
          <>
            <Button onClick={() => onOpenChange(false)}>Close</Button>
            <Button
              onClick={() => {
                cw.disconnect();
                onOpenChange(false);
              }}
            >
              Return to sample mode
            </Button>
          </>
        ) : (
          <>
            <Button onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button
              variant="primary"
              disabled={!valid || busy || probe.state === "down"}
              onClick={() => void connect()}
            >
              {busy ? "Connecting…" : "Connect"}
            </Button>
          </>
        )
      }
    >
      <div className="cw-form">
        {cw.storedProblem && (
          <p className="cw-warn" role="status">
            Saved connection settings could not be read, so sample mode is in use. They were not
            overwritten.
          </p>
        )}
        <p className="cw-probe" role="status">
          {probe.state === "checking" && "Checking the server…"}
          {probe.state === "ok" &&
            `Server reachable${probe.health.backend ? ` · storage: ${probe.health.backend}` : ""}${
              probe.health.models_available ? "" : " · AI drafting unavailable"
            }`}
          {probe.state === "down" && `Server not reachable. ${probe.message}`}
        </p>
        {cw.active && cw.me ? (
          <dl className="cw-facts">
            <div>
              <dt>Connected as</dt>
              <dd>
                {cw.me.actor_id} · {cw.me.tenant_id}
              </dd>
            </div>
            <div>
              <dt>Roles from the server</dt>
              <dd>{cw.me.roles.join(", ") || "none assigned"}</dd>
            </div>
            <div>
              <dt>Sites</dt>
              <dd>{cw.me.site_ids.join(", ") || "none"}</dd>
            </div>
            <div>
              <dt>Sign-in</dt>
              <dd>{authLabel(cw.me.auth_mode)}</dd>
            </div>
          </dl>
        ) : (
          <>
            <label>
              <span>Tenant</span>
              <input
                value={tenant}
                maxLength={128}
                autoCapitalize="none"
                spellCheck={false}
                onChange={(e) => setTenant(e.target.value)}
              />
            </label>
            <label>
              <span>Person</span>
              <input
                value={actor}
                maxLength={128}
                autoCapitalize="none"
                spellCheck={false}
                onChange={(e) => setActor(e.target.value)}
              />
            </label>
            {!valid && (
              <p className="cw-muted">
                Use letters, numbers and . _ : @ - only.
              </p>
            )}
          </>
        )}
        {error && (
          <p className="cw-error" role="alert">
            {error}
          </p>
        )}
        <p className="cw-muted">
          Development sign-in: the server trusts the tenant and person you enter. Roles always
          come from the server’s assignments, never from this screen.
        </p>
        <p className="cw-muted">
          Sample mode keeps working without a server. Work saved in sample mode stays in this
          browser and is not copied to the server.
        </p>
      </div>
    </Sheet>
  );
}
