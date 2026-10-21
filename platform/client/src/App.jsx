import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./lib/auth.jsx";
import { ProjectProvider } from "./lib/project.jsx";
import Layout from "./components/Layout.jsx";
import Login from "./pages/Login.jsx";
import Overview from "./pages/Overview.jsx";
import PlanningPage from "./pages/PlanningPage.jsx";
import SprintPage from "./pages/SprintPage.jsx";
import QualityPage from "./pages/QualityPage.jsx";
import PullRequestsPage from "./pages/PullRequestsPage.jsx";
import DataSources from "./pages/DataSources.jsx";

export default function App() {
  const { user, checking } = useAuth();
  if (checking) {
    return (
      <div className="app-loading" role="status">
        <span className="brand-mark" aria-hidden="true">
          DI
        </span>
        <span className="muted small">Loading DevIntel…</span>
      </div>
    );
  }
  if (!user) return <Login />;

  return (
    <ProjectProvider>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Overview />} />
          <Route path="planning" element={<PlanningPage />} />
          <Route path="sprint" element={<SprintPage />} />
          <Route path="quality" element={<QualityPage />} />
          <Route path="pull-requests" element={<PullRequestsPage />} />
          <Route path="data-sources" element={<DataSources />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </ProjectProvider>
  );
}
