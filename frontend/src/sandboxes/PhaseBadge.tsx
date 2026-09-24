import type { SandboxPhase } from "../types";

interface PhaseBadgeProps {
  phase: SandboxPhase;
  message: string;
}

export function PhaseBadge({ phase, message }: PhaseBadgeProps) {
  const className = phase === "Ready" ? "badge-baseline" : phase === "Failed" ? "badge-error" : "badge-sandbox";
  return (
    <span className={`badge ${className}`} title={message || ""}>
      {phase}
    </span>
  );
}
