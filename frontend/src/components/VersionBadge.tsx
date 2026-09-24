interface VersionBadgeProps {
  version: string | null;
}

export function VersionBadge({ version }: VersionBadgeProps) {
  if (!version) return <span className="badge badge-error">error</span>;
  const className = version === "baseline" ? "badge-baseline" : "badge-sandbox";
  return <span className={`badge ${className}`}>{version}</span>;
}
