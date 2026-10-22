import { useMemo, useState } from "react";
import { RiArrowRightSLine, RiCheckLine, RiExternalLinkLine } from "@remixicon/react";
import { checked, evidence as baseEvidence, hypotheses, type Evidence, type Hypothesis, type Stance } from "./scenario";
import { useScenario } from "./state";
import { AgentMark, Button, Confidence, SimNote, Sheet, SourceRef, StanceMark, Tip, cx, stanceLabel } from "./ui";

export function useEvidence() {
  const { assayPosted } = useScenario();
  return useMemo(() => {
    if (!assayPosted) return baseEvidence;
    return baseEvidence.map<Evidence>((e) =>
      e.id === "M3"
        ? {
            ...e,
            id: "S4",
            stance: "supports",
            claim: "The 60 h titer posted at 2.16 g/L, 17 % below the reference mean",
            detail: "The gap has held rather than widened since 48 h.",
            location: "LIMS result 9 · 60 h sample",
            retrieved: "20:14",
            columns: ["Sample", "F-2408", "Reference mean", "Reference range"],
            rows: [["60 h", "2.16 g/L", "2.60 g/L", "2.43–2.77 g/L"]],
            limit: "Confirms the shortfall persists. It does not tell H1 and H2 apart.",
            request: undefined,
          }
        : e,
    );
  }, [assayPosted]);
}

export function counts(list: Evidence[]) {
  return {
    s: list.filter((e) => e.stance === "supports").length,
    c: list.filter((e) => e.stance === "contradicts").length,
    m: list.filter((e) => e.stance === "missing").length,
  };
}

export function EvidenceRow({ e, onOpen, detail = true }: { e: Evidence; onOpen: (e: Evidence) => void; detail?: boolean }) {
  const { requested } = useScenario();
  return (
    <button type="button" className={cx("ev", `is-${e.stance}`)} onClick={() => onOpen(e)} aria-label={`${stanceLabel[e.stance]}: ${e.claim}. Open the source record.`}>
      <StanceMark stance={e.stance} />
      <span className="ev-main">
        <span className="ev-claim">
          {e.claim}
          {e.id === "S4" && <span className="pill pill-neutral">New at 20:14</span>}
        </span>
        {detail && <span className="ev-detail">{e.detail}</span>}
        <span className="ev-meta">
          <SourceRef system={e.system} refId={e.ref} />
          {e.stance !== "missing" && <span>{e.weight}</span>}
          {e.stance === "missing" && requested.includes(e.id) && (
            <span className="ev-done">
              <RiCheckLine size={13} /> Requested
            </span>
          )}
        </span>
      </span>
      <RiArrowRightSLine size={16} className="ev-go" aria-hidden="true" />
    </button>
  );
}

const titles: Record<Stance, string> = {
  supports: "Supports the leading explanation",
  contradicts: "Contradicts it, or points elsewhere",
  missing: "Missing, not inferred",
};

export function EvidenceGroup({ stance, onOpen, detail = true, footer }: { stance: Stance; onOpen: (e: Evidence) => void; detail?: boolean; footer?: React.ReactNode }) {
  const list = useEvidence().filter((e) => e.stance === stance);
  return (
    <section className="panel ev-group" aria-labelledby={`ev-${stance}`}>
      <header className="panel-head">
        <h3 id={`ev-${stance}`}>
          <StanceMark stance={stance} />
          {titles[stance]}
        </h3>
        <span className="meta num">{list.length}</span>
      </header>
      <div className="rows">
        {list.map((e) => (
          <EvidenceRow key={e.id} e={e} onOpen={onOpen} detail={detail} />
        ))}
      </div>
      {footer}
    </section>
  );
}

