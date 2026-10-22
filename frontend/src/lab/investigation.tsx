import { useState } from "react";
import { batch } from "./scenario";
import { useScenario } from "./state";
import { DataAvailability, ProcessStack, TiterChart, useTiterSeries } from "./charts";
import { CheckedInline, EvidenceGroup, Hypotheses, SourceSheet, counts, useEvidence } from "./evidence";
import { ActionCard } from "./review";
import type { Evidence } from "./scenario";
import { AgentMark, Balance, Confidence } from "./ui";

/** The finding, stated once: the agent's sentence, the figures that answer it, and how sure it is. */
export function FindingSummary({ figures = true }: { figures?: boolean }) {
  const { at, value, mean, gap } = useTiterSeries();
  const n = counts(useEvidence());
  return (
    <div className="finding">
      <p className="finding-text">
        <AgentMark size={16} />
        <span>
          Dissolved oxygen fell when agitation reached its limit, soon after heavy antifoam use. That is the leading explanation, not a confirmed cause: one earlier batch argues against it, and the off-gas data that would test it is missing.
        </span>
      </p>
      {figures && (
        <dl className="figures">
          <div className="lead">
            <dt>F-2408 titer at {at} h</dt>
            <dd className="num">
              {value.toFixed(2)}
              <small>g/L</small>
            </dd>
          </div>
          <div>
            <dt>Reference mean, 6 batches</dt>
            <dd className="num">
              {mean.toFixed(2)}
              <small>g/L</small>
            </dd>
          </div>
          <div>
            <dt>Against the mean</dt>
            <dd className="num">
              {"\u2212"}
              {gap}
              <small>%</small>
            </dd>
          </div>
          <div>
            <dt>DO at 48 h, setpoint 40</dt>
            <dd className="num">
              25<small>%</small>
            </dd>
          </div>
        </dl>
      )}
      <div className="finding-status">
        <Confidence level={2} />
        <Balance {...n} />
      </div>
    </div>
  );
}

export function Investigation({ onReview }: { onReview: () => void }) {
  const [source, setSource] = useState<Evidence | null>(null);
  const { reach } = useScenario();
  const open = (e: Evidence) => {
    setSource(e);
    reach("inspect");
  };
  return (
    <div className="grid">
      <section className="panel span-9" aria-labelledby="inv-titer">
        <header className="panel-head">
          <h2 id="inv-titer">Titer against the R7 reference</h2>
          <span className="meta">
            {batch.vessel} · {batch.references.length} prior batches, same recipe and vessel
          </span>
        </header>
        <FindingSummary />
        <div className="inner">
          <TiterChart height={250} />
        </div>
      </section>

      <section className="panel span-3" aria-labelledby="inv-hyp">
        <header className="panel-head">
          <h2 id="inv-hyp">Explanations</h2>
        </header>
        <Hypotheses />
      </section>

      <section className="panel span-12" aria-labelledby="inv-proc">
        <header className="panel-head">
          <h2 id="inv-proc">What moved at the same time</h2>
          <span className="meta">Historian, 1-min data aligned by batch age. Use ← → on a chart to read all three.</span>
        </header>
        <ProcessStack />
      </section>

      <div className="span-6">
        <EvidenceGroup stance="supports" onOpen={open} />
      </div>
      <div className="span-6">
        <EvidenceGroup stance="contradicts" onOpen={open} footer={<CheckedInline />} />
      </div>

      <div className="span-6">
        <EvidenceGroup stance="missing" onOpen={open} />
      </div>
      <section className="panel span-6" aria-labelledby="inv-avail">
        <header className="panel-head">
          <h2 id="inv-avail">What the agent could see</h2>
          <span className="meta">Gaps are drawn as gaps</span>
        </header>
        <DataAvailability />
      </section>

      <div className="span-12">
        <ActionCard onReview={onReview} />
      </div>
      <SourceSheet e={source} onClose={() => setSource(null)} />
    </div>
  );
}
