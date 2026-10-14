import { Link } from 'react-router-dom';
import { useProject } from '../lib/project.jsx';
import { useApi } from '../lib/useApi.js';
import { COMPONENTS } from '../lib/components.js';
import InsightCard from '../components/InsightCard.jsx';
import RunAnalysisButton from '../components/RunAnalysisButton.jsx';
import { StatusPill } from '../components/Badge.jsx';

const SEVERITY_RANK = { critical: 4, high: 3, medium: 2, low: 1, info: 0 };

export default function Overview() {
  const { project, projectId } = useProject();
  const q = projectId ? encodeURIComponent(projectId) : null;
  const summary = useApi(q ? `/projects/${q}/summary` : null);
  const health = useApi('/orchestrator/components/health');
  const runs = useApi(q ? `/orchestrator/runs?projectId=${q}` : null);
  const insights = useApi(q ? `/insights?projectId=${q}` : null);

  const reloadAll = () => {
    summary.reload();
    runs.reload();
    insights.reload();
  };

  const counts = summary.data?.counts || {};
  const lastRun = runs.data?.runs?.[0];
  const all = insights.data?.insights || [];
  const top = [...all].sort((a, b) => SEVERITY_RANK[b.severity] - SEVERITY_RANK[a.severity]).slice(0, 4);

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>{project?.name || 'Overview'}</h1>
          <p className="muted">Project health across planning, sprints, code quality and pull requests.</p>
        </div>
        <RunAnalysisButton projectId={projectId} onDone={reloadAll} />
      </header>

      <section className="stat-row">
        {[
          ['Pull requests', counts.pullRequests, `${counts.openPullRequests ?? 0} open`],
          ['Jira issues', counts.issues, `${counts.sprints ?? 0} sprints`],
          ['Quality files', counts.qualityFiles, 'from SonarQube'],
          ['Requirement docs', counts.requirements, 'uploaded'],
          ['Insights', counts.insights, 'in knowledge repository'],
        ].map(([label, value, sub]) => (
          <div className="card stat" key={label}>
            <div className="muted small">{label}</div>
            <div className="stat-value">{value ?? '–'}</div>
            <div className="muted small">{sub}</div>
          </div>
        ))}
      </section>

      <section>
        <h2>Intelligence components</h2>
        <div className="component-grid">
          {COMPONENTS.map((c) => {
            const h = health.data?.components?.find((x) => x.component === c.key);
            const r = lastRun?.components?.find((x) => x.component === c.key);
            const n = all.filter((i) => i.component === c.key).length;
            return (
              <Link to={c.path} className="card component-card" key={c.key}>
                <div className="component-card-head">
                  <h3>{c.name}</h3>
                  <span className={`dot ${h?.up ? 'up' : 'down'}`} title={h?.up ? `Service up (${h.modelVersion})` : `Service down: ${h?.error || 'unknown'}`} />
                </div>
                <p className="muted small">{c.summary}</p>
                <div className="component-card-foot">
                  <span className="small">{n} insight{n === 1 ? '' : 's'}</span>
                  {r && <StatusPill status={r.status} />}
                </div>
              </Link>
            );
          })}
        </div>
        {lastRun && (
          <p className="muted small">
            Last analysis {new Date(lastRun.startedAt).toLocaleString()} by {lastRun.triggeredBy}: {lastRun.status}
          </p>
        )}
      </section>

      <section>
        <h2>Needs attention</h2>
        {top.length === 0 ? (
          <div className="card empty">No insights yet. Run the analysis to generate them.</div>
        ) : (
          <div className="insight-grid">
            {top.map((ins) => (
              <InsightCard key={ins._id} insight={ins} showComponent />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
