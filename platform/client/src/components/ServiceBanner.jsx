import { useCallback, useEffect, useState } from 'react';
import { api } from '../lib/api.js';
import { componentByKey } from '../lib/components.js';

const CHECK_EVERY_MS = 30000;

// Warns at the top of every page when the platform API or an AI service is not running.
export default function ServiceBanner() {
  const [down, setDown] = useState([]);
  const [apiDown, setApiDown] = useState(false);
  const [checking, setChecking] = useState(false);

  const check = useCallback(async () => {
    setChecking(true);
    try {
      const d = await api('/orchestrator/components/health');
      setApiDown(false);
      setDown((d.components || []).filter((c) => !c.up));
    } catch {
      setApiDown(true);
      setDown([]);
    } finally {
      setChecking(false);
    }
  }, []);

  useEffect(() => {
    check();
    const timer = setInterval(check, CHECK_EVERY_MS);
    return () => clearInterval(timer);
  }, [check]);

  if (!apiDown && down.length === 0) return null;

  const names = down.map((c) => {
    const port = (c.url || '').split(':').pop();
    return `${componentByKey[c.component]?.name || c.component}${port ? ` (port ${port})` : ''}`;
  });

  return (
    <div className="service-banner" role="alert">
      <div>
        <strong>{apiDown ? 'Cannot reach the DevIntel server.' : `${names.length === 1 ? 'An AI service is' : 'Some AI services are'} not running: ${names.join(', ')}.`}</strong>
        <div className="small">
          {apiDown
            ? 'Start the platform API (npm run dev in platform/server) and check that MongoDB is running.'
            : 'Start them with: python components/run_all_services.py. Analysis for these components will fail until then.'}
        </div>
      </div>
      <button type="button" className="btn btn-small" onClick={check} disabled={checking}>
        {checking ? 'Checking…' : 'Check again'}
      </button>
    </div>
  );
}