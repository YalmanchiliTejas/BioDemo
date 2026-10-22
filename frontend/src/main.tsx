import React from "react";
import ReactDOM from "react-dom/client";
import "./index.css";

const Landing = React.lazy(() => import("./os/Landing"));
const Hub = React.lazy(() => import("./os/Hub"));
const Benchmarks = React.lazy(() => import("./App"));
const LabApp = React.lazy(() => import("./lab/LabApp"));
const ConceptLabV1 = React.lazy(() => import("./concepts/ConceptLab"));

const path = location.pathname.replace(/\/+$/, "") || "/";
const route = () => {
  if (path === "/app" || path.startsWith("/app/")) return <Hub />;
  if (path.startsWith("/concepts/v1")) return <ConceptLabV1 />;
  if (path === "/concepts" || path.startsWith("/concepts/")) return <LabApp />;
  // The measured-benchmark app keeps its query-string tabs (?tab=cases, ?tab=ingestion) under /benchmarks.
  if (path === "/benchmarks" || location.search.includes("tab=")) return <Benchmarks />;
  return <Landing />;
};

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <React.Suspense fallback={<div className="app-loading" role="status">Opening your workspace…</div>}>{route()}</React.Suspense>
  </React.StrictMode>,
);
