import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { api } from './api.js';

// The project currently being viewed (projectId used by every page).
const ProjectContext = createContext(null);

export function ProjectProvider({ children }) {
  const [projects, setProjects] = useState([]);
  const [projectId, setProjectId] = useState(null);
  const [error, setError] = useState(null);

  const reload = useCallback(async () => {
    try {
      const d = await api('/projects');
      setProjects(d.projects);
      setProjectId((cur) => cur ?? d.projects[0]?.key ?? null);
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
