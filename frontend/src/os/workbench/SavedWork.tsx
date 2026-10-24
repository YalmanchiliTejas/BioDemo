import { useState } from "react";
import { RiStackLine } from "@remixicon/react";
import { useWorkspace } from "../WorkspaceProvider";
import { kindLabel, type WorkKind } from "../workspace-model";
import { Button } from "../../lab/ui";
import { PageHead, WorkRow } from "./shared";

export function SavedWork({ openWork }: { openWork: (id: string) => void }) {
  const { data } = useWorkspace();
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"all" | WorkKind>("all");
  const work = data.work.filter(
    (w) =>
      (filter === "all" || w.kind === filter) &&
      w.goal.toLowerCase().includes(query.toLowerCase()),
  );
  return (
    <div className="ws-page">
      <PageHead eyebrow="" title="Saved work" description="" />
      <div className="ws-filter-bar saved-filters">
        <label>
          <span className="sr-only">Find saved work</span>
          <input
            aria-label="Find saved work"
            placeholder="Find saved work…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <select
          aria-label="Filter work type"
          value={filter}
          onChange={(e) => setFilter(e.target.value as typeof filter)}
        >
          <option value="all">All work types</option>
          {Object.entries(kindLabel).map(([key, label]) => (
            <option key={key} value={key}>
              {label}
            </option>
          ))}
        </select>
      </div>
      {work.length ? (
        <div className="ws-work-list">
          {work.map((w) => (
            <WorkRow key={w.id} work={w} onOpen={() => openWork(w.id)} />
          ))}
        </div>
      ) : (
        <div className="ws-empty">
          <RiStackLine size={28} />
          <h2>No matching work</h2>
          <p>Try a different search or start a new question.</p>
          <Button
            onClick={() => {
              setQuery("");
              setFilter("all");
            }}
          >
            Clear filters
          </Button>
        </div>
      )}
    </div>
  );
}
