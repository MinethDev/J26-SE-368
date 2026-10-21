import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { api } from './api.js';

// The project currently being viewed (projectId used by every page).
const ProjectContext = createContext(null);

// Remember the chosen project across page reloads.
const STORAGE_KEY = 'devintel.projectId';
const readSaved = () => {
  try { return localStorage.getItem(STORAGE_KEY); } catch { return null; }
};
const writeSaved = (id) => {
  try {
    if (id) localStorage.setItem(STORAGE_KEY, id);
    else localStorage.removeItem(STORAGE_KEY);
  } catch { /* storage blocked: ignore */ }
};

export function ProjectProvider({ children }) {
  const [projects, setProjects] = useState([]);
  const [projectId, setProjectIdState] = useState(readSaved);
  const [error, setError] = useState(null);

  const setProjectId = useCallback((id) => {
    setProjectIdState(id);
    writeSaved(id);
  }, []);

  const reload = useCallback(async () => {
    try {
      const d = await api('/projects');
      setProjects(d.projects);
      setProjectIdState((cur) => {
        // Keep the saved project if it still exists, otherwise fall back to the first one.
        const next = d.projects.some((p) => p.key === cur) ? cur : d.projects[0]?.key ?? null;
        writeSaved(next);
        return next;
      });
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const project = projects.find((p) => p.key === projectId) || null;
  return <ProjectContext.Provider value={{ projects, project, projectId, setProjectId, reload, error }}>{children}</ProjectContext.Provider>;
}

export const useProject = () => useContext(ProjectContext);