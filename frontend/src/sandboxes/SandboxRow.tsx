import { DELETING_PHASE } from "../types";
import type { ChainResult, SandboxSummary } from "../types";
import { PhaseBadge } from "./PhaseBadge";
import { TryItResult } from "./TryItResult";

function ageFrom(createdAt: string | null): string {
  if (!createdAt) return "-";
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(createdAt).getTime()) / 1000));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  return `${Math.floor(minutes / 60)}h`;
}

interface SandboxRowProps {
  sandbox: SandboxSummary;
  onOpenMocks: (sandboxId: string) => void;
  onTryIt: (name: string) => void;
  tryItResult: ChainResult | null | undefined;
  tryItLoading: boolean;
  onRequestDelete: (name: string) => void;
}

export function SandboxRow({
  sandbox,
  onOpenMocks,
  onTryIt,
  tryItResult,
  tryItLoading,
  onRequestDelete,
}: SandboxRowProps) {
  const isDeleting = sandbox.phase === DELETING_PHASE;
  return (
    <>
      <tr>
        <td>{sandbox.name}</td>
        <td>
          <PhaseBadge phase={sandbox.phase} message={sandbox.message} />
        </td>
        <td>{sandbox.services.join(", ") || "-"}</td>
        <td>{sandbox.mocks_count}</td>
        <td>{ageFrom(sandbox.created_at)}</td>
        <td className="rule-actions">
          <button onClick={() => onTryIt(sandbox.name)} disabled={tryItLoading || isDeleting}>
            {tryItLoading ? "trying…" : "try it"}
          </button>
          <button onClick={() => onOpenMocks(sandbox.name)} disabled={isDeleting}>
            mocks
          </button>
          <button onClick={() => onRequestDelete(sandbox.name)} disabled={isDeleting}>
            {isDeleting ? "deleting…" : "delete"}
          </button>
        </td>
      </tr>
      {tryItResult && (
        <tr>
          <td colSpan={6}>
            <TryItResult result={tryItResult} />
          </td>
        </tr>
      )}
    </>
  );
}
