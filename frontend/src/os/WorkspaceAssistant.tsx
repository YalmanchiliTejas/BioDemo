import { useMemo, useRef, useState } from "react";
import {
  AssistantRuntimeProvider,
  ComposerPrimitive,
  ThreadPrimitive,
  useLocalRuntime,
  type ThreadMessageLike,
} from "@assistant-ui/react";
import {
  RiArrowRightSLine,
  RiArrowUpLine,
  RiCheckLine,
  RiCloseLine,
  RiShieldCheckLine,
} from "@remixicon/react";
import { useScenario } from "../lab/state";
import { agentSteps, NOW, type Evidence } from "../lab/scenario";
import { useEvidence } from "../lab/evidence";
import {
  AssistantMessage,
  UserMessage,
  makeAdapter,
  order,
  replies,
  type Act,
} from "../lab/ConceptB";
import { tagContext, type Tag } from "../lab/hosts";
import { AgentMark, Button, cx } from "../lab/ui";
import { viewName, type View } from "./WorkspaceShell";

const contextNote = (
  view: View,
  tag: Tag,
): { text: string; linked?: boolean } | null => {
  switch (view) {
    case "historian":
      return { text: tagContext[tag].text, linked: tagContext[tag].linked };
    case "lims":
      return {
        text: "The 36 h and 48 h titer results are below the reference range of 6 prior R7 batches. The 60 h sample is due at 20:00.",
      };
    case "mes":
      return {
        text: "Step 4.3 records the foam alarm at 22 h. Antifoam use rose after it, which is part of the leading explanation.",
      };
    case "qms":
      return {
        text: "I drafted the fields with a teal edge from 8 linked records. Check each one; you save and route it with QMS's own button.",
      };
    default:
      return null;
  }
};

export default function WorkspaceAssistant({
  view,
  tag,
  overlay,
  setOverlay,
  onAct,
  onOpen,
  onDraft,
  onClose,
}: {
  view: View;
  tag: Tag;
  overlay: boolean;
  setOverlay: (v: boolean) => void;
  onAct: (a: Act) => void;
  onOpen: (e: Evidence) => void;
  onDraft: () => void;
  onClose: () => void;
}) {
  const s = useScenario();
  const list = useEvidence();
  const [used, setUsed] = useState<Act[]>([]);
  const actRef = useRef(onAct);
  actRef.current = (a) => {
    setUsed((u) => (u.includes(a) ? u : [...u, a]));
    onAct(a);
  };
  const adapter = useMemo(() => makeAdapter((a) => actRef.current(a)), []);
  const initial: ThreadMessageLike[] = [
    {
      role: "assistant",
      content: `In this sample, batch F-2408 is 18 % below the R7 reference at 48 h. I can guide you through its predefined trends, evidence and review plan. I do not run new investigations or monitor live systems.`,
    },
  ];
  const runtime = useLocalRuntime(adapter, {
    initialMessages: initial,
    maxSteps: 1,
  });
  const next = order.filter((a) => !used.includes(a)).slice(0, 3);
  const note = s.detecting ? null : contextNote(view, tag);
  const missing = list.filter((e) => e.stance === "missing");

  return (
    <div className="assistant-inner">
      <header className="assistant-head">
        <AgentMark size={16} working={s.detecting} />
        <div>
          <h2>Assistant</h2>
          <p>
            Scripted sample guide. No live data access or background monitoring.
          </p>
        </div>
        <button
          type="button"
          className="icon-btn assistant-close"
          aria-label="Close assistant panel"
          onClick={onClose}
        >
          <RiCloseLine size={17} />
        </button>
      </header>
      <p className="assistant-ctx">
        Looking at <b>{viewName[view]}</b>
        {view === "historian" && (
          <>
            {" "}
            ·{" "}
            {tag === "DO"
              ? "BR04.DO.PV"
              : tag === "AG"
                ? "BR04.SIC-110.OUT"
                : tag === "AF"
                  ? "BR04.AF.TOT"
                  : tag === "TEMP"
                    ? "BR04.TEMP.PV"
                    : "BR04.PH.PV"}
          </>
        )}
      </p>
      {s.detecting ? (
        <div className="assistant-body">
          <ol className="steps" role="status" aria-live="polite">
            {agentSteps.map((t, i) => (
              <li
                key={t}
                className={cx(i < s.step && "done", i === s.step && "now")}
              >
                {i < s.step ? (
                  <RiCheckLine size={14} />
                ) : (
                  <span className="pip" />
                )}
                {t}
              </li>
            ))}
          </ol>
        </div>
      ) : (
        <AssistantRuntimeProvider runtime={runtime}>
          <ThreadPrimitive.Root className="assistant-thread">
            <ThreadPrimitive.Viewport className="assistant-body">
              {note && (
                <div
                  className={cx(
                    "assistant-note-card",
                    note.linked === false && "is-quiet",
                  )}
                >
                  <p>{note.text}</p>
                  {view === "historian" && note.linked && (
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => setOverlay(!overlay)}
                      icon={overlay ? <RiCheckLine size={14} /> : undefined}
                    >
                      {overlay
                        ? "Reference shown on this trend"
                        : "Show reference on this trend"}
                    </Button>
                  )}
                  {view === "lims" && (
                    <button
                      type="button"
                      className="link"
                      onClick={() => onOpen(missing[2] ?? missing[0])}
                    >
                      What the 60 h result will tell us
                    </button>
                  )}
                </div>
              )}
              {view !== "qms" && !s.receipt && !s.detecting && (
                <button
                  type="button"
                  className="assistant-draft"
                  onClick={onDraft}
                >
                  <RiShieldCheckLine size={15} />
                  <span>
                    <b>Deviation drafted in QualityTrack</b>
                    <small>
                      3 tasks · no setpoint changes · waiting for your check
                    </small>
                  </span>
                  <RiArrowRightSLine size={16} />
                </button>
              )}
              <ThreadPrimitive.Messages
                components={{ UserMessage, AssistantMessage }}
              />
            </ThreadPrimitive.Viewport>
            <div className="assistant-foot">
              {next.length > 0 && (
                <div className="suggest" aria-label="Suggested questions">
                  {next.map((a) => (
                    <ThreadPrimitive.Suggestion
                      key={a}
                      prompt={replies[a].prompt}
                      send
                      className="chip"
                    >
                      {replies[a].chip}
                    </ThreadPrimitive.Suggestion>
                  ))}
                </div>
              )}
              <ComposerPrimitive.Root className="composer">
                <ComposerPrimitive.Input
                  className="composer-input"
                  placeholder="Ask about this batch"
                  rows={1}
                  aria-label="Ask the Assistant"
                />
                <ComposerPrimitive.Send
                  className="composer-send"
                  aria-label="Send"
                >
                  <RiArrowUpLine size={15} />
                </ComposerPrimitive.Send>
              </ComposerPrimitive.Root>
              <p className="assistant-note">
                Scripted in this prototype. Answers open the record they come
                from.
              </p>
            </div>
          </ThreadPrimitive.Root>
        </AssistantRuntimeProvider>
      )}
    </div>
  );
}
