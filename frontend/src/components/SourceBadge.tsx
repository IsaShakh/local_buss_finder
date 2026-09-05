export function SourceBadge({ code, name }: { code: string; name: string }) {
  return (
    <span className="source-badge" title={name}>
      {code}
    </span>
  );
}
