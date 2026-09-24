interface MockBadgeProps {
  mocked: boolean;
}

export function MockBadge({ mocked }: MockBadgeProps) {
  const className = mocked ? "badge-sandbox" : "badge-baseline";
  return <span className={`badge ${className}`}>{mocked ? "mocked" : "real"}</span>;
}
