import { useCallback, useEffect, useState } from 'react';
import { api } from './api.js';

// Loads data from the API and exposes { data, loading, error, reload }.
export function useApi(path) {
  const [state, setState] = useState({ data: null, loading: !!path, error: null });

  const reload = useCallback(async () => {
    if (!path) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      setState({ data: await api(path), loading: false, error: null });
    } catch (e) {
      setState({ data: null, loading: false, error: e.message });
    }
  }, [path]);

  useEffect(() => {
    reload();
  }, [reload]);

  return { ...state, reload };
}
