import { useState } from "react";
import {
  RiArrowRightLine,
  RiLineChartLine,
  RiFileSearchLine,
  RiTaskLine,
} from "@remixicon/react";
import { workflows, type WorkEntry } from "./work-entry";
import "./workflow-gallery.css";

const filters = [
  { id: "all", label: "All work" },
  { id: "understand", label: "Understand" },
  { id: "verify", label: "Verify" },
  { id: "follow", label: "Follow through" },
] as const;
const icons = {
  understand: RiLineChartLine,
  verify: RiFileSearchLine,
  follow: RiTaskLine,
};
export function WorkflowGallery({
  onChoose,
  dark = false,
  compact = false,
}: {
  onChoose: (entry: WorkEntry) => void;
  dark?: boolean;
  compact?: boolean;
}) {
  const [filter, setFilter] = useState<(typeof filters)[number]["id"]>("all");
  return (
    <div
      className={`workflow-gallery${dark ? " workflow-dark" : ""}${compact ? " workflow-compact" : ""}`}
    >
      <div
        className="workflow-filters"
        role="group"
        aria-label="Filter starting points"
      >
        {filters.map((f) => (
          <button
            key={f.id}
            type="button"
            aria-pressed={filter === f.id}
            onClick={() => setFilter(f.id)}
          >
            {f.label}
          </button>
        ))}
      </div>
      <div className="workflow-grid">
        {workflows
          .filter((w) => filter === "all" || w.group === filter)
          .map((w) => {
            const Icon = icons[w.group];
            return (
              <article className="workflow-card" key={w.id}>
                <div className="workflow-card-top">
                  <Icon size={20} aria-hidden="true" />
                  <span>
                    {w.context === "sample"
                      ? "Sample context"
                      : "Your own question"}
                  </span>
                </div>
                <h3>{w.title}</h3>
                <p>{w.description}</p>
                <button
                  type="button"
                  onClick={() =>
                    onChoose({ goal: w.goal, kind: w.kind, context: w.context })
                  }
                >
                  Try this starting point <RiArrowRightLine size={16} />
                </button>
              </article>
            );
          })}
      </div>
    </div>
  );
}
