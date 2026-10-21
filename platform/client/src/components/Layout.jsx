import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../lib/auth.jsx";
import { useProject } from "../lib/project.jsx";
import { COMPONENTS } from "../lib/components.js";
import ThemeToggle from "./ThemeToggle.jsx";
import ServiceBanner from "./ServiceBanner.jsx";
import {
  IconChevron,
  IconData,
  IconOverview,
  IconPlanning,
  IconPullRequest,
  IconQuality,
  IconSignOut,
  IconSprint,
} from "./Icons.jsx";

const COMPONENT_ICONS = {
  planning: IconPlanning,
  sprint: IconSprint,
  quality: IconQuality,
  "pull-request": IconPullRequest,
};

const initials = (name = "") =>
  name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0].toUpperCase())
    .join("") || "?";

export default function Layout() {
  const { user, logout } = useAuth();
  const { projects, projectId, setProjectId } = useProject();

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            DI
          </span>
          <span className="brand-text">
            <span className="brand-name">DevIntel</span>
            <span className="brand-sub">Development intelligence</span>
          </span>
        </div>

        <div className="project-picker">
          <label className="picker-label" htmlFor="project-select">
            Project
          </label>
          <div className="select-wrap">
            <select
              id="project-select"
              value={projectId || ""}
              onChange={(e) => setProjectId(e.target.value)}
            >
              {projects.map((p) => (
                <option key={p.key} value={p.key}>
                  {p.name}
                </option>
              ))}
            </select>
            <span className="select-chevron">
              <IconChevron />
            </span>
          </div>
        </div>

        <nav aria-label="Main">
          <NavLink to="/" end>
            <IconOverview /> <span>Overview</span>
          </NavLink>
          <div className="nav-section">Intelligence</div>
          {COMPONENTS.map((c) => {
            const Icon = COMPONENT_ICONS[c.key];
            return (
              <NavLink key={c.key} to={c.path}>
                {Icon && <Icon />} <span>{c.name}</span>
              </NavLink>
            );
          })}
          <div className="nav-section">Platform</div>
          <NavLink to="/data-sources">
            <IconData /> <span>Data sources</span>
          </NavLink>
        </nav>

        <div className="sidebar-footer">
          <div className="user-card">
            <span className="avatar" aria-hidden="true">
              {initials(user?.name)}
            </span>
            <span className="user-text">
              <span className="user-name">{user?.name}</span>
              <span className="user-role">{user?.role}</span>
            </span>
          </div>
          <div className="footer-actions">
            <ThemeToggle />
            <button
              type="button"
              className="icon-button"
              onClick={logout}
              title="Sign out"
              aria-label="Sign out"
            >
              <IconSignOut />
            </button>
          </div>
        </div>
      </aside>
      <main className="content">
        <ServiceBanner />
        <Outlet />
      </main>
    </div>
  );
}
