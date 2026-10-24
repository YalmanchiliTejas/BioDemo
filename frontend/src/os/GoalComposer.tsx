import {
  RiArrowRightLine,
  RiDatabase2Line,
  RiQuestionLine,
  RiLineChartLine,
  RiFileList3Line,
  RiTaskLine,
} from "@remixicon/react";
import { entryExamples, type WorkEntry } from "./work-entry";
import type { WorkContext } from "./workspace-model";
import "./goal-composer.css";

const icons = [RiQuestionLine, RiLineChartLine, RiFileList3Line, RiTaskLine];
const shortNames = [
  "Understand a yield change",
  "Compare batches",
  "Check the evidence",
  "Plan the next step",
];
export function GoalComposer({
  value,
  onChange,
  onSubmit,
  id,
  submitLabel = "Start work",
  dark = false,
}: {
  value: WorkEntry;
  onChange: (value: WorkEntry) => void;
  onSubmit: () => void;
  id: string;
  submitLabel?: string;
  dark?: boolean;
}) {
  return (
    <div className={`goal-composer${dark ? " goal-composer-dark" : ""}`}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (value.goal.trim()) onSubmit();
        }}
      >
        <label className="goal-label" htmlFor={id}>
          Your question or goal
        </label>
        <textarea
          id={id}
          name="goal"
          autoComplete="off"
          value={value.goal}
          maxLength={1200}
          onChange={(e) => onChange({ ...value, goal: e.target.value })}
          placeholder="What would you like to work on?"
          rows={2}
        />
        <div className="goal-toolbar">
          <label className="goal-context">
            <RiDatabase2Line size={15} />
            <span className="goal-label">Starting context</span>
            <select
              aria-label="Starting context"
              name="context"
              value={value.context}
              onChange={(e) =>
                onChange({ ...value, context: e.target.value as WorkContext })
              }
            >
              <option value="sample">Sample batch F-2408</option>
              <option value="none">Add context later</option>
            </select>
          </label>
          <button
            type="submit"
            className="goal-submit"
            disabled={!value.goal.trim()}
          >
            {submitLabel}
            <RiArrowRightLine size={17} />
          </button>
        </div>
      </form>
      <div className="goal-examples" aria-label="Example starting points">
        {entryExamples.map((example, i) => {
          const Icon = icons[i];
          return (
            <button
              type="button"
              key={example.id}
              aria-pressed={value.goal === example.goal}
              onClick={() => {
                onChange({
                  goal: example.goal,
                  kind: example.kind,
                  context: example.context,
                });
                document.getElementById(id)?.focus({ preventScroll: true });
              }}
            >
              <Icon size={15} />
              {shortNames[i]}
            </button>
          );
        })}
      </div>
    </div>
  );
}
