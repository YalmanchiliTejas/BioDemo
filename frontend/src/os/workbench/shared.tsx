import type { ReactNode } from "react";
import { RiStackLine, RiArrowRightSLine } from "@remixicon/react";
import { kindLabel, SAMPLE_ID, type WorkItem } from "../workspace-model";

const dateLabel = (date: string) =>
  new Date(date).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });

export function WorkRow({
  work,
  onOpen,
}: {
  work: WorkItem;
  onOpen: () => void;
}) {
  return (
    <button type="button" className="ws-work-row" onClick={onOpen}>
      <span className="ws-work-icon">
        <RiStackLine size={19} />
      </span>
      <span className="ws-work-title">
        <b>{work.goal}</b>
        <span>
          {kindLabel[work.kind]}
          <i />
          {work.context === "sample" ? "F-2408" : "No context"}
        </span>
      </span>
      <span className="ws-work-state">
        {work.id === SAMPLE_ID ? "Ready" : "Draft"}
      </span>
      <span className="ws-work-date">{dateLabel(work.updatedAt)}</span>
      <RiArrowRightSLine size={17} />
    </button>
  );
}

export function PageHead({
  eyebrow,
  title,
  description,
  action: control,
}: {
  eyebrow: string;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <header className="ws-page-head">
      <div>
        <p className="ws-eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {control}
    </header>
  );
}
