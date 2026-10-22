import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import * as Tooltip from "@radix-ui/react-tooltip";
import { RiCloseLine, RiDatabase2Line, RiFlaskLine, RiFileList3Line, RiShieldCheckLine } from "@remixicon/react";
import type { Stance, System } from "./scenario";

/** A missing value in a table or timeline: a grey dash, never a zero. */
export const MISSING = "\u2014";

export const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost";
  size?: "sm" | "md";
  kbd?: string;
  icon?: ReactNode;
};
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "secondary", size = "md", kbd, icon, className, children, type = "button", ...rest },
  ref,
) {
  return (
    <button ref={ref} type={type} className={cx("btn", `btn-${variant}`, size === "sm" && "btn-sm", className)} {...rest}>
      {icon}
      {children}
      {kbd && <Kbd>{kbd}</Kbd>}
    </button>
  );
});

export const Kbd = ({ children }: { children: ReactNode }) => (
  <kbd className="kbd" aria-hidden="true">
    {children}
  </kbd>
);

export function Tip({ label, children, side = "top" }: { label: ReactNode; children: ReactNode; side?: "top" | "bottom" | "left" | "right" }) {
  return (
    <Tooltip.Root>
      <Tooltip.Trigger asChild>{children}</Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Content side={side} sideOffset={6} className="lab tip">
          {label}
        </Tooltip.Content>
      </Tooltip.Portal>
    </Tooltip.Root>
  );
}

export function Sheet({
  open,
  onOpenChange,
  title,
  description,
  children,
  width = 520,
  footer,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  title: ReactNode;
  description?: ReactNode;
  children: ReactNode;
  width?: number;
  footer?: ReactNode;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="lab sheet-overlay" />
        <Dialog.Content className="lab sheet" style={{ ["--sheet-w" as string]: `${width}px` }}>
          <header className="sheet-head">
            <div>
              <Dialog.Title className="sheet-title">{title}</Dialog.Title>
              {description ? <Dialog.Description className="sheet-desc">{description}</Dialog.Description> : <Dialog.Description className="sr-only">Details</Dialog.Description>}
            </div>
            <Dialog.Close className="icon-btn" aria-label="Close">
              <RiCloseLine size={18} />
            </Dialog.Close>
          </header>
          <div className="sheet-body">{children}</div>
          {footer && <footer className="sheet-foot">{footer}</footer>}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

/** The agent's mark: wherever text or work came from the agent rather than a source system. */
export function AgentMark({ size = 16, working = false }: { size?: number; working?: boolean }) {
  return (
    <svg className={cx("agent-mark", working && "is-working")} width={size} height={size} viewBox="0 0 16 16" aria-hidden="true">
      <circle cx="8" cy="8" r="6.5" fill="none" stroke="currentColor" strokeWidth="1.5" opacity=".3" />
      <path d="M8 1.5a6.5 6.5 0 0 1 6.5 6.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" className="agent-arc" />
      <circle cx="8" cy="8" r="2.5" fill="currentColor" />
    </svg>
  );
}

/** The product mark: a fermenter in section, impeller on its shaft. */
export function ProductMark({ size = 22 }: { size?: number }) {
  return (
    <svg className="product-mark" width={size} height={size} viewBox="0 0 22 22" aria-hidden="true">
      <rect x="4" y="2" width="14" height="18" rx="7" fill="currentColor" />
      <path d="M11 5v10M7.5 15h7M7.5 11h7" stroke="#fff" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

export const SimNote = ({ children = "Simulated" }: { children?: ReactNode }) => <span className="pill pill-warn">{children}</span>;

const systemIcon: Record<System, ReactNode> = {
  Historian: <RiDatabase2Line size={14} />,
  LIMS: <RiFlaskLine size={14} />,
  MES: <RiFileList3Line size={14} />,
  QMS: <RiShieldCheckLine size={14} />,
};
export const SourceRef = ({ system, refId }: { system: System; refId?: string }) => (
  <span className="source-ref">
    {systemIcon[system]}
    <span>{system}</span>
    {refId && <span className="id">{refId}</span>}
  </span>
);

export const stanceLabel: Record<Stance, string> = { supports: "Supports", contradicts: "Contradicts", missing: "Missing" };
/** Stance is a mark, not a hue: a solid disc, a ring, a dashed ring. */
export const StanceMark = ({ stance }: { stance: Stance }) => (
  <svg className={cx("stance", `is-${stance}`)} width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
    {stance === "supports" && <circle cx="6" cy="6" r="4.5" fill="currentColor" />}
    {stance === "contradicts" && <circle cx="6" cy="6" r="4" fill="none" stroke="currentColor" strokeWidth="1.75" />}
    {stance === "missing" && <circle cx="6" cy="6" r="4" fill="none" stroke="currentColor" strokeWidth="1.5" strokeDasharray="2 1.8" />}
  </svg>
);

export function Confidence({ level, label = true }: { level: 1 | 2 | 3; label?: boolean }) {
  const word = ["Low", "Moderate", "High"][level - 1];
  return (
    <span className="confidence" aria-label={`${word} confidence`}>
      <span className="confidence-bars" aria-hidden="true">
        {[1, 2, 3].map((i) => (
          <i key={i} className={i <= level ? "on" : ""} />
        ))}
      </span>
      {label && <span>{word} confidence</span>}
    </span>
  );
}

export function Balance({ s, c, m }: { s: number; c: number; m: number }) {
  return (
    <span className="balance">
      <span>
        <StanceMark stance="supports" />
        {s} support
      </span>
      <span>
        <StanceMark stance="contradicts" />
        {c} contradict
      </span>
      <span>
        <StanceMark stance="missing" />
        {m} missing
      </span>
    </span>
  );
}
