export function SeverityBadge({ severity = 'info' }) {
  return <span className={`badge sev-${severity}`}>{severity}</span>;
}

export function StubBadge() {
  return (
    <span className="badge stub" title="Placeholder output: the real model is not connected yet">
      stub
    </span>
  );
}

export function StatusPill({ status }) {
  return <span className={`pill status-${status}`}>{status}</span>;
}
