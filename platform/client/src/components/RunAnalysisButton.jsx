import { useEffect, useState } from 'react';
import { api } from '../lib/api.js';
import { useAuth } from '../lib/auth.jsx';
import { COMPONENTS } from '../lib/components.js';

const mmss = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;

// Triggers the AI Orchestrator. Managers only (enforced by the server too).
// While it runs, shows which components are running (in orchestrator order) and the elapsed time.
export default function RunAnalysisButton({ projectId, components, label = 'Run analysis', onDone }) {
  const { isManager } = useAuth();
  const [busy, setBusy] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [message, setMessage] = useState(null);

  useEffect(() => {
    if (!busy) return undefined;
    setElapsed(0);
    const t = setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, [busy]);

  if (!isManager) return null;

  const order = COMPONENTS.filter((c) => !components || components.includes(c.key)).map((c) => c.name);

  async function run() {
    setBusy(true);
    setMessage(null);
    try {
      const { run } = await api('/orchestrator/run', { method: 'POST', body: { projectId, components } });
      const failed = run.components.filter((c) => c.status !== 'ok');
      const rejected = run.components.reduce((n, c) => n + (c.rejectedCount || 0), 0);
      const made = run.components.reduce((n, c) => n + (c.insightCount || 0), 0);
      setMessage(
        failed.length
          ? { kind: 'error', text: `Finished with problems: ${failed.map((c) => `${c.component} (${c.errorMessages?.[0] || c.status})`).join('; ')}` }
          : { kind: 'ok', text: `Done: ${made} insight${made === 1 ? '' : 's'}${rejected ? `, ${rejected} invalid rejected` : ''}.` }
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
        {busy ? `Running… ${mmss(elapsed)}` : label}
      </button>
      {busy && (
        <span className="muted small run-progress" role="status">
          <span className="spinner" aria-hidden="true" /> {order.join(' → ')}
          {elapsed > 20 && ' (the AI code review can take a few minutes)'}
        </span>
      )}
      {!busy && message && <span className={message.kind === 'error' ? 'error small' : 'ok-text small'} role="status">{message.text}</span>}
    </div>
  );
}
