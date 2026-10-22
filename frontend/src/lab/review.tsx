import { useEffect, useState } from "react";
import { RiArrowRightLine, RiCheckLine, RiCloseCircleLine, RiForbidLine, RiTimeLine } from "@remixicon/react";
import { action, people } from "./scenario";
import { useScenario } from "./state";
import { useEvidence } from "./evidence";
import { AgentMark, Button, Kbd, MISSING, SimNote, Sheet, SourceRef, StanceMark, cx } from "./ui";

export function ActionCard({ onReview, compact = false }: { onReview: () => void; compact?: boolean }) {
  const { receipt } = useScenario();
  const sent = receipt?.decision === "sent";
  return (
    <section className={cx("panel action", compact && "is-compact")} aria-labelledby="action-h">
      <header className="panel-head">
        <h3 id="action-h">
          <AgentMark size={14} /> {action.title}
        </h3>
        {receipt ? <span className={cx("pill", sent ? "pill-pos" : "pill-neutral")}>{sent ? "Sent for QA approval" : "Declined"}</span> : <span className="pill pill-warn">Awaiting your review</span>}
      </header>
      {!compact && <p className="action-why">{action.why}</p>}
      <ol className="rows action-steps">
        {action.steps.map((s) => (
          <li key={s.id} className={cx("row", receipt && !receipt.steps.includes(s.id) && "is-excluded")}>
            <span>{s.text}</span>
            <small>
              {s.owner} · {s.due}
            </small>
          </li>
        ))}
      </ol>
      {!compact && (
        <p className="action-boundary">
          <RiForbidLine size={14} aria-hidden="true" />
          {action.notProposed}
        </p>
      )}
      <div className="action-foot">
        <span className="action-route">
          <SourceRef system="QMS" refId={action.target.record} />
          <span>{sent ? "Draft created, QA reviewing" : action.target.state}</span>
        </span>
        <Button variant={receipt ? "secondary" : "primary"} onClick={onReview} kbd="R">
          {receipt ? "View receipt" : "Review plan"}
        </Button>
      </div>
    </section>
  );
}

