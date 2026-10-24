import { RiArrowRightLine, RiShieldCheckLine } from "@remixicon/react";
import type { View } from "../WorkspaceShell";
import { connectors } from "../../lab/scenario";
import { useScenario } from "../../lab/state";
import { sourceApps } from "./catalog";
import { PageHead } from "./shared";

export function Sources({ go }: { go: (v: View) => void }) {
  const { assayPosted } = useScenario();
  return (
    <div className="ws-page">
      <PageHead eyebrow="" title="Sources" description="" />
      <div className="ws-notice">
        <RiShieldCheckLine size={18} />
        <p>
          <b>Sample sources.</b> No live systems connected.
        </p>
      </div>
      <div className="ws-connection-list">
        {connectors.map((c) => {
          const a = sourceApps.find((app) => app.system === c.system)!;
          return (
            <section className="ws-connection" key={c.id}>
              <div className="ws-connection-heading">
                <span className="ws-source-icon">
                  <a.icon size={23} />
                </span>
                <div>
                  <h2>
                    {a.name} <span>{c.system}</span>
                  </h2>
                  <p>{c.scope}</p>
                </div>
                <span className="ws-tag">Simulated</span>
              </div>
              <dl>
                <div>
                  <dt>Access scope</dt>
                  <dd>
                    {c.access === "read"
                      ? "Read-only example"
                      : "Draft-only example; human submits"}
                  </dd>
                </div>
                <div>
                  <dt>Recorded retrieval</dt>
                  <dd>{c.lastSync} · sample snapshot</dd>
                </div>
                <div>
                  <dt>Known limits</dt>
                  <dd>
                    {c.system === "Historian"
                      ? "Off-gas gap at 31–44 h; aeration tag unavailable"
                      : c.system === "LIMS"
                        ? assayPosted
                          ? "60 h assay posted in the sample; historical snapshot only"
                          : "60 h assay pending in the sample"
                        : c.system === "MES"
                          ? "Executed records only; no recipe changes"
                          : "Local simulated draft; no live handoff"}
                  </dd>
                </div>
              </dl>
              <button type="button" onClick={() => go(a.view)}>
                Inspect source workspace <RiArrowRightLine size={16} />
              </button>
            </section>
          );
        })}
      </div>
      <details className="studio-connection-requirements">
        <summary>Connection requirements</summary>
        <p>
          Production connections require authorized access and validated
          mappings. Existing systems remain the systems of record.
        </p>
      </details>
    </div>
  );
}
