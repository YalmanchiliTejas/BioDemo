import { useState } from "react";
import { RiAddLine } from "@remixicon/react";
import { useWorkspace } from "../WorkspaceProvider";
import type { WorkItem } from "../workspace-model";
import { Button, Sheet } from "../../lab/ui";

export function ProposeNextStep({
  work,
  onSaved,
}: {
  work: WorkItem;
  onSaved?: () => void;
}) {
  const { propose } = useWorkspace();
  const [open, setOpen] = useState(false);
  const [fields, setFields] = useState({
    title: "",
    owner: "",
    rationale: "",
    expected: "",
    constraint: "",
  });
  const ready = Object.values(fields).every((value) => value.trim());
  const inputs = [
    ["title", "Proposed next step", "Describe the specific action"],
    ["owner", "Responsible person or role", "Who would own this work?"],
    [
      "rationale",
      "Rationale and uncertainty",
      "Why this step, and what could change the recommendation?",
    ],
    [
      "expected",
      "Expected result or outcome measure",
      "What evidence would tell you whether it helped?",
    ],
    [
      "constraint",
      "Constraints and required approval",
      "What must be reviewed or authorized before proceeding?",
    ],
  ] as const;
  return (
    <>
      <Button variant="primary" onClick={() => setOpen(true)}>
        <RiAddLine size={15} />
        Propose next step
      </Button>
      <Sheet
        open={open}
        onOpenChange={setOpen}
        title="Propose a next step"
        description="A local proposal for your saved work. No operational action is approved or executed."
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Cancel</Button>
            <Button
              variant="primary"
              disabled={!ready}
              onClick={() => {
                propose({ ...fields, workId: work.id, evidenceIds: [] });
                setOpen(false);
                onSaved?.();
                setFields({
                  title: "",
                  owner: "",
                  rationale: "",
                  expected: "",
                  constraint: "",
                });
              }}
            >
              Save proposal
            </Button>
          </>
        }
      >
        <div className="ws-proposal">
          <p>{work.goal}</p>
          {inputs.map(([key, label, placeholder]) => (
            <label key={key}>
              <span>{label}</span>
              {key === "title" || key === "owner" ? (
                <input
                  value={fields[key]}
                  maxLength={500}
                  placeholder={placeholder}
                  onChange={(e) =>
                    setFields((f) => ({ ...f, [key]: e.target.value }))
                  }
                />
              ) : (
                <textarea
                  rows={3}
                  value={fields[key]}
                  maxLength={2000}
                  placeholder={placeholder}
                  onChange={(e) =>
                    setFields((f) => ({ ...f, [key]: e.target.value }))
                  }
                />
              )}
            </label>
          ))}
          <p>
            This proposal has no linked source evidence. It remains a
            user-authored next step, not a verified system recommendation.
          </p>
        </div>
      </Sheet>
    </>
  );
}