export function ReviewSheet({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const { receipt, setReceipt, reach } = useScenario();
  const list = useEvidence();
  const [steps, setSteps] = useState<string[]>(action.steps.map((s) => s.id));
  const [note, setNote] = useState("");
  const [declining, setDeclining] = useState(false);

  useEffect(() => {
    if (open) reach("review");
  }, [open, reach]);

  const send = () => {
    if (!steps.length) return;
    setReceipt({ decision: "sent", note, at: "09:47", steps });
  };
  const decline = () => {
    if (!note.trim()) return;
    setReceipt({ decision: "declined", note, at: "09:47", steps: [] });
  };

  const onKey = (e: React.KeyboardEvent) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter" && !receipt) {
      e.preventDefault();
      declining ? decline() : send();
    }
  };

  return (
    <Sheet
      open={open}
      onOpenChange={onOpenChange}
      width={600}
      title={receipt ? "Review receipt" : "Review the verification plan"}
      description={receipt ? `${action.target.record} · ${receipt.decision === "sent" ? "sent to QMS as a draft" : "declined"}` : "Prepared by the Assistant. Nothing leaves this screen until you decide."}
      footer={
        receipt ? (
          <>
            <Button variant="ghost" onClick={() => setReceipt(null)}>
              Undo (prototype only)
            </Button>
            <Button variant="primary" onClick={() => onOpenChange(false)}>
              Done
            </Button>
          </>
        ) : declining ? (
          <>
            <Button variant="ghost" onClick={() => setDeclining(false)}>
              Back
            </Button>
            <Button variant="primary" disabled={!note.trim()} onClick={decline} kbd="⌘↵">
              Decline with reason
            </Button>
          </>
        ) : (
          <>
            <Button variant="ghost" onClick={() => setDeclining(true)}>
              Decline…
            </Button>
            <Button variant="primary" disabled={!steps.length} onClick={send} kbd="⌘↵">
              Send to QMS as draft
            </Button>
          </>
        )
      }
    >
      <div className="sheet-stack" onKeyDown={onKey}>
        {receipt ? (
          <Receipt />
        ) : (
          <>
            <section className="agent-note">
              <p className="agent-by">
                <AgentMark size={14} /> Why this, and why now
              </p>
              <p>{action.why}</p>
            </section>

            <section className="review-block">
              <h4>Will be created</h4>
              <div className="target">
                <SourceRef system="QMS" refId={action.target.record} />
                <span>{action.target.type}</span>
                <span className="target-state">{action.target.state}</span>
                <SimNote />
              </div>
              <p className="review-sub">
                Linked evidence ({list.length}):{" "}
                {list.map((e) => (
                  <span key={e.id} className="ev-ref">
                    <StanceMark stance={e.stance} />
                    {e.id}
                  </span>
                ))}
              </p>
            </section>

            <section className="review-block">
              <h4>Tasks to include</h4>
              <ul className="checks">
                {action.steps.map((s) => (
                  <li key={s.id}>
                    <label>
                      <input type="checkbox" checked={steps.includes(s.id)} onChange={(ev) => setSteps(ev.target.checked ? [...steps, s.id] : steps.filter((x) => x !== s.id))} />
                      <span>
                        {s.text}
                        <small>
                          {s.owner} · {s.due}
                        </small>
                      </span>
                    </label>
                  </li>
                ))}
              </ul>
              {!steps.length && <p className="field-hint">Include at least one task, or decline the action.</p>}
            </section>

            <section className="review-block boundary">
              <h4>
                <RiForbidLine size={14} /> Not proposed
              </h4>
              <p>{action.notProposed}</p>
            </section>

            <section className="review-block">
              <h4>
                <RiTimeLine size={14} /> How we'll know
              </h4>
              <p>{action.followUp}</p>
            </section>

            <section className="review-block">
              <h4>Approval route</h4>
              <ol className="route">
                {action.approvals.map((a, i) => (
                  <li key={a} className={i === 0 ? "is-current" : ""}>
                    {a}
                  </li>
                ))}
              </ol>
            </section>

            <label className="field">
              <span>{declining ? "Reason for declining (required)" : "Note to QA (optional)"}</span>
              <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3} placeholder={declining ? "e.g. Off-gas logs already requested under EV-2026-0411" : "Add context for the reviewer"} autoFocus={declining} />
            </label>
            <p className="kbd-hint">
              <Kbd>⌘</Kbd>
              <Kbd>↵</Kbd> to {declining ? "decline" : "send"}
            </p>
          </>
        )}
      </div>
    </Sheet>
  );
}

function Receipt() {
  const { receipt } = useScenario();
  if (!receipt) return null;
  const sent = receipt.decision === "sent";
  const items = sent
    ? [
        { t: "09:42", text: "Drafted by the Assistant from 8 linked records", done: true },
        { t: receipt.at, text: `Reviewed by ${people.you.name} · ${receipt.steps.length} of ${action.steps.length} tasks included`, done: true },
        { t: MISSING, text: `Awaiting ${people.qa.name} (QA) in QMS`, done: false },
        { t: "≈20:00", text: "The Assistant re-assesses when the 60 h titer posts", done: false },
      ]
    : [
        { t: "09:42", text: "Drafted by the Assistant", done: true },
        { t: receipt.at, text: `Declined by ${people.you.name}`, done: true },
        { t: MISSING, text: "The Assistant keeps watching BR-04 and will not re-propose without new evidence", done: false },
      ];
  return (
    <div className="receipt">
      <div className={cx("receipt-banner", sent ? "is-ok" : "is-muted")}>
        {sent ? <RiCheckLine size={18} /> : <RiCloseCircleLine size={18} />}
        <div>
          <b>{sent ? "Draft event created for QA review" : "Action declined"}</b>
          <span>Simulated. No QMS record was written. This is not a GMP signature.</span>
        </div>
      </div>
      <ol className="timeline">
        {items.map((i) => (
          <li key={i.text} className={i.done ? "is-done" : ""}>
            <span className="num">{i.t}</span>
            <span>{i.text}</span>
          </li>
        ))}
      </ol>
      {receipt.note && (
        <blockquote className="receipt-note">
          <span>Your note</span>
          {receipt.note}
        </blockquote>
      )}
      {sent && (
        <p className="receipt-follow">
          <RiArrowRightLine size={14} /> Added to your ongoing work: <b>Follow EV-2026-0418 to closure</b>
        </p>
      )}
    </div>
  );
}
