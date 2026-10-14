import { useState } from 'react';
import { api } from '../lib/api.js';
import { useAuth } from '../lib/auth.jsx';

// Triggers the AI Orchestrator. Managers only (enforced by the server too).
export default function RunAnalysisButton({ projectId, components, label = 'Run analysis', onDone }) {
  const { isManager } = useAuth();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(null);

  if (!isManager) return null;

  async function run() {
    setBusy(true);
    setMessage(null);
    try {
      const { run } = await api('/orchestrator/run', { method: 'POST', body: { projectId, components } });
      const failed = run.components.filter((c) => c.status !== 'ok');
      const rejected = run.components.reduce((n, c) => n + (c.rejectedCount || 0), 0);
      setMessage(
        failed.length
          ? { kind: 'error', text: `Finished with problems: ${failed.map((c) => `${c.component} (${c.errorMessages?.[0] || c.status})`).join('; ')}` }
          : { kind: 'ok', text: `Done${rejected ? `, ${rejected} invalid insight(s) rejected` : ''}.` }
      );
      onDone?.(run);
    } catch (e) {
      setMessage({ kind: 'error', text: e.message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="run-analysis">
      <button className="btn btn-primary" onClick={run} disabled={busy || !projectId}>
        {busy ? 'Running…' : label}
      </button>
      {message && <span className={message.kind === 'error' ? 'error small' : 'muted small'}>{message.text}</span>}
    </div>
  );
}