export function CheckedInline() {
  return (
    <div className="checked-inline">
      <h4>
        <RiCheckLine size={14} /> Checked and unremarkable
      </h4>
      <dl>
        {checked.map((c) => (
          <div key={c.label}>
            <dt>{c.label}</dt>
            <dd>
              <span className="num">{c.value}</span>, {c.note}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

export function CheckedList() {
  return (
    <details className="checked">
      <summary>
        <RiCheckLine size={14} /> Checked and unremarkable · {checked.length}
      </summary>
      <dl>
        {checked.map((c) => (
          <div key={c.label}>
            <dt>{c.label}</dt>
            <dd>
              <span className="num">{c.value}</span> · {c.note}
            </dd>
          </div>
        ))}
      </dl>
    </details>
  );
}

export function HypothesisRow({ h, active, onSelect }: { h: Hypothesis; active?: boolean; onSelect?: () => void }) {
  const Tag = onSelect ? "button" : "div";
  return (
    <Tag type={onSelect ? "button" : undefined} className={cx("hyp", active && "is-active")} onClick={onSelect} aria-pressed={onSelect ? active : undefined}>
      <span className="hyp-top">
        <span className="hyp-title">
          <span className="hyp-id">{h.id}</span> {h.title}
        </span>
        <Confidence level={h.confidence} label={false} />
      </span>
      <span className="hyp-status">
        {h.status} · {["low", "moderate", "high"][h.confidence - 1]} confidence
      </span>
      {active !== false && (
        <>
          <span className="hyp-sum">{h.summary}</span>
          <span className="hyp-change">Would change this: {h.wouldChange}</span>
        </>
      )}
    </Tag>
  );
}

export function Hypotheses({ expandable = true }: { expandable?: boolean }) {
  const [active, setActive] = useState<string>("H1");
  return (
    <div className="rows hyps">
      {hypotheses.map((h) => (
        <HypothesisRow key={h.id} h={h} active={expandable ? active === h.id : undefined} onSelect={expandable ? () => setActive(h.id) : undefined} />
      ))}
    </div>
  );
}

export function SourceActions({ e }: { e: Evidence }) {
  const { requested, request } = useScenario();
  return e.request ? (
    <>
      <span className="foot-note">Uses your site's request process. Nothing is sent from this prototype.</span>
      <Button variant={requested.includes(e.id) ? "secondary" : "primary"} disabled={requested.includes(e.id)} onClick={() => request(e.id)} icon={requested.includes(e.id) ? <RiCheckLine size={16} /> : undefined}>
        {requested.includes(e.id) ? "Request drafted" : e.request}
      </Button>
    </>
  ) : (
    <>
      <span className="foot-note">Read only. The Assistant cannot change source records.</span>
      <Tip label="Opens the record in its own application. Not connected in this prototype.">
        <span>
          <Button disabled icon={<RiExternalLinkLine size={15} />}>
            Open in {e.system}
          </Button>
        </span>
      </Tip>
    </>
  );
}

export function SourceDetail({ e }: { e: Evidence }) {
  return (
    <>
      <section className="agent-note">
        <p className="agent-by">
          <AgentMark size={14} /> Agent's reading
        </p>
        <p>{e.detail}</p>
      </section>
      <section className="record" aria-label="Source record">
        <div className="record-head">
          <SourceRef system={e.system} refId={e.ref} />
          <SimNote>Simulated record</SimNote>
        </div>
        <dl className="record-meta">
          <div>
            <dt>Location</dt>
            <dd>{e.location}</dd>
          </div>
          <div>
            <dt>Retrieved</dt>
            <dd className="num">{e.retrieved} today</dd>
          </div>
          <div className="wide">
            <dt>Query</dt>
            <dd>
              <code>{e.query}</code>
            </dd>
          </div>
        </dl>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                {e.columns.map((c, j) => (
                  <th key={c} scope="col" className={cx(j > 0 && "n")}>
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {e.rows.map((r, i) => (
                <tr key={i} aria-selected={String(r[0]).startsWith("F-2408") || undefined}>
                  {r.map((v, j) => (
                    <td key={j} className={cx(j > 0 && "n num")}>
                      {v}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section className="limit">
        <h4>What this does not show</h4>
        <p>{e.limit}</p>
      </section>
    </>
  );
}

export const SourceTitle = ({ e }: { e: Evidence }) => (
  <span className="src-title">
    <StanceMark stance={e.stance} />
    {stanceLabel[e.stance]} · {e.id}
  </span>
);

export function SourceSheet({ e, onClose }: { e: Evidence | null; onClose: () => void }) {
  if (!e) return null;
  return (
    <Sheet open onOpenChange={(v) => !v && onClose()} width={560} title={<SourceTitle e={e} />} description={e.claim} footer={<SourceActions e={e} />}>
      <SourceDetail e={e} />
    </Sheet>
  );
}
