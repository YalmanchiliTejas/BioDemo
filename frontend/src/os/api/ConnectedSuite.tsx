import { lazy, Suspense, useState } from "react";
import { useConnected } from "./ConnectedWorkspace";
import { PageHead } from "../workbench/shared";
import "./suite.css";

const applications = [
  { id: "procedures", label: "Procedures", Component: lazy(() => import("./RecipeDesigner").then((m) => ({ default: m.RecipeDesigner }))) },
  { id: "manufacturing", label: "Manufacturing", Component: lazy(() => import("./ManufacturingWorkspace").then((m) => ({ default: m.ManufacturingWorkspace }))) },
  { id: "laboratory", label: "Laboratory", Component: lazy(() => import("./LaboratoryWorkspace").then((m) => ({ default: m.LaboratoryWorkspace }))) },
  { id: "quality", label: "Quality", Component: lazy(() => import("./QualityWorkspace").then((m) => ({ default: m.QualityWorkspace }))) },
  { id: "network", label: "Transfers and partners", Component: lazy(() => import("./TransferWorkspace").then((m) => ({ default: m.TransferWorkspace }))) },
  { id: "intelligence", label: "Data flows", Component: lazy(() => import("./IntelligenceWorkspace").then((m) => ({ default: m.IntelligenceWorkspace }))) },
  { id: "collaboration", label: "Remote collaboration", Component: lazy(() => import("./CollaborationWorkspace").then((m) => ({ default: m.CollaborationWorkspace }))) },
  { id: "edge", label: "Site gateways", Component: lazy(() => import("./EdgeWorkspace").then((m) => ({ default: m.EdgeWorkspace }))) },
];

export function ConnectedSuite() {
  const { active, client, me } = useConnected();
  const [area, setArea] = useState("procedures");
  const Component = applications.find((a) => a.id === area)!.Component;
  return <div className="suite-page"><PageHead eyebrow="Connected platform" title="Manufacturing suite" description="Versioned procedures, laboratory work, transfers and collaboration share evidence and human decisions." />
    {!active || !client || !me ? <p>Connect to a tenant to use the suite.</p> : <>
      <nav className="suite-tabs" aria-label="Suite applications">{applications.map((a) => <button type="button" key={a.id} aria-current={area === a.id ? "page" : undefined} onClick={() => setArea(a.id)}>{a.label}</button>)}</nav>
      <Suspense fallback={<p role="status">Loading workflow…</p>}><Component key={`${area}:${me.tenant_id}:${me.actor_id}`} /></Suspense>
    </>}
  </div>;
}
