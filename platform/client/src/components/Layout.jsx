import { NavLink, Outlet } from 'react-router-dom';
import { useAuth } from '../lib/auth.jsx';
import { useProject } from '../lib/project.jsx';
import { COMPONENTS } from '../lib/components.js';

export default function Layout() {
  const { user, logout } = useAuth();
  const { projects, projectId, setProjectId } = useProject();

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">DI</span>
          <span>DevIntel</span>
        </div>

        <label className="field-label" htmlFor="project-select">Project</label>
        <select id="project-select" value={projectId || ''} onChange={(e) => setProjectId(e.target.value)}>
          {projects.map((p) => (
            <option key={p.key} value={p.key}>{p.name}</option>
          ))}
        </select>

        <nav>
          <NavLink to="/" end>Overview</NavLink>
          <div className="nav-section">Intelligence</div>
          {COMPONENTS.map((c) => (
            <NavLink key={c.key} to={c.path}>{c.name}</NavLink>
          ))}
          <div className="nav-section">Platform</div>
          <NavLink to="/data-sources">Data sources</NavLink>
        </nav>

        <div className="sidebar-footer">
          <div className="user-name">{user?.name}</div>
          <div className="muted small">{user?.role}</div>
          <button className="link-button" onClick={logout}>Sign out</button>
        </div>
      </aside>
      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}
